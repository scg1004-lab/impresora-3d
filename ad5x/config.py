"""Configuration, read once from the environment / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


@dataclass(frozen=True)
class Config:
    # --- Printer (LAN) -----------------------------------------------------
    printer_ip: str | None
    serial_number: str | None
    check_code: str | None
    printer_port: int

    # --- Slicer ------------------------------------------------------------
    slicer_exe: Path | None
    system_profiles: Path | None

    # --- Print defaults ----------------------------------------------------
    leveling_before_print: bool

    # --- Paths -------------------------------------------------------------
    parts_dir: Path
    output_dir: Path
    profiles_dir: Path

    @property
    def printer_configured(self) -> bool:
        # The address is only a hint: if DHCP moves the printer, it is found
        # again by discovery. What identifies it is the serial and its code.
        return bool(self.serial_number and self.check_code)

    @property
    def slicer_available(self) -> bool:
        return self.slicer_exe is not None and self.slicer_exe.is_file()

    @property
    def vendor_profiles_available(self) -> bool:
        return self.system_profiles is not None


def _find_slicer() -> Path | None:
    """Locate the Orca binary, preferring an explicit override."""
    override = os.getenv("SLICER_EXE")
    if override:
        candidate = Path(override)
        return candidate if candidate.is_file() else None

    program_files = Path(os.getenv("PROGRAMFILES", r"C:\Program Files"))
    program_files_x86 = Path(os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    local_programs = Path(os.getenv("LOCALAPPDATA", "")) / "Programs"

    # Known layouts, most specific first. Orca-Flashforge installs one level
    # deeper than upstream OrcaSlicer does.
    candidates = [
        program_files / "Flashforge" / "Orca-Flashforge" / "orca-flashforge.exe",
        local_programs / "Flashforge" / "Orca-Flashforge" / "orca-flashforge.exe",
        program_files / "Orca-Flashforge" / "orca-flashforge.exe",
        program_files / "OrcaSlicer" / "orca-slicer-console.exe",
        program_files / "OrcaSlicer" / "orca-slicer.exe",
        program_files_x86 / "OrcaSlicer" / "orca-slicer.exe",
        local_programs / "OrcaSlicer" / "orca-slicer.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _system_profiles(slicer_exe: Path | None) -> Path | None:
    """The vendor profile folder that ships with the slicer."""
    if slicer_exe is None:
        return None
    folder = slicer_exe.parent / "resources" / "profiles" / "Flashforge"
    return folder if folder.is_dir() else None


def load() -> Config:
    slicer_exe = _find_slicer()
    return Config(
        printer_ip=os.getenv("PRINTER_IP") or None,
        serial_number=os.getenv("PRINTER_SERIAL") or None,
        check_code=os.getenv("PRINTER_CHECK_CODE") or None,
        printer_port=int(os.getenv("PRINTER_PORT", "8898")),
        slicer_exe=slicer_exe,
        system_profiles=_system_profiles(slicer_exe),
        leveling_before_print=_flag("LEVELING_BEFORE_PRINT", False),
        parts_dir=ROOT / "piezas",
        output_dir=ROOT / "salida",
        profiles_dir=ROOT / "perfiles",
    )


CONFIG = load()
