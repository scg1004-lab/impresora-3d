"""Resuelve los perfiles de filamento de Orca, con su herencia.

Un perfil como «Flashforge PLA Basic @FF AD5X» declara solo lo que cambia y
hereda el resto: PLA Basic → Flashforge Generic PLA → fdm_filament_pla. El
laminador resuelve esa cadena por su cuenta cuando se le pasan por la línea de
órdenes, pero un proyecto 3MF lleva los ajustes **dentro**, ya resueltos, y
Orca no admite que falten: sin `project_settings.config` revienta.

De ahí este módulo: aplanar la cadena y meter el material elegido en el
proyecto, para que una pieza de dos colores no se imprima con el perfil que
venía en la plantilla.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_HERENCIA = 8  # cadenas más largas que esto huelen a ciclo


def _buscar(nombre: str, raiz: Path) -> Path | None:
    """El fichero de un perfil por su nombre, mirando en todo el árbol."""
    directo = raiz / f"{nombre}.json"
    if directo.is_file():
        return directo
    return next(iter(sorted(raiz.rglob(f"{nombre}.json"))), None)


def resolver(fichero: Path, raiz: Path | None = None) -> dict[str, Any]:
    """Un perfil con todo lo que hereda ya incorporado."""
    raiz = raiz or fichero.parent.parent
    cadena: list[dict[str, Any]] = []
    actual: Path | None = fichero

    for _ in range(MAX_HERENCIA):
        if actual is None or not actual.is_file():
            break
        try:
            datos = json.loads(actual.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            break
        cadena.append(datos)
        padre = datos.get("inherits")
        actual = _buscar(padre, raiz) if padre else None

    # Del más general al más concreto, para que el hijo gane.
    resuelto: dict[str, Any] = {}
    for datos in reversed(cadena):
        resuelto.update(datos)
    resuelto.pop("inherits", None)
    return resuelto


def aplicar_filamento(
    ajustes: dict[str, Any], perfil: dict[str, Any], extrusores: int
) -> dict[str, Any]:
    """Mete el filamento elegido en los ajustes de un proyecto.

    En un proyecto, cada clave de filamento es una lista con un valor por
    extrusor; el perfil trae listas de uno. Se replica para todos.
    """
    salida = dict(ajustes)

    def como_estaba(clave: str, valor: Any) -> Any:
        """Respeta la forma que la clave ya tenía en el proyecto.

        No todas son listas por extrusor: `enable_filament_ramming` o
        `machine_load_filament_time` son texto suelto, y meterles una lista
        hace que el laminador falle con «type must be string, but is array».
        """
        unidad = valor[0] if isinstance(valor, list) and valor else valor
        previo = ajustes.get(clave)
        if isinstance(previo, list):
            return [unidad] * extrusores
        if previo is not None:
            return unidad
        return [unidad] * extrusores if isinstance(valor, list) else unidad

    for clave, valor in perfil.items():
        if not (clave.startswith("filament_") or clave in TEMPERATURAS):
            continue
        if clave in SOLO_DEL_PROYECTO:
            continue
        salida[clave] = como_estaba(clave, valor)

    # El nombre y el id identifican el material en la pantalla de la impresora.
    if perfil.get("name"):
        salida["filament_settings_id"] = [perfil["name"]] * extrusores
    if perfil.get("filament_id"):
        salida["filament_ids"] = [perfil["filament_id"]] * extrusores

    return salida


# Las temperaturas no empiezan por filament_, pero vienen del material.
TEMPERATURAS = {
    "nozzle_temperature",
    "nozzle_temperature_initial_layer",
    "nozzle_temperature_range_low",
    "nozzle_temperature_range_high",
    "hot_plate_temp",
    "hot_plate_temp_initial_layer",
    "textured_plate_temp",
    "textured_plate_temp_initial_layer",
    "cool_plate_temp",
    "cool_plate_temp_initial_layer",
    "eng_plate_temp",
    "eng_plate_temp_initial_layer",
    "chamber_temperature",
}

# Estas describen el proyecto, no el material: se dejan como están.
SOLO_DEL_PROYECTO = {
    "filament_colour",
    "filament_maps",
    "filament_map_mode",
    "wall_filament",
    "sparse_infill_filament",
    "solid_infill_filament",
    "support_filament",
    "support_interface_filament",
    "wipe_tower_filament",
}
