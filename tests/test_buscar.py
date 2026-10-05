"""El buscador del servicio de GeoCAM, contra un ArcGIS Server simulado.

No toca la red: la sesion es falsa y sirve un arbol de servicios parecido al
que publica ArcGIS Server. Lo que se prueba es el recorrido del directorio,
la puntuacion de las capas y la escritura en config.yaml.
"""

import pytest
import requests

from camino import buscar

RAIZ = "https://geocam.cultura.gob.pe/server/rest/services"

ARBOL = {
    RAIZ: {"folders": ["QhapaqNan", "Limites"],
           "services": [{"name": "Base", "type": "MapServer"}]},
    f"{RAIZ}/QhapaqNan": {
        "services": [{"name": "QhapaqNan/RedVialInca", "type": "MapServer"}]},
    f"{RAIZ}/Limites": {
        "services": [{"name": "Limites/Distritos", "type": "FeatureServer"}]},
    f"{RAIZ}/QhapaqNan/RedVialInca/MapServer": {"layers": [
        {"id": 0, "name": "Tramo Qhapaq Nan",
         "geometryType": "esriGeometryPolyline"},
        {"id": 1, "name": "Tambos", "geometryType": "esriGeometryPoint"},
        {"id": 9, "name": "Grupo", "subLayerIds": [0, 1]},
    ]},
    f"{RAIZ}/Limites/Distritos/FeatureServer": {"layers": [
        {"id": 0, "name": "Limites distritales",
         "geometryType": "esriGeometryPolygon"}]},
    f"{RAIZ}/Base/MapServer": {"layers": [
        {"id": 0, "name": "Curvas de nivel",
         "geometryType": "esriGeometryPolyline"}]},
}


class _Resp:
    def __init__(self, cuerpo, codigo=200):
        self._cuerpo, self.status_code = cuerpo, codigo

    def json(self):
        if self._cuerpo is None:
            raise ValueError("no es json")
        return self._cuerpo


class SesionFalsa:
    """Sirve `ARBOL` y cuenta las peticiones. 404 para lo que no conoce."""

    def __init__(self, arbol=None, revienta=(), no_json=()):
        self.arbol = ARBOL if arbol is None else arbol
        self.revienta = tuple(revienta)
        self.no_json = tuple(no_json)
        self.pedidas = []

    def get(self, url, params=None, timeout=None, headers=None, **kw):
        self.pedidas.append(url)
        self.ultimas_cabeceras = headers or {}
        if any(url.startswith(p) for p in self.revienta):
            raise requests.ConnectionError("simulado")
        if url in self.no_json:
            return _Resp(None)
        if url in self.arbol:
            return _Resp(self.arbol[url])
        return _Resp({"error": {"code": 404}}, 404)


# ------------------------------------------------------------ puntuacion

def test_la_capa_del_camino_puntua_mas_que_el_ruido():
    camino = buscar.puntua("QhapaqNan Tramo Qhapaq Nan", "esriGeometryPolyline")
    limites = buscar.puntua("Limites Limites distritales", "esriGeometryPolygon")
    curvas = buscar.puntua("Base Curvas de nivel", "esriGeometryPolyline")
    assert camino > limites
    assert camino > curvas
    assert limites < 0


def test_una_linea_puntua_mas_que_un_poligono_con_el_mismo_nombre():
    linea = buscar.puntua("camino inca", "esriGeometryPolyline")
    poligono = buscar.puntua("camino inca", "esriGeometryPolygon")
    assert linea > poligono


def test_la_puntuacion_ignora_tildes_y_mayusculas():
    assert buscar.puntua("QHAPAQ ÑAN") == buscar.puntua("qhapaq ñan")
    assert buscar.puntua("Camino Inca") > 0


def test_las_raices_prueban_las_rutas_habituales():
    r = buscar.raices()
    assert r[0] == RAIZ
    assert any("arcgis/rest/services" in u for u in r)
    assert all(u.startswith("https://") for u in r)


# -------------------------------------------------------------- recorrido

def test_recorre_entra_en_las_carpetas():
    s = SesionFalsa()
    servicios = buscar.recorre(RAIZ, s)
    nombres = sorted(x["nombre"] for x in servicios)
    assert nombres == ["Base", "Distritos", "RedVialInca"]
    assert f"{RAIZ}/QhapaqNan/RedVialInca/MapServer" in \
        [x["url"] for x in servicios]


def test_recorre_devuelve_vacio_si_el_directorio_esta_cerrado():
    assert buscar.recorre(RAIZ, SesionFalsa(arbol={})) == []


def test_recorre_sobrevive_a_un_error_de_red():
    s = SesionFalsa(revienta=(RAIZ,))
    assert buscar.recorre(RAIZ, s) == []


def test_recorre_sobrevive_a_una_respuesta_que_no_es_json():
    s = SesionFalsa(no_json=(RAIZ,))
    assert buscar.recorre(RAIZ, s) == []


def test_capas_descarta_los_grupos():
    s = SesionFalsa()
    serv = {"url": f"{RAIZ}/QhapaqNan/RedVialInca/MapServer",
            "nombre": "RedVialInca", "tipo": "MapServer"}
    cs = buscar.capas(serv, s)
    assert [c["capa"] for c in cs] == ["Tramo Qhapaq Nan", "Tambos"]
    assert cs[0]["geometria"] == "Polyline"
    assert cs[0]["url"].endswith("/MapServer/0")


# ------------------------------------------------------------- candidatas

def test_candidatas_pone_el_camino_primero():
    s = SesionFalsa()
    enc = buscar.candidatas(sesion=s)
    assert enc[0]["capa"] == "Tramo Qhapaq Nan"
    assert enc[0]["puntos"] > 0
    assert enc[-1]["capa"] == "Limites distritales"


def test_candidatas_para_en_el_primer_directorio_que_responde():
    s = SesionFalsa()
    buscar.candidatas(sesion=s)
    # no debe haber probado las rutas alternativas
    assert not any("arcgis/rest/services" in u for u in s.pedidas)


def test_candidatas_prueba_la_siguiente_ruta_si_la_primera_falla():
    alterno = "https://geocam.cultura.gob.pe/arcgis/rest/services"
    arbol = {alterno: {"services": [{"name": "QN", "type": "FeatureServer"}]},
             f"{alterno}/QN/FeatureServer": {"layers": [
                 {"id": 3, "name": "Qhapaq Nan tramo",
                  "geometryType": "esriGeometryPolyline"}]}}
    enc = buscar.candidatas(sesion=SesionFalsa(arbol=arbol))
    assert len(enc) == 1
    assert enc[0]["url"].endswith("/FeatureServer/3")


def test_candidatas_devuelve_vacio_si_nada_responde():
    assert buscar.candidatas(sesion=SesionFalsa(arbol={})) == []


def test_candidatas_respeta_el_limite():
    assert len(buscar.candidatas(sesion=SesionFalsa(), limite=2)) == 2


# --------------------------------------------------- escritura en config

def test_guarda_en_config_sin_perder_los_comentarios(tmp_path):
    ruta = tmp_path / "config.yaml"
    ruta.write_text(
        'datos:\n'
        '  # un comentario que tiene que sobrevivir\n'
        '  api_key_opentopography: ""\n'
        '\n'
        '  # otro comentario\n'
        '  geocam_servicio: ""\n'
        'costo:\n  g_max: 0.45\n', encoding="utf-8")

    buscar.guarda_en_config(ruta, "https://x/FeatureServer/0")
    texto = ruta.read_text(encoding="utf-8")

    assert '  geocam_servicio: "https://x/FeatureServer/0"\n' in texto
    assert "# un comentario que tiene que sobrevivir" in texto
    assert "# otro comentario" in texto
    assert "g_max: 0.45" in texto
    assert 'api_key_opentopography: ""' in texto


def test_guarda_en_config_reemplaza_un_valor_anterior(tmp_path):
    ruta = tmp_path / "config.yaml"
    ruta.write_text('  geocam_servicio: "https://viejo/MapServer/1"\n',
                    encoding="utf-8")
    buscar.guarda_en_config(ruta, "https://nuevo/MapServer/2")
    assert ruta.read_text(encoding="utf-8") == \
        '  geocam_servicio: "https://nuevo/MapServer/2"\n'


def test_guarda_en_config_avisa_si_no_encuentra_la_linea(tmp_path):
    ruta = tmp_path / "config.yaml"
    ruta.write_text("costo:\n  g_max: 0.45\n", encoding="utf-8")
    with pytest.raises(ValueError, match="geocam_servicio"):
        buscar.guarda_en_config(ruta, "https://x/0")


def test_la_config_real_tiene_la_linea_que_el_buscador_edita():
    """Si alguien renombra la clave en config.yaml, esto lo caza."""
    from camino import config
    ruta = config.RAIZ / "config.yaml"
    assert "geocam_servicio:" in ruta.read_text(encoding="utf-8")


# ----------------------------------------------------------------- la CLI

def test_buscar_esta_en_la_cli_y_no_dentro_del_pipeline():
    from camino import cli
    assert "buscar" in cli.AYUDAS
    assert "buscar" not in cli.ORDEN


def test_las_peticiones_se_presentan_como_navegador():
    """Muchos portales del Estado devuelven 500 o 403 a python-requests y
    responden al mismo URL desde Chrome."""
    s = SesionFalsa()
    buscar.candidatas(sesion=s)
    assert "Mozilla/5.0" in s.ultimas_cabeceras.get("User-Agent", "")
