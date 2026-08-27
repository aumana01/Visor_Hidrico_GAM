"""Compatibilidad del módulo geoespacial de necesidades.

La implementación histórica se conserva en ``geo_necesidades_legacy.py``.
Esta fachada mantiene la API existente y sustituye únicamente la Vista 3.2
por la versión con geoproceso territorial automático.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from geo_necesidades_legacy import *  # noqa: F401,F403
import territorio_necesidades as _territorio


BASE_DIR = Path(__file__).resolve().parent
GEO_DIR = BASE_DIR / "data" / "geoespacial"
DISTRICTS_FILE = GEO_DIR / "distritos.geojson"

# Usar siempre el GeoJSON real cargado al repositorio.
# La versión comprimida temporal ya no se usa.
_territorio.DISTRICTS_FILE = DISTRICTS_FILE


def _geodata_signature() -> tuple[tuple[str, int, int], ...]:
    """Firma de los insumos geoespaciales para invalidar caché si cambian."""
    paths = [DISTRICTS_FILE, *sorted(GEO_DIR.glob("sistemas_*.json"))]
    signature: list[tuple[str, int, int]] = []
    for path in paths:
        if not path.exists():
            signature.append((path.name, -1, -1))
            continue
        stat = path.stat()
        signature.append((path.name, int(stat.st_size), int(stat.st_mtime_ns)))
    return tuple(signature)


def _clear_territorial_cache_if_needed() -> None:
    """Evita conservar un cruce vacío calculado antes de subir distritos.geojson."""
    signature = _geodata_signature()
    state_key = "_territorial_geodata_signature"
    if st.session_state.get(state_key) == signature:
        return

    for cached_function_name in ("load_admin_geojson", "territorial_crosswalk"):
        cached_function = getattr(_territorio, cached_function_name, None)
        clear_method = getattr(cached_function, "clear", None)
        if callable(clear_method):
            clear_method()

    # Fuerza una nueva sincronización a Supabase cuando cambian los insumos.
    st.session_state.pop("_territorial_crosswalk_synced", None)
    st.session_state[state_key] = signature


def vista_mapa_necesidades() -> None:
    _territorio.DISTRICTS_FILE = DISTRICTS_FILE
    _clear_territorial_cache_if_needed()
    _territorio.vista_mapa_necesidades_territorial()
