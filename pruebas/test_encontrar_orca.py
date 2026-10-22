r"""Comprueba que el laminador aparece aunque lo instalen en otro sitio.

    .venv\Scripts\python.exe pruebas\test_encontrar_orca.py

Monta instalaciones de mentira en carpetas temporales y mira si la app las
encuentra. Es una prueba que no existía y debería: la app decía «no tienes
Orca» en un ordenador que lo tenía instalado, porque la búsqueda era una
lista de rutas fijas y Flashforge había renombrado el programa de
«Orca-Flashforge» a «Flash Studio Desktop».

La seña que no depende del nombre es la carpeta `resources/profiles` que el
laminador lleva al lado. Por eso el caso que más importa aquí es el del
programa con un nombre que nadie ha visto todavía.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ad5x.config as cfg  # noqa: E402

fallos: list[str] = []


def instalacion(base: Path, carpeta: str, exe: str, *, perfiles: bool = True,
                acompanantes: tuple[str, ...] = ()) -> Path:
    """Una instalación falsa: el programa, sus perfiles y algún estorbo."""
    sitio = base / "Program Files" / carpeta
    sitio.mkdir(parents=True, exist_ok=True)
    # El programa pesa; los acompañantes no. Así se distinguen cuando hay
    # que elegir por tamaño.
    (sitio / exe).write_bytes(b"x" * 5_000_000)
    for otro in acompanantes:
        (sitio / otro).write_bytes(b"x" * 1000)
    if perfiles:
        (sitio / "resources" / "profiles" / "Flashforge").mkdir(parents=True)
    return sitio / exe


def buscar(base: Path) -> Path | None:
    """Busca con PROGRAMFILES apuntando a la instalación de mentira.

    El registro se anula: aquí se prueba la búsqueda en disco, y si no, en
    este ordenador ganaría siempre la instalación de verdad.
    """
    entorno = {
        "PROGRAMFILES": str(base / "Program Files"),
        "PROGRAMFILES(X86)": str(base / "Program Files (x86)"),
        "LOCALAPPDATA": str(base / "AppData"),
        "APPDATA": str(base / "AppData"),
    }
    with patch.dict(os.environ, entorno), \
         patch.dict(os.environ, {"SLICER_EXE": ""}), \
         patch.object(cfg, "_del_registro", return_value=[]):
        return cfg._find_slicer()


CASOS = [
    ("el de siempre",
     "Flashforge/Orca-Flashforge", "orca-flashforge.exe", True),
    ("renombrado a Flash Studio",
     "Flashforge/Flash Studio Desktop", "FlashStudio.exe", True),
    ("un nombre que nadie ha visto aún",
     "Flashforge/Laminador 2030", "ff-slice-2030.exe", True),
    ("OrcaSlicer de la comunidad",
     "OrcaSlicer", "orca-slicer.exe", True),
    ("sin perfiles al lado: eso no es el laminador",
     "Flashforge/Otra Cosa", "cualquiera.exe", False),
]


def main() -> int:
    for titulo, carpeta, exe, debe_salir in CASOS:
        base = Path(tempfile.mkdtemp(prefix="orca-falso-"))
        try:
            esperado = instalacion(
                base, carpeta, exe,
                perfiles=debe_salir,
                acompanantes=("unins000.exe", "crashpad_handler.exe"),
            )
            hallado = buscar(base)
            if debe_salir and hallado != esperado:
                fallos.append(f"{titulo}: esperaba {esperado.name}, salió {hallado}")
                print(f"   FALLO  {titulo}")
            elif not debe_salir and hallado is not None:
                fallos.append(f"{titulo}: no debía encontrar nada y encontró {hallado}")
                print(f"   FALLO  {titulo}")
            else:
                print(f"   OK   {titulo}"
                      + (f" -> {hallado.name}" if hallado else " (no lo da por bueno)"))
        finally:
            shutil.rmtree(base, ignore_errors=True)

    # Y en este ordenador, el de verdad tiene que seguir apareciendo.
    print("\nEn este ordenador:")
    propio = cfg._find_slicer()
    if propio and propio.is_file():
        print(f"   OK   {propio}")
    else:
        print("   (no hay laminador instalado aquí, nada que comprobar)")

    print("\n" + ("TODO CORRECTO" if not fallos else f"{len(fallos)} FALLOS"))
    for f in fallos:
        print("  ·", f)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
