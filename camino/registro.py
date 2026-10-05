"""Lectura del registro del Qhapaq Nan en KML/KMZ.

El KMZ del registro no es una traza suelta: trae las CATEGORIAS con que el
Ministerio clasifica cada segmento, cada una en su propia capa.

    Trazo de Camino                       camino fisico, observado
    Camino Registrado                     observado y formalmente registrado
    Camino Identificado                   observado, identificado en campo
    Camino Afectado                       observado, con danos
    Proyeccion de Camino por Reemplazo    INFERIDO: lo tapo una carretera
    Proyeccion de Camino por Danos        INFERIDO: el tramo se destruyo
    Proyeccion de Camino por Ausencia     INFERIDO: no se encontro en campo

La distincion no es burocratica, decide el estudio. Las tres de "Proyeccion"
son tramos donde el camino YA NO ESTA y la linea la dibujo alguien
infiriendo por donde iba. Ajustar un modelo de costo contra una linea
proyectada es circular: lo que se recupera son los supuestos de quien la
proyecto, no el comportamiento de quien construyo el camino. Por eso el
valor por omision solo incluye las cuatro capas observadas.

Los atributos (tramnomb, dptonomb, provnomb, distnomb, TipoCamino) no vienen
como campos: vienen dentro de una tabla HTML en el campo `description`, que
es como Google Earth guarda las tablas de atributos. Hay que extraerlos.
"""

from __future__ import annotations

import math
import pathlib
import re
import tempfile
import zipfile

OBSERVADAS = ("Trazo de Camino", "Camino Registrado",
              "Camino Identificado", "Camino Afectado")

PROYECTADAS = ("Proyeccion de Camino por Reemplazo",
               "Proyeccion de Camino por Danos",
               "Proyeccion de Camino por Ausencia")

# Campos que el registro guarda dentro del HTML de `description`.
CAMPOS = ("tramnomb", "longitud", "dptonomb", "provnomb", "distnomb",
          "ubigeo", "ccppprox", "TipoCamino")

_PAR = re.compile(r"<td>([^<>]+)</td>\s*\n*\s*<td>(.*?)</td>", re.S)
_ETIQUETA = re.compile(r"<[^>]+>")


def sin_tildes(s: str) -> str:
    """Compara nombres de capa sin depender de tildes ni mayusculas."""
    tabla = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    return str(s).translate(tabla).strip().lower()


def atributos(html) -> dict:
    """Saca los pares campo/valor de la tabla HTML de `description`."""
    if not isinstance(html, str) or "<td>" not in html:
        return {}
    return {k.strip(): _ETIQUETA.sub("", v).strip() for k, v in _PAR.findall(html)}


def abrir_kmz(ruta) -> pathlib.Path:
    """Un KMZ es un ZIP con un doc.kml dentro. Devuelve la ruta al KML."""
    ruta = pathlib.Path(ruta)
    if ruta.suffix.lower() != ".kmz":
        return ruta
    destino = pathlib.Path(tempfile.mkdtemp(prefix="kmz_"))
    with zipfile.ZipFile(ruta) as z:
        kmls = [n for n in z.namelist() if n.lower().endswith(".kml")]
        if not kmls:
            raise SystemExit(f"{ruta.name} no tiene ningun .kml dentro")
        z.extract(kmls[0], destino)
    return destino / kmls[0]


def capas(ruta) -> list[str]:
    """Nombres de las capas de un KML/KMZ."""
    import pyogrio
    return [str(c[0]) for c in pyogrio.list_layers(str(abrir_kmz(ruta)))]


def diagonal(gdf) -> float:
    """Diagonal de la caja envolvente de un grupo, en metros del CRS."""
    xmin, ymin, xmax, ymax = gdf.total_bounds
    return float(math.hypot(xmax - xmin, ymax - ymin))


def no_es_un_tramo(gdf, diagonal_max: float) -> str:
    """Razon por la que un grupo de `tramnomb` NO es un tramo, o "".

    Hace falta porque el registro usa el campo del nombre del tramo para dos
    cosas distintas. La mayoria de los valores son tramos de verdad, con
    forma "A - B". Pero hay al menos uno, "En proceso", que es un ESTADO DE
    TRABAJO del Ministerio y aparece en rasgos repartidos por todo el pais:
    agrupar por nombre lo convierte en un "tramo" cuya caja envolvente va de
    Ayacucho a Amazonas, 551 x 924 km.

    Eso no es un detalle cosmetico. Un grupo asi:

      - propone una caja de estudio 180 veces mas grande que la necesaria
      - y, si entrara al analisis como unidad, pondria a comparar los pesos
        de un camino contra los de una etiqueta administrativa.

    El criterio es la DIAGONAL, en terminos absolutos, y no la dispersion
    relativa (diagonal partido por largo): los tramos del registro vienen en
    pedazos con huecos, asi que su diagonal ya es mayor que su longitud y la
    razon relativa no separa limpiamente. Un tramo con nombre, en cambio,
    une dos lugares vecinos: el mas largo que aparece por aqui es
    Chachapoyas - Jumbilla con 61 km completos. Mil kilometros no es un
    tramo por ningun criterio.
    """
    d = diagonal(gdf)
    if d > diagonal_max:
        return (f"su caja envolvente mide {d / 1000:.0f} km de diagonal, "
                f"mas del limite de {diagonal_max / 1000:.0f} km: no es un "
                "tramo, es una etiqueta repartida por el mapa")
    return ""


def separa_los_que_no_son_tramos(cfg, qn):
    """Quita del registro los grupos de `tramnomb` que no son tramos.

    Devuelve (qn_limpio, [(nombre, razon)]). Se aplica ANTES de recortar a la
    caja: una vez recortado, un grupo disperso parece local y ya no se puede
    distinguir.
    """
    if "tramnomb" not in qn.columns:
        return qn, []

    nombres = qn["tramnomb"].fillna("(sin nombre)")
    fuera = []
    for nombre, sub in qn.groupby(nombres):
        if str(nombre) in cfg.tramos_excluidos:
            fuera.append((str(nombre), "excluido a mano en config.yaml "
                                       "(datos.tramos_excluidos)"))
            continue
        razon = no_es_un_tramo(sub, cfg.diagonal_max_tramo)
        if razon:
            fuera.append((str(nombre), razon))

    if not fuera:
        return qn, []

    descartados = {n for n, _ in fuera}
    print("\n  --- grupos de 'tramnomb' que NO son tramos ---")
    for nombre, razon in fuera:
        print(f"  '{nombre}': {razon}")
    print("  Se quitan del registro. Si alguno te interesa, sacalo de")
    print("  'datos.tramos_excluidos' o sube 'datos.diagonal_max_tramo'.")
    return qn[~nombres.isin(descartados)].copy(), fuera


def clasifica(nombre: str) -> str:
    """'observado', 'proyectado' u 'otro', segun el nombre de la capa."""
    n = sin_tildes(nombre)
    if any(sin_tildes(c) == n for c in OBSERVADAS):
        return "observado"
    if n.startswith("proyeccion de camino"):
        return "proyectado"
    return "otro"


def lee(ruta, crs_destino: str, solo_observadas: bool = True,
        capas_pedidas=None):
    """Lee un KML/KMZ del registro y devuelve un GeoDataFrame con atributos.

    Anade tres columnas propias: `capa` (la capa de origen), `categoria`
    ('observado' / 'proyectado') y los campos del registro extraidos del
    HTML.
    """
    import geopandas as gpd
    import pandas as pd

    kml = abrir_kmz(ruta)
    disponibles = capas(ruta)

    if capas_pedidas:
        pedidas = {sin_tildes(c) for c in capas_pedidas}
        elegidas = [c for c in disponibles if sin_tildes(c) in pedidas]
    elif solo_observadas:
        elegidas = [c for c in disponibles if clasifica(c) == "observado"]
    else:
        elegidas = [c for c in disponibles if clasifica(c) != "otro"]

    if not elegidas:
        raise SystemExit(
            f"Ninguna capa util en {pathlib.Path(ruta).name}.\n"
            f"Tiene: {disponibles}\n"
            "Si es un KMZ de otro sitio, pasa las capas a mano en config.yaml,"
            " en datos.capas_camino.")

    trozos = []
    for nombre in elegidas:
        g = gpd.read_file(kml, layer=nombre)
        g = g[~g.geometry.isna() & (g.geometry.geom_type
                                    .isin(["LineString", "MultiLineString"]))]
        if not len(g):
            continue
        at = pd.DataFrame([atributos(d) for d in g.get("description", [])],
                          index=g.index)
        salida = g[["geometry"]].copy()
        if "Name" in g:
            salida["nombre"] = g["Name"]
        for campo in CAMPOS:
            salida[campo] = at.get(campo)
        salida["capa"] = nombre
        salida["categoria"] = clasifica(nombre)
        trozos.append(salida)

    if not trozos:
        raise SystemExit("las capas elegidas no tienen ninguna polilinea")

    out = gpd.GeoDataFrame(pd.concat(trozos, ignore_index=True), crs=g.crs)
    return out.to_crs(crs_destino)


def tramos(gdf) -> "list[tuple[str, int, float, float]]":
    """Resumen por tramo: (nombre, rasgos, km totales, continuo mayor en km)."""
    from shapely.ops import linemerge, unary_union

    filas = []
    for nombre, g in gdf.groupby(gdf["tramnomb"].fillna("(sin nombre)")):
        geoms = [x for x in g.geometry if x is not None and not x.is_empty]
        if not geoms:
            continue
        u = unary_union(geoms)
        m = linemerge(u) if u.geom_type != "LineString" else u
        piezas = list(m.geoms) if m.geom_type == "MultiLineString" else [m]
        filas.append((str(nombre), len(g),
                      float(g.geometry.length.sum()) / 1000,
                      float(max(p.length for p in piezas)) / 1000))
    return sorted(filas, key=lambda f: -f[3])
