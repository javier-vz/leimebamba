"""Los pasos del estudio, en orden, cada uno dejando su salida en disco.

El orden NO es decorativo. El paso `nulos` va antes que `barrido_sectores`
porque un sector cuyo mejor camino no le gana a terreno aleatorio no tiene
pesos que reportar, y compararle los pesos a otro sector seria comparar dos
numeros sin contenido.
"""

from __future__ import annotations

import json

import numpy as np

from . import (barrido, costo, descarga, equifinalidad, grafo, hidrologia,
               metricas, nulos, preparar, superficies)


def _guarda_json(cfg, nombre, obj):
    ruta = cfg.dir_resultados / nombre
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, default=float)
    print(f"  -> {ruta.relative_to(cfg.raiz)}")
    return ruta


# ------------------------------------------------------------- 1. bajar

def bajar(cfg, forzar=False):
    print("DEM (dos fuentes, para tener la banda de incertidumbre):")
    rutas = descarga.dems(cfg, forzar=forzar)
    print("\nCuerpos de agua (OpenStreetMap) -- opcional:")
    descarga.agua(cfg, forzar=forzar)
    print("\nLa red de drenaje no se baja: se deriva del DEM en 'superficies'.")
    return rutas


# --------------------------------------------------------- 2. preparar

def preparar_rasteres(cfg):
    import geopandas as gpd

    print("Alineando los dos DEM a la rejilla comun:")
    salidas = preparar.alinear(cfg, {
        "cop30": cfg.dir_datos / "cop30_raw.tif",
        "aw3d30": cfg.dir_datos / "aw3d30_raw.tif"})

    a, t, _ = preparar.lee(salidas["cop30"])
    b, _, _ = preparar.lee(salidas["aw3d30"])
    banda = preparar.banda_incertidumbre(a, b)
    print(f"  incertidumbre vertical entre fuentes: {banda}")

    ruta_camino = cfg.dir_datos / "qn_geocam.gpkg"
    if ruta_camino.exists():
        print("Mascara del corredor:")
        camino = gpd.read_file(ruta_camino, layer="camino")
        agua_geoms = _agua_geoms(cfg)
        mascara, _ = preparar.mascara_corredor(cfg, camino, agua_geoms)
    else:
        print("Sin camino observado todavia: la mascara es la caja entera.")
        print("  Puedes seguir con 'superficies', que no lo necesita. Para")
        print("  'grafo' en adelante si hace falta: `python -m camino ruta`.")
        mascara = np.isfinite(a)

    preparar.escribe(cfg.dir_derivados / "mascara.tif",
                     mascara.astype(np.float32), t, cfg.crs, nodata=0)
    print(f"  {int(mascara.sum())} celdas transitables de {mascara.size} "
          f"({100 * mascara.mean():.1f}%)")

    _guarda_json(cfg, "incertidumbre_vertical.json", banda)
    return salidas


def _agua_geoms(cfg):
    """Geometrias de agua de la respuesta de Overpass, ya reproyectadas."""
    ruta = cfg.dir_datos / "agua_osm.json"
    if not ruta.exists():
        return []
    import geopandas as gpd
    from shapely.geometry import LineString, Polygon

    with open(ruta, encoding="utf-8") as f:
        d = json.load(f)
    geoms = []
    for el in d.get("elements", []):
        pts = [(p["lon"], p["lat"]) for p in el.get("geometry", []) or []]
        if len(pts) < 2:
            continue
        if el.get("tags", {}).get("natural") == "water" and pts[0] == pts[-1]:
            geoms.append(Polygon(pts))
        else:
            geoms.append(LineString(pts).buffer(15.0))
    if not geoms:
        return []
    return list(gpd.GeoSeries(geoms, crs="EPSG:4326").to_crs(cfg.crs))


# ------------------------------------------------------ 3. superficies

def construir_superficies(cfg):
    """Las componentes del costo, cada una normalizada y guardada."""
    dem, t, _ = preparar.lee(cfg.dir_derivados / "cop30.tif")
    mascara = preparar.lee(cfg.dir_derivados / "mascara.tif")[0] > 0.5
    mascara &= np.isfinite(dem)
    res = cfg.resolucion

    print("Pendiente y aspecto (Horn, sobre el DEM SIN rellenar):")
    S, A = superficies.pendiente_aspecto(dem, res, valido=mascara)

    print("Rugosidad (VRM):")
    rug = superficies.vrm(S, A)

    print("Hidrologia (el relleno de depresiones se usa SOLO aqui):")
    relleno = hidrologia.rellenar(dem, mascara)
    dirs = hidrologia.d8(relleno, res, valido=mascara)
    acc = hidrologia.acumulacion(dirs, valido=mascara, z_relleno=relleno)
    sca = hidrologia.area_especifica(acc, res)
    n_cauce = int(hidrologia.cauces(acc, cfg.umbral_quebrada).sum())
    print(f"  {n_cauce} celdas de quebrada con umbral {cfg.umbral_quebrada:g}")

    crudas = {
        "rugosidad": rug,
        "drenaje": superficies.phi_drenaje(acc),
        "humedad": superficies.twi(sca, S),
    }

    comps = {}
    for nombre in cfg.componentes_simetricas:
        if nombre not in crudas:
            raise SystemExit(f"no se como calcular la componente '{nombre}'")
        comps[nombre] = costo.normaliza(crudas[nombre], mascara,
                                        cfg.percentiles, cfg.epsilon)
        preparar.escribe(cfg.dir_derivados / f"phi_{nombre}.tif",
                         comps[nombre], t, cfg.crs)
        v = comps[nombre][mascara]
        print(f"  phi_{nombre}: mediana {np.nanmedian(v):.3f}, "
              f"rango {np.nanmin(v):.3f}-{np.nanmax(v):.3f}")

    preparar.escribe(cfg.dir_derivados / "pendiente_rad.tif", S, t, cfg.crs)
    preparar.escribe(cfg.dir_derivados / "acumulacion.tif", acc, t, cfg.crs)
    return comps


# ------------------------------------------------------------ 4. grafo

def construir_grafo(cfg):
    dem, t, _ = preparar.lee(cfg.dir_derivados / "cop30.tif")
    mascara = preparar.lee(cfg.dir_derivados / "mascara.tif")[0] > 0.5
    comps = {n: preparar.lee(cfg.dir_derivados / f"phi_{n}.tif")[0]
             for n in cfg.componentes_simetricas}

    print(f"Grafo con vecindad {cfg.vecindad} y g_max = {cfg.g_max}:")
    g = grafo.construir(dem, mascara, comps, cfg.resolucion,
                        g_max=cfg.g_max, vecinos=cfg.vecinos)
    print(f"  {g.n} nodos, {g.e} aristas ({g.e / g.n:.1f} por nodo)")
    print(f"  componentes: {g.nombres}")

    ruta = cfg.dir_derivados / "grafo.npz"
    g.guardar(ruta)
    print(f"  -> {ruta.relative_to(cfg.raiz)}")
    return g


def revisar_grafo(cfg):
    """Un solo Dijkstra con todo el peso en la pendiente, para mirarlo.

    Si ESTE camino no es plausible sobre el terreno, nada de lo que sigue lo
    es. Es el paso que no se salta.
    """
    import geopandas as gpd
    from scipy.sparse.csgraph import dijkstra
    from shapely.geometry import LineString

    g = grafo.Grafo.cargar(cfg.dir_derivados / "grafo.npz")
    t = preparar.rejilla(cfg)[0]
    camino = gpd.read_file(cfg.dir_datos / "qn_geocam.gpkg", layer="camino")
    linea = preparar.lineas_unidas(camino)[0]

    fc = preparar.filcol_de_xy(np.array([linea.coords[0], linea.coords[-1]]), t)
    o = g.nodo_mas_cercano(*fc[0])
    d = g.nodo_mas_cercano(*fc[1])

    w = np.zeros(len(g.nombres))
    w[0] = 1.0
    _, pred = dijkstra(g.costos(w), directed=True, indices=o,
                       return_predecessors=True)
    cam = grafo.recorre(pred, o, d)
    if cam.size == 0:
        raise SystemExit("no hay camino entre los extremos: revisa la mascara")

    xy = grafo.xy(g.filcol[cam], tuple(t)[:6])
    obs = preparar.vertices(linea, paso=cfg.resolucion)
    mascara = preparar.lee(cfg.dir_derivados / "mascara.tif")[0] > 0.5

    info = {
        "nodos": g.n, "aristas": g.e,
        "largo_modelado_km": round(metricas.longitud(xy) / 1000, 2),
        "largo_observado_km": round(linea.length / 1000, 2),
        "distancia_media_m": round(metricas.distancia_media_simetrica(xy, obs), 1),
        "frechet_m": round(metricas.frechet_discreta(xy, obs), 1),
        "toca_borde_del_corredor": bool(metricas.toca_borde(g.filcol[cam], mascara)),
    }
    for k, v in info.items():
        print(f"  {k}: {v}")
    if info["toca_borde_del_corredor"]:
        print("\n  AVISO: el camino modelado toca el borde del corredor. Es el")
        print("  buffer el que esta decidiendo el resultado: ensanchalo en")
        print("  config.yaml (dominio.buffer_corredor) y vuelve a correr.")

    gpd.GeoDataFrame(geometry=[LineString(xy)], crs=cfg.crs).to_file(
        cfg.dir_resultados / "revision_pendiente.gpkg", driver="GPKG")
    _guarda_json(cfg, "revision_grafo.json", info)
    return info


# ------------------------------------------- 5. nulos, antes del barrido

def correr_nulos(cfg):
    """Un nulo por sector, con el espectro de la superficie real.

    Sale ANTES del barrido: los sectores que no le ganan al nulo quedan
    fuera del analisis de pesos y se reportan como tales.
    """
    import geopandas as gpd
    from scipy.sparse.csgraph import dijkstra

    g = grafo.Grafo.cargar(cfg.dir_derivados / "grafo.npz")
    t = preparar.rejilla(cfg)[0]
    t6 = tuple(t)[:6]
    camino = gpd.read_file(cfg.dir_datos / "qn_geocam.gpkg", layer="camino")
    secs = preparar.sectores(camino, cfg.n_sectores)

    ref = preparar.lee(cfg.dir_derivados / f"phi_{cfg.componentes_simetricas[0]}.tif")[0]
    beta = nulos.beta_espectral(ref)
    print(f"  exponente espectral de la superficie real: beta = {beta:.2f}")

    rng = np.random.default_rng(cfg.semilla)
    salida = {}
    for nombre, trozo in secs:
        obs = preparar.vertices(trozo, paso=cfg.resolucion)
        fc = preparar.filcol_de_xy(np.array([trozo.coords[0], trozo.coords[-1]]), t)
        o, d = g.nodo_mas_cercano(*fc[0]), g.nodo_mas_cercano(*fc[1])

        ds = np.full(cfg.m_nulos, np.inf)
        for m in range(cfg.m_nulos):
            g._csr.data[:] = g.L * _nulo_por_arista(g, beta, rng, cfg)
            _, pred = dijkstra(g._csr, directed=True, indices=o,
                               return_predecessors=True)
            cam = grafo.recorre(pred, o, d)
            if cam.size:
                ds[m] = metricas.distancia_media_simetrica(
                    grafo.xy(g.filcol[cam], t6), obs)
        salida[nombre] = ds
        print(f"  {nombre}: nulo mediano {np.nanmedian(ds):.0f} m")

    np.savez_compressed(cfg.dir_derivados / "nulos.npz", beta=beta, **salida)
    return salida


def _nulo_por_arista(g, beta, rng, cfg):
    """Una superficie nula convertida a costo por arista.

    El campo se genera sobre la rejilla completa y se promedia entre los dos
    extremos de cada arista, igual que una componente simetrica real: asi el
    nulo tiene la misma estructura que lo que se esta probando.
    """
    campo = nulos.superficie_nula(g.forma, beta, rng, cfg.epsilon, cfg.percentiles)
    plano = campo.ravel()
    org = g.filcol[:, 0] * g.forma[1] + g.filcol[:, 1]
    valor = np.empty(g.n)
    valor[:] = plano[org]
    filas = np.repeat(np.arange(g.n), np.diff(g._csr.indptr))
    return 0.5 * (valor[filas] + valor[g._csr.indices])


# -------------------------------------------------------- 6. el barrido

def barrer(cfg):
    import geopandas as gpd

    g = grafo.Grafo.cargar(cfg.dir_derivados / "grafo.npz")
    t = preparar.rejilla(cfg)[0]
    t6 = tuple(t)[:6]
    camino = gpd.read_file(cfg.dir_datos / "qn_geocam.gpkg", layer="camino")
    secs = preparar.sectores(camino, cfg.n_sectores)

    red = barrido.red_simplex(len(g.nombres), cfg.n_simplex)
    print(f"  red del simplex: {len(red)} vectores de peso "
          f"(K = {len(g.nombres)}, h = {1 / cfg.n_simplex:g})")

    nul = {}
    ruta_nulos = cfg.dir_derivados / "nulos.npz"
    if ruta_nulos.exists():
        nul = dict(np.load(ruta_nulos))

    D_por_sector, tablas = {}, []
    for nombre, trozo in secs:
        obs = preparar.vertices(trozo, paso=cfg.resolucion)
        fc = preparar.filcol_de_xy(np.array([trozo.coords[0], trozo.coords[-1]]), t)
        o, d = g.nodo_mas_cercano(*fc[0]), g.nodo_mas_cercano(*fc[1])

        D, largos, caminos = barrido.barre(g, red, o, d, obs, t6,
                                           n_trabajos=cfg.n_trabajos)
        D_por_sector[nombre] = D

        fila = barrido.tabla_optimo(D, largos, red, g.nombres, trozo.length)
        fila["sector"] = nombre
        if nombre in nul:
            fila["p_nulo"] = round(nulos.p_empirico(float(np.nanmin(D)),
                                                    nul[nombre]), 4)
            fila["piso_p"] = round(nulos.piso_p(cfg.m_nulos), 4)
        i = int(np.nanargmin(D))
        m = equifinalidad.conjunto_casi_optimo(D, 0.10)
        fila["casi_optimos_tau10"] = int(m.sum())
        for k, nom in enumerate(g.nombres):
            lo, hi = equifinalidad.extension(red, m)[k]
            fila[f"{nom}_tau10"] = f"{lo:.2f}-{hi:.2f}"
        tablas.append(fila)
        print(f"  {nombre}: {fila}")

    np.savez_compressed(cfg.dir_derivados / "barrido.npz",
                        red=red, **D_por_sector)
    _guarda_json(cfg, "optimos_por_sector.json", tablas)
    return D_por_sector, red


# ---------------------------------------------------- 7. equifinalidad

def resultados(cfg):
    """El perfil de Jaccard: la respuesta a la pregunta del proyecto."""
    d = np.load(cfg.dir_derivados / "barrido.npz")
    red = d["red"]
    D_por_sector = {k: d[k] for k in d.files if k != "red"}

    taus = np.linspace(0.0, cfg.tau_max, 26)
    taus, perfiles = equifinalidad.perfil_jaccard(D_por_sector, taus)

    salida = {"taus": taus.tolist(), "pares": {}}
    for (s, t), j in perfiles.items():
        salida["pares"][f"{s}|{t}"] = j.tolist()
        print(f"  J({s},{t}): tau=0.05 -> {j[2]:.2f}   tau=0.25 -> {j[13]:.2f}")

    salida["centroides"] = {
        s: equifinalidad.centroide(
            red, equifinalidad.conjunto_casi_optimo(D, 0.10)).tolist()
        for s, D in D_por_sector.items()}

    _guarda_json(cfg, "perfil_equifinalidad.json", salida)
    _figura_perfil(cfg, taus, perfiles)
    return salida


def _figura_perfil(cfg, taus, perfiles):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.5, 4.6), dpi=160)
    for (s, t), j in sorted(perfiles.items()):
        ax.plot(taus, j, lw=1.4, label=f"{s} vs {t}")
    ax.set_xlabel("tau (margen relativo sobre el optimo)")
    ax.set_ylabel("Jaccard de los conjuntos casi-optimos")
    ax.set_ylim(-0.02, 1.02)
    ax.grid(alpha=0.25, lw=0.5)
    ax.legend(fontsize=7, ncol=2, frameon=False)
    ax.set_title("Separacion de los conjuntos de pesos entre sectores")
    fig.tight_layout()
    ruta = cfg.dir_resultados / "perfil_equifinalidad.png"
    fig.savefig(ruta)
    plt.close(fig)
    print(f"  -> {ruta.relative_to(cfg.raiz)}")
    return ruta
