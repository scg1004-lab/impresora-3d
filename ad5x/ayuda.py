"""Textos de la ayuda contextual (los ⓘ de la página).

Todos en un solo sitio: la plantilla los pinta con la macro `tip` y app.js les
da el comportamiento (ratón, teclado, toque, Escape). La ayuda de cada
cota de una pieza no está aquí: la escribe la propia pieza en `help=` de su
`Param`, que es quien sabe qué significa.

Los valores de laminado salen de los perfiles de Orca-Flashforge para la AD5X
con boquilla de 0,4 mm (comprobados el 25/10/2026). Si se actualiza Orca o se
deja un JSON propio en `perfiles/`, pueden cambiar: revisar estos textos.
"""
from __future__ import annotations

AYUDA: dict[str, str] = {
    # --- cabecera -----------------------------------------------------------
    "trabajos": (
        "Abre el panel de trabajos: lo que imprime ahora, la cola de la app, "
        "lo guardado en la impresora y lo generado en este ordenador. "
        "El número indica los trabajos pendientes en la cola."
    ),
    "impresora": (
        "Estado de la AD5X por su conexión de red (modo LAN), consultado cada "
        "15 segundos. Necesita PRINTER_SERIAL y PRINTER_CHECK_CODE en el .env. "
        "Si la API no contesta pero la impresora se anuncia en la red, dice "
        "«sin modo LAN». El avance es la capa actual sobre el total."
    ),
    # --- catálogo -----------------------------------------------------------
    "catalogo": (
        "Piezas paramétricas: cada una dibuja el modelo con CadQuery a partir "
        "de sus cotas. Al elegir una, sus cotas salen en el formulario."
    ),
    "importar": (
        "Formatos: .stl, .obj, .step y .stp como modelo; .gcode, .gx y .3mf "
        "laminados. Se copia a salida/. Lo ya laminado va directo a elegir "
        "color y enviar; un .3mf que solo trae geometría se trata como modelo."
    ),
    "thingiverse": (
        "Busca en Thingiverse con su API (hace falta THINGIVERSE_TOKEN en el "
        ".env). Al elegir un fichero se descarga a salida/ como si lo "
        "hubieras traído tú."
    ),
    "rotas": (
        "Ficheros de piezas/ que no se han podido cargar. No salen en el "
        "catálogo hasta que se arreglen; aparecen al recargar la página."
    ),
    # --- formulario ---------------------------------------------------------
    "cotas": (
        "Medidas de la pieza, en milímetros salvo que diga otra cosa. Cada "
        "cota tiene un mínimo y un máximo que fija la pieza; fuera de ese "
        "rango no se genera. «Generar STL» crea el fichero en salida/ y, si "
        "está Orca, lo lamina solo para darte el tiempo."
    ),
    # --- resultado ----------------------------------------------------------
    "r_medidas": (
        "Caja que ocupa la pieza: ancho × fondo × alto en mm. La cama de la "
        "AD5X admite 220 mm por eje; si algo no cabe, sale un aviso."
    ),
    "r_material": (
        "Volumen macizo de la pieza en cm³, calculado por CadQuery. No es el "
        "filamento gastado: ese lo da Orca al laminar (en la línea de estado), "
        "y suele ser menor por el relleno. En modelos importados no se calcula."
    ),
    "r_tiempo": (
        "Estimación de Orca en modo normal, leída de la cabecera del G-code. "
        "Cambia con el material y la calidad: si los cambias, vuelve a laminar."
    ),
    "r_fichero": (
        "Nombre del fichero en la carpeta salida/ de este ordenador, con fecha "
        "y hora para que no se pisen."
    ),
    # --- ajustes de laminado ------------------------------------------------
    "material": (
        "Perfil de filamento de Orca-Flashforge para la AD5X (boquilla 0,4 mm). "
        "Fija temperaturas, ventilador y flujo. Por defecto: Flashforge PLA "
        "Basic. ABS Basic, ASA Basic y PLA LW no salen porque Orca rechaza sus "
        "perfiles. Un JSON de filamento en perfiles/ manda sobre esta lista."
    ),
    "calidad": (
        "Perfil de proceso de Orca. El número es la altura de capa: menos es "
        "más fino y más lento. Por defecto: «0.20mm Standard». Los tres "
        "perfiles comparten relleno, paredes y soportes (ver las ayudas de abajo)."
    ),
    "altura_capa": (
        "Grosor de cada capa: 0,16 mm (más detalle), 0,20 mm (por defecto) o "
        "0,24 mm (borrador, más rápido). La primera capa va a 0,20 mm en el "
        "perfil de 0,16 y a 0,25 mm en los otros dos, para que agarre a la cama."
    ),
    "relleno": (
        "Interior al 15 % en patrón de rejilla, con 2 paredes, 5 capas macizas "
        "arriba y 3 abajo, en los tres perfiles. La app no lo cambia: para "
        "otra densidad, ábrelo en Orca a mano o deja un perfil en perfiles/."
    ),
    "soportes": (
        "Desactivados en los tres perfiles. La app pide a Orca que oriente y "
        "coloque la pieza sola, y el borde (brim) va en automático. Si la "
        "pieza tiene voladizos grandes, lamínala en Orca con soportes."
    ),
    "temperaturas": (
        "Las pone el material, no la calidad. PLA: boquilla 210 °C (215 °C la "
        "primera capa) y cama 60 °C; PLA Silk: 230 °C. HS PETG: 235 °C y "
        "cama 75 °C; PETG Pro y Transparent: 265 °C. TPU: 225 °C y cama 45 °C."
    ),
    # --- color --------------------------------------------------------------
    "ifs": (
        "El IFS es el cargador de 4 bobinas de la AD5X. Con una pieza de un "
        "color eliges la bobina; con varias, qué bobina saca cada color. Los "
        "colores cargados los da la impresora; si no responde, salen los 4 "
        "canales en gris. Dos colores no pueden ir a la misma bobina."
    ),
    # --- botones ------------------------------------------------------------
    "acciones": (
        "Laminar: Orca convierte el modelo en G-code, sin enviar nada. "
        "Añadir a la cola: lo deja en la cola de la app. Enviar a la "
        "impresora: lo sube y se lanza desde su pantalla. Enviar e imprimir: "
        "lo sube y empieza ya. Solo se envía lo laminado, nunca el STL."
    ),
    # --- galería ------------------------------------------------------------
    "galeria": (
        "Resultados de Thingiverse. Al elegir un modelo salen sus ficheros; "
        "el que traigas se guarda en salida/ y se lamina como uno importado."
    ),
    # --- panel de trabajos --------------------------------------------------
    "t_actual": (
        "Lo que la impresora dice que está haciendo: trabajo, capa y "
        "temperaturas. Se pide al abrir el panel y cada 10 segundos mientras "
        "sigue abierto."
    ),
    "t_cola": (
        "La AD5X solo acepta un trabajo a la vez, así que la cola la lleva "
        "esta app. Se guarda en salida/.cola.json y sobrevive a un reinicio."
    ),
    "t_auto": (
        "La app mira la impresora cada 20 segundos; tras enviar un trabajo "
        "espera 45 segundos antes de volver a mirar. Desactivado, la cola "
        "se queda quieta hasta que lo vuelvas a marcar."
    ),
    "t_limpiar": (
        "Quita de la lista los trabajos hechos o con error. Los pendientes y "
        "los enviados se quedan. No borra ningún fichero."
    ),
    "t_almacenados": (
        "Lista de ficheros que la impresora tiene en su memoria: todo lo que "
        "se le sube desde aquí (enviar, enviar e imprimir o la cola) y lo que "
        "tuviera de antes."
    ),
    "t_salida": (
        "Ficheros de la carpeta salida/ (STL, proyectos y G-code). «Borrar» "
        "quita los que superan la antigüedad elegida. Lo que espera en la "
        "cola no se borra."
    ),
}
