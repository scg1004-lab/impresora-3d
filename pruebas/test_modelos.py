r"""Lo que llega de internet, tratado como lo que es: cosa de fuera.

    .venv\Scripts\python.exe pruebas\test_modelos.py

El buscador de Thingiverse baja ficheros de otra gente al ordenador. No se
prueba aquí que la búsqueda encuentre cosas bonitas —eso se ve usándola—,
sino lo que tiene que aguantar aunque la respuesta venga torcida: que el
nombre del fichero lo pongamos nosotros, que nada se escriba fuera de la
carpeta de salida, y que un fichero enorme no entre.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ad5x.modelos as mod  # noqa: E402

fallos: list[str] = []


def con_token(valor):
    """CONFIG con (o sin) token. Es un dataclass congelado: se sustituye entero."""
    return patch.object(mod, "CONFIG", replace(mod.CONFIG, thingiverse_token=valor))


def mal(m: str) -> None:
    fallos.append(m)
    print(f"   FALLO  {m}")


def bien(m: str) -> None:
    print(f"   OK   {m}")


class Respuesta:
    """Una descarga fingida, del tamaño que se le pida."""

    def __init__(self, trozos):
        self._trozos = trozos
        self.status_code = 200

    def raise_for_status(self):
        return None

    def iter_content(self, _n):
        return iter(self._trozos)


def main() -> int:
    print("1. El nombre del fichero lo ponemos nosotros")
    trampas = [
        "../../.env",
        "C:/Windows/system32/algo",
        "..\\..\\fuera",
        "con/barras y espacios",
        "ñandú con acentos",
        "",
    ]
    for t in trampas:
        nombre = mod._nombre_seguro(t, ".stl")
        if any(c in nombre for c in "/\\:") or ".." in nombre or not nombre.endswith(".stl"):
            mal(f"«{t}» -> «{nombre}»")
    else:
        bien("ni barras, ni dos puntos, ni «..» en ninguno")
    if mod._nombre_seguro("", ".stl") != "modelo.stl":
        mal("sin título no sale un nombre usable")

    print("2. Sin token, se dice y no se intenta nada")
    with patch.dict(os.environ, {"THINGIVERSE_TOKEN": ""}), \
         con_token(None):
        if mod.hay_token():
            mal("dice que hay token cuando no lo hay")
        try:
            mod.buscar("llavero")
            mal("ha buscado sin token")
        except mod.ModelosError as exc:
            bien(str(exc)[:60] + "…")

    print("3. Un fichero enorme no entra")
    taller = Path(tempfile.mkdtemp(prefix="modelos-"))
    try:
        gordo = [b"x" * (1 << 20)] * (mod.TOPE // (1 << 20) + 3)
        with patch.dict(os.environ, {"THINGIVERSE_TOKEN": "falso"}), \
             con_token("falso"), \
             patch.object(mod, "_pedir", return_value={
                 "name": "enorme.stl", "download_url": "https://ejemplo/x.stl"}), \
             patch.object(mod.requests, "get", return_value=Respuesta(gordo)):
            try:
                mod.traer(1, 2, "enorme", taller)
                mal("ha aceptado un fichero por encima del tope")
            except mod.ModelosError as exc:
                bien(str(exc)[:60] + "…")
        sobras = list(taller.iterdir())
        if sobras:
            mal(f"ha dejado el fichero a medias: {[p.name for p in sobras]}")
        else:
            bien("no deja nada a medias")

        print("4. Solo se aceptan ficheros que sepamos abrir")
        with patch.dict(os.environ, {"THINGIVERSE_TOKEN": "falso"}), \
             con_token("falso"), \
             patch.object(mod, "_pedir", return_value={
                 "name": "lee_me.exe", "download_url": "https://ejemplo/x.exe"}):
            try:
                mod.traer(1, 2, "raro", taller)
                mal("ha aceptado un .exe")
            except mod.ModelosError as exc:
                bien(str(exc)[:60] + "…")

        print("5. Una descarga normal cae donde debe y con nuestro nombre")
        with patch.dict(os.environ, {"THINGIVERSE_TOKEN": "falso"}), \
             con_token("falso"), \
             patch.object(mod, "_pedir", return_value={
                 "name": "pieza original.stl", "download_url": "https://ejemplo/x.stl"}), \
             patch.object(mod.requests, "get", return_value=Respuesta([b"solid\n"])):
            ruta = mod.traer(1, 2, "Gato articulado", taller)
        if ruta.parent == taller and ruta.name == "gato-articulado.stl":
            bien(ruta.name)
        else:
            mal(f"ha caído en {ruta}")
    finally:
        shutil.rmtree(taller, ignore_errors=True)

    print("\n" + ("TODO CORRECTO" if not fallos else f"{len(fallos)} FALLOS"))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
