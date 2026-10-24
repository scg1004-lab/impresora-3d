"""Local web app: pick a part, set its dimensions, print it.

Binds to 127.0.0.1 on purpose. Parts in `piezas/` are executed as Python, so
this is not something to expose to a network.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

from . import modelos
from .cad import build_part
from .catalog import discover as discover_parts
from .config import BUSCADO, CONFIG, ENV_PATH
from .gcode import default_mappings, is_sliced, read_info
from .mesh import MeshError, threemf_to_stl
from .cola import Cola, Despachador
from .printer import Printer, PrinterError, validate_mappings
from .printer import discover as discover_printers
from .slicer import (
    DEFAULT_MATERIAL,
    DEFAULT_QUALITY,
    SlicerError,
    list_options,
    slice_stl,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="AD5X", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

printer = Printer(CONFIG)

# The printer takes one job at a time, so the queue lives here.
cola = Cola(path=CONFIG.output_dir / ".cola.json")
cola.load()


def _send_job(file: str, mappings) -> str:
    """Hand one queued job to the printer and start it."""
    path = _safe_output(file)
    return printer.upload(path, print_now=True, mappings=mappings)


despachador = Despachador(cola, printer.free_for_work, _send_job)
despachador.start()


def _assets_version() -> str:
    """Newest timestamp of the static files, to bust the browser cache.

    Without this the browser keeps serving the stylesheet it already has, and
    a fix looks like it did nothing.
    """
    stamps = [
        path.stat().st_mtime
        for name in ("static/app.css", "static/app.js")
        if (path := WEB_DIR / name).is_file()
    ]
    return str(int(max(stamps))) if stamps else "0"


def _catalogue():
    """Re-read the folder on every request, so a new part shows up on reload."""
    return discover_parts(CONFIG.parts_dir)


def _safe_output(name: str) -> Path:
    """Resolve a file name strictly inside salida/, never above it."""
    candidate = (CONFIG.output_dir / name).resolve()
    if not candidate.is_relative_to(CONFIG.output_dir.resolve()):
        raise HTTPException(400, "Ruta no permitida")
    if not candidate.is_file():
        raise HTTPException(404, f"No existe {name}")
    return candidate


# --- models ---------------------------------------------------------------

class BuildRequest(BaseModel):
    slug: str
    values: dict[str, Any] = {}


class FileRequest(BaseModel):
    file: str


class SliceRequest(BaseModel):
    file: str
    material: str = DEFAULT_MATERIAL
    quality: str = DEFAULT_QUALITY


class QueueRequest(BaseModel):
    file: str
    mappings: list[dict[str, Any]] | None = None
    label: str = ""


class MoveRequest(BaseModel):
    index: int
    delta: int


class AutoRequest(BaseModel):
    auto: bool


class SendRequest(BaseModel):
    file: str
    print_now: bool = False
    mappings: list[dict[str, Any]] | None = None


# --- pages ----------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    parts, broken = _catalogue()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "parts": [
                {
                    "slug": p.slug,
                    "name": p.name,
                    "description": p.description,
                    "notes": p.notes,
                    "params": [
                        {
                            "name": q.name,
                            "label": q.label,
                            "default": q.default,
                            "unit": q.unit,
                            "min": q.minimum,
                            "max": q.maximum,
                            "step": q.step,
                            "kind": q.kind,
                            "options": list(q.options) if q.options else None,
                            "help": q.help,
                        }
                        for q in p.params
                    ],
                }
                for p in parts.values()
            ],
            "broken": broken,
            "v": _assets_version(),
            "slicer_ready": CONFIG.slicer_available,
            # Para poder decir donde se ha buscado cuando no aparece:
            # «no lo encuentro» a secas no se puede arreglar a distancia.
            "slicer_searched": [] if CONFIG.slicer_available else BUSCADO,
            "options": list_options(CONFIG),
            "default_material": DEFAULT_MATERIAL,
            "default_quality": DEFAULT_QUALITY,
            "printer_ready": CONFIG.printer_configured,
            "modelos_ready": modelos.hay_token(),
        },
    )


# --- api ------------------------------------------------------------------

@app.post("/api/build")
def api_build(request: BuildRequest):
    parts, _ = _catalogue()
    part = parts.get(request.slug)
    if part is None:
        raise HTTPException(404, f"No existe la pieza «{request.slug}»")

    try:
        values = part.coerce_all(request.values)
        result = build_part(part, values, CONFIG.output_dir)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # a part's own build() blowing up
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc

    return {
        # The STL is what the viewer shows and what you would take on a
        # pendrive; a multicolour part also leaves a project for the slicer.
        "file": result.path.name,
        "url": f"/salida/{result.path.name}",
        "slice_file": (result.project or result.path).name,
        "size": result.size_label,
        "volume_cm3": round(result.volume_cm3, 1),
        "warnings": result.warnings,
        "parts": list(result.parts),
    }


@app.post("/api/slice")
def api_slice(request: SliceRequest):
    stl = _safe_output(request.file)
    try:
        result = slice_stl(
            stl, CONFIG, material=request.material, quality=request.quality
        )
    except SlicerError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "file": result.path.name,
        "url": f"/salida/{result.path.name}",
        "estimate": result.estimate,
        "layers": result.layers,
        "filament_cm3": result.filament_cm3,
        "size_kb": result.size_kb,
    }


def _found_on_network() -> list[dict[str, str]]:
    """Printers that answer UDP discovery, to explain an unreachable API."""
    try:
        return [
            {"ip": ip, "model": model}
            for ip, model in discover_printers(timeout=0.8)
        ]
    except Exception:  # discovery is a nicety, never a reason to fail
        return []


@app.get("/api/printer")
def api_printer():
    if not CONFIG.printer_configured:
        # Decir DONDE va el fichero, no solo que falta: quien lo tiene que
        # crear suele estar en otra casa y sin saber que es un «.env».
        return {
            "configured": False,
            "found": _found_on_network(),
            "env_file": str(ENV_PATH),
        }
    try:
        status = printer.status()
    except PrinterError as exc:
        return {
            "configured": True,
            "online": False,
            "error": str(exc),
            "found": _found_on_network(),
        }
    return {
        "configured": True,
        "online": True,
        "slots": [
            {
                "slot_id": slot.slot_id,
                "colour": slot.colour,
                "material": slot.material,
                "loaded": slot.loaded,
            }
            for slot in status.slots
        ],
        "state": status.state,
        "machine": status.machine,
        "nozzle": status.nozzle_temp,
        "bed": status.bed_temp,
        "job": status.job,
        "progress": status.progress,
        "layer": status.layer,
        "total_layers": status.total_layers,
        "busy": status.busy,
    }


@app.post("/api/send")
def api_send(request: SendRequest):
    path = _safe_output(request.file)
    if path.suffix.lower() not in {".gcode", ".3mf", ".gx"}:
        raise HTTPException(
            400,
            "A la impresora solo se le manda el fichero laminado (.gcode/.3mf), no el STL",
        )
    # Check the channel map first: a clash there is the user's mistake to fix,
    # and it should not hide behind a missing-configuration message.
    if request.mappings:
        try:
            validate_mappings(request.mappings)
        except PrinterError as exc:
            raise HTTPException(400, str(exc)) from exc

    try:
        name = printer.upload(
            path, print_now=request.print_now, mappings=request.mappings
        )
    except PrinterError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "file": name,
        "started": request.print_now,
        "message": (
            f"«{name}» enviado y lanzado" if request.print_now
            else f"«{name}» está en la impresora, lánzalo desde su pantalla"
        ),
    }


@app.post("/api/gcode-info")
def api_gcode_info(request: FileRequest):
    """What a sliced file needs: its tools, and a starting channel map."""
    path = _safe_output(request.file)
    if path.suffix.lower() not in {".gcode", ".3mf", ".gx"}:
        raise HTTPException(400, "Eso no es un fichero laminado")

    try:
        info = read_info(path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"No se ha podido leer el fichero: {exc}") from exc

    return {
        "file": path.name,
        "multicolour": info.multicolour,
        "layers": info.layers,
        "estimate": info.estimate,
        "tools": [
            {
                "tool_id": t.tool_id,
                "colour": t.colour,
                "material": t.material,
                "label": t.label,
            }
            for t in info.tools
        ],
        "mappings": default_mappings(info),
    }


MODEL_SUFFIXES = {".stl", ".obj", ".step", ".stp"}
SLICED_SUFFIXES = {".gcode", ".3mf", ".gx"}


@app.post("/api/import")
async def api_import(file: UploadFile = File(...)):
    """Take in a file from outside: a model downloaded from the internet, or
    something already sliced elsewhere."""
    name = Path(file.filename or "").name  # never trust the client's path
    if not name:
        raise HTTPException(400, "Fichero sin nombre")

    suffix = Path(name).suffix.lower()
    if suffix not in MODEL_SUFFIXES | SLICED_SUFFIXES:
        raise HTTPException(
            400,
            "Vale un modelo (.stl, .obj, .step) o algo ya laminado (.gcode, .3mf)",
        )

    CONFIG.output_dir.mkdir(parents=True, exist_ok=True)
    target = CONFIG.output_dir / name
    stem, suffix = target.stem, target.suffix
    index = 2
    while target.exists():  # keep what is already there
        target = CONFIG.output_dir / f"{stem}_{index}{suffix}"
        index += 1

    size = 0
    with target.open("wb") as handle:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            handle.write(chunk)

    # A .3mf can be either: geometry from a model site, or a finished job from
    # a slicer. Only its contents say which, so look inside.
    if is_sliced(target):
        return {"file": target.name, "size_kb": size // 1024, "kind": "sliced"}

    note = None
    if target.suffix.lower() == ".3mf":
        # Model sites hand out 3MF written by a newer slicer than ours, which
        # Orca refuses to open. The geometry inside is fine, so pull it out as
        # an STL, which has no version to argue about.
        stl = target.with_suffix(".stl")
        try:
            triangles = threemf_to_stl(target, stl)
        except MeshError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                400, f"No se ha podido leer la geometría del 3MF: {exc}"
            ) from exc

        target.unlink(missing_ok=True)  # the STL replaces it
        target = stl
        size = target.stat().st_size
        note = f"convertido a STL ({triangles:,} triángulos)".replace(",", ".")

    return {
        "file": target.name,
        "size_kb": size // 1024,
        "kind": "model",
        "note": note,
    }


@app.get("/api/trabajos")
def api_trabajos():
    """What the printer is doing now, what it has stored, and what is queued."""
    actual: dict[str, Any] | None = None
    almacenados: list[str] = []
    error = None

    if CONFIG.printer_configured:
        try:
            status = printer.status()
            actual = {
                "state": status.state,
                "job": status.job,
                "layer": status.layer,
                "total_layers": status.total_layers,
                "done": status.done_fraction,
                "elapsed_s": status.elapsed_s,
                "remaining_s": status.remaining_s,
                "nozzle": status.nozzle_temp,
                "bed": status.bed_temp,
                "busy": status.busy,
            }
            almacenados = printer.files()
        except PrinterError as exc:
            error = str(exc)

    return {
        "configured": CONFIG.printer_configured,
        "actual": actual,
        "error": error,
        "almacenados": almacenados,
        "cola": cola.snapshot(),
        "auto": cola.auto,
        "ultimo_error": cola.last_error,
    }


@app.post("/api/cola")
def api_cola_add(request: QueueRequest):
    _safe_output(request.file)  # fail now if it is not there
    if request.mappings:
        try:
            validate_mappings(request.mappings)
        except PrinterError as exc:
            raise HTTPException(400, str(exc)) from exc

    job = cola.add(request.file, request.mappings, request.label)
    return {"added": job.label, "pending": cola.pending}


@app.post("/api/cola/mover")
def api_cola_move(request: MoveRequest):
    if not cola.move(request.index, request.delta):
        raise HTTPException(400, "No se puede mover ahí")
    return {"cola": cola.snapshot()}


@app.delete("/api/cola/{index}")
def api_cola_remove(index: int):
    if not cola.remove(index):
        raise HTTPException(404, "No hay nada en esa posición")
    return {"cola": cola.snapshot()}


@app.post("/api/cola/auto")
def api_cola_auto(request: AutoRequest):
    cola.set_auto(request.auto)
    return {"auto": cola.auto}


@app.post("/api/cola/limpiar")
def api_cola_clean():
    cola.clear_finished()
    return {"cola": cola.snapshot()}


class LimpiarRequest(BaseModel):
    dias: int = 7


def _en_la_cola(nombre: str) -> bool:
    """¿Hay un trabajo pendiente que use este fichero?"""
    for trabajo in cola.snapshot():
        # «hecho» y «error» ya no esperan nada: esos sí se pueden borrar.
        if trabajo.get("file") == nombre and trabajo.get("state") in {
            "pendiente", "enviado",
        }:
            return True
    return False


def _lo_generado() -> list[Path]:
    """Lo que hay en salida/, sin contar lo que es de la propia app."""
    if not CONFIG.output_dir.is_dir():
        return []
    return sorted(
        (p for p in CONFIG.output_dir.iterdir()
         if p.is_file() and not p.name.startswith(".")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


class TraerRequest(BaseModel):
    modelo_id: int
    fichero_id: int
    titulo: str = ""


@app.get("/api/modelos/buscar")
def api_modelos_buscar(q: str = "", pagina: int = 1):
    """Busca en Thingiverse. Sin token configurado, lo dice y ya está."""
    if not modelos.hay_token():
        return {"token": False, "modelos": []}
    try:
        encontrados = modelos.buscar(q, pagina)
    except modelos.ModelosError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "token": True,
        "modelos": [
            {
                "id": m.id,
                "nombre": m.nombre,
                "autor": m.autor,
                "miniatura": m.miniatura,
                "enlace": m.enlace,
                "likes": m.likes,
            }
            for m in encontrados
        ],
    }


@app.get("/api/modelos/miniatura")
def api_modelos_miniatura(url: str = ""):
    try:
        datos, tipo = modelos.miniatura(url)
    except modelos.ModelosError as exc:
        raise HTTPException(400, str(exc)) from exc
    # Son imágenes que no cambian: que el navegador no las vuelva a pedir.
    return Response(content=datos, media_type=tipo,
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/modelos/{modelo_id}/ficheros")
def api_modelos_ficheros(modelo_id: int):
    try:
        return {"ficheros": modelos.ficheros(modelo_id)}
    except modelos.ModelosError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/modelos/traer")
def api_modelos_traer(request: TraerRequest):
    """Baja el fichero a salida/ y lo deja listo para laminar.

    Un 3MF de las webs de modelos suele venir escrito por un laminador más
    nuevo que el nuestro, y Orca lo rechaza; la geometría de dentro sirve
    igual, así que se saca a STL como ya se hace al traer un fichero a mano.
    """
    try:
        ruta = modelos.traer(
            request.modelo_id, request.fichero_id, request.titulo,
            CONFIG.output_dir,
        )
    except modelos.ModelosError as exc:
        raise HTTPException(400, str(exc)) from exc

    nota = None
    if ruta.suffix.lower() == ".3mf" and not is_sliced(ruta):
        stl = ruta.with_suffix(".stl")
        try:
            triangulos = threemf_to_stl(ruta, stl)
        except Exception as exc:  # noqa: BLE001 - se explica, no se traga
            raise HTTPException(
                400, f"No se ha podido leer la geometría del 3MF: {exc}"
            ) from exc
        ruta.unlink(missing_ok=True)
        ruta = stl
        nota = f"convertido a STL ({triangulos:,} triángulos)".replace(",", ".")

    return {
        "file": ruta.name,
        "size_kb": ruta.stat().st_size // 1024,
        "kind": "model",
        "note": nota,
    }


@app.get("/api/salida")
def api_salida():
    """Lo generado en este ordenador, para poder ir limpiando.

    Lo de la impresora no se puede borrar por red: su API no tiene esa
    función (probado contra la máquina: todas las rutas dan 404, incluida
    una inventada de control). Eso se hace en su pantalla. Esto es lo otro,
    que es lo que de verdad se acumula: cada pieza deja aquí su STL, su
    g-code y su .3mf.
    """
    ahora = time.time()
    ficheros = []
    total = 0
    for ruta in _lo_generado():
        tam = ruta.stat().st_size
        total += tam
        ficheros.append({
            "nombre": ruta.name,
            "kb": tam // 1024,
            "dias": int((ahora - ruta.stat().st_mtime) // 86400),
            "en_cola": _en_la_cola(ruta.name),
        })
    return {"ficheros": ficheros, "total_mb": round(total / 1024 / 1024, 1)}


@app.delete("/api/salida/{name}")
def api_salida_borrar(name: str):
    ruta = _safe_output(name)
    if _en_la_cola(ruta.name):
        raise HTTPException(400, f"«{ruta.name}» está en la cola; quítalo de ahí primero")
    try:
        ruta.unlink()
    except OSError as exc:
        raise HTTPException(400, f"No se ha podido borrar: {exc}") from exc
    return {"borrado": ruta.name}


@app.post("/api/salida/limpiar")
def api_salida_limpiar(request: LimpiarRequest):
    """Borra lo más viejo que los días pedidos. Con 0, todo."""
    limite = time.time() - max(request.dias, 0) * 86400
    borrados, liberado, intocables = 0, 0, 0
    for ruta in _lo_generado():
        if ruta.stat().st_mtime > limite:
            continue
        if _en_la_cola(ruta.name):
            intocables += 1
            continue
        tam = ruta.stat().st_size
        try:
            ruta.unlink()
        except OSError:
            continue
        borrados += 1
        liberado += tam
    return {
        "borrados": borrados,
        "mb": round(liberado / 1024 / 1024, 1),
        "en_cola": intocables,
    }


@app.get("/salida/{name}")
def download(name: str):
    path = _safe_output(name)
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")
