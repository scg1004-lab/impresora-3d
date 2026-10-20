"""Arranca el taller y abre el navegador cuando de verdad está listo.

Importar CadQuery lleva sus buenos segundos la primera vez, y abrir el
navegador antes de eso da un «127.0.0.1 rechazó la conexión» que parece una
avería y no lo es. Así que se espera a que el puerto conteste.

Y si ya había una copia corriendo, el segundo doble clic no revienta con un
error de socket: abre el navegador en la que ya está y se quita de en medio.
"""
from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

try:
    from ad5x.actualizar import comprobar as comprobar_actualizacion
except Exception:  # noqa: BLE001 - sin actualizador se arranca igual
    def comprobar_actualizacion(raiz: Path) -> str | None:  # type: ignore[misc]
        return None

HOST = "127.0.0.1"
PORT = 8099
ESPERA_MAXIMA = 180  # segundos; en un portátil lento el primer arranque tarda


def _escuchando() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((HOST, PORT)) == 0


def _ya_es_el_taller() -> bool:
    """Si hay algo en el puerto, ¿es nuestra propia app o un desconocido?"""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{PORT}/", timeout=5) as respuesta:
            return "Taller AD5X" in respuesta.read(8000).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        return False


def _abrir_cuando_este_listo() -> None:
    limite = time.monotonic() + ESPERA_MAXIMA
    while time.monotonic() < limite:
        if _escuchando():
            webbrowser.open(f"http://{HOST}:{PORT}")
            return
        time.sleep(0.5)

    print(
        "\n  El programa tarda más de lo normal en arrancar.\n"
        f"  Prueba a abrir tú el navegador en: http://{HOST}:{PORT}\n"
    )


if __name__ == "__main__":
    print("\n  Taller AD5X")
    print("  -----------")

    if _escuchando():
        if _ya_es_el_taller():
            print("  Ya estaba abierto. Te lo saco en el navegador.\n")
            webbrowser.open(f"http://{HOST}:{PORT}")
            raise SystemExit(0)
        print(
            f"  El puerto {PORT} lo está usando otro programa, no este.\n"
            "  Cierra lo que haya en ese puerto y vuelve a intentarlo.\n"
        )
        raise SystemExit(1)

    # Antes de levantar nada: en el paquete portátil, ponerse al día.
    # Solo ahí; en el equipo donde se programa no se toca el código.
    novedad = comprobar_actualizacion(Path(__file__).resolve().parent)
    if novedad:
        print(f"  {novedad}")
        print()

    print("  Arrancando… la primera vez tarda unos segundos.")
    print("  El navegador se abrirá solo cuando esté listo.\n")

    threading.Thread(target=_abrir_cuando_este_listo, daemon=True).start()
    uvicorn.run("ad5x.web:app", host=HOST, port=PORT, reload=False, log_level="warning")
