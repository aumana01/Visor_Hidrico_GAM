from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import streamlit as st

try:
    from supabase import Client, create_client
except Exception:  # pragma: no cover - Supabase is optional for local demo mode.
    Client = None
    create_client = None

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOCAL_DIR = DATA_DIR / "_local_runtime"
LOCAL_DIR.mkdir(exist_ok=True)

TABLE_FILES: dict[str, str] = {
    "proyectos": "proyectos_seed.csv",
    "sistemas_clusters": "sistemas_clusters.csv",
    "capacidad_base": "capacidad_base_seed.csv",
    "necesidades": "necesidades_seed.csv",
    "catalogo_tipos_proyecto": "catalogo_tipos_proyecto.csv",
    "catalogo_beneficios_impactos": "catalogo_beneficios_impactos.csv",
    "catalogo_actividades_criticas": "catalogo_actividades_criticas.csv",
    "catalogo_plazos": "catalogo_plazos.csv",
    "catalogo_situacion_terrenos": "catalogo_situacion_terrenos.csv",
}

ID_TABLES = {"proyectos", "necesidades"}


def _get_secret(name: str, default: str | None = None) -> str | None:
    """Read a value from Streamlit secrets or environment variables."""
    try:
        value = st.secrets.get(name)  # type: ignore[attr-defined]
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)


@st.cache_resource(show_spinner=False)
def get_supabase_client() -> Client | None:
    """Return a Supabase client when credentials exist; otherwise use local CSV mode."""
    url = _get_secret("SUPABASE_URL")
    key = _get_secret("SUPABASE_KEY") or _get_secret("SUPABASE_ANON_KEY")
    if not url or not key or create_client is None:
        return None
    try:
        return create_client(url, key)
    except Exception as exc:
        st.warning(f"No se pudo conectar a Supabase. Se usará modo local CSV. Detalle: {exc}")
        return None


def is_supabase_enabled() -> bool:
    return get_supabase_client() is not None


def _runtime_file(table: str) -> Path:
    return LOCAL_DIR / f"{table}.csv"


def _seed_file(table: str) -> Path:
    return DATA_DIR / TABLE_FILES[table]


def _read_csv(table: str) -> pd.DataFrame:
    runtime = _runtime_file(table)
    source = runtime if runtime.exists() else _seed_file(table)
    if not source.exists():
        return pd.DataFrame()
    return pd.read_csv(source, dtype=str, keep_default_na=False)


def _coerce_known_types(table: str, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    numeric_cols = {
        "id",
        "latitud",
        "longitud",
        "expectativa_caudal_lps",
        "caudal_temporal_lps",
        "poblacion_beneficiada_estimada",
        "anio_efecto",
        "anio",
        "balance_lps",
        "caudal_estimado_lps",
        "volumen_estimado_m3",
        "km_estimado",
    }
    bool_cols = {"activo_en_capacidad", "activo"}
    for col in numeric_cols.intersection(out.columns):
        out[col] = pd.to_numeric(out[col], errors="coerce")
        if col in {"id", "anio", "anio_efecto"}:
            out[col] = out[col].astype("Int64")
    for col in bool_cols.intersection(out.columns):
        out[col] = out[col].map(lambda x: str(x).strip().lower() in {"true", "1", "sí", "si", "yes", "y", "x"})
    return out


@st.cache_data(show_spinner=False)
def read_table(table: str) -> pd.DataFrame:
    """Read a full table from Supabase or local CSV fallback."""
    client = get_supabase_client()
    if client is None:
        return _coerce_known_types(table, _read_csv(table))

    try:
        response = client.table(table).select("*").execute()
        data = response.data or []
        return _coerce_known_types(table, pd.DataFrame(data))
    except Exception as exc:
        st.error(f"Error leyendo la tabla '{table}' en Supabase: {exc}")
        return _coerce_known_types(table, _read_csv(table))


def _clean_value(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if pd.isna(value):
        return None
    return value


def _records_for_supabase(df: pd.DataFrame) -> list[dict[str, Any]]:
    clean = df.copy()
    clean = clean.replace({np.nan: None})
    records: list[dict[str, Any]] = []
    for record in clean.to_dict(orient="records"):
        new_record = {key: _clean_value(value) for key, value in record.items()}
        # Avoid sending empty identity fields to Supabase.
        if "id" in new_record and new_record["id"] in {None, "", 0}:
            new_record.pop("id", None)
        records.append(new_record)
    return records


def clear_cache() -> None:
    read_table.clear()


def reset_local_runtime(tables: Iterable[str] | None = None) -> list[str]:
    """Delete local runtime CSV files so the app falls back to seed data."""
    targets = set(tables or TABLE_FILES.keys())
    deleted: list[str] = []
    for table in targets:
        path = _runtime_file(table)
        if path.exists():
            path.unlink()
            deleted.append(table)
    clear_cache()
    return deleted


def upsert_rows(table: str, df: pd.DataFrame) -> None:
    """Insert/update rows. In local mode the table is rewritten into _local_runtime."""
    if df.empty:
        return
    df = df.copy()
    client = get_supabase_client()
    if client is not None:
        records = _records_for_supabase(df)
        if records:
            client.table(table).upsert(records).execute()
        clear_cache()
        return

    current = _coerce_known_types(table, _read_csv(table))
    if table in ID_TABLES:
        if "id" not in df.columns:
            df.insert(0, "id", pd.NA)
        max_id = int(pd.to_numeric(current.get("id", pd.Series(dtype=float)), errors="coerce").max() or 0)
        for idx in df.index:
            if pd.isna(df.at[idx, "id"]) or str(df.at[idx, "id"]).strip() in {"", "0"}:
                max_id += 1
                df.at[idx, "id"] = max_id
    if not current.empty and "id" in current.columns and "id" in df.columns:
        current = current[~current["id"].astype(str).isin(df["id"].astype(str))]
        combined = pd.concat([current, df], ignore_index=True)
    else:
        combined = pd.concat([current, df], ignore_index=True) if not current.empty else df
    combined.to_csv(_runtime_file(table), index=False, encoding="utf-8-sig")
    clear_cache()


def delete_rows(table: str, ids: Iterable[Any]) -> None:
    ids_list = [int(x) for x in ids if str(x).strip()]
    if not ids_list:
        return
    client = get_supabase_client()
    if client is not None:
        client.table(table).delete().in_("id", ids_list).execute()
        clear_cache()
        return
    current = _coerce_known_types(table, _read_csv(table))
    if "id" in current.columns:
        current = current[~current["id"].astype(int).isin(ids_list)]
        current.to_csv(_runtime_file(table), index=False, encoding="utf-8-sig")
    clear_cache()


def seed_supabase(overwrite: bool = False) -> dict[str, int]:
    """Load CSV seed data into Supabase. Use overwrite=True only for controlled resets."""
    client = get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase no está configurado.")

    inserted: dict[str, int] = {}
    ordered_tables = [
        "sistemas_clusters",
        "capacidad_base",
        "catalogo_tipos_proyecto",
        "catalogo_beneficios_impactos",
        "catalogo_actividades_criticas",
        "catalogo_plazos",
        "catalogo_situacion_terrenos",
        "proyectos",
        "necesidades",
    ]
    for table in ordered_tables:
        df = _coerce_known_types(table, _read_csv(table))
        if df.empty:
            inserted[table] = 0
            continue
        if overwrite:
            client.table(table).delete().neq("id", -1).execute() if "id" in df.columns else client.table(table).delete().neq(list(df.columns)[0], "__never__").execute()
        records = _records_for_supabase(df)
        for start in range(0, len(records), 500):
            client.table(table).upsert(records[start:start + 500]).execute()
        inserted[table] = len(records)
    clear_cache()
    return inserted
