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
    """Consulta Overpass de trazas que puedan ser el camino.

    Se piden las vias con etiqueta `historic` y las que llevan 'inca',
    'qhapaq' o 'camino' en el nombre. No se piden todos los senderos: en los
    Andes hay miles y ninguno dice de cual se trata.
    """
    oeste, sur, este, norte = bbox
    caja = f"{sur},{oeste},{norte},{este}"
    return (
        "[out:json][timeout:180];"
        f'(way["historic"]({caja});'
        f' way["name"~"[Ii]nca|[Qq]hapaq|[Cc]amino|[Ññ]an"]({caja});'
        f' relation["route"="hiking"]({caja});'
        f' way["highway"="path"]["name"~"[Ii]nca|[Qq]hapaq"]({caja}););'
        "out geom;")


def desde_osm(cfg, sesion=None):
    """Trazas de OpenStreetMap, como apano provisional."""
    import geopandas as gpd
    from shapely.geometry import LineString

    sesion = sesion or requests.Session()
    r = sesion.get("https://overpass-api.de/api/interpreter",
                   params={"data": consulta_osm(cfg.bbox)}, timeout=300)
    r.raise_for_status()
    d = r.json()

    filas, geoms = [], []
    for el in d.get("elements", []):
        pts = [(p["lon"], p["lat"]) for p in el.get("geometry", []) or []]
        if len(pts) < 2:
            continue
        tags = el.get("tags", {})
        filas.append({"osm_id": el.get("id"),
                      "nombre": tags.get("name", ""),
                      "historic": tags.get("historic", ""),
                      "highway": tags.get("highway", ""),
                      "fuente": "osm_provisional"})
        geoms.append(LineString(pts))

    if not geoms:
        raise SystemExit(
            "OpenStreetMap no tiene ninguna traza etiquetada como camino inca\n"
            "en esa caja. Queda importar un archivo propio:\n"
            "  python -m camino ruta --archivo mi_camino.gpx")

    return gpd.GeoDataFrame(filas, geometry=geoms,
                            crs="EPSG:4326").to_crs(cfg.crs)


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
