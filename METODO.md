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
unidades. Sin ella, $\mathbf{w}$ y $2\mathbf{w}$ dan exactamente el mismo
camino, el óptimo no es único, y la frase «en este tramo manda el costo
físico» no quiere decir nada. Con ella, los pesos viven en un símplex y «0.6
de físico» significa lo mismo en un tramo que en otro.

### Dos modelos, no uno

La ecuación se instancia **dos veces**, y es la arquitectura del proyecto:

| modelo | componentes | qué representa |
|---|---|---|
| **referencia** | $\varphi_{\text{fis}}$ | desplazamiento sólo por costo físico |
| **ampliado** | $\varphi_{\text{fis}},\ \varphi_{\text{cer}}$ (y $\varphi_{\text{vis}}$ si se enciende) | le suma relaciones espaciales |

El de referencia es **literalmente el caso restringido** del ampliado con los
pesos de las componentes extra en cero, así que el grafo se construye una sola
vez con todas las columnas y cada modelo se evalúa sobre la cara del símplex
que le toca. Los dos corren con los mismos nodos de inicio y fin y las mismas
restricciones, de modo que la diferencia sea atribuible a las componentes
añadidas y no al espacio de tránsito.

Lo que **no** se puede concluir de que el ampliado ajuste mejor: nada. Tiene
más parámetros, así que ajusta mejor por construcción sobre los mismos datos
con que se estimaron sus pesos. La prueba está en §8 ter, sobre bloques
retenidos.

Código: `camino/grafo.py`, método `Grafo.costos`; `camino/pipeline.py`,
`red_del_modelo`.

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

## 3. Las componentes simétricas: el espacio ceremonial

Son propiedades de la celda y no del paso, así que la arista toma el promedio
de sus dos extremos:

$$\varphi_k(i,j) \;=\; \tfrac{1}{2}\left[\tilde\varphi_k(i) + \tilde\varphi_k(j)\right],
\qquad k \in \{\text{cer},\ \text{vis}\}$$

Las dos salen del **mismo archivo de entrada** —los espacios ceremoniales
documentados— y le preguntan cosas distintas: si lo que condiciona el trazado
es pasar **cerca** de un sitio o pasar **donde se lo ve**. Por eso pueden
entrar las dos al modelo ampliado sin ser redundantes, y por eso conviene
mirar si sus pesos se reparten o si una se come a la otra.

Las dos arrastran las dos reglas de diseño del proyecto, que no son técnicas y
sí cambian el resultado:

1. Un lugar cuya identificación dependa **principalmente del propio camino**
   no sirve como predictor. Si un sitio se reconoció porque está junto a la
   vía, usarlo para explicar por dónde va la vía es circular. Esto no lo puede
   decidir el código: se filtra en el archivo de entrada, con criterio
   arqueológico.
2. Un espacio ceremonial que coincida con el **inicio o el término** del tramo
   analizado se excluye de su componente. Si no, el modelo recibe como premio
   acercarse a un punto al que de todas formas tiene que llegar, y la
   componente mide el enunciado del problema en vez del paisaje. Esto sí lo
   hace el código, por unidad.

Por la regla 2, **ninguna de las dos superficies es global**: se recalculan
para cada unidad, porque en cada tramo quedan excluidos sitios distintos. Lo
que se mantiene constante entre unidades es la **regla** de transformación
—$d_{\text{sat}}$ y el radio de visibilidad—, que es lo que exige el proyecto
para que los pesos sean comparables.

Las dos van en el mismo sentido —**más valor = más penalización**—, que es lo
que hace que «0.4 de ceremonial» signifique lo mismo que «0.4 de visibilidad».

El $\varepsilon = 0.01$ que llevan sumado no es cosmético: con aristas de costo
cero, Dijkstra devuelve caminos degenerados que recorren kilómetros gratis.

### 3.1 Proximidad

$$\tilde\varphi_{\text{cer}}(i) \;=\; \varepsilon + \operatorname{clip}\!\left(
\frac{d_{\min}(i)}{d_{\text{sat}}},\ 0,\ 1\right),
\qquad d_{\text{sat}} = 5000\ \text{m}$$

con $d_{\min}(i)$ la distancia euclidiana de la celda al sitio pertinente más
próximo. Satura, y no crece sin límite, porque sin saturar un sitio aislado
domina la superficie de medio corredor.

Se calcula con un **árbol de vecinos y no con una transformada de distancia**
porque los sitios pueden caer *fuera* de la caja: un santuario a 2 km del
borde sigue condicionando las celdas de dentro, y la transformada sólo propaga
desde semillas que estén en la rejilla.

### 3.2 Visibilidad: la que **no** se transfiere tal cual

En el proyecto del Coropuna la visibilidad tiene un referente único y
documentado: el nevado. Es un apu con nombre, con culto registrado y con
santuario de altura en la cumbre, así que «ver el apu» es una variable bien
definida y la cuenca visual se calcula desde un punto.

**En el corredor del Utcubamba no hay nada equivalente.** La documentación de
los sitios Chachapoya del valle no describe ningún cerro tutelar con nombre:
describe una relación con el paisaje en conjunto, con sitios colocados sobre
afloramientos y farallones prominentes —los más inaccesibles, pero muy
visibles desde lejos— y estructuras funerarias en cornisas visibles de un lado
a otro del valle. La dirección de la mirada está **invertida** respecto del
Coropuna: lo que se hace visible es el sitio, no la montaña.

Así que la forma que sí se transfiere es la **intervisibilidad con los propios
espacios ceremoniales**: la fracción de sitios pertinentes que se ven desde
cada celda.

$$\tilde\varphi_{\text{vis}}(i) \;=\; \varepsilon + 1 - \frac{1}{|P|}
\sum_{p \in P} \mathbb{1}\!\left[\,p \text{ visible desde } i\,\right]$$

Ver sale barato y no ver sale caro, para ir en el mismo sentido que la
proximidad. Sólo cuentan los sitios a menos de un **radio** (8 km por
omisión): en ceja de selva una cuenca visual de 40 km es un artefacto del DEM
y no una relación que nadie haya tenido.

La línea de vista se muestrea a paso de media celda con interpolación
bilineal del DEM, y el terreno intermedio se corrige por curvatura y
refracción sobre la cuerda entre los dos extremos:

$$\Delta z(d_p) \;=\; (1-k)\,\frac{d_p\,(d - d_p)}{2R},
\qquad k = 0.13,\ R = 6371\ \text{km}$$

El terreno **sube** respecto de la recta, no baja: la cuerda entre dos puntos
de la esfera pasa por dentro, así que el suelo de en medio se interpone. Es
algebraicamente lo mismo que restarle $(1-k)d^2/2R$ a la cota del objetivo,
que es como lo escriben GRASS y ArcGIS. Se comprueba con dos puntos a cota 0
sobre llano: el despeje queda positivo, o sea tapado, que es lo correcto —dos
puntos al nivel del mar no se ven. A 8 km de cuerda la corrección es 1.1 m en
el punto medio; a 15 km, 3.8 m. Poco, pero del mismo orden que el error
vertical del DEM, así que no se tira. Para un observador de 1.65 m sobre
terreno llano fija el horizonte en 4.9 km, que es el número clásico.

**El límite va en el texto, no escondido**: sobre un DEM de 30 m esto es
visibilidad *potencial sobre terreno desnudo y con buen tiempo*. No hay
vegetación en el modelo, y esto es bosque de neblina con cobertura cerrada
buena parte del año. Es una idealización, igual que el resto del modelo, y el
proyecto ya la enmarca como «una hipótesis de modelamiento y no como evidencia
directa de intencionalidad histórica».

Si algún día aparece un cerro tutelar documentado para este corredor, va en
`visibilidad.puntos` de la config y se suma a los sitios sin tocar el código.
La lista está vacía **a propósito**.

Código: `camino/sitios.py`, `camino/visibilidad.py`, `camino/superficies.py`.

---

## 3 bis. Las superficies de terreno que **no** llevan peso

Pendiente, rugosidad y drenaje se calculan, se guardan y se miran, pero no son
componentes ponderadas del costo. La rugosidad es **restricción** —por un
farallón no se pasa, no es que sea caro— y el drenaje es **diagnóstico**. Lo
que delimita el espacio de tránsito no recibe peso y no se optimiza: es
idéntico para los dos modelos, y es eso lo que permite atribuir las
diferencias a las componentes añadidas y no al espacio por donde se puede ir.

### 3.1 bis Pendiente y aspecto (insumo del VRM)

Ventana 3×3 de Horn, sobre el DEM **sin rellenar**:

$$\frac{\partial z}{\partial E} = \frac{(z_3 + 2z_6 + z_9) - (z_1 + 2z_4 + z_7)}{8\,\Delta x},
\qquad
\frac{\partial z}{\partial N} = \frac{(z_1 + 2z_2 + z_3) - (z_7 + 2z_8 + z_9)}{8\,\Delta y}$$

$$S = \arctan\sqrt{\left(\frac{\partial z}{\partial E}\right)^2 + \left(\frac{\partial z}{\partial N}\right)^2},
\qquad
A = \operatorname{atan2}\!\left(-\frac{\partial z}{\partial E},\ -\frac{\partial z}{\partial N}\right)$$

### 3.2 bis Rugosidad: VRM, no TRI, y como restricción

$$\mathbf{n} = \big(\sin S \sin A,\ \ \sin S \cos A,\ \ \cos S\big)$$

$$\mathrm{VRM} \;=\; 1 - \frac{\left\lVert \sum_{c \in W} \mathbf{n}_c \right\rVert}{|W|}$$

con $W$ la ventana 3×3 y $|W| = 9$ (Sappington *et al.* 2007). $\mathrm{VRM}
\in [0,1]$: 0 es plano **o** inclinado pero uniforme; cerca de 1, terreno
quebrado.

Se usa esto y no el TRI a propósito. **El TRI es casi una función de la
pendiente**, así que como umbral dejaría fuera las cuestas empinadas pero
caminables, que es justo por donde van los caminos de herradura. El VRM separa
*qué tan inclinado* de *qué tan desordenado*. Hay una prueba que lo fija:
sobre un plano inclinado el VRM es cero exactamente, por inclinado que esté.

Y entra como **restricción**, no como peso:

$$\text{celda transitable} \iff \mathrm{VRM} \le q_{99}\!\left(\mathrm{VRM}\right)$$

El percentil 99 deja fuera el 1% más roto del corredor: farallones y terreno
desmoronado. Es la frontera entre «por aquí no se pasa» y «por aquí es caro
pasar», y ponerla aquí en vez de en el costo tiene una consecuencia que
importa: **los dos modelos comparten exactamente el mismo espacio de
tránsito**. Si la rugosidad llevara peso, el modelo ampliado podría ganarle al
de referencia simplemente porque le cambia por dónde se puede ir, y la
comparación no diría nada sobre el espacio ceremonial. Se desactiva poniendo
`rugosidad_percentil: 100`.

### 3.3 bis Agua: drenaje y anegamiento

Aquí sí, y **sólo aquí**, el DEM rellenado. Rellenar depresiones borra
concavidades reales del terreno; usado para la pendiente, inventa planicies.

El relleno es Priority-Flood (Barnes *et al.* 2014) con un incremento mínimo
que impone gradiente dentro de cada depresión rellenada: sin eso el D8 no sabe
hacia dónde drenar en el fondo de un lago. Después, direcciones D8 y
acumulación exacta recorriendo las celdas en orden decreciente de elevación.

Dificultad de cruzar un drenaje, que crece con el área que drena por la celda:

$$\phi_{\text{dren}} = \log_{10}\!\big(1 + A_{\text{celdas}}\big)$$

Se calcula y se guarda (`derivados/acumulacion.tif`), pero **no lleva peso**:
es diagnóstico. Está ahí porque es lo que explica por qué los ríos no se
enmascaran —el Utcubamba sale carísimo por esta vía sin necesidad de
prohibirlo— y porque un tramo que el modelo no explica suele pasar por donde
esta superficie tiene algo que decir.

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
$|g| \le g_{\max}$, las lagunas, y un corredor alrededor del camino
registrado.

**Los ríos no se enmascaran**, y es una decisión, no un descuido. Un río
enmascarado es un río que no se puede cruzar en ningún punto: el grafo queda
partido en dos orillas y no existe camino entre ellas. Los caminos incas
cruzaban ríos por puentes y vados, y no sabemos dónde estaban. Cruzar un río
no es imposible, es caro — y eso ya lo recoge la componente de drenaje,
$\varphi_{\text{dren}} = \log_{10}(1 + A)$, que crece justo con el tamaño
del cauce. El Utcubamba sale carísimo por esa vía, sin necesidad de
prohibirlo. Una laguna sí es infranqueable, así que los polígonos de agua
cerrados por encima de un tamaño mínimo se quedan fuera del dominio. El corredor existe por cómputo —la caja completa son
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

## 6 ter. El dominio de cada unidad, y por qué `revisar` se mide ahí

Cada unidad se analiza en **su propia vecindad**: los nodos a menos de
`buffer_corredor` de su trazado. No sobre el corredor completo, y hay dos
razones.

La primera es el nulo. La pregunta que tiene que responder es «¿una ruta
cualquiera **por aquí** se habría parecido tanto al trazado observado?», y
«por aquí» sólo significa algo dentro de la vecindad del tramo. Un nulo sobre
el corredor entero compara contra rutas que pasan por sitios donde nunca
hubo nada que ver.

La segunda es que el corredor completo es la **unión de los buffers de todos
los tramos registrados** —142 km en 28 piezas en esta caja—, así que es una
mancha conexa. Un camino de mínimo costo entre los extremos de un tramo puede
irse por el buffer de otro y volver, y la distancia resultante no mide nada.

Esto último era un error en `revisar`: corría un solo Dijkstra sobre el
corredor entero, así que su diagnóstico no era comparable con lo que después
iba a reportar el barrido. Ahora usa el mismo subgrafo, y el número que
imprime sí anticipa el del barrido con $w_{\text{fis}} = 1$.

Dos avisos que acompañan a cada unidad, y que invalidan su número:

- **recortada por la caja**: el trazado llega al borde del bbox, así que uno
  de sus extremos es un artefacto del encuadre y no un destino. En la caja
  actual le pasa a cuatro de las seis unidades. `python -m camino caja` mide
  qué bbox haría falta y lo que cuesta.
- **pegada al borde de su vecindad**: el `buffer_corredor` es el que está
  decidiendo el trazado, no el terreno. Existe por cómputo —el área completa
  no se puede barrer— pero si es él el que manda, el resultado es suyo.

## 6 bis. Qué se compara con qué

La pregunta —¿manda lo mismo en todo el tramo?— exige partir el camino en
unidades, y de qué sean esas unidades depende lo que se puede afirmar.

**Tramos del registro.** Cada tramo con nombre es una unidad. Son unidades
reales: el Ministerio las registró y las nombró de forma independiente, con
su propia campaña de prospección. Comparar pesos entre ellas compara cosas
que existen fuera del análisis.

**Sectores.** Un tramo se corta en $n$ pedazos iguales. Los cortes no
corresponden a nada del terreno. Sirven para preguntar si algo cambia *a lo
largo* de un tramo, pero un resultado por sectores arrastra siempre la
sospecha de depender de dónde cayó el corte. Por eso el paquete incluye una
prueba de sensibilidad: repetir el barrido con 3, 4, 5 y 6 sectores y graficar
el peso de cada componente **contra la posición a lo largo del camino**, que
sí es comparable entre particiones. Si las curvas se superponen, la estructura
es del terreno; si cada corte dice otra cosa, era del corte.

Dos condiciones que una unidad tiene que cumplir:

- **Ser continua.** Se usa la pieza continua mayor de cada unidad. Ajustar
  contra una línea con agujeros no significa nada.
- **No tocar el borde de la caja.** Una unidad cortada por el límite del
  estudio tiene un extremo inventado: el modelo debe reproducir una ruta hasta
  un punto que no es un destino sino donde pusimos el límite, y el corredor
  también queda cortado ahí. El paquete las detecta y avisa.

Cada unidad se analiza además en **su propia vecindad**: se extrae el
subgrafo de los nodos a menos de `buffer_corredor` de esa unidad. No es solo
por velocidad —el coste de un Dijkstra crece con el grafo entero— sino porque
el nulo debe preguntar «una ruta cualquiera *por aquí*, ¿se habría parecido
tanto?», y «por aquí» es la vecindad de esa unidad, no el área de estudio
completa.

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

## 8 bis. Qué cuenta como camino observado

El registro del Qhapaq Ñan no es una traza: clasifica cada segmento, y la
clase decide si ese segmento puede usarse para ajustar el modelo.

| Categoría | Qué es | ¿Sirve para ajustar? |
|---|---|---|
| Trazo de Camino | camino físico | sí |
| Camino Registrado | observado y formalmente registrado | sí |
| Camino Identificado | observado, identificado en campo | sí |
| Camino Afectado | observado, con daños | sí |
| Proyección por Reemplazo | lo tapó una carretera | **no** |
| Proyección por Daños | el tramo se destruyó | **no** |
| Proyección por Ausencia | no se encontró en campo | **no** |

Las tres de «Proyección» son tramos donde **el camino ya no está** y la línea
la dibujó alguien infiriendo por dónde iba. Ajustar un modelo de costo contra
una línea proyectada es circular: lo que se recupera son los supuestos de
quien la proyectó —que probablemente fueron, precisamente, que el camino
seguía la ruta más llevadera— y no el comportamiento de quien lo construyó.
El resultado saldría bien y no significaría nada.

El paquete excluye las tres por omisión (`datos.solo_observadas` en
`config.yaml`). En el tramo Chillo–Chachapoyas excluirlas no cuesta nada:
las proyecciones no alargan ni un metro la pieza continua mayor.

### Y `tramnomb` tampoco siempre nombra un tramo

El mismo campo lleva dos clases de valor. Casi todos son tramos, con forma
«A – B», pero **`En proceso` es un estado de trabajo**, no un lugar, y
aparece en rasgos de todo el país. Agrupado por nombre, su caja envolvente
mide 551 × 924 km de diagonal.

No es cosmético: si ese grupo pasa el filtro de longitud entra al análisis
como unidad, y entonces el perfil de equifinalidad compara los pesos de un
camino con los de una etiqueta administrativa. El filtro es la diagonal en
términos absolutos —el tramo con nombre más largo por aquí es
Chachapoyas–Jumbilla con 61 km— y no la dispersión relativa (diagonal
partido por longitud), porque los tramos del registro vienen en pedazos con
huecos y su diagonal ya excede su longitud, así que la razón relativa no
separa limpiamente.

Se aplica **antes** de recortar a la caja. Después, un grupo repartido por
el país parece local y la información que lo delataba está perdida.

Si en algún momento interesa usarlas, es para otra pregunta: contrastar por
dónde pasa el camino de mínimo costo contra por dónde se proyectó el tramo
perdido. Eso es una validación del registro, no un ajuste del modelo, y los
pesos tienen que venir ya fijados desde los sectores observados.

---

## 8 ter. Validación bloqueada: la prueba que decide

El nulo de §8 responde «¿este trazado se parece al observado más que una ruta
cualquiera por aquí?». No responde la otra pregunta, que es la del proyecto:
**¿el espacio ceremonial aporta algo, o el ampliado gana sólo por tener más
parámetros?**

Para eso, por cada unidad:

1. Se parte el trazado en $B = 4$ **bloques contiguos**.
2. Los pesos se estiman minimizando $\bar D$ sobre los $B-1$ bloques restantes.
3. Esos pesos, **sin recalibrar**, se evalúan sobre el bloque retenido.
4. Se repite con cada bloque como retenido, y se comparan los dos modelos
   bloque a bloque.

$$\mathbf{w}^{(-k)} = \arg\min_{\mathbf{w}\in\Delta}
\ \frac{1}{B-1}\sum_{b \ne k} D_b(\mathbf{w}),
\qquad\text{se reporta } D_k\!\left(\mathbf{w}^{(-k)}\right)$$

**Bloques contiguos y no una partición aleatoria**, y esto no es un detalle:
puntos espacialmente próximos comparten terreno, así que repartirlos al azar
entre ajuste y prueba filtra información de un lado al otro y el modelo parece
generalizar cuando sólo está recordando. Es el error estándar en validación de
modelos espaciales.

El resultado que vale es el conteo: **en cuántos de los bloques retenidos gana
el ampliado**. Si gana en la mitad o menos, la mejora que §5 reportaba era
capacidad de ajuste y no información espacial, y el paquete lo dice con esas
palabras en la consola. Es el único sitio del método donde el resultado puede
ser «las componentes añadidas no aportan», y tiene que poder serlo: si ningún
resultado posible refuta la hipótesis, no se está probando nada.

`python -m camino validar`. Código: `camino/pipeline.py`, `validar`.

## 9. Lo que este diseño no hace

- **No datea el camino.** Los pesos describen la relación entre una geometría y
  un terreno; no dicen cuándo se construyó ni en qué orden.
- **No prueba intención.** Que la pendiente explique un sector no significa que
  quien lo trazó estuviera minimizando energía: significa que el trazado es
  compatible con eso y no con las alternativas probadas.
- **No ve lo que no está en los datos de entrada.** Tenencia de tierras,
  estacionalidad, un puente que ya no existe, un sitio que nadie registró. Una
  unidad mal explicada puede estarlo por algo que no está medido, y conviene
  decirlo así en lugar de subir $K$ hasta que encaje.
- **No mide visibilidad real.** La componente de §3.2 es visibilidad potencial
  sobre terreno desnudo: ignora la vegetación —en bosque de neblina, con
  cobertura cerrada— y la niebla. Y no hay apu documentado para este corredor,
  así que mide intervisibilidad con los sitios y no «ver la montaña»: es otra
  variable que la del Coropuna, con el mismo nombre.
- **Depende del archivo de sitios tanto como del DEM.** Las dos componentes del
  modelo ampliado salen de ahí. Un catálogo incompleto, o uno que incluya
  sitios reconocidos *por* el camino, no da un resultado peor: da un resultado
  con la misma pinta y sin contenido.
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
  *Proceedings of the IEEE* 69(1), 14–47 — la ventana 3×3 de §3.1 bis.
- Sappington, J. M., Longshore, K. M. & Thompson, D. B. (2007). Quantifying
  landscape ruggedness for animal habitat analysis. *Journal of Wildlife
  Management* 71(5), 1419–1426 — el VRM de §3.2 bis.
- Beven, K. J. & Kirkby, M. J. (1979). A physically based, variable
  contributing area model of basin hydrology. *Hydrological Sciences Bulletin*
  24(1), 43–69 — el TWI de §3.3 bis.
- Barnes, R., Lehman, C. & Mulla, D. (2014). Priority-flood: an optimal
  depression-filling and watershed-labeling algorithm for digital elevation
  models. *Computers & Geosciences* 62, 117–127 — el relleno de §3.3 bis.
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
