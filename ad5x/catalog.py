"""The parametric part catalogue.

A part is a plain Python module in `piezas/` that declares:

    NAME        -- short label shown in the UI
    DESCRIPTION -- one line explaining what it is for
    PARAMS      -- list of Param, which the UI turns into a form
    def build(**values) -> cadquery.Workplane

Nothing else. Adding a part means dropping a file in that folder; no
registration step, no restart of anything but the server.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

MAX_BUILD_MM = 220.0  # AD5X build volume, per axis


@dataclass(frozen=True)
class Param:
    """One dimension the user can set, with the limits that keep it printable."""

    name: str
    label: str
    default: float | int | bool | str
    unit: str = "mm"
    minimum: float | None = None
    maximum: float | None = None
    step: float = 0.5
    help: str = ""
    # When set, the value is one of these rather than free text.
    options: tuple[str, ...] | None = None

    @property
    def kind(self) -> str:
        if self.options:
            return "choice"
        if isinstance(self.default, bool):
            return "bool"
        if isinstance(self.default, str):
            return "text"
        return "number"

    def coerce(self, raw: Any) -> float | int | bool | str:
        """Turn a form value into the right type, clamped to the declared range."""
        if self.kind == "bool":
            if isinstance(raw, bool):
                return raw
            return str(raw).strip().lower() in {"1", "true", "yes", "on", "si", "sí"}

        if self.kind == "choice":
            text = str(raw).strip()
            if text not in (self.options or ()):
                raise ValueError(f"«{self.label}»: «{text}» no está en la lista")
            return text

        if self.kind == "text":
            text = str(raw).strip()
            if self.maximum is not None and len(text) > self.maximum:
                raise ValueError(
                    f"«{self.label}»: como mucho {int(self.maximum)} caracteres"
                )
            return text

        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"«{self.label}»: «{raw}» no es un número") from exc

        # Hay campos sin unidad —una talla de anillo no son milímetros—, y
        # ahí el mensaje no debe acabar en un espacio suelto.
        unidad = f" {self.unit}" if self.unit else ""
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"«{self.label}»: el mínimo es {self.minimum}{unidad}")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"«{self.label}»: el máximo es {self.maximum}{unidad}")

        return int(value) if isinstance(self.default, int) else value


@dataclass(frozen=True)
class Part:
    slug: str
    name: str
    description: str
    params: list[Param]
    build: Callable[..., Any]
    notes: str = ""
    module: ModuleType | None = field(default=None, repr=False)

    def defaults(self) -> dict[str, Any]:
        return {p.name: p.default for p in self.params}

    def coerce_all(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Validate a whole form submission, reporting every bad field at once."""
        values: dict[str, Any] = {}
        errors: list[str] = []
        for param in self.params:
            given = raw.get(param.name, param.default)
            if given == "" or given is None:
                given = param.default
            try:
                values[param.name] = param.coerce(given)
            except ValueError as exc:
                errors.append(str(exc))
        if errors:
            raise ValueError("; ".join(errors))
        return values


def _load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"piezas.{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo cargar {path}")
    module = importlib.util.module_from_spec(spec)
    # Registering it lets a part import a sibling helper module if it needs one.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _as_part(path: Path) -> Part:
    module = _load_module(path)
    missing = [a for a in ("NAME", "PARAMS", "build") if not hasattr(module, a)]
    if missing:
        raise AttributeError(f"{path.name} no declara: {', '.join(missing)}")

    return Part(
        slug=path.stem,
        name=module.NAME,
        description=getattr(module, "DESCRIPTION", ""),
        params=list(module.PARAMS),
        build=module.build,
        notes=getattr(module, "NOTES", ""),
        module=module,
    )


def discover(parts_dir: Path) -> tuple[dict[str, Part], dict[str, str]]:
    """Load every part in the folder.

    Returns the parts that loaded and, separately, the ones that did not with
    their error — a broken part must not take the whole catalogue down.
    """
    parts: dict[str, Part] = {}
    broken: dict[str, str] = {}

    for path in sorted(parts_dir.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            part = _as_part(path)
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI, never swallowed
            broken[path.stem] = f"{type(exc).__name__}: {exc}"
        else:
            parts[part.slug] = part

    return parts, broken
