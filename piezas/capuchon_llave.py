"""Capuchón que se calza en la cabeza de una llave, para distinguirlas.

Se imprime de pie y con la boca contra la bandeja. Es lo que no tiene
vuelta de hoja: así las paredes suben rectas desde la primera capa y lo
único que queda en el aire es el techo, que son tres milímetros de puente
y cualquier impresora los hace. Al revés —tumbado o con la boca arriba—
el hueco interior habría que cerrarlo por arriba a lo ancho, y eso sí se
descuelga.

El agujero de la anilla atraviesa el capuchón y coincide con el de la
llave, así que el aro pasa por los dos y el capuchón no se puede salir
aunque quede holgado.
"""
import cadquery as cq

from ad5x.catalog import Param

NAME = "Capuchón para llave"
DESCRIPTION = "Caperuza de color que se calza en la cabeza de la llave, con la inicial."
NOTES = (
    "Mide tu llave con un calibre o una regla: el ancho de la cabeza y el "
    "grosor de la chapa son las dos cotas que deciden si entra. Si entra "
    "dura, baja la holgura; si baila, súbela. 0,3 mm es lo normal en PLA. "
    "El agujero del capuchón tiene que caer donde el de la llave: mide "
    "desde el borde de arriba de la cabeza hasta el centro del agujero. "
    "Imprime con faldilla: la pieza es alta y apoya poco."
)

PARAMS = [
    Param("texto", "Letra o nombre", "", unit="", maximum=10,
          help="Una inicial se lee de un vistazo en el bolsillo. Déjalo "
               "vacío para un capuchón liso de color."),
    Param("ancho_cabeza", "Ancho de la cabeza de la llave", 20.0,
          minimum=8, maximum=45, step=0.5,
          help="Lo ancho que es la parte gorda de la llave, la que se coge."),
    Param("grosor_llave", "Grosor de la cabeza", 3.0,
          minimum=1.0, maximum=8, step=0.1,
          help="Lo que mide de canto. En una llave de casa suelen ser 2 o 3 mm."),
    Param("cubrir", "Cuánto la cubre", 22.0, minimum=6, maximum=45, step=0.5,
          help="Desde el borde de arriba de la cabeza hacia abajo. Cuanto "
               "más cubra, más agarra, pero no tape la parte que empieza a "
               "estrecharse."),
    Param("agujero", "Agujero de la anilla", 5.0, minimum=0, maximum=12, step=0.5,
          help="El mismo que el de la llave. A 0 se queda sin agujero y "
               "aguanta solo a presión."),
    Param("altura_agujero", "Del borde de arriba al centro del agujero", 7.0,
          minimum=2, maximum=30, step=0.5,
          help="Medido en la llave. Es lo que hace que los dos agujeros "
               "coincidan y el aro pase por los dos."),
    Param("holgura", "Holgura", 0.3, minimum=0.0, maximum=1.0, step=0.05),
    Param("pared", "Espesor de las paredes", 1.2, minimum=0.8, maximum=4, step=0.2),
    Param("techo", "Espesor del techo", 1.6, minimum=0.8, maximum=5, step=0.2),
    Param("tamano_letra", "Tamaño de letra", 0.0, minimum=0, maximum=40, step=0.5,
          help="0 = el mayor que quepa en el hueco que deja el agujero."),
    Param("relieve", "Altura de la letra", 0.6, minimum=0.2, maximum=3, step=0.2),
    Param("grabado", "Letra grabada en hueco", True,
          help="En hueco sale siempre bien. En relieve se lee más, pero son "
               "letras que sobresalen de una pared vertical y se rozan."),
    Param("dos_colores", "Letra de otro color", False),
]

# Aire entre la letra y lo que la rodea (bordes y agujero).
MARGEN = 2.0


def _redondeado(ancho, fondo, alto, radio):
    """Una caja con los cantos verticales redondeados."""
    forma = cq.Workplane("XY").box(ancho, fondo, alto, centered=(True, True, False))
    radio = min(radio, ancho / 2 - 0.1, fondo / 2 - 0.1)
    if radio > 0.05:
        forma = forma.edges("|Z").fillet(radio)
    return forma


def _letras(texto, puntos, relieve):
    """El texto de pie en el plano XZ, que es como queda mirando de frente."""
    trazos = cq.Workplane("XZ").text(texto, puntos, relieve, combine=False).vals()
    if not trazos:
        raise ValueError(
            f"No se ha podido dibujar «{texto}» con la fuente del sistema"
        )
    return cq.Compound.makeCompound(trazos)


def build(texto, ancho_cabeza, grosor_llave, cubrir, agujero, altura_agujero,
          holgura, pared, techo, tamano_letra, relieve, grabado, dos_colores):
    hueco_ancho = ancho_cabeza + 2 * holgura
    hueco_fondo = grosor_llave + 2 * holgura
    ancho = hueco_ancho + 2 * pared
    fondo = hueco_fondo + 2 * pared
    alto = cubrir + techo

    cuerpo = _redondeado(ancho, fondo, alto, fondo / 2 - 0.2)
    hueco = _redondeado(hueco_ancho, hueco_fondo, cubrir, hueco_fondo / 2 - 0.2)
    cuerpo = cuerpo.cut(hueco)

    # El agujero del capuchón, a la altura del de la llave. Se mide desde
    # arriba porque es el borde que tope con el techo al calzarlo.
    z_agujero = None
    if agujero > 0:
        if altura_agujero >= cubrir:
            raise ValueError(
                f"El capuchón cubre {cubrir:g} mm y el agujero de la llave "
                f"está a {altura_agujero:g} mm del borde: no llega a taparlo. "
                "Sube «cuánto la cubre» o baja la altura del agujero"
            )
        z_agujero = cubrir - altura_agujero
        if z_agujero - agujero / 2 < pared:
            raise ValueError(
                "El agujero se sale por la boca del capuchón: sube «cuánto "
                "la cubre» o usa un agujero más pequeño"
            )
        if z_agujero + agujero / 2 > cubrir - 0.1:
            raise ValueError(
                "El agujero se come el techo: baja la altura del agujero o "
                "el diámetro"
            )
        cuerpo = cuerpo.cut(
            cq.Workplane("XZ")
            .circle(agujero / 2)
            .extrude(fondo * 2, both=True)
            .translate((0, 0, z_agujero))
        )

    rotulo = str(texto).strip()
    if not rotulo:
        if dos_colores:
            raise ValueError(
                "Has pedido la letra de otro color pero no has puesto ninguna "
                "letra"
            )
        return cuerpo

    # La letra va en la cara de delante, debajo del agujero: es el trozo de
    # pared que queda entero.
    ancho_util = ancho - 2 * MARGEN
    if z_agujero is None:
        abajo, arriba = MARGEN, alto - MARGEN
    else:
        abajo, arriba = MARGEN, z_agujero - agujero / 2 - MARGEN
    alto_util = arriba - abajo
    if alto_util < 3 or ancho_util < 3:
        raise ValueError(
            "No queda sitio para la letra entre la boca y el agujero: sube "
            "«cuánto la cubre» o quita el texto"
        )

    if tamano_letra and tamano_letra > 0:
        letras = _letras(rotulo, tamano_letra, relieve)
        caja = letras.BoundingBox()
        if caja.xlen > ancho_util or caja.zlen > alto_util:
            raise ValueError(
                f"«{rotulo}» a {tamano_letra:g} mm no cabe: ocuparía "
                f"{caja.xlen:.0f}×{caja.zlen:.0f} mm y hay "
                f"{ancho_util:.0f}×{alto_util:.0f}. Pon 0 para que lo calcule él"
            )
    else:
        # Se dibuja a un tamaño cualquiera, se mide y se escala: el texto
        # crece proporcional a los puntos, así que una regla de tres acierta.
        patron = _letras(rotulo, 10.0, relieve)
        caja = patron.BoundingBox()
        if caja.xlen <= 0 or caja.zlen <= 0:
            raise ValueError(f"«{rotulo}» no deja ninguna letra que poner")
        tamano_letra = 10.0 * min(ancho_util / caja.xlen, alto_util / caja.zlen)
        if tamano_letra < 3:
            raise ValueError(
                f"«{rotulo}» no cabe en esta cara ni a letra pequeña: pon "
                "menos letras o un capuchón más grande"
            )
        letras = _letras(rotulo, round(tamano_letra, 1), relieve)
        caja = letras.BoundingBox()

    # Colocadas contra la cara de delante: hacia dentro si van grabadas,
    # hacia fuera si van en relieve. Se mide en vez de confiar en hacia
    # dónde crece el texto, que depende del plano con el que se dibujó.
    cara = -fondo / 2
    y_destino = cara if grabado else cara - relieve
    puestas = cq.Workplane(obj=letras).translate((
        -caja.center.x,
        y_destino - caja.ymin,
        (abajo + arriba) / 2 - caja.center.z,
    ))

    if grabado:
        cuerpo = cuerpo.cut(puestas)
        if dos_colores:
            return {"Capuchón": cuerpo, "Letra": puestas}
        return cuerpo

    if dos_colores:
        return {"Capuchón": cuerpo, "Letra": puestas}
    return cuerpo.union(puestas)
