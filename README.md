# Taller AD5X

App local para pasar de una idea a una pieza impresa en la Flashforge AD5X sin
tocar el slicer a mano: eliges una pieza del catálogo, ajustas sus cotas, y la
app genera el STL, lo lamina y lo manda a la impresora por red.

```bash
.venv\Scripts\python.exe run.py
```

Abre `http://127.0.0.1:8099` solo, **cuando el servidor responde de verdad**:
importar CadQuery lleva sus segundos y abrir el navegador antes daba un
«127.0.0.1 rechazó la conexión» que parecía una avería. `run.py` sondea el
puerto y espera.

## Cómo funciona

```
piezas/*.py  →  CadQuery  →  STL  →  Orca (CLI)  →  .gcode  →  .3mf  →  AD5X
 catálogo      ad5x/cad     salida/   ad5x/slicer          ad5x/pack   8898
```

**Por qué ese `.3mf` al final.** Medido contra la impresora el 18-10: un
`.3mf` aparece en su lista de ficheros en unos 5 segundos, mientras que un
`.gcode` suelto puede tardar minutos o no llegar a aparecer, aunque la API
responda `Success` a los dos. Todos los ficheros propios de la impresora son
`.3mf`. Así que `ad5x/pack.py` envuelve el G-code en ese contenedor antes de
mandarlo, y el envío tarda unos 3 segundos de principio a fin.

Después de subir, la app **comprueba que el fichero está en la lista** antes de
decir que llegó, reintentando unos segundos porque la impresora tarda en
indexarlo.

Que un fichero se liste no significa que se pueda abrir: un contenedor
incompleto se acepta, aparece, y da **error de archivo** al elegirlo en la
pantalla. Por eso `pack.py` escribe todo lo que el firmware comprueba:

| Dentro del .3mf | Para qué |
|---|---|
| `Metadata/plate_1.gcode` | el trabajo |
| `Metadata/plate_1.gcode.md5` | checksum que el firmware verifica |
| `Metadata/slice_info.config` | tiempo, peso y filamentos del trabajo |
| `Metadata/plate_1.json` | posición en la cama, altura de capa, boquilla |
| `Metadata/plate_*.png` | vista previa; sin ella algunos firmwares fallan |
| `[Content_Types].xml`, `_rels/.rels`, `3D/3dmodel.model` | el envoltorio OPC |

El tiempo va en segundos (`prediction`) y el peso se calcula del volumen por
1,24 g/cm³, porque el perfil de Flashforge declara densidad 0 y el G-code
reporta 0 g.

### Por qué el contenedor es tan detallado

Un contenedor incompleto **se sube y se lista, pero la impresora da «error de
archivo» al abrirlo**. Costó dos intentos dar con la pieza que faltaba:
`Metadata/model_settings.config`, que es lo que apunta al G-code dentro del
paquete (`gcode_file`). Sin ese fichero el firmware no sabe qué imprimir.

La estructura se sacó de un fichero que generó el propio Orca con *Exportar
los objetos laminados de la bandeja a un archivo*, y está guardada en
`distribucion/plantilla-3mf/` junto al original de referencia. De ahí salen
las miniaturas y `project_settings.config`, que describen la máquina y no el
trabajo; el resto lo genera `pack.py` para cada pieza.

La extensión importa: Orca los llama `.gcode.3mf` y la app hace lo mismo.

### El modo LAN, y lo que cuesta

La API local **solo escucha con el modo LAN activo**. Sin él la impresora
responde al ping pero no tiene ningún puerto abierto, que es justo lo que
pasaba aquí el 18-10 con la dirección que tenía entonces.

La contrapartida, del propio manual: **con el modo LAN activo la app Flash
Maker deja de controlarla por internet**. Es uno u otro, así que decide qué
prefieres antes de cambiarlo.

Los códigos de verificación pueden caducar: si un día deja de responder con
las credenciales buenas, vuelve a leerlo en la pantalla.

### La IP no importa

La AD5X responde a un broadcast UDP en el puerto 19000 **aunque el modo LAN
esté desactivado y el 8898 cerrado**. Sobre eso se apoyan dos cosas.

La primera: **la dirección del `.env` es solo una pista**. Si el router le da
otra al encenderla, la app lo nota al primer fallo de conexión, la busca, y
repite la llamada en la nueva dirección sin que te enteres. Luego se queda con
la que funcionó. Lo que identifica a la impresora es el **número de serie**, no
la IP: entre las que respondan al descubrimiento, solo acepta la que valide tu
serie y tu código, así que dos impresoras en la misma red no se confunden.

La segunda: los mensajes dejan de ser un «no responde» a secas. El
descubrimiento distingue una impresora apagada de una encendida sin modo LAN,
y de una que simplemente se ha mudado de dirección.

Y cuando no aparece por ningún lado, la app compara su propia dirección con la
última conocida de la impresora: si los rangos no coinciden lo dice tal cual
(*«tu equipo está en la red 172.20.10.x y la impresora estaba en 192.168.1.x»*),
porque la causa más común no es que la impresora falle, sino que el portátil se
ha ido a los datos del móvil o a otra wifi.

Para no depender de nada de esto, también puedes darle una **reserva DHCP** en
el router, atándole siempre la misma IP por su MAC. Es lo más limpio si tienes
acceso al router, pero ya no hace falta.

`pruebas/test_reconexion.py` comprueba todo esto con una impresora simulada,
que es precisamente lo que hace falta cuando la de verdad está apagada.

### Cuando algo no conecta

```bash
.venv\Scripts\python.exe comprobar_impresora.py
```

Comprueba por orden el `.env`, el ping, el puerto, las credenciales y el
estado, y se para en el primero que falla diciendo qué hacer.

## Perfiles de laminado

No hay que exportar nada: la app usa **los perfiles que Orca-Flashforge trae
para la AD5X**, que ya vienen afinados por el fabricante. En la web eliges
material (20 filamentos: PLA Basic, Matte, Silk, PETG, ABS, ASA, TPU, los CF…)
y calidad (0,16 / 0,20 / 0,24 mm). La boquilla asumida es la **0,4 de serie**;
los perfiles de 0,25, 0,6 y 0,8 también están instalados, y se eligen con el
argumento `nozzle` de `slice_stl()`.

Si algún día quieres perfiles propios, los `.json` que dejes en `perfiles/`
tienen prioridad sobre los del fabricante. Un fichero cuyo nombre contenga
`filament` va como filamento; el resto, como máquina y proceso. Se exportan
desde el propio Orca con *File > Export > Export preset*.

Instalado en este equipo: **Orca-Flashforge 1.6.2**, en
`C:\Program Files\Flashforge\Orca-Flashforge\`. La app lo encuentra sola; solo
hace falta `SLICER_EXE` en el `.env` si lo mueves de sitio.

## Detalles que conviene saber

**Solo HTTP, nunca el puerto 8899.** La AD5X también habla un protocolo TCP en
8899, pero admite una sola sesión y una segunda conexión puede dejar el firmware
colgado hasta apagar la impresora físicamente. Este código no lo toca.

**Las piezas son código que se ejecuta.** `piezas/*.py` se importa y se ejecuta
tal cual, por eso el servidor escucha solo en `127.0.0.1`. No lo expongas a la
red ni pongas ahí ficheros de terceros sin leerlos.

**Avisos al generar.** La app comprueba que la pieza cabe en los 220 mm de cama
y que no hay paredes por debajo de 0,8 mm (dos perímetros de una boquilla de
0,4). Avisa, no bloquea: tú decides.

**La tapa y las piezas múltiples** salen separadas en la misma placa, ya con
hueco entre ellas.

## Llaveros y anillos

Dos piezas que se llevan puestas, y por eso tienen reglas propias.

**El llavero** (`piezas/llavero.py`) va en cuatro formas: placa, pastilla,
círculo y corazón. La placa y la pastilla se dimensionan solas a partir del
texto; el círculo y el corazón van al tamaño que pidas y es el texto el que se
encoge para caber dentro. La anilla **no es un agujero hecho en la chapa**,
sino un aro que sale por fuera con su propio grosor alrededor: un taladro en
el borde de una chapa de 3 mm se rompe al primer tirón, y es justo la parte
que más sufre. El aro se mete unos milímetros dentro de la chapa para que
suelden en un solo sólido, y en el corazón apunta al **valle entre los
lóbulos**, no a lo alto de la caja: si no, quedaría colgando del pico de uno
de los dos.

**El anillo** (`piezas/anillo.py`) se mide de dos maneras, porque la gente usa
las dos: el diámetro interior en milímetros, o la **talla española**, que es
el contorno interior en milímetros menos 40 (talla 12 = 52 mm de contorno =
16,55 mm de diámetro). La conversión es `(talla + 40) / π`. Se imprime de pie,
con el eje en Z: así cada capa es un anillo cerrado y la pieza aguanta el
esfuerzo de ponérsela, que es el que la parte. A la medida se le suma una
**holgura** de 0,3 mm por defecto; el PLA no da de sí, conviene imprimir uno
de prueba antes de hacer la serie.

El sello es una chapa plana tangente a la banda, arraigada dentro de ella.
Trampa que cuesta ver hasta que lo tienes impreso: para pasar un texto del
plano XY a una cara vertical **no basta con girarlo 90° sobre X**. Esa sola
rotación lo deja cabeza abajo, y la que lo endereza lo deja en espejo. La
buena es girar 90° sobre X y después 180° sobre Z.

## Trabajos y cola

El botón **Trabajos** de la cabecera abre un panel con tres cosas: lo que la
impresora está haciendo ahora (fichero, capa X de Y, cuánto le queda,
temperaturas), la **cola** de la app, y los ficheros guardados en la máquina.

La AD5X acepta **un trabajo cada vez**: no se puede encolar en ella. Así que la
cola la lleva la app (`ad5x/cola.py`), en un JSON dentro de `salida/` para que
sobreviva a cerrar la ventana. Un hilo vigilante mira cada 20 s y, cuando la
impresora queda libre, manda el siguiente y lo lanza. Se puede desactivar con
«Lanzar sola» y entonces la cola es solo una lista de espera.

Ese vigilante usa una comprobación barata (`free_for_work`) que **no** sale a
buscar la impresora por la red: preguntando cada 20 s, un barrido cada vez
sería absurdo. Si la dirección ha caducado, la arregla la siguiente llamada de
verdad.

El progreso se mide **por capas**, no por el `printProgress` de la impresora,
que va muy retrasado: marcaba 0,4 % cuando iba por la capa 22 de 72.

## Elegir el color

La impresora dice qué bobina hay en cada bahía del IFS (`matlStationInfo` en
`/detail`), con su color real. La app lo pinta como muestras: eliges una y la
pieza sale entera de ese color.

Por dentro es el mismo mecanismo que el multicolor: se manda la herramienta 0
del G-code apuntando al canal que has elegido. Por eso no hay que volver a
laminar para cambiar de color — basta con elegir otra bobina y enviar.

## Piezas de dos colores

Una pieza del catálogo puede devolver **partes con nombre** en vez de un solo
sólido, y entonces cada una se imprime con su bobina. Lo hacen la **caja**
(cuerpo y tapa), la **placa con texto**, el **llavero** y el **anillo** (la
pieza y sus letras), marcando la casilla correspondiente. En la web aparecen luego en «Canales del IFS», una fila por
parte, para decir en qué bahía está cada color.

Costó dar con la receta, y conviene dejarla escrita:

- Orca **no** asigna colores desde la línea de órdenes. Hay que dárselos
  dentro de un proyecto `.3mf`.
- No vale cualquier 3MF: tiene que ser un objeto con varias `<part>`, cada una
  con su `extruder`, y la geometría en un fichero aparte bajo `3D/Objects/`
  al que el modelo principal apunta con `p:path`. Lo escribe `ad5x/proyecto.py`,
  copiando la estructura de un proyecto real de Orca que está guardado en
  `distribucion/plantilla-3mf/_referencia-dos-colores.3mf`.
- Sin `Metadata/project_settings.config` dentro, el laminador **revienta con
  segfault**. Y ese fichero lleva su propio perfil de material, que gana a lo
  que pases por la línea de órdenes: sin tocarlo, una pieza de dos colores se
  imprimiría con el perfil de la plantilla (ABS a 240°) aunque hubieras
  elegido PLA. Por eso `ad5x/perfiles.py` resuelve la herencia del filamento
  elegido y lo inyecta en el proyecto antes de laminar.
- Al inyectarlo hay que **respetar la forma de cada clave**: unas son listas
  con un valor por extrusor y otras texto suelto, y confundirlas da
  «type must be string, but is array».

**Tres materiales no se ofrecen** aunque Orca los traiga: ABS Basic, ASA Basic
y PLA LW tienen el perfil sin la clave `type` y el laminador los rechaza. La
app los filtra para no ofrecerte algo que va a fallar.

## Multicolor con el IFS

El catálogo lamina a un color: Orca por línea de órdenes no asigna extrusores
por pieza, eso se hace en la interfaz de Flash Studio. Lo que sí hace la app es
**mandar cualquier G-code multicolor con sus canales bien asignados**:

1. Lamina el multicolor en Flash Studio y guarda el fichero.
2. En el catálogo, **«Traer fichero»** y elígelo. Vale `.gcode` y `.3mf`: de un
   3MF se saca el G-code de dentro (`Metadata/plate_1.gcode`) para leerlo.
3. Aparece **Canales del IFS**, una fila por color, leídos del propio fichero,
   con las bobinas reales de la impresora en cada desplegable.
4. Di en qué canal está cada bobina y envía.

Si el 3MF es un proyecto sin laminar, la app lo dice y no deja enviarlo.

El número que Orca pone junto a un color **no** es el canal del IFS — es solo
un orden, como avisa el manual. Por eso hay que decirlo aquí.

Dos colores apuntando al mismo canal bloquean el envío, en el navegador y otra
vez en el servidor. El mapeo viaja como `materialMappings` (base64 en la
cabecera al subir, JSON al lanzar), con `useMatlStation` y `gcodeToolCnt`.

Un detalle de la especificación: la cabecera de `/uploadGcode` dice llevar solo
`{toolId, slotId}` mientras su propio esquema exige cinco campos. Mandamos los
cinco; un firmware que quiera la forma corta ignorará los demás.

## Cómo se actualiza el otro ordenador

El paquete portátil pesa unos 537 MB, pero de eso el **programa son 170 KB**:
el resto es el intérprete de Python con CadQuery dentro y los modelos
descargados, y ninguna de las dos cosas cambia cuando se añade una pieza.
Pasar medio giga por un pendrive para mover 170 KB es lo que había que
dejar de hacer.

Así que el código vive en un repositorio público,
`github.com/scg1004-lab/impresora-3d`, y el paquete se pone al día solo:
`ad5x/actualizar.py` corre al arrancar, pregunta a la API de GitHub por el
sha del último commit (una respuesta de 40 bytes), y si no coincide con el
que tiene guardado en `.version` se baja el ZIP de **ese commit** y reemplaza
el código. Un segundo. Quien lo usa no se entera de nada: sigue dando doble
clic y abriéndose el navegador.

Reglas del diseño, por orden de importancia:

- **Solo se actualiza el paquete portátil**, nunca el equipo donde se
  programa. Se distingue por la carpeta `py\`, que solo existe en el
  paquete. Sin esa regla, arrancar la app aquí antes de hacer push
  machacaría el código sin subir con el de GitHub.
- **`comprobar()` no levanta excepciones. Ninguna.** Es su contrato, y está
  envuelta entera para cumplirlo. Arrancar tiene que funcionar aunque la
  actualización no, porque el ordenador que la recibe está lejos de quien
  escribió el fallo.
- **Nunca existe un instante con el código a medio poner.** Lo nuevo se
  extrae a `.nuevo/`, se valida allí, y el cambio son dos `os.replace()` por
  elemento: lo que había se renombra al respaldo, lo nuevo se renombra a su
  sitio. Renombrar es atómico. Si algo falla, se deshace renombrando al
  revés.
- **Se comprueba que el código nuevo arranca**, no solo que compile: se
  lanza `py\python.exe -c "import ad5x.web"` en un subproceso contra el
  árbol recién extraído. Compilar solo caza erratas de sintaxis; lo que de
  verdad rompe una actualización es un módulo que ya no está.
- **Solo se reemplaza código**: `ad5x/`, `piezas/`, `web/`, `pruebas/` y un
  puñado de ficheros sueltos. Ni `py/`, ni `modelos/`, ni `salida/`, ni
  `perfiles/`, ni el `.env`. Y las piezas que haya escrito quien usa el
  programa se rescatan del respaldo: una actualización no puede llevarse por
  delante el trabajo de nadie.

Al extraer no se usa `extractall`: se filtran los miembros uno a uno
(`_contenido`), descartando rutas absolutas, con `..`, con dos puntos en
cualquier tramo —un `web.py:oculto` escribe un flujo alterno de NTFS que
luego no se ve— o fuera de las carpetas conocidas, y se comprueba otra vez
con `is_relative_to` antes de escribir cada fichero. Es nuestro propio ZIP,
pero llega por la red, y volcar a ciegas lo que llega por la red es cómo se
acaban escribiendo ficheros donde no se debe.

Dos detalles que parecen quisquillosos y no lo son. Se descarga
`/zip/<sha>`, no `/zip/refs/heads/main`: entre preguntar la versión y
bajarla puede entrar otro push, y acabarías instalando algo distinto de lo
que comprobaste; además se exige que la carpeta raíz del ZIP sea exactamente
`impresora-3d-<sha>`. Y las redirecciones no se siguen a ciegas: urllib
acepta por su cuenta hasta diez saltos a cualquier host, `http` pelado
incluido, así que `_SoloGitHub` rechaza todo lo que no sea HTTPS contra
GitHub.

**Nada de esto estaba en la primera versión.** Se escribió con un `rmtree`
seguido de escribir encima, y el revisor de seguridad la tumbó con dos
fallos reproducidos: `http.client.IncompleteRead` no hereda de `OSError`,
así que una descarga cortada —y codeload responde troceado— se escapaba del
`except` y reventaba el arranque; y el propio rescate podía lanzar
`FileExistsError` si el antivirus tenía un fichero abierto, dejando el
código a medio borrar y el programa sin abrir. Los 15 casos de
`pruebas/test_actualizador.py` existen para que no vuelvan.

El repositorio es **público a propósito**: así el portátil se actualiza sin
credencial ninguna. Uno privado obligaría a guardar un token de lectura
dentro del paquete —una credencial en el portátil de una niña, que además
caduca—, y no compraría nada: lo que hay que proteger aquí es la
integridad, no el secreto. Quien pueda hacer push a `main` ejecuta código en
ese portátil, y eso no cambia porque el repositorio esté oculto. La
seguridad de esto es la de la cuenta de GitHub: 2FA y protección de rama.
En el repositorio no hay nada que esconder: el `.env` con el check code y el
número de serie, la última IP, los modelos descargados y el ZIP construido
están todos en `.gitignore`, y `pruebas/test_publicacion.py` lo comprueba
fichero por fichero antes de cada subida, mirando también dentro de los que
son ZIP.

`empaquetar.py` escribe la marca `.version` con el commit que lleva el
paquete, pero **solo si el árbol está limpio**: con cambios sin subir, el
paquete y lo publicado no son lo mismo, y una marca mentiría diciendo que
está al día. Sin marca, simplemente se actualiza en el primer arranque.

## API

| Ruta | Qué hace |
|---|---|
| `POST /api/build` | `{slug, values}` → genera el STL |
| `POST /api/slice` | `{file}` → lamina con Orca |
| `POST /api/send` | `{file, print_now}` → sube a la impresora y, opcionalmente, la lanza |
| `GET /api/printer` | Estado de la impresora |

## Referencias

- Endpoints de la impresora: [Parallel-7/flashforge-api-docs](https://github.com/Parallel-7/flashforge-api-docs) (AD5X, firmware 1.2.1)
- [CLI de OrcaSlicer](https://www.orcaslicer.com/wiki/cli/cli_mode)
- [Documentación de CadQuery](https://cadquery.readthedocs.io/)
