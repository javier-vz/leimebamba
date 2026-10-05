"""Que caja haria falta para que los tramos entren completos.

Esto existe por un problema concreto del tramo Leimebamba - Chachapoyas: de
las seis unidades que pasan el filtro de largo, CUATRO llegan al borde de la
caja. Un tramo recortado tiene un extremo inventado -- no es un destino, es
donde pusimos el limite-- asi que sus pesos valen menos que los de una
unidad completa, y con dos unidades limpias el perfil de equifinalidad se
queda en UN par.

La decision (ensanchar o descartar) no la puede tomar el codigo, pero si
puede poner el numero delante: cuanto habria que ensanchar, y cuanto costaria
en celdas. `python -m camino caja`.

Se lee el archivo de origen SIN recortar, porque `datos/qn_geocam.gpkg` ya
viene cortado por la caja actual y ahi la informacion de donde terminan de
verdad los tramos esta perdida.
"""

from __future__ import annotations

import math

import numpy as np

MARGEN_GRADOS = 0.02        # ~2 km de aire alrededor de los extremos


def _bbox_grados(cfg, geometria):
    """Caja envolvente en grados de una geometria en el CRS de trabajo.

    De la GEOMETRIA y no del grupo entero: la unidad de analisis es la pieza
    continua mayor (es lo que usa `preparar.unidades`), asi que la caja que
    hace falta es la de esa pieza. Tomar la del grupo completo mete en la
    cuenta rasgos sueltos con el mismo nombre que no forman parte de la
    unidad, y propone una caja mas grande que la necesaria.
    """
    import geopandas as gpd
    g = gpd.GeoSeries([geometria], crs=cfg.crs).to_crs("EPSG:4326")
    return tuple(float(v) for v in g.total_bounds)   # oeste, sur, este, norte


def _celdas(cfg, bbox) -> tuple[int, int]:
    """Ancho y alto de la rejilla que cubriria esa caja, a la resolucion."""
    from rasterio.warp import transform_bounds

    res = cfg.resolucion
    xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", cfg.crs, *bbox,
                                             densify_pts=21)
    xmin, ymin = math.floor(xmin / res) * res, math.floor(ymin / res) * res
    xmax, ymax = math.ceil(xmax / res) * res, math.ceil(ymax / res) * res
    return int(round((xmax - xmin) / res)), int(round((ymax - ymin) / res))


def _une(cajas):
    """Caja que contiene a todas."""
    o = min(c[0] for c in cajas)
    s = min(c[1] for c in cajas)
    e = max(c[2] for c in cajas)
    n = max(c[3] for c in cajas)
    return o, s, e, n


def informe(cfg) -> dict:
    import geopandas as gpd
    from shapely.geometry import box

    from . import preparar, registro, ruta as _ruta

    fuente = _ruta.busca_archivo(cfg)
    if fuente is None:
        raise SystemExit(
            "No hay archivo de geometria en datos/, y de GeoCAM no se puede\n"
            "pedir la parte de fuera de la caja. Deja el KMZ del registro en\n"
            "datos/ y vuelve a correr esto.")
    print(f"  leyendo SIN recortar: {fuente.name}")
    qn = _ruta.desde_archivo(cfg, fuente)

    if "tramnomb" not in qn.columns:
        raise SystemExit(
            "Esta fuente no trae tramos con nombre, asi que no hay nada que\n"
            "medir por tramo (un GPX o unas trazas de OSM no los traen).")

    # Lo mismo que hace `ruta`: un grupo de 'tramnomb' repartido por el mapa
    # no es un tramo, y aqui pesa el doble porque arrastra la caja propuesta.
    qn, no_tramos = registro.separa_los_que_no_son_tramos(cfg, qn)
    if qn.empty:
        raise SystemExit("no quedo ningun tramo despues del filtro")

    caja_actual = tuple(cfg.bbox)
    recorte = gpd.GeoSeries([box(*caja_actual)],
                            crs="EPSG:4326").to_crs(cfg.crs)[0]

    filas = []
    for nombre, sub in qn.groupby(qn["tramnomb"].fillna("(sin nombre)")):
        try:
            pieza = preparar.lineas_unidas(sub)[0]       # la unidad real
        except (ValueError, IndexError):
            continue
        dentro = sub[sub.intersects(recorte)]
        if dentro.empty:
            continue
        cortado = gpd.clip(dentro, recorte)
        try:
            en_caja = preparar.lineas_unidas(cortado)[0].length
        except (ValueError, IndexError):
            en_caja = 0.0
        filas.append({
            "tramo": str(nombre),
            "continuo_en_la_caja_km": round(en_caja / 1000, 2),
            "continuo_completo_km": round(pieza.length / 1000, 2),
            "entra_completo": bool(pieza.length - en_caja < cfg.resolucion),
            "caja": _bbox_grados(cfg, pieza),
        })

    if not filas:
        raise SystemExit("ningun tramo de la fuente toca la caja actual")

    filas.sort(key=lambda f: -f["continuo_completo_km"])
    cuentan = [f for f in filas
               if f["continuo_completo_km"] * 1000 >= cfg.largo_min_unidad]

    print(f"\n  --- tramos, con y sin la caja actual ---")
    print(f"  {'tramo':34s} {'en caja':>9s} {'completo':>9s}  {'':3s}")
    for f in filas:
        marca = "" if f["entra_completo"] else "CORTADO"
        cuenta = "*" if f in cuentan else " "
        print(f"  {f['tramo'][:34]:34s} {f['continuo_en_la_caja_km']:9.2f} "
              f"{f['continuo_completo_km']:9.2f}  {cuenta} {marca}")
    print(f"  (km continuos; * pasa el filtro de "
          f"{cfg.largo_min_unidad / 1000:.0f} km)")
    print("\n  CORTADO quiere decir que el tramo SIGUE fuera de la caja, asi")
    print("  que ensancharla te daria mas unidad. No es lo mismo que el aviso")
    print("  de 'revisar', que marca la unidad cuyo trazado LLEGA al borde --")
    print("  ahi el extremo es un artefacto del encuadre. Un tramo puede")
    print("  seguir fuera sin tocar el borde, si un hueco del registro corta")
    print("  su pieza continua mayor antes de llegar.")

    ancho0, alto0 = _celdas(cfg, caja_actual)
    salida = {"caja_actual": caja_actual, "celdas_actuales": [ancho0, alto0],
              "tramos": [{k: v for k, v in f.items() if k != "caja"}
                         for f in filas]}

    print(f"\n  caja actual: {ancho0} x {alto0} = {ancho0 * alto0 / 1e6:.2f} "
          "millones de celdas")

    cortados = [f for f in cuentan if not f["entra_completo"]]
    if not cortados:
        print("\n  Todos los tramos que cuentan entran completos. No hay nada "
              "que decidir.")
        return salida

    # El coste de cada tramo POR SEPARADO, para ordenarlos de mas barato a
    # mas caro. No es aditivo -- dos tramos que se salen por el mismo lado
    # casi no suman-- y por eso despues va la tabla acumulada, que es la que
    # sirve para elegir.
    for f in cortados:
        nueva = _con_margen(_une([caja_actual, f["caja"]]))
        a, al = _celdas(cfg, nueva)
        f["celdas_solo"] = a * al
        f["factor_solo"] = round(a * al / (ancho0 * alto0), 2)
    cortados.sort(key=lambda f: f["celdas_solo"])

    print(f"\n  --- cuanto cuesta cada tramo cortado, por separado ---")
    for f in cortados:
        print(f"  {f['tramo'][:34]:34s} "
              f"{f['celdas_solo'] / 1e6:7.2f} M celdas  "
              f"{f['factor_solo']:5.1f}x")

    # La tabla que decide: anadiendo tramos de mas barato a mas caro, donde
    # esta el salto. Se eligen tramos, no coordenadas: la caja sale de ellos.
    print("\n  --- acumulado, anadiendo de mas barato a mas caro ---")
    print(f"  {'unidades completas':>18s} {'celdas':>12s} {'factor':>7s} "
          f"{'grafo':>9s}   ultimo tramo anadido")
    completas_ya = len([f for f in cuentan if f["entra_completo"]])
    acumulado = []
    for i, f in enumerate(cortados, start=1):
        bb = _con_margen(_une([caja_actual] + [c["caja"] for c in cortados[:i]]))
        a, al = _celdas(cfg, bb)
        fila = {
            "tramos_anadidos": [c["tramo"] for c in cortados[:i]],
            "unidades_completas": completas_ya + i,
            "bbox": bb, "celdas": [a, al],
            "factor": round(a * al / (ancho0 * alto0), 2),
            "memoria_grafo_gb": round(_memoria_gb(a * al, cfg.k), 2),
        }
        acumulado.append(fila)
        print(f"  {fila['unidades_completas']:18d} {a * al / 1e6:10.2f} M "
              f"{fila['factor']:6.1f}x {fila['memoria_grafo_gb']:7.2f} GB   "
              f"{f['tramo'][:32]}")
    salida["acumulado"] = acumulado

    print(f"\n  Con n unidades completas salen n(n-1)/2 pares para el perfil "
          "de")
    print("  equifinalidad: con 2 unidades hay 1 par (no se puede contrastar "
          "nada),")
    print("  con 4 hay 6, con 6 hay 15.")

    ultima = acumulado[-1]
    print("\n  Para quedarte en una fila cualquiera de esa tabla, copia su "
          "bbox.")
    print(f"  La ultima (todas) seria:")
    print(f"""
extension:
  bbox:
    oeste: {ultima['bbox'][0]}
    sur: {ultima['bbox'][1]}
    este: {ultima['bbox'][2]}
    norte: {ultima['bbox'][3]}
""")
    print("  Lo que crece con la caja son los pasos de UNA vez (bajar,")
    print("  preparar, superficies, grafo) y la memoria del grafo. El barrido")
    print("  y la validacion NO: trabajan sobre la vecindad de cada unidad,")
    print(f"  que sigue siendo la misma. Ahora el grafo pide "
          f"{_memoria_gb(ancho0 * alto0, cfg.k):.2f} GB con K = {cfg.k}.")
    salida["caja_para_todos"] = ultima["bbox"]
    salida["celdas_para_todos"] = ultima["celdas"]
    salida["factor"] = ultima["factor"]
    return salida


def _con_margen(bbox):
    """Caja con un poco de aire, redondeada a tres decimales de grado."""
    return (round(bbox[0] - MARGEN_GRADOS, 3), round(bbox[1] - MARGEN_GRADOS, 3),
            round(bbox[2] + MARGEN_GRADOS, 3), round(bbox[3] + MARGEN_GRADOS, 3))


def _memoria_gb(celdas, k, transitable=0.35, aristas_por_nodo=12.9) -> float:
    """Lo que ocuparia el grafo en memoria, a float64.

    Phi es (E, K) y es lo que manda. Los factores salen de la corrida real:
    35% de la caja transitable y 12.9 aristas por nodo con vecindad 16.
    """
    e = celdas * transitable * aristas_por_nodo
    return (e * k * 8 + e * 8 + e * 4) / 1024 ** 3
