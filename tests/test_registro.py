"""Lectura del registro del Qhapaq Nan en KML/KMZ.

Lo que se protege aqui es la distincion entre camino OBSERVADO y camino
PROYECTADO. Las capas de "Proyeccion..." son tramos donde el camino ya no
esta y la linea la dibujo alguien infiriendo por donde iba; ajustar el
modelo contra ellas es circular. Si alguien las cuela sin querer, estas
pruebas lo cazan.
"""

import zipfile

import pytest

from camino import config, registro

HTML = """<html><body><table>
<tr><td>{campo}</td><td>{valor}</td></tr>
<tr><td>tramnomb</td><td>{tramo}</td></tr>
<tr><td>dptonomb</td><td>Amazonas</td></tr>
<tr><td>TipoCamino</td><td>{tipo}</td></tr>
</table></body></html>"""


def _kml(capas):
    """Un KML con una carpeta por capa y una linea en cada una."""
    cuerpo = []
    for nombre, (tramo, tipo, coords) in capas.items():
        desc = HTML.format(campo="longitud", valor="1.5", tramo=tramo, tipo=tipo)
        cuerpo.append(f"""
  <Folder><name>{nombre}</name>
    <Placemark>
      <name>{tramo}</name>
      <description><![CDATA[{desc}]]></description>
      <LineString><coordinates>{coords}</coordinates></LineString>
    </Placemark>
  </Folder>""")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            + "".join(cuerpo) + "</Document></kml>")


CAPAS = {
    "Trazo de Camino":
        ("Chillo - Chachapoyas", "Trazo de Camino",
         "-77.85,-6.60,0 -77.86,-6.50,0"),
    "Camino Registrado":
        ("Chillo - Chachapoyas", "Camino Registrado",
         "-77.86,-6.50,0 -77.87,-6.40,0"),
    "Proyección de Camino por Ausencia":
        ("Chillo - Chachapoyas", "Proyeccion",
         "-77.87,-6.40,0 -77.88,-6.30,0"),
    "Proyección de Camino por Daños":
        ("La Jalca - Mendoza", "Proyeccion",
         "-77.80,-6.70,0 -77.81,-6.65,0"),
}


@pytest.fixture
def kmz(tmp_path):
    kml = tmp_path / "doc.kml"
    kml.write_text(_kml(CAPAS), encoding="utf-8")
    ruta = tmp_path / "registro.kmz"
    with zipfile.ZipFile(ruta, "w") as z:
        z.write(kml, "doc.kml")
    return ruta


@pytest.fixture
def cfg():
    return config.Config.cargar()


# ---------------------------------------------------------- el KMZ

def test_abre_un_kmz_y_encuentra_el_kml_dentro(kmz):
    kml = registro.abrir_kmz(kmz)
    assert kml.suffix == ".kml"
    assert "<kml" in kml.read_text(encoding="utf-8")


def test_un_kml_suelto_se_usa_tal_cual(tmp_path):
    k = tmp_path / "x.kml"
    k.write_text(_kml(CAPAS), encoding="utf-8")
    assert registro.abrir_kmz(k) == k


def test_un_kmz_sin_kml_dentro_avisa(tmp_path):
    ruta = tmp_path / "vacio.kmz"
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("leeme.txt", "nada")
    with pytest.raises(SystemExit, match="ningun .kml"):
        registro.abrir_kmz(ruta)


def test_lista_las_capas(kmz):
    assert set(registro.capas(kmz)) == set(CAPAS)


# ------------------------------------------- observado contra proyectado

def test_clasifica_las_capas_del_registro():
    assert registro.clasifica("Trazo de Camino") == "observado"
    assert registro.clasifica("Camino Registrado") == "observado"
    assert registro.clasifica("Camino Identificado") == "observado"
    assert registro.clasifica("Camino Afectado") == "observado"
    assert registro.clasifica("Proyección de Camino por Ausencia") == "proyectado"
    assert registro.clasifica("Proyección de Camino por Daños") == "proyectado"
    assert registro.clasifica("Proyección de Camino por Reemplazo") == "proyectado"
    assert registro.clasifica("Curvas de nivel") == "otro"


def test_la_clasificacion_no_depende_de_tildes():
    assert registro.clasifica("Proyeccion de Camino por Danos") == "proyectado"
    assert registro.clasifica("PROYECCIÓN DE CAMINO POR DAÑOS") == "proyectado"


def test_por_omision_las_proyecciones_quedan_fuera(kmz, cfg):
    """Ajustar un modelo de costo contra una linea que alguien ya proyecto
    recupera los supuestos de quien la dibujo, no el camino."""
    g = registro.lee(kmz, cfg.crs)
    assert set(g["categoria"]) == {"observado"}
    assert set(g["capa"]) == {"Trazo de Camino", "Camino Registrado"}


def test_se_pueden_pedir_tambien_las_proyecciones(kmz, cfg):
    g = registro.lee(kmz, cfg.crs, solo_observadas=False)
    assert set(g["categoria"]) == {"observado", "proyectado"}
    assert len(g) == 4


def test_se_pueden_fijar_capas_concretas(kmz, cfg):
    g = registro.lee(kmz, cfg.crs, capas_pedidas=["Camino Registrado"])
    assert set(g["capa"]) == {"Camino Registrado"}


def test_avisa_si_ninguna_capa_sirve(tmp_path, cfg):
    kml = tmp_path / "doc.kml"
    kml.write_text(_kml({"Curvas de nivel":
                         ("x", "y", "-77.8,-6.5,0 -77.9,-6.6,0")}),
                   encoding="utf-8")
    with pytest.raises(SystemExit, match="Ninguna capa util"):
        registro.lee(kml, cfg.crs)


# ------------------------------------------------- atributos en el HTML

def test_saca_los_atributos_de_la_tabla_html():
    at = registro.atributos(HTML.format(campo="longitud", valor="5.97",
                                        tramo="Chillo - Chachapoyas",
                                        tipo="Trazo de Camino"))
    assert at["tramnomb"] == "Chillo - Chachapoyas"
    assert at["dptonomb"] == "Amazonas"
    assert at["longitud"] == "5.97"


def test_los_atributos_sobreviven_a_algo_que_no_es_html():
    assert registro.atributos(None) == {}
    assert registro.atributos("texto suelto") == {}


def test_las_columnas_del_registro_llegan_al_geodataframe(kmz, cfg):
    g = registro.lee(kmz, cfg.crs)
    for campo in ("tramnomb", "dptonomb", "TipoCamino", "capa", "categoria"):
        assert campo in g.columns
    assert set(g["tramnomb"]) == {"Chillo - Chachapoyas"}
    assert g.crs.to_string() == cfg.crs


# ------------------------------------------------------------- tramos

def test_el_inventario_mide_lo_continuo_no_lo_sumado(kmz, cfg):
    """Los dos rasgos observados se tocan en (-77.86,-6.50): cuentan como
    una sola pieza continua, no como dos sueltas."""
    g = registro.lee(kmz, cfg.crs)
    inv = registro.tramos(g)
    assert len(inv) == 1
    nombre, n, km, continuo = inv[0]
    assert nombre == "Chillo - Chachapoyas"
    assert n == 2
    assert continuo == pytest.approx(km, rel=1e-6)   # se cosen enteros


def test_el_inventario_ordena_por_continuo(kmz, cfg):
    g = registro.lee(kmz, cfg.crs, solo_observadas=False)
    inv = registro.tramos(g)
    assert [f[0] for f in inv][0] == "Chillo - Chachapoyas"
    assert all(inv[i][3] >= inv[i + 1][3] for i in range(len(inv) - 1))


# ------------------------------------------- filtro de tramo y recorte

def test_filtra_el_tramo_que_pide_la_config(kmz, cfg):
    from camino import ruta
    g = registro.lee(kmz, cfg.crs, solo_observadas=False)
    con = type(cfg)(**{**cfg.__dict__, "unidad": "sector",
                       "tramo": "La Jalca - Mendoza"})
    sel = ruta.filtra_tramo(con, g)
    assert set(sel["tramnomb"]) == {"La Jalca - Mendoza"}


def test_avisa_si_el_tramo_pedido_no_esta(kmz, cfg):
    from camino import ruta
    g = registro.lee(kmz, cfg.crs)
    con = type(cfg)(**{**cfg.__dict__, "unidad": "sector",
                       "tramo": "Cusco - Puno"})
    with pytest.raises(SystemExit, match="no aparece en la caja"):
        ruta.filtra_tramo(con, g)


def test_sin_tramo_se_queda_con_todo(kmz, cfg):
    from camino import ruta
    g = registro.lee(kmz, cfg.crs, solo_observadas=False)
    con = type(cfg)(**{**cfg.__dict__, "unidad": "sector", "tramo": ""})
    assert len(ruta.filtra_tramo(con, g)) == len(g)


def test_el_resumen_cose_antes_de_medir_lo_continuo(kmz, cfg):
    """Era un error real: medir el rasgo mas largo por separado daba 7.96 km
    donde habia 12.40 km continuos."""
    from camino import descarga
    g = registro.lee(kmz, cfg.crs)
    mayor, piezas = descarga.continuo_mayor(g)
    assert piezas == 1
    assert mayor == pytest.approx(float(g.geometry.length.sum()), rel=1e-6)


def test_el_recorte_corta_la_geometria_no_solo_la_selecciona(cfg):
    """Fuera de la caja no hay DEM, asi que ese trozo no se puede modelar."""
    import geopandas as gpd
    from camino import descarga
    from shapely.geometry import LineString

    oeste, sur, este, norte = cfg.bbox
    larga = LineString([(oeste + 0.01, sur + 0.01), (oeste - 2.0, sur - 2.0)])
    g = gpd.GeoDataFrame({"n": [1]}, geometry=[larga],
                         crs="EPSG:4326").to_crs(cfg.crs)
    antes = float(g.geometry.length.iloc[0])
    despues = float(descarga.recorta(g, cfg).geometry.length.sum())
    assert despues < antes / 10
