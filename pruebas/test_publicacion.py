r"""Comprueba que no se publica nada que deba quedarse en casa.

    .venv\Scripts\python.exe pruebas\test_publicacion.py

El repositorio es público: cualquiera lo puede leer. Lo que no debe salir de
aquí no es solo el `.env` —ese está en el `.gitignore` y es el caso fácil—,
sino los datos de la impresora y las rutas del ordenador de casa colados
dentro de otros ficheros: un ejemplo en el README, la ruta absoluta que Orca
deja escrita dentro de un 3MF exportado, el nombre de usuario de Windows en
un camino cualquiera.

Mira los ficheros que git va a publicar de verdad, y también dentro de los
que son ZIP (un 3MF lo es), porque ahí es donde no se mira nunca.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ad5x.config import CONFIG  # noqa: E402

# Cosas que nunca pueden aparecer en lo publicado, vengan de donde vengan.
# Las de longitud ridícula se descartan solas: buscar "a" daría siempre.
MINIMO = 4


def agujas() -> dict[str, str]:
    fuentes = {
        "el número de serie de la impresora": CONFIG.serial_number or "",
        "el check code de la impresora": CONFIG.check_code or "",
        "la IP de la impresora": CONFIG.printer_ip or "",
        "el usuario de Windows": os.environ.get("USERNAME", ""),
        "la ruta del disco de proyectos": str(RAIZ),
    }
    return {k: v for k, v in fuentes.items() if v and len(v) >= MINIMO}


# Además de lo de arriba, cualquier cosa con esta pinta es sospechosa por sí
# sola, aunque no coincida con la configuración de este ordenador.
PATRONES = {
    "una ruta absoluta de Windows": re.compile(rb"[A-Za-z]:\\\\?[A-Za-z0-9_ ]+", re.I),
    "una IP de red local": re.compile(rb"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
}
# Rutas que son de Windows, no de nadie: el instalador de Orca vive ahí y
# decirlo no cuenta nada de este ordenador.
DE_LA_CASA = re.compile(rb"^[A-Za-z]:\\\\?(Program Files|Windows|ProgramData)", re.I)
# Donde esas pintas son legítimas y no hay nada que esconder.
PERDONADOS = {
    "README.md",            # explica rutas y redes; se revisa a mano
    ".env.example",         # son los huecos a rellenar, con valores de mentira
    "distribucion/LEEME.txt",
    "distribucion/LEEME-ESTA-CARPETA.txt",
    "pruebas/test_publicacion.py",
    "pruebas/test_reconexion.py",
    "ad5x/printer.py",      # los mensajes de ayuda hablan de 192.168.x.x
    "ad5x/actualizar.py",
}


def publicados() -> list[str]:
    salida = subprocess.run(
        ["git", "ls-files", "-z"], cwd=RAIZ, capture_output=True, check=False)
    return [p.decode("utf-8") for p in salida.stdout.split(b"\x00") if p]


def trozos(ruta: Path):
    """El contenido del fichero, y si es un ZIP, el de cada cosa que lleva dentro."""
    if zipfile.is_zipfile(ruta):
        with zipfile.ZipFile(ruta) as z:
            for nombre in z.namelist():
                yield f"::{nombre}", z.read(nombre)
    else:
        yield "", ruta.read_bytes()


def main() -> int:
    ficheros = publicados()
    if not ficheros:
        print("Aquí no hay repositorio todavía, o no hay nada añadido.")
        return 0

    buscar = agujas()
    fallos: list[str] = []

    for relativo in ficheros:
        ruta = RAIZ / relativo
        if not ruta.is_file():
            continue
        for dentro, datos in trozos(ruta):
            bajo = datos.lower()
            for que, aguja in buscar.items():
                if aguja.lower().encode("utf-8") in bajo:
                    fallos.append(f"{relativo}{dentro}: lleva {que}")
            if relativo in PERDONADOS:
                continue
            for que, patron in PATRONES.items():
                sospechas = [m.group(0) for m in patron.finditer(datos)]
                sospechas = [s for s in sospechas if not DE_LA_CASA.match(s)]
                if sospechas:
                    muestra = sospechas[0].decode("utf-8", "replace")[:60]
                    fallos.append(f"{relativo}{dentro}: parece llevar {que} ({muestra})")

    print(f"{len(ficheros)} ficheros publicados, revisados uno a uno\n")
    if fallos:
        print(f"{len(fallos)} COSAS QUE NO DEBEN SALIR DE AQUÍ:")
        for f in sorted(set(fallos)):
            print("  ·", f)
        return 1
    print("Nada que no deba publicarse.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
