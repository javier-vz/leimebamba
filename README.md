# Camino inca, tramo Leimebamba – Chachapoyas

Optimización inversa de pesos de terreno. La pregunta no es por dónde pasó el
camino —eso ya está registrado— sino **qué variables del terreno explican por
dónde pasó, y si son las mismas a lo largo de todo el tramo**.

Las ecuaciones y el porqué de cada decisión están en [`METODO.md`](METODO.md).
Este archivo es sólo cómo correrlo.

---

## Antes de empezar: cómo está organizado

Descomprime el zip donde guardes tus proyectos. Da igual la ruta exacta, pero
que no tenga espacios ni tildes. Por ejemplo:

- Windows: `C:\proyectos\camino_leimebamba`
- Linux o Mac: `~/proyectos/camino_leimebamba`

Dentro queda esto:

```
camino_leimebamba/
│
├── config.yaml          ← el ÚNICO archivo que vas a editar
├── environment.yml         receta del entorno de conda
├── README.md               este archivo
├── METODO.md               las ecuaciones
│
├── camino/                 el programa (no hace falta abrirlo)
│   ├── descarga.py
│   ├── preparar.py
│   ├── superficies.py
│   ├── hidrologia.py
│   ├── costo.py
│   ├── grafo.py
│   ├── barrido.py
│   ├── metricas.py
│   ├── nulos.py
│   ├── equifinalidad.py
│   ├── pipeline.py
│   ├── config.py
│   └── cli.py
│
├── tests/                  las pruebas
│
├── datos/               ← aquí caen las descargas, solas
│   └── gpx/             ← aquí van los .gpx del Garmin, cuando lleguen
│
├── derivados/           ← aquí caen los rásteres calculados, solos
│
└── resultados/          ← aquí caen las tablas y las figuras, solas
```

Las tres carpetas de abajo (`datos`, `derivados`, `resultados`) empiezan
vacías y **el programa las llena solo**. Tú no bajas ni mueves ningún archivo a
mano, con una sola excepción: los `.gpx` del Garmin, que van a `datos/gpx/`
cuando Dina vuelva del campo.

---

## Paso 1 — Instalar el entorno

Abre la **consola de Anaconda** (en Windows se llama *Anaconda Prompt*; búscala
en el menú de inicio). Métete en la carpeta del proyecto y crea el entorno:

```bash
cd C:\proyectos\camino_leimebamba
conda env create -f environment.yml
conda activate camino
```

Eso instala numpy, scipy, rasterio, geopandas y lo demás. Tarda unos minutos la
primera vez y no hay que repetirlo nunca más.

Comprueba que quedó bien:

```bash
python -m pytest -q
```

Tienen que pasar 123 pruebas en dos o tres segundos. Si algo falla aquí, falla
antes de tocar datos, que es cuando conviene que falle.

> **Cada vez que abras la consola de nuevo** hay que repetir dos cosas:
> `conda activate camino` y `cd` a la carpeta del proyecto. Si Python dice que
> no encuentra un paquete, casi siempre es que falta el `conda activate`.

No hace falta QGIS, ni ArcGIS, ni GRASS, ni escribir comandos de GDAL. El
programa hace la reproyección, el recorte, la hidrología y el grafo en Python.
QGIS sólo sirve al final, para mirar los resultados en un mapa.

---

## Paso 2 — Conseguir la llave de OpenTopography

Es gratis e inmediata, y sirve para que el programa pueda bajar los dos modelos
de elevación.

1. Entra a <https://portal.opentopography.org/>
2. Créate una cuenta (o entra si ya tienes).
3. Ve a **My Account** y pide una *API key*. Te la dan en el momento: es una
   cadena larga de letras y números.

Ahora dísela a la consola. Escribe esto en la **misma ventana** donde vas a
trabajar, cambiando `pega_aqui_tu_llave` por la tuya:

```bash
set OPENTOPOGRAPHY_API_KEY=pega_aqui_tu_llave
```

En Linux o Mac es `export` en lugar de `set`:

```bash
export OPENTOPOGRAPHY_API_KEY=pega_aqui_tu_llave
```

Ojo: eso dura sólo mientras la ventana esté abierta. Si cierras la consola, hay
que volver a escribirlo. Se hace así, y no se guarda en un archivo, para que la
llave no acabe subida al repositorio sin querer.

---

## Paso 3 — La dirección de GeoCAM (ya viene puesta)

GeoCAM publica sus capas bajo el **estándar OGC**: es la sección «Servicios
web» de su página, con los iconos de WMS, WFS y KML. El WFS es el que
devuelve los vectores, y es la vía por la que entra el programa — una
interfaz documentada y estable, no una dirección sacada a mano del tráfico
del navegador.

El servidor es un GeoServer en `geoservicios.cultura.gob.pe`, y **el endpoint
ya viene escrito en `config.yaml`**:

```yaml
datos:
  geocam_wfs: "https://geoservicios.cultura.gob.pe/geoserver/wfs"
```

Así que en principio no tienes que tocar nada aquí. Sólo falta saber cuál de
las capas publicadas es la del camino, y eso lo averigua el programa:

```bash
python -m camino buscar
```

Lista las capas del WFS, las ordena de más a menos probable y escribe la
primera en la línea `geocam_capa` de `config.yaml`. Si funciona, pasa al
paso 4.

### El error 500: es del Ministerio, no tuyo

Ese servidor está detrás de un proxy que falla a ratos. Lo que sale es esto:

> **Proxy Error** — The proxy server could not handle the request
> `GET /geoserver/cultura/ows`.
> Reason: **Error during SSL Handshake with remote server**

Eso **no es un error de tu petición**: es el proxy del Ministerio, que no
consigue hablar con su propio GeoServer. Comprobado desde fuera: falla igual,
y de forma intermitente — la misma dirección contesta un minuto y falla al
siguiente. También cambia según la ruta: cuando `/geoserver/cultura/ows` da
500, `/geoserver/wfs` a veces responde.

Por eso el programa, en lugar de rendirse al primer intento:

- prueba cuatro rutas distintas del servidor, empezando por la más fiable;
- reintenta cada petición con espera creciente;
- y repite el barrido entero una segunda vez antes de darse por vencido.

Si aun así dice que ningún endpoint respondió, está caído de verdad. Espera
un rato y vuelve a correr `python -m camino buscar`. No hay nada que arreglar
de tu lado.

### Si GeoCAM no vuelve: el camino puede venir de otro sitio

El servidor del Ministerio se cae, y cuando se cae no hay nada que hacer
desde aquí. El resto del estudio no tiene por qué quedarse parado: el camino
observado puede entrar desde tres sitios.

```bash
python -m camino ruta                                  # de GeoCAM (lo correcto)
python -m camino ruta --fuente archivo --archivo X.shp # de un archivo tuyo
python -m camino ruta --fuente osm                     # apaño provisional
```

**Un archivo tuyo** es la salida más práctica mientras tanto. Vale un
shapefile, un KML, un GeoPackage, un GeoJSON o un GPX; el programa lo
reproyecta y lo recorta solo. Tres formas de conseguir uno:

- **GEO GPS PERÚ** publica el Qhapaq Ñan nacional en shapefile y KMZ,
  descarga directa desde Google Drive:
  <https://www.geogpsperu.com/2020/10/mapa-del-qhapaq-nan-camino-inca.html>
  Ojo: la página no dice de qué año es ni de dónde salió exactamente. Sirve
  para trabajar ya, pero antes de publicar hay que contrastarlo con GeoCAM.
- **Los tracks de Dina**, cuando vuelva del campo. El `.gpx` del Garmin entra
  directo: `python -m camino ruta --fuente archivo --archivo datos/gpx/dia1.gpx`
- **Digitalizarlo tú** en QGIS sobre una imagen satelital y guardarlo como
  GeoPackage.

**OpenStreetMap** (`--fuente osm`) baja las trazas etiquetadas como
`historic` o con «inca» / «qhapaq» en el nombre. Es un **apaño** para que el
código corra de punta a punta: son trazas de voluntarios, sin control de
precisión ni criterio arqueológico. El programa las marca como
`osm_provisional` y te lo recuerda al terminar. No valen para publicar.

**Y mientras tanto, sigue trabajando.** Los tres primeros pasos no necesitan
el camino para nada:

```bash
python -m camino bajar
python -m camino preparar
python -m camino superficies
```

Son los que más tardan —las descargas, el relleno de depresiones, la
acumulación de flujo— y dejan todo listo. Si al correr `preparar` todavía no
hay camino, usa la caja entera como dominio y te lo dice. A partir de
`grafo` sí hace falta.

### La última opción: sacar la dirección del tráfico del navegador

Sólo si GeoCAM vuelve a estar en pie pero `buscar` no la encuentra. Es lo más
engorroso y por eso va al final.

**Para abrir el panel de desarrollo.** El atajo habitual es `F12`, pero en
muchos portátiles —ASUS entre ellos— esa tecla la tiene tomada el fabricante
y abre su propia utilidad. Tres alternativas:

- **`Ctrl` + `Shift` + `I`** — funciona en Chrome, Edge y Firefox y no depende
  de las teclas F. Es la que conviene usar.
- **`Fn` + `F12`** — si tu teclado tiene las teclas F en modo multimedia.
  (`Fn` + `Esc` suele alternar los dos modos de forma permanente.)
- **Por menú, sin atajos** — en Chrome o Edge: los tres puntos de arriba a la
  derecha → *Más herramientas* → *Herramientas para desarrolladores*. En
  Firefox: el menú ☰ → *Más herramientas* → *Herramientas para
  desarrolladores*.

**Y luego:**

1. Abre <https://geocam.cultura.gob.pe/> con el panel abierto al lado.
2. En el panel, pestaña **Network** (en español, **Red**).
3. En la casilla de filtro escribe `query`.
4. Acércate a Chachapoyas en el mapa, hasta que se dibujen las capas del
   camino. En el panel irán apareciendo líneas: son las peticiones que el
   visor le hace a su servidor.
5. Clic derecho sobre una de ellas → *Copy* → *Copy URL*.
6. Pégala en un bloc de notas y **recorta todo desde `/query` en adelante**,
   el `/query` incluido. Te queda algo así:

   ```
   https://geocam.cultura.gob.pe/server/rest/services/QhapaqNan/MapServer/2
   ```

7. Eso va en `config.yaml`, en la línea `geocam_servicio`.

### Las tres líneas de config.yaml, para ubicarte

```yaml
datos:
  api_key_opentopography: ""     # vacía: la llave va en la consola (paso 2)

  geocam_wfs: "https://geoservicios.cultura.gob.pe/geoserver/wfs"
  geocam_capa: ""                # la rellena `python -m camino buscar`

  geocam_servicio: ""            # sólo si el WFS no vuelve
```


## Paso 4 — Correr el estudio

Nueve comandos, en este orden. Cada uno deja su resultado en disco, así que
puedes parar y seguir otro día sin perder nada.

```bash
python -m camino bajar
python -m camino geocam
python -m camino preparar
python -m camino superficies
python -m camino grafo
python -m camino revisar
python -m camino nulos
python -m camino barrido
python -m camino resultados
```

O todos de corrido con `python -m camino todo`.

### Qué hace cada uno y qué archivo deja

| Comando | Qué hace | Qué escribe |
|---|---|---|
| `bajar` | baja los dos modelos de elevación y los cuerpos de agua | `datos/cop30_raw.tif`, `datos/aw3d30_raw.tif`, `datos/agua_osm.json` |
| `geocam` | trae el camino registrado del servidor del Ministerio | `datos/qn_geocam.gpkg` |
| `preparar` | pone los dos modelos en la misma rejilla y recorta el corredor | `derivados/cop30.tif`, `derivados/aw3d30.tif`, `derivados/mascara.tif` |
| `superficies` | calcula pendiente, rugosidad, drenaje y humedad | `derivados/phi_rugosidad.tif`, `derivados/phi_drenaje.tif`, … |
| `grafo` | arma el grafo de tránsito sobre el terreno | `derivados/grafo.npz` |
| `revisar` | traza **un** camino para que lo mires | `resultados/revision_pendiente.gpkg` |
| `nulos` | genera el terreno aleatorio de comparación | `derivados/nulos.npz` |
| `barrido` | prueba los 231 juegos de pesos, sector por sector | `resultados/optimos_por_sector.json` |
| `resultados` | el perfil de equifinalidad y su gráfico | `resultados/perfil_equifinalidad.png` |

### Dos advertencias sobre el orden

**`nulos` va antes de `barrido`, y no es intercambiable.** Un sector cuyo mejor
camino no le gana a terreno aleatorio no tiene pesos que valga la pena
reportar. Si se corre al revés, se acaba comparando pesos de sectores donde el
modelo no explica nada, y los números parecen válidos aunque no lo sean.

**`revisar` es el paso que no se salta.** Traza un solo camino, poniendo todo el
peso en la pendiente, y lo guarda en `resultados/revision_pendiente.gpkg`.
Ábrelo en QGIS encima del modelo de elevación y míralo con ojos de arqueóloga:
¿pasa por donde pasaría un camino?, ¿cruza una quebrada por donde se puede
cruzar? Si ese camino no es plausible, ninguno de los que vienen después lo
será, y no hay estadística que lo arregle.

---

## Lo primero que hay que mirar

Al final de `python -m camino geocam`, el programa imprime cuántos metros de
**polilínea continua** trajo de GeoCAM. Es el número que decide el diseño del
estudio, y conviene mirarlo antes de seguir:

- Si hay bastante camino continuo, se puede partir en sectores **y** validar en
  bloques: ajustar los pesos en los sectores pares y medir qué tan bien
  predicen los impares.
- Si hay poco, las dos cosas compiten por los mismos metros, y hay que elegir
  una. Esa decisión se toma **antes** de correr el barrido, no después de ver
  los resultados.

Si el tramo continuo más largo baja de unos 15 km, el programa lo avisa en
pantalla.

---

## Los parámetros que vas a querer cambiar

Todos viven en `config.yaml`, cada uno con su comentario explicando qué hace.
Si un umbral aparece escrito dentro del código del programa, es un error.

Tres que probablemente toques:

**`componentes`** — qué variables del terreno entran al modelo.

```yaml
costo:
  componentes: [pendiente, rugosidad, drenaje]
```

Con esas tres son 231 juegos de pesos y el barrido tarda media hora. Si añades
`humedad`, pasan a ser 1771 y tarda unas dos horas. Empieza con tres.

**`buffer_corredor`** — media anchura, en metros, de la franja alrededor del
camino registrado por donde el modelo tiene permitido buscar.

```yaml
dominio:
  buffer_corredor: 4000
```

Existe por una razón de cómputo: el área completa son tres millones y medio de
celdas y no se pueden barrer. Pero si la franja es muy estrecha, es ella la que
decide el resultado. Por eso `revisar` comprueba si el camino modelado se pegó
al borde, y si avisa, hay que ensanchar este número y volver a correr desde
`preparar`.

**`umbral_quebrada`** — cuántas celdas de área drenada hacen que una celda
cuente como quebrada.

```yaml
dominio:
  umbral_quebrada: 500
```

500 celdas son 0.45 km² a 30 m de resolución. Es el único parámetro de todo el
modelo que el trabajo de campo fija directamente: se calibra contra las
quebradas que realmente haya que cruzar en el tramo.

---

## Los tracks del GPS

Todavía no están: Dina camina del 8 al 15 de octubre. **Nada del pipeline se
bloquea por eso.** Los tracks entran en la validación, al final; hasta que
lleguen, el modelo se ajusta contra la geometría de GeoCAM sola, y todos los
pasos de arriba corren igual.

Cuando lleguen: conecta el Garmin por USB, entra a la carpeta
`Garmin/Activities` del reloj y copia los `.gpx` a `datos/gpx/`. (También se
pueden exportar uno por uno desde Garmin Connect.) El programa los lee de ahí,
descarta los puntos con mala precisión y los tramos que van demasiado rápido
para ser alguien caminando.

---

## Datos sensibles

Las coordenadas de evidencias arqueológicas sensibles o no publicadas que
vengan de GeoCAM o de los tracks **no entran al repositorio público**. El
archivo `.gitignore` ya excluye `datos/` y `derivados/` justamente por eso, y
todo lo que hay en esas carpetas se puede regenerar corriendo los pasos otra
vez, así que no se pierde nada por no versionarlas.

Lo que se publique tiene que pasar antes por las restricciones institucionales
que correspondan.

---

## Si algo sale mal

| Lo que dice la consola | Qué pasa |
|---|---|
| `ModuleNotFoundError` | falta `conda activate camino` |
| `Falta la llave de OpenTopography` | el `set OPENTOPOGRAPHY_API_KEY=...` del paso 2, en esta misma ventana |
| `Falta la dirección de GeoCAM` | el paso 3; el propio mensaje repite las dos vías |
| `Proxy Error … SSL Handshake` | el proxy del Ministerio, caído a ratos. No es tuyo: espera y repite `python -m camino buscar` |
| `Ningún endpoint WFS respondió` | lo mismo: el servidor está caído en este momento. El programa ya probó cuatro rutas, dos veces |
| `El WFS publica N capas pero ninguna parece ser el camino` | mira la lista que imprime `buscar` y pon a mano la que reconozcas en `geocam_capa` |
| `no tiene nada dentro de la caja del tramo` | bajó una capa que no es la del camino, o el tramo no está digitalizado ahí. Prueba la 2ª o 3ª capa de la lista de `buscar` |
| `el camino modelado toca el borde del corredor` | sube `buffer_corredor` en `config.yaml` y vuelve a correr desde `preparar` |
| `la pieza continua mide X m` | hay muy poco camino continuo para el número de sectores pedido: baja `n_sectores` en `config.yaml` |

---

## Por qué no se usa un GIS para esto

- `r.cost` de GRASS es isotrópico: no distingue subir de bajar.
- `r.walk` sí distingue, pero tiene su propia función de marcha cableada por
  dentro y no admite pesos elegidos por el usuario.
- `MCP_Geometric` de scikit-image es isotrópico.
- QGIS no trae nada equivalente.

Ninguno permite recorrer sistemáticamente juegos de pesos sobre un costo que
distinga el sentido de la marcha, que es exactamente lo que pide la pregunta.
De ahí el programa: numpy y scipy, sin dependencias raras.
