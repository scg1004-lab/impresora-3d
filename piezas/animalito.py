"""Figuras pequeñas: coge un modelo de `modelos/` y lo lleva al tamaño pedido."""
import re
from pathlib import Path

import numpy as np

from ad5x.cad import Mesh
from ad5x.catalog import Param
from ad5x.mesh import threemf_to_stl

MODELS_DIR = Path(__file__).resolve().parent.parent / "modelos"
# Converted copies live apart, or they would show up as extra animals.
CACHE_DIR = MODELS_DIR / ".convertidos"
MAX_HEIGHT = 20.0  # mm; por encima deja de ser una figurita de mesa

NAME = "Animalito"
DESCRIPTION = "Una figura de la carpeta de modelos, al tamaño que elijas."
NOTES = (
    "«Tamaño total» es la medida más larga de la figura: con 20 mm cabe en un "
    "cubo de 2 cm, que es lo que suele querer decir «pequeñita». Por altura, "
    "un bicho alargado como la serpiente se va a 15 cm de largo. "
    "Ojo con los articulados: por debajo de unos 4 cm las juntas se pegan y la "
    "figura sale de una pieza, bonita pero rígida."
)

BY_TOTAL = "Tamaño total"
BY_HEIGHT = "Altura"


def _catalogue() -> list[tuple[str, Path]]:
    """The figures on disk, with a readable label each."""
    if not MODELS_DIR.is_dir():
        return []

    found: list[tuple[str, Path]] = []
    for path in sorted(MODELS_DIR.iterdir()):
        if path.is_dir() or path.suffix.lower() not in {".3mf", ".stl"}:
            continue
        # An .stl beside its .3mf is a leftover conversion, not another animal.
        if path.suffix.lower() == ".stl" and path.with_suffix(".3mf").is_file():
            continue
        # "02_mini-shark-articulated.3mf" -> "Mini shark articulated"
        label = re.sub(r"^\d+[_-]*", "", path.stem).replace("-", " ").replace("_", " ")
        found.append((label.strip().capitalize() or path.stem, path))
    return found


_FIGURES = _catalogue()
_BY_LABEL = {label: path for label, path in _FIGURES}

PARAMS = [
    Param(
        "animal",
        "Animal",
        _FIGURES[0][0] if _FIGURES else "",
        unit="",
        options=tuple(label for label, _ in _FIGURES),
        help="Las figuras de la carpeta modelos/",
    ),
    Param("size", "Medida", 20.0, minimum=5, maximum=MAX_HEIGHT, step=0.5),
    Param(
        "measure",
        "Esa medida es...",
        BY_TOTAL,
        unit="",
        options=(BY_TOTAL, BY_HEIGHT),
        help="El tamaño total es la dimensión más larga",
    ),
]

NOTES += (
    ""
    if _FIGURES
    else "  ⚠ No hay ninguna figura en modelos/: copia ahí los .3mf o .stl."
)


def _triangles(path: Path) -> np.ndarray:
    """The figure's triangles, whatever format it came in."""
    if path.suffix.lower() == ".3mf":
        # Reuse the 3MF reader: it writes an STL, which we then read back.
        CACHE_DIR.mkdir(exist_ok=True)
        cache = CACHE_DIR / (path.stem + ".stl")
        if not cache.is_file() or cache.stat().st_mtime < path.stat().st_mtime:
            threemf_to_stl(path, cache)
        path = cache

    with path.open("rb") as handle:
        handle.seek(80)
        count = int.from_bytes(handle.read(4), "little")
        raw = np.frombuffer(
            handle.read(count * 50), dtype=[("f", "<12f4"), ("attr", "<u2")]
        )
    return raw["f"][:, 3:12].reshape(-1, 3, 3).astype(np.float64)


def build(animal, size, measure):
    if not _FIGURES:
        raise ValueError(
            "No hay figuras en la carpeta modelos/. Descarga alguna de "
            "printables.com o makerworld.com y déjala ahí."
        )

    path = _BY_LABEL.get(animal)
    if path is None:
        raise ValueError(f"No encuentro «{animal}» en modelos/")

    triangles = _triangles(path)
    points = triangles.reshape(-1, 3)
    low, high = points.min(axis=0), points.max(axis=0)
    extent = high - low

    current = float(extent[2] if measure == BY_HEIGHT else extent.max())
    if current <= 0:
        raise ValueError(f"«{animal}» no tiene esa medida: el modelo parece plano")

    # Uniform scale, then sit it on the bed with its corner at the origin.
    scaled = (triangles - low) * (size / current)
    return Mesh(scaled, name=f"{animal} {size:.0f}mm")
