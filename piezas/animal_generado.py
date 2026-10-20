"""Animalitos generados por código: eliges la especie y el tamaño."""
from ad5x.catalog import Param
from ad5x.criaturas import construir, especies

POR_TOTAL = "Tamaño total"
POR_ALTURA = "Altura"

NAME = "Animalito (generado)"
DESCRIPTION = "Figuras de animales hechas al momento, al tamaño que pidas."
NOTES = (
    "No son ficheros descargados: se construyen con bultos redondeados, al "
    "estilo de las figuras de resina pequeñas. Tardan unos segundos. "
    "Con «Tamaño total» en 20 mm caben en un cubo de 2 cm. "
    "Salen macizas y sin partes voladizas, así que se imprimen sin soportes."
)

PARAMS = [
    Param("especie", "Animal", especies()[0], unit="", options=especies()),
    Param("medida", "Medida", 20.0, minimum=8, maximum=120, step=1),
    Param(
        "modo",
        "Esa medida es...",
        POR_TOTAL,
        unit="",
        options=(POR_TOTAL, POR_ALTURA),
    ),
    Param("ojos", "Con ojos", True),
]


def build(especie, medida, modo, ojos):
    return construir(especie, medida, por_altura=(modo == POR_ALTURA), con_ojos=ojos)
