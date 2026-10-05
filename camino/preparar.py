"""Alineacion de rasteres, mascara del corredor y particion en sectores.

Dos DEM distintos solo son comparables si caen en la MISMA rejilla: mismo
CRS, misma resolucion, mismo origen, misma forma. Aqui se impone eso de una
vez, y todo lo que venga despues asume que se cumple.
"""

from __future__ import annotations

import math
import pathlib

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds


def rejilla(cfg):
    """Rejilla comun: (transform, ancho, alto), pegada a multiplos de la
    resolucion para que dos corridas cualquiera caigan en las mismas celdas."""
    res = cfg.resolucion
    xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", cfg.crs, *cfg.bbox,
                                              densify_pts=21)
    xmin = math.floor(xmin / res) * res
    ymin = math.floor(ymin / res) * res
    xmax = math.ceil(xmax / res) * res
    ymax = math.ceil(ymax / res) * res
    ancho = int(round((xmax - xmin) / res))
    alto = int(round((ymax - ymin) / res))
    return from_origin(xmin, ymax, res, res), ancho, alto


def escribe(ruta, datos, transform, crs, nodata=np.nan):
    """Guarda un raster float32 comprimido, con el mismo perfil siempre."""
    datos = np.asarray(datos, dtype=np.float32)
    perfil = dict(driver="GTiff", height=datos.shape[0], width=datos.shape[1],
                  count=1, dtype="float32", crs=crs, transform=transform,
                  nodata=nodata, compress="deflate", predictor=2, tiled=True)
    with rasterio.open(ruta, "w", **perfil) as dst:
        dst.write(datos, 1)
    return pathlib.Path(ruta)


def lee(ruta):
    """Devuelve (datos float64 con nodata como nan, transform, crs)."""
    with rasterio.open(ruta) as src:
        a = src.read(1, masked=True).astype(np.float64).filled(np.nan)
        return a, src.transform, src.crs


def alinear(cfg, entradas: dict[str, str | pathlib.Path]) -> dict[str, pathlib.Path]:
    """Reproyecta y recorta cada entrada a la rejilla comun.

    `bilinear` se usa SOLO aqui, sobre el DEM. Nunca se remuestrea una
    superficie derivada: se remuestrea el DEM y se vuelve a derivar.
    """
    transform, ancho, alto = rejilla(cfg)
    salidas = {}
    for nombre, ruta in entradas.items():
        destino = cfg.dir_derivados / f"{nombre}.tif"
        with rasterio.open(ruta) as src:
            out = np.full((alto, ancho), np.nan, dtype=np.float32)
            reproject(source=rasterio.band(src, 1), destination=out,
                      src_transform=src.transform, src_crs=src.crs,
                      src_nodata=src.nodata,
                      dst_transform=transform, dst_crs=cfg.crs,
                      dst_nodata=np.nan, resampling=Resampling.bilinear)
        salidas[nombre] = escribe(destino, out, transform, cfg.crs)
        print(f"  {nombre}: {alto} x {ancho} celdas a {cfg.resolucion:g} m")
    return salidas


def banda_incertidumbre(a, b) -> dict:
    """Diferencia entre los dos DEM: la incertidumbre vertical, gratis.

    No es un chequeo de calidad, es un numero que va en el articulo: dice
    cuanta de la variacion del costo de pendiente es terreno y cuanta es el
    DEM que elegiste.
    """
    d = np.abs(np.asarray(a, dtype=np.float64) - np.asarray(b, dtype=np.float64))
    d = d[np.isfinite(d)]
    if d.size == 0:
        return {}
    return {"mediana_m": round(float(np.median(d)), 2),
            "p90_m": round(float(np.percentile(d, 90)), 2),
            "max_m": round(float(d.max()), 2)}


# -------------------------------------------------------------- corredor

def lineas_unidas(camino):
    """Une las polilineas del camino registrado en el menor numero de piezas.

    Pasa por `unary_union` antes de coser. El registro llega como
    MultiLineString por rasgo, y `linemerge` sobre esa lista no junta los
    segmentos que se tocan entre rasgos distintos: sin este paso, el camino
    disponible se subestima -- en el tramo Chillo-Chachapoyas, 7.96 km en
    vez de los 12.40 km reales.
    """
    from shapely.ops import linemerge, unary_union

    geoms = [g for g in camino.geometry
             if g is not None and not g.is_empty
             and g.geom_type in ("LineString", "MultiLineString")]
    if not geoms:
        raise ValueError("el camino registrado no tiene ninguna polilinea")
    u = unary_union(geoms)
    unido = linemerge(u) if u.geom_type != "LineString" else u
    piezas = list(unido.geoms) if unido.geom_type == "MultiLineString" else [unido]
    return sorted(piezas, key=lambda g: g.length, reverse=True)


def mascara_corredor(cfg, camino, agua_geoms=None):
    """Mascara booleana: corredor alrededor del camino, menos el agua.

    El corredor existe por computo: la caja completa son millones de celdas
    y no se barren. Pero un buffer estrecho DECIDE el resultado, asi que
    despues de cada corrida hay que comprobar que el camino modelado no
    toque el borde (`metricas.toca_borde`).
    """
    from rasterio.features import geometry_mask

    transform, ancho, alto = rejilla(cfg)
    piezas = lineas_unidas(camino)
    buffer = [p.buffer(cfg.buffer_corredor) for p in piezas]

    dentro = ~geometry_mask(buffer, out_shape=(alto, ancho), transform=transform,
                            invert=False, all_touched=True)
    if agua_geoms:
        agua = ~geometry_mask(list(agua_geoms), out_shape=(alto, ancho),
                              transform=transform, all_touched=True)
        dentro &= ~agua
    return dentro, transform


def sectores(camino, n: int):
    """Parte la pieza continua mas larga en `n` sectores de igual longitud.

    Se usa la pieza MAS LARGA, no todas: un sector que mezcla dos piezas
    separadas por un vacio de registro no es un sector, es un artefacto.
    """
    from shapely.ops import substring

    linea = lineas_unidas(camino)[0]
    largo = linea.length
    if n < 1:
        raise ValueError("hace falta al menos un sector")
    if largo / n < 500:
        raise ValueError(
            f"la pieza continua mide {largo:.0f} m: partirla en {n} sectores "
            f"deja {largo / n:.0f} m cada uno, menos de 20 celdas. "
            f"Usa menos sectores o valida en bloques, pero no las dos cosas.")

    salida = []
    for i in range(n):
        trozo = substring(linea, largo * i / n, largo * (i + 1) / n)
        salida.append((f"s{i + 1}", trozo))
    return salida


def filcol_de_xy(xy, transform):
    """Fila y columna de coordenadas proyectadas (inverso de grafo.xy)."""
    inv = ~transform
    xy = np.asarray(xy, dtype=np.float64)
    cols, fils = inv @ (xy[:, 0], xy[:, 1])
    return np.column_stack([np.floor(np.asarray(fils)).astype(np.int64),
                            np.floor(np.asarray(cols)).astype(np.int64)])


def vertices(geom, paso=None):
    """Vertices de una polilinea como array (n, 2); remuestrea si se da paso."""
    from shapely import get_coordinates
    if paso:
        n = max(2, int(math.ceil(geom.length / paso)) + 1)
        pts = [geom.interpolate(geom.length * k / (n - 1)) for k in range(n)]
        return np.array([[p.x, p.y] for p in pts])
    return get_coordinates(geom)
