"""El grafo: costos a mano, anisotropia, saltos de caballo y la permutacion CSR.

El test que importa es `test_la_permutacion_csr_es_correcta`. Es el bug que
no se nota: si `csr.data` no queda alineado con las filas de Phi, el modelo
corre, converge y devuelve numeros creibles -- sobre aristas equivocadas.
"""

import numpy as np
import pytest
import scipy.sparse as sp

from camino import costo, grafo

DX = 30.0


def tablero(nf=3, nc=3, rugosidad=0.5):
    z = np.zeros((nf, nc))
    comp = {"rugosidad": np.full((nf, nc), rugosidad)}
    mask = np.ones((nf, nc), dtype=bool)
    return z, mask, comp


def test_costo_de_una_arista_cardinal_a_mano():
    z, mask, comp = tablero()
    z[1, 2] = 3.0                      # 3 m en 30 m -> g = 0.1
    g = grafo.construir(z, mask, comp, DX)
    c = g.costos(np.array([1.0, 0.0]))
    i, j = g.nodo(1, 1), g.nodo(1, 2)
    assert c[i, j] == pytest.approx(30.0 * costo.minetti(0.1) / 2.5)


def test_costo_de_la_componente_simetrica_a_mano():
    z, mask, comp = tablero(rugosidad=0.5)
    g = grafo.construir(z, mask, comp, DX)
    c = g.costos(np.array([0.0, 1.0]))
    assert c[g.nodo(1, 1), g.nodo(1, 2)] == pytest.approx(30.0 * 0.5)


def test_la_diagonal_mide_raiz_de_dos():
    z, mask, comp = tablero()
    g = grafo.construir(z, mask, comp, DX)
    c = g.costos(np.array([1.0, 0.0]))
    assert c[g.nodo(1, 1), g.nodo(0, 2)] == pytest.approx(30.0 * np.sqrt(2))


def test_la_pendiente_es_anisotropica_y_las_demas_no():
    z, mask, comp = tablero()
    z[1, 2] = 3.0
    g = grafo.construir(z, mask, comp, DX)
    i, j = g.nodo(1, 1), g.nodo(1, 2)

    c_pend = g.costos(np.array([1.0, 0.0]))
    assert c_pend[i, j] != pytest.approx(c_pend[j, i])
    assert c_pend[i, j] > c_pend[j, i]          # subir cuesta mas que bajar

    c_rug = g.costos(np.array([0.0, 1.0]))
    assert c_rug[i, j] == pytest.approx(c_rug[j, i])


def test_las_aristas_fuera_del_rango_de_minetti_se_eliminan():
    z, mask, comp = tablero()
    z[1, 2] = 100.0                    # g = 3.33, muy fuera de +-0.45
    g = grafo.construir(z, mask, comp, DX)
    c = g.costos(np.array([1.0, 0.0]))
    i, j = g.nodo(1, 1), g.nodo(1, 2)
    assert c[i, j] == 0.0 and c[j, i] == 0.0     # no existe la arista
    assert (i, j) not in set(zip(*c.nonzero()))


def test_el_salto_de_caballo_existe_en_vecindad_16():
    z, mask, comp = tablero(5, 5)
    g16 = grafo.construir(z, mask, comp, DX, vecinos=grafo.VECINOS_16)
    c = g16.costos(np.array([1.0, 0.0]))
    assert c[g16.nodo(2, 2), g16.nodo(1, 4)] > 0


def test_la_vecindad_8_no_tiene_saltos_de_caballo():
    z, mask, comp = tablero(5, 5)
    g8 = grafo.construir(z, mask, comp, DX, vecinos=grafo.VECINOS_8)
    c = g8.costos(np.array([1.0, 0.0]))
    assert c[g8.nodo(2, 2), g8.nodo(1, 4)] == 0.0
    assert g8.e < grafo.construir(z, mask, comp, DX).e


def test_el_salto_de_caballo_respeta_la_celda_intermedia():
    """Es el error clasico de la vecindad 16: el paso (-1,+2) cruza por
    encima de (0,+1) y (-1,+1). Si no se comprueban, el camino salta
    acantilados."""
    z, mask, comp = tablero(5, 5)
    mask[2, 3] = False                 # una de las dos celdas intermedias
    g = grafo.construir(z, mask, comp, DX)
    c = g.costos(np.array([1.0, 0.0]))
    assert c[g.nodo(2, 2), g.nodo(1, 4)] == 0.0


def test_intermedias_de_cada_salto():
    assert grafo.intermedias(-1, 2) == ((0, 1), (-1, 1))
    assert grafo.intermedias(1, -2) == ((0, -1), (1, -1))
    assert grafo.intermedias(2, 1) == ((1, 0), (1, 1))
    assert grafo.intermedias(-2, -1) == ((-1, 0), (-1, -1))
    assert grafo.intermedias(1, 1) == ()      # las cardinales y diagonales no


def test_la_permutacion_csr_es_correcta():
    """Recalcula el costo de CADA arista desde el raster, sin tocar g.L ni
    g.Phi, y lo compara con lo que quedo en la matriz."""
    rng = np.random.default_rng(11)
    nf = nc = 12
    z = rng.normal(0, 4.0, (nf, nc))
    rug = rng.uniform(0.2, 1.0, (nf, nc))
    hum = rng.uniform(0.0, 1.0, (nf, nc))
    mask = np.ones((nf, nc), dtype=bool)
    mask[4, 7] = mask[9, 2] = False

    g = grafo.construir(z, mask, {"rugosidad": rug, "humedad": hum}, DX)
    assert g.nombres == ("pendiente", "rugosidad", "humedad")

    w = np.array([0.5, 0.3, 0.2])
    c = g.costos(w).tocoo()

    revisadas = 0
    for i, j, valor in zip(c.row, c.col, c.data):
        fi, ci = g.filcol[i]
        fj, cj = g.filcol[j]
        largo = float(np.hypot((fj - fi) * DX, (cj - ci) * DX))
        gg = (z[fj, cj] - z[fi, ci]) / largo
        esperado = largo * (
            w[0] * costo.minetti(gg) / 2.5
            + w[1] * 0.5 * (rug[fi, ci] + rug[fj, cj])
            + w[2] * 0.5 * (hum[fi, ci] + hum[fj, cj]))
        assert valor == pytest.approx(esperado, rel=1e-12), f"arista {i}->{j}"
        revisadas += 1

    assert revisadas == g.e > 500


def test_no_hay_aristas_duplicadas():
    rng = np.random.default_rng(5)
    z = rng.normal(0, 3.0, (10, 10))
    mask = np.ones((10, 10), dtype=bool)
    g = grafo.construir(z, mask, {"rug": np.full((10, 10), 0.5)}, DX)
    pares = set(zip(*g.costos(np.array([1.0, 0.0])).nonzero()))
    assert len(pares) == g.e


def test_los_costos_son_estrictamente_positivos():
    """Si una arista cuesta cero, Dijkstra devuelve caminos degenerados."""
    rng = np.random.default_rng(2)
    z = rng.normal(0, 3.0, (14, 14))
    comp = {"rug": costo.normaliza(rng.uniform(size=(14, 14)))}
    g = grafo.construir(z, np.ones((14, 14), dtype=bool), comp, DX)
    for w in (np.array([1.0, 0.0]), np.array([0.0, 1.0]), np.array([0.5, 0.5])):
        assert g.costos(w).data.min() > 0


def test_los_pesos_tienen_que_estar_en_el_simplex():
    z, mask, comp = tablero()
    g = grafo.construir(z, mask, comp, DX)
    with pytest.raises(ValueError, match="simplex"):
        g.costos(np.array([0.5, 0.2]))
    with pytest.raises(ValueError, match="negativ"):
        g.costos(np.array([1.5, -0.5]))
    with pytest.raises(ValueError, match="componentes"):
        g.costos(np.array([1.0]))


def test_la_mascara_saca_los_nodos():
    z, mask, comp = tablero(6, 6)
    mask[2:4, 2:4] = False
    g = grafo.construir(z, mask, comp, DX)
    assert g.n == 36 - 4
    assert g.indice[2, 2] == -1
    with pytest.raises(ValueError, match="enmascarada"):
        g.nodo(2, 2)


def test_recorre_reconstruye_el_camino():
    from scipy.sparse.csgraph import dijkstra
    z, mask, comp = tablero(8, 8)
    g = grafo.construir(z, mask, comp, DX)
    o, d = g.nodo(0, 0), g.nodo(7, 7)
    _, pred = dijkstra(g.costos(np.array([1.0, 0.0])), directed=True,
                       indices=o, return_predecessors=True)
    cam = grafo.recorre(pred, o, d)
    assert cam[0] == o and cam[-1] == d
    assert len(cam) >= 5


def test_recorre_devuelve_vacio_si_no_hay_camino():
    pred = np.array([-9999, -9999, -9999])
    assert grafo.recorre(pred, 0, 2).size == 0


def test_xy_usa_el_centro_de_pixel():
    # transform de rasterio: (a, b, c, d, e, f) con a=30, e=-30
    t = (30.0, 0.0, 161000.0, 0.0, -30.0, 9321000.0)
    out = grafo.xy(np.array([[0, 0], [1, 2]]), t)
    assert out[0] == pytest.approx([161015.0, 9320985.0])
    assert out[1] == pytest.approx([161075.0, 9320955.0])
