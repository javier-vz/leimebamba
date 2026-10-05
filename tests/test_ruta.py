"""Las tres fuentes del camino observado: GeoCAM, un archivo propio, OSM."""

import json

import pytest

from camino import config, descarga, ruta


@pytest.fixture
def cfg():
    return config.Config.cargar()


def _linea(cfg, dentro=True):
    """Una polilinea dentro (o fuera) de la caja del tramo."""
    import geopandas as gpd
    from shapely.geometry import LineString

    oeste, sur, este, norte = cfg.bbox
    if dentro:
        g = LineString([(-77.85, -6.60), (-77.86, -6.45), (-77.87, -6.30)])
    else:
        g = LineString([(-70.0, -12.0), (-70.1, -12.1)])
    return gpd.GeoDataFrame({"n": [1]}, geometry=[g], crs="EPSG:4326")


# ------------------------------------------------------- desde un archivo

def test_importa_un_geopackage_propio(cfg, tmp_path, monkeypatch):
    origen = tmp_path / "mi_camino.gpkg"
    _linea(cfg).to_file(origen, driver="GPKG")

    monkeypatch.setattr(type(cfg), "dir_datos",
                        property(lambda s: tmp_path))
    destino = ruta.importar(cfg, "archivo", origen)

    import geopandas as gpd
    salida = gpd.read_file(destino, layer="camino")
    assert len(salida) == 1
    assert salida.crs.to_string() == cfg.crs
    assert salida.geometry.iloc[0].length > 10_000      # en metros, no grados


def test_un_archivo_sin_crs_se_asume_en_grados(cfg, tmp_path):
    origen = tmp_path / "sin_crs.geojson"
    g = _linea(cfg)
    g.to_file(origen, driver="GeoJSON")
    # GeoJSON siempre es 4326, asi que el resultado tiene que ser metrico
    leido = ruta.desde_archivo(cfg, origen)
    assert leido.crs.to_string() == cfg.crs


def test_avisa_si_el_archivo_no_existe(cfg):
    with pytest.raises(SystemExit, match="No encuentro"):
        ruta.desde_archivo(cfg, "no_existe_este_archivo.gpx")


def test_importar_archivo_sin_decir_cual(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(type(cfg), "dir_datos", property(lambda s: tmp_path))
    with pytest.raises(SystemExit, match="--archivo"):
        ruta.importar(cfg, "archivo", None)


def test_rechaza_una_fuente_inventada(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(type(cfg), "dir_datos", property(lambda s: tmp_path))
    with pytest.raises(SystemExit, match="fuente desconocida"):
        ruta.importar(cfg, "inventada")


def test_falla_si_lo_importado_cae_fuera_de_la_caja(cfg, tmp_path, monkeypatch):
    origen = tmp_path / "lejos.gpkg"
    _linea(cfg, dentro=False).to_file(origen, driver="GPKG")
    monkeypatch.setattr(type(cfg), "dir_datos", property(lambda s: tmp_path))
    with pytest.raises(SystemExit, match="fuera de la caja|no quedo nada"):
        ruta.importar(cfg, "archivo", origen)


# -------------------------------------------------------------- desde OSM

def test_la_consulta_osm_pide_lo_historico_y_lo_que_se_llama_inca(cfg):
    q = ruta.consulta_osm(cfg.bbox)
    assert '["historic"]' in q
    assert "Qq]hapaq" in q
    oeste, sur, este, norte = cfg.bbox
    assert f"{sur},{oeste},{norte},{este}" in q      # Overpass va al reves
    assert "out geom;" in q


def test_la_consulta_osm_no_pide_todos_los_senderos(cfg):
    """En los Andes hay miles de senderos y ninguno dice cual es el camino."""
    q = ruta.consulta_osm(cfg.bbox)
    assert 'way["highway"="path"];' not in q
    assert q.count('way["highway"="path"]') <= 1     # solo el filtrado por nombre


class _SesionOSM:
    def __init__(self, elementos):
        self.elementos = elementos

    def post(self, url, data=None, headers=None, timeout=None, **kw):
        class _R:
            status_code = 200

            def __init__(s, d):
                s._d = d

            def raise_for_status(s):
                pass

            def json(s):
                return s._d
        return _R({"elements": self.elementos})


def test_osm_arma_las_lineas_y_conserva_las_etiquetas(cfg):
    elementos = [
        {"id": 1, "tags": {"name": "Camino Inca", "historic": "road"},
         "geometry": [{"lon": -77.85, "lat": -6.60},
                      {"lon": -77.86, "lat": -6.45}]},
        {"id": 2, "tags": {}, "geometry": [{"lon": -77.8, "lat": -6.5}]},
    ]
    g = ruta.desde_osm(cfg, sesion=_SesionOSM(elementos))
    assert len(g) == 1                       # el de un solo punto se descarta
    assert g.iloc[0]["nombre"] == "Camino Inca"
    assert g.iloc[0]["fuente"] == "osm_provisional"
    assert g.crs.to_string() == cfg.crs


def test_osm_avisa_si_no_hay_nada_etiquetado(cfg):
    with pytest.raises(SystemExit, match="OpenStreetMap no tiene"):
        ruta.desde_osm(cfg, sesion=_SesionOSM([]))


def test_lo_de_osm_queda_marcado_como_provisional(cfg):
    elementos = [{"id": 1, "tags": {"name": "Qhapaq Nan"},
                  "geometry": [{"lon": -77.85, "lat": -6.60},
                               {"lon": -77.86, "lat": -6.45}]}]
    g = ruta.desde_osm(cfg, sesion=_SesionOSM(elementos))
    assert (g["fuente"] == "osm_provisional").all()


# ------------------------------------------------------------------ la CLI

def test_ruta_es_un_paso_del_pipeline_y_va_despues_de_bajar():
    from camino import cli
    assert cli.ORDEN.index("bajar") < cli.ORDEN.index("ruta")
    assert cli.ORDEN.index("ruta") < cli.ORDEN.index("preparar")
    assert set(cli.ORDEN) == set(cli.PASOS)
    assert "geocam" not in cli.ORDEN        # lo reemplazo 'ruta'


def test_el_pipeline_no_exige_el_camino_para_preparar():
    """GeoCAM se cae; el DEM no tiene por que esperarla."""
    import inspect

    from camino import pipeline
    fuente = inspect.getsource(pipeline.preparar_rasteres)
    assert "ruta_camino.exists()" in fuente
    assert "la mascara es la caja entera" in fuente
