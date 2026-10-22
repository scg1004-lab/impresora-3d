"""Soporte para los cascos: de mesa, o colgado bajo el tablero."""
import cadquery as cq

from ad5x.catalog import Param

DE_MESA = "De mesa"
BAJO_LA_MESA = "Bajo la mesa"

NAME = "Soporte para cascos"
DESCRIPTION = "Para dejar los cascos: una torre sobre la mesa o un gancho bajo el tablero."
NOTES = (
    "«Bajo la mesa» es el práctico: se pega con cinta de doble cara al "
    "tablero, no ocupa sitio y tarda media hora. «De mesa» luce más pero son "
    "varias horas y bastante material, así que imprímelo con poco relleno. "
    "La diadema apoya en una cuna cóncava: no la deforma como los ganchos "
    "estrechos, que dejan marca si los cascos pasan ahí la noche. "
    "Nada de esto necesita soportes: lo que vuela lo hace a 45° o menos."
)

PARAMS = [
    Param("forma", "Dónde va", DE_MESA, unit="", options=(DE_MESA, BAJO_LA_MESA)),
    Param("cuna", "Ancho de la cuna", 80.0, minimum=40, maximum=140,
          help="Un poco más que el ancho de la diadema"),
    Param("hueco", "Fondo de la cuna", 24.0, minimum=8, maximum=60,
          help="Lo que se hunde la diadema; cuanto más, menos se escurre"),
    Param("grueso", "Grosor del material", 8.0, minimum=4, maximum=25),
    # Solo para el de mesa
    Param("altura", "Altura total", 180.0, minimum=80, maximum=215,
          help="Solo en el de mesa. Los cascos cuelgan desde arriba"),
    Param("base", "Lado de la base", 110.0, minimum=60, maximum=200,
          help="Solo en el de mesa. Cuanto más grande, menos se vuelca"),
    # Solo para el de bajo la mesa
    Param("agarre", "Largo de la pletina", 70.0, minimum=30, maximum=150,
          help="Solo en el de bajo la mesa: lo que se pega al tablero"),
    Param("caida", "Cuánto baja", 35.0, minimum=15, maximum=120,
          help="Solo en el de bajo la mesa"),
]


def _redondeado(ancho, fondo, alto, radio):
    pieza = cq.Workplane("XY").box(ancho, fondo, alto, centered=(True, True, False))
    radio = min(radio, ancho / 2 - 0.1, fondo / 2 - 0.1)
    if radio > 0.05:
        pieza = pieza.edges("|Z").fillet(radio)
    return pieza


def _cuna(ancho, fondo, grueso, hueco, z):
    """La pieza donde descansa la diadema, con su hueco cóncavo.

    El hueco es un trozo de cilindro tumbado: una curva ancha reparte el peso
    en vez de clavarse en la espuma, que es lo que estropea unos cascos
    colgados siempre del mismo sitio.
    """
    alto = hueco + grueso
    barra = _redondeado(ancho, fondo, alto, fondo / 2 - 0.1).translate((0, 0, z))

    # Radio del cilindro que talla el hueco: por geometría, para una cuerda
    # de «ancho» y una flecha de «hueco».
    radio = (hueco * hueco + (ancho / 2) ** 2) / (2 * hueco)
    # El cilindro va tumbado a lo largo de Y, para que la curva corra a lo
    # ANCHO de la cuna, que es por donde pasa la diadema. Con el eje en X la
    # curva sale cruzada y se come la pieza a lo alto sin sujetar nada.
    corte = (
        cq.Workplane("XZ")
        .circle(radio)
        .extrude(fondo * 2, both=True)
        .translate((0, 0, z + alto + radio - hueco))
    )
    return barra.cut(corte)


def _de_mesa(cuna, hueco, grueso, altura, base):
    cuerpo = _redondeado(base, base, grueso, base / 6)

    # La columna se ensancha hacia arriba hasta la cuna. El tramo de
    # ensanche mide lo mismo que lo que crece a cada lado, y así el vuelo
    # queda a 45°, que se imprime sin soportes.
    col_ancho, col_fondo = grueso * 2.2, grueso * 2.2
    cuna_fondo = grueso * 2.6
    crece = max((cuna - col_ancho) / 2, (cuna_fondo - col_fondo) / 2, 1.0)

    alto_cuna = hueco + grueso
    recta = altura - grueso - crece - alto_cuna
    if recta < 10:
        raise ValueError(
            f"Con {altura:g} mm no queda columna: sube la altura o baja la cuna"
        )

    columna = _redondeado(col_ancho, col_fondo, recta, col_ancho / 4).translate(
        (0, 0, grueso)
    )
    cuerpo = cuerpo.union(columna)

    # El ensanche: un loft del perfil de la columna al de la cuna.
    abajo = cq.Workplane("XY", origin=(0, 0, grueso + recta)).rect(col_ancho, col_fondo)
    arriba = abajo.workplane(offset=crece).rect(cuna, cuna_fondo)
    cuerpo = cuerpo.union(arriba.loft(ruled=True))

    cuerpo = cuerpo.union(
        _cuna(cuna, cuna_fondo, grueso, hueco, grueso + recta + crece)
    )
    return cuerpo.edges(cq.selectors.NearestToPointSelector((0, 0, grueso))).fillet(
        min(grueso * 0.8, 4.0)
    )


def _bajo_la_mesa(cuna, hueco, grueso, agarre, caida):
    """Una «J» tumbada en la cama, con el ancho en vertical.

    El perfil queda plano sobre la cama y se extruye hacia arriba, así que
    todas las capas son iguales: ni un voladizo, ni un soporte.

    Son cuatro cajas unidas y no un perfil dibujado de una tirada: una
    polilínea de diez puntos con medidas al límite sale como sólido
    inválido —Orca contesta «no layers were detected»— y es un fallo que no
    se ve hasta que intentas laminar.
    """
    brazo = hueco + grueso * 1.5          # lo que sale hacia fuera para colgar
    labio = min(hueco * 0.8 + grueso, caida - grueso * 0.5)  # el pico final
    labio = max(labio, grueso)

    # El ancho del gancho se imprime en vertical, así que cada milímetro son
    # minutos. Más de 45 mm no sujeta mejor —la diadema apoya igual— y pasa de
    # dos horas a cuatro. El de mesa sí usa la cuna entera: ahí se nota.
    ancho = min(cuna, 45.0)

    def bloque(x0, x1, y0, y1):
        return (
            cq.Workplane("XY")
            .box(x1 - x0, y1 - y0, ancho, centered=False)
            .translate((x0, y0, 0))
        )

    pletina = bloque(0.0, agarre, 0.0, grueso)
    bajada = bloque(agarre - grueso, agarre, 0.0, caida)
    brazo_h = bloque(agarre - grueso, agarre + brazo, caida - grueso, caida)
    pico = bloque(agarre + brazo - grueso, agarre + brazo, caida - labio, caida)

    gancho = pletina.union(bajada).union(brazo_h).union(pico)

    # Redondear los cantos del perfil: por dentro es donde rompería, y por
    # fuera es lo que roza con la diadema.
    for radio in (min(grueso * 0.8, caida / 4, labio / 2), grueso * 0.3):
        try:
            gancho = gancho.edges("|Z").fillet(radio)
            break
        except Exception:  # noqa: BLE001 - mejor a escuadra que sin pieza
            continue

    caja = gancho.val().BoundingBox()
    return gancho.translate((-caja.center.x, -caja.center.y, -caja.zmin))


def build(forma, cuna, hueco, grueso, altura, base, agarre, caida):
    if forma == BAJO_LA_MESA:
        return _bajo_la_mesa(cuna, hueco, grueso, agarre, caida)
    return _de_mesa(cuna, hueco, grueso, altura, base)
