"""Los espacios ceremoniales: el unico dato de entrada que no es terreno.

Las dos componentes del modelo ampliado -- proximidad y visibilidad -- salen
de este archivo, asi que las reglas de diseno del proyecto que viven aqui
(excluir los sitios de los extremos del tramo) se prueban aqui.
"""

import dataclasses

import numpy as np
import pytest
import yaml
from shapely.geometry import LineString

from camino import config, sitios

CONFIG_MINIMA = {
    "extension": {
        "bbox": {"oeste": -77.90, "sur": -6.42, "este": -77.87, "norte": -6.39},
        "crs": "EPSG:32718", "resolucion": 30,
    },
    "datos": {},
    "costo": {"g_max": 0.45, "epsilon": 0.01, "percentiles": [5.0, 95.0],
              "componentes_referencia": ["fisico"],
              "componentes_ampliado": ["fisico", "ceremonial"],
              "vecindad": 16},
    "ceremonial": {"archivo": "", "distancia_saturacion": 5000,
                   "radio_extremos": 500},
    "dominio": {"buffer_corredor": 4000, "umbral_quebrada": 500},
    "barrido": {"n_simplex": 4, "n_sectores": 2, "m_nulos": 5, "tau_max": 0.5,
                "semilla": 1, "n_trabajos": 1},
}


@pytest.fixture
def cfg(tmp_path):
    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(CONFIG_MINIMA, f)
    return config.Config.cargar(tmp_path / "config.yaml")


# ------------------------------------------- la regla de los extremos

def test_quita_los_sitios_de_los_extremos_del_tramo():
    """REGLA DEL PROYECTO: un sitio en el inicio o el final del tramo no
    puede ser predictor, porque el camino tiene que llegar ahi de todas
    formas. Si se deja, la componente mide el enunciado, no el paisaje."""
    linea = LineString([(0, 0), (0, 10000)])
    puntos = np.array([[100.0, 100.0],        # pegado al inicio: fuera
                       [50.0, 9800.0],        # pegado al final: fuera
                       [300.0, 5000.0]])      # a media altura: se queda
    quedan, quitados = sitios.sin_los_extremos(puntos, linea, 500.0)
    assert quitados == 2
    assert quedan.tolist() == [[300.0, 5000.0]]


def test_con_radio_cero_solo_quita_la_coincidencia_exacta():
    """radio_extremos = 0 no apaga la regla: la deja en su forma literal,
    que es la del proyecto -- "un espacio ceremonial que COINCIDA con el
    inicio o el termino del tramo". Un sitio a 1 m ya se queda."""
    linea = LineString([(0, 0), (0, 1000)])
    puntos = np.array([[0.0, 0.0],        # coincide con el inicio
                       [1.0, 0.0],        # a 1 m: se queda
                       [0.0, 500.0]])
    quedan, quitados = sitios.sin_los_extremos(puntos, linea, 0.0)
    assert quitados == 1
    assert quedan.tolist() == [[1.0, 0.0], [0.0, 500.0]]


def test_sin_sitios_devuelve_vacio_sin_fallar():
    linea = LineString([(0, 0), (0, 1000)])
    quedan, quitados = sitios.sin_los_extremos(np.empty((0, 2)), linea, 500.0)
    assert len(quedan) == 0 and quitados == 0


# ------------------------------------------------------ leer el archivo

def test_lee_un_csv_con_lon_lat(cfg):
    (cfg.dir_datos / "sitios.csv").write_text(
        "nombre,lon,lat\nKuelap,-77.925,-6.418\nRevash,-77.87,-6.40\n",
        encoding="utf-8")
    puntos, nombres = sitios.carga(cfg)
    assert nombres == ["Kuelap", "Revash"]
    assert puntos.shape == (2, 2)
    # proyectado a UTM 18S: metros, no grados
    assert 100_000 < puntos[0, 0] < 900_000
    assert 9_200_000 < puntos[0, 1] < 9_400_000


def test_un_csv_sin_coordenadas_lo_dice(cfg):
    (cfg.dir_datos / "sitios.csv").write_text(
        "nombre,periodo\nKuelap,Chachapoya\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="columnas de coordenadas"):
        sitios.carga(cfg)


def test_sin_archivo_de_sitios_no_revienta(cfg):
    puntos, nombres = sitios.carga(cfg)
    assert len(puntos) == 0 and nombres == []


def test_un_archivo_que_no_existe_se_dice_claro(cfg):
    malo = dataclasses.replace(cfg, ceremonial_archivo="datos/no_existe.gpkg")
    with pytest.raises(SystemExit, match="No encuentro el archivo"):
        sitios.carga(malo)


# ------------------------- el hueco para un apu, el dia que haya uno

def test_sin_puntos_en_la_config_la_lista_sale_vacia(cfg):
    """Hoy esta vacia A PROPOSITO: no hay cerro tutelar documentado para el
    corredor del Utcubamba."""
    assert cfg.visibilidad_puntos == ()
    assert sitios.puntos_de_config(cfg).shape == (0, 2)


def test_un_punto_escrito_a_mano_se_proyecta(cfg):
    con_apu = dataclasses.replace(cfg, visibilidad_puntos=("-6.418,-77.925",))
    p = sitios.puntos_de_config(con_apu)
    assert p.shape == (1, 2)
    assert 100_000 < p[0, 0] < 900_000 and 9_200_000 < p[0, 1] < 9_400_000


def test_un_punto_mal_escrito_explica_el_formato(cfg):
    malo = dataclasses.replace(cfg, visibilidad_puntos=("Cerro Puma",))
    with pytest.raises(SystemExit, match="lat,lon"):
        sitios.puntos_de_config(malo)
