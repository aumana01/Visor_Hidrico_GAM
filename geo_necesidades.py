"""Compatibilidad del módulo geoespacial de necesidades.

La implementación histórica se conserva en ``geo_necesidades_legacy.py``.
Esta fachada mantiene la API existente y sustituye únicamente la Vista 3.2
por la versión territorial actualizada.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from geo_necesidades_legacy import *  # noqa: F401,F403
import territorio_necesidades as _territorio_base
import territorio_necesidades_v2 as _territorio
import dta_nombres_extra as _dta


BASE_DIR = Path(__file__).resolve().parent
GEO_DIR = BASE_DIR / "data" / "geoespacial"
DISTRICTS_FILE = GEO_DIR / "distritos.geojson"

# Usar siempre el GeoJSON real cargado al repositorio.
_territorio_base.DISTRICTS_FILE = DISTRICTS_FILE

# Catálogo de nombres administrativos legibles para GAM y sistemas periféricos.
_territorio.province_name = _dta.province_name
_territorio.canton_name = _dta.canton_name
_territorio.district_name = _dta.district_name


def _geodata_signature() -> tuple[tuple[str, int, int], ...]:
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
    signature = _geodata_signature()
    state_key = "_territorial_geodata_signature_v2"
    if st.session_state.get(state_key) == signature:
        return

    for cached_function in (
        getattr(_territorio_base, "load_admin_geojson", None),
        getattr(_territorio_base, "territorial_crosswalk", None),
        getattr(_territorio, "territorial_crosswalk", None),
    ):
        clear_method = getattr(cached_function, "clear", None)
        if callable(clear_method):
            clear_method()

    st.session_state.pop("_territorial_crosswalk_synced", None)
    st.session_state.pop("_territorial_algorithm_version", None)
    st.session_state[state_key] = signature


def vista_mapa_necesidades() -> None:
    _territorio_base.DISTRICTS_FILE = DISTRICTS_FILE
    _clear_territorial_cache_if_needed()
    _territorio.vista_mapa_necesidades_territorial()
