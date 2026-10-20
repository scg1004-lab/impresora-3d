r"""Rompe el actualizador por dentro, a propósito, de todas las formas posibles.

    .venv\Scripts\python.exe pruebas\test_actualizador_adverso.py

`test_actualizador.py` comprueba casos concretos, y los escribió quien hizo
el arreglo: sabe dónde mirar, que es justo el problema. Esto no mira a
ningún sitio. Hace fallar **cada** función interna con **cada** tipo de
excepción plausible —132 combinaciones— y exige dos cosas en todas:

1. Que nada salga fuera de `comprobar()`. Es su contrato, y el fallo que
   tumbó la primera versión fue precisamente una excepción de un tipo que
   nadie había previsto (`http.client.IncompleteRead` no hereda de
   `OSError`). La lista de abajo tiene tipos que hoy no puede lanzar nadie:
   están porque mañana sí.
2. Que el programa quede entero. Ni a medio borrar ni a medio poner, con
   los modelos y la carpeta de salida sin tocar.

`KeyboardInterrupt` y `SystemExit` no están en la lista a propósito: esas
sí deben pasar de largo, porque son la forma de parar el programa.
"""
from __future__ import annotations

import http.client
import io
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ad5x.actualizar as act  # noqa: E402

SHA = "a" * 40

BUENO = {
    "ad5x/web.py": "VERSION = 'nueva'\n",
    "ad5x/catalog.py": "# nuevo\n",
    "ad5x/actualizar.py": "# nuevo\n",
    "piezas/caja.py": "# nueva\n",
    "run.py": "# nuevo\n",
}

# Lo que tiene que seguir ahí pase lo que pase. None = da igual el contenido,
# puede ser el viejo o el nuevo, pero el fichero no puede faltar.
INTACTO: dict[str, str | None] = {
    "ad5x/web.py": None,
    "ad5x/catalog.py": None,
    "piezas/caja.py": None,
    "run.py": None,
    "modelos/tortuga.stl": "mia",
    "salida/llavero.stl": "mio",
    "py/python.exe": None,
}

EXCEPCIONES: list[Exception] = [
    http.client.IncompleteRead(b"medio", 9),   # el que tumbó la v1
    http.client.HTTPException("vete a saber"),
    FileExistsError(183, "ya existe"),         # el otro que tumbó la v1
    PermissionError(13, "el antivirus lo tiene abierto"),
    OSError(28, "disco lleno"),
    MemoryError(),
    zipfile.BadZipFile("corrupto"),
    UnicodeDecodeError("utf-8", b"\xff", 0, 1, "raro"),
    RecursionError(),
    ValueError("cualquier cosa"),
    RuntimeError("inesperado"),
]

DIANAS = [
    "_version_publicada", "_version_instalada", "_descargar", "_contenido",
    "_extraer", "_compila", "_arranca", "_sitio_para_el_respaldo",
    "_cambiar", "_deshacer", "_devolver_sus_piezas", "es_el_paquete",
]


def paquete() -> Path:
    raiz = Path(tempfile.mkdtemp(prefix="taller-adverso-"))
    (raiz / "py").mkdir()
    (raiz / "py" / "python.exe").write_bytes(b"no soy python")
    (raiz / "ad5x").mkdir()
    (raiz / "ad5x" / "web.py").write_text("VERSION = 'vieja'\n", encoding="utf-8")
    (raiz / "ad5x" / "catalog.py").write_text("# viejo\n", encoding="utf-8")
    (raiz / "piezas").mkdir()
    (raiz / "piezas" / "caja.py").write_text("# vieja\n", encoding="utf-8")
    (raiz / "run.py").write_text("# viejo\n", encoding="utf-8")
    (raiz / "modelos").mkdir()
    (raiz / "modelos" / "tortuga.stl").write_text("mia", encoding="utf-8")
    (raiz / "salida").mkdir()
    (raiz / "salida" / "llavero.stl").write_text("mio", encoding="utf-8")
    return raiz


def zip_bueno(sha: str) -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nombre, contenido in BUENO.items():
            z.writestr(f"{act.NOMBRE_REPO}-{sha}/{nombre}", contenido)
    return zipfile.ZipFile(buf)


def entero(raiz: Path) -> str | None:
    for ruta, esperado in INTACTO.items():
        fichero = raiz / ruta
        if not fichero.exists():
            return f"falta {ruta}"
        if esperado is not None and fichero.read_text(encoding="utf-8") != esperado:
            return f"{ruta} ha cambiado y no debía"
    return None


def main() -> int:
    escapadas: list[str] = []
    rotos: list[str] = []
    probadas = 0

    for diana in DIANAS:
        for excepcion in EXCEPCIONES:
            raiz = paquete()
            probadas += 1
            try:
                parches = [
                    patch.object(act, "_version_publicada", return_value=SHA),
                    patch.object(act, "_descargar", lambda s: zip_bueno(s)),
                    patch.object(act, diana, side_effect=excepcion),
                ]
                for p in parches:
                    p.start()
                try:
                    act.comprobar(raiz)
                except BaseException as salida:  # noqa: BLE001 - es lo que se mide
                    escapadas.append(
                        f"{diana} + {type(excepcion).__name__} -> {type(salida).__name__}")
                finally:
                    for p in reversed(parches):
                        p.stop()
                mal = entero(raiz)
                if mal:
                    rotos.append(f"{diana} + {type(excepcion).__name__}: {mal}")
            finally:
                shutil.rmtree(raiz, ignore_errors=True)

    print(f"{probadas} combinaciones de (función rota, tipo de excepción)\n")
    if escapadas:
        print(f"{len(escapadas)} EXCEPCIONES ESCAPADAS:")
        for e in escapadas[:20]:
            print("  ·", e)
    else:
        print("  OK   ninguna excepción sale de comprobar()")
    if rotos:
        print(f"{len(rotos)} VECES QUE EL PROGRAMA QUEDA ROTO:")
        for r in rotos[:20]:
            print("  ·", r)
    else:
        print("  OK   el programa queda entero en todas")

    print("\n" + ("TODO CORRECTO" if not (escapadas or rotos) else "FALLOS"))
    return 1 if (escapadas or rotos) else 0


if __name__ == "__main__":
    sys.exit(main())
