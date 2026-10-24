"""Buscar modelos en Thingiverse y traérselos a la carpeta de salida.

La API es oficial y gratuita, pero pide un token: se saca registrando una
aplicación en thingiverse.com/apps/create y se guarda en el `.env` como
`THINGIVERSE_TOKEN`. Sin él, la app funciona igual y esta parte no aparece.

Lo que llega de ahí es **geometría de otra gente**, y se trata como tal:

* Baja a `salida/`, nunca a `piezas/`. Lo de `piezas/` es código que se
  ejecuta; lo de `salida/` son triángulos que solo mira el laminador.
* El nombre del fichero lo decidimos nosotros a partir del título, no se
  usa el que venga en la respuesta: un nombre con barras o con `..` escribe
  donde no debe.
* Hay tope de tamaño. Un modelo de 300 MB no es un modelo, es un problema.

Los modelos tienen licencia de su autor —casi siempre Creative Commons con
alguna cláusula de no comercial—. Para imprimir en casa no hay nada que
mirar; para cualquier otra cosa, sí.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .config import CONFIG

API = "https://api.thingiverse.com"
ESPERA = 20          # segundos para una búsqueda
ESPERA_DESCARGA = 180
TOPE = 200 * 1024 * 1024   # 200 MB por fichero
POR_PAGINA = 24

# Lo que el laminador sabe abrir. El resto (imágenes, pdf, gcode de otra
# máquina) no se ofrece.
UTILES = (".stl", ".3mf", ".obj", ".step", ".stp")

# De dónde se aceptan imágenes. Sin esta lista, la ruta que sirve las
# miniaturas sería un proxy abierto: cualquiera que abriese la app podría
# usarla para pedir lo que quisiera desde este ordenador.
CDN = ("cdn.thingiverse.com", "thingiverse-production-new.s3.amazonaws.com")
TOPE_IMAGEN = 8 * 1024 * 1024


class ModelosError(RuntimeError):
    pass


@dataclass(frozen=True)
class Modelo:
    id: int
    nombre: str
    autor: str
    miniatura: str
    enlace: str
    likes: int


def hay_token() -> bool:
    return bool(CONFIG.thingiverse_token or os.getenv("THINGIVERSE_TOKEN"))


def _cabeceras() -> dict[str, str]:
    # Por la configuración, que es quien lee el .env. Mirar solo el entorno
    # hacía que el token dependiera de quién importara antes qué.
    token = CONFIG.thingiverse_token or os.getenv("THINGIVERSE_TOKEN")
    if not token:
        raise ModelosError(
            "Falta el token de Thingiverse. Se saca registrando una aplicación "
            "en thingiverse.com/apps/create y se guarda en el .env como "
            "THINGIVERSE_TOKEN."
        )
    return {"Authorization": f"Bearer {token}", "User-Agent": "taller-ad5x"}


def _pedir(ruta: str, espera: int = ESPERA, **parametros: Any) -> Any:
    try:
        respuesta = requests.get(
            f"{API}{ruta}", headers=_cabeceras(), params=parametros, timeout=espera
        )
    except requests.RequestException as exc:
        raise ModelosError(f"No se ha podido hablar con Thingiverse: {exc}") from exc

    if respuesta.status_code == 401:
        raise ModelosError("Thingiverse rechaza el token: ¿está bien copiado?")
    if respuesta.status_code == 429:
        raise ModelosError("Demasiadas búsquedas seguidas; espera un minuto.")
    if not respuesta.ok:
        raise ModelosError(f"Thingiverse ha contestado {respuesta.status_code}")
    try:
        return respuesta.json()
    except ValueError as exc:
        raise ModelosError("Thingiverse ha contestado algo que no es JSON") from exc


def buscar(texto: str, pagina: int = 1) -> list[Modelo]:
    """Los modelos que coinciden con lo que se busca."""
    texto = (texto or "").strip()
    if not texto:
        raise ModelosError("Escribe algo que buscar")

    datos = _pedir(
        f"/search/{requests.utils.quote(texto, safe='')}",
        type="things", page=max(pagina, 1), per_page=POR_PAGINA,
    )
    crudos = datos.get("hits") if isinstance(datos, dict) else datos
    return [
        Modelo(
            id=int(c.get("id", 0)),
            nombre=str(c.get("name") or "sin nombre"),
            autor=str((c.get("creator") or {}).get("name") or "—"),
            miniatura=str(c.get("thumbnail") or c.get("preview_image") or ""),
            enlace=str(c.get("public_url") or f"https://www.thingiverse.com/thing:{c.get('id')}"),
            likes=int(c.get("like_count") or 0),
        )
        for c in (crudos or [])
        if c.get("id")
    ]


def ficheros(modelo_id: int) -> list[dict[str, Any]]:
    """Los ficheros imprimibles de un modelo, del más pequeño al más grande."""
    datos = _pedir(f"/things/{int(modelo_id)}/files")
    utiles = [
        {
            "id": f.get("id"),
            "nombre": str(f.get("name") or ""),
            "kb": int(f.get("size") or 0) // 1024,
            "url": str(f.get("public_url") or ""),
            "descarga": str(f.get("download_url") or ""),
        }
        for f in (datos or [])
        if str(f.get("name") or "").lower().endswith(UTILES)
    ]
    return sorted(utiles, key=lambda f: f["kb"])


def miniatura(url: str) -> tuple[bytes, str]:
    """La imagen de un modelo, servida por nosotros.

    El CDN de Thingiverse manda `Cross-Origin-Resource-Policy: same-origin`,
    así que el navegador se niega a pintarla dentro de nuestra página. Se
    trae aquí y se reenvía. Solo de los dominios de la lista: una ruta que
    descargue cualquier dirección que le pasen es un proxy abierto.
    """
    from urllib.parse import urlsplit

    trozos = urlsplit(url or "")
    if trozos.scheme != "https" or trozos.hostname not in CDN:
        raise ModelosError("Esa imagen no viene de Thingiverse")

    try:
        respuesta = requests.get(url, timeout=ESPERA, stream=True)
        respuesta.raise_for_status()
    except requests.RequestException as exc:
        raise ModelosError(f"No se ha podido traer la miniatura: {exc}") from exc

    tipo = respuesta.headers.get("Content-Type", "")
    if not tipo.startswith("image/"):
        raise ModelosError("Eso no es una imagen")

    datos = respuesta.raw.read(TOPE_IMAGEN + 1, decode_content=True)
    if len(datos) > TOPE_IMAGEN:
        raise ModelosError("La miniatura pesa demasiado")
    return datos, tipo


def _nombre_seguro(titulo: str, sufijo: str) -> str:
    """Un nombre de fichero hecho por nosotros, no el que venga de fuera.

    Un nombre con barras, con `..` o con dos puntos escribe donde no debe,
    y el de la respuesta no lo controlamos.
    """
    limpio = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    limpio = re.sub(r"[^A-Za-z0-9]+", "-", limpio).strip("-").lower()
    return (limpio[:60] or "modelo") + sufijo


def traer(modelo_id: int, fichero_id: int, titulo: str, destino: Path) -> Path:
    """Se baja un fichero del modelo a la carpeta de salida."""
    detalle = _pedir(f"/files/{int(fichero_id)}")
    url = str(detalle.get("download_url") or detalle.get("public_url") or "")
    nombre_remoto = str(detalle.get("name") or "")
    sufijo = Path(nombre_remoto).suffix.lower()
    if sufijo not in UTILES:
        raise ModelosError(f"«{nombre_remoto}» no es un modelo que sepamos abrir")
    if not url:
        raise ModelosError("Thingiverse no da enlace de descarga para ese fichero")

    try:
        respuesta = requests.get(
            url, headers=_cabeceras(), timeout=ESPERA_DESCARGA, stream=True
        )
        respuesta.raise_for_status()
    except requests.RequestException as exc:
        raise ModelosError(f"No se ha podido descargar: {exc}") from exc

    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / _nombre_seguro(titulo or nombre_remoto, sufijo)
    indice = 2
    while ruta.exists():   # no pisar lo que ya haya
        ruta = destino / _nombre_seguro(titulo or nombre_remoto, f"_{indice}{sufijo}")
        indice += 1

    tamano = 0
    try:
        with ruta.open("wb") as mano:
            for trozo in respuesta.iter_content(1 << 20):
                tamano += len(trozo)
                if tamano > TOPE:
                    raise ModelosError(
                        f"«{nombre_remoto}» pasa de {TOPE // 1024 // 1024} MB; "
                        "bájalo a mano si de verdad lo quieres"
                    )
                mano.write(trozo)
    except Exception:
        ruta.unlink(missing_ok=True)   # nada de ficheros a medias
        raise

    if tamano == 0:
        ruta.unlink(missing_ok=True)
        raise ModelosError("La descarga ha venido vacía")
    return ruta
