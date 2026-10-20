"""Build the portable package that runs without installing Python.

    .venv\\Scripts\\python.exe distribucion\\empaquetar.py <carpeta-del-python-embebido>

It copies the app next to an embedded Python interpreter that already has the
dependencies, and zips the lot. The result is a folder the other machine just
copies and double-clicks.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "distribucion"
PACKAGE = "Taller AD5X"

# What the other machine needs. Deliberately excludes .env (it holds this
# printer's check code) and salida/ (local output).
APP_PARTS = ("ad5x", "piezas", "web", "pruebas")
# Downloaded figures ride along so the other machine has something to print
# the moment it is unzipped.
OPTIONAL_PARTS = ("modelos",)
APP_FILES = (
    "run.py",
    # El lanzador vive en la raiz y vale en los dos sitios: aqui usa .venv y
    # dentro del paquete usa py\. Tener dos copias llevo a arrancar la que
    # no era y ver «no encuentro la carpeta py».
    "Taller AD5X.cmd",
    "requirements.txt",
    ".env.example",
    "README.md",
    "comprobar_impresora.py",
)
DIST_FILES = ("LEEME.txt",)

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".env")


MIN_PACKAGES = ("cadquery", "fastapi", "numpy", "uvicorn")


def build(python_dir: Path, out_dir: Path) -> Path:
    if not (python_dir / "python.exe").is_file():
        raise SystemExit(f"No hay un python.exe en {python_dir}")

    # A half-extracted interpreter still has python.exe, and the package it
    # produces looks fine until the other machine tries to run it.
    site_packages = python_dir / "Lib" / "site-packages"
    missing = [name for name in MIN_PACKAGES if not (site_packages / name).is_dir()]
    if missing:
        raise SystemExit(
            f"Al intérprete de {python_dir} le faltan: {', '.join(missing)}. "
            "El paquete no serviría en el otro equipo; reconstruye el intérprete."
        )

    target = out_dir / PACKAGE
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    print(f"Montando {target}")

    print("  · intérprete y librerías")
    shutil.copytree(python_dir, target / "py", ignore=IGNORE)

    for part in APP_PARTS:
        print(f"  · {part}/")
        shutil.copytree(ROOT / part, target / part, ignore=IGNORE)

    for part in OPTIONAL_PARTS:
        source = ROOT / part
        if source.is_dir() and any(source.iterdir()):
            count = sum(1 for _ in source.iterdir())
            print(f"  · {part}/ ({count} ficheros)")
            shutil.copytree(source, target / part, ignore=IGNORE)

    for name in APP_FILES:
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, target / name)

    for name in DIST_FILES:
        shutil.copy2(DIST / name, target / name)

    # pack.py needs the 3MF template to build a file the printer will open.
    print("  · plantilla-3mf/")
    (target / "distribucion").mkdir(exist_ok=True)
    shutil.copytree(
        DIST / "plantilla-3mf", target / "distribucion" / "plantilla-3mf", ignore=IGNORE
    )

    # Folders the app writes into; empty, but they must exist.
    for name in ("salida", "perfiles"):
        (target / name).mkdir(exist_ok=True)

    _stamp_version(target)
    return target


def _stamp_version(target: Path) -> None:
    """Record which commit this package carries, for the self-updater.

    Only when the tree is clean: with uncommitted changes the package and the
    published code differ, and a stamp would tell the other machine it is up
    to date when it is not. No stamp just means it updates on first run.
    """
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT,
            capture_output=True, text=True, timeout=30, check=False)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return
    if dirty.returncode or head.returncode or dirty.stdout.strip():
        print("  · sin marca de versión (hay cambios sin subir)")
        return
    (target / ".version").write_text(head.stdout.strip(), encoding="utf-8")
    print(f"  · versión {head.stdout.strip()[:7]}")


def zip_up(folder: Path) -> Path:
    archive = folder.parent / f"{folder.name}.zip"
    if archive.exists():
        archive.unlink()

    files = [p for p in folder.rglob("*") if p.is_file()]
    print(f"Comprimiendo {len(files):,} ficheros…")

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in files:
            # Forward slashes, so the zip is readable anywhere.
            inner = "/".join((folder.name, *path.relative_to(folder).parts))
            zf.write(path, inner)

    return archive


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)

    python_dir = Path(sys.argv[1]).resolve()
    out_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else DIST / "_build"
    out_dir.mkdir(parents=True, exist_ok=True)

    folder = build(python_dir, out_dir)
    size = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
    print(f"Carpeta lista: {size / 1024 / 1024:,.0f} MB")

    # The real thing is around 1.2 GB; anything far below means a bad copy.
    if size < 500 * 1024 * 1024:
        raise SystemExit(
            f"Solo {size / 1024 / 1024:,.0f} MB: la copia está incompleta. "
            "No se genera el ZIP para no dar por bueno un paquete roto."
        )

    archive = zip_up(folder)
    print(f"\nZIP: {archive}")
    print(f"     {archive.stat().st_size / 1024 / 1024:,.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
