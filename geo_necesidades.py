"""Compatibilidad del módulo geoespacial de necesidades.

La implementación histórica se conserva en ``geo_necesidades_legacy.py``.
Esta fachada mantiene la API existente y sustituye únicamente la Vista 3.2
por la versión con geoproceso territorial automático.
"""

from __future__ import annotations

import base64
import lzma
import tempfile
from pathlib import Path

from geo_necesidades_legacy import *  # noqa: F401,F403
import territorio_necesidades as _territorio


# El GeoJSON suministrado se conserva comprimido en el repositorio para reducir
# el peso del despliegue. Se descomprime de forma temporal al iniciar el proceso.
_packed_districts = (
    Path(__file__).resolve().parent
    / "data"
    / "geoespacial"
    / "distritos.geojson.xz.b64"
)

if _packed_districts.exists():
    try:
        _raw_districts = lzma.decompress(
            base64.b64decode(_packed_districts.read_text(encoding="utf-8").strip())
        )
        _runtime_districts = Path(tempfile.gettempdir()) / "visor_hidrico_distritos.geojson"
        _runtime_districts.write_bytes(_raw_districts)
        _territorio.DISTRICTS_FILE = _runtime_districts
    except Exception:
        # La vista territorial ya posee una ruta de contingencia que conserva
        # la consulta anterior si la capa administrativa no puede cargarse.
        pass


vista_mapa_necesidades = _territorio.vista_mapa_necesidades_territorial
