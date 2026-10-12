"""El analisis: que dicen juntos los resultados de los pasos anteriores.

Cada paso del pipeline deja su tabla, y una tabla por paso no es un
analisis: son numeros sueltos que hay que cruzar a mano para que signifiquen
algo. Una razon de costo de 1.07 no dice nada por si sola; dicha junto a una
distancia media de 668 m entre las dos rutas, dice que el modelo no puede
distinguir el recorrido de su propio optimo aunque vayan por sitios
distintos, que es un resultado y no una medida.

Este paso hace ese cruce. Lee lo que produjeron `revisar`, `trayectorias` y
`razon`, calcula lo que falta para interpretarlos, y escribe:

    resultados/analisis.md      el analisis, para leer y para pegar
    resultados/dos_rutas.png    un panel por unidad, sobre el relieve
    resultados/vista.gpkg       todas las capas juntas, para QGIS
    resultados/recorrido.kmz    lo mismo para Google Earth

Lo que cruza:

    COSTO CONTRA GEOMETRIA     razon de costo frente a separacion entre las
                               dos rutas. Razon ~1 con separacion grande es
                               equifinalidad: muchas maneras de cruzar el
                               paisaje por un precio parecido.
    DONDE SE SEPARAN           el perfil de separacion a lo largo de cada
                               unidad, su maximo y en que punto cae.
    PARADAS CONTRA WAYPOINTS   cuantas paradas caen cerca de un punto
                               marcado y cuales no. Una parada larga lejos
                               de todo waypoint es un lugar que el GPS
                               ubico y nadie habia marcado.
    LUZ                        cuanto se camino de noche. Un modelo de
                               costo no puede producir marcha nocturna:
                               nadie elige la hora mas fria y sin luz para
                               ahorrar energia.

Si falta una pieza, lo dice y sigue con las demas.

SOBRE EL KMZ Y GOOGLE EARTH. Se escribe la version que abre en LAS DOS,
la web y la de escritorio: sin `gx:Track` y sin `TimeSpan`, que la web no
soporta y le hacen dar error. El orden y las horas van en el nombre de cada
tramo, que se lee igual. Los iconos van DENTRO del kmz --es un zip-- para
que no dependan de ninguna URL.

SOBRE LOS WAYPOINTS. Un GPX de favoritos suele traer puntos personales
mezclados con los del estudio: la casa de uno, un cementerio, la casa de
alguien con nombre y apellido. Esos NO van en una capa de trabajo ni en un
archivo que se reenvia. Con 'trayectorias.prefijos_waypoints' en la config
se dice que prefijos son del estudio; sin eso entran todos y el paso avisa.
"""

from __future__ import annotations

import datetime as _dt
import math
import pathlib
import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import escape

import numpy as np

GPX = "{http://www.topografix.com/GPX/1/1}"

# El color codifica IDENTIDAD, como en `figuras`: que linea es cual.
OBSERVADO = "#1f4e79"
MODELADO = "#d1562f"
NOCHE = "#ffd900"

# KML usa aabbggrr, al reves del html. Es el error clasico al escribirlo a
# mano: el azul sale naranja.
KML_OBSERVADO = "ff794e1f"
KML_MODELADO = "ff2f56d1"
KML_NOCHE = "ff00d9ff"

# Sol por debajo de esto = oscuridad de verdad, no penumbra. Es el
# crepusculo nautico.
SOL_DE_NOCHE = -12.0


# ------------------------------------------------------------- analisis

def separacion(obs_geom, mod_geom, n=400):
    """Perfil de separacion entre las dos rutas, a lo largo de la observada.

    Devuelve (s, d): distancia recorrida y separacion en cada punto. Es lo
    que convierte una distancia media en algo interpretable: 668 m de media
    puede ser un apartamiento parejo o un rodeo concentrado en un trecho, y
    son dos cosas distintas.
    """
    s = np.linspace(0.0, obs_geom.length, n)
    d = np.array([obs_geom.interpolate(float(v)).distance(mod_geom)
                  for v in s])
    return s, d


# Por debajo de esto, un trecho no tiene margen para que el optimo pueda
# diferir del observado: casi cualquier juego de pesos da el mismo camino y
# la comparacion no tiene poder. Es el mismo orden que 'largo_min_bloque' y
# por la misma razon.
#
# NO se usa como puerta. El umbral de 'largo_min_unidad' decide que entra al
# analisis, y conviene ponerlo bajo para que entre todo el recorrido; esto
# solo MARCA las unidades en las que la razon vale poco, que es mas honesto
# que esconderlas.
CORTO_M = 1500.0


def costo_contra_geometria(filas):
    """La lectura cruzada: razon de costo frente a separacion.

    La razon dice cuanto MAS CARO es el recorrido que su optimo. La
    separacion dice cuan LEJOS va. Las cuatro combinaciones significan cosas
    distintas y solo una es "el modelo acierta".
    """
    salida = []
    for f in filas:
        r = f.get("razon_de_costo")
        d = f.get("distancia_media_m")
        if r is None or d is None:
            continue
        caro = r >= 1.15
        lejos = d >= 250.0
        if not caro and not lejos:
            lectura = ("el modelo reproduce el recorrido: ni mas caro ni "
                       "por otro sitio")
        elif not caro and lejos:
            lectura = ("EQUIFINALIDAD: va por otro sitio y cuesta casi lo "
                       "mismo, asi que el costo no puede explicar la forma "
                       "ni descartarla")
        elif caro and not lejos:
            lectura = ("sigue la misma linea pero pagando de mas: suele ser "
                       "la franja rozando celda enmascarada, mirarlo")
        else:
            lectura = ("el recorrido pasa por donde el modelo lo considera "
                       "caro: ahi falta algo en el modelo")
        corto = f.get("largo_observado_km", 99) * 1000 < CORTO_M
        if corto:
            lectura = ("trecho corto: en menos de "
                       f"{CORTO_M/1000:.1f} km casi cualquier juego de pesos "
                       "da el mismo camino, asi que la razon dice poco. " +
                       lectura)
        salida.append({**f, "caro": caro, "lejos": lejos, "corto": corto,
                       "lectura": lectura})
    return salida


def paradas_contra_waypoints(par, wpt, cerca_m=300.0):
    """A que distancia esta cada parada del waypoint mas cercano.

    La pregunta no es cuantas aciertan. Es al reves: una parada LARGA lejos
    de todo waypoint es un lugar donde la gente se detuvo mucho rato y nadie
    habia marcado nada. Si el recorrido esta organizado por estaciones, esas
    son candidatas a estacion, y el GPS las ubico solo.
    """
    if par is None or len(par) == 0 or wpt is None or len(wpt) == 0:
        return None
    filas = []
    for _, r in par.iterrows():
        d = wpt.distance(r.geometry)
        j = int(d.idxmin())
        filas.append({
            "traza": str(r.get("traza", "")),
            "minutos": float(r.get("minutos", 0)),
            "altitud_m": float(r.get("altitud_m", 0)),
            "waypoint": str(wpt.loc[j, "nombre"]),
            "distancia_m": float(d.loc[j]),
        })
    filas.sort(key=lambda f: -f["minutos"])
    d = np.array([f["distancia_m"] for f in filas])
    m = np.array([f["minutos"] for f in filas])
    return {
        "filas": filas,
        "n": len(filas),
        "cerca": int((d < cerca_m).sum()),
        "mediana_m": float(np.median(d)),
        "p25_m": float(np.percentile(d, 25)),
        # las que importan: largas y lejos
        "candidatas": [f for f in filas
                       if f["minutos"] >= 30 and f["distancia_m"] >= cerca_m],
    }


def luz(cfg):
    """Cuanto se CAMINO de noche, por tramo.

    Sol por debajo de -12 grados: crepusculo nautico, oscuridad de verdad.

    SOLO LOS TRAMOS A PIE. Contar los tramos en vehiculo convierte el
    resultado en una falsedad: en estos datos daba "135 km de noche", que
    son 14 caminados mas 121 de carretera nocturna. Ir en camion de noche no
    dice nada de como se organiza un recorrido a pie. El modo lo decide
    `trayectoria.modo`, con la velocidad del propio receptor.
    """
    from pyproj import Transformer

    from . import trayectoria

    carpeta = cfg.dir_datos / "trayectorias"
    if not carpeta.is_dir():
        return None
    tr = Transformer.from_crs("EPSG:4326", cfg.crs, always_xy=True)
    filas = []
    tot = {"dia": [0.0, 0.0], "noche": [0.0, 0.0]}
    fuera = 0
    for ruta in sorted(carpeta.glob("*.gpx")):
        try:
            tz = trayectoria.lee(ruta, cfg.crs)
        except SystemExit:
            continue
        ps = trayectoria.paradas(
            tz, getattr(cfg, "parada_radio", 20.0),
            getattr(cfg, "parada_min_s", 120.0),
            getattr(cfg, "parada_criterio", "ambos"))
        if trayectoria.modo(tz, ps,
                            getattr(cfg, "v_max_a_pie", 4.0)) == "vehiculo":
            fuera += 1
            continue
        try:
            raiz = ET.parse(ruta).getroot()
        except ET.ParseError:
            continue
        lat, lon, ts = [], [], []
        for pt in raiz.iter(GPX + "trkpt"):
            t = pt.find(GPX + "time")
            if t is None or not t.text:
                continue
            lat.append(float(pt.get("lat")))
            lon.append(float(pt.get("lon")))
            ts.append(_dt.datetime.fromisoformat(
                t.text.strip().replace("Z", "+00:00")))
        if len(ts) < 2:
            continue
        x, y = tr.transform(np.array(lon), np.array(lat))
        d = np.hypot(np.diff(x), np.diff(y))
        dt = np.array([(ts[i + 1] - ts[i]).total_seconds()
                       for i in range(len(ts) - 1)])
        oscuro = np.array([altura_solar(ts[i], lat[i], lon[i]) < SOL_DE_NOCHE
                           for i in range(len(ts) - 1)])
        val = (dt > 0) & (dt < 600)
        km_n = float(d[oscuro].sum()) / 1000
        h_n = float(dt[oscuro & val].sum()) / 3600
        km = float(d.sum()) / 1000
        h = float(dt[val].sum()) / 3600
        tot["noche"][0] += km_n; tot["noche"][1] += h_n
        tot["dia"][0] += km - km_n; tot["dia"][1] += h - h_n
        filas.append({"traza": ruta.stem, "km": km, "horas": h,
                      "km_noche": km_n, "horas_noche": h_n,
                      "fraccion_km": km_n / km if km else 0.0})
    if not filas:
        return None
    KM = tot["dia"][0] + tot["noche"][0]
    H = tot["dia"][1] + tot["noche"][1]
    return {"filas": filas, "km_noche": tot["noche"][0],
            "horas_noche": tot["noche"][1],
            "trazas_en_vehiculo": fuera,
            "fraccion_km": tot["noche"][0] / KM if KM else 0.0,
            "fraccion_horas": tot["noche"][1] / H if H else 0.0}


# ------------------------------------------------------------- utilidades

def _relieve(dem, res, az=315.0, alt=45.0):
    """Sombreado estandar. El terreno se lee sin colorearlo."""
    dy, dx = np.gradient(dem, res)
    pend = np.arctan(np.hypot(dx, dy))
    asp = np.arctan2(-dx, dy)
    a, z = math.radians(az), math.radians(90 - alt)
    s = (math.cos(z) * np.cos(pend)
         + math.sin(z) * np.sin(pend) * np.cos(a - asp))
    return np.clip(s, 0, 1)


def altura_solar(t, lat, lon) -> float:
    """Altura del sol sobre el horizonte, en grados.

    Formulas estandar con precision de minutos, que sobra para decidir si
    estaba oscuro.
    """
    n = (t - _dt.datetime(2000, 1, 1, 12, tzinfo=_dt.timezone.utc)
         ).total_seconds() / 86400
    L = (280.460 + 0.9856474 * n) % 360
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.0000004 * n)
    dec = math.asin(math.sin(eps) * math.sin(lam))
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    gmst = (18.697374558 + 24.06570982441908 * n) % 24
    H = math.radians((gmst * 15 + lon - math.degrees(ra)) % 360)
    la = math.radians(lat)
    return math.degrees(math.asin(
        math.sin(la) * math.sin(dec)
        + math.cos(la) * math.cos(dec) * math.cos(H)))


def _lee_waypoints(cfg):
    """Los waypoints de los GPX de datos/, filtrados por prefijo."""
    import geopandas as gpd
    from pyproj import Transformer
    from shapely.geometry import Point

    prefijos = tuple(getattr(cfg, "prefijos_waypoints", ()) or ())
    tr = Transformer.from_crs("EPSG:4326", cfg.crs, always_xy=True)
    filas, geoms, fuera = [], [], 0
    for p in sorted(cfg.dir_datos.glob("*.gpx")):
        try:
            raiz = ET.parse(p).getroot()
        except ET.ParseError:
            continue
        for w in raiz.iter(GPX + "wpt"):
            n = w.find(GPX + "name")
            nombre = (n.text or "").strip() if n is not None else ""
            if prefijos and not nombre.startswith(prefijos):
                fuera += 1
                continue
            e = w.find(GPX + "ele")
            x, y = tr.transform(float(w.get("lon")), float(w.get("lat")))
            filas.append({
                "nombre": nombre,
                "altitud_m": (float(e.text)
                              if e is not None and e.text else None),
                "fuente": p.name,
            })
            geoms.append(Point(x, y))
    if not filas:
        return None
    if fuera:
        print(f"  {fuera} waypoints fuera por no llevar ninguno de los "
              f"prefijos {prefijos}")
    elif not prefijos:
        print("  AVISO: 'trayectorias.prefijos_waypoints' esta vacio, asi "
              "que entran TODOS los")
        print("  waypoints. Si el GPX trae puntos personales, estan en el "
              "GeoPackage y en el KMZ.")
    return gpd.GeoDataFrame(filas, geometry=geoms, crs=cfg.crs)


def _lee(ruta, capa):
    import geopandas as gpd
    if not ruta.exists():
        return None
    try:
        return gpd.read_file(ruta, layer=capa)
    except Exception:
        return None


# ---------------------------------------------------------------- figura

def figura(cfg, obs, mod, par, wpt, destino, cam=None) -> None:
    """Un panel por unidad: lo observado, el optimo y las paradas.

    Un panel por unidad y no todos juntos: las unidades pueden estar lejos
    unas de otras, y en un solo encuadre cada una queda del tamano de una
    una.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as pe
    import rasterio
    from matplotlib.lines import Line2D

    dem_ruta = cfg.dir_derivados / "cop30.tif"
    if not dem_ruta.exists():
        print(f"  (sin {dem_ruta.name}: la figura necesita el DEM)")
        return
    with rasterio.open(dem_ruta) as r:
        dem = r.read(1, masked=True).filled(np.nan).astype(float)
        t = r.transform
        ext = (t.c, t.c + t.a * r.width, t.f + t.e * r.height, t.f)
    hs = _relieve(np.nan_to_num(dem, nan=float(np.nanmedian(dem))),
                  cfg.resolucion)

    unidades = list(obs["unidad"].unique())
    n = len(unidades)
    if n == 0:
        print("  (no hay unidades que dibujar)")
        return
    cols = min(n, 3)
    filas_n = int(np.ceil(n / cols))
    fig, ejes = plt.subplots(filas_n, cols, figsize=(7.2 * cols,
                                                    7.4 * filas_n), dpi=170)
    ejes = np.atleast_1d(ejes).ravel()

    for k, u in enumerate(unidades):
        ax = ejes[k]
        o = obs[obs["unidad"] == u]
        m = mod[mod["unidad"] == u]
        ax.imshow(hs, cmap="gray", extent=ext, vmin=0, vmax=1, zorder=1,
                  interpolation="bilinear")
        ax.imshow(dem, cmap="terrain", extent=ext, alpha=0.32, zorder=2,
                  interpolation="bilinear")
        if cam is not None and len(cam):
            # todo lo caminado, fino y debajo: sin esto las paradas de los
            # trechos cortos salen flotando sin linea
            cam.plot(ax=ax, color=OBSERVADO, linewidth=1.3, alpha=0.55,
                     zorder=3)
        if len(m):
            m.plot(ax=ax, color=MODELADO, linewidth=2.6,
                   linestyle=(0, (5, 2.5)), zorder=4)
        o.plot(ax=ax, color=OBSERVADO, linewidth=2.8, zorder=5)

        linea = o.geometry.iloc[0]
        if par is not None and len(par):
            cerca = par[par.distance(linea) < 450.0]
            if len(cerca):
                ax.scatter(cerca.geometry.x, cerca.geometry.y,
                           s=np.clip(cerca.get("minutos", 10) * 2.6, 9, 320),
                           facecolor="white", edgecolor=OBSERVADO,
                           linewidth=1.3, alpha=0.95, zorder=6)
        if wpt is not None and len(wpt):
            ax.scatter(wpt.geometry.x, wpt.geometry.y, marker="^", s=92,
                       facecolor="#f2c200", edgecolor="#2b2b2b",
                       linewidth=1.0, zorder=7)
            vistos = []
            for _, w in wpt.iterrows():
                etiqueta = str(w["nombre"]).split("_", 1)[-1].replace("_", " ")
                etiqueta = etiqueta.replace(" PRE", "").replace(" REF", "")
                juntos = sum(1 for x, y in vistos
                             if abs(x - w.geometry.x) < 900
                             and abs(y - w.geometry.y) < 900)
                ax.annotate(etiqueta, (w.geometry.x, w.geometry.y),
                            xytext=(9, 6 - 11 * juntos),
                            textcoords="offset points", fontsize=7.6,
                            color="#111", zorder=9,
                            path_effects=[pe.withStroke(linewidth=2.6,
                                                        foreground="white")])
                vistos.append((w.geometry.x, w.geometry.y))

        b = o.total_bounds
        margen = max((b[2] - b[0]), (b[3] - b[1])) * 0.12
        ax.set_xlim(b[0] - margen, b[2] + margen)
        ax.set_ylim(b[1] - margen, b[3] + margen)
        ax.set_title(f"{u[:52]}  ·  {linea.length / 1000:.2f} km",
                     fontsize=10.5, loc="left", pad=6)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_xlabel(""); ax.set_ylabel("")
        for s in ax.spines.values():
            s.set_edgecolor("#999")

    for ax in ejes[n:]:
        ax.axis("off")

    ejes[0].legend(handles=[
        Line2D([], [], color=OBSERVADO, lw=2.8, label="lo observado"),
        Line2D([], [], color=MODELADO, lw=2.6, ls=(0, (5, 2.5)),
               label="el optimo del modelo (costo fisico)"),
        Line2D([], [], marker="o", color="none", markerfacecolor="white",
               markeredgecolor=OBSERVADO, markersize=9,
               label="parada (tamano = duracion)"),
        Line2D([], [], marker="^", color="none", markerfacecolor="#f2c200",
               markeredgecolor="#2b2b2b", markersize=10,
               label="waypoint"),
    ], loc="upper left", fontsize=8.6, framealpha=0.95, borderpad=0.7)

    fig.savefig(destino, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  -> {destino.relative_to(cfg.raiz)}")


# ------------------------------------------------------------------- kmz

def _coords(geom, tr):
    xs, ys = geom.coords.xy
    lo, la = tr.transform(np.array(xs), np.array(ys))
    return " ".join(f"{a:.6f},{b:.6f},0" for a, b in zip(lo, la))


def _iconos():
    """Los iconos, generados aqui y metidos en el zip.

    Dentro del KMZ y no en una URL: asi no dependen de que un servidor ajeno
    siga vivo ni de que haya internet. Un href roto da "la imagen no existe"
    y no se ve nada.
    """
    import io
    from PIL import Image, ImageDraw

    def png(dibuja):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        dibuja(ImageDraw.Draw(im))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

    return {
        "iconos/parada.png": png(lambda d: d.ellipse(
            [6, 6, 58, 58], fill=(255, 255, 255, 235),
            outline=(31, 78, 121, 255), width=5)),
        "iconos/parada_larga.png": png(lambda d: d.ellipse(
            [6, 6, 58, 58], fill=(209, 86, 47, 255),
            outline=(60, 20, 10, 255), width=5)),
        "iconos/waypoint.png": png(lambda d: d.polygon(
            [(32, 5), (59, 59), (5, 59)], fill=(242, 194, 0, 255),
            outline=(35, 35, 35, 255), width=4)),
    }


def kmz(cfg, obs, mod, par, wpt, destino, cam=None) -> None:
    """El KMZ que abre en Google Earth web Y de escritorio.

    Sin `gx:Track` ni `TimeSpan`: la version web no los lee y da error. El
    tiempo va escrito en los nombres, que se lee igual.
    """
    from pyproj import Transformer

    tr = Transformer.from_crs(cfg.crs, "EPSG:4326", always_xy=True)
    iconos = _iconos()
    partes = [
        f'<Style id="obs"><LineStyle><color>{KML_OBSERVADO}</color>'
        f'<width>5</width></LineStyle></Style>',
        f'<Style id="caminado"><LineStyle><color>{KML_OBSERVADO}</color>'
        f'<width>3</width></LineStyle></Style>',
        f'<Style id="mod"><LineStyle><color>{KML_MODELADO}</color>'
        f'<width>4</width></LineStyle></Style>',
        '<Style id="par"><IconStyle><scale>0.8</scale>'
        '<Icon><href>iconos/parada.png</href></Icon></IconStyle>'
        '<LabelStyle><scale>0</scale></LabelStyle></Style>',
        '<Style id="parlarga"><IconStyle><scale>1.4</scale>'
        '<Icon><href>iconos/parada_larga.png</href></Icon></IconStyle>'
        '</Style>',
        '<Style id="wpt"><IconStyle><scale>1.2</scale>'
        '<Icon><href>iconos/waypoint.png</href></Icon></IconStyle></Style>',
    ]
    usados = {"iconos/parada.png", "iconos/parada_larga.png",
              "iconos/waypoint.png"}

    def carpeta(nombre, nota, cuerpo):
        return (f"<Folder><name>{escape(nombre)}</name>"
                f"<description>{escape(nota)}</description>{cuerpo}</Folder>")

    def lineas(gdf, estilo):
        return "".join(
            f'<Placemark><name>{escape(str(r["unidad"])[:60])}</name>'
            f'<description>{r.geometry.length / 1000:.2f} km</description>'
            f'<styleUrl>#{estilo}</styleUrl><LineString><tessellate>1'
            f'</tessellate><altitudeMode>clampToGround</altitudeMode>'
            f'<coordinates>{_coords(r.geometry, tr)}</coordinates>'
            f'</LineString></Placemark>' for _, r in gdf.iterrows())

    if cam is not None and len(cam):
        # Primero TODO lo caminado. Va antes que las unidades porque es el
        # recorrido: las unidades son un recorte del analisis, no del viaje.
        cuerpo = "".join(
            f'<Placemark><name>{escape(str(r["tramnomb"])[:60])}</name>'
            f'<description>{r.geometry.length / 1000:.2f} km'
            f'{"" if r.get("es_unidad", True) else " — demasiado corto para ser unidad de analisis"}'
            f'</description>'
            f'<styleUrl>#caminado</styleUrl><LineString><tessellate>1'
            f'</tessellate><altitudeMode>clampToGround</altitudeMode>'
            f'<coordinates>{_coords(r.geometry, tr)}</coordinates>'
            f'</LineString></Placemark>' for _, r in cam.iterrows())
        partes.append(carpeta(
            "Todo lo caminado",
            "El recorrido completo, trecho por trecho. Incluye los que son "
            "demasiado cortos para entrar al analisis.", cuerpo))
    partes.append(carpeta(
        "Lo observado (unidades de analisis)",
        "Los trechos que entran al analisis, que son los que se comparan "
        "con un optimo.", lineas(obs, "obs")))
    if mod is not None and len(mod):
        partes.append(carpeta(
            "El optimo del modelo",
            "La ruta de minimo costo entre los mismos dos extremos.",
            lineas(mod, "mod")))

    if par is not None and len(par):
        cuerpo = []
        for _, r in par.iterrows():
            lo, la = tr.transform(r.geometry.x, r.geometry.y)
            minutos = float(r.get("minutos", 0))
            larga = minutos >= 30
            inicio = str(r.get("inicio", ""))
            hora = ""
            if inicio:
                try:
                    t0 = _dt.datetime.fromisoformat(inicio).astimezone(
                        _dt.timezone(_dt.timedelta(hours=-5)))
                    hora = f"{t0:%H:%M} · "
                except ValueError:
                    pass
            nombre = (f'{hora}{minutos:.0f} min · '
                      f'{float(r.get("altitud_m", 0)):.0f} m'
                      if larga else "")
            # Sin HTML: Google Earth web muestra las etiquetas crudas.
            desc = (f'{minutos:.1f} minutos a '
                    f'{float(r.get("altitud_m", 0)):.0f} m. {inicio}')
            cuerpo.append(
                f'<Placemark><name>{escape(nombre)}</name>'
                f'<description>{escape(desc)}</description>'
                f'<styleUrl>#{"parlarga" if larga else "par"}</styleUrl>'
                f'<Point><altitudeMode>clampToGround</altitudeMode>'
                f'<coordinates>{lo:.6f},{la:.6f},0</coordinates>'
                f'</Point></Placemark>')
        partes.append(carpeta(
            "Paradas",
            "Donde se estuvo quieto. Las de media hora o mas, con su hora "
            "y duracion en el nombre.", "".join(cuerpo)))

    if wpt is not None and len(wpt):
        cuerpo = []
        for _, r in wpt.iterrows():
            lo, la = tr.transform(r.geometry.x, r.geometry.y)
            n = str(r["nombre"]).split("_", 1)[-1].replace("_", " ")
            alt = (f'{float(r["altitud_m"]):.0f} m'
                   if r.get("altitud_m") else "")
            cuerpo.append(
                f'<Placemark><name>{escape(n)}</name>'
                f'<description>{escape(alt)}</description>'
                f'<styleUrl>#wpt</styleUrl>'
                f'<Point><altitudeMode>clampToGround</altitudeMode>'
                f'<coordinates>{lo:.6f},{la:.6f},0</coordinates>'
                f'</Point></Placemark>')
        partes.append(carpeta("Waypoints", "Los puntos marcados en el GPS.",
                              "".join(cuerpo)))

    kml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           f'<name>{escape(cfg.raiz.name)}</name>'
           '<description>Lo observado y el optimo del modelo. Abre en '
           'Google Earth web y de escritorio.</description>'
           + "".join(partes) + "</Document></kml>")

    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml)
        for ruta, datos in iconos.items():
            if ruta in usados:
                z.writestr(ruta, datos)
    print(f"  -> {destino.relative_to(cfg.raiz)}")


# --------------------------------------------------------------- informe

def informe(cfg) -> dict:
    import json

    rev = cfg.dir_resultados / "revision_pendiente.gpkg"
    capa = _lee(rev, "revision")
    if capa is None:
        raise SystemExit(
            "No hay resultados/revision_pendiente.gpkg.\n"
            "Este paso cruza lo que ya se calculo; corre antes:\n"
            "    python -m camino revisar")
    obs = capa[capa["clase"] == "observado"].copy()
    mod = capa[capa["clase"] == "modelado"].copy()
    par = _lee(cfg.dir_resultados / "paradas.gpkg", "paradas")
    wpt = _lee_waypoints(cfg)

    # TODO lo caminado, no solo las unidades de analisis.
    #
    # `revisar` trabaja sobre las unidades, que son los trechos que pasan
    # 'largo_min_unidad'. Los mas cortos quedan fuera del analisis -- y esta
    # bien, en 1 km casi cualquier juego de pesos da el mismo camino-- pero
    # NO quedan fuera del recorrido. Sin esta capa, en el mapa aparecen las
    # paradas de la subida a Colque Punku y no la linea por la que se subio:
    # puntos flotando sobre el cerro.
    cam = _lee(cfg.dir_datos / "qn_geocam.gpkg", "camino")
    if cam is not None and "tramnomb" in cam.columns:
        unidades_ = set(obs["unidad"].astype(str))
        cam = cam.copy()
        cam["es_unidad"] = cam["tramnomb"].astype(str).isin(unidades_)
        fuera = int((~cam["es_unidad"]).sum())
        if fuera:
            print(f"  {len(cam)} trechos caminados, de los que {fuera} no "
                  f"llegan a {cfg.largo_min_unidad/1000:.1f} km y no son "
                  "unidad de analisis")
            print("  (se dibujan igual: son recorrido, aunque no se "
                  "modelen)")

    ruta_json = cfg.dir_resultados / "revision_grafo.json"
    filas = (json.loads(ruta_json.read_text(encoding="utf-8"))
             if ruta_json.exists() else [])

    md = [f"# Analisis — {cfg.raiz.name}", ""]

    # ---------------------------------------------- costo contra geometria
    print("\n  --- el costo frente a la geometria ---")
    md += ["## El costo frente a la geometria", ""]
    leidas = costo_contra_geometria(filas)
    if not leidas:
        print("  (sin revision_grafo.json: corre 'revisar')")
    for f in leidas:
        print(f"\n  {f['unidad'][:56]}")
        print(f"    {f['largo_observado_km']:.2f} km observados, "
              f"{f['largo_modelado_km']:.2f} km el optimo")
        print(f"    razon de costo {f['razon_de_costo']:.3f}   "
              f"separacion media {f['distancia_media_m']:.0f} m   "
              f"Frechet {f['frechet_m']:.0f} m")
        for trozo in _parte(f["lectura"], 66):
            print(f"    {trozo}")
        md += [f"**{f['unidad']}** — {f['largo_observado_km']:.2f} km. "
               f"Razon de costo {f['razon_de_costo']:.3f}, separacion media "
               f"{f['distancia_media_m']:.0f} m, Frechet "
               f"{f['frechet_m']:.0f} m.", "", f["lectura"][0].upper()
               + f["lectura"][1:] + ".", ""]

    # ------------------------------------------------- donde se separan
    print("\n  --- donde se separan las dos rutas ---")
    md += ["## Donde se separan las dos rutas", ""]
    sep = []
    for u in obs["unidad"].unique():
        o = obs[obs["unidad"] == u].geometry.iloc[0]
        m_ = mod[mod["unidad"] == u]
        if not len(m_):
            continue
        ss, dd = separacion(o, m_.geometry.iloc[0])
        k = int(np.argmax(dd))
        lejos = float((dd > 250.0).mean())
        print(f"  {u[:44]:46s} max {dd.max():6.0f} m en el km "
              f"{ss[k]/1000:5.2f}   {100*lejos:3.0f}% a mas de 250 m")
        fila = {"unidad": str(u), "max_m": float(dd.max()),
                "km_del_maximo": float(ss[k] / 1000),
                "fraccion_sobre_250m": lejos}
        if wpt is not None and len(wpt):
            from shapely.geometry import Point
            pmax = o.interpolate(float(ss[k]))
            dw = wpt.distance(pmax)
            j = int(dw.idxmin())
            fila["waypoint_mas_cercano"] = str(wpt.loc[j, "nombre"])
            fila["a_m"] = float(dw.loc[j])
            print(f"  {'':46s} lo mas cerca ahi: "
                  f"{fila['waypoint_mas_cercano'][:28]} a {fila['a_m']:.0f} m")
        sep.append(fila)
        md += [f"- **{u}**: se apartan hasta {dd.max():.0f} m, en el km "
               f"{ss[k]/1000:.2f}; el {100*lejos:.0f}% del recorrido va a "
               f"mas de 250 m del optimo."]
    md += [""]

    # --------------------------------------------- paradas y waypoints
    pw = paradas_contra_waypoints(par, wpt)
    if pw:
        print("\n  --- las paradas contra los waypoints ---")
        print(f"  {pw['cerca']} de {pw['n']} paradas caen a menos de 300 m "
              f"de un waypoint")
        print(f"  distancia al mas cercano: mediana {pw['mediana_m']:.0f} m, "
              f"p25 {pw['p25_m']:.0f} m")
        md += ["## Las paradas contra los waypoints", "",
               f"{pw['cerca']} de {pw['n']} paradas caen a menos de 300 m de "
               f"un waypoint marcado; la mediana al mas cercano es "
               f"{pw['mediana_m']:.0f} m.", ""]
        if pw["candidatas"]:
            print(f"\n  PARADAS LARGAS LEJOS DE TODO WAYPOINT "
                  f"({len(pw['candidatas'])}):")
            print(f"  {'min':>6s} {'altitud':>8s}  {'lo mas cerca':28s} "
                  f"{'a':>7s}")
            for f in pw["candidatas"][:12]:
                print(f"  {f['minutos']:6.0f} {f['altitud_m']:8.0f}  "
                      f"{f['waypoint'][:28]:28s} {f['distancia_m']:6.0f} m")
            print("\n  Son lugares donde se estuvo mucho rato y no hay nada")
            print("  marcado. Si el recorrido esta organizado por estaciones,")
            print("  son candidatas, y las ubico el GPS y no la bibliografia.")
            md += [f"**{len(pw['candidatas'])} paradas de media hora o mas "
                   f"estan a mas de 300 m de cualquier waypoint.** Son "
                   f"lugares donde se estuvo mucho rato y no hay nada "
                   f"marcado; si el recorrido esta organizado por "
                   f"estaciones, son candidatas.", ""]
            md += ["| minutos | altitud | lo mas cerca | a |",
                   "| --- | --- | --- | --- |"]
            md += [f"| {f['minutos']:.0f} | {f['altitud_m']:.0f} m | "
                   f"{f['waypoint']} | {f['distancia_m']:.0f} m |"
                   for f in pw["candidatas"][:12]]
            md += [""]

    # ------------------------------------------------------------- luz
    lz = luz(cfg)
    if lz:
        print("\n  --- cuanto se camino de noche ---")
        print(f"  {lz['km_noche']:.1f} km y {lz['horas_noche']:.1f} h a pie "
              f"con el sol bajo -12 grados:")
        print(f"  el {100*lz['fraccion_km']:.0f}% de la distancia y el "
              f"{100*lz['fraccion_horas']:.0f}% del tiempo A PIE.")
        if lz["trazas_en_vehiculo"]:
            print(f"  ({lz['trazas_en_vehiculo']} trazas en vehiculo fuera "
                  "de esta cuenta: ir en camion de")
            print("   noche no dice nada de como se organiza un recorrido a "
                  "pie.)")
        enteros = [f for f in lz["filas"] if f["fraccion_km"] > 0.95]
        if enteros:
            print(f"  Tramos nocturnos de punta a punta: "
                  + ", ".join(f["traza"][-26:] for f in enteros))
        print("\n  Un modelo de costo no puede producir esto: nadie elige la")
        print("  hora mas fria y sin luz para gastar menos energia.")
        md += ["## La luz", "",
               f"{lz['km_noche']:.1f} km y {lz['horas_noche']:.1f} horas con "
               f"el sol por debajo de 12 grados bajo el horizonte: el "
               f"{100*lz['fraccion_km']:.0f}% de la distancia y el "
               f"{100*lz['fraccion_horas']:.0f}% del tiempo a pie.", "",
               "Un modelo de costo no puede producir marcha nocturna: nadie "
               "elige la hora mas fria y sin luz para gastar menos energia.",
               ""]

    # ------------------------------------------------------- las salidas
    print("\n  --- archivos ---")
    figura(cfg, obs, mod, par, wpt, cfg.dir_resultados / "dos_rutas.png",
           cam)
    destino = cfg.dir_resultados / "vista.gpkg"
    if destino.exists():
        destino.unlink()
    obs.drop(columns=["clase"]).to_file(destino, layer="observado",
                                        driver="GPKG")
    if len(mod):
        mod.drop(columns=["clase"]).to_file(destino, layer="optimo",
                                            driver="GPKG")
    if par is not None and len(par):
        par.to_file(destino, layer="paradas", driver="GPKG")
    if wpt is not None and len(wpt):
        wpt.to_file(destino, layer="waypoints", driver="GPKG")
    if cam is not None and len(cam):
        cam.to_file(destino, layer="caminado", driver="GPKG")
    print(f"  -> {destino.relative_to(cfg.raiz)}  (arrastralo a QGIS)")
    kmz(cfg, obs, mod, par, wpt, cfg.dir_resultados / "recorrido.kmz",
        cam)

    ruta_md = cfg.dir_resultados / "analisis.md"
    ruta_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"  -> {ruta_md.relative_to(cfg.raiz)}")

    return {"unidades": leidas, "separacion": sep,
            "paradas_vs_waypoints": pw, "luz": lz}


def _parte(texto, n):
    palabras, filas, actual = texto.split(), [], ""
    for p in palabras:
        if len(actual) + len(p) + 1 > n:
            filas.append(actual)
            actual = p
        else:
            actual = f"{actual} {p}".strip()
    if actual:
        filas.append(actual)
    return filas
