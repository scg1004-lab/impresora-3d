"""L-bracket with counterbored holes and an optional gusset."""
import cadquery as cq

from ad5x.catalog import Param

NAME = "Escuadra en L"
DESCRIPTION = "Soporte en ángulo recto con agujeros pasantes y refuerzo triangular opcional."
NOTES = (
    "Se imprime de pie sobre el canto para que la L no necesite soportes. "
    "Para M4 deja 4,5 mm de agujero; para M3, 3,4 mm."
)

PARAMS = [
    Param("arm_a", "Brazo vertical", 60.0, minimum=15, maximum=200),
    Param("arm_b", "Brazo horizontal", 60.0, minimum=15, maximum=200),
    Param("width", "Anchura", 30.0, minimum=8, maximum=200),
    Param("thickness", "Espesor", 5.0, minimum=1.5, maximum=20, step=0.5),
    Param("hole", "Diámetro de agujero", 4.5, minimum=0, maximum=20, step=0.1),
    Param("hole_inset", "Distancia del agujero al extremo", 12.0, minimum=4, maximum=100),
    Param("holes_per_arm", "Agujeros por brazo", 1, unit="", minimum=0, maximum=4, step=1),
    Param("gusset", "Refuerzo triangular", True),
]


def build(arm_a, arm_b, width, thickness, hole, hole_inset, holes_per_arm, gusset):
    if hole >= width - 2:
        raise ValueError(
            f"Un agujero de {hole} mm no cabe en una escuadra de {width} mm de ancho"
        )
    if hole_inset + hole / 2 > min(arm_a, arm_b) - 1:
        raise ValueError("Los agujeros se salen del brazo: baja la distancia al extremo")

    # L profile drawn in XZ, then extruded across the width.
    profile = (
        cq.Workplane("XZ")
        .polyline([
            (0, 0),
            (arm_b, 0),
            (arm_b, thickness),
            (thickness, thickness),
            (thickness, arm_a),
            (0, arm_a),
        ])
        .close()
        .extrude(width)
        .translate((0, width / 2, 0))
    )

    if gusset:
        reach = min(arm_a, arm_b) * 0.7
        if reach > thickness + 2:
            rib = (
                cq.Workplane("XZ")
                .polyline([
                    (thickness, thickness),
                    (reach, thickness),
                    (thickness, reach),
                ])
                .close()
                .extrude(thickness)
                .translate((0, thickness / 2, 0))
            )
            profile = profile.union(rib)

    if hole > 0 and holes_per_arm > 0:
        spacing = width / (holes_per_arm + 1)
        offsets = [spacing * (i + 1) - width / 2 for i in range(int(holes_per_arm))]

        for y in offsets:
            # Through the horizontal arm, drilled down Z.
            profile = profile.cut(
                cq.Workplane("XY")
                .circle(hole / 2)
                .extrude(thickness * 3)
                .translate((arm_b - hole_inset, y, -thickness))
            )
            # Through the vertical arm, drilled along X.
            profile = profile.cut(
                cq.Workplane("YZ")
                .circle(hole / 2)
                .extrude(thickness * 3)
                .translate((-thickness, y, arm_a - hole_inset))
            )

    return profile
