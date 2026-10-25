r"""Un «Printer is Busy» justo después de subir no es un fallo.

    .venv\Scripts\python.exe pruebas\test_ocupada.py

Acabada la subida, la máquina sigue unos segundos asentando el fichero y
contesta «Printer is Busy» a cualquier orden de imprimir. Se reintenta.

Y si de verdad está imprimiendo otra cosa, lo que hay que decir no es «la
impresora rechazó /printGcode», que no le sirve a nadie, sino que el
fichero ya está guardado y cómo lanzarlo.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ad5x.printer as mod  # noqa: E402
from ad5x.config import Config  # noqa: E402

MAPEO = [{
    "toolId": 0, "slotId": 2, "materialName": "PLA",
    "toolMaterialColor": "#F2754E", "slotMaterialColor": "#F95D73",
}]

fallos: list[str] = []


def configuracion(tmp: Path) -> Config:
    return Config(
        printer_ip="127.0.0.1", serial_number="SNTEST", check_code="abcd1234",
        printer_port=18999, slicer_exe=None, system_profiles=None,
        thingiverse_token=None, leveling_before_print=False,
        parts_dir=RAIZ / "piezas", output_dir=tmp, profiles_dir=RAIZ / "perfiles",
    )


class Respuesta:
    status_code = 200

    def __init__(self, datos):
        self._datos = datos

    def raise_for_status(self):
        return None

    def json(self):
        return self._datos


def enviar(tmp: Path, ocupada_veces: int):
    """Sube y lanza, con la impresora diciendo «busy» las primeras veces."""
    estado = {"intentos": 0}
    llamadas: list[str] = []

    def post(url, **kwargs):
        llamadas.append(url)
        if url.endswith("/printGcode"):
            estado["intentos"] += 1
            if estado["intentos"] <= ocupada_veces:
                return Respuesta({"code": 5, "message": "Printer is Busy"})
            return Respuesta({"code": 0, "message": "Success"})
        if url.endswith("/gcodeList"):
            return Respuesta({"code": 0, "gcodeList": ["pieza.gcode.3mf"]})
        return Respuesta({"code": 0, "message": "Success"})

    gcode = tmp / "pieza.gcode"
    gcode.write_text(
        "; filament_type = PLA\n; filament_colour = #F2754E\n"
        "; nozzle_diameter = 0.4\n; layer_height = 0.2\n"
        "; estimated printing time (normal mode) = 1m 0s\n"
        "; filament used [cm3] = 0.1\nG1 X1 Y1 Z0.2 E1\n",
        encoding="utf-8")

    impresora = mod.Printer(configuracion(tmp))
    impresora._host = "127.0.0.1"
    with patch.object(mod.requests, "post", side_effect=post), \
         patch.object(mod.Printer, "_answers_here", return_value=True), \
         patch.object(mod.time, "sleep", return_value=None):   # sin esperas reales
        impresora.upload(gcode, print_now=True, mappings=MAPEO)
    return estado["intentos"], llamadas


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ocupada-"))
    try:
        print("1. Ocupada un par de veces: se reintenta y sale")
        try:
            intentos, _ = enviar(tmp, ocupada_veces=2)
            print(f"   OK   ha arrancado al intento {intentos}")
        except mod.PrinterError as exc:
            fallos.append(f"se ha rendido demasiado pronto: {exc}")
            print(f"   FALLO  {exc}")

        print("2. Ocupada siempre: se dice que el fichero ya está ahí")
        try:
            enviar(tmp, ocupada_veces=99)
            fallos.append("no ha avisado de que no arrancó")
            print("   FALLO  ha dicho que todo bien")
        except mod.PrinterError as exc:
            texto = str(exc)
            if "ya está guardado" in texto and "cola" in texto:
                print(f"   OK   {texto[:72]}…")
            else:
                fallos.append(f"el aviso no ayuda: {texto}")
                print(f"   FALLO  {texto}")

        print("3. Un error que no es «busy» no se reintenta")
        def post_roto(url, **kwargs):
            if url.endswith("/printGcode"):
                return Respuesta({"code": 9, "message": "No such file"})
            if url.endswith("/gcodeList"):
                return Respuesta({"code": 0, "gcodeList": ["otra.gcode.3mf"]})
            return Respuesta({"code": 0, "message": "Success"})

        gcode = tmp / "otra.gcode"
        shutil.copy2(tmp / "pieza.gcode", gcode)
        impresora = mod.Printer(configuracion(tmp))
        impresora._host = "127.0.0.1"
        with patch.object(mod.requests, "post", side_effect=post_roto), \
             patch.object(mod.Printer, "_answers_here", return_value=True), \
             patch.object(mod.time, "sleep", return_value=None):
            try:
                impresora.upload(gcode, print_now=True, mappings=MAPEO)
                fallos.append("se ha tragado un error de verdad")
                print("   FALLO  no ha dicho nada")
            except mod.PrinterError as exc:
                if "No such file" in str(exc):
                    print("   OK   lo dice tal cual, sin insistir")
                else:
                    fallos.append(f"ha cambiado el error: {exc}")
                    print(f"   FALLO  {exc}")

        print("\n" + ("TODO CORRECTO" if not fallos else f"{len(fallos)} FALLOS"))
        return 1 if fallos else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
