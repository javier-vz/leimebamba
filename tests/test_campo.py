"""De la razon de costo por tramo a una salida de campo."""

import numpy as np
import pytest
from shapely.geometry import LineString

from camino import campo


def recta(x0, y0, x1, y1, n=40):
    return LineString(np.column_stack([np.linspace(x0, x1, n),
                                       np.linspace(y0, y1, n)]))


# ------------------------------------------------- el perfil y las zonas

def test_el_perfil_mide_la_separacion_a_lo_largo_del_registrado():
    obs = recta(0, 0, 3000, 0)
    mod = recta(0, 400, 3000, 400)       # paralela, 400 m al norte
    s, puntos, d = campo.perfil(obs, mod)

    assert s[0] == 0 and s[-1] == pytest.approx(3000, abs=1)
    assert len(puntos) == len(d) == len(s)
    assert d.min() == pytest.approx(400, abs=5)


def test_la_zona_empieza_y_acaba_donde_las_rutas_van_JUNTAS():
    """El borde se toma un paso antes de cruzar el umbral: ese es el unico
    punto desde el que alguien habria visto las dos opciones."""
    s = np.arange(0, 3000, 30.0)
    d = np.zeros_like(s)
    d[20:60] = 900.0                     # separadas entre el km 0.6 y el 1.8

    zs = campo.zonas(s, d)
    assert len(zs) == 1
    z = zs[0]
    assert d[z["i"]] == 0 and d[z["j"]] == 0          # bordes, ya juntas
    assert d[z["k"]] == 900.0                          # el maximo, dentro


def test_una_separacion_corta_no_es_zona():
    """Un bache de digitalizacion no manda a nadie a campo."""
    s = np.arange(0, 3000, 30.0)
    d = np.zeros_like(s)
    d[20:30] = 900.0                     # 300 m: por debajo del minimo
    assert campo.zonas(s, d) == []


def test_una_separacion_chica_no_es_zona_por_larga_que_sea():
    s = np.arange(0, 6000, 30.0)
    d = np.full_like(s, 200.0)           # 200 m, por debajo del umbral
    assert campo.zonas(s, d) == []


def test_dos_zonas_separadas_no_se_funden():
    s = np.arange(0, 6000, 30.0)
    d = np.zeros_like(s)
    d[20:60] = 900.0
    d[120:160] = 700.0
    zs = campo.zonas(s, d)
    assert len(zs) == 2
    assert zs[0]["j"] < zs[1]["i"]


# ------------------------------------------------------ elegir los objetivos

def fila(tramo, zona=1, razon=1.2, km=7.0):
    return {"tramo": tramo, "zona": zona, "razon_local": razon,
            "largo_registrado_km": km}


def test_una_zona_demasiado_larga_no_es_un_destino():
    """41 km con razon alta no es una salida de campo: el desvio esta
    repartido y no hay lugar al que llegar. El filtro va ANTES de ordenar."""
    filas = [fila("A", razon=1.30, km=41.0),      # la peor, pero inmensa
             fila("B", razon=1.25, km=7.0),
             fila("C", razon=1.20, km=6.0)]
    elegidas = campo.elige(filas, {}, cuantas=2)

    assert [f["tramo"] for f in elegidas] == ["B", "C"]
    assert all(f["largo_registrado_km"] <= campo.KM_MAX_ZONA for f in elegidas)


def test_el_control_entra_aunque_su_razon_sea_la_mas_baja():
    """Sin un tramo donde el modelo acierta, lo que se encuentre en los
    otros no tiene con que compararse."""
    filas = [fila("A", razon=1.40), fila("B", razon=1.30),
             fila("C", razon=1.20), fila("D", razon=1.10),
             fila("CONTROL", razon=1.03)]
    razones = {"A": 1.45, "B": 1.30, "C": 1.22, "D": 1.15, "CONTROL": 1.03}

    elegidas = campo.elige(filas, razones, cuantas=4)
    nombres = [f["tramo"] for f in elegidas]

    assert "CONTROL" in nombres
    assert len(elegidas) == 5            # las cuatro peores + el control
    assert elegidas[-1]["control"] is True
    assert elegidas[0]["prioridad"] == 1


def test_el_control_no_se_duplica_si_ya_estaba_elegido():
    filas = [fila("A", razon=1.40), fila("B", razon=1.03)]
    elegidas = campo.elige(filas, {"A": 1.45, "B": 1.03}, cuantas=2)
    assert [f["tramo"] for f in elegidas] == ["A", "B"]
    assert len(elegidas) == 2


# ----------------------------------------------------------- las estaciones

def objetivo(tramo="Pauja - Santa Cruz"):
    obs = recta(0, 0, 8000, 0)
    mod = recta(0, 1500, 8000, 1500)
    return {"tramo": tramo, "zona": 1, "razon_local": 1.37, "prioridad": 1,
            "control": False, "desde_km": 0.0, "hasta_km": 8.0,
            "_obs": obs, "_mod": mod, "_trozo": obs, "_alterna": mod,
            "_a": obs.interpolate(0.0), "_b": obs.interpolate(obs.length)}


def test_cada_zona_da_ocho_estaciones_de_los_tres_tipos():
    pts = campo.estaciones([objetivo()])
    assert len(pts) == 8
    tipos = [p["tipo"] for p in pts]
    assert tipos.count("A") == 3 and tipos.count("B") == 3
    assert tipos.count("C") == 2


def test_las_estaciones_B_caen_sobre_la_ruta_del_modelo():
    """Son las que pueden cambiar el resultado: si estuvieran sobre el camino
    registrado no buscarian nada."""
    o = objetivo()
    pts = campo.estaciones([o])
    for p in pts:
        if p["tipo"] == "B":
            assert p["geometry"].distance(o["_mod"]) < 1.0
            assert p["geometry"].distance(o["_obs"]) > 1000.0
        if p["tipo"] == "A":
            assert p["geometry"].distance(o["_obs"]) < 1.0


def test_las_estaciones_C_estan_en_los_extremos_de_la_zona():
    o = objetivo()
    cs = [p for p in campo.estaciones([o]) if p["tipo"] == "C"]
    assert cs[0]["geometry"].distance(o["_a"]) < 1.0
    assert cs[1]["geometry"].distance(o["_b"]) < 1.0


def test_el_codigo_sale_del_nombre_del_tramo():
    pts = campo.estaciones([objetivo("La Jalca - Mendoza")])
    assert pts[0]["codigo"] == "LAJA-01"
    assert pts[-1]["codigo"].endswith("-08")


def test_dos_tramos_que_empiezan_igual_no_comparten_codigo():
    """El bug que solo se nota en campo: 'Chachapoyas - Jumbilla' y
    'Chachapoyas - Cochamal' daban los dos CHA-01, y con el GPS cargado no
    hay forma de saber cual es cual."""
    a = objetivo("Chachapoyas - Jumbilla")
    b = objetivo("Chachapoyas - Cochamal")
    codigos = {p["codigo"] for p in campo.estaciones([a, b])}
    assert len(codigos) == 16


def test_dos_zonas_del_MISMO_tramo_tampoco():
    a, b = objetivo("Pauja - Santa Cruz"), objetivo("Pauja - Santa Cruz")
    b["zona"] = 2
    pts = campo.estaciones([a, b])
    assert len({p["codigo"] for p in pts}) == 16


def test_sin_alternativa_no_hay_estaciones_B():
    """Si la ruta del modelo no deja trozo en la zona, no se inventa."""
    o = objetivo()
    o["_alterna"] = LineString([(0, 1500), (0, 1500)])
    pts = campo.estaciones([o])
    assert [p["tipo"] for p in pts].count("B") == 0
    assert len(pts) == 5


# ------------------------------------------------------------------- el GPX

def test_el_gpx_lleva_la_instruccion_en_cada_punto(tmp_path):
    """Un waypoint sin nota es un punto al que se llega sin saber que mirar."""
    import xml.etree.ElementTree as ET

    pts = [{"codigo": "PAU-06", "tipo": "B", "prioridad": 1,
            "tramo": "Pauja - Santa Cruz", "nota": "ruta del modelo",
            "altitud_m": 2280, "lat": -6.049356, "lon": -77.879069}]
    destino = tmp_path / "estaciones.gpx"
    campo.escribe_gpx(pts, destino)

    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    w = ET.parse(destino).findall(".//g:wpt", ns)
    assert len(w) == 1
    assert w[0].get("lat") == "-6.049356"
    assert w[0].find("g:ele", ns).text == "2280"
    desc = w[0].find("g:desc", ns).text
    assert "TIPO B" in desc and "300 m a cada lado" in desc


def test_el_gpx_aguanta_un_punto_sin_altitud(tmp_path):
    campo.escribe_gpx([{"codigo": "X-01", "tipo": "A", "prioridad": 1,
                        "tramo": "T", "nota": "n", "altitud_m": None,
                        "lat": -6.0, "lon": -77.0}], tmp_path / "x.gpx")
    assert (tmp_path / "x.gpx").exists()


def test_el_paso_esta_en_la_cli():
    from camino import cli
    assert "campo" in cli.AYUDAS and "campo" not in cli.ORDEN
