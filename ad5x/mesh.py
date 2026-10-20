"""Convert a 3MF model into a plain STL.

Model sites hand out 3MF files written by whatever slicer the author used, and
those carry a format version. Orca refuses one newer than its own ("File
Version 2.4.0.70 not supported"), which is what a MakerWorld download hits.

An STL has no version and no metadata — just triangles — so pulling the
geometry out sidesteps the whole problem. This reads the 3MF core spec:
meshes, the components that reuse them, and the build items that place them.
"""
from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np

NS_PRODUCTION = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
MODEL_ENTRY = "3d/3dmodel.model"

# 3MF may declare any of these; STL is always millimetres.
TO_MM = {
    "micron": 0.001,
    "millimeter": 1.0,
    "centimeter": 10.0,
    "inch": 25.4,
    "foot": 304.8,
    "meter": 1000.0,
}

MAX_RECURSION = 12  # components can nest; guard against a malformed cycle


class MeshError(RuntimeError):
    pass


def _tag(element: ET.Element) -> str:
    """Local tag name, ignoring whichever namespace the writer used."""
    return element.tag.rsplit("}", 1)[-1]


def _find(parent: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in parent if _tag(child) == name]


def _matrix(raw: str | None) -> np.ndarray:
    """A 3MF transform: 12 numbers, row-major 4x3, translation last."""
    if not raw:
        return np.eye(4)
    values = [float(v) for v in raw.replace(",", " ").split()]
    if len(values) != 12:
        return np.eye(4)

    m = np.eye(4)
    m[:3, :3] = np.array(values[:9]).reshape(3, 3).T  # 3MF rows are our columns
    m[:3, 3] = values[9:]
    return m


def _normalise(path: str) -> str:
    """A p:path reference as a zip entry name: no leading slash, lowercased."""
    return path.lstrip("/").lower()


def _load(archive: zipfile.ZipFile, entry: str) -> dict[str, ET.Element]:
    """Objects declared in one .model part, by id.

    Parsed incrementally and cleared as it goes: the geometry part of a
    detailed model runs to tens of megabytes, and holding the whole tree is
    what would make this fall over.
    """
    actual = next(
        (n for n in archive.namelist() if n.lower() == _normalise(entry)), None
    )
    if actual is None:
        return {}

    objects: dict[str, ET.Element] = {}
    with archive.open(actual) as handle:
        for event, element in ET.iterparse(handle, events=("end",)):
            if _tag(element) != "object":
                continue
            object_id = element.get("id")
            if object_id:
                objects[object_id] = element
            # Not clearing here on purpose: the objects we keep are the point.
    return objects


def _read_mesh(obj: ET.Element) -> tuple[np.ndarray, np.ndarray] | None:
    meshes = _find(obj, "mesh")
    if not meshes:
        return None

    mesh = meshes[0]
    vertex_nodes = _find(mesh, "vertices")
    triangle_nodes = _find(mesh, "triangles")
    if not vertex_nodes or not triangle_nodes:
        return None

    vertices = np.array(
        [
            (float(v.get("x", 0)), float(v.get("y", 0)), float(v.get("z", 0)))
            for v in vertex_nodes[0]
        ],
        dtype=np.float64,
    )
    triangles = np.array(
        [
            (int(t.get("v1", 0)), int(t.get("v2", 0)), int(t.get("v3", 0)))
            for t in triangle_nodes[0]
        ],
        dtype=np.int64,
    )

    if len(vertices) == 0 or len(triangles) == 0:
        return None
    return vertices, triangles


PATH_ATTR = f"{{{NS_PRODUCTION}}}path"


def _collect(
    archive: zipfile.ZipFile,
    parts: dict[str, dict[str, ET.Element]],
    part: str,
    object_id: str,
    transform: np.ndarray,
    out: list[np.ndarray],
    depth: int = 0,
) -> None:
    """Walk one object, following components, emitting placed triangles.

    A component may point into another .model part (the production
    extension), which is where detailed models keep their geometry.
    """
    if depth > MAX_RECURSION:
        return

    if part not in parts:
        parts[part] = _load(archive, part)
    obj = parts[part].get(object_id)
    if obj is None:
        return

    mesh = _read_mesh(obj)
    if mesh is not None:
        vertices, triangles = mesh
        # Homogeneous coordinates so one matrix multiply places everything.
        padded = np.hstack([vertices, np.ones((len(vertices), 1))])
        placed = (transform @ padded.T).T[:, :3]
        out.append(placed[triangles])

    for group in _find(obj, "components"):
        for component in _find(group, "component"):
            child = component.get("objectid")
            if not child:
                continue
            target = component.get(PATH_ATTR) or component.get("path")
            _collect(
                archive,
                parts,
                _normalise(target) if target else part,
                child,
                transform @ _matrix(component.get("transform")),
                out,
                depth + 1,
            )


def write_stl(triangles: np.ndarray, target: Path, name: str = "modelo") -> None:
    """Binary STL: 80-byte header, count, then 50 bytes per facet."""
    count = len(triangles)

    # Facet normals, with degenerate triangles left as zero (readers cope).
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    normals = np.cross(b - a, c - a)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, lengths, out=np.zeros_like(normals), where=lengths > 0)

    # One record per facet: 12 floats then a 2-byte attribute word.
    records = np.zeros((count, 12), dtype=np.float32)
    records[:, 0:3] = normals
    records[:, 3:6] = a
    records[:, 6:9] = b
    records[:, 9:12] = c

    body = np.zeros(count, dtype=[("f", "<12f4"), ("attr", "<u2")])
    body["f"] = records

    with target.open("wb") as handle:
        handle.write(name.encode("ascii", "replace")[:80].ljust(80, b"\0"))
        handle.write(struct.pack("<I", count))
        handle.write(body.tobytes())


def threemf_to_stl(source: Path, target: Path) -> int:
    """Write the 3MF's geometry as an STL. Returns the triangle count."""
    if not zipfile.is_zipfile(source):
        raise MeshError(f"«{source.name}» no es un 3MF válido")

    pieces: list[np.ndarray] = []

    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        entry = next((n for n in names if n.lower() == MODEL_ENTRY), None) or next(
            (n for n in names if n.lower().endswith(".model")), None
        )
        if entry is None:
            raise MeshError(f"«{source.name}» no contiene ningún modelo 3D")

        with archive.open(entry) as handle:
            root = ET.parse(handle).getroot()

        scale = TO_MM.get((root.get("unit") or "millimeter").lower(), 1.0)

        # Objects of the root part, keyed by part path so components can cross
        # into the geometry parts.
        parts: dict[str, dict[str, ET.Element]] = {
            _normalise(entry): {
                obj.get("id"): obj
                for resources in _find(root, "resources")
                for obj in _find(resources, "object")
                if obj.get("id")
            }
        }

        items = [
            item for build in _find(root, "build") for item in _find(build, "item")
        ]
        if items:
            for item in items:
                object_id = item.get("objectid")
                if object_id:
                    _collect(
                        archive,
                        parts,
                        _normalise(entry),
                        object_id,
                        _matrix(item.get("transform")),
                        pieces,
                    )
        else:
            # No build section: take every object in the root part.
            for object_id in list(parts[_normalise(entry)]):
                _collect(archive, parts, _normalise(entry), object_id, np.eye(4), pieces)

    if not pieces:
        raise MeshError(f"«{source.name}» no tiene geometría que convertir")

    triangles = np.concatenate(pieces, axis=0)
    if scale != 1.0:
        triangles = triangles * scale

    write_stl(triangles, target, source.stem)
    return len(triangles)
