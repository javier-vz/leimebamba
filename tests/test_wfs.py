"""El cliente WFS, contra un GeoServer simulado (incluido su proxy averiado).

El proxy del Ministerio de Cultura devuelve 500 de forma intermitente
("Error during SSL Handshake with remote server"). Varias pruebas de aqui
simulan justamente eso, porque es el fallo que el usuario se va a encontrar.
"""

import pytest
import requests

from camino import buscar, wfs

BASE = "https://geoservicios.cultura.gob.pe/geoserver/wfs"

CAPS_20 = """<?xml version="1.0"?>
<wfs:WFS_Capabilities xmlns:wfs="http://www.opengis.net/wfs/2.0"
                      xmlns:ows="http://www.opengis.net/ows/1.1" version="2.0.0">
  <ows:OperationsMetadata>
    <ows:Operation name="GetFeature">
      <ows:Parameter name="outputFormat">
        <ows:AllowedValues>
          <ows:Value>text/xml; subtype=gml/3.2</ows:Value>
          <ows:Value>application/json</ows:Value>
          <ows:Value>csv</ows:Value>
        </ows:AllowedValues>
      </ows:Parameter>
    </ows:Operation>
  </ows:OperationsMetadata>
  <wfs:FeatureTypeList>
    <wfs:FeatureType>
      <wfs:Name>cultura:qhapaq_nan_tramos</wfs:Name>
      <wfs:Title>Qhapaq Nan - tramos de camino</wfs:Title>
      <wfs:Abstract>Red vial inca registrada</wfs:Abstract>
      <wfs:DefaultCRS>urn:ogc:def:crs:EPSG::4326</wfs:DefaultCRS>
    </wfs:FeatureType>
    <wfs:FeatureType>
      <wfs:Name>cultura:limites_distritales</wfs:Name>
      <wfs:Title>Limites distritales</wfs:Title>
      <wfs:DefaultCRS>urn:ogc:def:crs:EPSG::4326</wfs:DefaultCRS>
    </wfs:FeatureType>
    <wfs:FeatureType>
      <wfs:Name>cultura:sitios_arqueologicos</wfs:Name>
      <wfs:Title>Sitios arqueologicos</wfs:Title>
      <wfs:DefaultCRS>urn:ogc:def:crs:EPSG::4326</wfs:DefaultCRS>
    </wfs:FeatureType>
  </wfs:FeatureTypeList>
</wfs:WFS_Capabilities>"""

# WFS 1.1.0 usa otro espacio de nombres y DefaultSRS en vez de DefaultCRS.
CAPS_11 = """<?xml version="1.0"?>
<wfs:WFS_Capabilities xmlns:wfs="http://www.opengis.net/wfs" version="1.1.0">
  <wfs:FeatureTypeList>
    <wfs:FeatureType>
      <wfs:Name>cultura:camino_inca</wfs:Name>
      <wfs:Title>Camino inca</wfs:Title>
      <wfs:DefaultSRS>EPSG:4326</wfs:DefaultSRS>
    </wfs:FeatureType>
  </wfs:FeatureTypeList>
</wfs:WFS_Capabilities>"""

ERROR_PROXY = ("<html><head><title>500 Proxy Error</title></head><body>"
               "<h1>Proxy Error</h1><p>Reason: <strong>Error during SSL "
               "Handshake with remote server</strong></p></body></html>")


class _Resp:
    def __init__(self, texto, codigo=200):
        self.text, self.status_code = texto, codigo
        self.content = texto.encode("utf-8")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class Servidor:
    """GeoServer simulado. `caidas` = cuantos 500 suelta antes de funcionar."""

    def __init__(self, caps=CAPS_20, caidas=0, siempre_caido=False,
                 solo_bases=None):
        self.caps, self.caidas = caps, caidas
        self.siempre_caido = siempre_caido
        self.solo_bases = solo_bases
        self.llamadas = []

    def get(self, url, params=None, timeout=None):
        self.llamadas.append((url, dict(params or {})))
        if self.solo_bases is not None and url not in self.solo_bases:
            return _Resp(ERROR_PROXY, 500)
        if self.siempre_caido:
            return _Resp(ERROR_PROXY, 500)
        if self.caidas > 0:
            self.caidas -= 1
            return _Resp(ERROR_PROXY, 500)
        if (params or {}).get("request") == "GetCapabilities":
            version = (params or {}).get("version")
            if version == "2.0.0":
                return _Resp(self.caps if self.caps is CAPS_20 else "")
            if version == "1.1.0":
                return _Resp(CAPS_11 if self.caps is CAPS_11 else "")
            return _Resp("")
        return _Resp('{"type":"FeatureCollection","features":[]}')


# ------------------------------------------------- lectura de capabilities

def test_lee_las_capas_de_un_capabilities_2_0():
    capas = wfs.lee_capabilities(CAPS_20)
    assert [c["nombre"] for c in capas] == [
        "cultura:qhapaq_nan_tramos",
        "cultura:limites_distritales",
        "cultura:sitios_arqueologicos"]
    assert capas[0]["titulo"] == "Qhapaq Nan - tramos de camino"
    assert capas[0]["resumen"] == "Red vial inca registrada"
    assert "4326" in capas[0]["crs"]


def test_lee_capabilities_de_la_version_1_1_con_otro_namespace():
    """Las versiones usan espacios de nombres distintos; se leen igual."""
    capas = wfs.lee_capabilities(CAPS_11)
    assert [c["nombre"] for c in capas] == ["cultura:camino_inca"]
    assert capas[0]["crs"] == "EPSG:4326"


def test_lee_capabilities_devuelve_vacio_ante_un_error_de_proxy():
    """La pagina de error del proxy es HTML, no un capabilities."""
    assert wfs.lee_capabilities(ERROR_PROXY) == []
    assert wfs.lee_capabilities("") == []
    assert wfs.lee_capabilities("no soy xml <<<") == []


def test_encuentra_el_formato_json_que_el_servidor_admite():
    fmts = wfs.formatos_salida(CAPS_20)
    assert "application/json" in fmts
    assert wfs.formato_json(fmts) == "application/json"


def test_formato_json_acepta_variantes_y_se_rinde_si_no_hay():
    assert wfs.formato_json(["GML2", "application/geo+json"]) == "application/geo+json"
    assert wfs.formato_json(["text/xml; subtype=gml/3.2", "shape-zip"]) is None
    assert wfs.formato_json(["GEOJSON"]) == "GEOJSON"


# -------------------------------------------------------------- las URL

def test_getcapabilities_pide_solo_la_seccion_de_capas_en_2_0():
    """El documento completo de GeoServer pesa megas; la seccion, kilobytes."""
    _, p = wfs.url_capabilities(BASE, "2.0.0", solo_capas=True)
    assert p["sections"] == "FeatureTypeList"
    _, p11 = wfs.url_capabilities(BASE, "1.1.0", solo_capas=True)
    assert "sections" not in p11          # la 1.1.0 no lo admite


def test_getfeature_usa_el_nombre_de_parametro_de_cada_version():
    _, p20 = wfs.url_getfeature(BASE, "cultura:x", "2.0.0", limite=10)
    assert p20["typeNames"] == "cultura:x" and p20["count"] == 10
    _, p11 = wfs.url_getfeature(BASE, "cultura:x", "1.1.0", limite=10)
    assert p11["typeName"] == "cultura:x" and p11["maxFeatures"] == 10


def test_getfeature_no_manda_bbox():
    """El orden de los ejes del bbox cambio entre versiones y cada servidor
    lo interpreta a su manera: se baja entera y se recorta en geopandas."""
    _, p = wfs.url_getfeature(BASE, "cultura:x", "2.0.0")
    assert not any("bbox" in k.lower() for k in p)


# --------------------------------------------------- el proxy averiado

def test_reintenta_cuando_el_proxy_devuelve_500():
    s = Servidor(caidas=2)
    r = wfs.pide(s, BASE, {"request": "GetCapabilities", "version": "2.0.0"},
                 intentos=3, espera=0)
    assert r.status_code == 200
    assert len(s.llamadas) == 3


def test_se_rinde_despues_de_los_intentos():
    s = Servidor(siempre_caido=True)
    r = wfs.pide(s, BASE, {}, intentos=3, espera=0)
    assert r.status_code == 500
    assert len(s.llamadas) == 3


def test_no_reintenta_un_error_que_no_es_del_proxy():
    class _404:
        def __init__(self):
            self.llamadas = []

        def get(self, url, params=None, timeout=None):
            self.llamadas.append(url)
            return _Resp("no existe", 404)

    s = _404()
    assert wfs.pide(s, BASE, {}, intentos=3, espera=0).status_code == 404
    assert len(s.llamadas) == 1


def test_capabilities_atraviesa_un_proxy_intermitente():
    s = Servidor(caidas=1)
    version, xml = wfs.capabilities(BASE, s, intentos=3, espera=0)
    assert version == "2.0.0"
    assert wfs.lee_capabilities(xml)


def test_busca_endpoint_prueba_la_ruta_global_cuando_el_workspace_falla():
    """Es el caso real: /geoserver/cultura/ows da 500 y /geoserver/wfs no."""
    s = Servidor(solo_bases={BASE})
    base, version, xml = wfs.busca_endpoint(s, wfs.ENDPOINTS_GEOCAM, rondas=1)
    assert base == BASE
    assert version == "2.0.0"


def test_busca_endpoint_se_rinde_si_todo_esta_caido():
    base, version, xml = wfs.busca_endpoint(Servidor(siempre_caido=True),
                                            rondas=1)
    assert (base, version, xml) == (None, None, "")


def test_los_endpoints_incluyen_el_global_y_el_del_workspace():
    eps = wfs.ENDPOINTS_GEOCAM
    assert "https://geoservicios.cultura.gob.pe/geoserver/wfs" in eps
    assert "https://geoservicios.cultura.gob.pe/geoserver/cultura/ows" in eps
    assert eps.index("https://geoservicios.cultura.gob.pe/geoserver/wfs") == 0


# ------------------------------------------------ puntuacion de las capas

def test_el_buscador_elige_la_capa_del_camino_del_wfs():
    base, version, capas = buscar.capas_wfs(sesion=Servidor(), rondas=1)
    assert base == BASE
    assert capas[0]["capa"] == "cultura:qhapaq_nan_tramos"
    assert capas[0]["puntos"] > capas[-1]["puntos"]
    assert capas[-1]["capa"] == "cultura:limites_distritales"
    assert all(c["fuente"] == "wfs" for c in capas)


def test_el_buscador_devuelve_vacio_si_el_wfs_esta_caido():
    base, version, capas = buscar.capas_wfs(sesion=Servidor(siempre_caido=True),
                                            rondas=1)
    assert (base, version, capas) == ("", "", [])


# ----------------------------------------------------------- config.yaml

def test_la_config_acepta_el_wfs_y_lo_prefiere_al_rest(tmp_path):
    from camino import config
    cfg = config.Config.cargar()
    con_ambos = type(cfg)(**{**cfg.__dict__,
                            "geocam_wfs": "https://x/geoserver/wfs?service=WFS",
                            "geocam_servicio": "https://y/FeatureServer/0"})
    assert con_ambos.fuente_geocam() == ("wfs", "https://x/geoserver/wfs")


def test_la_config_cae_al_rest_si_no_hay_wfs():
    from camino import config
    cfg = config.Config.cargar()
    solo_rest = type(cfg)(**{**cfg.__dict__, "geocam_wfs": "",
                             "geocam_servicio": "https://y/FeatureServer/0/query"})
    assert solo_rest.fuente_geocam() == ("rest", "https://y/FeatureServer/0")


def test_la_config_explica_las_dos_vias_si_no_hay_ninguna():
    from camino import config
    cfg = config.Config.cargar()
    vacia = type(cfg)(**{**cfg.__dict__, "geocam_wfs": "",
                         "geocam_servicio": ""})
    with pytest.raises(SystemExit, match="WFS"):
        vacia.fuente_geocam()


def test_la_config_real_trae_el_endpoint_wfs_puesto():
    from camino import config
    cfg = config.Config.cargar()
    clase, url = cfg.fuente_geocam()
    assert clase == "wfs"
    assert url.startswith("https://geoservicios.cultura.gob.pe/geoserver")


def test_guarda_en_config_escribe_cualquiera_de_las_dos_claves(tmp_path):
    ruta = tmp_path / "config.yaml"
    ruta.write_text('  geocam_wfs: ""\n  geocam_capa: ""\n', encoding="utf-8")
    buscar.guarda_en_config(ruta, "https://x/wfs", clave="geocam_wfs")
    buscar.guarda_en_config(ruta, "cultura:tramos", clave="geocam_capa")
    texto = ruta.read_text(encoding="utf-8")
    assert '  geocam_wfs: "https://x/wfs"' in texto
    assert '  geocam_capa: "cultura:tramos"' in texto
