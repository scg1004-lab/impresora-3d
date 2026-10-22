"""Configuration, read once from the environment / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

# Windows esconde las extensiones conocidas, asi que un fichero creado con el
# Bloc de notas y llamado ".env" acaba siendo ".env.txt" sin que se vea. Pasa
# siempre, y el sintoma es el peor posible: la app dice que falta configurar
# la impresora mientras el fichero esta ahi delante.
NOMBRES_ENV = (".env", ".env.txt", "env.txt", "env")

def _buscar_env() -> Path:
    for nombre in NOMBRES_ENV:
        candidato = ROOT / nombre
        if candidato.is_file():
            return candidato
    return ROOT / ".env"

ENV_PATH = _buscar_env()
load_dotenv(ENV_PATH)


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


# Cómo se llama el ejecutable, según quién lo haya empaquetado y en qué año.
NOMBRES_ORCA = (
    "orca-flashforge.exe",
    "orca-slicer.exe",
    "orca-slicer-console.exe",
    "OrcaSlicer.exe",
    "orca_flashforge.exe",
    "flash-studio.exe",
    "flashstudio.exe",
    "Flash Studio.exe",
    "FlashStudioDesktop.exe",
)

# Palabras que delatan al programa en el nombre de una carpeta o en la lista
# de programas instalados. Flashforge le cambió el nombre de «Orca-Flashforge»
# a «Flash Studio Desktop», así que buscar solo «orca» deja de encontrarlo en
# cuanto alguien actualiza.
PISTAS = ("orca", "flashforge", "flash studio", "flashstudio", "flash-studio")

# Ejecutables que acompañan a cualquier instalación y no son el programa.
ACOMPANANTES = (
    "unins", "setup", "install", "update", "crashpad", "vcredist",
    "vc_redist", "7z", "python", "helper", "report", "launcher",
)

# Dónde se ha mirado, para poder contarlo cuando no aparece.
BUSCADO: list[str] = []


def _del_registro() -> list[Path]:
    """Lo que Windows sabe de dónde se instaló. Es la fuente fiable.

    Las rutas fijas son una apuesta: valen en el ordenador donde se probó y
    fallan en el siguiente. El instalador, en cambio, deja escrito dónde
    puso las cosas, y eso vale en cualquiera.
    """
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    encontrados: list[Path] = []
    ramas = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for raiz, camino in ramas:
        try:
            with winreg.OpenKey(raiz, camino) as clave:
                total = winreg.QueryInfoKey(clave)[0]
                for indice in range(total):
                    try:
                        nombre = winreg.EnumKey(clave, indice)
                        with winreg.OpenKey(clave, nombre) as programa:
                            titulo = str(
                                winreg.QueryValueEx(programa, "DisplayName")[0])
                            if not any(p in titulo.lower() for p in PISTAS):
                                continue
                            try:
                                sitio = winreg.QueryValueEx(
                                    programa, "InstallLocation")[0]
                            except OSError:
                                sitio = ""
                            if sitio:
                                encontrados.append(Path(sitio))
                            try:
                                icono = str(winreg.QueryValueEx(
                                    programa, "DisplayIcon")[0]).split(",")[0]
                            except OSError:
                                icono = ""
                            if icono.lower().endswith(".exe"):
                                encontrados.append(Path(icono).parent)
                    except OSError:
                        continue
        except OSError:
            continue

    # Y el registro de rutas de aplicaciones, por si el instalador lo puso.
    for nombre in NOMBRES_ORCA:
        for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                camino = (r"SOFTWARE\Microsoft\Windows\CurrentVersion"
                          "\\App Paths\\" + nombre)
                with winreg.OpenKey(raiz, camino) as clave:
                    valor = str(winreg.QueryValueEx(clave, "")[0]).strip('"')
                    if valor:
                        encontrados.append(Path(valor).parent)
            except OSError:
                continue
    return encontrados


def _exe_dentro(carpeta: Path) -> Path | None:
    """El ejecutable del laminador dentro de una carpeta de instalación.

    Primero por nombre, que es lo barato. Y si no, por una seña que no
    depende de cómo decidan llamarlo: al lado lleva siempre su carpeta
    `resources/profiles`. Dentro de una carpeta así, el programa es el
    ejecutable más grande que no sea un acompañante (desinstalador,
    actualizador, el informe de fallos…).

    Esto no es rebuscamiento: «Orca-Flashforge» pasó a llamarse «Flash
    Studio Desktop» y una lista de nombres se quedó corta de un día para
    otro, en un ordenador que no es el mío.
    """
    for nombre in NOMBRES_ORCA:
        candidato = carpeta / nombre
        if candidato.is_file():
            return candidato

    if not (carpeta / "resources" / "profiles").is_dir():
        return None
    try:
        sueltos = [
            exe for exe in carpeta.glob("*.exe")
            if not any(a in exe.name.lower() for a in ACOMPANANTES)
        ]
    except OSError:
        return None
    if not sueltos:
        return None
    return max(sueltos, key=lambda exe: exe.stat().st_size)


def _del_fabricante() -> list[Path]:
    """Las carpetas que cuelgan de la del fabricante.

    `C:\\Program Files\\Flashforge\\<lo que sea>`: así da igual cómo
    bauticen la próxima versión, mientras la dejen donde siempre.
    """
    carpetas: list[Path] = []
    for raiz in (
        Path(os.getenv("PROGRAMFILES", r"C:\Program Files")),
        Path(os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)")),
        Path(os.getenv("LOCALAPPDATA", "")) / "Programs",
    ):
        for marca in ("Flashforge", "FlashForge", "Orca"):
            vendedor = raiz / marca
            if not vendedor.is_dir():
                continue
            carpetas.append(vendedor)
            try:
                carpetas.extend(h for h in vendedor.iterdir() if h.is_dir())
            except OSError:
                continue
    return carpetas


def _rebuscar() -> Path | None:
    """Último recurso: mirar dentro de las carpetas de programas.

    Acotado a tres niveles. Barrer el disco entero tardaría minutos y esto
    corre en cada arranque.
    """
    raices = [
        Path(os.getenv("PROGRAMFILES", r"C:\Program Files")),
        Path(os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)")),
        Path(os.getenv("LOCALAPPDATA", "")) / "Programs",
        Path(os.getenv("APPDATA", "")) / "Local" / "Programs",
        Path.home() / "Desktop",
    ]
    for raiz in raices:
        if not raiz.is_dir():
            continue
        BUSCADO.append(str(raiz))
        for hondura in ("*", "*/*", "*/*/*"):
            try:
                for carpeta in raiz.glob(hondura):
                    nombre = carpeta.name.lower()
                    if not carpeta.is_dir() or not any(p in nombre for p in PISTAS):
                        continue
                    exe = _exe_dentro(carpeta)
                    if exe:
                        return exe
            except OSError:
                continue
    return None


def _find_slicer() -> Path | None:
    """Localiza el ejecutable de Orca, mirando donde haga falta."""
    BUSCADO.clear()

    override = os.getenv("SLICER_EXE")
    if override:
        BUSCADO.append(f"SLICER_EXE del .env: {override}")
        candidato = Path(override)
        return candidato if candidato.is_file() else None

    # 1) Lo que dice Windows que se instaló. Es lo que funciona en un
    #    ordenador que no es el tuyo.
    for carpeta in _del_registro():
        BUSCADO.append(str(carpeta))
        exe = _exe_dentro(carpeta)
        if exe:
            return exe

    # 2) Lo que cuelgue de la carpeta del fabricante, se llame como se llame.
    for carpeta in _del_fabricante():
        BUSCADO.append(str(carpeta))
        exe = _exe_dentro(carpeta)
        if exe:
            return exe

    # 3) Los sitios de siempre, que son los más rápidos de mirar.
    program_files = Path(os.getenv("PROGRAMFILES", r"C:\Program Files"))
    program_files_x86 = Path(os.getenv("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    local_programs = Path(os.getenv("LOCALAPPDATA", "")) / "Programs"
    for carpeta in (
        program_files / "Flashforge" / "Orca-Flashforge",
        local_programs / "Flashforge" / "Orca-Flashforge",
        program_files / "Orca-Flashforge",
        local_programs / "Orca-Flashforge",
        program_files / "OrcaSlicer",
        program_files_x86 / "OrcaSlicer",
        local_programs / "OrcaSlicer",
    ):
        BUSCADO.append(str(carpeta))
        exe = _exe_dentro(carpeta)
        if exe:
            return exe

    # 4) Y si sigue sin aparecer, rebuscar en las carpetas de programas.
    return _rebuscar()


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
