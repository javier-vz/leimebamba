"""Parametros del proyecto, leidos de config.yaml.

Todo numero que se pueda discutir vive aqui y en ningun otro sitio. Si un
umbral aparece escrito en el codigo, es un bug.

La llave de OpenTopography se toma primero de la variable de entorno
OPENTOPOGRAPHY_API_KEY y solo despues del archivo, para que no acabe en el
control de versiones.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib

import yaml

from . import grafo

RAIZ = pathlib.Path(__file__).resolve().parent.parent


@dataclasses.dataclass(frozen=True)
class Config:
    raiz: pathlib.Path

    # extension del estudio
    bbox: tuple[float, float, float, float]   # oeste, sur, este, norte (grados)
    crs: str
    resolucion: float

    # acceso a datos
    api_key: str
    geocam_wfs: str          # endpoint WFS (la via preferida)
    geocam_capa: str         # nombre de la capa dentro del WFS, si ya se sabe
    geocam_servicio: str     # alternativa: capa de ArcGIS REST

    # modelo de costo
    g_max: float
    epsilon: float
    percentiles: tuple[float, float]
    componentes: tuple[str, ...]
    vecindad: int

    # dominio
    buffer_corredor: float
    umbral_quebrada: float

    # barrido e inferencia
    n_simplex: int
    n_sectores: int
    m_nulos: int
    tau_max: float
    semilla: int
    n_trabajos: int

    @classmethod
    def cargar(cls, ruta: str | pathlib.Path | None = None) -> "Config":
        ruta = pathlib.Path(ruta) if ruta else RAIZ / "config.yaml"
        with open(ruta, "r", encoding="utf-8") as f:
            d = yaml.safe_load(f)

        bbox = d["extension"]["bbox"]
        llave = os.environ.get("OPENTOPOGRAPHY_API_KEY") \
            or d["datos"].get("api_key_opentopography") or ""

        return cls(
            raiz=ruta.resolve().parent,
            bbox=(float(bbox["oeste"]), float(bbox["sur"]),
                  float(bbox["este"]), float(bbox["norte"])),
            crs=str(d["extension"]["crs"]),
            resolucion=float(d["extension"]["resolucion"]),
            api_key=str(llave),
            geocam_wfs=str(d["datos"].get("geocam_wfs") or ""),
            geocam_capa=str(d["datos"].get("geocam_capa") or ""),
            geocam_servicio=str(d["datos"].get("geocam_servicio") or ""),
            g_max=float(d["costo"]["g_max"]),
            epsilon=float(d["costo"]["epsilon"]),
            percentiles=tuple(float(v) for v in d["costo"]["percentiles"]),
            componentes=tuple(d["costo"]["componentes"]),
            vecindad=int(d["costo"]["vecindad"]),
            buffer_corredor=float(d["dominio"]["buffer_corredor"]),
            umbral_quebrada=float(d["dominio"]["umbral_quebrada"]),
            n_simplex=int(d["barrido"]["n_simplex"]),
            n_sectores=int(d["barrido"]["n_sectores"]),
            m_nulos=int(d["barrido"]["m_nulos"]),
            tau_max=float(d["barrido"]["tau_max"]),
            semilla=int(d["barrido"]["semilla"]),
            n_trabajos=int(d["barrido"]["n_trabajos"]),
        )

    # ----------------------------------------------------------- derivados

    @property
    def dir_datos(self) -> pathlib.Path:
        return self._dir("datos")

    @property
    def dir_derivados(self) -> pathlib.Path:
        return self._dir("derivados")

    @property
    def dir_resultados(self) -> pathlib.Path:
        return self._dir("resultados")

    def _dir(self, nombre: str) -> pathlib.Path:
        p = self.raiz / nombre
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def vecinos(self):
        if self.vecindad == 16:
            return grafo.VECINOS_16
        if self.vecindad == 8:
            return grafo.VECINOS_8
        raise ValueError("la vecindad tiene que ser 8 o 16")

    @property
    def k(self) -> int:
        """Numero de componentes del costo, incluida la pendiente."""
        return len(self.componentes)

    @property
    def componentes_simetricas(self) -> tuple[str, ...]:
        return tuple(c for c in self.componentes if c != "pendiente")

    def exige_llave(self) -> str:
        if not self.api_key:
            raise SystemExit(
                "Falta la llave de OpenTopography.\n"
                "  1. Entra a https://portal.opentopography.org/ -> My Account\n"
                "  2. Pide una llave (es gratis e inmediata)\n"
                "  3. En la consola de Anaconda:\n"
                "       Windows:  set OPENTOPOGRAPHY_API_KEY=tu_llave\n"
                "       Linux/Mac: export OPENTOPOGRAPHY_API_KEY=tu_llave\n"
                "     o pegala en config.yaml, en datos.api_key_opentopography")
        return self.api_key

    def fuente_geocam(self) -> tuple[str, str]:
        """Por donde bajar el camino: ('wfs', url) o ('rest', url).

        El WFS tiene prioridad: es el estandar OGC que el propio portal
        publica, no una URL interna sacada del trafico del navegador.
        """
        if self.geocam_wfs:
            return "wfs", self.geocam_wfs.split("?")[0].rstrip("/")
        if self.geocam_servicio:
            return "rest", self.geocam_servicio.rstrip("/").removesuffix("/query")
        raise SystemExit(
            "Falta la direccion de GeoCAM. Hay dos vias, de mas a menos comoda:\n"
            "\n"
            "  A) WFS, la estandar. En https://geocam.cultura.gob.pe/ hay una\n"
            "     seccion 'Servicios web' con iconos de WMS, WFS y KML. Haz clic\n"
            "     en el de WFS y copia la direccion que te de (lleva '/wfs' o\n"
            "     'service=WFS' dentro). Pegala en config.yaml, en la linea\n"
            "     'geocam_wfs'. Luego corre:  python -m camino buscar\n"
            "     para que te liste las capas y elija la del camino.\n"
            "\n"
            "  B) ArcGIS REST, si el WFS no responde. Esta en el README,\n"
            "     paso 3, opcion C. Va en la linea 'geocam_servicio'.")

    def exige_geocam(self) -> str:
        """La URL de ArcGIS REST, para el camino alternativo."""
        clase, url = self.fuente_geocam()
        if clase != "rest":
            raise SystemExit("esta configurado el WFS, no el servicio REST")
        return url
