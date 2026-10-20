"""Escribe un proyecto 3MF de varias partes, cada una con su color.

Orca no asigna colores desde la línea de órdenes, pero sí respeta lo que
venga dentro del fichero: un objeto con varias `<part>`, cada una apuntando a
un extrusor. Comprobado contra la impresora el 2026-10-19 — el G-code que sale
lleva los cambios de herramienta.

La estructura está copiada de un proyecto que guardó el propio Orca
(`distribucion/plantilla-3mf/_referencia-dos-colores.3mf`). Dos detalles que
no son evidentes: la geometría va en un fichero aparte bajo `3D/Objects/`, al
que el modelo principal apunta con `p:path`, y la asignación de color vive en
`model_settings.config`, no junto a la malla.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

PLANTILLA = Path(__file__).resolve().parent.parent / "distribucion" / "plantilla-3mf"
CENTRO_CAMA = (110.0, 110.0)  # la AD5X mide 220 mm
OBJETO_RAIZ = 3  # el id que usa Orca para el objeto que agrupa las partes
FICHERO_PARTES = "3D/Objects/piezas.model"

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="png" ContentType="image/png"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""

RELS_MODELO = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/{FICHERO_PARTES}" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
</Relationships>"""

CABECERA = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<model unit="millimeter" xml:lang="en-US"'
    ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
    ' xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"'
    ' xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
    ' requiredextensions="p">\n'
    ' <metadata name="Application">BambuStudio-2.3.1</metadata>\n'
    ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
)


@dataclass
class Parte:
    """Un trozo de la pieza que se imprime en su propio color."""

    nombre: str
    vertices: Sequence[tuple[float, float, float]]
    triangulos: Sequence[tuple[int, int, int]]
    extrusor: int = 1


def _uuid(bloque: int, indice: int) -> str:
    """Un UUID estable con la pinta que espera el formato."""
    return f"{bloque:04x}{indice:04x}-81cb-4c03-9d28-80fed5dfa1dc"


def _malla(parte: Parte) -> str:
    vertices = "".join(
        f'<vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>'
        for x, y, z in parte.vertices
    )
    caras = "".join(
        f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in parte.triangulos
    )
    return f"<mesh><vertices>{vertices}</vertices><triangles>{caras}</triangles></mesh>"


def _fichero_partes(partes: Sequence[Parte]) -> str:
    objetos = "".join(
        f'<object id="{i + 1}" p:UUID="{_uuid(1, i)}" type="model">{_malla(p)}</object>'
        for i, p in enumerate(partes)
    )
    return CABECERA + f" <resources>{objetos}</resources>\n <build/>\n</model>"


def _modelo_principal(partes: Sequence[Parte], centro: tuple[float, float]) -> str:
    componentes = "".join(
        f'<component p:path="/{FICHERO_PARTES}" objectid="{i + 1}"'
        f' p:UUID="{_uuid(1, i)}" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
        for i in range(len(partes))
    )
    return (
        CABECERA
        + f' <resources><object id="{OBJETO_RAIZ}" p:UUID="{_uuid(0, 1)}" type="model">'
        + f"<components>{componentes}</components></object></resources>\n"
        + f' <build><item objectid="{OBJETO_RAIZ}" p:UUID="{_uuid(0, 3)}"'
        + f' transform="1 0 0 0 1 0 0 0 1 {centro[0]} {centro[1]} 0" printable="1"/></build>\n'
        + "</model>"
    )


def _ajustes(partes: Sequence[Parte]) -> str:
    """Dónde vive de verdad la asignación de color."""
    trozos = "".join(
        f'<part id="{i + 1}" subtype="normal_part">'
        f'<metadata key="name" value="{p.nombre}"/>'
        f'<metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>'
        f'<metadata key="extruder" value="{p.extrusor}"/>'
        f'<mesh_stat edges_fixed="0" degenerate_facets="0" facets_removed="0"'
        f' facets_reversed="0" backwards_edges="0"/></part>'
        for i, p in enumerate(partes)
    )
    mapa = " ".join(str(p.extrusor) for p in partes)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n'
        f' <object id="{OBJETO_RAIZ}">'
        f'<metadata key="name" value="pieza"/>'
        f'<metadata key="extruder" value="{partes[0].extrusor}"/>'
        f"{trozos}</object>\n"
        ' <plate><metadata key="plater_id" value="1"/>'
        '<metadata key="plater_name" value=""/>'
        '<metadata key="locked" value="false"/>'
        '<metadata key="filament_map_mode" value="Manual"/>'
        f'<metadata key="filament_maps" value="{mapa}"/>'
        f'<model_instance><metadata key="object_id" value="{OBJETO_RAIZ}"/>'
        '<metadata key="instance_id" value="0"/></model_instance></plate>\n'
        "</config>"
    )


def escribir_proyecto(
    partes: Sequence[Parte],
    destino: Path,
    centro: tuple[float, float] = CENTRO_CAMA,
) -> Path:
    """Empaqueta las partes en un .3mf que Orca lamina a varios colores."""
    if not partes:
        raise ValueError("Un proyecto necesita al menos una parte")

    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", _modelo_principal(partes, centro))
        z.writestr("3D/_rels/3dmodel.model.rels", RELS_MODELO)
        z.writestr(FICHERO_PARTES, _fichero_partes(partes))
        z.writestr("Metadata/model_settings.config", _ajustes(partes))

        # Orca revienta sin los ajustes del proyecto: los toma de la plantilla,
        # que describe la máquina y no esta pieza en concreto.
        perfil = PLANTILLA / "project_settings.config"
        if perfil.is_file():
            z.writestr("Metadata/project_settings.config", perfil.read_bytes())
        for nombre in ("plate_1.png", "plate_1_small.png", "plate_no_light_1.png",
                       "top_1.png", "pick_1.png"):
            imagen = PLANTILLA / nombre
            if imagen.is_file():
                z.writestr(f"Metadata/{nombre}", imagen.read_bytes())

    return destino
