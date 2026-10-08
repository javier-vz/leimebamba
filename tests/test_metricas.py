"""Las dos distancias, sobre casos de valor conocido."""

import numpy as np
import pytest

from camino import metricas


def segmento(largo=1000.0, n=51, y=0.0):
    return np.column_stack([np.linspace(0.0, largo, n), np.full(n, y)])


def test_frechet_de_una_curva_consigo_misma_es_cero():
    P = segmento()
    assert metricas.frechet_discreta(P, P) == pytest.approx(0.0, abs=1e-9)


def test_frechet_de_dos_paralelas_es_la_separacion():
    assert metricas.frechet_discreta(segmento(y=0.0), segmento(y=37.0)) \
        == pytest.approx(37.0, abs=1e-6)


def test_frechet_respeta_el_orden_del_recorrido():
    """Frechet y distancia media NO son la misma cosa: sobre un segmento y
    su reverso los puntos coinciden (media = 0) pero el recorrido es
    incompatible (Frechet = el largo del segmento)."""
    P = segmento(1000.0)
    Q = P[::-1]
    assert metricas.distancia_media_simetrica(P, Q) == pytest.approx(0.0, abs=1e-9)
    assert metricas.frechet_discreta(P, Q) == pytest.approx(1000.0, abs=1.0)


def test_frechet_castiga_un_desvio_puntual_que_la_media_diluye():
    P = segmento(1000.0, 201)
    Q = P.copy()
    Q[100, 1] = 300.0                 # un solo vertice muy desviado
    assert metricas.frechet_discreta(P, Q) > 250.0
    assert metricas.distancia_media_simetrica(P, Q) < 20.0


def test_distancia_media_de_dos_paralelas():
    assert metricas.distancia_media_simetrica(segmento(y=0.0), segmento(y=12.0)) \
        == pytest.approx(12.0, abs=1e-6)


def test_distancia_media_es_simetrica():
    P, Q = segmento(y=0.0), segmento(800.0, 37, y=25.0)
    assert metricas.distancia_media_simetrica(P, Q) \
        == pytest.approx(metricas.distancia_media_simetrica(Q, P))


def test_distancia_de_una_curva_consigo_misma_es_cero():
    P = segmento()
    assert metricas.distancia_media_simetrica(P, P) == pytest.approx(0.0)


def test_caminos_vacios_dan_infinito():
    vacio = np.empty((0, 2))
    assert metricas.distancia_media_simetrica(vacio, segmento()) == np.inf
    assert metricas.frechet_discreta(segmento(), vacio) == np.inf


def test_remuestrea_conserva_extremos_y_equiespacia():
    P = np.array([[0.0, 0.0], [100.0, 0.0], [100.0, 100.0]])
    R = metricas.remuestrea(P, 21)
    assert R.shape == (21, 2)
    assert R[0] == pytest.approx(P[0])
    assert R[-1] == pytest.approx(P[-1])
    paso = np.linalg.norm(np.diff(R, axis=0), axis=1)
    assert paso.std() < 1e-6


def test_remuestrear_no_cambia_la_frechet_de_paralelas():
    a = metricas.frechet_discreta(segmento(n=11, y=0), segmento(n=501, y=5.0))
    assert a == pytest.approx(5.0, abs=1e-6)


def test_longitud():
    assert metricas.longitud(segmento(1000.0)) == pytest.approx(1000.0)
    assert metricas.longitud(np.array([[0.0, 0.0]])) == 0.0


def test_toca_borde_detecta_el_camino_pegado_al_corredor():
    m = np.zeros((10, 10), dtype=bool)
    m[3:7, 3:7] = True
    adentro = np.array([[5, 5]])
    pegado = np.array([[5, 5], [3, 3]])
    assert not metricas.toca_borde(adentro, m)
    assert metricas.toca_borde(pegado, m)


def test_sinuosidad_es_uno_en_una_recta_y_crece_con_el_rodeo():
    recta = metricas.sinuosidad(1000.0, [(0, 0), (1000, 0)])
    assert recta == pytest.approx(1.0)

    # media circunferencia entre dos puntos a 1000 m: pi*500 = 1570.8
    media_vuelta = metricas.sinuosidad(1570.8, [(0, 0), (1000, 0)])
    assert media_vuelta == pytest.approx(1.571, abs=0.001)

    # extremos coincidentes: no esta definida
    assert metricas.sinuosidad(500.0, [(0, 0), (0, 0)]) == float("inf")


def test_autoproximidad_separa_un_rodeo_de_una_horquilla():
    """La medida que distingue "el camino rodea un cerro" de "linemerge
    cosio dos ramas": las dos dan la misma sinuosidad."""
    import numpy as np

    # un rodeo: medio circulo de 2 km de radio. Se aleja de si mismo.
    th = np.linspace(0, np.pi, 120)
    rodeo = np.column_stack([2000 * np.cos(th), 2000 * np.sin(th)])
    assert metricas.autoproximidad(rodeo, 1000.0) > 500

    # una horquilla: ida y vuelta casi por el mismo sitio, 40 m aparte
    ida = np.column_stack([np.linspace(0, 5000, 120), np.zeros(120)])
    vuelta = np.column_stack([np.linspace(5000, 0, 120), np.full(120, 40.0)])
    horquilla = np.vstack([ida, vuelta])
    assert metricas.autoproximidad(horquilla, 1000.0) == pytest.approx(40.0,
                                                                      abs=1.0)

    # las dos tienen sinuosidad alta, que es lo que las confunde
    assert metricas.sinuosidad(np.pi * 2000, rodeo[[0, -1]]) > 1.5
    assert metricas.sinuosidad(10000.0, horquilla[[0, -1]]) > 100


def test_autoproximidad_de_una_recta_es_infinita():
    import numpy as np
    recta = np.column_stack([np.linspace(0, 5000, 50), np.zeros(50)])
    assert metricas.autoproximidad(recta, 1000.0) > 900


def test_giro_maximo_caza_la_inversion_de_una_union():
    import numpy as np

    suave = np.column_stack([np.linspace(0, 1000, 20),
                             np.linspace(0, 100, 20)])
    assert metricas.giro_maximo(suave) < 5

    # un vertice donde la linea se invierte
    pico = np.array([[0.0, 0.0], [1000.0, 0.0], [10.0, 30.0]])
    assert metricas.giro_maximo(pico) > 150

    assert metricas.giro_maximo(np.array([[0.0, 0.0]])) == 0.0
