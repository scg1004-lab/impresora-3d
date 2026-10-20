"""Wrap a sliced G-code in the .gcode.3mf container the AD5X will open.

Two things were learned the hard way against the real printer on 2026-10-18:

* A bare `.gcode` is accepted by the upload endpoint but can take minutes to
  appear in the printer's file list, or never appear. A `.3mf` shows up in
  about five seconds.
* Appearing in the list is not the same as being printable. A hand-made
  container was listed and then refused with a file error on screen.

The structure here is copied from a file Orca itself produced with
*Export plate sliced file* (`distribucion/plantilla-3mf/`). The piece that
matters most is `model_settings.config`: it is what points the firmware at
the G-code inside the archive. The printer's own profile blob travels as a
template, since it describes the machine rather than the job.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "distribucion" / "plantilla-3mf"
PREVIEWS = (
    "plate_1.png",
    "plate_1_small.png",
    "plate_no_light_1.png",
    "top_1.png",
    "pick_1.png",
)

PLA_DENSITY = 1.24  # g/cm3, for the weight the printer displays
DEFAULT_BBOX = [105.0, 105.0, 115.0, 115.0]
SCAN_LINES = 40000
HEADER_CHARS = 80000

# Flashforge's filament catalogue ids, by material.
TRAY_IDS = {"PLA": "GFA00", "ABS": "GFB99", "PETG": "GFG00", "ASA": "GFB98", "TPU": "GFU00"}

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="png" ContentType="image/png"/>
 <Default Extension="gcode" ContentType="text/x.gcode"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
 <Relationship Target="/Metadata/plate_1.png" Id="rel-2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"/>
 <Relationship Target="/Metadata/plate_1.png" Id="rel-4" Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-middle"/>
 <Relationship Target="/Metadata/plate_1_small.png" Id="rel-5" Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-small"/>
</Relationships>"""

MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">
 <metadata name="Application">BambuStudio-2.3.1</metadata>
 <metadata name="BambuStudio:3mfVersion">1</metadata>
 <resources>
 </resources>
 <build/>
</model>"""

# Points the firmware at the G-code and the previews. Without this the file
# lists but will not open.
MODEL_SETTINGS = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <plate>
    <metadata key="plater_id" value="1"/>
    <metadata key="plater_name" value=""/>
    <metadata key="locked" value="false"/>
    <metadata key="filament_map_mode" value="Auto For Flush"/>
    <metadata key="filament_maps" value="1 1"/>
    <metadata key="gcode_file" value="Metadata/plate_1.gcode"/>
    <metadata key="thumbnail_file" value="Metadata/plate_1.png"/>
    <metadata key="thumbnail_no_light_file" value="Metadata/plate_no_light_1.png"/>
    <metadata key="top_file" value="Metadata/top_1.png"/>
    <metadata key="pick_file" value="Metadata/pick_1.png"/>
    <metadata key="pattern_bbox_file" value="Metadata/plate_1.json"/>
  </plate>
</config>"""

MODEL_SETTINGS_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/Metadata/plate_1.gcode" Id="rel-1" Type="http://schemas.bambulab.com/package/2021/gcode"/>
</Relationships>"""


class PackError(RuntimeError):
    pass


def _header(text: str) -> str:
    return text[:HEADER_CHARS]


def _number(text: str, pattern: str, fallback: float) -> float:
    match = re.search(pattern, _header(text))
    if not match:
        return fallback
    try:
        return float(match.group(1))
    except ValueError:
        return fallback


def _bbox(text: str) -> list[float]:
    """Where the part sits on the bed, read from the moves themselves."""
    xs: list[float] = []
    ys: list[float] = []
    for index, line in enumerate(text.splitlines()):
        if index > SCAN_LINES:
            break
        if not line or line[0] != "G":
            continue
        x = re.search(r"\bX(-?[\d.]+)", line)
        y = re.search(r"\bY(-?[\d.]+)", line)
        if x and y:
            try:
                xs.append(float(x.group(1)))
                ys.append(float(y.group(1)))
            except ValueError:
                pass
    if not xs or not ys:
        return list(DEFAULT_BBOX)
    return [min(xs), min(ys), max(xs), max(ys)]


def _seconds(text: str) -> int:
    """The slicer writes '1h 10m 24s'; the printer wants plain seconds."""
    match = re.search(
        r"estimated printing time \(normal mode\)\s*=\s*(.+)", _header(text)
    )
    if not match:
        return 0
    units = {"h": 3600, "m": 60, "s": 1}
    return sum(
        int(value) * units[unit]
        for value, unit in re.findall(r"(\d+)\s*([hms])", match.group(1))
    )


def _grams(text: str) -> float:
    """What the job weighs. The profile often reports zero, so fall back."""
    reported = _number(text, r";\s*total filament used \[g\]\s*=\s*([\d.]+)", 0.0)
    if reported > 0:
        return reported
    volume = _number(text, r";\s*filament used \[cm3\]\s*=\s*([\d.]+)", 0.0)
    return round(volume * PLA_DENSITY, 2)


def _filaments(text: str) -> list[tuple[str, str]]:
    """(type, colour) per tool, as declared in the header."""

    def values(key: str) -> list[str]:
        match = re.search(rf";\s*{key}\s*=\s*(.+)", _header(text))
        if not match:
            return []
        return [v.strip().strip('"') for v in match.group(1).split(";") if v.strip()]

    types = values("filament_type") or ["PLA"]
    colours = values("filament_colour") or ["#FFFFFF"]
    count = max(len(types), len(colours))
    return [
        (
            types[i] if i < len(types) else types[0],
            colours[i] if i < len(colours) else colours[0],
        )
        for i in range(count)
    ]


def _slice_info(text: str, nozzle: float, name: str) -> str:
    """The job summary: machine, time, weight and the filaments it uses."""
    grams = _grams(text)
    filaments = _filaments(text)
    maps = " ".join("1" for _ in filaments) or "1"

    rows = "".join(
        f'    <filament id="{index + 1}" tray_info_idx="{TRAY_IDS.get(kind.upper(), "GFA00")}"'
        f' type="{kind}" color="{colour}" used_m="0.00" used_g="{grams}" />\n'
        for index, (kind, colour) in enumerate(filaments)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<config>\n"
        "  <header>\n"
        '    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
        '    <header_item key="X-BBL-Client-Version" value=""/>\n'
        "  </header>\n"
        "  <plate>\n"
        '    <metadata key="index" value="1"/>\n'
        '    <metadata key="printer_model_id" value="Flashforge-AD5X"/>\n'
        f'    <metadata key="nozzle_diameters" value="{nozzle}"/>\n'
        '    <metadata key="timelapse_type" value="0"/>\n'
        f'    <metadata key="prediction" value="{_seconds(text)}"/>\n'
        f'    <metadata key="weight" value="{grams}"/>\n'
        '    <metadata key="outside" value="false"/>\n'
        '    <metadata key="support_used" value="false"/>\n'
        '    <metadata key="label_object_enabled" value="false"/>\n'
        f'    <metadata key="filament_maps" value="{maps}"/>\n'
        f'    <object identify_id="1" name="{name}" skipped="false" />\n'
        f"{rows}"
        "  </plate>\n"
        "</config>"
    )


def gcode_to_3mf(gcode: Path, target: Path | None = None) -> Path:
    """Pack a sliced G-code into a .gcode.3mf. Returns the new path."""
    if not TEMPLATE_DIR.is_dir():
        raise PackError(
            f"Falta la plantilla en {TEMPLATE_DIR}. Se obtiene exportando una "
            "pieza desde Orca con «Exportar los objetos laminados de la "
            "bandeja a un archivo»."
        )

    text = gcode.read_text(encoding="utf-8", errors="ignore")
    body = text.encode("utf-8")

    bbox = _bbox(text)
    layer_height = _number(text, r";\s*layer_height\s*=\s*([\d.]+)", 0.2)
    nozzle = _number(text, r";\s*nozzle_diameter\s*=\s*([\d.]+)", 0.4)
    model_name = gcode.stem + ".stl"

    plate = {
        "bbox_all": bbox,
        "bbox_objects": [
            {
                "area": max((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]), 1.0),
                "bbox": bbox,
                "id": 1,
                "layer_height": layer_height,
                "name": model_name,
            }
        ],
        "bed_type": "hot_plate",
        "filament_colors": [colour for _, colour in _filaments(text)],
        "filament_ids": [0],
        "first_extruder": 0,
        "is_seq_print": False,
        "nozzle_diameter": nozzle,
        "version": 2,
    }

    # Orca names these .gcode.3mf; keep that so the printer sees what it expects.
    out = target or gcode.with_suffix(".gcode.3mf")
    profile = (TEMPLATE_DIR / "project_settings.config").read_bytes()

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", RELS)
        archive.writestr("3D/3dmodel.model", MODEL)
        archive.writestr("Metadata/model_settings.config", MODEL_SETTINGS)
        archive.writestr("Metadata/_rels/model_settings.config.rels", MODEL_SETTINGS_RELS)
        archive.writestr("Metadata/project_settings.config", profile)
        archive.writestr("Metadata/slice_info.config", _slice_info(text, nozzle, model_name))
        archive.writestr("Metadata/plate_1.json", json.dumps(plate))
        archive.writestr("Metadata/plate_1.gcode", body)
        archive.writestr(
            "Metadata/plate_1.gcode.md5", hashlib.md5(body).hexdigest().upper()
        )
        for name in PREVIEWS:
            archive.writestr(f"Metadata/{name}", (TEMPLATE_DIR / name).read_bytes())

    return out
