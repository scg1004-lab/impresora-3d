r"""Trae la última versión del código desde GitHub, si es que la hay.

Lo que cruza son unos 170 KB: el programa entero. Lo gordo del paquete —el
Python con CadQuery dentro, y los modelos descargados— no cambia nunca y no
viaja. Así el portátil de casa se pone al día solo, sin volver a pasar medio
giga por un pendrive.

Cuatro reglas que no se negocian:

* **Solo en el paquete portátil.** En el ordenador donde se programa hay
  código sin subir todavía, y una actualización lo machacaría. Se reconoce
  por la carpeta `py\`, que solo existe en el paquete.
* **Esta función no levanta excepciones. Nunca.** Se llama al arrancar, y
  arrancar tiene que funcionar aunque la actualización no. Una wifi que se
  corta a mitad de la descarga no puede dejar a nadie mirando un traceback.
* **Nunca existe un momento con el código a medio poner.** Lo nuevo se
  extrae aparte, se comprueba allí, y solo entonces se cambia con dos
  renombrados. Si algo sale mal, se deshacen y queda lo de antes.
* **Solo se toca el código.** Ni `py\`, ni `modelos\`, ni lo que haya
  generado en `salida\`, ni el `.env` con el código de la impresora. Y las
  piezas que haya escrito quien lo usa se respetan.

La primera versión de esto se escribió con un `rmtree` seguido de escribir
encima, y un revisor encontró dos formas de dejar el programa sin arrancar:
`http.client.IncompleteRead` no es `OSError`, así que una descarga cortada
—y codeload responde troceado— se escapaba del `except`; y el propio
rescate podía reventar con `FileExistsError` si el antivirus tenía un
fichero abierto, dejando el código a medio borrar. De ahí el diseño de
ahora.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

REPO = "scg1004-lab/impresora-3d"
NOMBRE_REPO = REPO.split("/")[1]
RAMA = "main"

MARCA = ".version"        # la versión instalada, para no bajar lo mismo dos veces
RESPALDO = ".anterior"    # la copia de seguridad, por si la nueva no arranca
ENTRANTE = ".nuevo"       # donde se arma la versión nueva antes de poner nada
CERROJO = ".actualizando"  # carpeta-cerrojo: dos arranques a la vez no se pisan
PARTE = "actualizaciones.txt"   # que paso en cada arranque, para poder mirarlo
LINEAS_PARTE = 40               # con las ultimas sobra

ESPERA = 6                # segundos para preguntar la versión
ESPERA_DESCARGA = 60      # segundos para bajarse el código
ESPERA_ARRANQUE = 240     # segundos para la prueba de que el código nuevo carga
TOPE_FICHERO = 5 * 1024 * 1024    # ningún fichero del programa pasa de esto
TOPE_DESCARGA = 20 * 1024 * 1024  # ni el ZIP entero

# Lo que se reemplaza. Todo lo que no esté aquí se queda como está.
# `distribucion` entra por la plantilla 3MF que lleva dentro: sin ella la
# impresora no abre el trabajo, y si algún día cambia tiene que llegar.
CARPETAS = ("ad5x", "piezas", "web", "pruebas", "distribucion")
FICHEROS = (
    "run.py",
    "requirements.txt",
    ".env.example",
    "README.md",
    "LEEME.txt",
    "Taller AD5X.cmd",
    "comprobar_impresora.py",
)
# Si esto no viene dentro del ZIP, la descarga no vale y no se toca nada.
IMPRESCINDIBLES = ("ad5x/web.py", "ad5x/catalog.py", "run.py")

SHA = re.compile(r"^[0-9a-f]{40}$")
HOSTS = ("github.com", "codeload.github.com", "api.github.com")


# ─── red ─────────────────────────────────────────────────────────────────────

class _SoloGitHub(urllib.request.HTTPRedirectHandler):
    """Sigue redirecciones, pero solo dentro de GitHub y solo por HTTPS.

    urllib, por su cuenta, sigue hasta diez saltos a cualquier sitio y acepta
    `http` pelado por el camino. Aquí sabemos exactamente de dónde tiene que
    venir el código.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        trozos = urllib.parse.urlsplit(newurl)
        if trozos.scheme != "https" or trozos.hostname not in HOSTS:
            return None  # no se sigue: urllib lanzará y lo recogemos arriba
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_abridor = urllib.request.build_opener(_SoloGitHub)


def _pedir(url: str, cabeceras: dict[str, str], espera: int, tope: int) -> bytes:
    peticion = urllib.request.Request(url, headers={"User-Agent": "taller-ad5x", **cabeceras})
    with _abridor.open(peticion, timeout=espera) as respuesta:
        return respuesta.read(tope)


def _version_publicada() -> str:
    """El sha del último commit, en texto plano: una respuesta de 40 bytes."""
    crudo = _pedir(
        f"https://api.github.com/repos/{REPO}/commits/{RAMA}",
        {"Accept": "application/vnd.github.sha"}, ESPERA, 64,
    )
    sha = crudo.decode("utf-8", "replace").strip()
    # Un portal cautivo contesta 200 con HTML: eso no es una versión.
    return sha if SHA.match(sha) else ""


def _descargar(sha: str) -> zipfile.ZipFile:
    """El ZIP de ese commit exacto.

    Por la rama no: entre preguntar la versión y bajarla puede haber entrado
    otro push, y acabarías instalando algo que no es lo que comprobaste.
    """
    datos = _pedir(
        f"https://codeload.github.com/{REPO}/zip/{sha}", {},
        ESPERA_DESCARGA, TOPE_DESCARGA,
    )
    return zipfile.ZipFile(io.BytesIO(datos))


# ─── el contenido del ZIP ────────────────────────────────────────────────────

def _util(partes: list[str]) -> bool:
    if not partes or any(p in ("..", "", ".") for p in partes):
        return False
    # Los dos puntos, en cualquier tramo: una unidad (C:) o un flujo alterno
    # de NTFS (`web.py:oculto`), que se escribe sin que luego se vea.
    if any(":" in p for p in partes):
        return False
    if partes[0] not in CARPETAS and "/".join(partes) not in FICHEROS:
        return False
    return True


def _contenido(zf: zipfile.ZipFile, sha: str) -> dict[str, zipfile.ZipInfo]:
    """Los miembros que nos sirven, con la carpeta que GitHub añade ya quitada.

    Se filtran uno a uno en vez de usar `extractall`: el ZIP es nuestro, pero
    llega por la red, y volcar a ciegas lo que llega por la red es cómo se
    acaban escribiendo ficheros donde no se debe.
    """
    util: dict[str, zipfile.ZipInfo] = {}
    for info in zf.infolist():
        if info.is_dir() or info.file_size > TOPE_FICHERO:
            continue
        tramos = info.filename.split("/")
        # La raíz que pone GitHub al bajar por sha es exactamente «<repo>-<sha>».
        # Si no coincide, esto no es el commit que pedimos: fuera.
        if not tramos or tramos[0] != f"{NOMBRE_REPO}-{sha}":
            continue
        partes = tramos[1:]
        if _util(partes):
            util["/".join(partes)] = info
    return util


# ─── poner la versión nueva ──────────────────────────────────────────────────

def _extraer(zf: zipfile.ZipFile, miembros: dict[str, zipfile.ZipInfo], destino: Path) -> None:
    for ruta, info in miembros.items():
        fichero = destino / ruta
        # Cinturón además de tirantes: nada fuera de la carpeta de trabajo.
        if not fichero.resolve().is_relative_to(destino.resolve()):
            raise ValueError(f"El ZIP traía una ruta rara: {ruta}")
        fichero.parent.mkdir(parents=True, exist_ok=True)
        fichero.write_bytes(zf.read(info))


def _compila(destino: Path, miembros: dict[str, zipfile.ZipInfo]) -> bool:
    """¿Lo descargado es Python válido? En memoria, sin dejar `__pycache__`."""
    for ruta in miembros:
        if not ruta.endswith(".py"):
            continue
        try:
            compile((destino / ruta).read_bytes(), ruta, "exec")
        except (SyntaxError, ValueError, OSError):
            return False
    return True


def _arranca(destino: Path, raiz: Path) -> bool:
    """Carga de verdad el programa nuevo, en un proceso aparte.

    Compilar solo encuentra erratas de sintaxis. Lo que de verdad rompe una
    actualización es un módulo que ya no está o un import que no resuelve, y
    eso solo se ve importando. Si no se puede hacer la prueba, no se toma
    como un fallo: no vamos a rechazar una versión buena por no poder mirarla.
    """
    piton = raiz / "py" / "python.exe"
    if not piton.is_file():
        return True
    orden = [str(piton), "-c", "import sys; sys.path.insert(0, '.'); import ad5x.web"]
    try:
        hecho = subprocess.run(
            orden, cwd=destino, capture_output=True, text=True,
            timeout=ESPERA_ARRANQUE, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return hecho.returncode == 0


def _sitio_para_el_respaldo(raiz: Path) -> Path | None:
    """Una carpeta vacía donde dejar lo de antes.

    Si no se puede vaciar la de siempre —un fichero abierto por el antivirus,
    OneDrive sincronizando— se usa la siguiente libre antes que arriesgarse.
    """
    for intento in range(1, 6):
        sitio = raiz / (RESPALDO if intento == 1 else f"{RESPALDO}-{intento}")
        if sitio.exists():
            shutil.rmtree(sitio, ignore_errors=True)
        if sitio.exists():
            continue
        try:
            sitio.mkdir(parents=True)
        except OSError:
            continue
        return sitio
    return None


def _cambiar(raiz: Path, nuevo: Path, respaldo: Path) -> list[tuple[Path, Path]]:
    """Cambia lo viejo por lo nuevo a base de renombrados, y dice qué movió.

    Renombrar es instantáneo y no deja a medias: en todo momento el programa
    está entero, o el de antes o el de después. Copiar encima, no.
    """
    movidos: list[tuple[Path, Path]] = []
    for nombre in CARPETAS + FICHEROS:
        viene = nuevo / nombre
        if not viene.exists():
            continue
        hay = raiz / nombre
        if hay.exists():
            os.replace(hay, respaldo / nombre)
            movidos.append((respaldo / nombre, hay))
        os.replace(viene, hay)
        movidos.append((hay, viene))
    return movidos


def _deshacer(movidos: list[tuple[Path, Path]]) -> bool:
    """Devuelve lo movido a su sitio. Dice si lo ha conseguido del todo.

    Lo que no pueda devolver sigue en la carpeta de respaldo, así que no se
    pierde nada; pero entonces no se puede decir que todo siguió igual, y el
    aviso tiene que contarlo. Un mensaje tranquilizador falso es peor que uno
    incómodo.
    """
    entero = True
    for origen, destino in reversed(movidos):
        try:
            if origen.exists():
                os.replace(origen, destino)
        except OSError:
            entero = False
    return entero


def _devolver_sus_piezas(raiz: Path, respaldo: Path) -> int:
    """Las piezas que haya escrito quien usa el programa no se pierden.

    Una actualización trae el catálogo de casa, y si alguien ha dejado ahí una
    pieza suya, borrarla sin más sería quitarle su trabajo.
    """
    suyas = respaldo / "piezas"
    if not suyas.is_dir():
        return 0
    rescatadas = 0
    for fichero in suyas.glob("*.py"):
        destino = raiz / "piezas" / fichero.name
        if not destino.exists():
            shutil.copy2(fichero, destino)
            rescatadas += 1
    return rescatadas


# ─── lo que llama run.py ─────────────────────────────────────────────────────

def hay_novedad(raiz: Path) -> str | None:
    """El sha publicado, si es distinto del instalado. None si no, o si falla.

    Mirar no instala nada: instalar solo se hace al arrancar, que es cuando
    no hay nadie usando el programa. Esto es para poder avisar.
    """
    try:
        if not es_el_paquete(raiz):
            return None
        publicada = _version_publicada()
        if publicada and publicada != _version_instalada(raiz):
            return publicada
    except Exception:  # noqa: BLE001 - avisar es un lujo, nunca un fallo
        return None
    return None


def version_instalada(raiz: Path) -> str:
    """La versión que lleva puesta, para poder enseñarla.

    El actualizador es silencioso a propósito —no puede molestar al
    arrancar—, pero entonces no hay forma de saber si corrió. Con la versión
    a la vista, «no me sale lo nuevo» se responde mirando la pantalla en vez
    de adivinando.
    """
    return _version_instalada(raiz)


def es_el_paquete(raiz: Path) -> bool:
    """¿Estamos en el paquete portátil, o en el equipo donde se programa?"""
    return (raiz / "py" / "python.exe").is_file()


def _version_instalada(raiz: Path) -> str:
    try:
        return (raiz / MARCA).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _hacerlo(raiz: Path) -> str | None:
    try:
        publicada = _version_publicada()
    except Exception as exc:  # noqa: BLE001 - lo normal es no tener internet
        _apuntar(raiz, f"no he podido preguntar a GitHub: {type(exc).__name__}")
        return None
    if not publicada:
        _apuntar(raiz, "GitHub ha contestado algo que no es una versión")
        return None
    if publicada == _version_instalada(raiz):
        _apuntar(raiz, f"ya estaba al día ({publicada[:7]})")
        return None

    zf = _descargar(publicada)
    miembros = _contenido(zf, publicada)
    if any(n not in miembros for n in IMPRESCINDIBLES):
        return None  # la descarga no trae el programa entero: ni tocarla

    nuevo = raiz / ENTRANTE
    shutil.rmtree(nuevo, ignore_errors=True)
    nuevo.mkdir(parents=True, exist_ok=True)
    movidos: list[tuple[Path, Path]] = []
    rescatadas = 0
    try:
        _extraer(zf, miembros, nuevo)
        if not _compila(nuevo, miembros) or not _arranca(nuevo, raiz):
            return "Hay una versión nueva pero no carga bien; sigo con esta."

        respaldo = _sitio_para_el_respaldo(raiz)
        if respaldo is None:
            return None  # sin sitio donde guardar lo de ahora, no se toca nada

        movidos = _cambiar(raiz, nuevo, respaldo)
        try:
            rescatadas = _devolver_sus_piezas(raiz, respaldo)
        except OSError:
            rescatadas = 0
    except Exception:  # noqa: BLE001 - pase lo que pase, se queda lo de antes
        try:
            entero = _deshacer(movidos)
        except Exception:  # noqa: BLE001 - ni el rescate puede tirar el arranque
            entero = False
        finally:
            shutil.rmtree(nuevo, ignore_errors=True)
        if entero:
            return "No se ha podido actualizar; sigo con la versión de antes."
        return (
            f"No se ha podido actualizar y la vuelta atrás ha quedado a medias. "
            f"No se ha perdido nada: está en la carpeta «{RESPALDO}». Díselo a papá."
        )

    shutil.rmtree(nuevo, ignore_errors=True)
    try:
        (raiz / MARCA).write_text(publicada, encoding="utf-8")
    except OSError:
        pass  # sin marca se vuelve a bajar la próxima vez; molesto, no grave

    aviso = f"Actualizado ({len(miembros)} ficheros). Versión {publicada[:7]}."
    if rescatadas == 1:
        aviso += " Tu pieza sigue ahí."
    elif rescatadas:
        aviso += f" Tus {rescatadas} piezas siguen ahí."
    return aviso


def _apuntar(raiz: Path, linea: str) -> None:
    """Deja constancia de lo que ha pasado, sin poder fallar por ello.

    Sin esto, un portátil que no se actualiza no da ninguna pista: ni por
    qué no, ni si llegó a intentarlo. Son cuatro líneas de texto que se
    abren con el Bloc de notas.
    """
    try:
        sello = time.strftime("%Y-%m-%d %H:%M")
        fichero = raiz / PARTE
        previas = []
        if fichero.is_file():
            previas = fichero.read_text(encoding="utf-8").splitlines()
        previas.append(f"{sello}  {linea}")
        fichero.write_text(
            "\n".join(previas[-LINEAS_PARTE:]) + "\n", encoding="utf-8"
        )
    except Exception:  # noqa: BLE001 - apuntar nunca puede tirar el arranque
        pass


def comprobar(raiz: Path) -> str | None:
    """Actualiza si toca. Devuelve qué ha hecho, o None si no ha hecho nada.

    No levanta excepciones. Ninguna. Es su contrato: lo llama el arranque.
    """
    try:
        if not es_el_paquete(raiz):
            return None   # el equipo de trabajo: ni se apunta, ni se toca

        # Dos dobles clics seguidos no pueden actualizar a la vez sobre la
        # misma carpeta. `mkdir` es atómico: o lo creas tú, o ya era de otro.
        cerrojo = raiz / CERROJO
        try:
            cerrojo.mkdir()
        except FileExistsError:
            _apuntar(raiz, "otro arranque estaba actualizando; no hago nada")
            return None
        except OSError as exc:
            _apuntar(raiz, f"no puedo escribir en la carpeta ({exc})")
            return None
        try:
            # Lo que haya pasado dentro ya queda apuntado ahí: aquí se
            # apuntaría encima, y con un «ya estaba al día» justo debajo de
            # un «no he podido preguntar a GitHub», que es decir dos cosas
            # distintas sobre el mismo arranque.
            hecho = _hacerlo(raiz)
            if hecho:
                _apuntar(raiz, hecho)
            return hecho
        finally:
            shutil.rmtree(cerrojo, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001 - arrancar vale más que actualizar
        _apuntar(raiz, f"ha fallado: {type(exc).__name__}: {exc}")
        return None
