r"""Comprueba el borrado de lo generado en este ordenador.

    .venv\Scripts\python.exe pruebas\test_limpieza.py

Borrar ficheros es de lo poco que esta app hace sin vuelta atrás, así que
lo que se prueba aquí no es tanto que borre como que **no borre de más**:
que no se salga de la carpeta de salida, que respete lo que está en la cola
y que un plazo que no alcanza a nadie no se lleve nada por delante.

Trabaja sobre una carpeta de usar y tirar, nunca sobre la de verdad.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fastapi import HTTPException  # noqa: E402

fallos: list[str] = []


def mal(mensaje: str) -> None:
    fallos.append(mensaje)
    print(f"   FALLO  {mensaje}")


def bien(mensaje: str) -> None:
    print(f"   OK   {mensaje}")


def montar(taller: Path):
    """La app apuntando a una carpeta de salida de mentira."""
    salida = taller / "salida"
    salida.mkdir(parents=True)

    import ad5x.web as web
    from ad5x.cola import Cola

    # La configuración es un dataclass congelado: se cambia la carpeta con
    # object.__setattr__, que es lo que hay cuando no se puede reconstruir
    # media app solo para una prueba.
    object.__setattr__(web.CONFIG, "output_dir", salida)

    # Y la cola, a otra de mentira. La de verdad se creó al importar la app y
    # apunta al salida/ real: si esta prueba la tocara, se llevaría por
    # delante los trabajos que alguien tuviera esperando.
    web.cola = Cola(path=salida / ".cola.json")
    return web, salida


def fichero(salida: Path, nombre: str, dias: float = 0.0) -> Path:
    ruta = salida / nombre
    ruta.write_text("; de mentira\n", encoding="utf-8")
    if dias:
        cuando = time.time() - dias * 86400
        os.utime(ruta, (cuando, cuando))
    return ruta


def main() -> int:
    taller = Path(tempfile.mkdtemp(prefix="limpieza-"))
    try:
        web, salida = montar(taller)

        def listar():
            return web.api_salida()

        def borrar(nombre):
            """Devuelve (ok, detalle), sin levantar la excepción de FastAPI."""
            try:
                web.api_salida_borrar(nombre)
                return True, ""
            except HTTPException as exc:
                return False, str(exc.detail)

        def limpiar(dias):
            return web.api_salida_limpiar(web.LimpiarRequest(dias=dias))

        fichero(salida, "nuevo.gcode", dias=0)
        fichero(salida, "viejo.gcode", dias=40)
        fichero(salida, "medio.stl", dias=10)
        (salida / ".oculto.json").write_text("{}", encoding="utf-8")

        print("1. Listado")
        datos = listar()
        nombres = {f["nombre"] for f in datos["ficheros"]}
        if nombres == {"nuevo.gcode", "viejo.gcode", "medio.stl"}:
            bien(f"{len(nombres)} ficheros, y los ocultos no salen")
        else:
            mal(f"lista rara: {nombres}")

        print("2. Borrar uno")
        hecho, detalle = borrar("medio.stl")
        if hecho and not (salida / "medio.stl").exists():
            bien("borrado")
        else:
            mal(f"no lo ha borrado: {detalle}")

        print("3. No se puede salir de la carpeta")
        antes = (RAIZ / ".env").is_file()
        for intento in ("../../.env", "../.env", "/etc/passwd", "C:/Windows/win.ini",
                        r"..\..\.env"):
            hecho, _ = borrar(intento)
            if hecho:
                mal(f"ha aceptado «{intento}»")
        if antes and not (RAIZ / ".env").is_file():
            mal("¡se ha cargado el .env de verdad!")
        else:
            bien("las rutas de fuera se rechazan")

        print("4. Lo que está en la cola no se toca")
        encolado = fichero(salida, "encolado.gcode", dias=99)
        web.cola.add("encolado.gcode", None, "prueba")
        try:
            hecho, _ = borrar("encolado.gcode")
            if hecho or not encolado.exists():
                mal("ha borrado un fichero que estaba en la cola")
            else:
                bien("se niega mientras esté en la cola")

            print("5. Un plazo que no alcanza a nadie no borra nada")
            quedan = len(listar()["ficheros"])
            r = limpiar(99999)
            ahora = len(listar()["ficheros"])
            if r["borrados"] == 0 and ahora == quedan:
                bien("no ha tocado nada")
            else:
                mal(f"ha borrado {r['borrados']} sin deberlo")

            print("6. Limpiar lo de más de una semana")
            r = limpiar(7)
            vivos = {f["nombre"] for f in listar()["ficheros"]}
            if "viejo.gcode" not in vivos and "nuevo.gcode" in vivos:
                bien(f"{r['borrados']} borrados, {r['en_cola']} intocables por la cola")
            else:
                mal(f"ha limpiado mal: quedan {vivos}")
            if "encolado.gcode" not in vivos:
                mal("se ha llevado el de la cola por delante")
        finally:
            # La cola de esta prueba vive en la carpeta temporal; se va con ella.
            pass

        print("\n" + ("TODO CORRECTO" if not fallos else f"{len(fallos)} FALLOS"))
        return 1 if fallos else 0
    finally:
        shutil.rmtree(taller, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
