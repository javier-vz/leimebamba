"""Rejilla comun, mascara del corredor, sectores, y las URL de descarga."""

import numpy as np
import pytest

from camino import config, descarga, grafo, preparar


@pytest.fixture
def cfg():
    return config.Config.cargar()


# ------------------------------------------------------------- la rejilla

def test_la_rejilla_queda_pegada_a_multiplos_de_la_resolucion(cfg):
    t, ancho, alto = preparar.rejilla(cfg)
    assert t.a == pytest.approx(cfg.resolucion)
    assert t.e == pytest.approx(-cfg.resolucion)
    assert t.c % cfg.resolucion == pytest.approx(0.0)
    assert t.f % cfg.resolucion == pytest.approx(0.0)
    assert ancho > 1000 and alto > 1000


def test_la_rejilla_cubre_el_tramo_entero(cfg):
    """Leimebamba y Chachapoyas tienen que caer dentro."""
    from rasterio.warp import transform as reproj
    t, ancho, alto = preparar.rejilla(cfg)
    lon = [-77.80, -77.872]          # Leimebamba, Chachapoyas
    lat = [-6.70, -6.229]
    xs, ys = reproj("EPSG:4326", cfg.crs, lon, lat)
    inv = ~t
    for x, y in zip(xs, ys):
        c, f = inv @ (x, y)
        assert 0 < f < alto and 0 < c < ancho


def test_la_rejilla_es_reproducible(cfg):
    assert preparar.rejilla(cfg) == preparar.rejilla(cfg)


# ---------------------------------------------- ida y vuelta de coordenadas

def test_filcol_y_xy_son_inversas(cfg):
    t, _, _ = preparar.rejilla(cfg)
    fc = np.array([[0, 0], [17, 423], [999, 1200]])
    xy = grafo.xy(fc, tuple(t)[:6])
    assert np.array_equal(preparar.filcol_de_xy(xy, t), fc)


# ----------------------------------------------------- lineas y sectores

def _camino_recto(largo=30000.0, x0=170000.0, y0=9270000.0, crs="EPSG:32718"):
    import geopandas as gpd
    from shapely.geometry import LineString
    linea = LineString([(x0, y0), (x0, y0 + largo)])
    return gpd.GeoDataFrame({"id": [1]}, geometry=[linea], crs=crs)


def test_lineas_unidas_ordena_de_mayor_a_menor():
    import geopandas as gpd
    from shapely.geometry import LineString
    g = gpd.GeoDataFrame(geometry=[
        LineString([(0, 0), (0, 100)]),
        LineString([(500, 0), (500, 5000)]),
    ], crs="EPSG:32718")
    piezas = preparar.lineas_unidas(g)
    assert [round(p.length) for p in piezas] == [5000, 100]


def test_lineas_unidas_cose_los_tramos_contiguos():
    import geopandas as gpd
    from shapely.geometry import LineString
    g = gpd.GeoDataFrame(geometry=[
        LineString([(0, 0), (0, 1000)]),
        LineString([(0, 1000), (0, 3000)]),
    ], crs="EPSG:32718")
    piezas = preparar.lineas_unidas(g)
    assert len(piezas) == 1
    assert piezas[0].length == pytest.approx(3000.0)


def test_lineas_unidas_falla_sin_polilineas():
    import geopandas as gpd
    from shapely.geometry import Point
    g = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:32718")
    with pytest.raises(ValueError, match="polilinea"):
        preparar.lineas_unidas(g)


def test_los_sectores_parten_la_pieza_en_partes_iguales():
    g = _camino_recto(30000.0)
    secs = preparar.sectores(g, 6)
    assert [n for n, _ in secs] == ["s1", "s2", "s3", "s4", "s5", "s6"]
    assert all(t.length == pytest.approx(5000.0) for _, t in secs)
    assert sum(t.length for _, t in secs) == pytest.approx(30000.0)


def test_los_sectores_se_tocan_de_punta_a_punta():
    secs = preparar.sectores(_camino_recto(12000.0), 4)
    for (_, a), (_, b) in zip(secs, secs[1:]):
        assert a.coords[-1] == pytest.approx(b.coords[0])


def test_sectores_se_niega_si_quedarian_demasiado_cortos():
    """Es el aviso que importa: con poco camino continuo, sectores y
    validacion bloqueada compiten por los mismos metros."""
    g = _camino_recto(2000.0)
    with pytest.raises(ValueError, match="sectores"):
        preparar.sectores(g, 6)


def test_vertices_remuestrea_al_paso_pedido():
    g = _camino_recto(3000.0)
    linea = preparar.lineas_unidas(g)[0]
    v = preparar.vertices(linea, paso=30.0)
    assert len(v) >= 100
    paso = np.linalg.norm(np.diff(v, axis=0), axis=1)
    assert paso.max() <= 30.5


# -------------------------------------------------------- el corredor

def test_la_mascara_del_corredor_tiene_el_ancho_pedido(cfg):
    g = _camino_recto(20000.0)
    m, t = preparar.mascara_corredor(cfg, g)
    assert m.dtype == bool
    assert m.any()
    # el ancho del corredor en celdas, medido en la fila central
    fila = np.flatnonzero(m.any(axis=1))
    centro = fila[len(fila) // 2]
    ancho_celdas = int(m[centro].sum())
    esperado = 2 * cfg.buffer_corredor / cfg.resolucion
    assert ancho_celdas == pytest.approx(esperado, rel=0.05)


def test_el_corredor_deja_fuera_el_agua(cfg):
    from shapely.geometry import Point
    g = _camino_recto(20000.0)
    sin_agua, t = preparar.mascara_corredor(cfg, g)
    laguna = Point(170000.0, 9280000.0).buffer(600.0)
    con_agua, _ = preparar.mascara_corredor(cfg, g, agua_geoms=[laguna])
    assert con_agua.sum() < sin_agua.sum()
    assert con_agua.sum() > 0.5 * sin_agua.sum()


# ------------------------------------------------- rasteres y descargas

def test_escribe_y_lee_conservan_los_datos_y_la_rejilla(cfg, tmp_path):
    t, _, _ = preparar.rejilla(cfg)
    datos = np.arange(12, dtype=np.float64).reshape(3, 4)
    datos[1, 1] = np.nan
    ruta = preparar.escribe(tmp_path / "x.tif", datos, t, cfg.crs)
    vuelta, t2, crs2 = preparar.lee(ruta)
    assert np.allclose(vuelta, datos, equal_nan=True)
    assert t2 == t
    assert crs2.to_string() == cfg.crs


def test_banda_incertidumbre():
    a = np.array([[100.0, 100.0, np.nan]])
    b = np.array([[103.0, 100.0, 50.0]])
    d = preparar.banda_incertidumbre(a, b)
    assert d["mediana_m"] == pytest.approx(1.5)
    assert d["max_m"] == pytest.approx(3.0)
    assert d["pct_sobre_50m"] == 0.0


def test_la_incertidumbre_distingue_el_p90_del_maximo():
    """El maximo lo fija un pixel suelto; el numero publicable es el p90."""
    import numpy as np
    a = np.zeros(1000)
    b = np.full(1000, 2.0)
    b[0] = 700.0                       # un vacio de datos, o una pared
    d = preparar.banda_incertidumbre(a, b)
    assert d["p90_m"] == pytest.approx(2.0)
    assert d["max_m"] == pytest.approx(700.0)
    assert d["pct_sobre_50m"] == pytest.approx(0.1)


def test_los_tiles_de_copernicus_usan_la_esquina_suroeste(cfg):
    ts = descarga.tiles_copernicus(cfg.bbox)
    assert "Copernicus_DSM_COG_10_S07_00_W078_00_DEM" in ts
    # la caja llega a -78.05, asi que toca tambien el tile de al lado
    assert "Copernicus_DSM_COG_10_S07_00_W079_00_DEM" in ts
    assert descarga.tiles_copernicus((14.2, 50.3, 14.8, 50.9)) == \
        ["Copernicus_DSM_COG_10_N50_00_E014_00_DEM"]


def test_la_url_de_opentopography_lleva_la_caja_y_la_llave(cfg):
    url, p = descarga.url_opentopography(cfg.bbox, "COP30", "XYZ")
    assert url.endswith("/API/globaldem")
    assert p["demtype"] == "COP30" and p["API_Key"] == "XYZ"
    assert (p["west"], p["south"], p["east"], p["north"]) == cfg.bbox


def test_overpass_usa_su_propio_orden_de_coordenadas(cfg):
    from camino import osm
    oeste, sur, este, norte = cfg.bbox
    assert f"{sur},{oeste},{norte},{este}" in osm.consulta_agua(cfg.bbox)


def test_los_parametros_de_geocam_paginan(cfg):
    p = descarga.params_geocam(cfg.bbox, offset=2000)
    assert p["resultOffset"] == 2000 and p["resultRecordCount"] == 1000
    assert p["f"] == "geojson" and p["inSR"] == 4326


def test_config_pide_la_llave_con_instrucciones(cfg, monkeypatch):
    monkeypatch.delenv("OPENTOPOGRAPHY_API_KEY", raising=False)
    vacio = type(cfg)(**{**cfg.__dict__, "api_key": ""})
    with pytest.raises(SystemExit, match="opentopography.org"):
        vacio.exige_llave()


def test_config_limpia_el_sufijo_query_del_servicio(cfg):
    con = type(cfg)(**{**cfg.__dict__, "geocam_wfs": "",
                       "geocam_servicio": "https://x/FeatureServer/0/query"})
    assert con.exige_geocam() == "https://x/FeatureServer/0"


def test_config_conoce_sus_componentes(cfg):
    assert cfg.componentes[0] == "fisico"
    assert cfg.k == len(cfg.componentes)
    assert "fisico" not in cfg.componentes_simetricas
    assert len(cfg.vecinos) == cfg.vecindad


def test_el_modelo_de_referencia_es_el_caso_restringido(cfg):
    """El proyecto lo exige: mismo grafo, mismos extremos, y el de
    referencia como caso restringido del ampliado."""
    assert set(cfg.componentes_referencia) <= set(cfg.componentes_ampliado)
    assert cfg.componentes[0] == "fisico"
    assert set(cfg.componentes) == set(cfg.componentes_referencia) | \
        set(cfg.componentes_ampliado)


# ------------------------------------------ unidades: tramos o sectores

def _camino_con_tramos(cfg):
    """Dos tramos con nombre, uno largo y uno corto."""
    import geopandas as gpd
    from shapely.geometry import LineString
    largo = LineString([(175000, 9290000), (176000, 9280000)])     # ~10 km
    corto = LineString([(180000, 9300000), (180500, 9298000)])     # ~2 km
    return gpd.GeoDataFrame(
        {"tramnomb": ["Chillo - Chachapoyas", "Ubillon - Zuta"]},
        geometry=[largo, corto], crs=cfg.crs)


def test_las_unidades_tramo_son_los_tramos_del_registro(cfg):
    g = _camino_con_tramos(cfg)
    con = type(cfg)(**{**cfg.__dict__, "unidad": "tramo",
                       "largo_min_unidad": 5000})
    uds = preparar.unidades(con, g)
    assert [n for n, _ in uds] == ["Chillo - Chachapoyas"]   # el corto no llega


def test_las_unidades_tramo_se_ordenan_de_mayor_a_menor(cfg):
    g = _camino_con_tramos(cfg)
    con = type(cfg)(**{**cfg.__dict__, "unidad": "tramo",
                       "largo_min_unidad": 100})
    uds = preparar.unidades(con, g)
    assert [n for n, _ in uds] == ["Chillo - Chachapoyas", "Ubillon - Zuta"]
    assert uds[0][1].length > uds[1][1].length


def test_sin_tramos_que_lleguen_al_minimo_avisa(cfg):
    g = _camino_con_tramos(cfg)
    con = type(cfg)(**{**cfg.__dict__, "unidad": "tramo",
                       "largo_min_unidad": 1e6})
    with pytest.raises(SystemExit, match="Ningun tramo"):
        preparar.unidades(con, g)


def test_unidad_tramo_necesita_una_fuente_con_tramos(cfg):
    """Un GPX o unas trazas de OSM no traen tramos con nombre."""
    g = _camino_recto(10000.0).drop(columns=[])
    con = type(cfg)(**{**cfg.__dict__, "unidad": "tramo"})
    with pytest.raises(SystemExit, match="no trae tramos"):
        preparar.unidades(con, g)


def test_unidad_sector_corta_el_tramo(cfg):
    g = _camino_recto(12000.0)
    con = type(cfg)(**{**cfg.__dict__, "unidad": "sector", "n_sectores": 4})
    uds = preparar.unidades(con, g)
    assert [n for n, _ in uds] == ["s1", "s2", "s3", "s4"]
    assert all(t.length == pytest.approx(3000.0) for _, t in uds)


def test_unidad_desconocida_se_rechaza(cfg):
    con = type(cfg)(**{**cfg.__dict__, "unidad": "inventada"})
    with pytest.raises(ValueError, match="tramo.*sector"):
        preparar.unidades(con, _camino_recto(5000.0))


# ------------------------------------------------- subgrafo por unidad

def test_el_subgrafo_conserva_los_costos_de_sus_aristas():
    """Cada unidad se analiza en su vecindad; los costos no pueden cambiar
    al recortar el grafo."""
    import numpy as np
    from camino import costo, grafo

    rng = np.random.default_rng(4)
    z = rng.normal(0, 3.0, (16, 16))
    comp = {"rug": costo.normaliza(rng.uniform(size=(16, 16)))}
    g = grafo.construir(z, np.ones((16, 16), dtype=bool), comp, 30.0)

    nodos = np.array([g.nodo(f, c) for f in range(4, 12) for c in range(4, 12)])
    sub = g.subconjunto(nodos)
    assert sub.n == len(nodos)
    assert sub.e < g.e

    w = np.array([0.6, 0.4])
    entero, recortado = g.costos(w).tocoo(), sub.costos(w).tocoo()
    de_sub = {(tuple(sub.filcol[i]), tuple(sub.filcol[j])): v
              for i, j, v in zip(recortado.row, recortado.col, recortado.data)}
    comprobadas = 0
    for i, j, v in zip(entero.row, entero.col, entero.data):
        clave = (tuple(g.filcol[i]), tuple(g.filcol[j]))
        if clave in de_sub:
            assert de_sub[clave] == pytest.approx(v, rel=1e-12)
            comprobadas += 1
    assert comprobadas == sub.e > 100


def test_el_subgrafo_se_niega_si_queda_vacio():
    import numpy as np
    from camino import costo, grafo
    g = grafo.construir(np.zeros((8, 8)), np.ones((8, 8), dtype=bool),
                        {"rug": np.full((8, 8), 0.5)}, 30.0)
    with pytest.raises(ValueError, match="ningun nodo"):
        g.subconjunto([])
    with pytest.raises(ValueError, match="ninguna arista"):
        g.subconjunto([g.nodo(0, 0)])


def test_nodos_cerca_de_una_geometria(cfg):
    import numpy as np
    from camino import grafo
    from shapely.geometry import LineString

    t = preparar.rejilla(cfg)[0]
    g = grafo.construir(np.zeros((20, 20)), np.ones((20, 20), dtype=bool),
                        {"rug": np.full((20, 20), 0.5)}, cfg.resolucion)
    xy0 = grafo.xy(np.array([[10, 0], [10, 19]]), tuple(t)[:6])
    linea = LineString(xy0)
    cerca = g.nodos_cerca_de(linea, tuple(t)[:6], 60.0)
    assert 0 < len(cerca) < g.n
    filas = {int(f) for f, _ in g.filcol[cerca]}
    assert filas <= {8, 9, 10, 11, 12}


def test_detecta_las_unidades_cortadas_por_la_caja(cfg):
    """Un tramo cortado por la caja tiene un extremo inventado."""
    import geopandas as gpd
    from shapely.geometry import LineString

    oeste, sur, este, norte = cfg.bbox
    # una que llega justo al borde este, y otra bien dentro
    borde = gpd.GeoSeries(
        [LineString([(este, -6.40), (este - 0.05, -6.45)])],
        crs="EPSG:4326").to_crs(cfg.crs)[0]
    dentro = gpd.GeoSeries(
        [LineString([(-77.88, -6.40), (-77.87, -6.45)])],
        crs="EPSG:4326").to_crs(cfg.crs)[0]

    assert preparar.recortada_por_la_caja(cfg, borde)
    assert not preparar.recortada_por_la_caja(cfg, dentro)


def test_el_aviso_nombra_las_unidades_cortadas(cfg, capsys):
    import geopandas as gpd
    from shapely.geometry import LineString
    oeste, sur, este, norte = cfg.bbox
    borde = gpd.GeoSeries(
        [LineString([(este, -6.40), (este - 0.05, -6.45)])],
        crs="EPSG:4326").to_crs(cfg.crs)[0]
    tocadas = preparar.avisa_recortadas(cfg, [("La Jalca - Mendoza", borde)])
    assert tocadas == ["La Jalca - Mendoza"]
    assert "borde de la caja" in capsys.readouterr().out
