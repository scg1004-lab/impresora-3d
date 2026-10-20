"""Llavero: una chapa con anilla para el aro de las llaves.

La anilla no es un agujero hecho en la chapa, sino un aro que sale por fuera
con su propio grosor alrededor: un agujero en el borde de una placa fina se
rompe al primer tirón, y es justo la parte que más sufre.
"""
import cadquery as cq

from ad5x.catalog import Param

PLACA = "Placa con nombre"
PASTILLA = "Pastilla"
CIRCULO = "Círculo"
CORAZON = "Corazón"
FORMAS = (PLACA, PASTILLA, CIRCULO, CORAZON)

NAME = "Llavero"
DESCRIPTION = "Chapa con anilla para las llaves: el nombre, una inicial o un corazón."
NOTES = (
    "La placa y la pastilla se hacen a la medida del texto; el círculo y el "
    "corazón van al tamaño que pidas y la letra se encoge sola para caber. "
    "Con «letras de otro color» eliges una bobina para la chapa y otra para "
    "el texto. El grabado en hueco no admite dos colores: ahí las letras son "
    "un agujero, no una pieza. "
    "Por debajo de 2,5 mm de espesor un llavero de uso diario se parte."
)

PARAMS = [
    Param("texto", "Texto", "ANA", unit="", maximum=20),
    Param("forma", "Forma", PLACA, unit="", options=FORMAS),
    Param("tamano_letra", "Tamaño de letra", 10.0, minimum=4, maximum=40),
    Param(
        "tamano_figura",
        "Tamaño del círculo o el corazón",
        35.0,
        minimum=15,
        maximum=120,
        help="No se usa en la placa ni en la pastilla: esas van a la medida del texto",
    ),
    Param("margen", "Margen alrededor del texto", 6.0, minimum=2, maximum=30),
    Param("espesor", "Espesor de la chapa", 3.0, minimum=1.6, maximum=10, step=0.2),
    Param("relieve", "Altura del relieve", 0.8, minimum=0.2, maximum=4, step=0.1),
    Param("grabado", "Letras grabadas en hueco", False),
    Param("anilla", "Agujero de la anilla", 4.0, minimum=2, maximum=12, step=0.5),
    Param("aro", "Grosor del aro alrededor del agujero", 2.5, minimum=1.2, maximum=8, step=0.5),
    Param("dos_colores", "Letras de otro color", False),
]


def _letras(texto, altura, relieve):
    dibujo = cq.Workplane("XY").text(texto, altura, relieve, combine=False)
    solidos = dibujo.vals()
    if not solidos:
        raise ValueError(f"No se ha podido dibujar «{texto}» con la fuente del sistema")
    return cq.Compound.makeCompound(solidos)


def _encajar(letras, ancho_util, alto_util):
    """Encoge el texto —sin tocar el relieve— hasta que quepa en el hueco."""
    caja = letras.BoundingBox()
    factor = min(1.0, ancho_util / max(caja.xlen, 0.01), alto_util / max(caja.ylen, 0.01))
    if factor >= 0.999:
        return letras
    matriz = cq.Matrix([[factor, 0, 0, 0], [0, factor, 0, 0], [0, 0, 1, 0]])
    return letras.transformGeometry(matriz)


def _corazon(tamano, espesor):
    """Dos lóbulos que se tocan en el centro y una punta abajo.

    Devuelve el corazón ya centrado y la altura del valle entre los lóbulos,
    que es donde muerde la anilla: si se midiera por lo alto de la caja, el
    aro quedaría colgando del pico de un lóbulo.
    """
    r = tamano / 4  # el ancho total son los dos lóbulos: 4·r
    lobulos = (
        cq.Workplane("XY").center(-r, 0).circle(r).extrude(espesor)
        .union(cq.Workplane("XY").center(r, 0).circle(r).extrude(espesor))
    )
    punta = (
        cq.Workplane("XY")
        .polyline([(-2 * r, 0.0), (2 * r, 0.0), (0.0, -2.4 * r)])
        .close()
        .extrude(espesor)
    )
    figura = lobulos.union(punta)
    caja = figura.val().BoundingBox()
    desplazamiento = -(caja.ymin + caja.ymax) / 2
    return figura.translate((0, desplazamiento, 0)), desplazamiento


def _cuerpo(forma, letras, tamano_letra, tamano_figura, margen, espesor):
    """La chapa, el texto ya colocado y por dónde tiene que salir la anilla.

    Devuelve (chapa, texto, centro_del_texto, punto_de_salida, dirección).
    """
    caja = letras.BoundingBox()

    if forma in (PLACA, PASTILLA):
        ancho = caja.xlen + 2 * margen
        # Sin mayúsculas altas ni bajas, «ana» mide poco: la chapa no debe
        # encogerse con el texto o sale una astilla.
        fondo = max(caja.ylen, tamano_letra) + 2 * margen
        chapa = cq.Workplane("XY").box(ancho, fondo, espesor, centered=(True, True, False))
        radio = fondo / 2 - 0.01 if forma == PASTILLA else min(margen, fondo / 2 - 0.1)
        if radio > 0.05:
            chapa = chapa.edges("|Z").fillet(min(radio, ancho / 2 - 0.1))
        return chapa, letras, (0.0, 0.0), (-ancho / 2, 0.0), (-1.0, 0.0)

    if forma == CIRCULO:
        chapa = cq.Workplane("XY").circle(tamano_figura / 2).extrude(espesor)
        texto = _encajar(letras, tamano_figura * 0.80, tamano_figura * 0.50)
        return chapa, texto, (0.0, 0.0), (0.0, tamano_figura / 2), (0.0, 1.0)

    chapa, valle = _corazon(tamano_figura, espesor)
    texto = _encajar(letras, tamano_figura * 0.54, tamano_figura * 0.26)
    # A la altura de los lóbulos es donde el corazón es más ancho, y además
    # el texto queda por debajo del agujero de la anilla, que cae en el valle.
    return chapa, texto, (0.0, 0.0), (0.0, valle), (0.0, 1.0)


def build(texto, forma, tamano_letra, tamano_figura, margen, espesor, relieve,
          grabado, anilla, aro, dos_colores):
    rotulo = str(texto).strip()
    if not rotulo:
        raise ValueError("El texto está vacío")
    if relieve >= espesor:
        raise ValueError(
            f"El relieve ({relieve} mm) no puede ser tan alto como la chapa "
            f"({espesor} mm): baja el relieve o sube el espesor"
        )

    letras = _letras(rotulo, tamano_letra, relieve)
    chapa, letras, centro, salida, direccion = _cuerpo(
        forma, letras, tamano_letra, tamano_figura, margen, espesor
    )

    # La anilla: un aro macizo que muerde la chapa, y luego su agujero.
    radio_aro = anilla / 2 + aro
    mordida = min(radio_aro * 0.7, 3.0)
    centro_aro = (
        salida[0] + direccion[0] * (radio_aro - mordida),
        salida[1] + direccion[1] * (radio_aro - mordida),
    )
    chapa = chapa.union(
        cq.Workplane("XY").center(*centro_aro).circle(radio_aro).extrude(espesor)
    )
    chapa = chapa.cut(
        cq.Workplane("XY")
        .center(*centro_aro)
        .circle(anilla / 2)
        .extrude(espesor * 3)
        .translate((0, 0, -espesor))
    )

    # text() dibuja centrado en el origen; subirlo a la cara de la chapa.
    caja = letras.BoundingBox()
    encima = cq.Workplane(obj=letras).translate(
        (centro[0] - caja.center.x, centro[1] - caja.center.y, espesor)
    )

    if grabado:
        return chapa.cut(encima.translate((0, 0, -relieve)))
    if dos_colores:
        return {"Chapa": chapa, "Letras": encima}
    return chapa.union(encima)
