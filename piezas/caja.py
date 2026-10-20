"""Box with rounded corners and an optional push-fit lid."""
import cadquery as cq

from ad5x.catalog import Param

NAME = "Caja con tapa"
DESCRIPTION = "Caja rectangular de esquinas redondeadas, con tapa opcional que encaja a presión."
NOTES = (
    "La tapa sale junto a la caja en la misma placa. Si queda floja, sube la "
    "holgura; si no entra, bájala. 0,2 mm es lo normal en PLA. "
    "Marcando «tapa de otro color» podrás elegir una bobina para cada una."
)

PARAMS = [
    Param("width", "Ancho exterior", 80.0, minimum=15, maximum=210),
    Param("depth", "Fondo exterior", 60.0, minimum=15, maximum=210),
    Param("height", "Altura exterior", 40.0, minimum=8, maximum=210),
    Param("wall", "Espesor de pared", 2.0, minimum=0.8, maximum=10, step=0.2),
    Param("floor", "Espesor del fondo", 2.0, minimum=0.8, maximum=10, step=0.2),
    Param("corner", "Radio de esquina", 4.0, minimum=0, maximum=30, step=0.5),
    Param("with_lid", "Incluir tapa", True),
    Param("lid_height", "Altura del labio de la tapa", 6.0, minimum=2, maximum=20),
    Param("clearance", "Holgura de la tapa", 0.2, minimum=0.0, maximum=1.0, step=0.05),
    Param("dos_colores", "Tapa de otro color", False),
]


def _rounded(width, depth, height, radius):
    shape = cq.Workplane("XY").box(width, depth, height, centered=(True, True, False))
    if radius > 0.05:
        shape = shape.edges("|Z").fillet(min(radius, width / 2 - 0.1, depth / 2 - 0.1))
    return shape


def build(width, depth, height, wall, floor, corner, with_lid, lid_height,
          clearance, dos_colores):
    inner_w = width - 2 * wall
    inner_d = depth - 2 * wall
    if inner_w <= 1 or inner_d <= 1:
        raise ValueError(
            f"Con paredes de {wall} mm no queda hueco dentro: sube el ancho/fondo "
            "o baja el espesor de pared"
        )
    if floor >= height:
        raise ValueError("El fondo es más alto que la caja entera")

    cavity = _rounded(inner_w, inner_d, height, corner - wall).translate((0, 0, floor))
    box = _rounded(width, depth, height, corner).cut(cavity)

    if not with_lid:
        return box

    lid_plate = _rounded(width, depth, floor, corner)
    lip_w = inner_w - 2 * clearance
    lip_d = inner_d - 2 * clearance
    if lip_w <= 1 or lip_d <= 1:
        raise ValueError("La holgura se come el labio de la tapa entero")

    lip = _rounded(lip_w, lip_d, lid_height, corner - wall - clearance).translate(
        (0, 0, floor)
    )
    lid = lid_plate.union(lip)

    # Side by side on the plate, with a 10 mm gap so the slicer keeps them apart.
    lid = lid.translate((width + 10, 0, 0))
    if dos_colores:
        # Named pieces: each one goes to its own IFS channel.
        return {"Caja": box, "Tapa": lid}
    return box.union(lid)
