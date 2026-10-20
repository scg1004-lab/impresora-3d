"""Anillo a medida del dedo, con sello opcional para un nombre.

La medida se puede dar de dos formas: el diámetro interior en milímetros, o
la talla española de toda la vida, que es el contorno interior en milímetros
menos 40 (una talla 12 son 52 mm de contorno, 16,6 mm de diámetro).
"""
import math

import cadquery as cq

from ad5x.catalog import Param

POR_DIAMETRO = "Diámetro interior (mm)"
POR_TALLA = "Talla española"

NAME = "Anillo"
DESCRIPTION = "Anillo al tamaño del dedo, liso o con un sello con texto."
NOTES = (
    "Para saber la medida: rodea el dedo con una tira de papel, márcala, "
    "mídela y esos milímetros son el contorno; la talla española es ese "
    "contorno menos 40. O mide por dentro un anillo que ya le valga y usa "
    "ese diámetro. "
    "Se imprime de pie, sin soportes. El PLA no da de sí: imprime uno de "
    "prueba antes de hacer la serie, y si entra justo sube la holgura "
    "0,2 mm. Por debajo de 1,5 mm de grosor se parte al ponérselo."
)

PARAMS = [
    # Sin unidad a propósito: el mismo campo vale para milímetros y para
    # tallas, y poner «mm» al lado sería mentira la mitad de las veces.
    Param("medida", "Medida del dedo", 17.0, unit="", minimum=4, maximum=34,
          help="Diámetro en mm (12 a 28), o la talla (4 a 30), según lo que elijas debajo"),
    Param("modo", "Esa medida es...", POR_DIAMETRO, unit="",
          options=(POR_DIAMETRO, POR_TALLA)),
    Param("holgura", "Holgura", 0.3, minimum=0.0, maximum=1.5, step=0.1,
          help="Se suma al diámetro interior; 0,3 mm es lo normal en PLA"),
    Param("ancho", "Ancho de la banda", 6.0, minimum=2, maximum=25),
    Param("grosor", "Grosor de la banda", 2.2, minimum=1.2, maximum=8, step=0.2),
    Param("confort", "Interior redondeado", True,
          help="Redondea los cantos de dentro: entra y sale mucho mejor"),
    Param("sello", "Con sello", False),
    Param("texto", "Texto del sello", "", unit="", maximum=14),
    Param("tamano_letra", "Tamaño de letra del sello", 5.0, minimum=2, maximum=15),
    Param("saliente", "Cuánto sobresale el sello", 1.2, minimum=0.4, maximum=6, step=0.2),
    Param("relieve", "Altura del relieve", 0.6, minimum=0.2, maximum=3, step=0.1),
    Param("grabado", "Letras grabadas en hueco", False),
    Param("dos_colores", "Letras de otro color", False),
]


def _diametro_interior(medida, modo, holgura):
    if modo == POR_TALLA:
        diametro = (medida + 40.0) / math.pi
        if not 4 <= medida <= 30:
            raise ValueError(f"La talla {medida:g} no existe: van de la 4 a la 30")
    else:
        diametro = float(medida)
        if not 12 <= diametro <= 28:
            raise ValueError(
                f"{diametro:g} mm de diámetro no es un dedo: van de 12 a 28 mm. "
                "Si querías dar la talla, cámbialo en «esa medida es...»"
            )
    return diametro + holgura


def _redondear(pieza, selector, radio):
    """Redondea si se puede; una cota apurada no debe tirar la pieza abajo."""
    if radio <= 0.05:
        return pieza
    try:
        return pieza.edges(selector).fillet(radio)
    except Exception:  # noqa: BLE001 - mejor sin redondeo que sin anillo
        return pieza


def _banda(interior, exterior, ancho, grosor, confort):
    tubo = (
        cq.Workplane("XY").circle(exterior / 2).extrude(ancho)
        .cut(cq.Workplane("XY").circle(interior / 2).extrude(ancho * 3)
             .translate((0, 0, -ancho)))
    )
    if confort:
        tubo = _redondear(tubo, "%CIRCLE", min(grosor * 0.45, ancho / 3))
    else:
        tubo = _redondear(tubo, "%CIRCLE", min(0.5, grosor / 4, ancho / 6))
    return tubo


def _texto_de_pie(rotulo, tamano, relieve, ancho_util, alto_util):
    """El texto dibujado en vertical, mirando hacia +Y, y encogido si no cabe."""
    dibujo = cq.Workplane("XY").text(rotulo, tamano, relieve, combine=False)
    solidos = dibujo.vals()
    if not solidos:
        raise ValueError(f"No se ha podido dibujar «{rotulo}» con la fuente del sistema")
    letras = cq.Compound.makeCompound(solidos)

    caja = letras.BoundingBox()
    factor = min(1.0, ancho_util / max(caja.xlen, 0.01), alto_util / max(caja.ylen, 0.01))
    if factor < 0.999:
        letras = letras.transformGeometry(
            cq.Matrix([[factor, 0, 0, 0], [0, factor, 0, 0], [0, 0, 1, 0]])
        )
    # El texto se dibuja tumbado y se extruye hacia +Z. De pie tiene que
    # salir hacia +Y y leerse derecho: girarlo sobre X lo pone vertical, y el
    # medio giro sobre Z lo deja mirando al que tiene el anillo delante (si no,
    # sale en espejo, que es el error clásico de grabar sobre una cara).
    return (
        letras
        .rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 90)
        .rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 180)
    )


def build(medida, modo, holgura, ancho, grosor, confort, sello, texto,
          tamano_letra, saliente, relieve, grabado, dos_colores):
    interior = _diametro_interior(medida, modo, holgura)
    exterior = interior + 2 * grosor
    anillo = _banda(interior, exterior, ancho, grosor, confort)

    rotulo = str(texto).strip()
    if not sello:
        return anillo
    if not rotulo:
        raise ValueError("Has marcado «con sello» pero no has escrito ningún texto")
    if relieve >= saliente + grosor:
        raise ValueError("El relieve es más alto que el sello entero")

    letras = _texto_de_pie(
        rotulo, tamano_letra, relieve,
        ancho_util=exterior * 0.75,
        alto_util=ancho * 0.72,
    )
    caja = letras.BoundingBox()

    # La chapa del sello: tangente a la banda, metida en ella para que suelden.
    ancho_sello = min(caja.xlen + 2 * tamano_letra * 0.45, exterior * 0.95)
    cara = exterior / 2 + saliente
    arraigo = exterior / 2 - grosor * 0.9
    chapa = (
        # El plano XZ mira hacia -Y, de ahí el signo: así el sello sale hacia fuera.
        cq.Workplane("XZ")
        .rect(ancho_sello, ancho)
        .extrude(-(cara - arraigo))
        .translate((0, arraigo, ancho / 2))
    )
    chapa = _redondear(chapa, "|Y", min(ancho_sello / 4, ancho / 4, 2.0))
    anillo = anillo.union(chapa)

    encima = cq.Workplane(obj=letras).translate(
        (-caja.center.x, cara - caja.ymin, ancho / 2 - caja.center.z)
    )

    if grabado:
        return anillo.cut(encima.translate((0, -relieve, 0)))
    if dos_colores:
        return {"Anillo": anillo, "Letras": encima}
    return anillo.union(encima)
