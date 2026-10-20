r"""Dos laminados a la vez no pueden darse el cambiazo.

    .venv\Scripts\python.exe pruebas\test_laminado_simultaneo.py

Orca siempre escribe su resultado como «plate_1.gcode». Mientras los dos
laminados compartían carpeta de salida, el que terminaba segundo podía
llevarse el g-code del primero —o encontrarse con que ya no estaba y
reventar con un error 500 sin explicación—. Y no hace falta ser dos
personas: el navegador lamina solo en cuanto traes un modelo, así que basta
con traer uno mientras hay otro en marcha.

Lo peor no era el error, era el acierto aparente: te llevas un g-code que no
es el de tu pieza, y lo descubres cuando la impresora ya está imprimiendo
otra cosa.

Esta prueba lamina dos piezas distintas a la vez y exige que cada una salga
con lo suyo, comparado con laminarlas por separado. Necesita Orca; sin él se
salta sola.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ad5x.cad import build_part  # noqa: E402
from ad5x.catalog import discover  # noqa: E402
from ad5x.config import CONFIG  # noqa: E402
from ad5x.slicer import slice_stl  # noqa: E402

# Dos piezas que no se parecen en nada: si hay cambiazo, se nota.
# Dos piezas que tardan PARECIDO en laminarse, para que las dos tengan su
# «plate_1.gcode» escrito a la vez: ahí está la ventana del cambiazo. Con una
# rápida y otra lenta no se solapan nunca y la prueba pasa sin probar nada.
# Distinta altura para poder distinguirlas por el número de capas.
PAREJA = [
    ("caja", {"width": 60.0, "depth": 45.0, "height": 30.0}),
    ("caja", {"width": 58.0, "depth": 43.0, "height": 18.0}),
]
INTENTOS = 3  # una carrera no siempre se pierde a la primera


def main() -> int:
    if not CONFIG.slicer_available:
        print("Orca no está instalado aquí: nada que comprobar.")
        return 0

    partes, _ = discover(RAIZ / "piezas")
    taller = Path(tempfile.mkdtemp(prefix="taller-simultaneo-"))
    try:
        modelos = []
        for numero, (slug, extra) in enumerate(PAREJA, start=1):
            pieza = partes[slug]
            construido = build_part(pieza, pieza.defaults() | extra, taller)
            hecho = construido.project or construido.path
            # Dos piezas de la misma clase en el mismo segundo salen con el
            # mismo nombre y la segunda pisa a la primera: entonces esto
            # compararía una pieza consigo misma y pasaría sin probar nada.
            propio = hecho.with_name(f"pieza_{numero}{hecho.suffix}")
            hecho.rename(propio)
            modelos.append(propio)
        print(f"piezas: {', '.join(m.name for m in modelos)}")

        print("\n1. Por separado, para saber qué tiene que salir")
        solos = {}
        for modelo in modelos:
            aparte = Path(tempfile.mkdtemp(prefix="solo-", dir=taller))
            resultado = slice_stl(modelo, CONFIG, output_dir=aparte)
            solos[modelo.stem] = resultado.layers
            print(f"   {modelo.stem}: {resultado.layers} capas, {resultado.estimate}")

        fallos = 0
        for intento in range(1, INTENTOS + 1):
            print(f"\n2.{intento} Los dos a la vez, en la MISMA carpeta de salida")
            juntos = Path(tempfile.mkdtemp(prefix="juntos-", dir=taller))
            with ThreadPoolExecutor(max_workers=len(modelos)) as pool:
                futuros = {
                    modelo.stem: pool.submit(
                        slice_stl, modelo, CONFIG, output_dir=juntos)
                    for modelo in modelos
                }
                a_la_vez = {}
                for nombre, futuro in futuros.items():
                    try:
                        a_la_vez[nombre] = futuro.result()
                    except Exception as exc:  # noqa: BLE001 - es lo que se mide
                        print(f"   FALLO  {nombre} ha reventado: "
                              f"{type(exc).__name__}: {exc}")
                        a_la_vez[nombre] = None

            for nombre, resultado in a_la_vez.items():
                corto = nombre.split("_", 2)[-1]
                if resultado is None:
                    fallos += 1
                elif resultado.path.stem != nombre:
                    print(f"   FALLO  {corto} ha devuelto «{resultado.path.stem}»")
                    fallos += 1
                elif resultado.layers != solos[nombre]:
                    print(f"   FALLO  {corto}: {resultado.layers} capas a la vez "
                          f"contra {solos[nombre]} por separado: CAMBIAZO")
                    fallos += 1
                else:
                    print(f"   OK   {corto}: {resultado.layers} capas, las suyas")

        print("\n" + ("TODO CORRECTO" if not fallos else f"{fallos} FALLOS"))
        return 1 if fallos else 0
    finally:
        shutil.rmtree(taller, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
