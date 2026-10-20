"""Cola de impresión, que la lleva la app porque la impresora no sabe.

La AD5X acepta un trabajo cada vez: no hay forma de encolar en ella. Así que
la lista se guarda aquí, y en cuanto la impresora queda libre se le manda el
siguiente y se lanza.

El estado vive en un JSON para que sobreviva a un reinicio de la app: si se
cierra la ventana a media tarde, la cola sigue donde estaba.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

CHECK_EVERY = 20  # seconds between looks at the printer
SETTLE_AFTER_SEND = 45  # give the printer time to pick the job up


@dataclass
class Trabajo:
    """Un encargo pendiente: el fichero y con qué color imprimirlo."""

    file: str
    added: str
    mappings: list[dict[str, Any]] | None = None
    label: str = ""
    state: str = "pendiente"  # pendiente | enviado | hecho | error
    detail: str = ""

    @property
    def colour(self) -> str | None:
        if self.mappings:
            return self.mappings[0].get("slotMaterialColor")
        return None


@dataclass
class Cola:
    """La lista, con su candado: la toca el navegador y también el vigilante."""

    path: Path
    items: list[Trabajo] = field(default_factory=list)
    auto: bool = True
    last_error: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # -- persistence -------------------------------------------------------

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        with self._lock:
            self.auto = bool(raw.get("auto", True))
            self.items = [Trabajo(**t) for t in raw.get("items", [])]

    def _save_locked(self) -> None:
        payload = {
            "auto": self.auto,
            "items": [asdict(t) for t in self.items],
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        except OSError:
            pass  # a queue we cannot persist still works in memory

    # -- operations --------------------------------------------------------

    def add(self, file: str, mappings=None, label: str = "") -> Trabajo:
        job = Trabajo(
            file=file,
            added=datetime.now().strftime("%H:%M"),
            mappings=mappings,
            label=label or file,
        )
        with self._lock:
            self.items.append(job)
            self._save_locked()
        return job

    def remove(self, index: int) -> bool:
        with self._lock:
            if not 0 <= index < len(self.items):
                return False
            self.items.pop(index)
            self._save_locked()
            return True

    def move(self, index: int, delta: int) -> bool:
        with self._lock:
            target = index + delta
            if not (0 <= index < len(self.items) and 0 <= target < len(self.items)):
                return False
            self.items[index], self.items[target] = self.items[target], self.items[index]
            self._save_locked()
            return True

    def clear_finished(self) -> None:
        with self._lock:
            self.items = [t for t in self.items if t.state in {"pendiente", "enviado"}]
            self._save_locked()

    def set_auto(self, value: bool) -> None:
        with self._lock:
            self.auto = value
            self._save_locked()

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(t) for t in self.items]

    @property
    def pending(self) -> int:
        with self._lock:
            return sum(1 for t in self.items if t.state == "pendiente")

    def next_pending(self) -> Trabajo | None:
        """The job that should go next, if any."""
        with self._lock:
            return next((t for t in self.items if t.state == "pendiente"), None)

    def mark(self, job: Trabajo, state: str, detail: str = "") -> None:
        with self._lock:
            job.state = state
            job.detail = detail
            self._save_locked()


class Despachador:
    """Vigila la impresora y le va dando los trabajos de la cola."""

    def __init__(
        self,
        cola: Cola,
        is_free: Callable[[], bool],
        send: Callable[[str, list[dict[str, Any]] | None], str],
    ) -> None:
        self.cola = cola
        self.is_free = is_free
        self.send = send
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(CHECK_EVERY):
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 - a watcher must not die
                self.cola.last_error = f"{type(exc).__name__}: {exc}"

    def tick(self, settle: bool = True) -> bool:
        """One look at the printer. Returns True if a job went out."""
        if not self.cola.auto:
            return False

        job = self.cola.next_pending()
        if job is None or not self.is_free():
            return False

        try:
            name = self.send(job.file, job.mappings)
        except Exception as exc:  # noqa: BLE001 - reported on the job itself
            self.cola.mark(job, "error", str(exc))
            self.cola.last_error = str(exc)
            return False

        self.cola.mark(job, "enviado", f"lanzado como {name}")
        if settle:
            # Give the printer time to leave "ready", or the next tick would
            # think it is still free and fire the following job on top.
            time.sleep(SETTLE_AFTER_SEND)
        return True
