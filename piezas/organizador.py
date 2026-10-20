"""Drawer tray divided into a grid of compartments."""
import cadquery as cq

from ad5x.catalog import Param

NAME = "Bandeja organizadora"
DESCRIPTION = "Bandeja de cajón dividida en celdas, para tornillería, cables o herramienta pequeña."
NOTES = "Mide el cajón y resta 1 o 2 mm: una bandeja a medida exacta no entra."

PARAMS = [
    Param("width", "Ancho exterior", 150.0, minimum=30, maximum=215),
    Param("depth", "Fondo exterior", 100.0, minimum=30, maximum=215),
    Param("height", "Altura", 35.0, minimum=8, maximum=210),
    Param("columns", "Celdas a lo ancho", 3, unit="", minimum=1, maximum=12, step=1),
    Param("rows", "Celdas a lo largo", 2, unit="", minimum=1, maximum=12, step=1),
    Param("wall", "Espesor de pared", 1.6, minimum=0.8, maximum=8, step=0.2),
    Param("divider", "Espesor de los tabiques", 1.2, minimum=0.8, maximum=8, step=0.2),
    Param("floor", "Espesor del fondo", 1.6, minimum=0.8, maximum=8, step=0.2),
    Param("corner", "Radio de esquina", 3.0, minimum=0, maximum=25, step=0.5),
]


def build(width, depth, height, columns, rows, wall, divider, floor, corner):
    columns, rows = int(columns), int(rows)
    inner_w = width - 2 * wall
    inner_d = depth - 2 * wall
    cell_w = (inner_w - (columns - 1) * divider) / columns
    cell_d = (inner_d - (rows - 1) * divider) / rows

    if cell_w < 4 or cell_d < 4:
        raise ValueError(
            f"Con {columns}×{rows} celdas cada hueco queda en "
            f"{cell_w:.1f}×{cell_d:.1f} mm: reduce las divisiones o agranda la bandeja"
        )
    if floor >= height:
        raise ValueError("El fondo es más alto que la bandeja entera")

    shell = cq.Workplane("XY").box(width, depth, height, centered=(True, True, False))
    if corner > 0.05:
        shell = shell.edges("|Z").fillet(min(corner, width / 2 - 0.1, depth / 2 - 0.1))

    # Hollow out one pocket per cell, leaving walls and dividers standing.
    pocket_depth = height - floor + 1
    for column in range(columns):
        for row in range(rows):
            x = -inner_w / 2 + column * (cell_w + divider) + cell_w / 2
            y = -inner_d / 2 + row * (cell_d + divider) + cell_d / 2
            pocket = cq.Workplane("XY").box(
                cell_w, cell_d, pocket_depth, centered=(True, True, False)
            )
            inner_fillet = min(corner - wall, cell_w / 2 - 0.5, cell_d / 2 - 0.5)
            if inner_fillet > 0.3:
                pocket = pocket.edges("|Z").fillet(inner_fillet)
            shell = shell.cut(pocket.translate((x, y, floor)))

    return shell
