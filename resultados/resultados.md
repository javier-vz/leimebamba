# Resultados Leimebamba–Chachapoyas

Javier Vera Zúñiga · 6 de octubre de 2026

En cinco de los seis tramos del Qhapaq Ñan que analizamos en Amazonas, el camino registrado resulta **más barato de caminar que cualquiera de las 500 rutas alternativas** que generamos sobre el mismo terreno. En el sexto, Pauja – Santa Cruz, no: ahí el camino real es más caro que el 73% de las alternativas, y da una vuelta que el terreno no explica. Ése es el tramo que conviene mirar en campo.

## Qué se midió, en palabras

El método responde tres preguntas, y cada una corrige un problema de la anterior.

**Primera: ¿el camino va por donde caminar cuesta menos?** Para cada tramo calculamos la ruta de menor esfuerzo entre sus dos extremos y la comparamos con el trazado registrado. «Esfuerzo» no es distancia: es la energía que cuesta caminar en cada pendiente, medida en laboratorio por Minetti y sus colegas en 2002. Bajar suave sale más barato que el plano; subir al 45% sale siete veces más caro. La comparación da una separación media en metros.

**Segunda: ¿y si la separación engaña?** Dos rutas pueden ir por sitios distintos y costar casi lo mismo. En un valle ancho hay muchas maneras de pasar por un precio parecido, así que el modelo puede estar lejos del camino real sin equivocarse en nada. Para separar eso medimos cuánto cuesta recorrer **el trazado real**, dividido por lo que cuesta la ruta más barata. Si sale 1.03, el camino real cuesta un 3% más que lo mínimo posible: el modelo no lo ubica exactamente, pero el camino sí es barato.

**Tercera: ¿1.45 es mucho o poco?** Esa razón no significa nada por sí sola, porque no hay con qué compararla. Así que generamos **500 rutas alternativas por tramo**: caminos de menor costo entre los mismos dos extremos, pero sobre terrenos sintéticos con la misma textura que el real. Son el conjunto de control. A cada una le medimos lo mismo, y entonces la pregunta tiene respuesta: ¿el camino real es barato comparado con las rutas que alguien podría haber tomado por ahí?

## Qué se estima y qué está fijado

El costo de cruzar de una celda a su vecina es una suma ponderada:

$$
c_{ij} = L_{ij} \sum_{k=1}^{K} w_k \, \varphi_k(i,j),
\qquad \sum_{k=1}^{K} w_k = 1, \quad w_k \ge 0
$$

Los **pesos** `w` son lo único que se estima, y no se fijan a mano: se buscan los que hacen que el camino de mínimo costo se parezca más al trazado registrado. Que sumen 1 es lo que los hace comparables entre tramos: sin esa restricción, `w` y `2w` dan exactamente el mismo camino, el óptimo no es único, y la frase «en este tramo manda la pendiente» no quiere decir nada.

**Y en los resultados de este documento no hay ningún peso estimado**, porque sólo hay una componente activa: el costo físico. Con una componente el símplex es un punto y `w = [1]`. Lo que aquí se reporta no es todavía una optimización inversa — es un camino de mínimo costo y su comparación contra el conjunto de control. La optimización empieza cuando entra la componente ceremonial: con dos componentes son 21 juegos de pesos (paso 1/20 del símplex), con tres son 231.

Todo lo demás está **fijado antes de ver el resultado**, y eso es deliberado:

| Fijado de antemano | Valor | Por qué no se ajusta |
| --- | --- | --- |
| Curva de costo metabólico | Minetti *et al.* 2002 | medida en laboratorio, R² = 0.999 |
| Pendiente máxima transitable | ±45% | borde de validez de ese ajuste; más allá la polinomial se dispara |
| Normalización de componentes | percentiles 5–95 | que un píxel de ruido del DEM no fije la escala |
| Rugosidad como restricción | percentil 99 | separa «por aquí no se pasa» de «por aquí es caro» |
| Media anchura del corredor | 4 km | límite de cómputo, declarado y comprobado |
| Vecindad del grafo | 16 | con 8, los caminos se alargan hasta un 8.2% |
| Saturación de la proximidad | 5 km | que un sitio aislado no domine medio corredor |

Si esos umbrales se ajustaran junto con los pesos, el modelo tendría tantos grados de libertad que explicaría cualquier trazado, y el resultado no sería refutable.

## De dónde salen los datos

El trazado observado viene del **registro del Ministerio de Cultura**, en el KMZ que publica GEO GPS Perú. El modelo de elevación es Copernicus GLO-30, a 30 m por celda, y se bajó también AW3D30 para medir cuánta de la variación del costo es terreno y cuánta es la fuente elegida: entre las dos fuentes la diferencia mediana es de 2.4 m y el percentil 99 es de 19.6 m.

Del registro se usó **sólo lo observado**. El Ministerio clasifica cada segmento, y tres de sus categorías —«Proyección de Camino por Reemplazo», «por Daños» y «por Ausencia»— son tramos donde el camino ya no está y la línea la dibujó alguien infiriendo por dónde iba. Ajustar un modelo de costo contra una línea proyectada es circular: lo que se recupera son los supuestos de quien la proyectó, que probablemente fueron justamente que el camino seguía la ruta más llevadera.

También hubo que descartar tres grupos del campo `tramnomb`, porque ese campo lleva dos clases de valor. La mayoría son tramos de verdad, con forma «A – B», pero **«En proceso» es un estado de trabajo**, no un lugar, y aparece en rasgos repartidos por todo el país: agrupado por nombre, su caja envolvente va de Ayacucho a Amazonas. Aparece además con dos grafías distintas, «En proceso» y «En Proceso», que el registro trata como grupos separados. Con el nombre vacío, son 381 km de línea sin tramo asignado.

Un defecto parecido, que vale anotar aunque no afecte a esta zona: `Huarautambo - Huancaspata` aparece dos veces, una con guión corto y otra con guión largo.

Quedaron **seis tramos con al menos 8 km continuos**, 169 km en total. Para que entraran completos hubo que ensanchar la caja de estudio hasta 6.4 millones de celdas: con la caja mínima sólo Chillo – Chachapoyas entraba entero, y con una sola unidad completa no hay nada que comparar entre tramos.

## El resultado

Cada número es lo que cuesta recorrer una ruta dividido por lo que cuesta el
óptimo del modelo. 1.00 sería el óptimo mismo.

| Tramo | Camino registrado | Rutas de control (p25 / mediana / p75) | *p* |
| --- | --- | --- | --- |
| Chillo – Chachapoyas | **1.03** | 1.68 / 2.00 / 2.57 | 0.002 |
| La Jalca – Mendoza | **1.11** | 1.55 / 1.71 / 1.88 | 0.002 |
| Leymebamba – Chilchos – Mendoza | **1.16** | 1.62 / 1.78 / 1.98 | 0.002 |
| Chachapoyas – Cochamal | **1.17** | 1.78 / 2.10 / 2.45 | 0.002 |
| Chachapoyas – Jumbilla | **1.25** | 1.79 / 1.95 / 2.15 | 0.002 |
| Pauja – Santa Cruz | **1.45** | 1.22 / 1.30 / 1.47 | 0.729 |

En los cinco primeros tramos el camino registrado cuesta menos que el cuarto
más barato de las 500 rutas de control: su valor cae por debajo del p25 de la
banda. Ninguna de las 500 lo igualó, así que *p* está en su piso, $1/(M+1)$
con $M = 500$. En Pauja – Santa Cruz el valor cae **dentro** de la banda y por
encima de su mediana.

Lo que estos números muestran y la separación en metros esconde: Leymebamba –
Chilchos y Chachapoyas – Jumbilla están a más de 1 500 m del trazado modelado,
y sin embargo su camino es barato. En esos valles hay muchas rutas que cuestan
parecido, así que el terreno restringe el **costo** del camino sin fijar su
**posición**. Eso es equifinalidad espacial, y con la distancia sola parecía un
fracaso del modelo.

## Los seis tramos, uno por uno

La separación media entre el trazado modelado y el registrado varía de 155 m a 1 909 m. La sinuosidad es el largo recorrido dividido por la distancia en línea recta entre los extremos: 1.00 sería una recta.

| Tramo | Registrado | Modelado | Separación media | Fréchet | Sinuosidad obs / mod |
| --- | --- | --- | --- | --- | --- |
| Chillo – Chachapoyas | 12.40 km | 11.78 km | 155 m | 515 m | 1.24 / 1.17 |
| La Jalca – Mendoza | 28.19 km | 27.66 km | 336 m | 1 564 m | 1.19 / 1.17 |
| Chachapoyas – Cochamal | 17.70 km | 18.26 km | 555 m | 2 249 m | 1.19 / 1.22 |
| Leymebamba – Chilchos – Mendoza | 29.29 km | 26.86 km | 1 524 m | 4 333 m | 1.31 / 1.20 |
| Chachapoyas – Jumbilla | 61.19 km | 50.66 km | 1 566 m | 5 388 m | 1.75 / 1.45 |
| Pauja – Santa Cruz | 20.72 km | 10.46 km | 1 909 m | 3 808 m | 2.37 / 1.20 |

A 30 m de resolución, los 155 m de Chillo – Chachapoyas son cinco celdas: para 12.4 km de camino, el modelo lo ubica prácticamente encima.

Un detalle que va al revés de lo esperado: en **Chachapoyas – Cochamal** el camino modelado es más largo y más sinuoso que el real (18.26 km contra 17.70, sinuosidad 1.22 contra 1.19). El camino de verdad es más recto que el óptimo del modelo. Eso sugiere que los constructores aceptaban pendientes más duras de lo que la curva de Minetti penaliza, o que hay obra —escalinatas, cortes, muros de contención— que abarata lo empinado y el modelo no ve.

## Pauja – Santa Cruz: el tramo que el terreno no explica

Es el único de los seis donde el camino real **no** es barato. Recorre 20.72 km entre dos puntos que están a 8.75 km en línea recta, y el terreno los conecta en 10.46 km. Sinuosidad 2.37 contra 1.20. Caminarlo cuesta un 45% más que la ruta más barata, y el 73% de las rutas alternativas que generamos son más baratas que él.

Eso da dos explicaciones posibles, y hay que descartar una antes de contar la otra.

**Que no sea un camino.** Las unidades se arman cosiendo los segmentos del registro que se tocan, y si un tramo tiene una horquilla, la pieza resultante podría ser una rama de ida y otra de vuelta unidas por un vértice. Entonces los «extremos» del tramo serían los dos cabos de una Y, y ajustar un modelo de costo contra eso no significa nada. Un rodeo y una horquilla dan la misma sinuosidad, así que la sinuosidad no lo decide.

Lo que sí lo decide es si la línea **vuelve sobre sí misma**. Un rodeo real es un arco que se aleja de sí mismo; una horquilla pasa dos veces casi por el mismo sitio. Medido: la línea de Pauja – Santa Cruz nunca se acerca a menos de **362 m** de sí misma entre puntos separados por más de 1 km de recorrido, y su giro más brusco es de 135°. Para comparar, Chillo – Chachapoyas —la unidad mejor explicada de todas— tiene un giro de 130°, así que giros de ese orden son geometría normal de camino en este registro. Las seis unidades quedan entre 362 y 859 m de autoproximidad.

**Entonces el rodeo es real.** Y es el único resultado del conjunto que pide una explicación que no sea el costo de caminar. Es también, por eso, el mejor caso de prueba para la componente de espacios ceremoniales.

Lo que esta comprobación **no** descarta, y conviene decirlo así: que dos caminos distintos se hayan unido por un extremo compartido con un ángulo moderado. Eso seguiría pareciendo un trazado continuo. Cerrarlo necesita los atributos del registro (`ccppprox`, `categoria`) o una mirada al mapa.

## Lo que falta: el catálogo de espacios ceremoniales

Todo lo anterior es el modelo de **referencia**: sólo costo físico. La pregunta del proyecto es si añadir la relación con los espacios ceremoniales explica el trazado mejor que el terreno solo, y eso necesita un dato que el programa no puede bajar: el catálogo de sitios de Amazonas.

Basta un archivo en `datos/` cuyo nombre empiece por `sitios`. Acepta GeoPackage, shapefile, GeoJSON, KMZ o un CSV simple:

```csv
nombre,lon,lat
Nombre del sitio,-77.925,-6.418
```

Acepta puntos y polígonos, y los reproyecta solos. Los sitios pueden caer fuera de la caja de estudio: uno a 2 km del borde sigue condicionando las celdas de dentro y se usa igual.

### Las dos reglas que hay que aplicarle

Vienen del diseño del proyecto, no son técnicas, y cambian el resultado.

1. **Un sitio que se reconoció *por* el camino no puede explicar el camino.** Si la identificación de un lugar dependió principalmente de estar junto a la vía, usarlo como predictor es circular. Esto el programa **no lo puede decidir**: es criterio arqueológico y se filtra al armar el archivo. Es la decisión más importante de todo este paso.
2. **Un sitio en el extremo del tramo analizado se excluye de su componente.** Si no, el modelo recibe como premio acercarse a un punto al que de todas formas tiene que llegar, y la componente mide el enunciado del problema en vez del paisaje. Esta sí la hace el programa, tramo por tramo, y dice en pantalla cuántos sitios quitó.

Con el archivo puesto, quedan tres pasos: el barrido de pesos (unos 6 minutos), la validación bloqueada (unos 20 minutos) y las figuras. La validación es la que decide: estima los pesos dejando fuera un pedazo del trazado y los mide **sobre ese pedazo**, sin recalibrar. El modelo ampliado tiene más parámetros, así que ajusta mejor por construcción sobre los datos con que se estimó; si no gana también en los bloques retenidos, la mejora era capacidad de ajuste y no información espacial.

Y eso también es un resultado publicable. El diseño permite que la respuesta sea «el espacio ceremonial no añade nada», y tiene que permitirlo: si ningún resultado posible refutara la hipótesis, no se estaría probando nada.

### Las coordenadas sensibles

Los Excel de campo llevan ubicaciones exactas de evidencias. Esos crudos no entran al repositorio público; las carpetas de datos están excluidas del control de versiones y todo lo que hay en ellas se regenera corriendo los pasos. Lo que se publique pasa antes por las restricciones institucionales que correspondan.

## Lo que este trabajo no muestra

- **No datea el camino.** Los pesos describen la relación entre una geometría y un terreno; no dicen cuándo se construyó ni en qué orden.
- **No prueba intención.** Que el costo físico explique un tramo no significa que quien lo trazó estuviera minimizando energía: significa que el trazado es compatible con eso y no con las alternativas probadas.
- **No mide visibilidad.** Para el corredor del Utcubamba no hay apu documentado —la documentación de los sitios Chachapoya del valle describe una relación con el paisaje en conjunto, con sitios colocados para ser «muy visibles desde lejos», no un cerro tutelar con nombre—, así que la componente de visibilidad del proyecto del Coropuna no se transfiere tal cual. Está implementada en su forma transferible, la intervisibilidad con los propios sitios, y está apagada.
- **Hereda el modelo de elevación.** Sobre un DEM de 30 m no hay escalinatas, ni calzada, ni muros de contención. El caso de Chachapoyas – Cochamal, donde el camino real es más recto que el óptimo, probablemente sea eso.
- **Depende del catálogo de sitios tanto como del DEM.** Un catálogo incompleto, o uno que incluya sitios reconocidos por el camino, no dará un resultado peor: dará un resultado con la misma pinta y sin contenido.

Y una decisión de parametrización declarada: el grafo usa vecindad de 16 y no de 8. Con 8 vecinos los caminos sólo giran en pasos de 45° y se alargan hasta un 8.2%; con 16 el sesgo baja al 2.8%. El proyecto original especifica 8, y se puede correr con 8 para comparar.
