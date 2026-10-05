"""Pruebas de la cuenca visual.

Lo que se comprueba no es "que corra": es que tape lo que tiene que tapar.
Un calculo de visibilidad mal hecho no falla, devuelve un mapa plausible.
"""

import numpy as np
import pytest

from camino import grafo, visibilidad

RES = 30.0
T6 = (RES, 0.0, 500000.0, 0.0, -RES, 9300000.0)


def llano(forma=(60, 60), z=0.0):
    return np.full(forma, float(z))


def xy_de(fil, col, t6=T6):
    return grafo.xy(np.array([[fil, col]]), t6)[0]


def test_indices_invierten_a_grafo_xy():
    """El ida y vuelta tiene que cerrar: centro de pixel -> centro de pixel."""
    filcol = np.array([[0, 0], [7, 13], [59, 41]])
    xy = grafo.xy(filcol, T6)
    fil, col = visibilidad.indices_fraccionarios(T6, xy[:, 0], xy[:, 1])
    assert np.allclose(fil, filcol[:, 0])
    assert np.allclose(col, filcol[:, 1])


def test_bilineal_recupera_el_valor_de_la_celda():
    dem = np.arange(36, dtype=float).reshape(6, 6)
    fil, col = np.array([2.0, 5.0]), np.array([3.0, 0.0])
    assert np.allclose(visibilidad.bilineal(dem, fil, col), [15.0, 30.0])
    # a medio camino, la media
    assert visibilidad.bilineal(dem, np.array([2.5]), np.array([3.0]))[0] == 18.0


def test_bilineal_fuera_del_raster_es_nan():
    dem = llano((5, 5))
    z = visibilidad.bilineal(dem, np.array([-2.0, 2.0, 99.0]),
                             np.array([2.0, 2.0, 2.0]))
    assert np.isnan(z[0]) and np.isfinite(z[1]) and np.isnan(z[2])


def test_sobre_llano_y_a_corta_distancia_se_ve_todo():
    dem = llano()
    nodos = grafo.xy(np.argwhere(np.ones((60, 60), bool)), T6)
    frac, info = visibilidad.fraccion_visible(
        dem, T6, [xy_de(30, 30)], nodos, radio=600.0)
    cerca = np.hypot(nodos[:, 0] - xy_de(30, 30)[0],
                     nodos[:, 1] - xy_de(30, 30)[1]) <= 600.0
    assert frac[cerca].min() == 1.0
    assert frac[~cerca].max() == 0.0
    assert info["sitios_usados"] == 1


def test_un_muro_tapa_lo_que_hay_detras():
    """La prueba que de verdad importa: una pared entre sitio y nodo."""
    dem = llano()
    dem[:, 35] = 200.0                       # muro norte-sur
    sitio = xy_de(30, 30)
    detras = grafo.xy(np.array([[30, 45]]), T6)
    delante = grafo.xy(np.array([[30, 20]]), T6)

    f_detras, _ = visibilidad.fraccion_visible(dem, T6, [sitio], detras, 1000.0)
    f_delante, _ = visibilidad.fraccion_visible(dem, T6, [sitio], delante, 1000.0)
    assert f_detras[0] == 0.0
    assert f_delante[0] == 1.0


@pytest.mark.parametrize("z_alto, visible", [(500.0, False), (700.0, True)])
def test_subir_al_nodo_por_encima_del_muro_lo_hace_visible(z_alto, visible):
    """Cuanto hay que subir depende de DONDE esta el muro, no solo de su
    altura: el muro de 200 m esta a un tercio del camino, asi que la linea
    pasa por encima solo si el nodo supera los 600 m. 500 no basta."""
    dem = llano()
    dem[:, 35] = 200.0
    dem[30, 45] = z_alto
    f, _ = visibilidad.fraccion_visible(
        dem, T6, [xy_de(30, 30)], grafo.xy(np.array([[30, 45]]), T6), 1000.0)
    assert bool(f[0]) is visible


def test_la_visibilidad_es_simetrica_con_alturas_iguales():
    """Ver y ser visto son lo mismo si las dos alturas coinciden.

    Si esto falla, el calculo esta metiendo una direccion donde no la hay.
    """
    rng = np.random.default_rng(7)
    dem = rng.normal(0, 60, (60, 60)).cumsum(axis=0).cumsum(axis=1) / 50
    a, b = xy_de(10, 12), xy_de(44, 51)
    ida, _ = visibilidad.fraccion_visible(dem, T6, [a], np.array([b]), 3000.0,
                                          h_observador=0.0, h_objetivo=0.0)
    vuelta, _ = visibilidad.fraccion_visible(dem, T6, [b], np.array([a]), 3000.0,
                                             h_observador=0.0, h_objetivo=0.0)
    assert ida[0] == vuelta[0]


def test_la_fraccion_cuenta_cuantos_sitios_se_ven():
    dem = llano()
    dem[:, 35] = 200.0
    nodo = grafo.xy(np.array([[30, 45]]), T6)      # detras del muro
    # uno delante del muro (tapado) y otro al mismo lado que el nodo (visible)
    frac, info = visibilidad.fraccion_visible(
        dem, T6, [xy_de(30, 30), xy_de(30, 50)], nodo, 1000.0)
    assert frac[0] == pytest.approx(0.5)
    assert info["sitios_usados"] == 2


def test_el_radio_corta():
    dem = llano()
    lejos = grafo.xy(np.array([[30, 59]]), T6)     # a 870 m
    assert visibilidad.fraccion_visible(
        dem, T6, [xy_de(30, 30)], lejos, 500.0)[0][0] == 0.0
    assert visibilidad.fraccion_visible(
        dem, T6, [xy_de(30, 30)], lejos, 1000.0)[0][0] == 1.0


def test_la_curvatura_pone_el_horizonte_donde_debe():
    """Sobre llano, un observador de 1.65 m ve hasta unos 4.9 km.

    Es el horizonte clasico con refraccion, 3.86*sqrt(h) km. Si el signo de
    la correccion estuviera invertido, el llano se veria entero y esta
    prueba lo caza.
    """
    n = 260
    dem = llano((3, n))
    t6 = (RES, 0.0, 0.0, 0.0, -RES, 0.0)
    sitio = grafo.xy(np.array([[1, 0]]), t6)[0]
    nodos = grafo.xy(np.column_stack([np.ones(n, int), np.arange(n)]), t6)
    frac, _ = visibilidad.fraccion_visible(dem, t6, [sitio], nodos, 9000.0,
                                           h_observador=1.65, h_objetivo=0.0)
    d = nodos[:, 0] - sitio[0]
    ultimo = d[frac > 0].max()
    assert 4500 < ultimo < 5400, ultimo


def test_sitio_fuera_del_dem_se_reporta_y_no_cuenta():
    dem = llano()
    fuera = np.array([T6[2] - 10000.0, T6[5] - 10000.0])
    frac, info = visibilidad.fraccion_visible(
        dem, T6, np.vstack([xy_de(30, 30), fuera]),
        grafo.xy(np.array([[30, 32]]), T6), 1000.0)
    assert info["sitios_fuera_del_dem"] == 1
    assert info["sitios_usados"] == 1
    assert frac[0] == 1.0


def test_sin_ningun_sitio_dentro_del_dem_falla_claro():
    dem = llano()
    fuera = np.array([[T6[2] - 10000.0, T6[5] - 10000.0]])
    with pytest.raises(ValueError, match="ninguno de los sitios"):
        visibilidad.fraccion_visible(dem, T6, fuera,
                                     grafo.xy(np.array([[1, 1]]), T6), 1000.0)


def test_el_costo_invierte_la_fraccion():
    """Ver tiene que salir BARATO, para ir en el mismo sentido que la
    proximidad ceremonial (mas separacion = mas penalizacion)."""
    assert visibilidad.costo([0.0, 0.5, 1.0]).tolist() == [1.0, 0.5, 0.0]


def test_los_huecos_del_dem_no_obstruyen():
    """Un NaN en el DEM no puede inventar un muro."""
    dem = llano()
    dem[30, 35] = np.nan
    f, _ = visibilidad.fraccion_visible(
        dem, T6, [xy_de(30, 30)], grafo.xy(np.array([[30, 45]]), T6), 1000.0)
    assert f[0] == 1.0
