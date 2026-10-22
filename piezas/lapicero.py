"""Lapicero con las iniciales en la cara de delante."""
import math

import cadquery as cq

from ad5x.catalog import Param

CUADRADO = "Cuadrado"
REDONDO = "Redondo"

NAME = "Lapicero"
DESCRIPTION = "Bote para lápices, con unas iniciales en relieve o grabadas."
NOTES = (
    "Se imprime de pie y abierto por arriba: ni soportes ni puentes. "
    "El redondo lleva una cara plana delante para las letras; sobre la curva "
    "quedarían torcidas. "
    "Con «letras de otro color» eliges una bobina para el bote y otra para "
    "las iniciales. El grabado en hueco no admite dos colores. "
    "El fondo va más grueso que la pared a propósito: es lo que le da peso y "
    "evita que se vuelque al sacar un boli."
)

PARAMS = [
    Param("texto", "Iniciales", "MDM", unit="", maximum=12),
    Param("forma", "Forma", CUADRADO, unit="", options=(CUADRADO, REDONDO)),
    Param("lado", "Ancho (o diámetro)", 80.0, minimum=40, maximum=160),
    Param("alto", "Altura", 100.0, minimum=40, maximum=200),
    Param("pared", "Espesor de pared", 2.4, minimum=1.2, maximum=8, step=0.2),
    Param("fondo", "Espesor del fondo", 4.0, minimum=1.5, maximum=15, step=0.5),
    Param("esquina", "Radio de esquina", 8.0, minimum=0, maximum=40,
          help="Solo en el cuadrado"),
    Param("tamano_letra", "Tamaño de letra", 28.0, minimum=6, maximum=90),
    Param("relieve", "Altura del relieve", 1.2, minimum=0.2, maximum=5, step=0.2),
    Param("grabado", "Letras grabadas en hueco", False),
    Param("separador", "Con separador en cruz", False,
          help="Parte el bote en cuatro: lápices, bolis, tijeras…"),
    Param("dos_colores", "Letras de otro color", False),
]


# Dónde se corta el plano de delante del bote redondo, en fracción del radio.
# Con 0,78 la cara plana sale de unos dos tercios del diámetro: suficiente
# para tres iniciales, y el bote sigue pareciendo redondo.
PLANO = 0.78


def _medio_espacio(lado, alto, y):
    """Todo lo que queda por delante de y, para rebanar el bote."""
    return (
        cq.Workplane("XY")
        .box(lado * 3, lado * 3, alto * 3, centered=(True, False, True))
        .translate((0, y, alto))
    )


def _bote(forma, lado, alto, pared, esquina):
    """El vaso: la forma exterior menos su hueco."""
    if forma == REDONDO:
        # Una cara plana de arriba abajo, por dentro y por fuera, para que la
        # pared siga midiendo lo mismo en todo el contorno. Sobre la pared
        # curva las letras saldrían torcidas, y una plaquita pegada por fuera
        # quedaría volando por los lados.
        corte = lado / 2 * PLANO
        fuera = (
            cq.Workplane("XY").circle(lado / 2).extrude(alto)
            .cut(_medio_espacio(lado, alto, corte))
        )
        dentro = (
            cq.Workplane("XY").circle(lado / 2 - pared).extrude(alto)
            .cut(_medio_espacio(lado, alto, corte - pared))
        )
        return fuera, dentro

    radio = min(esquina, lado / 2 - 0.1)
    fuera = cq.Workplane("XY").box(lado, lado, alto, centered=(True, True, False))
    dentro = cq.Workplane("XY").box(
        lado - 2 * pared, lado - 2 * pared, alto, centered=(True, True, False)
    )
    if radio > 0.05:
        fuera = fuera.edges("|Z").fillet(radio)
        if radio - pared > 0.05:
            dentro = dentro.edges("|Z").fillet(radio - pared)
    return fuera, dentro


def _letras(texto, tamano, relieve, ancho_util, alto_util):
    """El texto, de pie y mirando hacia delante, encogido si no cabe."""
    dibujo = cq.Workplane("XY").text(texto, tamano, relieve, combine=False)
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
    # Se extruye hacia +Z; de pie tiene que salir hacia +Y y leerse derecho.
    # Girar solo sobre X la deja cabeza abajo; el medio giro sobre Z la
    # endereza sin dejarla en espejo.
    return (
        letras
        .rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 90)
        .rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), 180)
    )


def _cruz(lado, alto, fondo, pared, forma):
    """Dos tabiques cruzados, de media altura, para separar lo que se guarda."""
    hueco = lado - 2 * pared
    largo = hueco if forma != REDONDO else lado - 2 * pared
    altura = (alto - fondo) * 0.75
    uno = cq.Workplane("XY").box(largo, pared, altura, centered=(True, True, False))
    otro = cq.Workplane("XY").box(pared, largo, altura, centered=(True, True, False))
    cruz = uno.union(otro).translate((0, 0, fondo))
    if forma == REDONDO:  # recortar lo que se saldría del círculo
        cruz = cruz.intersect(
            cq.Workplane("XY").circle(lado / 2 - pared).extrude(alto)
        )
    return cruz


def build(texto, forma, lado, alto, pared, fondo, esquina, tamano_letra,
          relieve, grabado, separador, dos_colores):
    iniciales = str(texto).strip()
    if not iniciales:
        raise ValueError("No has escrito ninguna inicial")
    if fondo >= alto:
        raise ValueError("El fondo es más alto que el bote entero")
    if 2 * pared >= lado:
        raise ValueError(
            f"Con paredes de {pared:g} mm no queda hueco dentro: sube el ancho"
        )
    if relieve >= pared:
        raise ValueError(
            f"El relieve ({relieve:g} mm) no puede ser tan hondo como la pared "
            f"({pared:g} mm): bájalo o engorda la pared"
        )

    fuera, dentro = _bote(forma, lado, alto, pared, esquina)
    bote = fuera.cut(dentro.translate((0, 0, fondo)))

    if separador:
        bote = bote.union(_cruz(lado, alto, fondo, pared, forma))

    # Las letras, centradas en la cara de delante y algo por encima del medio:
    # un lapicero se mira desde arriba y ahí es donde se leen mejor.
    if forma == REDONDO:
        # La cuerda de la cara plana, menos un margen a cada lado.
        cuerda = 2 * math.sqrt((lado / 2) ** 2 - (lado / 2 * PLANO) ** 2)
        ancho_util = max(cuerda - 2 * pared - 4, 6.0)
    else:
        ancho_util = lado * 0.72

    letras = _letras(
        iniciales, tamano_letra, relieve,
        ancho_util=ancho_util,
        alto_util=(alto - fondo) * 0.55,
    )
    # Las letras muerden una décima en la pared. Apoyadas justo encima, las
    # dos caras quedan en el mismo plano y a veces no sueldan: salen tres
    # cuerpos sueltos que en la cama se despegan.
    caja = letras.BoundingBox()
    centro_z = alto * 0.58

    cara = lado / 2 * PLANO if forma == REDONDO else lado / 2

    puestas = cq.Workplane(obj=letras).translate(
        (-caja.center.x, cara - caja.ymin - 0.1, centro_z - caja.center.z)
    )

    if grabado:
        return bote.cut(puestas.translate((0, -relieve, 0)))
    if dos_colores:
        return {"Lapicero": bote, "Letras": puestas}
    return bote.union(puestas)
