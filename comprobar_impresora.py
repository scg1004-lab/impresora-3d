"""Diagnose the connection to the printer, step by step.

Run it whenever the app says the printer does not answer:

    .venv\\Scripts\\python.exe comprobar_impresora.py

It checks one thing at a time and stops at the first that fails, saying what
to do about it, instead of giving a single unhelpful "no responde".
"""
from __future__ import annotations

import socket
import subprocess
import sys

from ad5x.config import CONFIG
from ad5x.printer import Printer, PrinterError, discover

OK, FAIL, WARN = "  [OK] ", "  [--] ", "  [!!] "


def step(title: str) -> None:
    print(f"\n{title}")


def reachable(host: str, timeout: int = 2) -> bool:
    flag = "-n" if sys.platform == "win32" else "-c"
    result = subprocess.run(
        ["ping", flag, "2", host],
        capture_output=True,
        text=True,
        timeout=timeout * 6,
    )
    return result.returncode == 0


def port_open(host: str, port: int, timeout: float = 3.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def main() -> int:
    print("Comprobación de la conexión con la AD5X")
    print("=" * 52)

    step("1. Configuración del .env")
    missing = [
        name
        for name, value in (
            ("PRINTER_SERIAL", CONFIG.serial_number),
            ("PRINTER_CHECK_CODE", CONFIG.check_code),
        )
        if not value
    ]
    if missing:
        print(FAIL + "faltan: " + ", ".join(missing))
        print("       Los tres salen en la pantalla de la impresora, en la")
        print("       pantalla de conexión LAN.")
        return 1
    print(OK + f"serie {CONFIG.serial_number}")

    step("2. ¿Dónde está la impresora?")
    host = CONFIG.printer_ip
    if host and port_open(host, CONFIG.printer_port):
        print(OK + f"en la dirección de siempre, {host}")
    else:
        # The .env address is only a hint; discovery is what finds it.
        seen = dict(discover())
        if not seen:
            print(FAIL + "no responde ninguna impresora al descubrimiento")
            if host:
                print(f"       La última conocida era {host}.")
            print("       Comprueba que está encendida, en esta red y con el")
            print("       modo LAN activo en su pantalla.")
            return 1
        nueva = next(iter(seen))
        if host and nueva != host:
            print(WARN + f"ha cambiado de dirección: ahora está en {nueva}")
            print(f"       (el .env dice {host}; la app lo resuelve sola, pero")
            print("        puedes actualizarlo para ahorrarte la búsqueda)")
        else:
            print(OK + f"encontrada en {nueva}")
        host = nueva

    step("2b. ¿Responde al ping?")
    if not reachable(host):
        print(FAIL + f"{host} no responde al ping")
        print("       O está apagada, o la IP ha cambiado. Míralas en la")
        print("       pantalla: Ajustes > Red.")
        return 1
    print(OK + "responde al ping")

    step(f"3. ¿Está abierto el puerto {CONFIG.printer_port} (API local)?")
    if not port_open(host, CONFIG.printer_port):
        print(FAIL + f"el puerto {CONFIG.printer_port} está cerrado")

        # UDP discovery answers even with the HTTP API closed, so it separates
        # "LAN mode is off" from "that IP is not the printer".
        seen = dict(discover())
        if host in seen:
            print(f"       Pero la impresora SÍ está ahí: responde «{seen[host]}»")
            print("       al descubrimiento UDP. Entonces es el MODO LAN, que")
            print("       está desactivado. Actívalo en la pantalla.")
            print("       Ojo: con el modo LAN activo, la app Flash Maker deja")
            print("       de controlarla por internet. Es uno u otro.")
        elif seen:
            print("       Y en esa IP no hay ninguna impresora. Sí responden:")
            for ip, model in seen.items():
                print(f"         {ip}  ({model})")
            print("       Corrige PRINTER_IP en el .env.")
        else:
            print("       Ninguna impresora responde al descubrimiento tampoco.")
            print("       Revisa que esté encendida y en esta misma red.")
        return 1
    print(OK + "puerto abierto")

    printer = Printer(CONFIG)

    step("4. ¿Son válidos el número de serie y el código?")
    try:
        printer.check()
    except PrinterError as exc:
        print(FAIL + str(exc))
        print("       Los códigos de verificación caducan: vuelve a leerlo en")
        print("       la pantalla y actualiza PRINTER_CHECK_CODE en el .env.")
        return 1
    print(OK + "credenciales aceptadas")

    step("5. Estado de la impresora")
    try:
        status = printer.status()
    except PrinterError as exc:
        print(WARN + f"responde pero no da el detalle: {exc}")
        return 0

    print(OK + f"{status.machine} · {status.state}")
    if status.nozzle_temp is not None:
        print(f"       boquilla {status.nozzle_temp:.0f} °C", end="")
        if status.bed_temp is not None:
            print(f" · cama {status.bed_temp:.0f} °C", end="")
        print()
    if status.job:
        print(f"       trabajo en curso: {status.job}")

    print("\nTodo correcto: la app puede enviarle trabajos.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
