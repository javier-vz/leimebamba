"""Optimizacion inversa de pesos de terreno sobre el camino inca.

Tramo Leimebamba - Chachapoyas, Amazonas.

La pregunta no es "por donde paso el camino" (eso ya esta registrado) sino
"que variables del terreno explican por donde paso, y si esas variables son
las mismas a lo largo de todo el tramo".

Modulos, en el orden en que se usan:

    config         parametros del proyecto, leidos de config.yaml
    descarga       DEM, camino registrado en GeoCAM, agua
    preparar       alinear rasteres, mascara del corredor, sectores
    superficies    pendiente, aspecto, rugosidad (VRM), TWI
    hidrologia     relleno de depresiones, D8, acumulacion
    costo          Minetti, normalizacion de componentes
    grafo          grafo dirigido de vecindad 16 y la matriz Phi
    barrido        red del simplex y el barrido de pesos
    metricas       distancia media simetrica y Frechet discreta
    nulos          campos gaussianos y el valor p empirico
    equifinalidad  conjuntos casi-optimos y el perfil de Jaccard
"""

__version__ = "0.1.0"
