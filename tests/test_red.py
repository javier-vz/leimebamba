"""El Qhapaq Nan como RED, y si el registro da para medirla."""

import numpy as np
import pytest
from shapely.geometry import LineString

from camino import red


def recta(x0, y0, x1, y1, n=20):
    return LineString(np.column_stack([np.linspace(x0, x1, n),
                                       np.linspace(y0, y1, n)]))


def escalera(x0=0, tramos=6, paso=10000, alto=2000):
    """Dos travesanos paralelos con peldanos: ~134 km y con bifurcaciones.

    Hace falta para probar centralidad. Una linea recta, por larga que sea,
    `linemerge` la devuelve como UNA cadena: sin bifurcaciones no hay
    aristas que ordenar ni caminos alternativos, y la betweenness no existe.
    """
    gs = []
    for i in range(tramos):
        gs.append(recta(x0 + i * paso, 0, x0 + (i + 1) * paso, 0))
        gs.append(recta(x0 + i * paso, alto, x0 + (i + 1) * paso, alto))
    for i in range(tramos + 1):
        gs.append(recta(x0 + i * paso, 0, x0 + i * paso, alto))
    return gs


# --------------------------------------------------- nodado

def test_une_lo_que_se_toca_y_separa_lo_que_no():
    """Dos segmentos que comparten extremo son una cadena; con un hueco de
    300 m son dos componentes, hasta que la tolerancia los une."""
    a = recta(0, 0, 1000, 0)
    b = recta(1300, 0, 2300, 0)          # 300 m de hueco

    G, _ = red.construir([a, b], tolerancia=0.0)
    assert red.medidas(G)["componentes"] == 2

    G, _ = red.construir([a, b], tolerancia=100.0)
    assert red.medidas(G)["componentes"] == 2     # 100 < 300: sigue partido

    G, _ = red.construir([a, b], tolerancia=400.0)
    assert red.medidas(G)["componentes"] == 1     # 400 > 300: se cierra


def test_una_bifurcacion_da_un_nodo_de_grado_tres():
    """`unary_union` corta en la interseccion aunque nadie la haya marcado."""
    tronco = recta(0, 0, 2000, 0)
    rama = recta(1000, 0, 1000, 1000)

    G, cs = red.construir([tronco, rama], tolerancia=0.0)
    m = red.medidas(G)
    assert m["componentes"] == 1
    assert m["grado_maximo"] == 3
    assert len(cs) == 3          # el tronco se parte en dos + la rama


def test_una_linea_sola_es_una_arista_con_dos_cabos():
    G, _ = red.construir([recta(0, 0, 1000, 0)], tolerancia=0.0)
    m = red.medidas(G)
    assert (m["nodos"], m["aristas"], m["componentes"]) == (2, 1, 1)
    assert m["fraccion_grado_1"] == 1.0
    assert m["km_totales"] == pytest.approx(1.0, abs=0.01)


def test_sin_polilineas_lo_dice():
    with pytest.raises(ValueError, match="ninguna polilinea"):
        red.cadenas([])


# ------------------------------------------- centralidad y sensibilidad

def test_la_centralidad_es_mayor_en_el_puente():
    """Dos grupos unidos por un solo tramo: ese tramo tiene que ser el mas
    central, porque todos los caminos entre grupos pasan por el."""
    izq = [recta(0, 0, 500, 0), recta(0, 0, 0, 500), recta(0, 500, 500, 500)]
    der = [recta(2000, 0, 2500, 0), recta(2500, 0, 2500, 500),
           recta(2000, 500, 2500, 500)]
    puente = recta(500, 0, 2000, 0)

    geoms = izq + der + [puente]
    G, cs = red.construir(geoms, tolerancia=10.0)
    assert red.medidas(G)["componentes"] == 1

    v = red.por_rasgo(cs, red.centralidad_por_cadena(G, k=None), geoms)
    i_puente = len(geoms) - 1
    assert v[i_puente] == max(v[np.isfinite(v)]), v


def test_la_sensibilidad_devuelve_una_fila_por_tolerancia():
    geoms = [recta(0, 0, 1000, 0), recta(1200, 0, 2200, 0),
             recta(2200, 0, 2200, 1000)]
    filas = red.sensibilidad(geoms, tolerancias=(0.0, 100.0, 500.0), k=None)

    assert [f["tolerancia_m"] for f in filas] == [0.0, 100.0, 500.0]
    assert filas[0]["spearman_con_la_anterior"] is None   # no hay anterior
    # al cerrar el hueco de 200 m, las componentes bajan
    assert filas[2]["componentes"] < filas[0]["componentes"]


# ------------------------------------------------------- el veredicto

def fila(comp=100, km_mayor=50.0, grandes=0, pct_grandes=0.0,
         gr1=0.5, rho=None, tol=0.0, mediana=3.0, cinco=None,
         rho_corr=None, comunes=0):
    """Una fila de `sensibilidad`, para probar lo que se imprime sin correr
    el barrido. `rho` es el global (de contraste) y `rho_corr` el que de
    verdad decide, el de dentro de los corredores."""
    return {"tolerancia_m": tol, "componentes": comp,
            "km_en_la_mayor": km_mayor,
            "componentes_grandes": grandes,
            "fraccion_km_en_las_grandes": pct_grandes,
            "km_mediana_de_componente": mediana,
            "km_de_las_cinco_mayores": cinco or [km_mayor],
            "fraccion_en_la_mayor": 0.1, "fraccion_grado_1": gr1,
            "corredores": grandes,
            "rasgos_con_centralidad": 0 if not grandes else 500,
            "rasgos_comparables": comunes,
            "spearman_con_la_anterior": rho,
            "spearman_en_corredores": rho_corr}


def test_veredicto_sin_red():
    """Si casi todos los km son esquirlas sueltas, no hay nada que medir."""
    filas = [fila(comp=900, km_mayor=20, grandes=0, pct_grandes=0.05),
             fila(comp=800, km_mayor=25, grandes=0, pct_grandes=0.10,
                  rho_corr=0.9, comunes=400, tol=50)]
    assert "No hay red que medir" in red._veredicto(filas)


def test_veredicto_nombra_los_corredores_cuando_el_orden_es_inestable():
    """El caso real del registro: no hay UNA red, pero si corredores de
    cientos de km. El veredicto tiene que decir eso y no 'no hay red'."""
    filas = [fila(comp=917, km_mayor=196, grandes=11, pct_grandes=0.17),
             fila(comp=745, km_mayor=400, grandes=18, pct_grandes=0.52,
                  rho_corr=0.29, comunes=1600, tol=50)]
    v = " ".join(red._veredicto(filas).split())
    assert "NO hay una red" in v and "11 corredores" in v
    assert "196 km" in v and "CAMBIA" in v
    assert "inestabilidad" in v
    # las cifras citadas tienen que ser TODAS de la misma corrida (tol 0),
    # no una mezcla del conteo de una tolerancia con el % de otra
    assert "17% de los kilometros" in v and "52%" in v


def test_veredicto_reportable_dentro_de_cada_corredor():
    filas = [fila(comp=40, km_mayor=800, grandes=20, pct_grandes=0.80),
             fila(comp=30, km_mayor=900, grandes=22, pct_grandes=0.85,
                  rho_corr=0.95, comunes=2600, tol=50),
             fila(comp=25, km_mayor=950, grandes=23, pct_grandes=0.88,
                  rho_corr=0.88, comunes=2650, tol=100)]
    v = " ".join(red._veredicto(filas).split())   # el salto de linea da igual
    assert "20 corredores" in v and "aguanta" in v
    assert "DENTRO de cada corredor" in v


def test_la_masa_de_la_red_se_mide_en_km_y_no_en_nodos():
    """El caso que me hacia fallar el veredicto: un corredor largo rodeado
    de muchas esquirlas. Por NODOS la componente mayor es minoria; por
    KILOMETROS es la columna vertebral, y eso es lo que importa."""
    corredor = [recta(i * 1000, 0, (i + 1) * 1000, 0) for i in range(300)]
    esquirlas = [recta(0, 5000 + i * 500, 200, 5000 + i * 500)
                 for i in range(400)]

    G, _ = red.construir(corredor + esquirlas, tolerancia=0.0)
    m = red.medidas(G)

    assert m["componentes"] == 401
    assert m["fraccion_en_la_mayor"] < 0.5          # por nodos, minoria
    assert m["km_en_la_mayor"] == pytest.approx(300.0, abs=1)
    assert m["fraccion_km_en_la_mayor"] > 0.75      # por km, casi todo
    assert m["componentes_grandes"] == 1
    assert m["km_mediana_de_componente"] == pytest.approx(0.2, abs=0.01)
    assert m["km_de_las_cinco_mayores"][0] == pytest.approx(300.0, abs=1)


def test_el_umbral_de_corredor_es_explicito():
    assert red.KM_GRANDE == 100.0


# ------------------- observado frente a proyectado: las dos corridas

def test_veredicto_dice_de_cual_corrida_habla(capsys):
    red._veredicto([fila(grandes=0, pct_grandes=0.0)], "solo observado")
    assert "(solo observado)" in capsys.readouterr().out


def test_la_tabla_pone_las_dos_corridas_lado_a_lado(capsys):
    obs = [fila(comp=917, km_mayor=196, grandes=11, pct_grandes=0.17),
           fila(comp=745, km_mayor=200, grandes=12, pct_grandes=0.20,
                rho=0.29, tol=50)]
    todo = [fila(comp=572, km_mayor=306, grandes=24, pct_grandes=0.32),
            fila(comp=404, km_mayor=320, grandes=25, pct_grandes=0.35,
                 rho=0.42, tol=50)]

    red._tabla(obs, todo)
    salida = capsys.readouterr().out
    assert "solo observado" in salida and "mas lo proyectado" in salida
    linea = [l for l in salida.splitlines() if l.strip().startswith("0m")][0]
    assert "917" in linea and "572" in linea       # las dos, misma linea
    assert "196" in linea and "306" in linea       # km de cada columna


def test_la_tabla_va_sola_si_el_kmz_no_trae_proyectado(capsys):
    red._tabla([fila(comp=917, km_mayor=196)], None)
    salida = capsys.readouterr().out
    assert "mas lo proyectado" not in salida
    assert "917" in salida


def test_la_columna_vertebral_se_mide_sin_cerrar_huecos(capsys):
    f = fila(km_mayor=196, grandes=11, pct_grandes=0.17, mediana=2.97,
             cinco=[196.0, 183.0, 178.0, 172.0, 147.0])
    red._columna_vertebral([f], "solo observado")
    salida = capsys.readouterr().out
    assert "tol 0 m" in salida
    assert "196, 183, 178, 172, 147 km" in salida
    assert "2.97" in salida or "3.0" in salida
    assert "11" in salida and "17%" in salida


def test_la_columna_vertebral_exige_que_la_primera_fila_sea_tol_cero():
    """Si el barrido cambiara de orden, la cifra 'honesta' dejaria de serlo
    en silencio. Mejor que reviente."""
    with pytest.raises(AssertionError, match="tol 0"):
        red._columna_vertebral([fila(tol=50.0)], "x")


RESUMEN = {"km_proyectado": 1697.0, "fraccion_km_inferida": 0.15,
           "rasgos_proyectado": 717}


def test_la_lectura_cuando_lo_proyectado_agranda_la_columna():
    """El caso real: 196 -> 306 km de columna vertebral, pagando 15% de km
    inferidos. La proporcion tiene que quedar dicha."""
    v = _compara_mudo(
        [fila(km_mayor=196, grandes=11, pct_grandes=0.17)],
        [fila(km_mayor=306, grandes=24, pct_grandes=0.32)])
    assert "SI aporta topologia" in v
    assert "196" in v and "306" in v and "1.6x" in v
    assert "15% de km inferidos" in v
    assert "la infiere el registro" in v


def test_la_lectura_cuando_lo_proyectado_no_compra_nada():
    v = _compara_mudo(
        [fila(km_mayor=196, grandes=11, pct_grandes=0.17)],
        [fila(km_mayor=205, grandes=12, pct_grandes=0.19)])
    assert "casi no agranda" in v
    assert "es del registro" in v


def _compara_mudo(obs, todo):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return red._compara(obs, todo, RESUMEN)


def test_separa_observado_de_proyectado(monkeypatch, capsys):
    """`_lee_las_dos` tiene que leer las DOS categorias y partirlas, porque
    el filtro a 'observado' del pipeline es justo lo que se quiere probar."""
    import pathlib
    import types

    import geopandas as gpd

    from camino import registro, ruta as _ruta

    gdf = gpd.GeoDataFrame(
        {"categoria": ["observado", "observado", "proyectado"]},
        geometry=[recta(0, 0, 1000, 0), recta(1000, 0, 2000, 0),
                  recta(2000, 0, 5000, 0)], crs="EPSG:32718")

    monkeypatch.setattr(_ruta, "busca_archivo",
                        lambda cfg: pathlib.Path("q.kmz"))
    monkeypatch.setattr(registro, "lee", lambda *a, **k: gdf)
    cfg = types.SimpleNamespace(crs="EPSG:32718", capas_camino=None,
                                tramos_excluidos=())

    obs, todo, resumen, _ = red._lee_las_dos(cfg)

    assert len(obs) == 2 and len(todo) == 3
    assert resumen["rasgos_observado"] == 2
    assert resumen["rasgos_proyectado"] == 1
    assert resumen["km_observado"] == pytest.approx(2.0, abs=0.01)
    assert resumen["km_proyectado"] == pytest.approx(3.0, abs=0.01)
    # 3 de 5 km del registro serian inferencia
    assert resumen["fraccion_km_inferida"] == pytest.approx(0.6, abs=0.01)
    assert "inferidos por el registro" in capsys.readouterr().out


def test_se_niega_si_el_archivo_no_trae_categorias(monkeypatch):
    """Un GPKG o un GPX no distinguen observado de proyectado: sin eso la
    comparacion no existe, y es mejor decirlo que correr media prueba."""
    import pathlib
    import types

    from camino import ruta as _ruta

    monkeypatch.setattr(_ruta, "busca_archivo",
                        lambda cfg: pathlib.Path("qn_geocam.gpkg"))
    cfg = types.SimpleNamespace(crs="EPSG:32718", capas_camino=None,
                                tramos_excluidos=())

    with pytest.raises(SystemExit, match="CATEGORIAS"):
        red._lee_las_dos(cfg)


def test_el_paso_esta_en_la_cli():
    from camino import cli
    assert "red" in cli.AYUDAS and "red" not in cli.ORDEN


# ------------------- centralidad restringida a los corredores

def test_los_corredores_son_las_componentes_grandes():
    grande = escalera()                       # ~134 km
    esquirla = [recta(0, 90000, 1000, 90000)]  # 1 km, aparte

    G, _ = red.construir(grande + esquirla, tolerancia=0.0)
    cs = red.corredores(G)

    assert len(cs) == 1                       # solo la escalera califica
    km = sum(d["largo"] for *_, d in cs[0].edges(data=True)) / 1000
    assert km == pytest.approx(134.0, abs=1)
    assert len(red.corredores(G, km_min=0.5)) == 2


def test_la_centralidad_restringida_deja_fuera_las_esquirlas():
    """Lo que arregla el rho: los rasgos sin corredor no valen CERO, valen
    nada. Un cero seria afirmar que no son de paso, y eso no se sabe."""
    grande = escalera()
    geoms = grande + [recta(0, 90000, 1000, 90000)]
    n = len(grande)

    G, cs = red.construir(geoms, tolerancia=0.0)
    v = red.por_rasgo(cs, red.centralidad_en_corredores(G, k=None), geoms)

    assert np.isfinite(v[:n]).all()           # los del corredor, con valor
    assert not np.isfinite(v[n])              # la esquirla, sin valor
    # La global, en cambio, le da un numero: la esquirla esta en el camino
    # mas corto entre sus propios dos extremos, asi que recibe una cifra
    # diminuta pero FINITA, entra a la correlacion y la contamina. Eso es
    # exactamente lo que rompia el rho de la primera tabla.
    g = red.por_rasgo(cs, red.centralidad_por_cadena(G, k=None), geoms)
    assert np.isfinite(g[n])
    assert g[n] < v[np.isfinite(v)].mean()


def test_la_sensibilidad_en_corredores_reporta_su_propio_n():
    grande = escalera()
    geoms = grande + [recta(0, 90000, 1000, 90000)]
    n = len(grande)

    filas = red.sensibilidad(geoms, tolerancias=(0.0, 100.0), k=None)

    assert filas[0]["corredores"] == 1
    assert filas[0]["rasgos_con_centralidad"] == n
    assert filas[0]["rasgos_comparables"] == 0          # no hay anterior
    assert filas[1]["rasgos_comparables"] == n
    assert filas[0]["spearman_en_corredores"] is None


def test_todo_sale_en_el_orden_del_gdf(monkeypatch):
    """Si `todo` saliera como obs + proy, cada tramo se nombraria con el
    nombre de otro y nada avisaria. El orden tiene que ser el del gdf."""
    import pathlib
    import types

    import geopandas as gpd

    from camino import registro, ruta as _ruta

    # proyectado PRIMERO, para que concatenar por categoria desordene
    gdf = gpd.GeoDataFrame(
        {"categoria": ["proyectado", "observado"],
         "tramnomb": ["el proyectado", "el observado"]},
        geometry=[recta(0, 0, 3000, 0), recta(3000, 0, 4000, 0)],
        crs="EPSG:32718")

    monkeypatch.setattr(_ruta, "busca_archivo",
                        lambda cfg: pathlib.Path("q.kmz"))
    monkeypatch.setattr(registro, "lee", lambda *a, **k: gdf)
    cfg = types.SimpleNamespace(crs="EPSG:32718", capas_camino=None,
                                tramos_excluidos=())

    obs, todo, _, salida = red._lee_las_dos(cfg)

    assert len(todo) == 2
    assert todo[0].length == pytest.approx(3000.0)   # el proyectado, primero
    assert list(salida["tramnomb"]) == ["el proyectado", "el observado"]
    assert obs[0].length == pytest.approx(1000.0)


def test_los_mas_centrales_nombran_el_tramo(capsys):
    """El corredor mayor con un cuello de botella claro: el puente tiene que
    salir primero, y con su nombre del registro."""
    import geopandas as gpd

    izq, der = escalera(0), escalera(70000)
    puente = recta(60000, 0, 70000, 0)
    geoms = izq + der + [puente]

    gdf = gpd.GeoDataFrame(
        {"tramnomb": (["izq"] * len(izq) + ["der"] * len(der)
                      + ["EL PUENTE"])},
        geometry=geoms, crs="EPSG:32718")

    red._mas_centrales(geoms, gdf, tol=0.0, cuantos=3, k=None)
    salida = capsys.readouterr().out
    assert "CORREDOR MAYOR" in salida
    primera = [l for l in salida.splitlines() if "izq" in l or "der" in l
               or "PUENTE" in l][0]
    assert "EL PUENTE" in primera


def test_sin_corredores_lo_dice_y_no_revienta(capsys):
    import geopandas as gpd

    geoms = [recta(0, 0, 1000, 0), recta(0, 5000, 1000, 5000)]
    gdf = gpd.GeoDataFrame({"tramnomb": ["a", "b"]}, geometry=geoms,
                           crs="EPSG:32718")

    red._mas_centrales(geoms, gdf, k=None)
    assert "no hay ningun corredor" in capsys.readouterr().out


def test_el_veredicto_usa_el_rho_de_los_corredores_no_el_global():
    """El caso real del registro: el rho global dice 'inestable' porque esta
    dominado por miles de rasgos aislados, mientras que dentro de los
    corredores el orden aguanta. El veredicto tiene que creerle al segundo."""
    filas = [fila(comp=572, km_mayor=306, grandes=24, pct_grandes=0.32),
             fila(comp=404, km_mayor=445, grandes=26, pct_grandes=0.42,
                  rho=0.42, rho_corr=0.83, comunes=1651, tol=50),
             fila(comp=374, km_mayor=445, grandes=26, pct_grandes=0.43,
                  rho=0.73, rho_corr=0.95, comunes=2653, tol=100)]
    v = " ".join(red._veredicto(filas).split())
    assert "24 corredores" in v and "aguanta" in v


def test_el_veredicto_desconfia_de_un_rho_alto_con_n_chico():
    """Un 0.99 sobre doce rasgos no es estabilidad, es casualidad."""
    filas = [fila(comp=572, km_mayor=306, grandes=24, pct_grandes=0.32),
             fila(comp=404, km_mayor=445, grandes=24, pct_grandes=0.42,
                  rho_corr=0.99, comunes=12, tol=50)]
    v = " ".join(red._veredicto(filas).split())
    assert "CAMBIA" in v or "inestabilidad" in v


def test_los_mas_centrales_agrupan_por_tramo_y_no_por_rasgo(capsys):
    """El registro parte un tramo en decenas de rasgos. Si no se agrupa, el
    top son diez pedazos del mismo tramo con la misma cifra."""
    import geopandas as gpd

    izq, der = escalera(0), escalera(70000)
    puente = recta(60000, 0, 70000, 0)
    geoms = izq + der + [puente]
    gdf = gpd.GeoDataFrame(
        {"tramnomb": ["izq"] * len(izq) + ["der"] * len(der) + ["EL PUENTE"]},
        geometry=geoms, crs="EPSG:32718")

    red._mas_centrales(geoms, gdf, cuantos=10, k=None)
    salida = capsys.readouterr().out

    filas = [l for l in salida.splitlines()
             if l.strip().startswith(("0.", "1.")) and "  " in l]
    nombres = [l.split()[-1] for l in filas]
    assert nombres.count("PUENTE") == 1      # una fila por tramo, no por rasgo
    assert len(set(nombres)) == len(nombres)
    assert "rasgos" in salida                 # cuantos rasgos trae cada tramo


def test_los_mas_centrales_se_niegan_si_el_gdf_no_alinea():
    """Nombrar por posicion contra un gdf de otro largo desplazaria cada
    nombre en silencio. Mejor que reviente."""
    import geopandas as gpd

    geoms = escalera()
    gdf = gpd.GeoDataFrame({"tramnomb": ["a", "b"]},
                           geometry=geoms[:2], crs="EPSG:32718")

    with pytest.raises(ValueError, match="desplazados"):
        red._mas_centrales(geoms, gdf, k=None)


# ------------------------------------- redundancia: el indice alfa

def test_alfa_es_cero_en_un_arbol_y_sube_con_los_ciclos():
    """La medida que dice si la betweenness significa algo: sin ciclos no
    hay rutas alternativas, asi que no hay nada que elegir."""
    # una Y: tres ramas desde un nodo, ningun ciclo
    arbol = [recta(0, 0, 1000, 0), recta(1000, 0, 2000, 500),
             recta(1000, 0, 2000, -500)]
    G, _ = red.construir(arbol, tolerancia=0.0)
    assert red.alfa(G) == 0.0
    assert red.medidas(G)["ciclos"] == 0

    # la escalera tiene un ciclo por cada cuadro
    G, _ = red.construir(escalera(tramos=3), tolerancia=0.0)
    assert red.medidas(G)["ciclos"] == 3
    assert red.alfa(G) > 0.0


def test_alfa_no_depende_de_la_tolerancia_sino_de_la_topologia():
    """Es lo que la vuelve reportable: sale del conteo de nodos y aristas."""
    gs = escalera(tramos=4)
    a = red.alfa(red.construir(gs, 0.0)[0])
    b = red.alfa(red.construir(gs, 100.0)[0])
    assert a == b == pytest.approx(red.alfa(red.construir(gs, 500.0)[0]))


def test_la_tabla_por_corredor_cuenta_los_arboles(capsys):
    """Un corredor con ciclos y otro que es una sola cadena: la tabla tiene
    que decir que la mitad de los km no tiene alternativas."""
    con_ciclos = escalera()                          # ~134 km, con ciclos
    cadena = [recta(0, 200000 + i * 1000, 0, 201000 + i * 1000)
              for i in range(130)]                   # 130 km, un arbol

    salida = red._tabla_de_cada_corredor(con_ciclos + cadena)
    texto = capsys.readouterr().out

    assert salida["corredores"] == 2
    assert salida["arboles"] == 1
    assert salida["km_en_arboles"] == pytest.approx(130.0, abs=1)
    assert 0.4 < salida["fraccion_km_sin_alternativas"] < 0.6
    assert "ARBOLES" in texto and "alfa" in texto


def test_el_veredicto_avisa_cuando_los_corredores_son_arboles():
    """Sin este aviso, "la centralidad es reportable" se leeria como que
    mide eleccion de ruta, y en un arbol no mide eso."""
    filas = [fila(comp=572, km_mayor=306, grandes=24, pct_grandes=0.32),
             fila(comp=404, km_mayor=445, grandes=24, pct_grandes=0.42,
                  rho_corr=0.9, comunes=1600, tol=50)]
    estructura = {"corredores": 24, "arboles": 14, "km_en_corredor": 3618.0,
                  "km_en_arboles": 1826.0,
                  "fraccion_km_sin_alternativas": 0.52}

    v = " ".join(red._veredicto(filas, estructura=estructura).split())
    assert "14 de los 24 corredores no tienen ningun ciclo" in v
    assert "52% de los km" in v
    assert "indice alfa" in v


def test_el_veredicto_no_avisa_si_casi_todo_tiene_ciclos():
    filas = [fila(comp=20, km_mayor=800, grandes=10, pct_grandes=0.80),
             fila(comp=18, km_mayor=820, grandes=10, pct_grandes=0.82,
                  rho_corr=0.9, comunes=1600, tol=50)]
    estructura = {"corredores": 10, "arboles": 1, "km_en_corredor": 2000.0,
                  "km_en_arboles": 120.0,
                  "fraccion_km_sin_alternativas": 0.06}
    assert "ningun ciclo" not in red._veredicto(filas, estructura=estructura)
