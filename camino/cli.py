"""Linea de comandos: `python -m camino <paso>`.

El orden de los pasos no es decorativo y la ayuda lo dice.
"""

from __future__ import annotations

import argparse
import sys
import time

from . import buscar, config, pipeline, ruta as _ruta

PASOS = {
    "bajar": (pipeline.bajar, "DEM (dos fuentes) y cuerpos de agua"),
    "geocam": (pipeline.geocam, "el camino registrado, del servidor del Ministerio"),
    "preparar": (pipeline.preparar_rasteres, "alinear los DEM y armar la mascara del corredor"),
    "superficies": (pipeline.construir_superficies, "pendiente, rugosidad, drenaje y humedad"),
    "grafo": (pipeline.construir_grafo, "el grafo dirigido y la matriz Phi"),
    "revisar": (pipeline.revisar_grafo, "UN camino, para mirarlo antes de seguir"),
    "nulos": (pipeline.correr_nulos, "el nulo por sector; va ANTES del barrido"),
    "barrido": (pipeline.barrer, "el barrido de pesos sobre el simplex"),
    "resultados": (pipeline.resultados, "el perfil de equifinalidad y su figura"),
}

ORDEN = ("bajar", "geocam", "preparar", "superficies", "grafo", "revisar",
         "nulos", "barrido", "resultados")

# Ayudas que no son parte del pipeline: se corren cuando hacen falta.
AYUDAS = {
    "buscar": (buscar.informe,
               "encuentra la direccion del servicio de GeoCAM y la guarda"),
    "ruta": (None,
             "trae el camino observado: de GeoCAM, de un archivo tuyo o de OSM"),
}

_FORZABLES = {"bajar", "geocam"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m camino",
        description="Optimizacion inversa de pesos de terreno, "
                    "tramo Leimebamba - Chachapoyas.",
        epilog="Pasos en orden: " + " -> ".join(ORDEN)
               + ".  'todo' los corre todos.\n"
               + "Ayuda aparte: 'buscar' encuentra la direccion de GeoCAM "
                 "antes del paso 'geocam'.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paso", choices=(*ORDEN, "todo", *AYUDAS),
                    help="; ".join(f"{k}: {v[1]}"
                                   for k, v in (*PASOS.items(), *AYUDAS.items())))
    ap.add_argument("--config", default=None, help="ruta de config.yaml")
    ap.add_argument("--forzar", action="store_true",
                    help="vuelve a bajar lo que ya esta en disco")
    ap.add_argument("--fuente", choices=_ruta.FUENTES, default="geocam",
                    help="solo con 'ruta': de donde sacar el camino observado")
    ap.add_argument("--archivo", default=None,
                    help="solo con 'ruta --fuente archivo': el .gpx/.kml/.shp")
    args = ap.parse_args(argv)

    cfg = config.Config.cargar(args.config)

    if args.paso == "ruta":
        print(f"=== ruta: trayendo el camino observado desde '{args.fuente}' ===")
        _ruta.importar(cfg, args.fuente, args.archivo, forzar=args.forzar)
        return 0

    if args.paso in AYUDAS:
        fn, texto = AYUDAS[args.paso]
        print(f"=== {args.paso}: {texto} ===")
        fn(cfg)
        return 0

    pasos = ORDEN if args.paso == "todo" else (args.paso,)

    for nombre in pasos:
        fn, texto = PASOS[nombre]
        print(f"\n=== {nombre}: {texto} ===")
        t0 = time.perf_counter()
        if nombre in _FORZABLES:
            fn(cfg, forzar=args.forzar)
        else:
            fn(cfg)
        print(f"    ({time.perf_counter() - t0:.1f} s)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
