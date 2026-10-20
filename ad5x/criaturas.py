"""Recetas de animalitos, construidos con bultos redondeados.

Cada especie es una lista de piezas simples —elipsoides y algún cono— en
coordenadas pensadas para una figura de unos 20 mm de alto. Lo que distingue
a un gato de un oso no es el detalle, sino las proporciones: tamaño relativo
de la cabeza, forma de las orejas, largo del hocico.

El estilo es deliberadamente simple y redondeado, como las figuras de resina
de bazar: a 2 cm no cabe más detalle, y las formas gordas se imprimen sin
soportes y no se rompen en manos de un niño.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cadquery as cq

BASE_HEIGHT = 20.0  # mm que miden las recetas antes de escalar
MIN_WALL = 0.9  # mm; por debajo de esto una pieza no se imprime bien


@dataclass(frozen=True)
class Bulto:
    """Un elipsoide: el ladrillo con el que está hecho todo."""

    rx: float
    ry: float
    rz: float
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def solid(self) -> cq.Workplane:
        sphere = cq.Solid.makeSphere(1.0, angleDegrees1=-90, angleDegrees2=90)
        matrix = cq.Matrix(
            [[self.rx, 0, 0, self.x], [0, self.ry, 0, self.y], [0, 0, self.rz, self.z]]
        )
        return cq.Workplane(obj=sphere.transformGeometry(matrix))


@dataclass(frozen=True)
class Cono:
    """Para lo que acaba en punta: picos, cuernos, orejas de gato."""

    base: float
    punta: float
    alto: float
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    inclinacion: float = 0.0  # grados hacia delante (-Y)

    def solid(self) -> cq.Workplane:
        cone = cq.Workplane("XY").circle(self.base).workplane(offset=self.alto)
        cone = cone.circle(max(self.punta, 0.01)).loft()
        if self.inclinacion:
            cone = cone.rotate((0, 0, 0), (1, 0, 0), self.inclinacion)
        return cone.translate((self.x, self.y, self.z))


Pieza = Bulto | Cono


@dataclass(frozen=True)
class Receta:
    nombre: str
    partes: list[Pieza]
    nota: str = ""
    ojos: tuple[float, float, float, float] = field(default=(0, 0, 0, 0))
    """(separación, y, z, radio); radio 0 = sin ojos."""


def _par(pieza: Bulto, separacion: float) -> list[Bulto]:
    """La misma pieza a izquierda y derecha."""
    izq = Bulto(pieza.rx, pieza.ry, pieza.rz, -separacion, pieza.y, pieza.z)
    der = Bulto(pieza.rx, pieza.ry, pieza.rz, separacion, pieza.y, pieza.z)
    return [izq, der]


def _patas(ancho: float, delante: float, detras: float, r: float, z: float) -> list[Bulto]:
    """Las cuatro patas de un cuadrúpedo, como bultos redondos."""
    return [
        Bulto(r, r * 1.15, r, -ancho, delante, z),
        Bulto(r, r * 1.15, r, ancho, delante, z),
        Bulto(r * 1.1, r * 1.2, r * 1.1, -ancho, detras, z),
        Bulto(r * 1.1, r * 1.2, r * 1.1, ancho, detras, z),
    ]


def _oso(cabeza: float, oreja: float, hocico: float, nombre: str, nota: str) -> Receta:
    """El patrón común a oso, panda y ratón: cuerpo gordo y cabeza redonda."""
    return Receta(
        nombre=nombre,
        nota=nota,
        ojos=(2.3, -4.4, 15.8, 0.75),
        partes=[
            Bulto(7, 6, 6, 0, 0, 7),  # cuerpo
            Bulto(cabeza, cabeza * 0.92, cabeza * 0.92, 0, -1, 15),  # cabeza
            Bulto(hocico, hocico * 0.85, hocico * 0.78, 0, -cabeza * 0.85, 13.6),
            *_par(Bulto(oreja, oreja * 0.55, oreja, 0, 0.4, 18.6), cabeza * 0.78),
            *_patas(4.3, -3.4, 3.0, 2.5, 2.7),
        ],
    )


RECETAS: dict[str, Receta] = {
    "Oso panda": _oso(5.5, 2.2, 2.6, "Oso panda", "Sale redondo y macizo; el más fácil de imprimir."),
    "Osito": _oso(5.0, 1.9, 2.4, "Osito", "Como el panda pero con la cabeza algo menor."),
    "Ratón": _oso(4.4, 2.9, 2.2, "Ratón", "Orejas enormes: es lo que lo hace un ratón."),
    "Gato": Receta(
        nombre="Gato",
        nota="Orejas de pico y cola levantada.",
        ojos=(2.0, -4.2, 15.4, 0.7),
        partes=[
            Bulto(6, 5.4, 5.6, 0, 0, 6.6),
            Bulto(5, 4.6, 4.6, 0, -1, 14.6),
            Bulto(2.3, 1.9, 1.6, 0, -4.4, 13.2),
            Cono(2.0, 0.25, 3.2, -3.4, 0.4, 17.6),
            Cono(2.0, 0.25, 3.2, 3.4, 0.4, 17.6),
            Bulto(1.5, 3.6, 3.8, 0, 5.2, 9.5),  # cola pegada al lomo
            *_patas(3.9, -3.2, 2.9, 2.3, 2.5),
        ],
    ),
    "Conejo": Receta(
        nombre="Conejo",
        nota="Las orejas largas van hacia atrás para que no necesiten soporte.",
        ojos=(2.1, -4.0, 14.6, 0.7),
        partes=[
            Bulto(5.8, 5.4, 5.6, 0, 0, 6.4),
            Bulto(4.6, 4.3, 4.4, 0, -1, 14),
            Bulto(2.0, 1.8, 1.5, 0, -4.1, 12.8),
            Bulto(1.5, 1.1, 4.6, -2.3, 1.6, 19.5),
            Bulto(1.5, 1.1, 4.6, 2.3, 1.6, 19.5),
            Bulto(2.2, 2.2, 2.2, 0, 5.4, 6.2),  # rabo
            *_patas(3.7, -3.2, 3.0, 2.3, 2.4),
        ],
    ),
    "Cerdito": Receta(
        nombre="Cerdito",
        nota="El hocico plano y las orejas caídas hacia delante.",
        ojos=(2.0, -4.6, 14.2, 0.7),
        partes=[
            Bulto(6.6, 5.8, 5.4, 0, 0, 6.6),
            Bulto(4.6, 4.2, 4.2, 0, -1.4, 13.6),
            Bulto(2.4, 1.5, 2.0, 0, -5.0, 12.6),  # morro
            Bulto(1.8, 1.4, 1.6, -2.8, -2.6, 16.6),
            Bulto(1.8, 1.4, 1.6, 2.8, -2.6, 16.6),
            *_patas(3.9, -3.0, 3.0, 2.2, 2.3),
        ],
    ),
    "Elefante": Receta(
        nombre="Elefante",
        nota="La trompa baja recta hasta el suelo, así se sostiene sola.",
        ojos=(2.6, -4.0, 15.0, 0.7),
        partes=[
            Bulto(7.2, 6.2, 6.0, 0, 0, 7),
            Bulto(5.2, 4.6, 4.8, 0, -1.4, 14.6),
            Bulto(1.5, 1.5, 4.2, 0, -5.2, 10.4),  # trompa
            Bulto(1.4, 1.2, 2.6, 0, -5.6, 6.6),
            Bulto(3.6, 0.9, 3.4, -5.0, -0.6, 15.2),  # orejotas
            Bulto(3.6, 0.9, 3.4, 5.0, -0.6, 15.2),
            *_patas(4.4, -3.4, 3.2, 2.7, 2.9),
        ],
    ),
    "Pingüino": Receta(
        nombre="Pingüino",
        nota="De una pieza, sin patas sueltas: es el más resistente.",
        ojos=(1.8, -3.9, 15.2, 0.65),
        partes=[
            Bulto(5.4, 4.8, 9.5, 0, 0, 9.5),  # cuerpo entero
            Bulto(4.2, 4.0, 4.0, 0, -0.4, 16.2),
            Cono(1.5, 0.2, 2.6, 0, -4.4, 14.6, -90),  # pico
            Bulto(1.3, 3.2, 4.6, -5.0, 0, 9.0),  # alas
            Bulto(1.3, 3.2, 4.6, 5.0, 0, 9.0),
            Bulto(2.6, 3.4, 1.0, -2.4, -2.6, 0.9),  # pies
            Bulto(2.6, 3.4, 1.0, 2.4, -2.6, 0.9),
        ],
    ),
    "Patito": Receta(
        nombre="Patito",
        nota="El clásico de goma. Muy agradecido de imprimir.",
        ojos=(1.7, -3.6, 14.6, 0.6),
        partes=[
            Bulto(6.2, 5.4, 5.2, 0, 0, 5.6),
            Bulto(4.2, 4.0, 4.0, 0, -1.2, 13.4),
            Bulto(2.4, 2.0, 0.9, 0, -5.0, 12.4),  # pico plano
            Bulto(2.6, 4.2, 2.2, 0, 5.0, 8.0),  # cola
            Bulto(1.2, 3.0, 3.0, -5.4, 0, 6.2),  # alas
            Bulto(1.2, 3.0, 3.0, 5.4, 0, 6.2),
        ],
    ),
    "Rana": Receta(
        nombre="Rana",
        nota="Achatada y con los ojos saltones encima, como la de tu foto.",
        ojos=(3.0, -2.2, 12.6, 1.5),
        partes=[
            Bulto(7.4, 6.6, 4.6, 0, 0, 4.6),
            Bulto(6.0, 5.4, 4.4, 0, -0.8, 9.0),
            Bulto(3.2, 2.6, 1.6, -4.6, -3.0, 1.6),  # patas delanteras
            Bulto(3.2, 2.6, 1.6, 4.6, -3.0, 1.6),
            Bulto(2.6, 3.6, 2.0, -5.4, 2.8, 2.0),  # patas traseras
            Bulto(2.6, 3.6, 2.0, 5.4, 2.8, 2.0),
        ],
    ),
    "Búho": Receta(
        nombre="Búho",
        nota="Todo cabeza. Los ojos grandes son media figura.",
        ojos=(2.6, -4.2, 13.4, 1.6),
        partes=[
            Bulto(6.0, 5.0, 9.0, 0, 0, 9.2),
            Bulto(3.0, 1.0, 2.4, -3.4, 0.6, 17.6),  # penachos
            Bulto(3.0, 1.0, 2.4, 3.4, 0.6, 17.6),
            Cono(1.2, 0.2, 2.0, 0, -4.2, 11.6, -90),  # pico
            Bulto(1.2, 2.6, 4.4, -5.4, 0, 8.6),  # alas
            Bulto(1.2, 2.6, 4.4, 5.4, 0, 8.6),
            Bulto(2.4, 3.0, 0.9, -2.2, -2.8, 0.8),
            Bulto(2.4, 3.0, 0.9, 2.2, -2.8, 0.8),
        ],
    ),
    "Ovejita": Receta(
        nombre="Ovejita",
        nota="El cuerpo con bultos imita la lana sin complicar la impresión.",
        ojos=(1.8, -4.8, 14.0, 0.65),
        partes=[
            Bulto(6.6, 5.8, 5.6, 0, 0, 7.0),
            Bulto(3.0, 2.8, 2.8, -3.6, -2.0, 9.6),  # rizos
            Bulto(3.0, 2.8, 2.8, 3.6, -2.0, 9.6),
            Bulto(3.0, 2.8, 2.8, 0, 3.6, 10.2),
            Bulto(3.4, 3.2, 3.4, 0, -4.2, 13.4),  # carita
            Bulto(2.2, 1.0, 1.4, -3.2, -4.0, 14.2),  # orejas
            Bulto(2.2, 1.0, 1.4, 3.2, -4.0, 14.2),
            *_patas(3.6, -2.8, 3.0, 1.9, 2.2),
        ],
    ),
    "Tortuguita": Receta(
        nombre="Tortuguita",
        nota="Caparazón de cúpula: imposible que salga mal.",
        ojos=(1.6, -6.2, 6.6, 0.6),
        partes=[
            Bulto(8.0, 7.0, 5.4, 0, 0, 3.4),  # caparazón
            Bulto(7.6, 6.6, 1.8, 0, 0, 1.8),  # panza
            Bulto(2.8, 2.6, 2.4, 0, -6.4, 5.0),  # cabeza
            Bulto(2.2, 2.6, 1.2, -5.6, -4.2, 1.2),
            Bulto(2.2, 2.6, 1.2, 5.6, -4.2, 1.2),
            Bulto(2.2, 2.6, 1.2, -5.6, 4.2, 1.2),
            Bulto(2.2, 2.6, 1.2, 5.6, 4.2, 1.2),
            Bulto(1.4, 2.0, 1.0, 0, 6.8, 1.6),  # rabito
        ],
    ),
}


def especies() -> tuple[str, ...]:
    return tuple(RECETAS)


def construir(
    especie: str, medida: float, por_altura: bool = False, con_ojos: bool = True
) -> cq.Workplane:
    """Monta la figura, la apoya en la cama y la lleva al tamaño pedido.

    `medida` es la dimensión más larga, salvo que `por_altura` diga otra cosa.
    Se mide sobre la figura ya montada, no sobre la receta: las orejas del
    conejo sobresalen y harían que «20 mm» no fuesen 20.
    """
    receta = RECETAS.get(especie)
    if receta is None:
        raise ValueError(f"No tengo receta para «{especie}»")

    figura = None
    for parte in receta.partes:
        solido = parte.solid()
        figura = solido if figura is None else figura.union(solido)

    if con_ojos and receta.ojos[3] > 0:
        sep, y, z, r = receta.ojos
        for lado in (-sep, sep):
            figura = figura.union(Bulto(r, r, r, lado, y, z).solid())

    # Cortar lo que quede bajo la cama: así apoya plano y no necesita soportes.
    suelo = (
        cq.Workplane("XY")
        .box(200, 200, 40, centered=(True, True, False))
        .translate((0, 0, -40))
    )
    figura = figura.cut(suelo)

    caja = figura.val().BoundingBox()
    actual = caja.zlen if por_altura else max(caja.xlen, caja.ylen, caja.zlen)
    if actual <= 0:
        raise ValueError(f"«{especie}» ha salido sin volumen")

    escala = medida / actual
    if abs(escala - 1.0) > 1e-6:
        matrix = cq.Matrix([[escala, 0, 0, 0], [0, escala, 0, 0], [0, 0, escala, 0]])
        figura = cq.Workplane(obj=figura.val().transformGeometry(matrix))

    return figura
