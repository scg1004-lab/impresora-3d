"""Build a part and export it as STL, checking it will actually fit the bed."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import cadquery as cq

from .catalog import MAX_BUILD_MM, Part

# Rough rule of thumb: finer than this and the slicer gains nothing, the STL
# just gets heavier.
STL_TOLERANCE = 0.01
STL_ANGULAR_TOLERANCE = 0.1


@dataclass(frozen=True)
class Build:
    path: Path
    size: tuple[float, float, float]
    volume_cm3: float
    warnings: list[str]
    # For a part made of several colours: the 3MF Orca will slice, and the
    # name of each piece in tool order.
    project: Path | None = None
    parts: tuple[str, ...] = ()

    @property
    def size_label(self) -> str:
        x, y, z = self.size
        return f"{x:.1f} × {y:.1f} × {z:.1f} mm"


def _slugify(text: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return clean or "pieza"


class Mesh:
    """Triangles ready to write, for parts that are not built with CAD.

    A scaled-down figure comes from a downloaded mesh, not from solids, and
    squeezing it through CadQuery would cost minutes and gain nothing.
    """

    def __init__(self, triangles: Any, name: str = "pieza") -> None:
        self.triangles = triangles
        self.name = name


def _solid_of(result: Any) -> cq.Shape:
    """Accept whatever a part's build() returns and get a single shape out."""
    if isinstance(result, cq.Workplane):
        solids = result.vals()
        if not solids:
            raise ValueError("La pieza no ha producido ningún sólido")
        if len(solids) == 1:
            return solids[0]
        return cq.Compound.makeCompound(solids)
    if isinstance(result, cq.Shape):
        return result
    if isinstance(result, cq.Assembly):
        return result.toCompound()
    raise TypeError(
        f"build() devolvió {type(result).__name__}; se esperaba un Workplane de CadQuery"
    )


def _write_mesh(part: Part, mesh: Mesh, output_dir: Path) -> Build:
    """Export a part that produced triangles rather than CAD solids."""
    import numpy as np

    from .mesh import write_stl

    triangles = np.asarray(mesh.triangles, dtype=np.float64)
    if triangles.size == 0:
        raise ValueError("La pieza no ha producido geometría")

    points = triangles.reshape(-1, 3)
    size = tuple(points.max(axis=0) - points.min(axis=0))

    warnings: list[str] = []
    for axis, length in zip("XYZ", size):
        if length > MAX_BUILD_MM:
            warnings.append(
                f"No cabe en la cama: {length:.1f} mm en {axis}, "
                f"el máximo es {MAX_BUILD_MM:.0f} mm"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = output_dir / f"{stamp}_{_slugify(mesh.name)}.stl"
    write_stl(triangles, path, mesh.name)

    return Build(
        path=path,
        size=size,  # type: ignore[arg-type]
        volume_cm3=0.0,  # the slicer reports the real figure
        warnings=warnings,
    )


def _write_multicolour(part: Part, pieces: dict, output_dir: Path) -> Build:
    """A part whose build() returned named pieces, one colour each.

    Writes two files: an STL of everything together, which is what the viewer
    shows and what you would take on a pendrive, and the 3MF project that
    carries the colour assignment for the slicer.
    """
    from .proyecto import Parte, escribir_proyecto

    named = [(name, _solid_of(shape)) for name, shape in pieces.items() if shape is not None]
    if not named:
        raise ValueError("La pieza no ha producido ningún sólido")

    partes = []
    for index, (name, shape) in enumerate(named):
        vertices, triangles = shape.tessellate(STL_TOLERANCE * 3)
        partes.append(
            Parte(
                nombre=name,
                vertices=[(v.x, v.y, v.z) for v in vertices],
                triangulos=triangles,
                extrusor=index + 1,
            )
        )

    whole = named[0][1] if len(named) == 1 else cq.Compound.makeCompound(
        [shape for _, shape in named]
    )
    bb = whole.BoundingBox()
    size = (bb.xlen, bb.ylen, bb.zlen)

    warnings = [
        f"No cabe en la cama: {length:.1f} mm en {axis}, "
        f"el máximo es {MAX_BUILD_MM:.0f} mm"
        for axis, length in zip("XYZ", size)
        if length > MAX_BUILD_MM
    ]
    if len(partes) > 4:
        warnings.append(
            f"{len(partes)} colores, y el IFS tiene 4 bahías: se imprimirán "
            "los cuatro primeros"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    base = f"{stamp}_{_slugify(part.name)}"

    stl = output_dir / f"{base}.stl"
    cq.exporters.export(whole, str(stl), tolerance=STL_TOLERANCE,
                        angularTolerance=STL_ANGULAR_TOLERANCE)

    # Centre it on the bed, like the slicer would.
    centre = (110.0 - (bb.xmin + bb.xmax) / 2, 110.0 - (bb.ymin + bb.ymax) / 2)
    project = escribir_proyecto(partes, output_dir / f"{base}.3mf", centre)

    return Build(
        path=stl,
        size=size,
        volume_cm3=whole.Volume() / 1000.0,
        warnings=warnings,
        project=project,
        parts=tuple(p.nombre for p in partes),
    )


def build_part(part: Part, values: dict[str, Any], output_dir: Path) -> Build:
    """Run a part's build() with the given dimensions and write the STL."""
    try:
        result = part.build(**values)
    except TypeError as exc:
        raise ValueError(f"Los parámetros no encajan con la pieza: {exc}") from exc

    if isinstance(result, Mesh):
        return _write_mesh(part, result, output_dir)

    if isinstance(result, dict):
        return _write_multicolour(part, result, output_dir)

    shape = _solid_of(result)

    if shape.Volume() <= 0:
        raise ValueError(
            "El resultado tiene volumen cero: revisa las cotas, probablemente "
            "un corte se ha comido la pieza entera"
        )

    bb = shape.BoundingBox()
    size = (bb.xlen, bb.ylen, bb.zlen)

    warnings: list[str] = []
    for axis, length in zip("XYZ", size):
        if length > MAX_BUILD_MM:
            warnings.append(
                f"No cabe en la cama: {length:.1f} mm en {axis}, "
                f"el máximo es {MAX_BUILD_MM:.0f} mm"
            )

    thin = min(size)
    if thin < 0.8:
        warnings.append(
            f"La pared más fina mide {thin:.2f} mm: por debajo de 0,8 mm "
            "(dos perímetros de una boquilla de 0,4) puede no imprimirse"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = output_dir / f"{stamp}_{_slugify(part.name)}.stl"

    cq.exporters.export(
        shape,
        str(path),
        tolerance=STL_TOLERANCE,
        angularTolerance=STL_ANGULAR_TOLERANCE,
    )

    return Build(
        path=path,
        size=size,
        volume_cm3=shape.Volume() / 1000.0,
        warnings=warnings,
    )
