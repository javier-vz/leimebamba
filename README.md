# Camino inca, tramo Leimebamba – Chachapoyas

La pregunta no es por dónde pasó el camino —eso ya está registrado— sino
**qué variables del terreno explican por dónde pasó, y si son las mismas a lo
largo de todo el tramo**.

Este archivo es cómo correrlo. Las ecuaciones y el porqué de cada decisión
están en [`METODO.md`](METODO.md).

---

## Contenido

1. [Cómo está organizada la carpeta](#1-cómo-está-organizada-la-carpeta)
2. [Instalar el entorno](#2-instalar-el-entorno-una-sola-vez)
3. [La llave de OpenTopography](#3-la-llave-de-opentopography-una-sola-vez)
4. [Correr el estudio](#4-correr-el-estudio)
5. [El camino observado: de dónde sale](#5-el-camino-observado-de-dónde-sale)
6. [Qué mirar en los resultados](#6-qué-mirar-en-los-resultados)
7. [Los parámetros](#7-los-parámetros)
8. [Si algo falla](#8-si-algo-falla)

---

## 1. Cómo está organizada la carpeta

Descomprime el zip donde guardes tus proyectos, en una ruta sin espacios ni
tildes. Por ejemplo `C:\proyectos\camino_leimebamba`.

```
camino_leimebamba/
│
├── config.yaml          ← el único archivo que vas a editar
├── environment.yml         receta del entorno de conda
├── README.md               este archivo
├── METODO.md               las ecuaciones
│
├── camino/                 el programa (no hace falta abrirlo)
├── tests/                  las pruebas
│
├── datos/               ← aquí caen las descargas, solas
│   └── gpx/             ← aquí van los .gpx del Garmin, cuando lleguen
├── derivados/           ← aquí caen los rásteres calculados, solos
└── resultados/          ← aquí caen las tablas y las figuras, solas
```

Las tres carpetas de abajo empiezan vacías y **el programa las llena solo**.
No tienes que bajar ni mover ningún archivo a mano, con una excepción: los
`.gpx` del Garmin, que van a `datos/gpx/` cuando Dina vuelva del campo.

---

## 2. Instalar el entorno (una sola vez)

Abre la **consola de Anaconda** (en Windows, *Anaconda Prompt*; búscala en el
menú de inicio). Entra a la carpeta y crea el entorno:

```bash
cd C:\proyectos\camino_leimebamba
conda env create -f environment.yml
conda activate camino
```

Tarda unos minutos la primera vez. Comprueba que quedó bien:

```bash
python -m pytest -q
```

Tienen que pasar **214 pruebas** en dos o tres segundos. Si falla algo aquí,
falla antes de tocar datos, que es cuando conviene.

> **Cada vez que abras la consola de nuevo**, dos cosas: `conda activate
> camino` y `cd` a la carpeta del proyecto. Si Python dice que no encuentra un
> paquete, casi siempre es que falta el `conda activate`.

No hace falta QGIS, ArcGIS, GRASS ni comandos de GDAL. El programa hace la
reproyección, el recorte, la hidrología y el grafo en Python. QGIS sólo sirve
al final, para mirar los resultados en un mapa.

---

## 3. La llave de OpenTopography (una sola vez)

Es gratis e inmediata, y sirve para bajar los modelos de elevación.

1. Entra a <https://portal.opentopography.org/> y créate una cuenta.
2. Ve a **My Account** y pide una *API key*.
3. Dísela a la consola, en la misma ventana donde vas a trabajar:

```bash
set OPENTOPOGRAPHY_API_KEY=pega_aqui_tu_llave          REM Windows
export OPENTOPOGRAPHY_API_KEY=pega_aqui_tu_llave       # Linux / macOS
```

Eso dura mientras la ventana esté abierta; si la cierras, hay que repetirlo.
Se hace así, y no se guarda en un archivo, para que la llave no acabe subida
al repositorio sin querer.

---

## 4. Correr el estudio

Nueve pasos, en orden. Cada uno deja su resultado en disco, así que puedes
parar y seguir otro día sin perder nada.

```bash
python -m camino bajar          # 1
python -m camino ruta           # 2
python -m camino preparar       # 3
python -m camino superficies    # 4
python -m camino grafo          # 5
python -m camino revisar        # 6
python -m camino nulos          # 7
python -m camino barrido        # 8
python -m camino resultados     # 9
```

O `python -m camino todo` de corrido.

| # | Paso | Qué hace | Qué escribe | Tarda |
|---|---|---|---|---|
| 1 | `bajar` | los dos modelos de elevación y los cuerpos de agua | `datos/cop30_raw.tif`, `datos/aw3d30_raw.tif`, `datos/agua_osm.json` | minutos, según la conexión |
| 2 | `ruta` | el camino observado (ver §5) | `datos/qn_geocam.gpkg` | segundos |
| 3 | `preparar` | pone los dos modelos en la misma rejilla, recorta el corredor | `derivados/cop30.tif`, `derivados/mascara.tif` | ~1 min |
| 4 | `superficies` | pendiente, rugosidad, drenaje, humedad | `derivados/phi_*.tif` | 2–5 min |
| 5 | `grafo` | el grafo de tránsito sobre el terreno | `derivados/grafo.npz` | 1–2 min |
| 6 | `revisar` | traza **un** camino para que lo mires | `resultados/revision_pendiente.gpkg` | segundos |
| 7 | `nulos` | el terreno aleatorio de comparación | `derivados/nulos.npz` | ~15 min |
| 8 | `barrido` | prueba los 231 juegos de pesos, sector por sector | `resultados/optimos_por_sector.json` | ~30 min |
| 9 | `resultados` | el perfil de equifinalidad y su gráfico | `resultados/perfil_equifinalidad.png` | segundos |

Los tiempos son estimaciones para un corredor de unos 350 000 píxeles en una
laptop de ocho núcleos. Los dos largos (7 y 8) salen del cálculo que está en
`METODO.md`, §5.

### Dos cosas sobre el orden

**`revisar` es el paso que no se salta.** Traza un solo camino, poniendo todo
el peso en la pendiente, y lo guarda como GeoPackage. Ábrelo en QGIS encima
del modelo de elevación y míralo con ojos de arqueóloga: ¿pasa por donde
pasaría un camino?, ¿cruza las quebradas por donde se puede cruzar? Si ese
camino no es plausible, ninguno de los siguientes lo será, y no hay
estadística que lo arregle.

**`nulos` va antes que `barrido`, y no es intercambiable.** Un sector cuyo
mejor camino no le gana a terreno aleatorio no tiene pesos que valga la pena
reportar. Al revés, se acaban comparando pesos de sectores donde el modelo no
explica nada, y los números parecen válidos sin serlo.

### Los pasos 1, 3 y 4 no necesitan el camino

Si el paso 2 se atasca, sáltatelo y sigue: `bajar`, `preparar` y
`superficies` sólo trabajan con el modelo de elevación. Son los que más
tardan, y dejan todo listo. Cuando `preparar` corre sin camino, usa la caja
entera como dominio y te lo dice. A partir de `grafo` sí hace falta.

---

## 5. El camino observado: de dónde sale

El paso 2 acepta tres fuentes:

```bash
python -m camino ruta                                       # GeoCAM
python -m camino ruta --fuente archivo --archivo X.shp      # un archivo tuyo
python -m camino ruta --fuente osm                          # apaño provisional
```

### GeoCAM, que es lo que corresponde

Es el registro del Ministerio de Cultura, y es la fuente que se cita en un
artículo. El programa entra por **WFS**, el estándar OGC que el propio portal
publica. El endpoint ya viene escrito en `config.yaml`; lo único que falta es
saber qué capa es el camino, y eso lo averigua:

```bash
python -m camino buscar
```

Lista las capas que publica el servidor, las ordena de más a menos probable y
escribe la primera en `config.yaml`. Después, `python -m camino ruta`.

**A octubre de 2026 ese servidor está caído.** Devuelve un *Proxy Error —
Error during SSL Handshake with remote server*, y falla igual desde el
navegador, así que no es nada que puedas arreglar de tu lado. El programa
prueba cuatro rutas del servidor y reintenta; si aun así no responde, está
caído y hay que usar una de las otras dos fuentes mientras tanto.

### Un archivo tuyo — el KMZ del registro

La salida práctica mientras GeoCAM no vuelva, y la que está en uso.

[GEO GPS PERÚ](https://www.geogpsperu.com/2020/10/mapa-del-qhapaq-nan-camino-inca.html)
publica el Qhapaq Ñan nacional en KMZ y shapefile, descarga directa. El KMZ
no es una traza suelta: trae **las categorías con que el Ministerio clasifica
cada segmento**, cada una en su propia capa. Ponlo en `datos/` y:

```bash
python -m camino ruta --fuente archivo --archivo datos/qhapaq_nan.kmz
```

El programa lo abre, saca los atributos (que vienen escondidos en una tabla
HTML dentro de cada placemark), imprime el inventario de tramos y se queda
con el que pide `config.yaml`.

**Excluye las capas de «Proyección de Camino»** por Reemplazo, Daños o
Ausencia. Son tramos donde el camino ya no está y la línea la dibujó alguien
infiriendo por dónde iba; ajustar el modelo contra ellas es circular. Está
explicado en `METODO.md`, §8 bis, y se controla con `datos.solo_observadas`.

Lo que hay en la caja del estudio, medido sobre ese KMZ:

| Tramo | rasgos | km | continuo |
|---|---|---|---|
| Leymebamba – Chilchos – Mendoza | 2 | 29.29 | 29.29 |
| La Jalca – Mendoza | 5 | 20.25 | 20.25 |
| Chachapoyas – Jumbilla | 9 | 16.97 | 14.28 |
| Pauja – Santa Cruz | 3 | 14.21 | 14.21 |
| **Chillo – Chachapoyas** | **11** | **23.02** | **12.40** |
| Chachapoyas – Cochamal | 13 | 28.71 | 8.55 |
| Pueblo Viejo – La Jalca Grande | 6 | 13.57 | 7.90 |

**Chillo – Chachapoyas** es el tramo del proyecto, y es el que viene puesto
en `config.yaml`. Para estudiar otro, cambia `datos.tramo`; para usarlos
todos, déjalo vacío.

También entran por aquí un shapefile, un GeoPackage, un GeoJSON, o el `.gpx`
del Garmin de Dina cuando vuelva del campo.

### OpenStreetMap, sólo como apaño

Baja las trazas etiquetadas como `historic` o con «inca» o «qhapaq» en el
nombre. Sirve para que el código corra de punta a punta mientras no hay nada
mejor. Son trazas cargadas por voluntarios, sin control de precisión ni
criterio arqueológico: el programa las marca como `osm_provisional` y te lo
recuerda al terminar. **No valen para publicar.**

---

## 6. Qué mirar en los resultados

**Al terminar el paso 2**, el programa imprime cuántos metros de *polilínea
continua* trajo. Es el número que decide el diseño del estudio:

- Con bastante camino continuo, se puede partir en sectores **y** validar en
  bloques: ajustar los pesos en los sectores pares y medir qué tan bien
  predicen los impares.
- Con poco, las dos cosas compiten por los mismos metros y hay que elegir
  una. Esa decisión se toma **antes** de correr el barrido, no después de ver
  los resultados.

Si el tramo continuo más largo baja de unos 15 km, el programa lo avisa.

Para Chillo – Chachapoyas ya está medido: **23.02 km registrados en 3 piezas,
la mayor de 12.40 km**. Con eso, `n_sectores: 4` da 3.10 km por sector (unas
103 celdas de 30 m), que deja margen al camino de mínimo costo dentro de cada
sector y además permite validación bloqueada —ajustar en los pares, medir en
los impares—. Con 6 sectores bajarían a 2.07 km y empezarían a ser demasiado
cortos para que los pesos signifiquen algo.

**Al terminar el paso 8**, `resultados/optimos_por_sector.json` trae una fila
por sector: los pesos óptimos, la distancia al camino observado, el valor *p*
contra el nulo, y el rango de cada peso dentro del conjunto casi-óptimo. Ese
rango es lo que se reporta en el texto — no «w_pendiente = 0.60» sino
«w_pendiente entre 0.45 y 0.70».

**Al terminar el paso 9**, `resultados/perfil_equifinalidad.png` es la figura
principal: cómo se separan los conjuntos de pesos entre sectores. Dos
sectores cuyas curvas se van abajo y se quedan abajo están gobernados por
variables distintas. Dos que se solapan no se distinguen con estos datos, y
eso también es un resultado.

---

## 7. Los parámetros

Todos viven en `config.yaml`, cada uno con su comentario. Si un umbral
aparece escrito dentro del código, es un error.

Tres que probablemente toques:

**`componentes`** — qué variables del terreno entran al modelo.

```yaml
costo:
  componentes: [pendiente, rugosidad, drenaje]
```

Con esas tres son 231 juegos de pesos y el barrido tarda media hora. Si
añades `humedad`, pasan a 1771 y tarda unas dos horas. Empieza con tres.

**`buffer_corredor`** — media anchura, en metros, de la franja alrededor del
camino por donde el modelo puede buscar.

```yaml
dominio:
  buffer_corredor: 4000
```

Existe por cómputo: el área completa son tres millones y medio de celdas y no
se pueden barrer. Pero si la franja es estrecha, es ella la que decide el
resultado. Por eso `revisar` comprueba si el camino modelado se pegó al
borde; si avisa, sube este número y vuelve a correr desde `preparar`.

**`umbral_quebrada`** — cuántas celdas de área drenada hacen que una celda
cuente como quebrada.

```yaml
dominio:
  umbral_quebrada: 500
```

500 celdas son 0.45 km² a 30 m. Es el único parámetro de todo el modelo que
el trabajo de campo fija directamente: se calibra contra las quebradas que
realmente haya que cruzar.

### Datos sensibles

Las coordenadas de evidencias arqueológicas sensibles o no publicadas no
entran al repositorio público. El `.gitignore` ya excluye `datos/` y
`derivados/`, y todo lo que hay ahí se regenera corriendo los pasos, así que
no se pierde nada por no versionarlo. Lo que se publique pasa antes por las
restricciones institucionales que correspondan.

---

## 8. Si algo falla

| Lo que dice la consola | Qué pasa |
|---|---|
| `ModuleNotFoundError` | falta `conda activate camino` |
| `Falta la llave de OpenTopography` | el `set OPENTOPOGRAPHY_API_KEY=...` del §3, en esta misma ventana |
| `no se pudo bajar el agua de OpenStreetMap` | Overpass está saturado. **No bloquea nada**: la máscara queda sin excluir lagunas. Reintenta luego con `python -m camino bajar --forzar` |
| `Falta la dirección de GeoCAM` | corre `python -m camino buscar`, o usa otra fuente (§5) |
| `Proxy Error … SSL Handshake` | el servidor del Ministerio está caído. No es tuyo. Usa otra fuente (§5) |
| `Ningún endpoint WFS respondió` | lo mismo; el programa ya probó cuatro rutas, dos veces |
| `ninguna parece ser el camino` | mira la lista que imprime `buscar` y pon a mano la capa en `geocam_capa` |
| `no tiene nada dentro de la caja del tramo` | bajó una capa que no es el camino, o el tramo no está digitalizado ahí |
| `el camino modelado toca el borde del corredor` | sube `buffer_corredor` y vuelve a correr desde `preparar` |
| `la pieza continua mide X m` | poco camino continuo para tantos sectores: baja `n_sectores` |

---

## Por qué no se usa un GIS para esto

- `r.cost` de GRASS es isotrópico: no distingue subir de bajar.
- `r.walk` sí distingue, pero tiene su función de marcha cableada por dentro
  y no admite pesos elegidos por el usuario.
- `MCP_Geometric` de scikit-image es isotrópico.
- QGIS no trae nada equivalente.

Ninguno permite recorrer sistemáticamente juegos de pesos sobre un costo que
distinga el sentido de la marcha, que es exactamente lo que pide la pregunta.
De ahí el programa: numpy y scipy, sin dependencias raras.
