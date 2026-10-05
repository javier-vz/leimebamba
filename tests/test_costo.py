"""La polinomial de Minetti contra los valores publicados, y la normalizacion."""

import numpy as np
import pytest

from camino import costo


def test_costo_en_plano_es_2_5():
    assert costo.minetti(0.0) == pytest.approx(2.5)
    assert costo.C_PLANO == pytest.approx(2.5)


def test_valores_de_referencia_de_minetti():
    # Minetti et al. 2002, fig. 1: caminar, J kg^-1 m^-1.
    assert costo.minetti(+0.45) == pytest.approx(17.6, abs=0.1)
    assert costo.minetti(-0.45) == pytest.approx(3.6, abs=0.1)
    assert costo.minetti(-0.10) == pytest.approx(1.13, abs=0.02)


def test_el_minimo_esta_bajando_suave_no_en_plano():
    """Bajar suave sale mas barato que caminar en plano. Si esto falla, los
    signos de los coeficientes estan mal."""
    g = np.linspace(-0.45, 0.45, 901)
    c = costo.minetti(g)
    g_min = g[int(np.argmin(c))]
    assert -0.16 < g_min < -0.05
    assert c.min() < costo.minetti(0.0)


def test_sube_monotono_cuesta_arriba():
    g = np.linspace(0.0, 0.45, 100)
    c = costo.minetti(g)
    assert np.all(np.diff(c) > 0)


def test_rango_de_validez_es_el_del_ajuste():
    assert costo.G_MAX == pytest.approx(0.45)
    assert costo.valido(0.45)
    assert not costo.valido(0.46)
    assert not costo.valido(-0.46)


def test_phi_pendiente_normalizada_y_recortada():
    phi = costo.phi_pendiente(np.array([0.0, 0.2, 0.6, -0.9]))
    assert phi[0] == pytest.approx(1.0)
    assert phi[1] > 1.0
    assert np.isnan(phi[2]) and np.isnan(phi[3])


def test_la_pendiente_es_anisotropica():
    assert costo.phi_pendiente(0.2) != pytest.approx(costo.phi_pendiente(-0.2))


def test_tobler_tiene_su_maximo_bajando_suave():
    g = np.linspace(-0.5, 0.5, 1001)
    assert g[int(np.argmax(costo.tobler(g)))] == pytest.approx(-0.05, abs=0.002)


def test_normaliza_usa_percentiles_no_min_max():
    x = np.arange(100.0)
    x[0] = -1e6          # un pixel de ruido que no debe fijar la escala
    y = costo.normaliza(x, percentiles=(5, 95), epsilon=0.01)
    assert y[50] == pytest.approx(0.01 + (50 - 4.95) / (94.05 - 4.95), abs=0.02)
    assert np.nanmin(y) == pytest.approx(0.01)
    assert np.nanmax(y) == pytest.approx(1.01)


def test_normaliza_nunca_devuelve_cero():
    """Con aristas de costo cero, Dijkstra da caminos degenerados."""
    y = costo.normaliza(np.random.default_rng(0).normal(size=1000))
    assert np.nanmin(y) > 0


def test_normaliza_superficie_constante():
    y = costo.normaliza(np.full(50, 7.0))
    assert np.allclose(y, 0.01)


def test_normaliza_respeta_la_mascara():
    x = np.arange(10.0)
    m = np.ones(10, dtype=bool)
    m[3] = False
    y = costo.normaliza(x, m)
    assert np.isnan(y[3])
    assert np.isfinite(y[[0, 1, 2, 4, 5]]).all()
