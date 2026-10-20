"""Slice an STL with the Orca command line.

Orca is optional: without it the app still produces the STL, which is all you
need to open the model in the slicer by hand. With it, the whole chain runs
unattended.

Profiles come from the ones Orca-Flashforge ships for the AD5X, so there is
nothing to export by hand. Dropping your own JSON in `perfiles/` overrides
them.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .config import Config

SLICE_TIMEOUT = 600  # a dense plate on a slow machine can take minutes

DEFAULT_NOZZLE = "0.4"
DEFAULT_MATERIAL = "Flashforge PLA Basic"
DEFAULT_QUALITY = "0.20mm Standard"


class SlicerError(RuntimeError):
    pass


@dataclass(frozen=True)
class Sliced:
    path: Path
    estimate: str | None
    filament_cm3: float | None
    layers: int | None

    @property
    def size_kb(self) -> int:
        return self.path.stat().st_size // 1024


def _nozzle_of(name: str) -> str:
    """The nozzle a profile is for. Profiles without a suffix are the 0.4."""
    match = re.search(r"(\d\.\d+)\s*nozzle", name)
    return match.group(1) if match else "0.4"


def _usable(path: Path) -> bool:
    """Whether Orca will accept this profile.

    Three of the filament profiles Flashforge ships (ABS Basic, ASA Basic,
    PLA LW) have no `type` key, and the slicer rejects them outright with
    "unknown config type". Offering them in the list would just hand you a
    failure later.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("type") == "filament"
    except (OSError, ValueError):
        return False


def _options(folder: Path, kind: str, nozzle: str) -> list[Path]:
    """AD5X profiles of one kind that match the nozzle fitted."""
    directory = folder / kind
    if not directory.is_dir():
        return []
    found = sorted(
        path
        for path in directory.glob("*AD5X*.json")
        if _nozzle_of(path.stem) == nozzle
    )
    if kind == "filament":
        found = [p for p in found if _usable(p)]
    return found


def list_options(config: Config, nozzle: str = DEFAULT_NOZZLE) -> dict[str, list[str]]:
    """Materials and layer heights available for the AD5X, for the UI."""
    if config.system_profiles is None:
        return {"materials": [], "qualities": []}

    def label(path: Path) -> str:
        # "Flashforge PLA Basic @FF AD5X" -> "Flashforge PLA Basic"
        return path.stem.split("@")[0].strip()

    return {
        "materials": [label(p) for p in _options(config.system_profiles, "filament", nozzle)],
        "qualities": [label(p) for p in _options(config.system_profiles, "process", nozzle)],
    }


def _pick(folder: Path, kind: str, wanted: str, nozzle: str) -> Path:
    for path in _options(folder, kind, nozzle):
        if path.stem.split("@")[0].strip().lower() == wanted.lower():
            return path
    raise SlicerError(
        f"No hay perfil de {kind} llamado «{wanted}» para boquilla de {nozzle} mm"
    )


def _machine(folder: Path, nozzle: str) -> Path:
    """The machine profile for this nozzle. Vendor files vary in capitalisation."""
    wanted = f"ad5x {nozzle} nozzle.json"
    for path in (folder / "machine").glob("*.json"):
        if path.name.lower().endswith(wanted):
            return path
    raise SlicerError(f"No hay perfil de máquina AD5X para boquilla de {nozzle} mm")


def _user_profiles(config: Config) -> tuple[list[Path], list[Path]]:
    """Anything in perfiles/ takes precedence over the vendor profiles."""
    if not config.profiles_dir.is_dir():
        return [], []
    found = sorted(config.profiles_dir.glob("*.json"))
    filaments = [p for p in found if "filament" in p.stem.lower()]
    settings = [p for p in found if p not in filaments]
    return settings, filaments


def _profile_args(
    config: Config, material: str, quality: str, nozzle: str
) -> list[str]:
    settings, filaments = _user_profiles(config)

    if not settings and config.system_profiles is not None:
        settings = [
            _machine(config.system_profiles, nozzle),
            _pick(config.system_profiles, "process", quality, nozzle),
        ]
    if not filaments and config.system_profiles is not None:
        filaments = [_pick(config.system_profiles, "filament", material, nozzle)]

    missing = [p for p in settings + filaments if not p.is_file()]
    if missing:
        raise SlicerError(
            "Falta el perfil " + ", ".join(p.name for p in missing)
        )

    args: list[str] = []
    if settings:
        args += ["--load-settings", ";".join(str(p) for p in settings)]
    if filaments:
        args += ["--load-filaments", ";".join(str(p) for p in filaments)]
    return args


def _read_metadata(gcode: Path) -> tuple[str | None, float | None, int | None]:
    """Pull time, material and layer count out of the G-code header."""
    estimate = volume = layers = None
    with gcode.open("r", encoding="utf-8", errors="ignore") as handle:
        for index, line in enumerate(handle):
            if index > 400:  # it is all in the header block
                break
            if estimate is None and "estimated printing time (normal mode)" in line:
                estimate = line.split("=", 1)[1].strip()
            elif volume is None and "filament used [cm3]" in line:
                try:
                    volume = float(line.split("=", 1)[1])
                except ValueError:
                    pass
            elif layers is None and "total layer number" in line:
                try:
                    layers = int(line.split(":", 1)[1])
                except ValueError:
                    pass
    return estimate, volume, layers


def _es_proyecto(path: Path) -> bool:
    """Un .3mf de los nuestros: lleva partes con su color asignado."""
    if path.suffix.lower() != ".3mf" or not zipfile.is_zipfile(path):
        return False
    with zipfile.ZipFile(path) as z:
        return "Metadata/model_settings.config" in z.namelist()


def _con_material(proyecto: Path, filamento: Path, destino: Path) -> Path:
    """Copia del proyecto con el material elegido metido dentro.

    Un proyecto lleva sus ajustes embebidos y Orca los prefiere a los de la
    línea de órdenes: sin esto, una pieza de dos colores se imprimiría con el
    perfil que traía la plantilla (ABS a 240°) en vez del que has elegido.
    """
    from .perfiles import aplicar_filamento, resolver

    perfil = resolver(filamento)
    with zipfile.ZipFile(proyecto) as z:
        piezas = {n: z.read(n) for n in z.namelist()}

    bruto = piezas.get("Metadata/project_settings.config")
    if bruto:
        try:
            ajustes = json.loads(bruto.decode("utf-8"))
            extrusores = len(ajustes.get("filament_type") or ["", ""])
            ajustes = aplicar_filamento(ajustes, perfil, extrusores)
            piezas["Metadata/project_settings.config"] = json.dumps(ajustes).encode()
        except (ValueError, KeyError):
            pass  # mejor laminar con la plantilla que no laminar

    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for nombre, datos in piezas.items():
            z.writestr(nombre, datos)
    return destino


def slice_stl(
    stl: Path,
    config: Config,
    *,
    material: str = DEFAULT_MATERIAL,
    quality: str = DEFAULT_QUALITY,
    nozzle: str = DEFAULT_NOZZLE,
    output_dir: Path | None = None,
) -> Sliced:
    if not config.slicer_available:
        raise SlicerError(
            "No se ha encontrado Orca. Instala Orca-Flashforge, o apunta "
            "SLICER_EXE en el .env al ejecutable."
        )

    assert config.slicer_exe is not None  # narrowed by slicer_available
    target_dir = output_dir or stl.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    entrada = stl
    if _es_proyecto(stl) and config.system_profiles is not None:
        try:
            entrada = _con_material(
                stl,
                _pick(config.system_profiles, "filament", material, nozzle),
                target_dir / f"{stl.stem}_listo.3mf",
            )
        except SlicerError:
            raise
        except Exception:
            entrada = stl  # si algo falla, al menos se lamina

    # Orca siempre escribe «plate_1.gcode», así que dos laminados a la vez en
    # la misma carpeta se pisan: uno se lleva el fichero del otro, o se
    # encuentra con que ya no está. Cada uno en su propia carpeta y se acabó.
    # (Pasó de verdad: el navegador lamina solo al traer un modelo, y basta
    # con que haya otro laminado en marcha para que uno de los dos acabe con
    # el g-code equivocado. Eso es peor que un error: imprimes otra cosa.)
    with tempfile.TemporaryDirectory(prefix="taller-ad5x-") as taller:
        obrador = Path(taller)
        command = [
            str(config.slicer_exe),
            str(entrada),
            *_profile_args(config, material, quality, nozzle),
            "--orient", "1",
            "--arrange", "1",
            "--slice", "0",
            "--outputdir", str(obrador),
        ]

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=SLICE_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SlicerError(f"El laminado superó {SLICE_TIMEOUT}s") from exc
        except OSError as exc:
            raise SlicerError(f"No se pudo lanzar Orca: {exc}") from exc

        log = (process.stdout or "") + (process.stderr or "")

        if process.returncode != 0:
            tail = "\n".join(log.strip().splitlines()[-12:]) or "sin salida"
            raise SlicerError(f"Orca terminó con código {process.returncode}:\n{tail}")

        produced = sorted(
            obrador.glob("plate_*.gcode"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not produced:
            tail = "\n".join(log.strip().splitlines()[-12:]) or "sin salida"
            raise SlicerError(f"Orca no dejó ningún .gcode.\n{tail}")

        if entrada != stl:
            entrada.unlink(missing_ok=True)  # copia de trabajo, ya no hace falta

        # Mover el resultado tampoco puede tirar la petición abajo: si el
        # fichero de destino lo tiene abierto otro programa, eso es un aviso
        # que se entiende, no un error 500 sin explicación.
        final = target_dir / f"{stl.stem}.gcode"
        try:
            if final.exists():
                final.unlink()
            shutil.move(str(produced[0]), str(final))
        except OSError as exc:
            raise SlicerError(
                f"No se ha podido guardar «{final.name}»: {exc}. "
                "¿Lo tienes abierto en otro programa?"
            ) from exc

    try:
        estimate, volume, layers = _read_metadata(final)
    except OSError as exc:
        raise SlicerError(f"No se ha podido leer «{final.name}»: {exc}") from exc
    return Sliced(path=final, estimate=estimate, filament_cm3=volume, layers=layers)
