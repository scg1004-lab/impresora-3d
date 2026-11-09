r"""Comprueba que el laminador aparece aunque lo instalen en otro sitio.

    .venv\Scripts\python.exe pruebas\test_encontrar_orca.py

Monta instalaciones de mentira en carpetas temporales y mira si la app las
encuentra. Es una prueba que no existía y debería: la app decía «no tienes
Orca» en un ordenador que lo tenía instalado, porque la búsqueda era una
lista de rutas fijas y Flashforge había renombrado el programa de
«Orca-Flashforge» a «Flash Studio Desktop».

La seña que no depende del nombre es la carpeta `resources/profiles` que el
laminador lleva al lado. Por eso el caso que más importa aquí es el del
programa con un nombre que nadie ha visto todavía.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ad5x.config as cfg  # noqa: E402

fallos: list[str] = []


def instalacion(base: Path, carpeta: str, exe: str, *, perfiles: bool = True,
                acompanantes: tuple[str, ...] = (),
                fabricante: str = "Flashforge") -> Path:
    """Una instalación falsa: el programa, sus perfiles y algún estorbo."""
    sitio = base / "Program Files" / carpeta
    sitio.mkdir(parents=True, exist_ok=True)
    # El programa pesa; los acompañantes no. Así se distinguen cuando hay
    # que elegir por tamaño.
    (sitio / exe).write_bytes(b"x" * 5_000_000)
    for otro in acompanantes:
        (sitio / otro).write_bytes(b"x" * 1000)
    if perfiles:
        (sitio / "resources" / "profiles" / fabricante).mkdir(parents=True)
    return sitio / exe


def buscar(base: Path) -> Path | None:
    """Busca con PROGRAMFILES apuntando a la instalación de mentira.

    El registro se anula: aquí se prueba la búsqueda en disco, y si no, en
    este ordenador ganaría siempre la instalación de verdad.
    """
    entorno = {
        "PROGRAMFILES": str(base / "Program Files"),
        "PROGRAMFILES(X86)": str(base / "Program Files (x86)"),
        "LOCALAPPDATA": str(base / "AppData"),
        "APPDATA": str(base / "AppData"),
    }
    with patch.dict(os.environ, entorno), \
         patch.dict(os.environ, {"SLICER_EXE": ""}), \
         patch.object(cfg, "_del_registro", return_value=[]):
        return cfg._find_slicer()


CASOS = [
    ("el de siempre",
     "Flashforge/Orca-Flashforge", "orca-flashforge.exe", True),
    ("renombrado a Flash Studio",
     "Flashforge/Flash Studio Desktop", "FlashStudio.exe", True),
    ("un nombre que nadie ha visto aún",
     "Flashforge/Laminador 2030", "ff-slice-2030.exe", True),
    ("OrcaSlicer de la comunidad",
     "OrcaSlicer", "orca-slicer.exe", True),
    ("sin perfiles al lado: eso no es el laminador",
     "Flashforge/Otra Cosa", "cualquiera.exe", False),
]


def con_perfiles_de(exe: Path, cuando: str,
                    fabricante: str = "Flashforge") -> None:
    """Le pone a una instalación perfiles de la AD5X con una fecha dada.

    `cuando` es «2025-09-24». La fecha va al fichero del perfil y a la
    carpeta, que es lo que mira la app para saber cuál es el más nuevo.
    """
    import datetime
    ano, mes, dia = (int(p) for p in cuando.split("-"))
    sello = datetime.datetime(ano, mes, dia).timestamp()

    perfiles = exe.parent / "resources" / "profiles" / fabricante
    maquina = perfiles / "machine"
    maquina.mkdir(parents=True, exist_ok=True)
    ficha = maquina / "Flashforge AD5X 0.4 nozzle.json"
    ficha.write_text('{"printer_model": "Flashforge AD5X"}', encoding="utf-8")
    # Los ficheros primero y las carpetas después: escribir dentro de una
    # carpeta le cambia la fecha.
    os.utime(ficha, (sello, sello))
    os.utime(maquina, (sello, sello))
    os.utime(perfiles, (sello, sello))


def caso_instalar_con_la_app_abierta() -> None:
    """Instalar el laminador con el Taller abierto tiene que bastar.

    El caso de verdad: la app dice «no encuentro Orca», uno va y lo
    instala… y la app sigue diciendo lo mismo, porque solo miró al
    arrancar. Pasa igual al actualizar, que cambia el nombre del
    ejecutable y deja la ruta vieja apuntando a nada.
    """
    import dataclasses

    base = Path(tempfile.mkdtemp(prefix="orca-enmarcha-"))
    try:
        # La app arrancó cuando ahí no había nada.
        config = dataclasses.replace(
            cfg.CONFIG, slicer_exe=base / "Program Files" / "ni-esta" / "x.exe",
            system_profiles=None)

        entorno = {
            "PROGRAMFILES": str(base / "Program Files"),
            "PROGRAMFILES(X86)": str(base / "Program Files (x86)"),
            "LOCALAPPDATA": str(base / "AppData"),
            "APPDATA": str(base / "AppData"),
        }
        with patch.dict(os.environ, entorno), \
             patch.dict(os.environ, {"SLICER_EXE": ""}), \
             patch.object(cfg, "_del_registro", return_value=[]):

            cfg._ULTIMA_BUSQUEDA = 0.0
            if config.slicer_available:
                fallos.append("app abierta: dice que hay laminador y no hay")
                print("   FALLO  app abierta: lo da por bueno sin haberlo")

            # Ahora se instala, con la app ya en marcha.
            exe = instalacion(base, "Flashforge/Flash Studio Desktop",
                              "FlashStudio.exe")
            con_perfiles_de(exe, "2026-10-27")

            cfg._ULTIMA_BUSQUEDA = 0.0
            if config.slicer_available and config.system_profiles is not None:
                print("   OK   app abierta: lo encuentra sin reiniciar "
                      f"-> {config.slicer_exe.name}")
            else:
                fallos.append("app abierta: no lo ve hasta reiniciar")
                print("   FALLO  app abierta: no lo ve hasta reiniciar")
    finally:
        cfg._ULTIMA_BUSQUEDA = 0.0
        shutil.rmtree(base, ignore_errors=True)


def caso_carpeta_de_perfiles() -> None:
    """Los perfiles tienen que aparecer aunque su carpeta se llame de otra forma.

    Todo el laminado cuelga de encontrar
    `resources/profiles/<fabricante>/machine/…AD5X….json`. Hasta hoy ese
    «fabricante» es «Flashforge», pero el programa ya se renombró una vez;
    si la carpeta cambia y la app la busca por su nombre, el botón
    «Laminar» deja de funcionar de golpe y sin explicación.
    """
    for titulo, fabricante, debe_salir in (
        ("la de siempre", "Flashforge", True),
        ("con otro nombre", "FlashStudio", True),
        ("sin perfiles de la AD5X dentro", None, False),
    ):
        base = Path(tempfile.mkdtemp(prefix="orca-perf-"))
        try:
            exe = instalacion(
                base, "Flashforge/Flash Studio Desktop", "FlashStudio.exe",
                fabricante=fabricante or "Otra Marca",
            )
            if fabricante:
                con_perfiles_de(exe, "2026-10-27", fabricante)

            hallado = cfg._perfiles_de(exe)
            bien = (hallado is not None
                    and any((hallado / "machine").glob("*AD5X*.json"))
                    ) if debe_salir else not (
                        hallado and any((hallado / "machine").glob("*AD5X*.json")))
            if bien:
                print(f"   OK   perfiles, {titulo}"
                      + (f" -> {hallado.name}" if hallado else ""))
            else:
                fallos.append(f"perfiles, {titulo}: salió {hallado}")
                print(f"   FALLO  perfiles, {titulo}: {hallado}")
        finally:
            shutil.rmtree(base, ignore_errors=True)


def caso_dos_instalados() -> None:
    """Con los dos instalados, tiene que ganar el de perfiles más nuevos.

    Es lo que pasa de verdad cuando alguien actualiza: Flashforge renombró
    el programa, así que el nuevo se instala al lado del viejo en vez de
    encima. Si gana el viejo, se sigue laminando con perfiles de hace un
    año y la impresora, con su firmware nuevo, imprime mal.
    """
    for titulo, orden in (
        ("el viejo primero", ("viejo", "nuevo")),
        ("el nuevo primero", ("nuevo", "viejo")),
    ):
        base = Path(tempfile.mkdtemp(prefix="orca-dos-"))
        try:
            instalados = {
                "viejo": (lambda: con_perfiles_de(
                    instalacion(base, "Flashforge/Orca-Flashforge",
                                "orca-flashforge.exe"), "2025-09-24")),
                "nuevo": (lambda: con_perfiles_de(
                    instalacion(base, "Flashforge/Flash Studio Desktop",
                                "FlashStudio.exe"), "2026-10-27")),
            }
            # El orden de creación cambia el orden en que aparecen al
            # recorrer la carpeta del fabricante: los dos casos tienen que
            # dar lo mismo.
            for cual in orden:
                instalados[cual]()

            hallado = buscar(base)
            # Sin mirar mayúsculas: el nombre sale de la lista de nombres
            # conocidos, no de cómo esté escrito en el disco.
            esperado = "flashstudio.exe"
            if hallado is None or hallado.name.lower() != esperado:
                fallos.append(f"dos instalados, {titulo}: esperaba "
                              f"{esperado}, salió {hallado}")
                print(f"   FALLO  dos instalados, {titulo}: {hallado}")
            else:
                print(f"   OK   dos instalados, {titulo} -> {hallado.parent.name}")
        finally:
            shutil.rmtree(base, ignore_errors=True)


def main() -> int:
    for titulo, carpeta, exe, debe_salir in CASOS:
        base = Path(tempfile.mkdtemp(prefix="orca-falso-"))
        try:
            esperado = instalacion(
                base, carpeta, exe,
                perfiles=debe_salir,
                acompanantes=("unins000.exe", "crashpad_handler.exe"),
            )
            hallado = buscar(base)
            if debe_salir and hallado != esperado:
                fallos.append(f"{titulo}: esperaba {esperado.name}, salió {hallado}")
                print(f"   FALLO  {titulo}")
            elif not debe_salir and hallado is not None:
                fallos.append(f"{titulo}: no debía encontrar nada y encontró {hallado}")
                print(f"   FALLO  {titulo}")
            else:
                print(f"   OK   {titulo}"
                      + (f" -> {hallado.name}" if hallado else " (no lo da por bueno)"))
        finally:
            shutil.rmtree(base, ignore_errors=True)

    caso_instalar_con_la_app_abierta()
    caso_carpeta_de_perfiles()
    caso_dos_instalados()

    # Y en este ordenador, el de verdad tiene que seguir apareciendo.
    print("\nEn este ordenador:")
    propio = cfg._find_slicer()
    if propio and propio.is_file():
        print(f"   OK   {propio}")
    else:
        print("   (no hay laminador instalado aquí, nada que comprobar)")

    print("\n" + ("TODO CORRECTO" if not fallos else f"{len(fallos)} FALLOS"))
    for f in fallos:
        print("  ·", f)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
