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

# Conserva una referencia a la sincronización RPC original. Algunas instancias de
# Supabase tienen habilitada la protección safeupdate y rechazan el DELETE sin
# WHERE de una versión anterior de sql/08. La función resiliente intenta primero
# la RPC y, únicamente ante ese error específico, hace el reemplazo por la API
# usando un DELETE con filtro explícito.
_original_sync_crosswalk = _territorio_base.sync_crosswalk_to_supabase


def _sync_crosswalk_resilient(crosswalk):
    ok, message = _original_sync_crosswalk(crosswalk)
    if ok:
        return ok, message

    if crosswalk is None or getattr(crosswalk, "empty", True):
        return ok, message

    if "DELETE requires a WHERE clause" not in str(message):
        return ok, message

    client = _territorio_base.get_supabase_client()
    if client is None:
        return ok, message

    records = crosswalk.where(crosswalk.notna(), None).to_dict(orient="records")
    try:
        # sistema_codigo es NOT NULL, por lo que != '' cubre todas las filas
        # válidas y satisface el requisito de un WHERE explícito en PostgREST.
        client.table("sistemas_territorios").delete().neq("sistema_codigo", "").execute()
        if records:
            client.table("sistemas_territorios").upsert(records).execute()
    except Exception as exc:
        return False, (
            "El geoproceso funciona en memoria, pero no fue posible persistir "
            "las relaciones territoriales en Supabase. Ejecute "
            "`sql/10_reparar_persistencia_territorial.sql`. Detalle: "
            f"{exc}"
        )

    digest = _territorio_base._crosswalk_hash(crosswalk)
    st.session_state["_territorial_crosswalk_synced"] = digest
    return True, (
        "Relaciones sistema–territorio sincronizadas en Supabase "
        "mediante el mecanismo de contingencia."
    )


_territorio_base.sync_crosswalk_to_supabase = _sync_crosswalk_resilient


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
