"""Box with rounded corners and an optional push-fit lid."""
import cadquery as cq

from ad5x.catalog import Param

NAME = "Caja con tapa"
DESCRIPTION = "Caja rectangular de esquinas redondeadas, con tapa opcional que encaja a presión."
NOTES = (
    "La tapa sale junto a la caja en la misma placa. Si queda floja, sube la "
    "holgura; si no entra, bájala. 0,2 mm es lo normal en PLA. "
    "Marcando «tapa de otro color» podrás elegir una bobina para cada una. "
    "El nombre va grabado en hueco en la cara de fuera de la tapa, que es la "
    "que toca la bandeja: así sale liso y bien definido. En relieve no puede "
    "ser, porque esa cara se imprime boca abajo y las letras quedarían "
    "colgando en el aire."
)

PARAMS = [
    Param("width", "Ancho exterior", 80.0, minimum=15, maximum=210),
    Param("depth", "Fondo exterior", 60.0, minimum=15, maximum=210),
    Param("height", "Altura exterior", 40.0, minimum=8, maximum=210),
    Param("wall", "Espesor de pared", 2.0, minimum=0.8, maximum=10, step=0.2),
    Param("floor", "Espesor del fondo", 2.0, minimum=0.8, maximum=10, step=0.2),
    Param("corner", "Radio de esquina", 4.0, minimum=0, maximum=30, step=0.5),
    Param("with_lid", "Incluir tapa", True),
    Param("lid_height", "Altura del labio de la tapa", 6.0, minimum=2, maximum=20),
    Param("clearance", "Holgura de la tapa", 0.2, minimum=0.0, maximum=1.0, step=0.05),
    Param("nombre", "Nombre en la tapa", "", unit="",
          help="Se graba en la cara de fuera de la tapa. Déjalo vacío para "
               "una tapa lisa."),
    Param("nombre_tamano", "Tamaño de letra", 0.0, minimum=0, maximum=80, step=0.5,
          help="0 = que lo calcule él, lo más grande que quepa dejando un "
               "margen. Pon un número si lo quieres más pequeño."),
    Param("nombre_profundidad", "Profundidad del grabado", 0.6,
          minimum=0.2, maximum=5, step=0.2,
          help="Cuánto se hunden las letras. 0,6 mm son tres capas: se ve "
               "bien y no debilita la tapa."),
    Param("dos_colores", "Tapa de otro color", False),
]

# Aire entre las letras y el borde de la tapa cuando el tamaño se calcula
# solo. Pegar el nombre al canto queda mal y además la esquina redondeada
# se come las puntas.
MARGEN_NOMBRE = 6.0


def _rounded(width, depth, height, radius):
    shape = cq.Workplane("XY").box(width, depth, height, centered=(True, True, False))
    if radius > 0.05:
        shape = shape.edges("|Z").fillet(min(radius, width / 2 - 0.1, depth / 2 - 0.1))
    return shape


def _letras_para_la_tapa(nombre, tamano, profundidad, ancho_util, fondo_util):
    """El nombre, listo para hundirlo en la cara de fuera de la tapa.

    Dos cosas que no son obvias:

    La cara de fuera de la tapa es la que se imprime contra la bandeja (la
    tapa sale con el labio hacia arriba, que es la única forma de que el
    labio no quede en el aire). Grabado ahí sale liso y definido; en
    relieve saldría colgando sobre la nada.

    Y como se mira desde abajo, el texto hay que darle la vuelta: se gira
    media vuelta sobre el eje Y, que le cambia el lado a la vez que lo deja
    creciendo hacia arriba desde z=0. Sin eso, el nombre se lee al revés en
    la tapa puesta.
    """
    rotulo = str(nombre).strip()
    if not rotulo:
        return None

    def dibujar(puntos):
        trazos = cq.Workplane("XY").text(
            rotulo, puntos, profundidad, combine=False).vals()
        if not trazos:
            raise ValueError(
                f"No se ha podido dibujar «{rotulo}» con la fuente del sistema"
            )
        return cq.Compound.makeCompound(trazos)

    if tamano and tamano > 0:
        letras = dibujar(tamano)
        caja = letras.BoundingBox()
        if caja.xlen > ancho_util or caja.ylen > fondo_util:
            raise ValueError(
                f"«{rotulo}» a {tamano:g} mm no cabe en la tapa: ocuparía "
                f"{caja.xlen:.0f}×{caja.ylen:.0f} mm y hay "
                f"{ancho_util:.0f}×{fondo_util:.0f}. Baja el tamaño de letra, "
                "pon 0 para que lo calcule él, o haz la caja más grande"
            )
    else:
        # Se dibuja una vez a un tamaño cualquiera y se escala: el ancho del
        # texto crece proporcional a los puntos, así que una regla de tres
        # acierta a la primera y no hay que ir probando.
        patron = dibujar(10.0)
        caja = patron.BoundingBox()
        if caja.xlen <= 0 or caja.ylen <= 0:
            raise ValueError(f"«{rotulo}» no deja ninguna letra que grabar")
        tamano = 10.0 * min(ancho_util / caja.xlen, fondo_util / caja.ylen)
        if tamano < 3:
            raise ValueError(
                f"«{rotulo}» no cabe en una tapa de {ancho_util + 2 * MARGEN_NOMBRE:.0f}"
                f"×{fondo_util + 2 * MARGEN_NOMBRE:.0f} mm ni a letra pequeña: "
                "haz la caja más grande o pon un nombre más corto"
            )
        letras = dibujar(round(tamano, 1))
        caja = letras.BoundingBox()

    centrado = cq.Workplane(obj=letras).translate(
        (-caja.center.x, -caja.center.y, 0)
    )
    # Media vuelta sobre Y: queda en espejo (para leerse desde abajo) y
    # colgando bajo z=0, así que se sube otra vez a su sitio.
    return centrado.rotate((0, 0, 0), (0, 1, 0), 180).translate(
        (0, 0, profundidad)
    )


def build(width, depth, height, wall, floor, corner, with_lid, lid_height,
          clearance, nombre, nombre_tamano, nombre_profundidad, dos_colores):
    inner_w = width - 2 * wall
    inner_d = depth - 2 * wall
    if inner_w <= 1 or inner_d <= 1:
        raise ValueError(
            f"Con paredes de {wall} mm no queda hueco dentro: sube el ancho/fondo "
            "o baja el espesor de pared"
        )
    if floor >= height:
        raise ValueError("El fondo es más alto que la caja entera")

    cavity = _rounded(inner_w, inner_d, height, corner - wall).translate((0, 0, floor))
    box = _rounded(width, depth, height, corner).cut(cavity)

    if not with_lid:
        if str(nombre).strip():
            raise ValueError(
                "El nombre va en la tapa, y has quitado la tapa: marca "
                "«Incluir tapa» o deja el nombre vacío"
            )
        return box

    lid_plate = _rounded(width, depth, floor, corner)
    lip_w = inner_w - 2 * clearance
    lip_d = inner_d - 2 * clearance
    if lip_w <= 1 or lip_d <= 1:
        raise ValueError("La holgura se come el labio de la tapa entero")

    lip = _rounded(lip_w, lip_d, lid_height, corner - wall - clearance).translate(
        (0, 0, floor)
    )
    lid = lid_plate.union(lip)

    if nombre_profundidad >= floor:
        raise ValueError(
            f"Un grabado de {nombre_profundidad:g} mm atraviesa una tapa de "
            f"{floor:g} mm: baja la profundidad o sube el espesor del fondo"
        )
    letras = _letras_para_la_tapa(
        nombre, nombre_tamano, nombre_profundidad,
        max(width - 2 * MARGEN_NOMBRE, 1.0),
        max(depth - 2 * MARGEN_NOMBRE, 1.0),
    )
    if letras is not None:
        lid = lid.cut(letras)

    # Side by side on the plate, with a 10 mm gap so the slicer keeps them apart.
    lid = lid.translate((width + 10, 0, 0))
    if dos_colores:
        # Named pieces: each one goes to its own IFS channel.
        piezas = {"Caja": box, "Tapa": lid}
        if letras is not None:
            # Las letras rellenan justo el hueco que se acaba de vaciar, así
            # que con otra bobina el nombre sale a dos colores y a ras.
            piezas["Nombre"] = letras.translate((width + 10, 0, 0))
        return piezas
    return box.union(lid)
