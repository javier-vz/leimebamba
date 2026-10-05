"""El nulo de Monte Carlo y el perfil de equifinalidad."""

import numpy as np
import pytest

from camino import equifinalidad, nulos


# ---------------------------------------------------------------- el nulo

def test_el_valor_p_tiene_piso_uno_sobre_m_mas_uno():
    d_nulos = np.full(500, 1000.0)
    assert nulos.p_empirico(10.0, d_nulos) == pytest.approx(1 / 501)
    assert nulos.piso_p(500) == pytest.approx(1 / 501)


def test_el_valor_p_es_uno_cuando_el_nulo_gana_siempre():
    assert nulos.p_empirico(1000.0, np.full(99, 10.0)) == pytest.approx(1.0)


def test_el_valor_p_cuenta_los_empates_del_lado_conservador():
    d = np.array([5.0, 10.0, 20.0, 30.0])
    assert nulos.p_empirico(10.0, d) == pytest.approx(3 / 5)


def test_el_valor_p_queda_en_cero_uno():
    rng = np.random.default_rng(0)
    d = rng.normal(100, 20, 300)
    for obs in (-50.0, 100.0, 500.0):
        p = nulos.p_empirico(obs, d)
        assert 0 < p <= 1


def test_el_campo_gaussiano_sale_normalizado():
    rng = np.random.default_rng(1)
    c = nulos.campo_gaussiano((64, 96), beta=2.5, rng=rng)
    assert c.shape == (64, 96)
    assert np.isfinite(c).all()
    assert c.mean() == pytest.approx(0.0, abs=1e-9)
    assert c.std() == pytest.approx(1.0, abs=1e-9)


def test_el_campo_es_mas_suave_cuanto_mayor_el_beta():
    """El nulo no es ruido blanco: conserva la autocorrelacion espacial. Si
    fuera blanco, el test saldria significativo siempre."""
    rng = np.random.default_rng(2)
    aspero = nulos.campo_gaussiano((128, 128), beta=0.5, rng=rng)
    suave = nulos.campo_gaussiano((128, 128), beta=4.0, rng=rng)
    rugosidad = lambda c: np.abs(np.diff(c, axis=0)).mean()
    assert rugosidad(suave) < rugosidad(aspero) / 3


def test_beta_espectral_recupera_el_exponente_sintetizado():
    rng = np.random.default_rng(3)
    for beta in (2.0, 3.0, 4.0):
        c = nulos.campo_gaussiano((256, 256), beta=beta, rng=rng)
        assert nulos.beta_espectral(c) == pytest.approx(beta, abs=0.6)


def test_la_superficie_nula_queda_en_el_rango_de_una_componente():
    rng = np.random.default_rng(4)
    s = nulos.superficie_nula((80, 80), beta=3.0, rng=rng, epsilon=0.01)
    assert s.min() == pytest.approx(0.01)
    assert s.max() == pytest.approx(1.01)


# -------------------------------------------------------- equifinalidad

def test_con_tau_cero_el_conjunto_es_solo_el_optimo():
    D = np.array([5.0, 3.0, 9.0, 3.0])
    m = equifinalidad.conjunto_casi_optimo(D, 0.0)
    assert m.tolist() == [False, True, False, True]


def test_el_conjunto_crece_con_tau():
    D = np.array([3.0, 3.3, 3.9, 10.0])
    # umbrales (1+tau)*3 = 3.0, 3.3, 3.9, 10.5
    tamanos = [int(equifinalidad.conjunto_casi_optimo(D, t).sum())
               for t in (0.0, 0.1, 0.3, 2.5)]
    assert tamanos == [1, 2, 3, 4]


def test_el_conjunto_ignora_los_pesos_sin_camino():
    D = np.array([np.inf, 4.0, np.inf])
    assert equifinalidad.conjunto_casi_optimo(D, 0.5).tolist() == [False, True, False]


def test_jaccard_identidad_y_disjuntos():
    a = np.array([True, True, False, False])
    b = np.array([False, False, True, True])
    assert equifinalidad.jaccard(a, a) == pytest.approx(1.0)
    assert equifinalidad.jaccard(a, b) == pytest.approx(0.0)
    assert equifinalidad.jaccard(a, np.array([True, False, False, False])) \
        == pytest.approx(0.5)


def test_jaccard_de_conjuntos_vacios_es_indefinido():
    vacio = np.zeros(4, dtype=bool)
    assert np.isnan(equifinalidad.jaccard(vacio, vacio))


def test_dos_sectores_identicos_dan_perfil_uno():
    D = np.array([3.0, 3.2, 5.0, 8.0])
    taus, perf = equifinalidad.perfil_jaccard({"s1": D, "s2": D.copy()})
    assert set(perf) == {("s1", "s2")}
    assert np.allclose(perf[("s1", "s2")], 1.0)


def test_dos_sectores_con_optimos_opuestos_se_separan():
    """Es el resultado que busca el proyecto: conjuntos que se separan
    significan que el sector esta gobernado por otras variables."""
    D1 = np.array([1.0, 2.0, 9.0, 9.0])
    D2 = np.array([9.0, 9.0, 2.0, 1.0])
    taus, perf = equifinalidad.perfil_jaccard({"a": D1, "b": D2},
                                              taus=[0.0, 0.1, 0.5])
    j = perf[("a", "b")]
    assert j[0] == pytest.approx(0.0)
    assert np.all((j >= 0) & (j <= 1))


def test_el_perfil_devuelve_un_par_por_combinacion():
    D = {n: np.array([1.0, 2.0, 3.0]) for n in ("s1", "s2", "s3", "s4")}
    taus, perf = equifinalidad.perfil_jaccard(D, taus=[0.0, 0.2])
    assert len(perf) == 6
    assert all(v.shape == (2,) for v in perf.values())


def test_centroide_y_extension_del_conjunto():
    red = np.array([[1.0, 0.0], [0.5, 0.5], [0.0, 1.0]])
    m = np.array([True, True, False])
    assert equifinalidad.centroide(red, m) == pytest.approx([0.75, 0.25])
    ext = equifinalidad.extension(red, m)
    assert ext[0] == pytest.approx([0.5, 1.0])
    assert ext[1] == pytest.approx([0.0, 0.5])


def test_centroide_de_un_conjunto_vacio_es_nan():
    red = np.array([[1.0, 0.0], [0.0, 1.0]])
    assert np.isnan(equifinalidad.centroide(red, np.zeros(2, dtype=bool))).all()
