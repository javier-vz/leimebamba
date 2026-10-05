"""La ayuda que pone un numero delante de la decision del bbox.

De las seis unidades de la corrida real, cuatro llegan al borde de la caja.
Esto no lo decide: lo mide.
"""

import numpy as np
import pytest
import yaml

from camino import caja, config

CONFIG = {
    "extension": {
        "bbox": {"oeste": -77.90, "sur": -6.42, "este": -77.87, "norte": -6.39},
        "crs": "EPSG:32718", "resolucion": 30,
    },
    "datos": {},
    "costo": {"g_max": 0.45, "epsilon": 0.01, "percentiles": [5.0, 95.0],
              "componentes_referencia": ["fisico"],
              "componentes_ampliado": ["fisico", "ceremonial"],
              "vecindad": 16},
    "dominio": {"buffer_corredor": 600, "umbral_quebrada": 500},
    "barrido": {"n_simplex": 4, "unidad": "tramo", "largo_min_unidad": 1000,
                "n_sectores": 2, "m_nulos": 5, "tau_max": 0.5,
                "semilla": 1, "n_trabajos": 1},
}


@pytest.fixture
def proyecto(tmp_path):
    """Dos tramos: uno dentro de la caja, otro que se sale por el este."""
    import geopandas as gpd
    from shapely.geometry import LineString

    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(CONFIG, f)
    cfg = config.Config.cargar(tmp_path / "config.yaml")

    dentro = LineString([(-77.895, -6.415), (-77.895, -6.395)])
    fuera = LineString([(-77.885, -6.405), (-77.800, -6.405)])   # sale al este
    gpd.GeoDataFrame(
        {"tramnomb": ["Entero", "Cortado"]},
        geometry=[dentro, fuera], crs="EPSG:4326").to_crs(cfg.crs) \
        .to_file(cfg.dir_datos / "registro.gpkg", layer="camino", driver="GPKG")
    return cfg


def test_distingue_el_tramo_entero_del_cortado(proyecto, capsys):
    salida = caja.informe(proyecto)
    por_nombre = {t["tramo"]: t for t in salida["tramos"]}

    assert por_nombre["Entero"]["entra_completo"] is True
    assert por_nombre["Cortado"]["entra_completo"] is False

    # el cortado mide mas completo que dentro de la caja; el entero, igual
    c = por_nombre["Cortado"]
    assert c["continuo_completo_km"] > c["continuo_en_la_caja_km"] + 1
    e = por_nombre["Entero"]
    assert e["continuo_completo_km"] == pytest.approx(
        e["continuo_en_la_caja_km"], abs=0.05)

    texto = capsys.readouterr().out
    assert "CORTADO" in texto


def test_la_caja_propuesta_contiene_el_tramo_cortado(proyecto):
    salida = caja.informe(proyecto)
    o, s, e, n = salida["caja_para_todos"]
    o0, s0, e0, n0 = salida["caja_actual"]

    # crece, y crece hacia el este, que es por donde se sale el tramo
    assert e > e0 and o <= o0 and n >= n0 and s <= s0
    assert e > -77.80
    assert salida["factor"] > 1.0
    assert (salida["celdas_para_todos"][0]
            > salida["celdas_actuales"][0])


def test_sin_tramos_cortados_no_propone_nada(tmp_path):
    """Si todo entra, no hay decision que tomar y lo dice."""
    import geopandas as gpd
    from shapely.geometry import LineString

    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(CONFIG, f)
    cfg = config.Config.cargar(tmp_path / "config.yaml")
    linea = LineString([(-77.895, -6.415), (-77.895, -6.395)])
    gpd.GeoDataFrame({"tramnomb": ["Entero"]}, geometry=[linea],
                     crs="EPSG:4326").to_crs(cfg.crs) \
        .to_file(cfg.dir_datos / "registro.gpkg", layer="camino", driver="GPKG")

    salida = caja.informe(cfg)
    assert "caja_para_todos" not in salida


def test_sin_archivo_lo_dice_en_vez_de_reventar(tmp_path):
    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(CONFIG, f)
    cfg = config.Config.cargar(tmp_path / "config.yaml")
    with pytest.raises(SystemExit, match="No hay archivo de geometria"):
        caja.informe(cfg)


def test_una_fuente_sin_tramos_con_nombre_lo_dice(tmp_path):
    import geopandas as gpd
    from shapely.geometry import LineString

    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(CONFIG, f)
    cfg = config.Config.cargar(tmp_path / "config.yaml")
    gpd.GeoDataFrame(
        geometry=[LineString([(-77.895, -6.415), (-77.895, -6.395)])],
        crs="EPSG:4326").to_crs(cfg.crs) \
        .to_file(cfg.dir_datos / "registro.gpkg", layer="camino", driver="GPKG")
    with pytest.raises(SystemExit, match="no trae tramos con nombre"):
        caja.informe(cfg)


def _con_en_proceso(tmp_path, nombre="En proceso"):
    """Un registro con un grupo repartido por medio pais, como el real.

    'En proceso' no es un tramo: es un estado de trabajo del Ministerio, y en
    el KMZ aparece en rasgos de Ayacucho a Amazonas. Agrupado por nombre, su
    caja envolvente mide 551 x 924 km y arrastra la caja propuesta a 180
    veces la necesaria.
    """
    import geopandas as gpd
    from shapely.geometry import LineString

    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(CONFIG, f)
    cfg = config.Config.cargar(tmp_path / "config.yaml")

    geoms = [
        LineString([(-77.895, -6.415), (-77.895, -6.395)]),      # tramo real
        LineString([(-77.890, -6.410), (-77.885, -6.405)]),      # en la caja
        # el pedazo de Ayacucho, y MAS LARGO que el de la caja: asi la pieza
        # continua mayor del grupo cae fuera, que es lo que pasa de verdad
        LineString([(-74.000, -13.500), (-74.000, -13.100)]),
    ]
    gpd.GeoDataFrame({"tramnomb": ["Entero", nombre, nombre]},
                     geometry=geoms, crs="EPSG:4326").to_crs(cfg.crs) \
        .to_file(cfg.dir_datos / "registro.gpkg", layer="camino", driver="GPKG")
    return cfg


def test_un_grupo_repartido_por_el_pais_no_cuenta_como_tramo(tmp_path, capsys):
    cfg = _con_en_proceso(tmp_path)
    salida = caja.informe(cfg)

    assert "En proceso" not in {t["tramo"] for t in salida["tramos"]}
    texto = capsys.readouterr().out
    assert "no es un tramo" in texto
    assert "km de diagonal" in texto

    # y la caja propuesta no se va a Ayacucho
    if "caja_para_todos" in salida:
        assert salida["caja_para_todos"][1] > -7.0


def test_se_puede_excluir_un_tramo_a_mano(tmp_path, capsys):
    import dataclasses
    cfg = _con_en_proceso(tmp_path, nombre="Pauja - Santa Cruz")
    # con un nombre normal, la diagonal lo delata igual
    caja.informe(cfg)
    assert "no es un tramo" in capsys.readouterr().out

    # y con la deteccion apagada, la lista a mano sigue sirviendo
    sin_deteccion = dataclasses.replace(
        cfg, diagonal_max_tramo=1e12,
        tramos_excluidos=("Pauja - Santa Cruz",))
    salida = caja.informe(sin_deteccion)
    assert "Pauja - Santa Cruz" not in {t["tramo"] for t in salida["tramos"]}
    assert "excluido a mano" in capsys.readouterr().out


def test_sin_la_deteccion_el_grupo_disperso_arrastra_la_caja(tmp_path):
    """La prueba de que el problema era real: con la deteccion apagada, la
    caja propuesta se va a cientos de millones de celdas."""
    import dataclasses
    cfg = dataclasses.replace(_con_en_proceso(tmp_path),
                              diagonal_max_tramo=1e12,
                              largo_min_unidad=100.0)
    salida = caja.informe(cfg)
    a, al = salida["celdas_para_todos"]
    assert a * al > 100e6
    assert salida["caja_para_todos"][1] < -13.0      # llega a Ayacucho


def test_el_acumulado_crece_y_cuenta_las_unidades(proyecto):
    salida = caja.informe(proyecto)
    acc = salida["acumulado"]
    assert len(acc) >= 1
    celdas = [f["celdas"][0] * f["celdas"][1] for f in acc]
    assert celdas == sorted(celdas)
    for f in acc:
        assert f["unidades_completas"] >= 1
        assert f["memoria_grafo_gb"] >= 0
        assert len(f["tramos_anadidos"]) >= 1


def test_la_memoria_crece_con_la_caja_y_con_las_componentes():
    """La cuenta que decide si la caja ancha cabe en la laptop."""
    chica = caja._memoria_gb(3_142_236, 2)
    grande = caja._memoria_gb(8_000_000, 2)
    tres = caja._memoria_gb(3_142_236, 3)
    assert grande > chica
    assert tres > chica
    # la corrida real: 3.14 M celdas, 2 componentes, del orden de 1 GB
    assert 0.3 < chica < 3.0
