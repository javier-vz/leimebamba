"""De donde sale el camino observado.

GeoCAM es la fuente que corresponde, pero su servidor se cae, y cuando se
cae no hay nada que hacer desde aqui. El resto del estudio no tiene por que
quedarse parado por eso: esta parte acepta la geometria desde tres sitios.

    geocam    el servidor del Ministerio (WFS o ArcGIS REST). Lo correcto.
    archivo   un archivo tuyo: el GPX del Garmin de Dina, un KML, un
              shapefile, un GeoPackage, lo que tengas.
    osm       OpenStreetMap, como APAÑO PROVISIONAL para poder desarrollar
              y probar mientras GeoCAM no vuelve.

La de `osm` NO es el registro oficial y no puede sustituirlo en un
resultado publicable: son trazas cargadas por voluntarios, sin control de
precision ni criterio arqueologico. Sirve para que el codigo corra de punta
a punta y para ver si el modelo hace algo sensato; los numeros finales
salen de GeoCAM o de los tracks de campo.
"""

from __future__ import annotations

import json
import pathlib

import requests

FUENTES = ("geocam", "archivo", "osm")

# Extensiones que geopandas abre sin ayuda. El GPX trae varias capas y hay
# que decirle cual.
CAPAS_GPX = ("tracks", "routes", "track_points")


def desde_archivo(cfg, ruta):
    """Lee el camino de un archivo local y lo deja en el CRS de trabajo."""
    import geopandas as gpd
    import pandas as pd

    ruta = pathlib.Path(ruta)
    if not ruta.exists():
        raise SystemExit(f"No encuentro el archivo: {ruta}")

    if ruta.suffix.lower() == ".gpx":
        trozos = []
        for capa in CAPAS_GPX:
            try:
                g = gpd.read_file(ruta, layer=capa)
            except Exception:
                continue
            if len(g):
                g["capa_gpx"] = capa
                trozos.append(g)
            if capa in ("tracks", "routes") and trozos:
                break            # con lineas basta; los puntos son el plan B
        if not trozos:
            raise SystemExit(f"{ruta.name} no tiene ni tracks ni rutas")
        gdf = gpd.GeoDataFrame(pd.concat(trozos, ignore_index=True),
                               crs=trozos[0].crs)
    else:
        gdf = gpd.read_file(ruta)

    if gdf.crs is None:
        print("  AVISO: el archivo no dice en que CRS esta; asumo EPSG:4326")
        gdf = gdf.set_crs("EPSG:4326")
    return gdf.to_crs(cfg.crs)


def consulta_osm(bbox) -> str:
    """La consulta de Overpass para trazas que puedan ser el camino."""
    from . import osm
    return osm.consulta_camino(bbox)


def desde_osm(cfg, sesion=None):
    """Trazas de OpenStreetMap, como apano provisional."""
    from . import osm

    d = osm.consulta(osm.consulta_camino(cfg.bbox), sesion=sesion)
    g = osm.lineas(d, cfg.crs)

    if g.empty:
        raise SystemExit(
            "OpenStreetMap no tiene ninguna traza etiquetada como camino inca\n"
            "en esa caja. Queda importar un archivo propio:\n"
            "  python -m camino ruta --fuente archivo --archivo mi_camino.gpx")

    g["fuente"] = "osm_provisional"
    return g


def importar(cfg, fuente: str = "geocam", archivo=None, forzar: bool = False):
    """Deja el camino observado en datos/qn_geocam.gpkg, venga de donde venga."""
    from . import descarga

    destino = cfg.dir_datos / "qn_geocam.gpkg"
    if destino.exists() and not forzar:
        print(f"  ya esta: {destino.name}  (usa --forzar para rehacerlo)")
        return destino

    if fuente == "geocam":
        return descarga.camino_registrado(cfg, forzar=forzar)

    if fuente == "archivo":
        if not archivo:
            raise SystemExit("falta --archivo con la ruta del archivo a importar")
        print(f"  importando {archivo}")
        qn = desde_archivo(cfg, archivo)
    elif fuente == "osm":
        print("  bajando trazas de OpenStreetMap (APANO PROVISIONAL)")
        qn = desde_osm(cfg)
    else:
        raise SystemExit(f"fuente desconocida: {fuente}. Usa una de {FUENTES}")

    qn = descarga.recorta(qn, cfg)
    if qn.empty:
        raise SystemExit("no quedo nada dentro de la caja del tramo")

    qn.to_file(destino, layer="camino", driver="GPKG")
    descarga.resumen(qn)

    if fuente == "osm":
        print("\n  RECUERDA: esto es un apano para que el codigo corra.")
        print("  No es el registro del Ministerio y no vale para publicar.")
    return destino
