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
        "componentes": ["pendiente", "rugosidad", "drenaje"],
        "vecindad": 16,
    },
    "dominio": {"buffer_corredor": 600, "umbral_quebrada": 50},
    "barrido": {
        "n_simplex": 4, "n_sectores": 2, "m_nulos": 5, "tau_max": 0.5,
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

    return cfg


def test_preparar_alinea_los_dos_dem_y_hace_la_mascara(proyecto):
    cfg = proyecto
    pipeline.preparar_rasteres(cfg)

    a, ta, _ = preparar.lee(cfg.dir_derivados / "cop30.tif")
    b, tb, _ = preparar.lee(cfg.dir_derivados / "aw3d30.tif")
    m, tm, _ = preparar.lee(cfg.dir_derivados / "mascara.tif")

    assert a.shape == b.shape == m.shape
    assert ta == tb == tm
    assert (m > 0.5).sum() > 200
    assert (m > 0.5).mean() < 1.0            # la mascara recorta de verdad

    inc = (cfg.dir_resultados / "incertidumbre_vertical.json")
    assert inc.exists()


def test_superficies_salen_normalizadas_y_en_la_misma_rejilla(proyecto):
    cfg = proyecto
    comps = pipeline.construir_superficies(cfg)

    assert set(comps) == {"rugosidad", "drenaje"}
    mascara = preparar.lee(cfg.dir_derivados / "mascara.tif")[0] > 0.5
    for nombre, c in comps.items():
        ruta = cfg.dir_derivados / f"phi_{nombre}.tif"
        assert ruta.exists()
        v = c[mascara]
        v = v[np.isfinite(v)]
        assert v.min() >= cfg.epsilon - 1e-9
        assert v.max() <= 1.0 + cfg.epsilon + 1e-9
        assert v.std() > 0                   # la componente aporta informacion


def test_el_grafo_se_construye_se_guarda_y_se_recarga_igual(proyecto):
    cfg = proyecto
    g = pipeline.construir_grafo(cfg)

    assert g.nombres == ("pendiente", "rugosidad", "drenaje")
    assert g.n > 200
    assert 6 < g.e / g.n <= 16               # vecindad 16 menos el recorte de g_max

    g2 = grafo.Grafo.cargar(cfg.dir_derivados / "grafo.npz")
    assert (g2.n, g2.e, g2.nombres, g2.forma) == (g.n, g.e, g.nombres, g.forma)
    w = np.array([0.4, 0.3, 0.3])
    assert np.allclose(g.costos(w).data, g2.costos(w).data)


def test_la_revision_devuelve_un_camino_plausible(proyecto):
    cfg = proyecto
    info = pipeline.revisar_grafo(cfg)

    assert info["largo_modelado_km"] > 1.0
    # el camino modelado no puede ser absurdamente mas largo que el observado
    assert info["largo_modelado_km"] < 4 * info["largo_observado_km"]
    assert np.isfinite(info["distancia_media_m"])
    assert np.isfinite(info["frechet_m"])
    assert (cfg.dir_resultados / "revision_pendiente.gpkg").exists()


def test_los_nulos_dan_una_distancia_por_realizacion(proyecto):
    cfg = proyecto
    nul = pipeline.correr_nulos(cfg)

    assert set(nul) == {"s1", "s2"}
    for nombre, ds in nul.items():
        assert len(ds) == cfg.m_nulos
        assert np.isfinite(ds).sum() >= 1, f"{nombre}: ningun nulo dio camino"
    assert (cfg.dir_derivados / "nulos.npz").exists()


def test_el_barrido_corre_por_sectores_y_reporta_el_optimo(proyecto):
    cfg = proyecto
    D_por_sector, red = pipeline.barrer(cfg)

    assert set(D_por_sector) == {"s1", "s2"}
    assert red.shape == (15, 3)              # C(4+3-1, 3-1) = C(6,2) = 15
    for nombre, D in D_por_sector.items():
        assert len(D) == len(red)
        assert np.isfinite(D).any(), f"{nombre}: ningun peso dio camino"

    import json
    with open(cfg.dir_resultados / "optimos_por_sector.json", encoding="utf-8") as f:
        tablas = json.load(f)
    assert len(tablas) == 2
    for fila in tablas:
        assert fila["sector"] in ("s1", "s2")
        assert 0 <= fila["pendiente"] <= 1
        assert "p_nulo" in fila              # los nulos corrieron antes
        assert fila["casi_optimos_tau10"] >= 1
        assert "-" in fila["pendiente_tau10"]


def test_los_resultados_dan_el_perfil_y_la_figura(proyecto):
    cfg = proyecto
    salida = pipeline.resultados(cfg)

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
