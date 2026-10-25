"""Client for the AD5X local HTTP API (port 8898).

Deliberately HTTP-only. The printer also speaks a TCP protocol on 8899, but
that one allows a single session at a time and a second connection is reported
to wedge the firmware until the printer is physically power-cycled. Nothing
here ever touches it.

Endpoint shapes follow the community spec at
https://github.com/Parallel-7/flashforge-api-docs (AD5X firmware 1.2.1).
"""
from __future__ import annotations

import base64
import json
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .config import Config
from .pack import gcode_to_3mf

TIMEOUT = 10  # seconds of silence from a printer that did answer
CONNECT_TIMEOUT = 3  # a dead address should not cost the full timeout
UPLOAD_TIMEOUT = 300


DISCOVERY_PORT = 19000
DISCOVERY_TIMEOUT = 1.0

# Knocking on every address of the subnet, when the broadcast stays quiet.
SCAN_TIMEOUT = 1.0
SCAN_WORKERS = 120

MAX_SLOTS = 4  # the IFS holds four spools

# The printer takes a moment to index what it has just received.
LISTING_RETRIES = 6
# Recien subido un fichero la maquina tarda unos segundos en poder
# arrancarlo: hasta entonces /printGcode contesta «Printer is Busy».
INTENTOS_LANZAR = 6
ESPERA_LANZAR = 5.0
LISTING_RETRY_WAIT = 2.5
_MAPPING_FIELDS = (
    "toolId",
    "slotId",
    "materialName",
    "toolMaterialColor",
    "slotMaterialColor",
)


def validate_mappings(mappings: list[dict[str, Any]]) -> None:
    """Catch a bad channel map here rather than mid-print."""
    if len(mappings) > MAX_SLOTS:
        raise PrinterError(
            f"{len(mappings)} herramientas para {MAX_SLOTS} canales del IFS"
        )

    seen: set[int] = set()
    for mapping in mappings:
        missing = [field for field in _MAPPING_FIELDS if field not in mapping]
        if missing:
            raise PrinterError("Falta en el mapeo de color: " + ", ".join(missing))

        slot = mapping["slotId"]
        if not isinstance(slot, int) or not 1 <= slot <= MAX_SLOTS:
            raise PrinterError(f"Canal {slot!r} fuera de rango: van del 1 al {MAX_SLOTS}")
        if slot in seen:
            raise PrinterError(
                f"El canal {slot} está asignado a dos colores; cada uno necesita el suyo"
            )
        seen.add(slot)


class PrinterError(RuntimeError):
    """The printer was reachable but refused, or could not be reached at all."""


def discover(timeout: float = DISCOVERY_TIMEOUT) -> list[tuple[str, str]]:
    """Find Flashforge printers on the local network, as (ip, model).

    This answers over UDP even when the HTTP API is closed, so it tells a
    printer that is merely missing LAN mode apart from one that is off.
    """
    found: dict[str, str] = {}

    # The payload the printer expects is not documented; empty datagrams are
    # enough for the AD5X, the rest are what other models have been seen to want.
    for payload in (b"", b"\x00", b"discover"):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except OSError:
            return []
        with sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(timeout)
            try:
                sock.sendto(payload, ("255.255.255.255", DISCOVERY_PORT))
            except OSError:
                continue

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    data, address = sock.recvfrom(2048)
                except socket.timeout:
                    break
                except OSError:
                    break
                model = data.split(b"\x00", 1)[0].decode("ascii", "replace").strip()
                if model and address[0] not in found:
                    found[address[0]] = model

    return sorted(found.items())


@dataclass(frozen=True)
class Slot:
    """One IFS bay, as the printer reports it."""

    slot_id: int
    colour: str
    material: str
    loaded: bool


@dataclass(frozen=True)
class Status:
    state: str
    machine: str
    nozzle_temp: float | None
    bed_temp: float | None
    job: str | None
    progress: float | None
    layer: int | None
    total_layers: int | None
    elapsed_s: int | None
    remaining_s: int | None
    grams: float | None
    slots: list[Slot]
    raw: dict[str, Any]

    @property
    def busy(self) -> bool:
        return self.state.lower() in {"printing", "busy", "heating", "pausing"}

    @property
    def idle(self) -> bool:
        """Free to take a new job."""
        return self.state.lower() in {"ready", "completed", "idle"}

    @property
    def done_fraction(self) -> float | None:
        """How far along, by layers: printProgress lags too much to use."""
        if self.layer and self.total_layers:
            return min(self.layer / self.total_layers, 1.0)
        return None


class Printer:
    def __init__(self, config: Config) -> None:
        self.config = config
        # The address last known to work. The one in .env is only a hint:
        # with DHCP the printer can come back on a different one, so a
        # remembered address beats it.
        self._host: str | None = self._remembered() or config.printer_ip

    def _memory_file(self):
        return self.config.output_dir.parent / ".ultima-ip"

    def _remembered(self) -> str | None:
        try:
            value = self._memory_file().read_text(encoding="ascii").strip()
        except OSError:
            return None
        return value or None

    def _remember(self, host: str) -> None:
        """So the next run goes straight there instead of searching again."""
        try:
            self._memory_file().write_text(host, encoding="ascii")
        except OSError:
            pass  # a cache we cannot write is not worth an error

    # -- plumbing ----------------------------------------------------------

    @property
    def _auth(self) -> dict[str, str]:
        return {
            "serialNumber": self.config.serial_number or "",
            "checkCode": self.config.check_code or "",
        }

    def _require_config(self) -> None:
        if not self.config.printer_configured:
            raise PrinterError(
                "La impresora no está configurada: faltan PRINTER_SERIAL "
                "o PRINTER_CHECK_CODE en el .env"
            )

    def _answers_here(self, host: str) -> bool:
        """Whether the printer at this address is ours.

        The serial is what identifies it; the discovery broadcast only gives
        the model, which would be ambiguous with two of them on the network.
        """
        try:
            response = requests.post(
                f"http://{host}:{self.config.printer_port}/checkCode",
                json=self._auth,
                timeout=4,
            )
            return response.json().get("code") in (0, "0", 200)
        except (requests.RequestException, ValueError):
            return False

    @staticmethod
    def _local_ip() -> str | None:
        """This machine's address on whatever network it is on right now."""
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            with probe:
                probe.connect(("8.8.8.8", 53))  # no traffic, just routing
                return probe.getsockname()[0]
        except OSError:
            return None

    def _scan(self) -> list[str]:
        """Addresses on this subnet with the printer's port open.

        The UDP broadcast is quicker but does not always answer — on
        2026-10-19 the printer had moved to .113 and stayed silent to
        discovery while serving HTTP perfectly. Knocking on the port finds it
        either way, and a /24 takes about two seconds in parallel.
        """
        local = self._local_ip()
        if local is None:
            return []
        prefix = local.rsplit(".", 1)[0]

        def knock(last: int) -> str | None:
            host = f"{prefix}.{last}"
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(SCAN_TIMEOUT)
                return host if sock.connect_ex((host, self.config.printer_port)) == 0 else None

        with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as pool:
            return [host for host in pool.map(knock, range(1, 255)) if host]

    def _relocate(self) -> str:
        """Find our printer again after its address changed."""
        # Broadcast first (cheap), then knock on every door (reliable).
        seen: list[str] = [ip for ip, _ in discover()]
        for host in seen + [h for h in self._scan() if h not in seen]:
            if self._answers_here(host):
                self._host = host
                self._remember(host)
                return host
            if host not in seen:
                seen.append(host)

        if seen:
            raise PrinterError(
                "Hay algo escuchando en " + ", ".join(seen) + " pero no acepta "
                "este número de serie y código. Vuelve a leerlos en la pantalla "
                "de la impresora: los códigos caducan."
            )
        # Being on a different network is the likeliest reason, and the one
        # a "check the printer" message would send you hunting in the wrong
        # place. Compare where we are with where it was.
        local = self._local_ip()
        conocida = self._remembered() or self.config.printer_ip
        if local and conocida:
            aqui = local.rsplit(".", 1)[0]
            alli = conocida.rsplit(".", 1)[0]
            if aqui != alli:
                raise PrinterError(
                    f"Tu equipo está en la red {aqui}.x y la impresora estaba "
                    f"en {alli}.x: no estáis en la misma red. Si te has "
                    "conectado a los datos del móvil o a otra wifi, vuelve a "
                    "la de casa."
                )

        raise PrinterError(
            "No se encuentra la impresora en la red. Comprueba que está "
            "encendida, en esta misma red y con el modo LAN activo."
        )

    @property
    def host(self) -> str | None:
        return self._host

    def _url(self, path: str) -> str:
        return f"http://{self._host}:{self.config.printer_port}{path}"

    def _post(
        self, path: str, body: dict[str, Any] | None = None, _retry: bool = True
    ) -> dict[str, Any]:
        self._require_config()
        if self._host is None:
            self._relocate()

        payload = {**self._auth, **(body or {})}
        try:
            response = requests.post(
                self._url(path), json=payload, timeout=(CONNECT_TIMEOUT, TIMEOUT)
            )
            response.raise_for_status()
            data = response.json()
        except (requests.Timeout, requests.ConnectionError) as exc:
            # Silence at this address usually means DHCP moved the printer.
            # Look for it again and repeat the call before giving up.
            if _retry:
                self._relocate()
                return self._post(path, body, _retry=False)
            raise PrinterError(
                f"No se puede conectar con la impresora en {self._host}. "
                "Comprueba que está encendida y con el modo LAN activo."
            ) from exc
        except ValueError as exc:
            raise PrinterError("La impresora devolvió algo que no es JSON") from exc
        except requests.HTTPError as exc:
            raise PrinterError(f"HTTP {response.status_code} en {path}") from exc

        if data.get("code") not in (0, "0", 200):
            message = data.get("message") or "sin detalle"
            raise PrinterError(f"La impresora rechazó {path}: {message}")

        return data

    # -- API ---------------------------------------------------------------

    def check(self) -> bool:
        """Validate the serial/check-code pair. Check codes can expire."""
        self._post("/checkCode")
        return True

    def status(self) -> Status:
        detail = self._post("/detail").get("detail", {}) or {}

        def number(*keys: str) -> float | None:
            for key in keys:
                value = detail.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
            return None

        station = detail.get("matlStationInfo") or {}
        slots = [
            Slot(
                slot_id=int(info.get("slotId", index + 1)),
                colour=str(info.get("materialColor") or "#CCCCCC"),
                material=str(info.get("materialName") or "?"),
                loaded=bool(info.get("hasFilament")),
            )
            for index, info in enumerate(station.get("slotInfos") or [])
        ]

        return Status(
            state=str(detail.get("status") or detail.get("machineStatus") or "desconocido"),
            machine=str(detail.get("name") or detail.get("machineType") or "AD5X"),
            nozzle_temp=number("rightTemp", "nozzleTemp"),
            bed_temp=number("platTemp", "bedTemp"),
            job=detail.get("printFileName") or None,
            progress=number("printProgress"),
            # printProgress lags badly (0.4% at layer 22 of 72); layers are
            # what actually tracks the job.
            layer=int(number("printLayer") or 0) or None,
            total_layers=int(number("targetPrintLayer") or 0) or None,
            elapsed_s=int(number("printDuration") or 0) or None,
            remaining_s=int(number("estimatedTime") or 0) or None,
            grams=number("estimatedRightWeight"),
            slots=slots,
            raw=detail,
        )

    def upload(
        self,
        path: Path,
        *,
        print_now: bool = False,
        leveling: bool | None = None,
        mappings: list[dict[str, Any]] | None = None,
    ) -> str:
        """Send a sliced file to the printer, optionally starting it.

        `mappings` points each G-code tool at an IFS slot, for multi-colour
        jobs. Returns the file name as the printer will list it.
        """
        self._require_config()
        if not path.is_file():
            raise PrinterError(f"No existe el fichero {path}")

        # Confirm where the printer is before pushing megabytes at it.
        if self._host is None or not self._answers_here(self._host):
            self._relocate()

        # The printer swallows a bare .gcode but takes minutes to index it, if
        # it ever does; the same job inside a .3mf appears in seconds.
        if path.suffix.lower() == ".gcode":
            # Los canales elegidos van DENTRO del .3mf: la impresora hace caso
            # a lo que lleva el fichero, no a la cabecera de la subida. Sin
            # esto, todo salia del canal 1 eligieras lo que eligieras.
            canales = [int(m["slotId"]) for m in mappings] if mappings else None
            try:
                path = gcode_to_3mf(path, slots=canales)
            except OSError as exc:
                raise PrinterError(f"No se pudo empaquetar el G-code: {exc}") from exc

        level = self.config.leveling_before_print if leveling is None else leveling

        # Elegir bahía solo tiene sentido cuando el G-code tiene varias
        # herramientas. Con una sola, el fichero que genera Orca da por hecho
        # que el filamento YA está cargado: calienta, hace la línea de purga
        # y se pone a imprimir, sin una sola orden que le diga a la estación
        # que cargue nada. Pedirle entonces la bahía 2 deja la boquilla vacía
        # y la pieza sale en aire. Pasó de verdad, 500 capas en vano.
        #
        # Así que con un color se manda tal cual y se imprime con lo que esté
        # puesto. Con varios, la impresión va en dos pasos: subir sin arrancar
        # y después /printGcode con el mapeo, que es donde el firmware sí lo
        # aplica —la cabecera de la subida solo lo registra—.
        varios_colores = bool(mappings) and len(mappings) > 1
        if not varios_colores:
            mappings = None
        en_dos_pasos = bool(print_now and mappings)

        headers = {
            **self._auth,
            "fileSize": str(path.stat().st_size),
            # The spec is explicit: these go as lowercase string booleans.
            "printNow": "false" if en_dos_pasos else ("true" if print_now else "false"),
            "levelingBeforePrint": "true" if level else "false",
        }

        if mappings:
            validate_mappings(mappings)
            # The upload endpoint takes the mapping array base64-encoded in a
            # header. The spec's header note mentions only toolId/slotId while
            # its schema requires five fields, so send all five: a firmware
            # that wants the short form ignores the extras.
            encoded = base64.b64encode(
                json.dumps(mappings, separators=(",", ":")).encode("utf-8")
            ).decode("ascii")
            headers.update(
                {
                    "useMatlStation": "true",
                    "gcodeToolCnt": str(len(mappings)),
                    "materialMappings": encoded,
                }
            )

        try:
            with path.open("rb") as handle:
                response = requests.post(
                    self._url("/uploadGcode"),
                    headers=headers,
                    files={"gcodeFile": (path.name, handle, "application/octet-stream")},
                    timeout=UPLOAD_TIMEOUT,
                )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            raise PrinterError("Se agotó el tiempo subiendo el fichero") from exc
        except requests.ConnectionError as exc:
            raise PrinterError(f"Se perdió la conexión con {self._host}") from exc
        except (ValueError, requests.HTTPError) as exc:
            raise PrinterError(f"La subida falló: {exc}") from exc

        if data.get("code") not in (0, "0", 200):
            raise PrinterError(f"La subida falló: {data.get('message') or 'sin detalle'}")

        # The printer indexes an upload a few seconds after accepting it, so
        # a listing taken straight away does not show it yet. Give it time
        # before saying anything is wrong.
        for attempt in range(LISTING_RETRIES):
            try:
                listado = path.name in self.files()
            except PrinterError:
                listado = True  # the listing failed, not the upload
            if listado:
                if en_dos_pasos:
                    self._lanzar_con_paciencia(path.name, level, mappings)
                return path.name
            if attempt < LISTING_RETRIES - 1:
                time.sleep(LISTING_RETRY_WAIT)

        raise PrinterError(
            f"La impresora aceptó «{path.name}» pero no aparece en su lista "
            f"tras {LISTING_RETRIES * LISTING_RETRY_WAIT:.0f} segundos. "
            "Míralo en su pantalla antes de volver a mandarlo."
        )

    def free_for_work(self) -> bool:
        """Quick look: is it idle and ready for another job?

        Deliberately does not go hunting for the printer — the queue watcher
        asks this every few seconds, and a network sweep each time would be
        absurd. If the address is stale, a real call will relocate it.
        """
        if not self.config.printer_configured or not self._host:
            return False
        try:
            response = requests.post(
                self._url("/detail"), json=self._auth, timeout=(2, 5)
            )
            detail = response.json().get("detail") or {}
        except (requests.RequestException, ValueError):
            return False

        state = str(detail.get("status") or "").lower()
        return state in {"ready", "completed", "idle"}

    def files(self) -> list[str]:
        """What the printer has stored and will list on its screen."""
        data = self._post("/gcodeList")
        return list(data.get("gcodeList") or [])

    def _lanzar_con_paciencia(
        self, nombre: str, level: bool, mappings: list[dict[str, Any]] | None
    ) -> None:
        """Arranca el trabajo en cuanto la impresora deje de estar ocupada.

        Acabada la subida, la máquina sigue unos segundos asentando el
        fichero y contesta «Printer is Busy» a cualquier orden de imprimir.
        No es un fallo: es que se ha llamado demasiado pronto. Se reintenta
        un rato antes de darlo por imposible.

        Y si de verdad está imprimiendo otra cosa, se dice lo que importa:
        que el fichero ya está ahí, y cómo lanzarlo.
        """
        for intento in range(INTENTOS_LANZAR):
            try:
                self.print_file(nombre, leveling=level, mappings=mappings)
                return
            except PrinterError as exc:
                texto = str(exc).lower()
                if "busy" not in texto and "ocupada" not in texto:
                    raise
                if intento == INTENTOS_LANZAR - 1:
                    raise PrinterError(
                        f"«{nombre}» ya está guardado en la impresora, pero no "
                        "ha podido arrancar porque está ocupada. Lánzalo desde "
                        "su pantalla cuando acabe, o añádelo a la cola y se "
                        "manda solo en cuanto quede libre."
                    ) from exc
                time.sleep(ESPERA_LANZAR)

    def print_file(
        self,
        file_name: str,
        *,
        leveling: bool | None = None,
        mappings: list[dict[str, Any]] | None = None,
    ) -> None:
        """Start a file that is already on the printer."""
        level = self.config.leveling_before_print if leveling is None else leveling
        body: dict[str, Any] = {
            "fileName": file_name,
            "levelingBeforePrint": level,
        }
        if mappings:
            validate_mappings(mappings)
            # Here the array goes as plain JSON, not base64.
            body.update(
                {
                    "useMatlStation": True,
                    "gcodeToolCnt": len(mappings),
                    "materialMappings": mappings,
                }
            )
        self._post("/printGcode", body)
