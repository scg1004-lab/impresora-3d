"""Cylindrical spacer / standoff."""
import cadquery as cq

from ad5x.catalog import Param

NAME = "Separador cilíndrico"
DESCRIPTION = "Casquillo o separador: cilindro con agujero pasante, en tirada de varias unidades."
NOTES = "Para que pase un tornillo M4 holgado, 4,5 mm. Hexagonal agarra mejor con los dedos."

PARAMS = [
    Param("outer", "Diámetro exterior", 10.0, minimum=3, maximum=100, step=0.5),
    Param("inner", "Diámetro del agujero", 4.5, minimum=0, maximum=90, step=0.1),
    Param("height", "Altura", 10.0, minimum=1, maximum=200, step=0.5),
    Param("hexagonal", "Cuerpo hexagonal", False),
    Param("count", "Unidades", 4, unit="", minimum=1, maximum=25, step=1),
]


def build(outer, inner, height, hexagonal, count):
    if inner >= outer - 0.8:
        raise ValueError(
            f"Con {outer} mm de exterior y {inner} mm de agujero la pared queda "
            "en nada: deja al menos 0,8 mm por lado"
        )

    base = cq.Workplane("XY")
    body = (
        base.polygon(6, outer).extrude(height)
        if hexagonal
        else base.circle(outer / 2).extrude(height)
    )

    if inner > 0:
        body = body.cut(
            cq.Workplane("XY").circle(inner / 2).extrude(height * 3).translate((0, 0, -height))
        )

    count = int(count)
    if count == 1:
        return body

    # Lay them out in a tidy grid rather than a single long row.
    pitch = outer + 5
    columns = min(count, 5)
    result = None
    for index in range(count):
        row, column = divmod(index, columns)
        piece = body.translate((column * pitch, row * pitch, 0))
        result = piece if result is None else result.union(piece)
    return result
