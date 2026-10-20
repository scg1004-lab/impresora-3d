"""Read back what a sliced G-code needs, to drive the IFS material station.

A multi-colour job declares one filament per tool. Before the printer can run
it, each tool has to be pointed at a physical IFS slot — that is what this
module works out, and what `printer.upload()` sends along.
"""
from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

HEADER_LINES = 600  # the config block sits at the top; no need to read further
MAX_TOOLS = 4  # the IFS holds four spools

_TOOL_CHANGE = re.compile(r"^T(\d+)\s*$")


@dataclass(frozen=True)
class Tool:
    """One tool (colour) a G-code uses, before it is mapped to a slot."""

    tool_id: int
    colour: str
    material: str

    @property
    def label(self) -> str:
        return f"Herramienta {self.tool_id + 1} · {self.material} {self.colour}"


@dataclass(frozen=True)
class GcodeInfo:
    tools: list[Tool]
    layers: int | None
    estimate: str | None

    @property
    def multicolour(self) -> bool:
        return len(self.tools) > 1


def _header_values(line: str) -> list[str]:
    """Orca writes per-filament settings as a ;-separated list."""
    raw = line.split("=", 1)[1].strip()
    return [part.strip().strip('"') for part in raw.split(";") if part.strip()]


def is_sliced(path: Path) -> bool:
    """Whether a file is a print job, as opposed to a model to be sliced.

    The extension does not say: a .3mf from a model site holds geometry and
    still needs slicing, while the one a slicer produces carries the G-code
    inside. Only the contents tell them apart.
    """
    suffix = path.suffix.lower()
    if suffix in {".gcode", ".gx"}:
        return True
    if suffix != ".3mf" or not zipfile.is_zipfile(path):
        return False

    try:
        with zipfile.ZipFile(path) as archive:
            return any(n.lower().endswith(".gcode") for n in archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def _lines(path: Path) -> Iterator[str]:
    """Yield the G-code text, whether it is plain or packed inside a 3MF.

    A sliced .3mf is a zip with the G-code under Metadata/. Read as text it is
    binary noise, so unpack it first.
    """
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            inner = [n for n in archive.namelist() if n.lower().endswith(".gcode")]
            if not inner:
                raise ValueError(
                    f"«{path.name}» es un 3MF sin G-code dentro: parece un "
                    "proyecto sin laminar, no un fichero listo para imprimir"
                )
            # Plates are numbered; the first is the one that gets printed.
            with archive.open(sorted(inner)[0]) as handle:
                for raw in handle:
                    yield raw.decode("utf-8", "ignore")
        return

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        yield from handle


def read_info(path: Path) -> GcodeInfo:
    """Which tools a G-code actually uses, with their declared colours."""
    colours: list[str] = []
    materials: list[str] = []
    layers: int | None = None
    estimate: str | None = None
    used: set[int] = set()

    for index, line in enumerate(_lines(path)):
        if index < HEADER_LINES:
            if line.startswith("; filament_colour =") and not colours:
                colours = _header_values(line)
            elif line.startswith("; filament_type =") and not materials:
                materials = _header_values(line)
            elif layers is None and "total layer number" in line:
                try:
                    layers = int(line.split(":", 1)[1])
                except ValueError:
                    pass
            elif estimate is None and "estimated printing time (normal mode)" in line:
                estimate = line.split("=", 1)[1].strip()

        # Tool changes appear throughout the body, not just the header.
        match = _TOOL_CHANGE.match(line.strip())
        if match:
            tool = int(match.group(1))
            if tool < MAX_TOOLS:
                used.add(tool)

    if not used:
        used = {0}

    tools = [
        Tool(
            tool_id=tool,
            colour=colours[tool] if tool < len(colours) else "#FFFFFF",
            material=materials[tool] if tool < len(materials) else "PLA",
        )
        for tool in sorted(used)
    ]

    return GcodeInfo(tools=tools, layers=layers, estimate=estimate)


def default_mappings(info: GcodeInfo) -> list[dict[str, object]]:
    """Map each tool to the slot of the same number, as a starting point."""
    return [
        {
            "toolId": tool.tool_id,
            "slotId": tool.tool_id + 1,  # slots are 1-based
            "materialName": tool.material,
            "toolMaterialColor": tool.colour,
            "slotMaterialColor": tool.colour,
        }
        for tool in info.tools
    ]
