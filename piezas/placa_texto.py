"""Sign / label plate with raised or engraved text."""
import cadquery as cq

from ad5x.catalog import Param

NAME = "Placa con texto"
DESCRIPTION = "Cartel o etiqueta con texto en relieve o grabado, con agujero opcional para colgar."
NOTES = (
    "Marca «letras de otro color» y podrás darle una bobina a la placa y otra "
    "al texto: es donde más se nota el IFS. Grabado en hueco no admite dos "
    "colores, porque las letras son un agujero, no una pieza."
)

PARAMS = [
    Param("text", "Texto", "ETIQUETA", unit=""),
    Param("font_size", "Tamaño de letra", 12.0, minimum=4, maximum=80),
    Param("margin", "Margen alrededor del texto", 8.0, minimum=2, maximum=50),
    Param("plate_thickness", "Espesor de la placa", 3.0, minimum=1, maximum=20, step=0.5),
    Param("text_depth", "Altura del relieve", 1.0, minimum=0.2, maximum=10, step=0.2),
    Param("engraved", "Grabado en hueco", False),
    Param("corner", "Radio de esquina", 3.0, minimum=0, maximum=25, step=0.5),
    Param("hanging_hole", "Diámetro del agujero para colgar", 0.0, minimum=0, maximum=15, step=0.5),
    Param("dos_colores", "Letras de otro color", False),
]


def build(text, font_size, margin, plate_thickness, text_depth, engraved, corner,
          hanging_hole, dos_colores):
    label = str(text).strip()
    if not label:
        raise ValueError("El texto está vacío")

    # Build the lettering first so the plate can be sized to fit it.
    letters = cq.Workplane("XY").text(label, font_size, text_depth, combine=False)
    solids = letters.vals()
    if not solids:
        raise ValueError(f"No se ha podido dibujar «{label}» con la fuente del sistema")

    lettering = cq.Compound.makeCompound(solids)
    bb = lettering.BoundingBox()

    width = bb.xlen + 2 * margin
    depth = bb.ylen + 2 * margin
    if hanging_hole > 0:
        width += hanging_hole + margin

    plate = cq.Workplane("XY").box(width, depth, plate_thickness, centered=(True, True, False))
    if corner > 0.05:
        plate = plate.edges("|Z").fillet(min(corner, width / 2 - 0.1, depth / 2 - 0.1))

    # text() centres on the origin; shift it to the plate's text area.
    text_shift_x = -(hanging_hole + margin) / 2 if hanging_hole > 0 else 0.0
    centred = cq.Workplane(obj=lettering).translate(
        (-bb.center.x + text_shift_x, -bb.center.y, plate_thickness)
    )

    letras = None
    if engraved:
        sunk = centred.translate((0, 0, -text_depth))
        plate = plate.cut(sunk)
    elif dos_colores:
        letras = centred  # kept apart so it can take its own colour
    else:
        plate = plate.union(centred)

    if hanging_hole > 0:
        hole_x = width / 2 - margin / 2 - hanging_hole / 2
        plate = plate.cut(
            cq.Workplane("XY")
            .circle(hanging_hole / 2)
            .extrude(plate_thickness * 3)
            .translate((hole_x, 0, -plate_thickness))
        )

    if letras is not None:
        return {"Placa": plate, "Letras": letras}
    return plate
