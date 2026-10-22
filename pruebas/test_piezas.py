r"""Comprueba que todas las piezas del catálogo se construyen de verdad.

    .venv\Scripts\python.exe pruebas\test_piezas.py

No mira que la pieza sea bonita, que eso no se puede automatizar. Mira lo que
sí se puede: que no revienta, que tiene volumen, que cabe en la cama, y cuántos
cuerpos sueltos deja.

Eso último es lo que más vale. Hay piezas que dejan varios a propósito —la caja
va con su tapa al lado, el separador salen cuatro en la misma placa— y para
esas se declara el número aquí abajo. En las demás, dos cuerpos sueltos
significa que algo que debía estar soldado no lo está: unas letras flotando un
pelo por encima de su chapa se ven perfectas en el visor y salen despegadas de
la impresora.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cadquery as cq  # noqa: E402

from ad5x.cad import Mesh  # noqa: E402
from ad5x.catalog import MAX_BUILD_MM, discover  # noqa: E402

PIEZAS = Path(__file__).resolve().parent.parent / "piezas"

# Casos que merecen una pasada además de los valores por defecto: los que han
# dado problemas alguna vez, o los que cambian de forma por completo.
# «_trozos» es cuántos cuerpos sueltos debe dejar ese caso (1 si no se dice).
VARIANTES: dict[str, list[dict]] = {
    "llavero": [
        {"forma": "Placa con nombre", "texto": "ANA"},
        {"forma": "Pastilla", "texto": "LUCIA"},
        {"forma": "Círculo", "texto": "MARIA", "tamano_letra": 28},
        {"forma": "Corazón", "texto": "MAMA"},
        {"forma": "Corazón", "texto": "PAPA", "grabado": True},
        {"forma": "Placa con nombre", "texto": "ANA", "dos_colores": True},
    ],
    "anillo": [
        {"modo": "Talla española", "medida": 12},
        {"sello": True, "texto": "ANA"},
        {"sello": True, "texto": "LUCIA", "ancho": 9, "grabado": True},
        {"sello": True, "texto": "S", "dos_colores": True},
    ],
    "caja": [{"with_lid": False}, {"dos_colores": True}],
    "soporte_cascos": [
        {"forma": "Bajo la mesa"},
        {"forma": "Bajo la mesa", "hueco": 60.0, "caida": 15.0, "grueso": 25.0},
        {"altura": 215.0, "cuna": 140.0, "hueco": 60.0},
    ],
    "lapicero": [
        {"forma": "Redondo"},
        {"forma": "Redondo", "separador": True},
        {"separador": True, "grabado": True},
        {"dos_colores": True},
        {"texto": "A", "lado": 40.0, "tamano_letra": 90.0},
    ],
    "placa_texto": [{"engraved": True}, {"dos_colores": True}],
}

# Lo que deja cada pieza con sus valores por defecto, cuando no es un cuerpo.
TROZOS_POR_DEFECTO = {
    "caja": 2,       # la caja y su tapa, separadas en la misma placa
    "separador": 4,  # cuatro separadores de una tacada
}

fallos: list[str] = []


def _solidos(forma) -> int:
    return len(forma.Solids())


def revisar(etiqueta: str, resultado, trozos: int, varias_partes: bool) -> None:
    if isinstance(resultado, Mesh):
        # Una figura descargada llega como triángulos, no como sólidos.
        if len(resultado.triangles) == 0:
            fallos.append(f"{etiqueta}: la malla ha salido vacía")
        return

    if isinstance(resultado, dict):
        if not varias_partes:
            fallos.append(f"{etiqueta}: ha devuelto partes sin pedírselo")
        piezas = [v.val() if hasattr(v, "val") else v for v in resultado.values()]
        # Cada parte va a una bobina distinta: ninguna puede salir vacía.
        for nombre, parte in zip(resultado, piezas):
            if parte.Volume() <= 0:
                fallos.append(f"{etiqueta}: la parte «{nombre}» no tiene volumen")
        forma = cq.Compound.makeCompound(piezas)
    else:
        forma = resultado.val() if hasattr(resultado, "val") else resultado
        if varias_partes:
            fallos.append(f"{etiqueta}: se esperaban partes con nombre")
        if _solidos(forma) != trozos:
            fallos.append(
                f"{etiqueta}: {_solidos(forma)} cuerpos sueltos, se esperaban {trozos}"
            )

    # Un sólido inválido se construye igual, se ve bien en el visor y revienta
    # al laminar con «no layers were detected», que no dice nada de dónde está
    # el problema. Pasó con un perfil de diez puntos dibujado de una tirada.
    if not forma.isValid():
        fallos.append(f"{etiqueta}: el sólido no es válido, no se podrá laminar")
    if forma.Volume() <= 0:
        fallos.append(f"{etiqueta}: volumen cero")
    caja = forma.BoundingBox()
    for eje, largo in zip("XYZ", (caja.xlen, caja.ylen, caja.zlen)):
        if largo > MAX_BUILD_MM:
            fallos.append(f"{etiqueta}: {largo:.0f} mm en {eje}, no cabe en la cama")


def _rejilla(pieza, slug: str) -> None:
    """El navegador valida los números como min + n*paso.

    Un valor por defecto que no caiga en esa rejilla bloquea el formulario:
    sale «los dos valores más próximos son 2,2 y 2,7» y de ahí no pasa. El
    fallo no está en el código de la pieza, así que no lo caza nada más.
    """
    for p in pieza.params:
        if p.kind != "number" or p.minimum is None:
            continue
        paso = p.step or 1
        resto = (float(p.default) - float(p.minimum)) % paso
        if min(resto, paso - resto) > 1e-9:
            fallos.append(
                f"{slug}: «{p.name}» vale {p.default} por defecto, pero con "
                f"mínimo {p.minimum} y paso {paso} el navegador no lo acepta"
            )


def main() -> int:
    partes, rotas = discover(PIEZAS)
    for slug, error in rotas.items():
        fallos.append(f"{slug}: no carga ({error})")

    print(f"{len(partes)} piezas en el catálogo\n")
    for slug, pieza in sorted(partes.items()):
        _rejilla(pieza, slug)
        for extra in [{}] + VARIANTES.get(slug, []):
            extra = dict(extra)
            trozos = extra.pop("_trozos", None)
            if trozos is None:
                trozos = TROZOS_POR_DEFECTO.get(slug, 1) if not extra else 1
            valores = pieza.defaults() | extra
            etiqueta = f"{slug} {extra or '(por defecto)'}"
            antes = len(fallos)
            try:
                revisar(etiqueta, pieza.build(**valores), trozos,
                        varias_partes=bool(valores.get("dos_colores")))
            except Exception as exc:  # noqa: BLE001 - es justo lo que se busca
                fallos.append(f"{etiqueta}: {type(exc).__name__}: {exc}")
            print(("  FALLA " if len(fallos) > antes else "  ok    ") + etiqueta)

    print()
    if fallos:
        print(f"{len(fallos)} FALLOS:")
        for f in fallos:
            print("  ·", f)
        return 1
    print("Todas las piezas se construyen bien.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
