"""Del resultado a una salida de campo: zonas, estaciones y waypoints.

La tabla de `revisar` da una razon de costo por tramo. Una razon de 1.45
sobre 20 km no dice adonde ir: es un promedio, y el desvio que la produce
puede estar concentrado en un trecho de 2 km o repartido por todo el tramo.
Este paso la desarma.

Hace tres cosas, en este orden:

    1. ZONAS. Parte cada camino registrado en los trechos donde se aparta de
       la ruta del modelo, y a cada trecho le mide su PROPIA razon de costo,
       con los mismos dos extremos para las dos alternativas. Asi se ve
       donde esta el desvio y no solo cuanto vale en promedio.

    2. OBJETIVOS. Elige las zonas a las que vale la pena ir: las de mayor
       razon local que ademas sean recorribles, mas una zona de CONTROL en
       el tramo que el modelo mejor explica. El control no es un adorno: sin
       un caso donde el modelo acierta, cualquier cosa que se encuentre en
       los otros se puede atribuir a lo que uno quiera.

    3. ESTACIONES. Reparte puntos sobre cada zona, de tres tipos:

           A  sobre el camino registrado      comprueba el registro
           B  sobre la ruta del modelo        busca camino sin registro
           C  donde las dos rutas se separan  desde ahi se ven las dos opciones

       Las B son las que pueden cambiar el resultado: si aparece camino inca
       sobre la ruta que el modelo propone, el registro esta incompleto
       justo donde comparamos, y la separacion entre las dos lineas mide un
       hueco del registro y no una decision inca.

Sale un GPX para el GPS, un GeoPackage para QGIS y un CSV.
"""

from __future__ import annotations

import pathlib
import xml.etree.ElementTree as ET

import numpy as np

# Separacion desde la que dos rutas se consideran distintas. Por debajo de
# esto estamos dentro del error de digitalizacion del registro y de la celda
# del DEM, y la diferencia no significa nada.
UMBRAL_M = 250.0

# Una zona mas corta que esto es un bache de la digitalizacion, no un desvio.
LARGO_MIN_M = 500.0

# Y una mas larga que esto no es una salida de campo: es un tramo entero. Su
# desvio esta repartido, asi que no hay un lugar al que ir.
KM_MAX_ZONA = 20.0

# Se muestrea cada camino a la celda del DEM.
PASO_M = 30.0

# Donde caen las estaciones dentro de la zona. Tres es el minimo para poder
# decir "recorrimos la zona" y no "miramos un punto".
FRACCIONES = (0.25, 0.50, 0.75)

QUE_HACER = {
    "A": ("Ficha completa. Caminar 200 m en cada sentido y anotar si la "
          "plataforma sigue o se corta."),
    "B": ("Ficha completa. Caminar 300 m a cada lado, cruzado a la ruta, "
          "buscando plataforma, piedras alineadas o terrazas de camino. Si "
          "el terreno no deja, anotar hasta donde se llego."),
    "C": ("Ficha completa. Foto panoramica, y anotar que se ve de cada una "
          "de las dos rutas desde aqui."),
}


def perfil(obs, mod, paso: float = PASO_M):
    """Separacion entre las dos rutas a lo largo del camino registrado."""
    n = max(int(obs.length // paso) + 1, 2)
    s = np.linspace(0.0, obs.length, n)
    puntos = [obs.interpolate(float(x)) for x in s]
    return s, puntos, np.array([p.distance(mod) for p in puntos])


def zonas(s, d, umbral: float = UMBRAL_M, largo_min: float = LARGO_MIN_M):
    """Trechos contiguos por encima del umbral, con sus bordes.

    El borde se toma un paso ANTES de cruzar el umbral: ahi las dos rutas
    todavia van juntas, y es el unico lugar desde el que alguien que fuera
    caminando habria visto las dos opciones.
    """
    alto = d > umbral
    salida, i = [], 0
    while i < len(alto):
        if not alto[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(alto) and alto[j + 1]:
            j += 1
        if s[j] - s[i] >= largo_min:
            salida.append({"i": max(i - 1, 0), "j": min(j + 1, len(s) - 1),
                           "k": i + int(np.argmax(d[i:j + 1]))})
        i = j + 1
    return salida


def _alternativa(obs, mod, a, b):
    """El trozo de la ruta del modelo que corresponde a una zona."""
    from shapely.ops import nearest_points, substring

    sa = mod.project(nearest_points(a, mod)[1])
    sb = mod.project(nearest_points(b, mod)[1])
    return substring(mod, min(sa, sb), max(sa, sb))


def mide_zonas(cfg, rev, unidades=None) -> list[dict]:
    """Una fila por zona, con su razon de costo LOCAL.

    La razon local se calcula igual que la del tramo: el costo de seguir el
    trazado observado entre los dos extremos de la zona, dividido por el
    costo del camino mas barato entre esos mismos dos extremos. Los extremos
    son los mismos para las dos, que es lo que hace comparable el cociente.
    """
    from scipy.sparse.csgraph import dijkstra
    from shapely.ops import substring

    from . import pipeline, preparar

    g, t, uds = pipeline._carga_unidades(cfg)
    w = np.zeros(len(g.nombres))
    w[0] = 1.0

    filas = []
    for nombre, linea in uds:
        if unidades and nombre not in unidades:
            continue
        obs = _linea(rev, nombre, "observado")
        mod = _linea(rev, nombre, "modelado")
        if obs is None or mod is None:
            continue

        s, puntos, d = perfil(obs, mod)
        zs = zonas(s, d)
        if not zs:
            continue

        sub, _, _, _, t6 = pipeline._contexto(cfg, g, t, linea,
                                              con_componentes=False)
        costos = sub.costos(w)

        for n, z in enumerate(zs, 1):
            a, b = puntos[z["i"]], puntos[z["j"]]
            trozo = substring(obs, s[z["i"]], s[z["j"]])

            fc = preparar.filcol_de_xy(np.array([[a.x, a.y], [b.x, b.y]]), t)
            na = sub.nodo_mas_cercano(*fc[0])
            nb = sub.nodo_mas_cercano(*fc[1])
            c_opt = float(dijkstra(costos, directed=True, indices=na)[nb])
            c_obs, _ = pipeline.costo_de_seguir_el_trazado(
                cfg, g, t6, trozo, w, (a.x, a.y), (b.x, b.y))

            alterna = _alternativa(obs, mod, a, b)
            filas.append({
                "tramo": nombre, "zona": n,
                "desde_km": round(s[z["i"]] / 1000, 2),
                "hasta_km": round(s[z["j"]] / 1000, 2),
                "largo_registrado_km": round(trozo.length / 1000, 2),
                "largo_alternativa_km": round(alterna.length / 1000, 2),
                "separacion_max_m": round(float(d[z["k"]])),
                "razon_local": round(float(c_obs / c_opt), 3) if c_opt else
                float("nan"),
                "_obs": obs, "_mod": mod, "_a": a, "_b": b, "_trozo": trozo,
                "_alterna": alterna,
            })
    return filas


def elige(filas, razones_de_tramo, cuantas: int = 4,
          km_max: float = KM_MAX_ZONA) -> list[dict]:
    """Las zonas a las que se va: las peores recorribles, mas un control.

    Una zona de 41 km no es un destino aunque su razon sea alta: su desvio
    esta repartido y no hay un lugar al que llegar. Por eso el filtro de
    largo va ANTES de ordenar por razon.

    El control sale del tramo que el modelo mejor explica, y entra siempre,
    tenga la razon que tenga. Es lo que permite saber como se ve sobre el
    terreno un acuerdo bueno; sin eso, lo que se encuentre en los otros no
    tiene con que compararse.
    """
    cortas = [f for f in filas if f["largo_registrado_km"] <= km_max]
    objetivos = sorted(cortas, key=lambda f: -f["razon_local"])[:cuantas]

    if razones_de_tramo:
        mejor = min(razones_de_tramo, key=razones_de_tramo.get)
        del_control = [f for f in cortas if f["tramo"] == mejor]
        if del_control and not any(f["tramo"] == mejor for f in objetivos):
            objetivos.append(max(del_control,
                                 key=lambda f: f["largo_registrado_km"]))

    for n, f in enumerate(objetivos, 1):
        f["prioridad"] = n
        f["control"] = (razones_de_tramo or {}).get(f["tramo"]) == min(
            (razones_de_tramo or {1: 1}).values())
    return objetivos


def estaciones(objetivos, dem=None) -> list[dict]:
    """Los puntos a visitar, de los tres tipos, repartidos por zona."""
    codigos = _codigos(objetivos)
    salida = []
    for f in objetivos:
        cod = codigos[(f["tramo"], f["zona"])]
        puntos = [(f["_a"], "C", "donde las dos rutas se separan"),
                  (f["_b"], "C", "donde las dos rutas se vuelven a juntar")]
        for x in FRACCIONES:
            p = f["_trozo"].interpolate(x, normalized=True)
            km = f["desde_km"] + x * (f["hasta_km"] - f["desde_km"])
            puntos.append((p, "A",
                           f"camino registrado, km {km:.1f} del tramo"))
        if f["_alterna"].length > 0:
            for x in FRACCIONES:
                p = f["_alterna"].interpolate(x, normalized=True)
                sep = p.distance(f["_obs"])
                puntos.append((p, "B", "ruta del modelo, a "
                                       f"{sep:.0f} m del camino registrado"))

        for n, (p, tipo, nota) in enumerate(puntos, 1):
            salida.append({
                "codigo": f"{cod}-{n:02d}", "tipo": tipo,
                "prioridad": f["prioridad"], "control": bool(f["control"]),
                "tramo": f["tramo"], "zona": f["zona"],
                "razon_local": f["razon_local"], "nota": nota,
                "altitud_m": _altitud(dem, p), "geometry": p,
            })
    return salida


def escribe_gpx(puntos, destino: pathlib.Path) -> None:
    """Un waypoint por estacion, con su tipo y su instruccion en la nota.

    La nota importa: un waypoint sin ella es un punto al que se llega sin
    saber que mirar, y eso en campo es un dia perdido.
    """
    ET.register_namespace("", "http://www.topografix.com/GPX/1/1")
    raiz = ET.Element("{http://www.topografix.com/GPX/1/1}gpx",
                      {"version": "1.1", "creator": "camino"})
    for p in puntos:
        wpt = ET.SubElement(raiz, "wpt", {"lat": f"{p['lat']:.6f}",
                                          "lon": f"{p['lon']:.6f}"})
        ET.SubElement(wpt, "name").text = p["codigo"]
        if p.get("altitud_m") is not None:
            ET.SubElement(wpt, "ele").text = str(p["altitud_m"])
        ET.SubElement(wpt, "desc").text = (
            f"TIPO {p['tipo']} | prioridad {p['prioridad']} | {p['tramo']} | "
            f"{p['nota']} | {QUE_HACER[p['tipo']]}")
    ET.ElementTree(raiz).write(destino, encoding="UTF-8",
                               xml_declaration=True)


def informe(cfg) -> dict:
    """`python -m camino campo`: las zonas, las estaciones y los archivos."""
    import geopandas as gpd

    rev = _lee_revision(cfg)
    razones = _razones_de_tramo(cfg)

    filas = mide_zonas(cfg, rev)
    if not filas:
        raise SystemExit(
            "Ninguna zona pasa el umbral: las dos rutas van juntas en todos\n"
            "los tramos. No hay nada que ir a ver, y eso es un resultado.")

    _tabla_de_zonas(filas, razones)
    objetivos = elige(filas, razones)
    pts = estaciones(objetivos, dem=_dem(cfg))

    g = gpd.GeoDataFrame(pts, crs=rev.crs)
    w84 = g.to_crs("EPSG:4326")
    g["lat"], g["lon"] = w84.geometry.y.round(6), w84.geometry.x.round(6)

    destino = cfg.dir_resultados
    destino.mkdir(parents=True, exist_ok=True)
    g.to_file(destino / "estaciones.gpkg", layer="estaciones", driver="GPKG")
    g.drop(columns="geometry").to_csv(destino / "estaciones.csv", index=False)
    escribe_gpx(g.to_dict("records"), destino / "estaciones.gpx")

    _tabla_de_estaciones(g)
    print(f"\n  -> {destino / 'estaciones.gpx'}  (para el GPS o el celular)")
    print(f"  -> {destino / 'estaciones.gpkg'}  (para QGIS)")
    print(f"  -> {destino / 'estaciones.csv'}")
    return {"zonas": [{k: v for k, v in f.items() if not k.startswith("_")}
                      for f in filas],
            "estaciones": g.drop(columns="geometry").to_dict("records")}


# ------------------------------------------------------------- auxiliares

def _linea(rev, tramo: str, clase: str):
    sel = rev[(rev["unidad"] == tramo) & (rev["clase"] == clase)]
    return None if sel.empty else sel["geometry"].iloc[0]


def _codigos(objetivos) -> dict:
    """Un codigo corto y UNICO por zona, para los waypoints.

    Los primeros caracteres del nombre no bastan: 'Chachapoyas - Jumbilla' y
    'Chachapoyas - Cochamal' empiezan igual, y dos zonas distintas con el
    mismo codigo de waypoint es un error que no se nota hasta estar en campo
    con el GPS. Un tramo puede ademas aportar dos zonas. Asi que el codigo
    se construye y despues se desambigua contando.
    """
    import re

    usados, salida = {}, {}
    for f in objetivos:
        palabras = [p for p in re.split(r"[^0-9A-Za-zNn]+",
                                        f["tramo"].upper()) if p]
        base = "".join(p[:2] for p in palabras[:2])[:4] or "ZON"
        n = usados.get(base, 0)
        usados[base] = n + 1
        salida[(f["tramo"], f["zona"])] = base if n == 0 else f"{base}{n + 1}"
    return salida


def _altitud(dem, p):
    if dem is None:
        return None
    v = float(list(dem.sample([(p.x, p.y)], 1))[0][0])
    return None if v < -1000 else round(v)


def _dem(cfg):
    import rasterio
    ruta = cfg.dir_derivados / "cop30.tif"
    return rasterio.open(ruta) if ruta.exists() else None


def _lee_revision(cfg):
    import geopandas as gpd

    ruta = cfg.dir_resultados / "revision_pendiente.gpkg"
    if not ruta.exists():
        raise SystemExit(
            "Falta resultados/revision_pendiente.gpkg.\n"
            "Este paso trabaja sobre las dos lineas que produce `revisar`:\n"
            "la registrada y la modelada. Corre antes:\n"
            "    python -m camino revisar")
    return gpd.read_file(ruta, layer="revision")


def _razones_de_tramo(cfg) -> dict:
    import json

    ruta = cfg.dir_resultados / "revision_grafo.json"
    if not ruta.exists():
        return {}
    return {r["unidad"]: r["razon_de_costo"] for r in json.loads(
        ruta.read_text())}


def _tabla_de_zonas(filas, razones) -> None:
    print("\n  --- donde se concentra el desvio de cada tramo ---")
    print(f"  {'tramo':30s} {'zona, km':>13s} {'regis':>6s} {'alter':>6s} "
          f"{'razon':>6s} {'tramo':>6s}")
    for f in sorted(filas, key=lambda x: -x["razon_local"]):
        print(f"  {f['tramo'][:30]:30s} "
              f"{f['desde_km']:5.1f}-{f['hasta_km']:<7.1f} "
              f"{f['largo_registrado_km']:5.1f} "
              f"{f['largo_alternativa_km']:6.1f} {f['razon_local']:6.2f} "
              f"{razones.get(f['tramo'], float('nan')):6.2f}")
    print("\n  regis  km del camino registrado en la zona.")
    print("  alter  km de la ruta del modelo entre los mismos dos extremos.")
    print("  razon  lo que cuesta la zona dividido por lo que cuesta esa")
    print("         alternativa. La ultima columna es la del tramo entero:")
    print("         si la local es mucho mayor, el desvio esta concentrado")
    print("         ahi y el resto del tramo va pegado al modelo.")


def _tabla_de_estaciones(g) -> None:
    print(f"\n  --- {len(g)} estaciones en "
          f"{g['tramo'].nunique()} zona(s) ---")
    print(f"  {'codigo':8s} {'tipo':4s} {'pri':>3s} {'altura':>7s}  nota")
    for _, r in g.iterrows():
        marca = " (control)" if r["control"] else ""
        print(f"  {r['codigo']:8s} {r['tipo']:4s} {r['prioridad']:3d} "
              f"{r['altitud_m'] or 0:6d} m  {r['nota']}{marca}")
    print("\n  A  sobre el camino registrado: comprueba que ahi hay camino.")
    print("  B  sobre la ruta del modelo: busca camino donde el registro no")
    print("     tiene nada. Es la que puede cambiar el resultado.")
    print("  C  donde las dos rutas se separan: el unico punto desde el que")
    print("     se ven las dos opciones.")
