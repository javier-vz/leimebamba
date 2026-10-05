"""Pendiente, aspecto y rugosidad sobre superficies de respuesta conocida."""

import numpy as np
import pytest

from camino import superficies

DX = 30.0


def plano(nf=21, nc=21, pend_E=0.1, pend_N=0.0):
    """Plano con pendiente conocida. Fila 0 al norte, asi que el norte
    crece cuando el indice de fila baja."""
    j = np.arange(nc)[None, :] * DX
    i = np.arange(nf)[:, None] * DX
    return pend_E * j - pend_N * i


def test_gradientes_sobre_un_plano_inclinado_al_este():
    z = plano(pend_E=0.1)
    dE, dN = superficies.gradientes(z, DX)
    interior = (slice(1, -1), slice(1, -1))
    assert dE[interior] == pytest.approx(0.1, abs=1e-9)
    assert dN[interior] == pytest.approx(0.0, abs=1e-9)


def test_gradiente_al_norte():
    # pend_N = 0.2 significa que z crece 0.2 por metro hacia el norte
    z = plano(pend_E=0.0, pend_N=0.2)
    _, dN = superficies.gradientes(z, DX)
    assert dN[1:-1, 1:-1] == pytest.approx(0.2, abs=1e-9)


def test_pendiente_es_el_arcotangente_del_gradiente():
    z = plano(pend_E=0.25)
    S, _ = superficies.pendiente_aspecto(z, DX)
    assert S[1:-1, 1:-1] == pytest.approx(np.arctan(0.25), abs=1e-9)


def test_aspecto_apunta_cuesta_abajo():
    """Si el terreno sube hacia el este, la maxima bajada va al oeste
    (azimut 270 grados)."""
    z = plano(pend_E=0.1)
    _, A = superficies.pendiente_aspecto(z, DX)
    assert np.degrees(A[1:-1, 1:-1]) == pytest.approx(270.0, abs=1e-6)


def test_aspecto_al_sur():
    z = plano(pend_E=0.0, pend_N=0.1)    # sube hacia el norte
    _, A = superficies.pendiente_aspecto(z, DX)
    assert np.degrees(A[1:-1, 1:-1]) == pytest.approx(180.0, abs=1e-6)


def test_vrm_es_cero_en_un_plano_aunque_este_inclinado():
    """Es la razon de usar VRM y no TRI: separa inclinado de desordenado."""
    for p in (0.0, 0.1, 0.4):
        z = plano(pend_E=p)
        S, A = superficies.pendiente_aspecto(z, DX)
        assert np.nanmax(superficies.vrm(S, A)[2:-2, 2:-2]) < 1e-9


def test_vrm_crece_con_el_desorden_y_queda_en_cero_uno():
    rng = np.random.default_rng(42)
    z = plano(41, 41, 0.1) + rng.normal(0, 25, (41, 41))
    S, A = superficies.pendiente_aspecto(z, DX)
    v = superficies.vrm(S, A)[2:-2, 2:-2]
    assert np.nanmin(v) >= 0.0 and np.nanmax(v) <= 1.0
    assert np.nanmean(v) > 0.01


def test_nodata_no_contamina_mas_alla_de_su_celda():
    z = plano(21, 21, 0.1)
    val = np.ones(z.shape, dtype=bool)
    val[10, 10] = False
    dE, _ = superficies.gradientes(z, DX, valido=val)
    assert np.isnan(dE[10, 10])
    # la celda vecina sigue dando la pendiente del plano, renormalizada
    assert dE[10, 12] == pytest.approx(0.1, abs=1e-9)
    assert np.isfinite(dE[10, 11])


def test_twi_crece_con_el_area():
    S = np.array([[np.arctan(0.1), np.arctan(0.1)]])
    t = superficies.twi(np.array([[100.0, 1000.0]]), S)
    assert t[0, 1] - t[0, 0] == pytest.approx(np.log(10.0), abs=1e-9)


def test_twi_baja_con_la_pendiente():
    a = np.array([[500.0, 500.0]])       # misma area, distinta pendiente
    t = superficies.twi(a, np.array([[np.arctan(0.1), np.arctan(0.5)]]))
    assert t[0, 1] < t[0, 0]


def test_phi_drenaje_es_logaritmica():
    phi = superficies.phi_drenaje(np.array([0.0, 9.0, 999.0]))
    assert phi == pytest.approx([0.0, 1.0, 3.0])
