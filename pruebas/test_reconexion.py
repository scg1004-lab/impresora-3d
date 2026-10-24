"""Comprueba que la app reencuentra la impresora si DHCP le cambia la IP.

    .venv\\Scripts\\python.exe pruebas\\test_reconexion.py

Levanta una impresora de mentira en localhost y le dice a la app que la busque
en una dirección equivocada. No necesita la impresora real, que es justo el
caso en el que hace falta probar esto.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ad5x.printer as mod  # noqa: E402
from ad5x.config import Config  # noqa: E402

SERIAL = "SNTEST123"
CODE = "abcd1234"
PORT = 18898

# Carpeta de usar y tirar. La app recuerda la ultima IP en un fichero junto a
# la carpeta de salida, y apuntando a la de verdad esta prueba le dejaba
# escrito al programa de Santi que su impresora vive en 127.0.0.1.
TEMPORAL = Path(tempfile.mkdtemp(prefix="taller-prueba-"))
SALIDA = TEMPORAL / "salida"
SALIDA.mkdir()
MEMORIA = SALIDA.parent / ".ultima-ip"


class FakePrinter(BaseHTTPRequestHandler):
    """Answers like an AD5X, but only to the right serial and code."""

    def do_POST(self) -> None:  # noqa: N802 - the name is http.server's
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or "{}")
        ours = body.get("serialNumber") == SERIAL and body.get("checkCode") == CODE

        payload: dict = (
            {"code": 0, "message": "Success"} if ours else {"code": 5, "message": "bad code"}
        )
        if ours and self.path == "/detail":
            payload["detail"] = {
                "status": "ready",
                "name": "AD5X",
                "printLayer": 3,
                "targetPrintLayer": 10,
                "matlStationInfo": {"slotInfos": []},
            }

        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: object) -> None:
        pass  # quiet


def config(serial: str = SERIAL, ip: str | None = "192.168.1.250") -> Config:
    return Config(
        printer_ip=ip,
        serial_number=serial,
        check_code=CODE,
        printer_port=PORT,
        slicer_exe=None,
        system_profiles=None,
        thingiverse_token=None,
        leveling_before_print=False,
        parts_dir=Path("piezas"),
        output_dir=SALIDA,
        profiles_dir=Path("perfiles"),
    )


def main() -> int:
    server = HTTPServer(("127.0.0.1", PORT), FakePrinter)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    found = [("127.0.0.1", "AD5X")]
    fallos = 0

    try:
        print("1. La IP guardada ya no responde: debe reencontrarla")
        printer = mod.Printer(config())
        with patch.object(mod, "discover", return_value=found):
            status = printer.status()
        if status.state == "ready" and printer.host == "127.0.0.1":
            print(f"   OK   la situó en {printer.host}")
        else:
            fallos += 1
            print(f"   FALLO  host={printer.host} estado={status.state}")

        print("2. La siguiente llamada no debe volver a buscar")
        with patch.object(mod, "discover", side_effect=AssertionError("buscó de más")):
            printer.status()
        print("   OK   fue directa a la dirección aprendida")

        print("3. Otra impresora con distinto serial: debe avisar, no usarla")
        otra = mod.Printer(config(serial="NO-ES-LA-MIA"))
        with patch.object(mod, "discover", return_value=found):
            try:
                otra.status()
                fallos += 1
                print("   FALLO  la dio por buena")
            except mod.PrinterError as exc:
                print(f"   OK   {str(exc)[:70]}…")

        print("4. Sin ninguna impresora en la red: mensaje claro")
        # Sin esto la prueba se engana sola: la impresora de mentira sigue
        # levantada y la direccion aprendida en el caso 1 la encuentra.
        MEMORIA.unlink(missing_ok=True)
        sola = mod.Printer(config())
        with patch.object(mod, "discover", return_value=[]):
            try:
                sola.status()
                fallos += 1
                print("   FALLO  no avisó")
            except mod.PrinterError as exc:
                print(f"   OK   {str(exc)[:70]}…")
    finally:
        server.shutdown()
        shutil.rmtree(TEMPORAL, ignore_errors=True)

    print("\n" + ("TODO CORRECTO" if not fallos else f"{fallos} FALLOS"))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
