"""El cliente de Overpass, con sus fallos reales simulados.

El 406 Not Acceptable que devolvio overpass-api.de en la primera corrida es
el caso que manda aqui: pasa cuando la consulta va por GET en la URL en vez
de por POST en el cuerpo, y es facil confundirlo con "no hay datos".
"""

import pytest
import requests

from camino import config, osm

Q = "[out:json];out;"


@pytest.fixture
def cfg():
    return config.Config.cargar()


class _Resp:
    def __init__(self, cuerpo, codigo=200):
        self._cuerpo, self.status_code = cuerpo, codigo
        self.text = str(cuerpo)

    def json(self):
        if self._cuerpo is None:
            raise ValueError("no es json")
        return self._cuerpo


_NADA = object()


class Overpass:
    """Simula los espejos. `codigos` mapea url -> codigo que devuelve."""

    def __init__(self, codigos=None, cuerpo=_NADA):
        self.codigos = codigos or {}
        self.cuerpo = {"elements": []} if cuerpo is _NADA else cuerpo
        self.posts, self.gets = [], []

    def post(self, url, data=None, headers=None, timeout=None, **kw):
        self.posts.append((url, dict(data or {}), dict(headers or {})))
        codigo = self.codigos.get(url, 200)
        if codigo == 0:
            raise requests.ConnectionError("simulado")
        return _Resp(self.cuerpo if codigo == 200 else "error", codigo)

    def get(self, *a, **kw):
        self.gets.append(a)
        return _Resp("no deberia usarse", 406)


# --------------------------------------------------------- la peticion

def test_la_consulta_va_por_post_no_por_get():
    """Es la causa del 406: varios espejos rechazan la consulta en la URL."""
    s = Overpass()
    osm.consulta(Q, sesion=s)
    assert len(s.posts) == 1
    assert not s.gets
    url, data, _ = s.posts[0]
    assert data == {"data": Q}


def test_la_peticion_se_identifica():
    """Overpass es gratuito y limita a los clientes anonimos."""
    s = Overpass()
    osm.consulta(Q, sesion=s)
    _, _, cabeceras = s.posts[0]
    assert "camino-leimebamba" in cabeceras["User-Agent"]
    assert cabeceras["Accept"] == "application/json"


def test_devuelve_el_json_del_servidor():
    s = Overpass(cuerpo={"elements": [{"id": 1}]})
    assert osm.consulta(Q, sesion=s) == {"elements": [{"id": 1}]}


# ------------------------------------------------- fallos y recuperacion

def test_cambia_de_espejo_cuando_el_primero_da_406():
    s = Overpass(codigos={osm.ESPEJOS[0]: 406})
    assert osm.consulta(Q, sesion=s, intentos=1) == {"elements": []}
    assert [u for u, _, _ in s.posts] == list(osm.ESPEJOS[:2])


def test_cambia_de_espejo_cuando_el_primero_esta_saturado():
    s = Overpass(codigos={osm.ESPEJOS[0]: 429, osm.ESPEJOS[1]: 504})
    osm.consulta(Q, sesion=s, intentos=1)
    assert len(s.posts) == 3


def test_cambia_de_espejo_si_no_hay_conexion():
    s = Overpass(codigos={osm.ESPEJOS[0]: 0})
    assert osm.consulta(Q, sesion=s, intentos=1) == {"elements": []}


def test_repite_la_ronda_antes_de_rendirse():
    s = Overpass(codigos={u: 429 for u in osm.ESPEJOS})
    with pytest.raises(RuntimeError):
        osm.consulta(Q, sesion=s, intentos=2, espera=0)
    assert len(s.posts) == 2 * len(osm.ESPEJOS)


def test_el_error_dice_que_paso_en_cada_espejo():
    s = Overpass(codigos={u: 429 for u in osm.ESPEJOS})
    with pytest.raises(RuntimeError, match="HTTP 429"):
        osm.consulta(Q, sesion=s, intentos=1, espera=0)


def test_una_respuesta_que_no_es_json_no_se_cuela():
    s = Overpass(cuerpo=None)
    with pytest.raises(RuntimeError, match="no es JSON"):
        osm.consulta(Q, sesion=s, intentos=1, espera=0)


# ------------------------------------------------------- las consultas

def test_la_caja_va_en_el_orden_de_overpass(cfg):
    """Overpass usa sur,oeste,norte,este, al reves de casi todo lo demas."""
    oeste, sur, este, norte = cfg.bbox
    assert osm.caja(cfg.bbox) == f"{sur},{oeste},{norte},{este}"


def test_la_consulta_de_agua_pide_rios_y_lagunas(cfg):
    q = osm.consulta_agua(cfg.bbox)
    assert '"waterway"="river"' in q and '"natural"="water"' in q
    assert osm.caja(cfg.bbox) in q
    assert q.endswith("out geom;")


def test_la_consulta_de_camino_no_pide_todos_los_senderos(cfg):
    q = osm.consulta_camino(cfg.bbox)
    assert '["historic"]' in q
    assert "Qq]hapaq" in q
    assert q.count('way["highway"="path"]') <= 1


# ----------------------------------------------------- de JSON a lineas

def test_convierte_los_elementos_en_lineas(cfg):
    d = {"elements": [
        {"id": 7, "tags": {"name": "Rio Utcubamba", "waterway": "river"},
         "geometry": [{"lon": -77.85, "lat": -6.6}, {"lon": -77.86, "lat": -6.5}]},
        {"id": 8, "tags": {}, "geometry": [{"lon": -77.8, "lat": -6.5}]},
    ]}
    g = osm.lineas(d, cfg.crs)
    assert len(g) == 1                      # el de un solo punto se descarta
    assert g.iloc[0]["nombre"] == "Rio Utcubamba"
    assert g.iloc[0]["waterway"] == "river"
    assert g.crs.to_string() == cfg.crs


def test_una_respuesta_vacia_da_un_geodataframe_vacio(cfg):
    g = osm.lineas({"elements": []}, cfg.crs)
    assert g.empty


# --------------------------------------- el agua no bloquea la corrida

def test_el_agua_es_opcional_y_no_tumba_la_descarga(cfg, tmp_path, monkeypatch):
    """Fue el fallo real: un 406 en un insumo opcional aborto todo."""
    from camino import descarga

    monkeypatch.setattr(type(cfg), "dir_datos", property(lambda s: tmp_path))

    def revienta(*a, **kw):
        raise RuntimeError("Overpass no respondio en ningun espejo")
    monkeypatch.setattr(osm, "consulta", revienta)

    assert descarga.agua(cfg) is None       # avisa y devuelve None, no levanta
    assert not (tmp_path / "agua_osm.json").exists()


def test_la_mascara_se_arma_igual_sin_el_archivo_de_agua(cfg, tmp_path, monkeypatch):
    from camino import pipeline
    monkeypatch.setattr(type(cfg), "dir_datos", property(lambda s: tmp_path))
    assert pipeline._agua_geoms(cfg) == []


# ------------------------------------ el agua, en metros y no en grados

def _agua_json(tmp_path):
    """Una respuesta de Overpass con un rio (linea) y una laguna (poligono)."""
    import json
    d = {"elements": [
        {"id": 1, "type": "way", "tags": {"waterway": "river", "name": "Utcubamba"},
         "geometry": [{"lon": -77.88, "lat": -6.40}, {"lon": -77.87, "lat": -6.35},
                      {"lon": -77.86, "lat": -6.30}]},
        {"id": 2, "type": "way", "tags": {"natural": "water", "name": "Laguna"},
         "geometry": [{"lon": -77.90, "lat": -6.50}, {"lon": -77.89, "lat": -6.50},
                      {"lon": -77.89, "lat": -6.49}, {"lon": -77.90, "lat": -6.49},
                      {"lon": -77.90, "lat": -6.50}]},
    ]}
    (tmp_path / "agua_osm.json").write_text(json.dumps(d), encoding="utf-8")


def test_los_rios_no_se_enmascaran(cfg, tmp_path, monkeypatch):
    """Un rio enmascarado parte el grafo en dos orillas sin camino posible.
    Cruzarlo es caro -- de eso se encarga la componente de drenaje -- no
    imposible."""
    from camino import pipeline
    monkeypatch.setattr(type(cfg), "dir_datos", property(lambda s: tmp_path))
    _agua_json(tmp_path)

    geoms = pipeline._agua_geoms(cfg)
    assert len(geoms) == 1               # solo la laguna; el rio no entra


def test_las_areas_se_miden_en_metros_no_en_grados(cfg, tmp_path, monkeypatch):
    """Si se midieran en grados cuadrados, la laguna 'mediria' 0.0001 y
    caeria por debajo de cualquier umbral razonable."""
    from camino import pipeline
    monkeypatch.setattr(type(cfg), "dir_datos", property(lambda s: tmp_path))
    _agua_json(tmp_path)
    (laguna,) = pipeline._agua_geoms(cfg)
    assert 0.5e6 < laguna.area < 3e6     # ~1.2 km2, en metros cuadrados


def test_las_lagunas_pequenas_se_descartan(cfg, tmp_path, monkeypatch):
    from camino import pipeline
    monkeypatch.setattr(type(cfg), "dir_datos", property(lambda s: tmp_path))
    _agua_json(tmp_path)
    exigente = type(cfg)(**{**cfg.__dict__, "area_min_laguna": 1e8})
    assert pipeline._agua_geoms(exigente) == []





def test_la_mascara_se_niega_si_el_agua_se_come_el_corredor(cfg):
    """La comprobacion que habria cazado el bug en el acto."""
    import geopandas as gpd
    import pytest
    from camino import preparar
    from shapely.geometry import LineString, box

    oeste, sur, este, norte = cfg.bbox
    linea = gpd.GeoDataFrame(
        {"n": [1]},
        geometry=[LineString([(-77.86, -6.50), (-77.87, -6.30)])],
        crs="EPSG:4326").to_crs(cfg.crs)
    # "agua" del tamano de toda la caja: justo lo que producia el bug
    enorme = gpd.GeoSeries([box(oeste, sur, este, norte)],
                           crs="EPSG:4326").to_crs(cfg.crs)[0]

    with pytest.raises(ValueError, match="no es creible"):
        preparar.mascara_corredor(cfg, linea, [enorme])


def test_la_mascara_avisa_si_el_camino_cae_fuera_de_la_caja(cfg):
    import geopandas as gpd
    import pytest
    from camino import preparar
    from shapely.geometry import LineString

    lejos = gpd.GeoDataFrame(
        {"n": [1]}, geometry=[LineString([(-70.0, -12.0), (-70.1, -12.1)])],
        crs="EPSG:4326").to_crs(cfg.crs)
    with pytest.raises(ValueError, match="no toca la rejilla"):
        preparar.mascara_corredor(cfg, lejos)
