r"""Comprueba el autoactualizador sin tocar GitHub ni la instalación de verdad.

    .venv\Scripts\python.exe pruebas\test_actualizador.py

Monta un paquete de mentira en una carpeta temporal y le da ZIPs hechos a
mano, incluidos los que intentan escribir fuera. Es la parte del programa que
más cuidado merece: baja código de internet y lo escribe en el disco de otro
ordenador, uno al que no se puede ir corriendo a arreglar nada.

Los casos 10 a 13 salieron de una revisión de seguridad que tumbó la primera
versión: una descarga cortada levantaba una excepción que nadie recogía
—`IncompleteRead` no es `OSError`— y el propio rescate podía reventar y dejar
el código a medio borrar. Están aquí para que no vuelvan.
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

fallos: list[str] = []


def mal(mensaje: str) -> None:
    fallos.append(mensaje)
    print(f"   FALLO  {mensaje}")


def bien(mensaje: str) -> None:
    print(f"   OK   {mensaje}")


def paquete_falso() -> Path:
    """Un paquete portátil de mentira: lo justo para que se crea que lo es."""
    raiz = Path(tempfile.mkdtemp(prefix="taller-act-"))
    (raiz / "py").mkdir()
    # Un python.exe de pega: basta para que se reconozca como paquete, y hace
    # que la prueba de arranque se salte sola por no poder ejecutarlo.
    (raiz / "py" / "python.exe").write_bytes(b"no soy python")
    (raiz / "ad5x").mkdir()
    (raiz / "ad5x" / "web.py").write_text("VERSION = 'vieja'\n", encoding="utf-8")
    (raiz / "ad5x" / "catalog.py").write_text("# viejo\n", encoding="utf-8")
    (raiz / "piezas").mkdir()
    (raiz / "piezas" / "caja.py").write_text("# vieja\n", encoding="utf-8")
    (raiz / "run.py").write_text("# viejo\n", encoding="utf-8")
    # Lo que la actualización NO puede tocar.
    (raiz / "modelos").mkdir()
    (raiz / "modelos" / "tortuga.stl").write_text("mia", encoding="utf-8")
    (raiz / "salida").mkdir()
    (raiz / "salida" / "llavero.stl").write_text("mio", encoding="utf-8")
    (raiz / ".env").write_text("CHECK_CODE=secreto\n", encoding="utf-8")
    return raiz


def zip_con(entradas: dict[str, str], sha: str, tope: str | None = None) -> zipfile.ZipFile:
    carpeta = tope if tope is not None else f"{act.NOMBRE_REPO}-{sha}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nombre, contenido in entradas.items():
            z.writestr(f"{carpeta}/{nombre}", contenido)
    return zipfile.ZipFile(buf)


BUENO = {
    "ad5x/web.py": "VERSION = 'nueva'\n",
    "ad5x/catalog.py": "# nuevo\n",
    "ad5x/actualizar.py": "# nuevo\n",
    "piezas/caja.py": "# nueva\n",
    "piezas/llavero.py": "# pieza nueva\n",
    "run.py": "# nuevo\n",
}


def correr(raiz: Path, entradas: dict[str, str], sha: str = "a" * 40,
           tope: str | None = None):
    with patch.object(act, "_version_publicada", return_value=sha), \
         patch.object(act, "_descargar", lambda s: zip_con(entradas, s, tope)):
        return act.comprobar(raiz)


def main() -> int:  # noqa: C901 - es una lista de casos, se lee de arriba abajo
    print("1. En el equipo donde se programa no se actualiza nada")
    if act.comprobar(RAIZ) is None and not act.es_el_paquete(RAIZ):
        bien("no toca el código de trabajo")
    else:
        mal("ha intentado actualizar el equipo de desarrollo")

    print("2. Actualización normal")
    raiz = paquete_falso()
    try:
        aviso = correr(raiz, BUENO)
        nuevo = (raiz / "ad5x" / "web.py").read_text(encoding="utf-8")
        if aviso and "nueva" in nuevo and (raiz / "piezas" / "llavero.py").is_file():
            bien(aviso)
        else:
            mal(f"no ha actualizado: {aviso!r}")
        if (raiz / act.MARCA).read_text(encoding="utf-8").strip() != "a" * 40:
            mal("no ha guardado la versión")
        if (raiz / act.ENTRANTE).exists() or (raiz / act.CERROJO).exists():
            mal("ha dejado carpetas de trabajo tiradas")

        print("3. No vuelve a bajarse lo mismo")
        if correr(raiz, BUENO) is None:
            bien("con la misma versión no hace nada")
        else:
            mal("se ha actualizado dos veces a lo mismo")

        print("4. No toca lo que no es código")
        intacto = (
            (raiz / "modelos" / "tortuga.stl").read_text(encoding="utf-8") == "mia"
            and (raiz / "salida" / "llavero.stl").read_text(encoding="utf-8") == "mio"
            and (raiz / ".env").read_text(encoding="utf-8").startswith("CHECK_CODE")
            and (raiz / "py" / "python.exe").is_file()
        )
        bien("modelos, salida, .env y py siguen ahí") if intacto else mal(
            "ha tocado algo que no era código")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)

    print("5. Un ZIP que intenta escribir fuera de la carpeta")
    raiz = paquete_falso()
    fuera = raiz.parent / "VICTIMA.txt"
    try:
        trampas = dict(BUENO)
        for ruta in ("../VICTIMA.txt", "../../VICTIMA.txt", "ad5x/../../VICTIMA.txt",
                     "C:/VICTIMA.txt", "ad5x/web.py:oculto"):
            trampas[ruta] = "me he escapado"
        correr(raiz, trampas, sha="b" * 40)
        if fuera.exists():
            mal("¡ha escrito FUERA de la carpeta del programa!")
        else:
            bien("rutas con .., absolutas y con dos puntos: descartadas")
    finally:
        fuera.unlink(missing_ok=True)
        shutil.rmtree(raiz, ignore_errors=True)

    print("6. Un ZIP que trae ficheros que no son del programa")
    raiz = paquete_falso()
    try:
        colados = dict(BUENO)
        colados[".env"] = "CHECK_CODE=robado"
        colados["py/python.exe"] = "virus"
        colados["modelos/tortuga.stl"] = "machacada"
        correr(raiz, colados, sha="c" * 40)
        if (raiz / ".env").read_text(encoding="utf-8").startswith("CHECK_CODE=secreto") \
                and (raiz / "modelos" / "tortuga.stl").read_text(encoding="utf-8") == "mia" \
                and (raiz / "py" / "python.exe").read_bytes() == b"no soy python":
            bien("solo se reemplaza lo que está en la lista")
        else:
            mal("ha reemplazado algo fuera de la lista")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)

    print("7. Un ZIP incompleto no se aplica")
    raiz = paquete_falso()
    try:
        if correr(raiz, {"piezas/llavero.py": "# suelta\n"}, sha="d" * 40) is None \
                and not (raiz / "piezas" / "llavero.py").exists():
            bien("sin el programa entero, ni se toca")
        else:
            mal("ha aplicado una descarga incompleta")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)

    print("8. Código roto: no se pone")
    raiz = paquete_falso()
    try:
        roto = dict(BUENO)
        roto["ad5x/web.py"] = "def (((\n"
        aviso = correr(raiz, roto, sha="e" * 40)
        vuelto = (raiz / "ad5x" / "web.py").read_text(encoding="utf-8")
        if "vieja" in vuelto and (raiz / "piezas" / "caja.py").is_file() \
                and not (raiz / act.MARCA).exists():
            bien(f"se queda la de antes: {aviso}")
        else:
            mal("ha dejado el programa con el código roto")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)

    print("9. Sin internet se arranca igual")
    raiz = paquete_falso()
    try:
        with patch.object(act, "_version_publicada", side_effect=OSError("sin red")):
            if act.comprobar(raiz) is None:
                bien("se calla y sigue")
            else:
                mal("ha dicho algo cuando no había red")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)

    print("10. Descarga cortada a medias (IncompleteRead no es OSError)")
    raiz = paquete_falso()
    try:
        corte = http.client.IncompleteRead(b"medio zip", 999)
        with patch.object(act, "_version_publicada", return_value="f" * 40), \
             patch.object(act, "_descargar", side_effect=corte):
            try:
                if act.comprobar(raiz) is None:
                    bien("la recoge y arranca igual")
                else:
                    mal("ha dicho algo raro")
            except Exception as exc:  # noqa: BLE001 - es justo lo que se prueba
                mal(f"la excepción se ha escapado: {type(exc).__name__}")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)

    print("11. Si el propio rescate falla, tampoco revienta")
    raiz = paquete_falso()
    try:
        with patch.object(act, "_cambiar", side_effect=OSError("disco ocupado")), \
             patch.object(act, "_deshacer", side_effect=OSError("y el rescate también")):
            try:
                act.comprobar(raiz)
                bien("ni con el rescate roto sale una excepción")
            except Exception as exc:  # noqa: BLE001
                mal(f"la excepción se ha escapado: {type(exc).__name__}")
        if not (raiz / "ad5x" / "web.py").exists():
            mal("ha dejado el código a medio borrar")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)

    print("12. Dos arranques a la vez: solo actualiza uno")
    raiz = paquete_falso()
    try:
        (raiz / act.CERROJO).mkdir()  # como si otro estuviera actualizando
        if correr(raiz, BUENO, sha="1" * 40) is None \
                and "vieja" in (raiz / "ad5x" / "web.py").read_text(encoding="utf-8"):
            bien("el segundo se aparta")
        else:
            mal("los dos han actualizado a la vez")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)

    print("13. Un ZIP que no es el commit que se pidió")
    raiz = paquete_falso()
    try:
        if correr(raiz, BUENO, sha="2" * 40, tope="otro-repo-main") is None \
                and "vieja" in (raiz / "ad5x" / "web.py").read_text(encoding="utf-8"):
            bien("si la raíz del ZIP no cuadra, no se instala")
        else:
            mal("ha instalado un ZIP que no era el suyo")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)

    print("14. Las piezas propias de quien lo usa se respetan")
    raiz = paquete_falso()
    try:
        (raiz / "piezas" / "mi_dinosaurio.py").write_text("# mia\n", encoding="utf-8")
        aviso = correr(raiz, BUENO, sha="3" * 40)
        if (raiz / "piezas" / "mi_dinosaurio.py").is_file():
            bien(f"sigue ahí: {aviso}")
        else:
            mal("le ha borrado su pieza")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)

    print("15. Una versión que no es un sha no vale")
    raiz = paquete_falso()
    try:
        with patch.object(act, "_version_publicada", return_value=""):
            if act.comprobar(raiz) is None:
                bien("un portal cautivo que conteste HTML no cuela")
            else:
                mal("se ha creído cualquier cosa")
    finally:
        shutil.rmtree(raiz, ignore_errors=True)

    print("\n" + ("TODO CORRECTO" if not fallos else f"{len(fallos)} FALLOS"))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
