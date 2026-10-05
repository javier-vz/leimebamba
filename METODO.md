# El método, con sus ecuaciones

Cómo correrlo está en [`README.md`](README.md). Esto es qué hace y por qué.

El modelo tiene **una sola ecuación de verdad**: el costo de cruzar de una
celda a su vecina. Todo lo demás es cómo llenarla y cómo barrer sus pesos.

---

## 1. La ecuación

Para cada arista dirigida que va de la celda $i$ a la celda $j$:

$$c_{ij}(\mathbf{w}) \;=\; L_{ij}\sum_{k=1}^{K} w_k\,\varphi_k(i,j),
\qquad \sum_{k=1}^{K} w_k = 1,\quad w_k \ge 0$$

- $L_{ij}$ es la longitud de la arista en metros.
- $\varphi_k(i,j)$ es la componente $k$ del costo, adimensional, del orden de 1.
- $\mathbf{w}$ son los pesos, y son **lo que se busca**: no se fijan a mano, se
  estiman del camino observado.

La restricción $\sum_k w_k = 1$ es la que hace comparables los pesos entre
sectores. Sin ella, $\mathbf{w}$ y $2\mathbf{w}$ dan exactamente el mismo
camino, el óptimo no es único, y la frase «en este sector manda la pendiente»
no quiere decir nada. Con ella, los pesos viven en un símplex y «0.6 de
pendiente» significa lo mismo en el sector 1 y en el sector 5.

Código: `camino/grafo.py`, método `Grafo.costos`.

## 2. La componente de pendiente, la única anisotrópica

Primero el gradiente **dirigido** de la arista:

$$L_{ij} = \sqrt{(x_j-x_i)^2 + (y_j-y_i)^2},
\qquad g_{ij} = \frac{z_j - z_i}{L_{ij}}$$

Aquí vive toda la asimetría del modelo, porque $g_{ij} = -g_{ji}$. Las otras
componentes son simétricas; es este término el que hace que ir de Leimebamba a
Chachapoyas no cueste lo mismo que ir al revés. Por eso **la pendiente no es
un ráster** en este modelo: un ráster de pendiente no sabe en qué dirección
vas.

Luego el costo metabólico de caminar, en J·kg⁻¹·m⁻¹
(Minetti *et al.* 2002):

$$C_w(g) \;=\; 280.5\,g^{5} - 58.7\,g^{4} - 76.8\,g^{3} + 51.9\,g^{2} + 19.6\,g + 2.5$$

Ajustada con $R^2 = 0.999$ sobre $g \in [-0.45,\,+0.45]$. Valores de
referencia, para comprobar cualquier implementación:

| $g$ | $C_w$ (J·kg⁻¹·m⁻¹) | |
|---|---|---|
| −0.45 | 3.6 | bajada fuerte |
| **−0.10** | **1.13** | **el mínimo: bajar suave sale más barato que el plano** |
| 0 | 2.5 | plano |
| +0.45 | 17.6 | subida fuerte |

Eso fija $g_{\max} = 0.45$, y **no es una elección estética**: es el borde de
validez del ajuste. Fuera de ese rango la polinomial se dispara y deja de
significar nada. Las aristas con $|g| > g_{\max}$ **se eliminan del grafo**, no
se recortan a 0.45 — recortarlas convierte un acantilado en una cuesta
transitable.

La componente, normalizada a 1 en terreno plano:

$$\varphi_{\text{pend}}(i,j) \;=\; \frac{C_w(g_{ij})}{C_w(0)} \;=\; \frac{C_w(g_{ij})}{2.5}$$

Para contrastar se puede correr la función de marcha de Tobler (1993),
$v(g) = 1.662\,e^{-3.5|g+0.05|}$ m/s con costo por metro $1/v$, pero **como
modelo alterno, nunca como componente adicional**: Tobler es velocidad y
Minetti es energía, y sumarlos deja un número sin unidades que no se puede
interpretar.

Código: `camino/costo.py`.

## 3. Las componentes simétricas

Rugosidad, drenaje y humedad son propiedades de la celda, no del paso, así que
la arista toma el promedio de sus dos extremos:

$$\varphi_k(i,j) \;=\; \tfrac{1}{2}\left[\tilde\varphi_k(i) + \tilde\varphi_k(j)\right],
\qquad k \in \{\text{rug},\ \text{dren},\ \text{hum}\}$$

Cada ráster se escala con **percentiles**, no con mínimo–máximo (un solo píxel
de ruido en el DEM no debe fijar la escala de toda la superficie), y se
desplaza para que nunca valga cero:

$$\tilde\varphi_k \;=\; \varepsilon + \operatorname{clip}\!\left(
\frac{x_k - q_{05}(x_k)}{q_{95}(x_k) - q_{05}(x_k)},\ 0,\ 1\right),
\qquad \varepsilon = 0.01$$

El $\varepsilon$ no es cosmético: con aristas de costo cero, Dijkstra devuelve
caminos degenerados que recorren kilómetros gratis.

### 3.1 Pendiente y aspecto (insumo del VRM)

Ventana 3×3 de Horn, sobre el DEM **sin rellenar**:

$$\frac{\partial z}{\partial E} = \frac{(z_3 + 2z_6 + z_9) - (z_1 + 2z_4 + z_7)}{8\,\Delta x},
\qquad
\frac{\partial z}{\partial N} = \frac{(z_1 + 2z_2 + z_3) - (z_7 + 2z_8 + z_9)}{8\,\Delta y}$$

$$S = \arctan\sqrt{\left(\frac{\partial z}{\partial E}\right)^2 + \left(\frac{\partial z}{\partial N}\right)^2},
\qquad
A = \operatorname{atan2}\!\left(-\frac{\partial z}{\partial E},\ -\frac{\partial z}{\partial N}\right)$$

### 3.2 Rugosidad: VRM, no TRI

$$\mathbf{n} = \big(\sin S \sin A,\ \ \sin S \cos A,\ \ \cos S\big)$$

$$\mathrm{VRM} \;=\; 1 - \frac{\left\lVert \sum_{c \in W} \mathbf{n}_c \right\rVert}{|W|}$$

con $W$ la ventana 3×3 y $|W| = 9$ (Sappington *et al.* 2007). $\mathrm{VRM}
\in [0,1]$: 0 es plano **o** inclinado pero uniforme; cerca de 1, terreno
quebrado.

Se usa esto y no el TRI a propósito. **El TRI es casi una función de la
pendiente**: como componente aparte haría que dos de los pesos midieran lo
mismo y el óptimo dejaría de ser único. El VRM separa *qué tan inclinado* de
*qué tan desordenado*. Hay una prueba que lo fija: sobre un plano inclinado el
VRM es cero exactamente, por inclinado que esté.

### 3.3 Agua: drenaje y anegamiento

Aquí sí, y **sólo aquí**, el DEM rellenado. Rellenar depresiones borra
concavidades reales del terreno; usado para la pendiente, inventa planicies.

El relleno es Priority-Flood (Barnes *et al.* 2014) con un incremento mínimo
que impone gradiente dentro de cada depresión rellenada: sin eso el D8 no sabe
hacia dónde drenar en el fondo de un lago. Después, direcciones D8 y
acumulación exacta recorriendo las celdas en orden decreciente de elevación.

Costo de cruzar un drenaje, que crece con el área que drena por la celda:

$$\varphi_{\text{dren}} = \log_{10}\!\big(1 + A_{\text{celdas}}\big)$$

Y el anegamiento del suelo, que en bosque de neblina es lo que la pendiente no
ve:

$$\mathrm{TWI} = \ln\!\left(\frac{a}{\tan S + 0.001}\right)$$

con $a$ el área de contribución específica (área por unidad de contorno, m).

El umbral de quebrada ($A \ge 500$ celdas $\approx 0.45$ km² a 30 m) es **el
único parámetro de todo el modelo que el trabajo de campo fija directamente**:
se calibra contra las quebradas que realmente haya que cruzar.

Código: `camino/superficies.py`, `camino/hidrologia.py`.

## 4. El grafo y la máscara

Nodos: las celdas transitables. Aristas: **vecindad de 16, no de 8**. Con 8
vecinos los caminos sólo pueden girar en pasos de 45° y se alargan hasta 8.2%
($1/\cos 22.5°$); con 16 el sesgo de cuantización angular baja a 2.8%
($1/\cos 13.3°$).

Los ocho vecinos extra son los saltos de caballo $(\pm1,\pm2)$ y
$(\pm2,\pm1)$, y **pasan por encima de dos celdas intermedias**: hay que
comprobar que esas celdas sean transitables antes de crear la arista. Es el
error clásico de la vecindad 16 y hace que los caminos salten acantilados y
ríos.

La **máscara** saca del dominio: las celdas sin ninguna arista con
$|g| \le g_{\max}$, los cuerpos de agua permanentes, y un corredor alrededor
del camino registrado. El corredor existe por cómputo —la caja completa son
3.5 millones de celdas y no se barren— pero un buffer estrecho **decide** el
resultado. De ahí el chequeo de `revisar`: si el camino modelado toca el borde
del corredor, hay que ensancharlo. Es una línea de código y se olvida siempre.

La máscara va **fija** para todos los vectores de pesos y para todos los
nulos. Si cambia entre corridas, nada es comparable.

### 4.1 El truco que hace factible el barrido

La topología del grafo y las componentes $\varphi$ **no dependen de
$\mathbf{w}$**. Se precalculan una vez la matriz $\Phi$ de $E \times K$ y el
vector $L$ de longitudes; por cada vector de pesos lo único que se recalcula es
el vector de datos de la matriz dispersa:

```python
csr.data[:] = L * (Phi @ w)
```

Si se reconstruye la matriz dentro del bucle, ahí se va el 95% del tiempo.

Hay una trampa que arruina esto en silencio:
`csr_matrix((data, (rows, cols)))` **reordena las aristas y suma los
duplicados**, así que `csr.data` no queda en el orden en que se le pasaron. El
paquete lo resuelve con un mapa de posiciones explícito
(`grafo._permutacion_csr`): se construye una matriz con las aristas numeradas
$1..E$ como datos, y al convertir a CSR cada posición dice qué arista le tocó.
No se supone nada del orden interno de scipy.

Es el bug que no se nota: con las filas de $\Phi$ desalineadas, el modelo
corre, converge y devuelve números creíbles — sobre aristas equivocadas. Por
eso hay una prueba (`test_la_permutacion_csr_es_correcta`) que recalcula el
costo de **cada** arista desde el ráster y lo compara con lo que quedó en la
matriz.

Código: `camino/grafo.py`.

## 5. El barrido

Red regular sobre el símplex con paso $h = 1/n$:

$$\Lambda_{K,h} = \left\{\mathbf{w} : w_k = \frac{m_k}{n},\ \ m_k \in \mathbb{Z}_{\ge 0},\ \ \sum_{k=1}^{K} m_k = n\right\}$$

$$\bigl|\Lambda_{K,h}\bigr| = \binom{n + K - 1}{K - 1}$$

Con $n = 20$ ($h = 0.05$): $K = 3$ da **231** vectores, $K = 4$ da **1771**.

Barrido exhaustivo y no un optimizador, por tres razones: con $K \le 4$ sale
gratis, no hay mínimos locales de los que preocuparse, y —sobre todo— lo que
el proyecto necesita es **el paisaje completo y no el óptimo**, porque el
resultado es el conjunto de pesos casi-óptimos (§7).

### Presupuesto

Con ~350 000 nodos y ~5 millones de aristas, un Dijkstra de fuente única corre
en ~2 s; en el subgrafo de un sector (~60 000 nodos), en ~0.3 s.

| Corrida | Dijkstras | 1 núcleo |
|---|---|---|
| Barrido por sector, $K=3$ | 6 × 231 = 1 386 | ~7 min |
| Ruta completa, $K=3$ | 231 | ~8 min |
| Nulos, $M=500$ × 6 sectores | 3 000 | ~15 min |
| **Total $K=3$** | **~4 600** | **~30 min** |
| Total $K=4$ | ~13 000 | ~2 h |

Con `joblib` sobre 8 núcleos, $K=3$ son cinco minutos. Corre en una laptop.

Código: `camino/barrido.py`.

## 6. Las dos distancias

Se reportan **dos** números, no uno.

La distancia media simétrica mide el desacuerdo típico:

$$D_H(P,Q) = \tfrac{1}{2}\left(
\frac{1}{|P|}\sum_{p \in P} \min_{q \in Q} \lVert p-q \rVert
+ \frac{1}{|Q|}\sum_{q \in Q} \min_{p \in P} \lVert q-p \rVert \right)$$

La Fréchet discreta mide el peor desacuerdo **respetando el orden del
recorrido** (Eiter & Mannila 1994):

$$\delta(a,b) = \max\Big\{\, d(P_a, Q_b),\ \ \min\big\{\delta(a{-}1,b),\ \delta(a{-}1,b{-}1),\ \delta(a,b{-}1)\big\}\Big\}$$

$$D_F(P,Q) = \delta\big(|P|,\,|Q|\big)$$

$D_H$ sola esconde que el modelo se fue por otra quebrada y volvió; $D_F$ sola
castiga igual un desvío puntual que un error sistemático. El óptimo se busca
con $D_H$, que es la que se puede calcular miles de veces, y la $D_F$ se
reporta para los óptimos.

**Cuidado con el muestreo.** La Fréchet discreta es sensible a cómo están
muestreadas las polilíneas, no sólo a su forma: comparar un camino modelado de
1500 celdas contra una geometría de GeoCAM de 200 vértices sin igualar el
muestreo infla la distancia por decenas de metros que no son desacuerdo, son
discretización. El paquete remuestrea **las dos** a un número fijo de vértices
antes de comparar.

El óptimo de un sector es entonces:

$$\mathbf{w}^{*}_{s} = \arg\min_{\mathbf{w} \in \Lambda_{K,h}}
D_H\big(P_s(\mathbf{w}),\ Q_s\big)$$

Código: `camino/metricas.py`.

## 7. Equifinalidad: el resultado de verdad

El óptimo puntual **no es el hallazgo**. Con datos reales, ese punto es ruido:
muchos vectores de pesos distintos producen caminos prácticamente iguales. Lo
que se puede sostener es el conjunto de pesos que explican el camino observado
casi igual de bien:

$$S_s(\tau) = \big\{\mathbf{w} \in \Lambda_{K,h} :\ D_s(\mathbf{w}) \le (1+\tau)\,D^{*}_{s}\big\}$$

y cómo se comparan esos conjuntos entre sectores:

$$J_{st}(\tau) = \frac{\bigl|S_s(\tau) \cap S_t(\tau)\bigr|}{\bigl|S_s(\tau) \cup S_t(\tau)\bigr|}$$

**Graficar $J_{st}$ contra $\tau$ es la respuesta a la pregunta del
proyecto.** Dos sectores cuyos conjuntos se separan —$J$ baja y se queda baja
al crecer $\tau$— están gobernados por variables distintas. Dos cuyos
conjuntos se solapan incluso con $\tau$ pequeño no se distinguen con estos
datos, y eso también es un resultado, no un fracaso.

En el texto no se reporta «$w_{\text{pend}} = 0.60$» sino «$w_{\text{pend}}$
entre 0.45 y 0.70 con $\tau = 0.10$», que es lo que el paquete imprime.

Código: `camino/equifinalidad.py`.

## 8. El nulo, y por qué va primero

Un sector cuyo mejor camino no le gana a terreno aleatorio **no tiene pesos
que reportar**, y decir «aquí manda la rugosidad» sobre un sector así es decir
nada. Por eso `nulos` corre antes de `barrido`.

El nulo **no es ruido blanco**. Un camino de mínimo costo sobre ruido blanco es
fácil de ganar y el test saldría significativo siempre. El nulo correcto
conserva la autocorrelación espacial de la superficie real y sólo destruye su
relación con el terreno: campos gaussianos con el mismo exponente espectral,
por síntesis espectral,

$$\hat g(\mathbf{k}) = \mathcal{N}(0,1)\cdot \lVert\mathbf{k}\rVert^{-\beta/2}$$

con $\beta$ estimado del periodograma radial de la propia superficie de costo,
y escalados al mismo rango por los mismos percentiles. Luego, con $M$
realizaciones:

$$p_s = \frac{1 + \#\{m : D^{\text{nulo}}_m \le D^{*}_{s}\}}{M+1}$$

El piso es $1/(M+1)$: con $M = 500$ **no se puede reportar «$p < 0.002$»**, se
reporta «$p = 0.002$ con $M = 500$».

Código: `camino/nulos.py`.

## 9. Lo que este diseño no hace

- **No datea el camino.** Los pesos describen la relación entre una geometría y
  un terreno; no dicen cuándo se construyó ni en qué orden.
- **No prueba intención.** Que la pendiente explique un sector no significa que
  quien lo trazó estuviera minimizando energía: significa que el trazado es
  compatible con eso y no con las alternativas probadas.
- **No ve lo que no está en el DEM.** Visibilidad hacia huacas, tenencia de
  tierras, nieve estacional, un puente que ya no existe. Un sector mal
  explicado por las cuatro variables puede estar bien explicado por algo que no
  está medido, y conviene decirlo así en lugar de subir $K$ hasta que encaje.
- **Hereda el DEM.** La banda de incertidumbre vertical entre Copernicus y
  AW3D30 (que `preparar` calcula y guarda) dice cuánta de la variación del
  costo de pendiente es terreno y cuánta es la fuente elegida. Va en el
  artículo, no en una nota al pie.

---

## Fuentes

**Las ecuaciones**

- Minetti, A. E., Moia, C., Roi, G. S., Susta, D. & Ferretti, G. (2002).
  Energy cost of walking and running at extreme uphill and downhill slopes.
  *Journal of Applied Physiology* 93(3), 1039–1046.
  <https://journals.physiology.org/doi/full/10.1152/japplphysiol.01177.2001>
  — la polinomial de §2, con $R^2 = 0.999$ sobre $g \in [-0.45, 0.45]$.
- Tobler, W. (1993). *Three presentations on geographical analysis and
  modeling.* NCGIA Technical Report 93-1 — la función de marcha del contraste.
- Horn, B. K. P. (1981). Hill shading and the reflectance map.
  *Proceedings of the IEEE* 69(1), 14–47 — la ventana 3×3 de §3.1.
- Sappington, J. M., Longshore, K. M. & Thompson, D. B. (2007). Quantifying
  landscape ruggedness for animal habitat analysis. *Journal of Wildlife
  Management* 71(5), 1419–1426 — el VRM de §3.2.
- Beven, K. J. & Kirkby, M. J. (1979). A physically based, variable
  contributing area model of basin hydrology. *Hydrological Sciences Bulletin*
  24(1), 43–69 — el TWI de §3.3.
- Barnes, R., Lehman, C. & Mulla, D. (2014). Priority-flood: an optimal
  depression-filling and watershed-labeling algorithm for digital elevation
  models. *Computers & Geosciences* 62, 117–127 — el relleno de §3.3.
- Eiter, T. & Mannila, H. (1994). *Computing discrete Fréchet distance.*
  Technical Report CD-TR 94/64, TU Wien — la recursión de §6.

**Los datos**

- Copernicus DEM GLO-30, ESA / Airbus.
  <https://registry.opendata.aws/copernicus-dem/> — bucket público
  `copernicus-dem-30m`; el nombre del tile lleva su esquina **suroeste**.
- ALOS World 3D 30 m (AW3D30), JAXA — vía OpenTopography.
- OpenTopography, API de DEM globales.
  <https://portal.opentopography.org/apidocs/> — endpoint `/API/globaldem`,
  llave gratis desde *My Account*.
- GeoCAM, Ministerio de Cultura del Perú.
  <https://geocam.cultura.gob.pe/> — servidor ArcGIS; la URL del servicio se
  saca del navegador (ver `README.md` §2b).
- OpenStreetMap, vía la API de Overpass — cuerpos de agua permanentes.
  © colaboradores de OpenStreetMap, ODbL.

**Pendiente de verificar**

- Cómo se capturó la geometría del Qhapaq Ñan en GeoCAM (¿GPS en campo?,
  ¿digitalizado sobre imagen?, ¿con qué precisión nominal?). Hay que
  preguntárselo al proyecto Qhapaq Ñan: de eso depende si la distancia media
  que se reporta es desacuerdo del modelo o error del registro.
