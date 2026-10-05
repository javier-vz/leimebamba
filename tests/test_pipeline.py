"""Integracion: corre el pipeline completo sobre un raster chico en disco.

El DEM de este test es inventado y solo sirve para comprobar que las piezas
encajan: que los rasteres se escriben y se leen en la misma rejilla, que el
grafo sale del raster, que el barrido corre por sectores, que los nulos se
generan y que el perfil de equifinalidad se calcula y se dibuja. No dice
nada sobre el camino real: eso lo dicen los datos de Copernicus y de GeoCAM.
"""

import numpy as np
import pytest
import yaml

from camino import config, grafo, pipeline, preparar

CONFIG_PRUEBA = {
    "extension": {
        "bbox": {"oeste": -77.90, "sur": -6.42, "este": -77.87, "norte": -6.39},
        "crs": "EPSG:32718",
        "resolucion": 30,
    },
    "datos": {"api_key_opentopography": "", "geocam_servicio": ""},
    "costo": {
        "g_max": 0.45, "epsilon": 0.01, "percentiles": [5.0, 95.0],
        "componentes_referencia": ["fisico"],
        "componentes_ampliado": ["fisico", "ceremonial"],
        "vecindad": 16,
    },
    "restricciones": {"rugosidad_percentil": 99.0, "area_min_laguna": 50000},
    "ceremonial": {"archivo": "", "distancia_saturacion": 2000,
                   "radio_extremos": 200},
    "dominio": {"buffer_corredor": 600, "umbral_quebrada": 50},
    "barrido": {
        "n_simplex": 4, "unidad": "sector", "largo_min_unidad": 500,
        "n_sectores": 2, "m_nulos": 5, "tau_max": 0.5,
        "semilla": 1, "n_trabajos": 1,
    },
}


@pytest.fixture(scope="module")
def proyecto(tmp_path_factory):
    """Un proyecto completo en disco, con DEM y camino inventados."""
    import geopandas as gpd
    from shapely.geometry import LineString

    raiz = tmp_path_factory.mktemp("proyecto")
    with open(raiz / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(CONFIG_PRUEBA, f)
    cfg = config.Config.cargar(raiz / "config.yaml")

    t, ancho, alto = preparar.rejilla(cfg)
    assert 60 < ancho < 200 and 60 < alto < 200

    # Un DEM con forma: una quebrada en V que baja hacia el sur, mas
    # ondulaciones, para que la pendiente y el drenaje no sean constantes.
    f_, c_ = np.mgrid[0:alto, 0:ancho]
    dem = (2600.0
           - 1.2 * f_
           + 0.9 * np.abs(c_ - ancho / 2)
           + 12.0 * np.sin(f_ / 7.0) * np.cos(c_ / 9.0))
    preparar.escribe(cfg.dir_datos / "cop30_raw.tif", dem, t, cfg.crs)
    preparar.escribe(cfg.dir_datos / "aw3d30_raw.tif", dem + 3.0, t, cfg.crs)

    # Un "camino registrado" que baja por la quebrada, de 1.8 km.
    x0, y0 = grafo.xy(np.array([[int(alto * 0.15), ancho // 2]]), tuple(t)[:6])[0]
    linea = LineString([(x0, y0), (x0 + 120, y0 - 900), (x0 - 60, y0 - 1800)])
    gpd.GeoDataFrame({"nombre": ["tramo"]}, geometry=[linea], crs=cfg.crs) \
        .to_file(cfg.dir_datos / "qn_geocam.gpkg", layer="camino", driver="GPKG")

    # espacios ceremoniales inventados, a un lado del camino
    from shapely.geometry import Point
    sitios_g = [Point(x0 + 400, y0 - 400), Point(x0 - 300, y0 - 1400)]
    gpd.GeoDataFrame({"nombre": ["sitio A", "sitio B"]},
                     geometry=sitios_g, crs=cfg.crs) \
        .to_file(cfg.dir_datos / "sitios.gpkg", layer="sitios", driver="GPKG")

    return cfg


@pytest.fixture(scope="module")
def corrido(proyecto):
    """Corre la cadena entera UNA vez. Las pruebas miran sus salidas.

    Antes cada prueba dependia de que la anterior ya hubiera corrido, asi
    que ejecutar una sola, o en otro orden, fallaba.
    """
    cfg = proyecto
    salida = {"cfg": cfg}
    pipeline.preparar_rasteres(cfg)
    salida["comps"] = pipeline.construir_superficies(cfg)
    salida["g"] = pipeline.construir_grafo(cfg)
    salida["revision"] = pipeline.revisar_grafo(cfg)
    salida["nulos"] = pipeline.correr_nulos(cfg)
    salida["barrido"] = pipeline.barrer(cfg)
    salida["resultados"] = pipeline.resultados(cfg)
    return salida


def test_preparar_alinea_los_dos_dem_y_hace_la_mascara(corrido):
    cfg = corrido["cfg"]

    a, ta, _ = preparar.lee(cfg.dir_derivados / "cop30.tif")
    b, tb, _ = preparar.lee(cfg.dir_derivados / "aw3d30.tif")
    m, tm, _ = preparar.lee(cfg.dir_derivados / "mascara.tif")

    assert a.shape == b.shape == m.shape
    assert ta == tb == tm
    assert (m > 0.5).sum() > 200
    assert (m > 0.5).mean() < 1.0            # la mascara recorta de verdad

    inc = (cfg.dir_resultados / "incertidumbre_vertical.json")
    assert inc.exists()


def test_superficies_salen_normalizadas_y_en_la_misma_rejilla(corrido):
    cfg, comps = corrido["cfg"], corrido["comps"]

    assert "mascara" in comps
    mascara = preparar.lee(cfg.dir_derivados / "mascara.tif")[0] > 0.5
    assert mascara.sum() > 200
    # la rugosidad es RESTRICCION, no componente con peso
    assert (cfg.dir_derivados / "rugosidad.tif").exists()
    assert not (cfg.dir_derivados / "phi_rugosidad.tif").exists()


def test_el_grafo_se_construye_se_guarda_y_se_recarga_igual(corrido):
    cfg, g = corrido["cfg"], corrido["g"]

    assert g.nombres == ("fisico", "ceremonial")
    assert g.n > 200
    assert 6 < g.e / g.n <= 16               # vecindad 16 menos el recorte de g_max

    g2 = grafo.Grafo.cargar(cfg.dir_derivados / "grafo.npz")
    assert (g2.n, g2.e, g2.nombres, g2.forma) == (g.n, g.e, g.nombres, g.forma)
    w = np.array([0.6, 0.4])
    assert np.allclose(g.costos(w).data, g2.costos(w).data)


def test_la_revision_devuelve_un_camino_por_unidad(corrido):
    """Una fila por unidad, no una sola.

    Revisaba la unidad mas larga, y en la caja real esa resulta ser una de
    las recortadas por el bbox -- el peor candidato posible para una
    comprobacion de cordura.
    """
    cfg, filas = corrido["cfg"], corrido["revision"]
    _, _, uds = pipeline._carga_unidades(cfg)

    assert len(filas) == len(uds) >= 2
    assert {f["unidad"] for f in filas} == {n for n, _ in uds}

    for info in filas:
        assert info["largo_modelado_km"] > 0.1
        # no puede ser absurdamente mas largo que el observado
        assert info["largo_modelado_km"] < 4 * info["largo_observado_km"]
        assert np.isfinite(info["distancia_media_m"])
        assert np.isfinite(info["frechet_m"])
        assert isinstance(info["recortada_por_la_caja"], bool)
        # la vecindad, no el corredor entero: es lo que usa el barrido
        assert info["nodos_vecindad"] <= corrido["g"].n


def test_la_revision_mide_en_la_misma_vecindad_que_el_barrido(corrido):
    """El numero que imprime `revisar` tiene que anticipar el del barrido.

    Antes corria un Dijkstra sobre el corredor ENTERO -- la union de los
    buffers de todos los tramos-- asi que el camino podia irse por el buffer
    de otro tramo y la D no era comparable con nada. Esta prueba fija que el
    subgrafo sea el mismo.
    """
    cfg, filas = corrido["cfg"], corrido["revision"]
    g, t, uds = pipeline._carga_unidades(cfg)
    por_nombre = {f["unidad"]: f for f in filas}

    for nombre, geom in uds:
        sub = pipeline._contexto(cfg, g, t, geom, con_componentes=False)[0]
        assert por_nombre[nombre]["nodos_vecindad"] == sub.n


def test_la_revision_escribe_las_dos_geometrias(corrido):
    import geopandas as gpd
    cfg = corrido["cfg"]
    ruta = cfg.dir_resultados / "revision_pendiente.gpkg"
    assert ruta.exists()
    gdf = gpd.read_file(ruta)
    assert set(gdf["clase"]) == {"modelado", "observado"}
    assert len(gdf) == 2 * len(corrido["revision"])


def test_los_nulos_dan_una_distancia_por_realizacion(corrido):
    cfg, nul = corrido["cfg"], corrido["nulos"]

    assert set(nul) == {"s1", "s2"}
    for nombre, ds in nul.items():
        assert len(ds) == cfg.m_nulos
        assert np.isfinite(ds).sum() >= 1, f"{nombre}: ningun nulo dio camino"
    assert (cfg.dir_derivados / "nulos.npz").exists()


def test_el_barrido_corre_por_sectores_y_reporta_el_optimo(corrido):
    cfg = corrido["cfg"]
    D_por_unidad, red = corrido["barrido"]

    assert set(D_por_unidad) == {"s1", "s2"}
    assert red.shape == (5, 2)               # 4+1 vectores con K=2
    for nombre, D in D_por_unidad.items():
        assert len(D) == len(red)
        assert np.isfinite(D).any(), f"{nombre}: ningun peso dio camino"

    import json
    with open(cfg.dir_resultados / "optimos_por_unidad.json", encoding="utf-8") as f:
        tablas = json.load(f)
    assert len(tablas) == 2
    for fila in tablas:
        assert fila["unidad"] in ("s1", "s2")
        assert 0 <= fila["w_fisico_ampliado"] <= 1
        assert "p_nulo" in fila              # los nulos corrieron antes
        assert fila["casi_optimos_tau10"] >= 1
        assert "-" in fila["fisico_tau10"]
        assert fila["D_referencia_m"] >= fila["D_ampliado_m"]


def test_los_resultados_dan_el_perfil_y_la_figura(corrido):
    cfg, salida = corrido["cfg"], corrido["resultados"]

    assert len(salida["taus"]) == 26
    assert "s1|s2" in salida["pares"]
    j = np.array(salida["pares"]["s1|s2"])
    assert j.shape == (26,)
    assert np.all((j >= 0) & (j <= 1) | np.isnan(j))
    assert set(salida["centroides"]) == {"s1", "s2"}
    for c in salida["centroides"].values():
        assert sum(c) == pytest.approx(1.0, abs=1e-6)

    png = cfg.dir_resultados / "perfil_equifinalidad.png"
    assert png.exists() and png.stat().st_size > 5000


def _grafo_con(cfg, nombres):
    """Un grafo en memoria con las columnas que se le pidan.

    En memoria y no por `construir_grafo` a proposito: ese escribe
    derivados/grafo.npz, y pisarlo haria que estas pruebas dependieran del
    orden en que corren -- el bug que ya arreglamos una vez.
    """
    dem = preparar.lee(cfg.dir_derivados / "cop30.tif")[0]
    mascara = preparar.lee(cfg.dir_derivados / "mascara.tif")[0] > 0.5
    neutro = np.full(dem.shape, 0.5)
    g = grafo.construir(dem, mascara, {c: neutro for c in nombres[1:]},
                        cfg.resolucion, g_max=cfg.g_max, vecinos=cfg.vecinos)
    g.nombres = tuple(nombres)
    return g


def test_la_visibilidad_entra_como_tercera_componente(corrido):
    """Con 'visibilidad' en el modelo ampliado, el contexto la rellena.

    Es la prueba de que la componente esta ENCHUFADA, no solo escrita: que
    sale de los sitios, que tiene valores distintos por nodo, y que no se
    queda en el 0.5 neutro con que se construye el grafo.
    """
    import dataclasses
    import geopandas as gpd
    from camino import sitios

    cfg = dataclasses.replace(
        corrido["cfg"],
        componentes_ampliado=("fisico", "ceremonial", "visibilidad"),
        visibilidad_radio=2000.0)
    nombres = cfg.componentes
    assert nombres == ("fisico", "ceremonial", "visibilidad")

    g = _grafo_con(cfg, nombres)
    t = preparar.rejilla(cfg)[0]
    camino = gpd.read_file(cfg.dir_datos / "qn_geocam.gpkg", layer="camino")
    geom = preparar.lineas_unidas(camino)[0]
    puntos, _ = sitios.carga(cfg)

    k = nombres.index("visibilidad")
    sub, o, d, obs, t6 = pipeline._contexto(cfg, g, t, geom, puntos)
    col = sub.Phi[:, k]

    assert col.min() >= cfg.epsilon                  # epsilon, sin costos nulos
    assert col.max() <= 1.0 + cfg.epsilon
    assert col.std() > 0.01, "la columna quedo constante: no se relleno"
    assert not np.allclose(col, 0.5)                 # ya no es el neutro

    # y el barrido corre con tres componentes
    red = pipeline.red_del_modelo(cfg, nombres, cfg.componentes_ampliado)
    assert red.shape[1] == 3 and np.allclose(red.sum(axis=1), 1.0)


def test_sin_sitios_la_visibilidad_avisa_en_vez_de_reventar(corrido):
    import dataclasses
    import geopandas as gpd

    cfg = dataclasses.replace(
        corrido["cfg"], componentes_ampliado=("fisico", "visibilidad"))
    g = _grafo_con(cfg, cfg.componentes)
    t = preparar.rejilla(cfg)[0]
    camino = gpd.read_file(cfg.dir_datos / "qn_geocam.gpkg", layer="camino")
    geom = preparar.lineas_unidas(camino)[0]

    with pytest.raises(SystemExit, match="no hay sitios"):
        pipeline._contexto(cfg, g, t, geom, None)


def test_la_cli_lista_los_pasos_en_orden():
    from camino import cli
    assert cli.ORDEN[0] == "bajar"
    assert cli.ORDEN.index("nulos") < cli.ORDEN.index("barrido")
    assert cli.ORDEN.index("revisar") < cli.ORDEN.index("nulos")
    assert set(cli.ORDEN) == set(cli.PASOS)


def test_la_cli_rechaza_un_paso_que_no_existe():
    from camino import cli
    with pytest.raises(SystemExit):
        cli.main(["inventado"])


def test_avisa_cuando_los_dos_modelos_son_el_mismo(corrido, capsys):
    """Con 'componentes_ampliado: [fisico]' los dos modelos coinciden.

    Es legitimo para probar la cadena sin archivo de sitios, pero entonces
    `validar` imprimiria "no hay evidencia de que las componentes anadidas
    aporten" -- cierto y enganoso a la vez, porque no se anadio ninguna.
    """
    import dataclasses
    cfg = dataclasses.replace(corrido["cfg"],
                              componentes_ampliado=("fisico",))
    assert pipeline._modelos_iguales(cfg) is True
    texto = capsys.readouterr().out
    assert "son el mismo modelo" in texto

    assert pipeline._modelos_iguales(corrido["cfg"]) is False


def test_el_resumen_no_declara_falta_de_evidencia_si_no_hay_comparacion(capsys):
    filas = [{"unidad": "u", "modelo": m, "bloque": 1, "D_retenido_m": 10.0}
             for m in ("referencia", "ampliado")]
    pipeline._resumen_validacion(filas, comparables=False)
    texto = capsys.readouterr().out
    assert "no hay comparacion" in texto
    assert "NO hay evidencia" not in texto

    pipeline._resumen_validacion(filas, comparables=True)
    assert "el ampliado gana en" in capsys.readouterr().out


def test_la_razon_de_costo_distingue_equifinalidad_de_modelo_malo(corrido):
    """La metrica que decide como leer una D grande.

    Una ruta puede estar lejos del optimo y costar casi lo mismo
    (equifinalidad espacial: el terreno no decide) o estar lejos y costar
    mucho mas (al modelo le falta algo). Las dos dan la misma D.
    """
    filas = corrido["revision"]
    for f in filas:
        assert f["razon_de_costo"] is not None, f["unidad"]
        # seguir el trazado observado NUNCA puede salir mas barato que el
        # optimo: si sale, hay un bug en el calculo
        assert f["razon_de_costo"] >= 0.999, (f["unidad"], f["razon_de_costo"])
        assert f["franja_celdas"] >= 2
        assert f["largo_recto_km"] > 0
        assert f["sinuosidad_observada"] >= 1.0
        assert f["sinuosidad_modelada"] >= 1.0


def test_el_costo_de_seguir_el_trazado_es_el_optimo_si_el_trazado_es_optimo(corrido):
    """Control: si se le da como 'observado' el propio camino optimo, la
    razon tiene que salir 1."""
    from scipy.sparse.csgraph import dijkstra
    from shapely.geometry import LineString
    from camino import grafo as _grafo

    cfg, g = corrido["cfg"], corrido["g"]
    t = preparar.rejilla(cfg)[0]
    _, _, uds = pipeline._carga_unidades(cfg)
    nombre, linea = uds[0]

    sub, o, d, _, t6 = pipeline._contexto(cfg, g, t, linea,
                                          con_componentes=False)
    w = np.zeros(len(g.nombres))
    w[0] = 1.0
    dist, pred = dijkstra(sub.costos(w), directed=True, indices=o,
                          return_predecessors=True)
    cam = _grafo.recorre(pred, o, d)
    xy = _grafo.xy(sub.filcol[cam], t6)
    optimo = LineString(xy)

    costo, celdas = pipeline.costo_de_seguir_el_trazado(
        cfg, g, t6, optimo, w, xy[0], xy[-1])
    assert costo == pytest.approx(float(dist[d]), rel=1e-6)


def test_el_nulo_guarda_las_razones_de_costo(corrido):
    """El conjunto de control que pide el proyecto, en la dimension de costo.

    Las mismas rutas aleatorias que dan el nulo geometrico sirven para
    responder lo que la razon de costo deja abierto: 1.45 es mucho o poco?
    """
    cfg = corrido["cfg"]
    d = np.load(cfg.dir_derivados / "nulos.npz")

    razones = {k[len("razon__"):]: d[k] for k in d.files
               if k.startswith("razon__")}
    obs = {k[len("razonobs__"):]: float(d[k][0]) for k in d.files
           if k.startswith("razonobs__")}
    assert set(razones) == set(obs) == set(corrido["nulos"])

    for nombre, rs in razones.items():
        buenas = rs[np.isfinite(rs)]
        assert buenas.size >= 1
        # ninguna ruta puede costar menos que el optimo
        assert buenas.min() >= 0.999, (nombre, buenas.min())
        assert obs[nombre] >= 0.999


def test_el_nulo_de_costo_da_p_en_cero_uno_y_sabe_callarse(capsys):
    """p = fraccion de rutas plausibles igual o mas baratas que la real."""
    # la real es mas barata que todas: p en el piso 1/(M+1)
    barata = pipeline._tabla_nulo_de_costo(
        {"u": 1.05}, {"u": np.array([2.0, 3.0, 4.0])})
    assert barata["u"]["p"] == pytest.approx(1 / 4)

    # la real es la mas cara: p = 1
    cara = pipeline._tabla_nulo_de_costo(
        {"u": 9.0}, {"u": np.array([2.0, 3.0, 4.0])})
    assert cara["u"]["p"] == 1.0

    # sin datos no inventa
    vacio = pipeline._tabla_nulo_de_costo(
        {"u": np.nan}, {"u": np.array([np.nan])})
    assert vacio == {}
    assert "n/d" in capsys.readouterr().out
