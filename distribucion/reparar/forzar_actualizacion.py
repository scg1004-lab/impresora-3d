r"""Baja la última versión del Taller desde GitHub y la pone, contándolo todo.

Esto existe por un problema de pescadilla: el actualizador del programa es
silencioso a propósito, y cuando no actualiza en un ordenador que no tienes
delante, el arreglo del actualizador no puede llegar **por** el
actualizador. Así que este fichero no depende de nada de lo que haya
instalado: se vale solo, y dice en voz alta cada paso.

Pesa dos kilobytes. Se manda por correo o por WhatsApp junto al
«Actualizar ahora.cmd» y se dejan los dos en la carpeta del Taller, la que
tiene dentro una carpeta «py». Doble clic y listo. No hace falta volver a
pasar el paquete de medio giga.

Hace lo mismo que el actualizador de siempre y con el mismo cuidado: solo
toca el código, nunca `py\`, `modelos\`, `salida\` ni el `.env`; guarda
antes una copia de lo que había; y si algo sale mal, lo deja como estaba.
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = "scg1004-lab/impresora-3d"
RAMA = "main"

CARPETAS = ("ad5x", "piezas", "web", "pruebas", "distribucion")
FICHEROS = (
    "run.py", "requirements.txt", ".env.example", "README.md",
    "LEEME.txt", "Taller AD5X.cmd", "comprobar_impresora.py",
)
IMPRESCINDIBLES = ("ad5x/web.py", "ad5x/catalog.py", "run.py")
RESPALDO = ".anterior-reparacion"


def decir(mensaje: str) -> None:
    print(mensaje, flush=True)


def version_publicada() -> str:
    peticion = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/commits/{RAMA}",
        headers={"Accept": "application/vnd.github.sha", "User-Agent": "taller-ad5x"},
    )
    with urllib.request.urlopen(peticion, timeout=20) as respuesta:
        return respuesta.read(64).decode("utf-8", "replace").strip()


def descargar(sha: str) -> zipfile.ZipFile:
    peticion = urllib.request.Request(
        f"https://codeload.github.com/{REPO}/zip/{sha}",
        headers={"User-Agent": "taller-ad5x"},
    )
    with urllib.request.urlopen(peticion, timeout=120) as respuesta:
        return zipfile.ZipFile(io.BytesIO(respuesta.read(20 * 1024 * 1024)))


def utiles(zf: zipfile.ZipFile) -> dict:
    """Los miembros que nos sirven, sin fiarse de las rutas que traigan."""
    salida = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        partes = info.filename.split("/")[1:]
        if not partes or any(p in ("..", "", ".") or ":" in p for p in partes):
            continue
        if partes[0] not in CARPETAS and "/".join(partes) not in FICHEROS:
            continue
        salida["/".join(partes)] = info
    return salida


def main() -> int:
    raiz = Path(__file__).resolve().parent
    decir(f"Carpeta del Taller: {raiz}")

    if not (raiz / "py" / "python.exe").is_file():
        decir("\n  Esto no es la carpeta del Taller: aquí no hay ninguna «py».")
        decir("  Copia este fichero al lado de «Taller AD5X.cmd» y repite.")
        return 1

    marca = raiz / ".version"
    tenia = marca.read_text(encoding="utf-8").strip() if marca.is_file() else ""
    decir(f"Versión que tienes:  {tenia[:7] or '(ninguna apuntada)'}")

    decir("\nPreguntando a GitHub…")
    try:
        sha = version_publicada()
    except Exception as exc:  # noqa: BLE001 - aquí sí se cuenta todo
        decir(f"  No se ha podido: {type(exc).__name__}: {exc}")
        decir("\n  Casi siempre es que este ordenador no tiene internet,")
        decir("  o que un antivirus corta la conexión con github.com.")
        return 1
    decir(f"  La última publicada es: {sha[:7]}")

    if sha == tenia:
        decir("\n  Ya tienes la última. No hay nada que hacer.")
        decir("  Si aun así no ves lo nuevo, puede que estés abriendo")
        decir("  OTRA carpeta distinta de esta.")
        return 0

    decir("\nDescargando…")
    try:
        zf = descargar(sha)
        miembros = utiles(zf)
    except Exception as exc:  # noqa: BLE001
        decir(f"  No se ha podido descargar: {type(exc).__name__}: {exc}")
        return 1
    decir(f"  {len(miembros)} ficheros")

    faltan = [n for n in IMPRESCINDIBLES if n not in miembros]
    if faltan:
        decir(f"  La descarga viene incompleta (falta {faltan[0]}). No toco nada.")
        return 1

    respaldo = raiz / RESPALDO
    shutil.rmtree(respaldo, ignore_errors=True)
    try:
        respaldo.mkdir(parents=True)
        for nombre in CARPETAS:
            if (raiz / nombre).is_dir():
                shutil.copytree(raiz / nombre, respaldo / nombre)
        for nombre in FICHEROS:
            if (raiz / nombre).is_file():
                shutil.copy2(raiz / nombre, respaldo / nombre)
        decir(f"\nCopia de seguridad en «{RESPALDO}»")
    except Exception as exc:  # noqa: BLE001
        decir(f"\n  No puedo escribir en esta carpeta: {type(exc).__name__}: {exc}")
        decir("  Eso explicaría que el programa tampoco pueda actualizarse solo.")
        decir("  Suele ser el antivirus, o que la carpeta está en Archivos de")
        decir("  programa. Prueba a mover el Taller al Escritorio.")
        return 1

    decir("Poniendo la versión nueva…")
    try:
        for nombre in CARPETAS:
            if (raiz / nombre).is_dir() and any(
                r.startswith(nombre + "/") for r in miembros
            ):
                shutil.rmtree(raiz / nombre)
        for ruta, info in miembros.items():
            destino = raiz / ruta
            if not destino.resolve().is_relative_to(raiz.resolve()):
                raise ValueError(f"ruta rara en el ZIP: {ruta}")
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(zf.read(info))
        marca.write_text(sha, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        decir(f"  Ha fallado: {type(exc).__name__}: {exc}")
        decir(f"  Lo de antes está intacto en «{RESPALDO}».")
        return 1

    decir(f"\n  LISTO. Ahora tienes la versión {sha[:7]}.")
    decir("  Cierra esta ventana y abre el Taller con «Taller AD5X.cmd».")
    decir(f"  Si todo va bien, puedes borrar la carpeta «{RESPALDO}».")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - que nunca se cierre sin decir nada
        decir(f"\n  Algo ha salido mal: {type(exc).__name__}: {exc}")
        sys.exit(1)
