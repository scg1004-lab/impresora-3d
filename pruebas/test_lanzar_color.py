r"""Imprimir con un color elegido va en dos pasos, no en uno.

    .venv\Scripts\python.exe pruebas\test_lanzar_color.py

Dos reglas, y la segunda se aprendió gastando 500 capas en vano.

Con VARIOS colores, el mapeo de bahías hay que mandarlo por `/printGcode`:
en la cabecera de la subida el firmware solo lo registra. Así que se sube
sin arrancar y se lanza después.

Con UN solo color no se manda ninguna bahía. El G-code de un color da por
hecho que el filamento ya está cargado —calienta, hace la línea de purga y
se pone a imprimir, sin una sola orden para la estación de materiales—, así
que pedirle otra bahía deja la boquilla vacía y la pieza sale en aire, sin
error y sin que nadie se entere hasta mirarla.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ad5x.printer as mod  # noqa: E402
from ad5x.config import Config  # noqa: E402

UN_COLOR = [{
    "toolId": 0, "slotId": 3, "materialName": "PLA",
    "toolMaterialColor": "#F2754E", "slotMaterialColor": "#2750E0",
}]

DOS_COLORES = UN_COLOR + [{
    "toolId": 1, "slotId": 4, "materialName": "PLA",
    "toolMaterialColor": "#FEF043", "slotMaterialColor": "#FEF043",
}]

fallos: list[str] = []


def configuracion(tmp: Path) -> Config:
    return Config(
        printer_ip="127.0.0.1", serial_number="SNTEST", check_code="abcd1234",
        printer_port=18999, slicer_exe=None, system_profiles=None,
        thingiverse_token=None,
        leveling_before_print=False, parts_dir=RAIZ / "piezas",
        output_dir=tmp, profiles_dir=RAIZ / "perfiles",
    )


class Respuesta:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"code": 0, "message": "Success", "gcodeList": ["pieza.gcode.3mf"]}


def correr(tmp: Path, *, print_now: bool, mappings):
    """Hace un envío con la red fingida y devuelve lo que habría salido."""
    llamadas: list[tuple[str, dict]] = []

    def post(url, **kwargs):
        llamadas.append((url, kwargs))
        return Respuesta()

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
         patch.object(mod.Printer, "_answers_here", return_value=True):
        impresora.upload(gcode, print_now=print_now, mappings=mappings)
    return llamadas


def main() -> int:
    import tempfile
    import shutil
    tmp = Path(tempfile.mkdtemp(prefix="lanzar-"))
    try:
        print("1. Con varios colores: subir sin arrancar y lanzar después")
        llamadas = correr(tmp, print_now=True, mappings=DOS_COLORES)
        subidas = [c for c in llamadas if c[0].endswith("/uploadGcode")]
        lanzas = [c for c in llamadas if c[0].endswith("/printGcode")]

        if len(subidas) != 1:
            fallos.append(f"{len(subidas)} subidas, se esperaba 1")
        else:
            cabeceras = subidas[0][1].get("headers", {})
            if cabeceras.get("printNow") != "false":
                fallos.append(f"printNow en la subida = {cabeceras.get('printNow')}")
            else:
                print("   OK   la subida va con printNow=false")

        if len(lanzas) != 1:
            fallos.append(f"{len(lanzas)} /printGcode, se esperaba 1")
        else:
            cuerpo = lanzas[0][1].get("json", {})
            bahias = [m.get("slotId") for m in cuerpo.get("materialMappings", [])]
            if bahias == [3, 4] and cuerpo.get("useMatlStation") is True:
                print(f"   OK   se lanza con las bahías {bahias}")
            else:
                fallos.append(f"el lanzamiento no lleva la bahía: {cuerpo}")

        print("2. Con UN color: no se fuerza bahía, que vacía la boquilla")
        llamadas = correr(tmp, print_now=True, mappings=UN_COLOR)
        subidas = [c for c in llamadas if c[0].endswith("/uploadGcode")]
        lanzas = [c for c in llamadas if c[0].endswith("/printGcode")]
        cabeceras = subidas[0][1].get("headers", {}) if subidas else {}
        if lanzas:
            fallos.append("ha mandado la bahía con un solo color")
        elif "materialMappings" in cabeceras:
            fallos.append("la cabecera lleva la bahía con un solo color")
        elif cabeceras.get("printNow") != "true":
            fallos.append("no ha arrancado de una vez")
        else:
            print("   OK   se imprime con lo que haya cargado")

        print("3. Sin color elegido: de una sola vez, como siempre")
        llamadas = correr(tmp, print_now=True, mappings=None)
        subidas = [c for c in llamadas if c[0].endswith("/uploadGcode")]
        lanzas = [c for c in llamadas if c[0].endswith("/printGcode")]
        if subidas and subidas[0][1]["headers"].get("printNow") == "true" and not lanzas:
            print("   OK   printNow=true y ningún paso de más")
        else:
            fallos.append("sin mapeo ya no se arranca en la propia subida")

        print("4. Solo enviar: ni se arranca ni se lanza")
        llamadas = correr(tmp, print_now=False, mappings=DOS_COLORES)
        lanzas = [c for c in llamadas if c[0].endswith("/printGcode")]
        subidas = [c for c in llamadas if c[0].endswith("/uploadGcode")]
        if not lanzas and subidas[0][1]["headers"].get("printNow") == "false":
            print("   OK   se queda guardado, sin imprimir")
        else:
            fallos.append("«solo enviar» ha arrancado una impresión")

        print("\n" + ("TODO CORRECTO" if not fallos else f"{len(fallos)} FALLOS"))
        for f in fallos:
            print("  ·", f)
        return 1 if fallos else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
