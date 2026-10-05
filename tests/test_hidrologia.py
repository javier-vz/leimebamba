"""Relleno de depresiones, D8 y acumulacion, sobre terrenos de respuesta exacta."""

import numpy as np
import pytest

from camino import hidrologia

DX = 30.0


def ladera(nf=10, nc=10, caida=1.0):
    """Ladera que baja hacia el sur: z = 100 - caida * fila."""
    return 100.0 - caida * np.arange(nf, dtype=float)[:, None] * np.ones(nc)


def test_la_ladera_monotona_no_se_altera_al_rellenar():
    z = ladera()
    r = hidrologia.rellenar(z, incremento=1e-4)
    assert np.allclose(r, z, atol=1e-3)


def test_el_relleno_sube_un_sumidero_a_su_nivel_de_derrame():
    """El pozo en la fila 5 derrama por sus vecinos de la fila 6, que estan
    a 94 m. El relleno debe dejarlo justo ahi, mas el incremento minimo."""
    z = ladera()
    z[5, 5] = -50.0
    r = hidrologia.rellenar(z, incremento=1e-4)
    assert r[5, 5] == pytest.approx(94.0 + 1e-4, abs=1e-3)


def test_despues_de_rellenar_no_quedan_sumideros_interiores():
    rng = np.random.default_rng(7)
    z = ladera(30, 30, caida=0.5) + rng.normal(0, 3.0, (30, 30))
    r = hidrologia.rellenar(z)
    for i in range(1, 29):
        for j in range(1, 29):
            vec = [r[i + a, j + b] for a in (-1, 0, 1) for b in (-1, 0, 1)
                   if (a, b) != (0, 0)]
            assert r[i, j] > min(vec) - 1e-9, f"sumidero en ({i},{j})"


def test_d8_apunta_cuesta_abajo_derecho_en_una_ladera():
    z = ladera()
    d = hidrologia.d8(z, DX)
    nf, nc = z.shape
    for i in range(nf - 1):
        for j in range(1, nc - 1):
            assert d[i, j] == (i + 1) * nc + j


def test_la_fila_de_salida_no_drena_a_ninguna_celda():
    z = ladera()
    d = hidrologia.d8(z, DX)
    assert np.all(d[-1, :] == -1)


def test_acumulacion_en_una_ladera_es_exacta():
    """Cada columna drena recta al sur, asi que la celda de salida de cada
    columna acumula exactamente el numero de filas."""
    z = ladera()
    nf, nc = z.shape
    d = hidrologia.d8(z, DX)
    acc = hidrologia.acumulacion(d, z_relleno=z)
    assert acc[-1, 1:-1] == pytest.approx(float(nf))
    assert acc[0, :] == pytest.approx(1.0)
    assert acc.min() >= 1.0
    assert acc.max() <= z.size


def test_la_acumulacion_conserva_el_total():
    rng = np.random.default_rng(3)
    z = ladera(24, 24, 0.5) + rng.normal(0, 2.0, (24, 24))
    r = hidrologia.rellenar(z)
    d = hidrologia.d8(r, DX)
    acc = hidrologia.acumulacion(d, z_relleno=r)
    salidas = d < 0
    assert acc[salidas].sum() == pytest.approx(float(z.size))


def test_el_valle_acumula_mas_que_la_ladera():
    nf = nc = 31
    j = np.arange(nc)[None, :]
    z = (100.0 - 0.5 * np.arange(nf)[:, None]) + 0.05 * np.abs(j - 15) * DX
    r = hidrologia.rellenar(z)
    acc = hidrologia.acumulacion(hidrologia.d8(r, DX), z_relleno=r)
    assert acc[-2, 15] > 5 * acc[-2, 2]


def test_cauces_respeta_el_umbral():
    acc = np.array([[1.0, 400.0, 500.0, 900.0]])
    m = hidrologia.cauces(acc, umbral=500.0)
    assert m.tolist() == [[False, False, True, True]]


def test_area_especifica_en_celdas_cuadradas():
    a = hidrologia.area_especifica(np.array([[10.0]]), DX)
    assert a[0, 0] == pytest.approx(10.0 * DX)


def test_la_mascara_recorta_el_dominio():
    z = ladera(12, 12)
    val = np.ones(z.shape, dtype=bool)
    val[:, :4] = False
    r = hidrologia.rellenar(z, valido=val)
    assert np.all(np.isnan(r[:, :4]))
    assert np.all(np.isfinite(r[:, 4:]))
