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


def test_un_grupo_disperso_ya_no_arrastra_la_caja(tmp_path, capsys):
    """El arreglo de fondo: se mide la pieza que TOCA la caja.

    Antes se tomaba la pieza continua mayor del grupo entero, que para una
    etiqueta esta en otro departamento, y la caja propuesta se iba al otro
    lado del pais: 'En proceso' pedia 582 M de celdas.
    """
    cfg = _con_en_proceso(tmp_path)
    salida = caja.informe(cfg)

    # el grupo sigue estando (no se excluye por una regla automatica)
    assert "En proceso" in {t["tramo"] for t in salida["tramos"]}
    # pero lo que se mide de el es la pieza de dentro de la caja
    fila = next(t for t in salida["tramos"] if t["tramo"] == "En proceso")
    assert fila["continuo_completo_km"] < 2.0
    # y la caja propuesta no se va a Ayacucho
    if "caja_para_todos" in salida:
        assert salida["caja_para_todos"][1] > -7.0

    # y avisa de que parece una etiqueta
    assert "parece una ETIQUETA" in capsys.readouterr().out


def test_no_descarta_un_tramo_real_aunque_sea_larguisimo(tmp_path, capsys):
    """Regresion del error que Javier caza en la corrida del 5-oct.

    Una regla automatica descartaba por diagonal > 150 km y dijo que Xauxa -
    Pachacamac (163 km), La Raya - Desaguadero (293), Pumpu - Pallasca (338)
    y Acostambo - Huamachuco (588) "no son tramos". Son secciones reales del
    Qhapaq Nan, varias inscritas en la UNESCO.
    """
    import geopandas as gpd
    import numpy as np
    from shapely.geometry import LineString

    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(CONFIG, f)
    cfg = config.Config.cargar(tmp_path / "config.yaml")

    # un tramo real, continuo, que entra en la caja y sigue 500 km al sur
    n = 400
    larguisimo = LineString(np.column_stack([
        np.linspace(-77.89, -77.50, n), np.linspace(-6.40, -10.90, n)]))
    gpd.GeoDataFrame({"tramnomb": ["Acostambo - Huamachuco"]},
                     geometry=[larguisimo], crs="EPSG:4326").to_crs(cfg.crs) \
        .to_file(cfg.dir_datos / "registro.gpkg", layer="camino", driver="GPKG")

    salida = caja.informe(cfg)
    nombres = {t["tramo"] for t in salida["tramos"]}
    assert "Acostambo - Huamachuco" in nombres
    texto = capsys.readouterr().out
    assert "no es un tramo" not in texto
    # es continuo, asi que tampoco dispara el aviso de etiqueta
    assert "parece una ETIQUETA" not in texto


def test_se_puede_excluir_un_tramo_a_mano(tmp_path, capsys):
    import dataclasses
    cfg = _con_en_proceso(tmp_path)
    excluido = dataclasses.replace(cfg, tramos_excluidos=("En proceso",))
    salida = caja.informe(excluido)
    assert "En proceso" not in {t["tramo"] for t in salida["tramos"]}
    assert "excluidos por config.yaml" in capsys.readouterr().out


def test_la_dispersion_separa_una_etiqueta_de_un_camino():
    """La medida que informa: razon diagonal/largo.

    Un camino es al menos tan largo como la recta entre sus extremos, asi
    que su razon ronda 1. Una etiqueta repartida por el mapa tiene mucha
    diagonal y poca linea.
    """
    import geopandas as gpd
    import numpy as np
    from shapely.geometry import LineString
    from camino import registro

    n = 200
    camino = gpd.GeoDataFrame(geometry=[LineString(np.column_stack([
        np.linspace(0, 0, n), np.linspace(0, 500_000, n)]))], crs="EPSG:32718")
    _, _, razon_camino = registro.dispersion(camino)
    assert razon_camino < 1.1

    etiqueta = gpd.GeoDataFrame(geometry=[
        LineString([(0, 0), (0, 1000)]),
        LineString([(500_000, 900_000), (500_000, 901_000)])],
        crs="EPSG:32718")
    _, _, razon_etiqueta = registro.dispersion(etiqueta)
    assert razon_etiqueta > 100

    assert registro.avisa_si_parece_etiqueta(camino, "real") == ""
    assert "parece una ETIQUETA" in registro.avisa_si_parece_etiqueta(
        etiqueta, "En proceso")


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


def test_reporta_la_unidad_de_hoy_aparte_de_la_pieza_que_crece(tmp_path):
    """Las dos medidas, porque pueden venir de piezas distintas.

    A Chachapoyas - Cochamal `caja` le daba 6.59 km y `ruta` 8.55: los dos
    correctos. 8.55 es la pieza continua mayor DENTRO de la caja, que es la
    unidad de analisis; 6.59 es el pedazo de dentro de la OTRA pieza, la que
    se sale. Sin reportar las dos, parece que uno de los numeros esta mal.
    """
    import geopandas as gpd
    import numpy as np
    from shapely.geometry import LineString

    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump({**CONFIG,
                        "barrido": {**CONFIG["barrido"],
                                    "largo_min_unidad": 1500}}, f)
    cfg = config.Config.cargar(tmp_path / "config.yaml")

    # dos piezas del MISMO tramo, separadas: una larga toda dentro de la
    # caja, otra que se sale por el este con poco adentro
    dentro = LineString([(-77.898, -6.418), (-77.898, -6.392)])       # ~2.9 km
    se_sale = LineString(np.column_stack([
        np.linspace(-77.875, -77.70, 50), np.full(50, -6.405)]))
    gpd.GeoDataFrame({"tramnomb": ["Dos piezas", "Dos piezas"]},
                     geometry=[dentro, se_sale], crs="EPSG:4326") \
        .to_crs(cfg.crs).to_file(cfg.dir_datos / "registro.gpkg",
                                 layer="camino", driver="GPKG")

    fila = caja.informe(cfg)["tramos"][0]
    assert fila["tramo"] == "Dos piezas"
    # la unidad de hoy es la pieza de dentro; la que crece es la otra
    assert fila["unidad_de_hoy_km"] > fila["continuo_en_la_caja_km"]
    assert fila["continuo_completo_km"] > fila["continuo_en_la_caja_km"]
    assert fila["entra_completo"] is False


def test_el_filtro_mira_la_unidad_de_hoy(tmp_path):
    """Un tramo cuya pieza completa es larga pero cuya unidad de hoy no llega
    al minimo NO es candidato: hoy no entra al analisis.

    Es lo que pasa con Pueblo Viejo - La Jalca Grande: 7.90 km de unidad,
    por debajo del filtro de 8 km.
    """
    import geopandas as gpd
    import numpy as np
    from shapely.geometry import LineString

    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump({**CONFIG,
                        "barrido": {**CONFIG["barrido"],
                                    "largo_min_unidad": 5000}}, f)
    cfg = config.Config.cargar(tmp_path / "config.yaml")

    corto_dentro = LineString(np.column_stack([
        np.linspace(-77.895, -77.885, 30), np.full(30, -6.405)]))   # ~1.1 km
    gpd.GeoDataFrame({"tramnomb": ["Corto adentro"]},
                     geometry=[corto_dentro], crs="EPSG:4326") \
        .to_crs(cfg.crs).to_file(cfg.dir_datos / "registro.gpkg",
                                 layer="camino", driver="GPKG")

    salida = caja.informe(cfg)
    assert salida["tramos"][0]["unidad_de_hoy_km"] < 5.0
    # no es candidato, asi que no hay nada que proponer
    assert "caja_para_todos" not in salida


def test_el_margen_sale_de_buffer_corredor_y_no_de_un_numero_a_mano(tmp_path):
    """La caja propuesta tiene que dejar al menos `buffer_corredor` de aire.

    Si no, la mascara del corredor queda recortada por el borde justo donde
    el tramo termina, el camino modelado se pega a ese borde y `revisar` lo
    marca con 'B' -- y arreglarlo obliga a volver a correr desde `bajar`.
    Habia un margen fijo de 0.02 grados (~2.2 km), MENOR que el buffer de 4
    km del proyecto: la propuesta venia mal por construccion.
    """
    import dataclasses
    import geopandas as gpd
    import numpy as np
    from shapely.geometry import LineString, box

    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump({**CONFIG,
                        "barrido": {**CONFIG["barrido"],
                                    "largo_min_unidad": 1000}}, f)
    base = config.Config.cargar(tmp_path / "config.yaml")

    se_sale = LineString(np.column_stack([
        np.linspace(-77.885, -77.84, 40), np.full(40, -6.405)]))
    gpd.GeoDataFrame({"tramnomb": ["Se sale"]}, geometry=[se_sale],
                     crs="EPSG:4326").to_crs(base.crs) \
        .to_file(base.dir_datos / "registro.gpkg", layer="camino",
                 driver="GPKG")

    anchos = {}
    for buffer in (1000.0, 8000.0):
        cfg = dataclasses.replace(base, buffer_corredor=buffer)
        bb = caja.informe(cfg)["caja_para_todos"]
        # el extremo del tramo tiene que quedar a mas de `buffer` del borde
        extremo = gpd.GeoSeries([se_sale], crs="EPSG:4326").to_crs(cfg.crs)[0]
        caja_m = gpd.GeoSeries([box(*bb)], crs="EPSG:4326").to_crs(cfg.crs)[0]
        assert extremo.distance(caja_m.exterior) >= buffer, buffer
        anchos[buffer] = caja_m.bounds[2] - caja_m.bounds[0]

    # y un buffer mayor pide una caja mayor
    assert anchos[8000.0] > anchos[1000.0]


def test_la_caja_propuesta_nunca_es_mas_chica_que_la_actual(tmp_path):
    cfg = _con_en_proceso(tmp_path)
    salida = caja.informe(cfg)
    if "caja_para_todos" not in salida:
        return
    o, s, e, n = salida["caja_para_todos"]
    o0, s0, e0, n0 = salida["caja_actual"]
    assert o <= o0 and s <= s0 and e >= e0 and n >= n0
