# Camino inca, tramo Leimebamba – Chachapoyas

Optimización inversa de pesos de terreno. La pregunta no es por dónde pasó el
camino —eso ya está registrado— sino **qué variables del terreno explican por
dónde pasó, y si son las mismas a lo largo de todo el tramo**.

El método y las ecuaciones están en [`METODO.md`](METODO.md). Esto es cómo
correrlo.

---

## 1. El entorno, una sola vez

Todo se hace en la **consola de Anaconda** (Anaconda Prompt). No hace falta
tocar QGIS, ArcGIS, GRASS, ni la línea de comandos de GDAL en ningún momento:
el paquete hace la reproyección, el recorte, la hidrología y el grafo en
Python.

```bash
conda env create -f environment.yml
conda activate camino
```

Si prefieres armarlo a mano:

```bash
conda create -n camino -c conda-forge python=3.12 numpy scipy pandas rasterio geopandas shapely pyyaml joblib matplotlib requests pytest -y
conda activate camino
```

Comprueba que quedó, desde la carpeta del proyecto:

```bash
python -m pytest -q
```

Deben pasar 123 pruebas en un par de segundos. Si falla algo aquí, falla antes
de tocar datos, que es cuando conviene.

> Cada vez que abras la consola de nuevo: `conda activate camino` y `cd` a la
> carpeta del proyecto. Si Python no encuentra un paquete, el 95% de las veces
> es que olvidaste activar el entorno.

## 2. Las dos llaves que hay que conseguir

**(a) La llave de OpenTopography**, gratis e inmediata, para bajar los DEM.
En <https://portal.opentopography.org/> → *My Account* → pide una API key.
Después, en la consola:

```bash
set OPENTOPOGRAPHY_API_KEY=tu_llave          REM Windows
export OPENTOPOGRAPHY_API_KEY=tu_llave       # Linux / macOS
```

Va en la variable de entorno y no en `config.yaml` para que no acabe en el
control de versiones.

**(b) La URL del servicio de GeoCAM**, que el portal no publica y hay que
sacar del navegador una sola vez:

1. Abre <https://geocam.cultura.gob.pe/>
2. `F12` → pestaña **Network**, escribe `query` en el filtro
3. Acerca el mapa a Chachapoyas hasta que carguen las capas del camino
4. Clic derecho sobre una de las peticiones → *Copy* → *Copy URL*
5. Quítale todo desde `/query` en adelante. Te queda algo como
   `https://.../FeatureServer/0`
6. Pégalo en `config.yaml`, en `datos.geocam_servicio`

Si te pierdes, `python -m camino geocam` sin configurarlo imprime estos
mismos pasos.

## 3. Correr el estudio

Un paso por comando, en este orden:

```bash
python -m camino bajar          # los dos DEM y los cuerpos de agua
python -m camino geocam         # el camino registrado
python -m camino preparar       # alinear rásteres + máscara del corredor
python -m camino superficies    # pendiente, rugosidad, drenaje, humedad
python -m camino grafo          # el grafo dirigido y la matriz Phi
python -m camino revisar        # UN camino, para mirarlo  <-- no te lo saltes
python -m camino nulos          # el nulo por sector
python -m camino barrido        # el barrido de pesos
python -m camino resultados     # el perfil de equifinalidad
```

o `python -m camino todo` de corrido.

**El orden no es decorativo.** `nulos` va antes de `barrido` porque un sector
cuyo mejor camino no le gana a terreno aleatorio no tiene pesos que reportar,
y compararle los pesos a otro sector sería comparar dos números vacíos.

**`revisar` es el paso que no se salta.** Corre un solo Dijkstra con todo el
peso en la pendiente y escribe `resultados/revision_pendiente.gpkg`. Ábrelo en
QGIS encima del DEM y míralo. Si ese camino no es plausible sobre el terreno,
nada de lo que viene después lo es, y no hay estadística que lo arregle.

## 4. Lo primero que hay que mirar

`python -m camino geocam` imprime, al final, **cuántos metros de polilínea
continua** hay en el registro. Es el número que decide el diseño del estudio:

- Con bastante camino continuo: se puede partir en sectores **y** validar en
  bloques (ajustar en los sectores pares, medir en los impares).
- Con poco: las dos cosas compiten por los mismos metros. Hay que **elegir una
  antes de correr el barrido**, no después de ver los resultados.

Si el tramo continuo más largo baja de ~15 km, el programa avisa.

## 5. Qué hay en cada carpeta

| Carpeta | Qué guarda |
|---|---|
| `datos/` | lo que se bajó, tal como vino. No se edita nunca. |
| `derivados/` | rásteres alineados, componentes de costo, el grafo, los nulos. Todo reproducible: se puede borrar. |
| `resultados/` | las tablas, el perfil de equifinalidad y su figura. |
| `camino/` | el paquete. |
| `tests/` | las pruebas. |

## 6. Los parámetros

Todos viven en [`config.yaml`](config.yaml), comentados uno por uno. Si un
umbral aparece escrito dentro del código, es un bug.

Los tres que vas a querer tocar:

- `costo.componentes` — empieza con tres (231 vectores de peso, ~30 min).
  Agregar `humedad` lo lleva a cuatro (1771 vectores, ~2 h).
- `dominio.buffer_corredor` — si `revisar` avisa que el camino toca el borde,
  ensánchalo.
- `dominio.umbral_quebrada` — es el único parámetro del modelo que el trabajo
  de campo fija directamente: se calibra contra las quebradas que realmente
  haya que cruzar.

## 7. Los tracks del GPS

Todavía no están: Dina camina del 8 al 15 de octubre. **Nada se bloquea por
eso.** Los tracks entran en la validación; hasta que lleguen, el modelo se
ajusta contra la geometría de GeoCAM sola.

Cuando lleguen, los `.gpx` salen del Garmin por USB (carpeta
`Garmin/Activities`) o exportándolos de Garmin Connect. Van a `datos/gpx/`.

## 8. Datos sensibles

Las coordenadas de evidencias arqueológicas sensibles o no publicadas que
salgan de GeoCAM o de los tracks **no entran al repositorio público**. El
`.gitignore` ya excluye `datos/` y `derivados/` por eso. Lo que se publique
tiene que pasar antes por las restricciones institucionales correspondientes.

## 9. Por qué no un GIS

- `r.cost` de GRASS es isotrópico: no distingue subir de bajar.
- `r.walk` sí es anisotrópico, pero tiene la función de Langmuir cableada y no
  admite pesos propios.
- `skimage.graph.MCP_Geometric` es isotrópico.
- QGIS no tiene nada equivalente.

Ninguno permite barrer pesos sobre un costo anisotrópico, que es justo lo que
pide la pregunta. De ahí el paquete: numpy y scipy, sin dependencias exóticas.
