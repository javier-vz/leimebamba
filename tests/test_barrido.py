"""La red del simplex y el barrido completo de punta a punta."""

import numpy as np
import pytest

from camino import barrido, costo, grafo

DX = 30.0
T6 = (DX, 0.0, 0.0, 0.0, -DX, 0.0)


def test_cuenta_de_la_red_es_la_combinatoria():
    assert barrido.cuenta_red(3, 20) == 231
    assert barrido.cuenta_red(4, 20) == 1771
    assert barrido.cuenta_red(2, 10) == 11
    assert barrido.cuenta_red(1, 20) == 1


def test_la_red_tiene_el_tamano_y_las_propiedades_del_simplex():
    for k, n in ((2, 10), (3, 20), (4, 8)):
        red = barrido.red_simplex(k, n)
        assert red.shape == (barrido.cuenta_red(k, n), k)
        assert np.allclose(red.sum(axis=1), 1.0)
        assert red.min() >= 0.0
        assert len({tuple(w) for w in red}) == len(red)


def test_la_red_incluye_los_vertices():
    red = barrido.red_simplex(3, 20)
    for k in range(3):
        v = np.zeros(3)
        v[k] = 1.0
        assert any(np.allclose(w, v) for w in red)


def test_el_paso_de_la_red_es_uno_sobre_n():
    red = barrido.red_simplex(3, 20)
    assert np.allclose(np.unique(red), np.arange(21) / 20)


def test_red_rechaza_argumentos_invalidos():
    with pytest.raises(ValueError):
        barrido.red_simplex(0, 10)
    with pytest.raises(ValueError):
        barrido.red_simplex(3, 0)


def _montaje(semilla=17, lado=18):
    rng = np.random.default_rng(semilla)
    z = rng.normal(0.0, 2.5, (lado, lado)).cumsum(axis=0) * 0.3
    rug = costo.normaliza(rng.uniform(size=(lado, lado)))
    mask = np.ones((lado, lado), dtype=bool)
    g = grafo.construir(z, mask, {"rugosidad": rug}, DX)
    return g, g.nodo(0, 0), g.nodo(lado - 1, lado - 1)


def test_el_barrido_recupera_los_pesos_que_generaron_el_camino():
    """Se genera un camino con w0 conocido, se usa como 'observado' y se
    barre: el optimo tiene que dar distancia cero."""
    from scipy.sparse.csgraph import dijkstra

    g, o, d = _montaje()
    w0 = np.array([0.75, 0.25])
    _, pred = dijkstra(g.costos(w0), directed=True, indices=o,
                       return_predecessors=True)
    observado = grafo.xy(g.filcol[grafo.recorre(pred, o, d)], T6)

    red = barrido.red_simplex(2, 20)
    D, largos, caminos = barrido.barre(g, red, o, d, observado, T6,
                                       n_trabajos=1)

    i, w = barrido.optimo(D, red)
    assert D[i] == pytest.approx(0.0, abs=1e-9)
    assert np.allclose(w, w0, atol=0.05)


def test_el_barrido_produce_caminos_distintos_segun_los_pesos():
    """Si todos los pesos dieran el mismo camino, el estudio no tendria
    nada que medir."""
    g, o, d = _montaje()
    red = barrido.red_simplex(2, 10)
    obs = grafo.xy(g.filcol[[o, d]], T6)
    _, _, caminos = barrido.barre(g, red, o, d, obs, T6, n_trabajos=1)
    distintos = {tuple(c.tolist()) for c in caminos}
    assert len(distintos) > 1


def test_el_barrido_devuelve_un_valor_por_vector_de_pesos():
    g, o, d = _montaje()
    red = barrido.red_simplex(2, 6)
    obs = grafo.xy(g.filcol[[o, d]], T6)
    D, largos, caminos = barrido.barre(g, red, o, d, obs, T6, n_trabajos=1)
    assert len(D) == len(largos) == len(caminos) == len(red)
    assert np.isfinite(D).all()
    assert (largos > 0).all()


def test_el_barrido_rechaza_una_red_con_otro_numero_de_componentes():
    g, o, d = _montaje()
    obs = grafo.xy(g.filcol[[o, d]], T6)
    with pytest.raises(ValueError, match="componentes"):
        barrido.barre(g, barrido.red_simplex(3, 4), o, d, obs, T6, n_trabajos=1)


def test_tabla_optimo_resume_en_claro():
    g, o, d = _montaje()
    red = barrido.red_simplex(2, 6)
    obs = grafo.xy(g.filcol[[o, d]], T6)
    D, largos, _ = barrido.barre(g, red, o, d, obs, T6, n_trabajos=1)
    fila = barrido.tabla_optimo(D, largos, red, g.nombres, observado_largo=1000.0)
    assert set(fila) == {"pendiente", "rugosidad", "D_media_m",
                         "largo_modelado_km", "largo_observado_km"}
    assert fila["pendiente"] + fila["rugosidad"] == pytest.approx(1.0, abs=1e-9)


def test_optimo_falla_si_ningun_peso_dio_camino():
    with pytest.raises(ValueError, match="ningun"):
        barrido.optimo(np.array([np.inf, np.inf]), barrido.red_simplex(2, 1))
