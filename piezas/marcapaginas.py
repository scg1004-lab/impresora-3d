"""Marcapáginas con el nombre, en relieve o calado."""
import cadquery as cq

from ad5x.catalog import Param

RELIEVE = "Letras en relieve"
CALADO = "Letras caladas"

NAME = "Marcapáginas"
DESCRIPTION = "Tira fina con un nombre, para el libro. Con agujero para la borla."
NOTES = (
    "Fino a propósito: a 1 mm el PLA dobla y no abulta entre las páginas. "
    "Por encima de 1,5 mm ya es una tablilla y levanta la tapa del libro. "
    "«Caladas» queda más fino y se imprime antes, pero las letras con hueco "
    "dentro —A, O, P, R, 4— se caerían; si el nombre lleva alguna, te lo "
    "digo al generar y lo haces en relieve. "
    "Se imprime tumbado, sin soportes, y tarda poco más de media hora."
)

PARAMS = [
    Param("texto", "Nombre", "LUCIA", unit="", maximum=20,
          help="Lo que va escrito. En mayúsculas se lee mejor de lejos"),
    Param("modo", "Las letras van...", RELIEVE, unit="", options=(RELIEVE, CALADO),
          help="En relieve sobresalen; caladas son un agujero con la forma de la letra"),
    Param("largo", "Largo", 150.0, minimum=80, maximum=210,
          help="Un libro de bolsillo pide unos 140 mm; uno grande, 180"),
    Param("ancho", "Ancho", 40.0, minimum=20, maximum=80),
    Param("espesor", "Espesor", 1.0, minimum=0.6, maximum=3, step=0.2,
          help="1 mm dobla y no abulta. Más de 1,5 ya es una tablilla"),
    Param("tamano_letra", "Tamaño de letra", 22.0, minimum=6, maximum=60,
          help="Se encoge sola si el nombre no cabe a lo largo"),
    Param("relieve", "Altura del relieve", 0.6, minimum=0.2, maximum=2, step=0.2,
          help="Solo si las letras van en relieve. Se suma al espesor"),
    Param("esquina", "Radio de esquina", 6.0, minimum=0, maximum=20,
          help="Redondear evita que se doblen las puntas con el uso"),
    Param("agujero", "Agujero para la borla", 5.0, minimum=0, maximum=15, step=0.5,
          help="0 = sin agujero. Va en el extremo izquierdo"),
    Param("dos_colores", "Letras de otro color", False,
          help="Solo con letras en relieve: una bobina para la tira y otra para el nombre"),
]


def _letras(texto, tamano, alto, ancho_util, alto_util):
    """El nombre dibujado, encogido si no cabe a lo largo de la tira."""
    dibujo = cq.Workplane("XY").text(texto, tamano, alto, combine=False)
    solidos = dibujo.vals()
    if not solidos:
        raise ValueError(f"No se ha podido dibujar «{texto}» con la fuente del sistema")
    letras = cq.Compound.makeCompound(solidos)

    caja = letras.BoundingBox()
    factor = min(1.0, ancho_util / max(caja.xlen, 0.01), alto_util / max(caja.ylen, 0.01))
    if factor < 0.999:
        letras = letras.transformGeometry(
            cq.Matrix([[factor, 0, 0, 0], [0, factor, 0, 0], [0, 0, 1, 0]])
        )
    return letras


def _calar(tira, caladas, espesor, tamano_letra):
    """Cala las letras y sujeta con un puente las que tienen hueco dentro.

    El hueco de una A, una O o una D queda suelto al atravesar la chapa: se
    cae de la tira y aparece por ahí en la cama. Las plantillas de toda la
    vida lo resuelven igual, con una barrita que une el hueco con el resto
    de la letra, y por eso una «O» de plantilla se ve partida.

    Se buscan los trozos sueltos sobre la pieza ya calada —que es donde se
    ven de verdad, sin adivinar qué letra los produce— y se le devuelve a
    cada uno su puente.
    """
    resultado = tira.cut(caladas)
    sueltas = [s for s in resultado.val().Solids()][1:]
    if not sueltas:
        return resultado

    grosor = max(tamano_letra * 0.09, 0.9)   # el puente, lo justo para aguantar
    alcance = tamano_letra * 0.35            # lo que hay que cruzar hasta la chapa

    puentes = None
    for isla in sueltas:
        caja = isla.BoundingBox()
        barra = (
            cq.Workplane("XY")
            .box(caja.xlen + 2 * alcance, grosor, espesor * 3, centered=(True, True, False))
            .translate((caja.center.x, caja.center.y, -espesor))
        )
        puentes = barra if puentes is None else puentes.union(barra)

    # El puente se le quita al corte, no se le añade a la tira: así queda
    # a ras y no sobresale por ningún lado.
    resultado = tira.cut(caladas.cut(puentes))

    todavia = len(resultado.val().Solids()) - 1
    if todavia > 0:
        raise ValueError(
            f"Quedan {todavia} trozo(s) sueltos que se caerían al calarlo. "
            "Prueba con la letra más grande, o ponlo en relieve"
        )
    return resultado


def build(texto, modo, largo, ancho, espesor, tamano_letra, relieve, esquina,
          agujero, dos_colores):
    nombre = str(texto).strip()
    if not nombre:
        raise ValueError("No has escrito ningún nombre")
    if modo == CALADO and dos_colores:
        raise ValueError(
            "Las letras caladas son un agujero, no una pieza: no se les puede "
            "dar otro color. Ponlas en relieve"
        )
    if modo == RELIEVE and relieve >= espesor + relieve:
        pass  # el relieve se suma por encima, nunca se come la tira

    tira = cq.Workplane("XY").box(largo, ancho, espesor, centered=(True, True, False))
    radio = min(esquina, ancho / 2 - 0.1, largo / 2 - 0.1)
    if radio > 0.05:
        tira = tira.edges("|Z").fillet(radio)

    # El agujero de la borla, en el extremo izquierdo.
    hueco_izquierdo = 0.0
    if agujero > 0:
        borde = max(agujero * 0.7, 3.0)          # material alrededor del agujero
        centro_x = -largo / 2 + agujero / 2 + borde
        hueco_izquierdo = agujero + 2 * borde
        tira = tira.cut(
            cq.Workplane("XY")
            .center(centro_x, 0)
            .circle(agujero / 2)
            .extrude(espesor * 3)
            .translate((0, 0, -espesor))
        )

    # El nombre, centrado en lo que queda de tira.
    margen = max(ancho * 0.12, 4.0)
    ancho_util = largo - hueco_izquierdo - 2 * margen
    if ancho_util < 10:
        raise ValueError(
            "Entre el agujero y los márgenes no queda sitio para el nombre: "
            "alarga la tira o quita el agujero"
        )
    alto_grabado = relieve if modo == RELIEVE else espesor * 3
    letras = _letras(nombre, tamano_letra, alto_grabado,
                     ancho_util, ancho - 2 * margen)

    caja = letras.BoundingBox()
    centro_x = (-largo / 2 + hueco_izquierdo + largo / 2) / 2
    if modo == CALADO:
        caladas = cq.Workplane(obj=letras).translate(
            (centro_x - caja.center.x, -caja.center.y, -espesor)
        )
        return _calar(tira, caladas, espesor, tamano_letra)

    encima = cq.Workplane(obj=letras).translate(
        (centro_x - caja.center.x, -caja.center.y, espesor - 0.05)
    )
    if dos_colores:
        return {"Tira": tira, "Nombre": encima}
    return tira.union(encima)
