from __future__ import annotations

import base64
import html
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

import fitz
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client

from database import delete_rows, is_supabase_enabled, read_table, reset_local_runtime, seed_supabase, upsert_rows

AYA_AZUL = "#002B5C"
AYA_DORADO = "#C9A227"
AYA_GRIS = "#F5F7FA"
PDF_BUCKET = "lecciones-aprendidas"
PDF_FOLDER = "pdfs"
YEARS = list(range(2024, 2041))
ANALYSIS_YEARS = list(range(2025, 2041))

CLUSTER_SYSTEMS = {
    "CLUSTER C-1": [
        "ME-A-01 Tres Rios", "ME-A-02 Guadalupe", "ME-A-04 Los Sitios", "ME-A-08 Los Cuadros",
        "ME-A-10 Mata de Plátano", "ME-A-13 San Jeronimo de Moravia", "ME-A-20 Padre Carazo",
        "ME-A-22 Pizote", "ME-A-28 Vista de Mar",
    ],
    "CLUSTER C-2": ["ME-A-15 San Pablo", "ME-A-17 La Valencia"],
    "CLUSTER C-3": [
        "ME-A-03 El Llano", "ME-A-06 San Juan de Dios", "ME-A-07 San Antonio de Escazu",
        "ME-A-09 Alajuelita", "ME-A-16 Potrerillos-San Antonio", "ME-A-23 Barrio Espana",
        "ME-A-25 Sur de Escazu", "ME-A-19 Puente Mulas",
    ],
    "CLUSTER C-4": ["ME-A-14 San Rafael de Coronado", "ME-A-21 Chiverrales"],
    "CLUSTER C-5": ["ME-A-12 Quitirrisi (Ciudad Colon)", "ME-A-26 Ticufres-Quebrada Honda", "ME-A-31 Puriscal"],
    "CLUSTER C-6": [
        "ME-A-05 Salitral", "ME-A-11 Guatuso Patarra", "ME-A-18 Sur Alajuelita",
        "ME-A-24 Matinilla", "ME-A-27 El Guarco", "ME-A-29 Lajas", "ME-A-30 Jerico",
    ],
}
CLUSTER_REPRESENTATIVO = {
    "CLUSTER C-1": "Tres Ríos, Guadalupe y Los Sitios",
    "CLUSTER C-2": "La Valencia y San Pablo",
    "CLUSTER C-3": "Puente Mulas, Potrerillos y San Juan de Dios",
    "CLUSTER C-4": "San Rafael de Coronado",
    "CLUSTER C-5": "Puriscal",
    "CLUSTER C-6": "Guarco",
}
SYSTEM_TO_CLUSTER = {sistema: cluster for cluster, sistemas in CLUSTER_SYSTEMS.items() for sistema in sistemas}
CODE_TO_CLUSTER = {sistema.split()[0].replace("ME-A-", "MEA"): cluster for cluster, sistemas in CLUSTER_SYSTEMS.items() for sistema in sistemas}
CLUSTER_DISPLAY = {cluster: "Cluster " + cluster.split("-")[-1] for cluster in CLUSTER_SYSTEMS}

ACCION_OPTIONS = ["Inmediato", "Corto plazo", "Mediano plazo", "Largo plazo", "Por definir"]
TIPO_INCORPORACION_OPTIONS = ["Temporal", "Definitiva", "Temporal / definitiva", "No aplica", "Por definir"]
ESTADO_INICIATIVA_OPTIONS = [
    "Incorporado",
    "Proyecto en ejecución",
    "Proyecto en ejecución (Incorporado temporal)",
    "En análisis de ofertas",
    "En diseño",
    "En formulación",
    "Suspendido",
    "Ejecutado",
    "Nuevo registro",
    "Por definir",
]
ESTUDIO_OPTIONS = ["Sí", "No", "En proceso", "Adquirido", "Adquiridos", "No aplica", "Por definir"]
ATENCION_NECESIDAD_OPTIONS = ["", "Lo puede atender el GAM", "Se requiere apoyo de otras dependencias","Ambos"]

NECESIDAD_VISIBLE_COLS = [
    "objetivo_de_la_iniciativa",
    "breve_descripcion",
    "tipo_de_proyecto",
    "codigo_de_sistema",
    "sistema_de_abastecimiento",
    "principal_reto_por_superar",
    "observacion",
    "caudal_estimado_lps",
    "volumen_estimado_m3",
    "km_estimado",
    "responsabilidad_atencion",
]

NECESIDAD_LABELS = {
    "objetivo_de_la_iniciativa": "Objetivo de la iniciativa",
    "breve_descripcion": "Breve descripción",
    "tipo_de_proyecto": "tipo_de_proyecto",
    "codigo_de_sistema": "Código de Sistema",
    "sistema_de_abastecimiento": "Sistema de Abastecimiento",
    "principal_reto_por_superar": "Principal reto por superar",
    "observacion": "Observación",
    "caudal_estimado_lps": "Caudal estimado que aporta la iniciativa (L/s)",
    "volumen_estimado_m3": "Volumen estimado que aporta la iniciativa (m³)",
    "km_estimado": "Km estimados que aporta la iniciativa (km)",
    "responsabilidad_atencion": "Clasificación de atención",
}

st.set_page_config(
    page_title="GAM Hídrico | Proyectos y Necesidades",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
    <style>
    .main .block-container {{padding-top: 1.2rem;}}
    .aya-title {{
        background: linear-gradient(90deg, {AYA_AZUL}, #0B4B8C);
        color: white;
        padding: 1.1rem 1.3rem;
        border-radius: 16px;
        border-left: 8px solid {AYA_DORADO};
        margin-bottom: 1rem;
    }}
    .aya-title h1 {{margin: 0; font-size: 1.7rem;}}
    .aya-title p {{margin: .25rem 0 0 0; opacity: .9;}}
    div[data-testid="stMetric"] {{
        background-color: white;
        border: 1px solid #E7EAF0;
        padding: 0.8rem;
        border-radius: 14px;
        box-shadow: 0 1px 3px rgba(0,0,0,.04);
    }}
    .section-card {{
        background: {AYA_GRIS};
        border: 1px solid #E8EDF5;
        padding: 1rem;
        border-radius: 16px;
    }}
    .aya-card {{
        background: white;
        border: 1px solid #E7EAF0;
        border-left: 6px solid {AYA_DORADO};
        padding: .95rem 1rem;
        border-radius: 16px;
        margin-bottom: .8rem;
        box-shadow: 0 2px 6px rgba(0,0,0,.06);
        min-height: 178px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


def title() -> None:
    st.markdown(
        """
        <div class="aya-title">
            <h1>UEN Optimización de Sistemas GAM</h1>
            <h1>Gestión de proyectos, capacidad hídrica y necesidades GAM</h1>
            <p>Herramienta para análisis ejecutivo, edición y trazabilidad institucional de proyectos PRAGAM e Iniciativas.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def clean_options(values: Iterable[object], extra: Iterable[str] | None = None, include_blank: bool = False) -> list[str]:
    out: list[str] = []
    if include_blank:
        out.append("")
    if extra is not None:
        for value in extra:
            value = str(value).strip()
            if value and value not in out:
                out.append(value)
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "<na>"} and text not in out:
            out.append(text)
    return out


def parse_options(series: pd.Series) -> list[str]:
    values: set[str] = set()
    for raw in series.dropna().astype(str):
        for part in re.split(r"[;/|,]", raw):
            part = part.strip()
            if part and part.lower() not in {"nan", "none", "<na>"}:
                values.add(part)
    return sorted(values)


def split_multi(value: object) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [part.strip() for part in re.split(r"[;/|]", str(value)) if part.strip()]


def join_multi(values: Iterable[str]) -> str:
    return "; ".join([str(v).strip() for v in values if str(v).strip()])


def option_index(options: list[str], current: object, default: int = 0) -> int:
    text = "" if current is None or pd.isna(current) else str(current).strip()
    if text and text not in options:
        options.append(text)
    if text in options:
        return options.index(text)
    return default if options else 0


def format_lps(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.1f} L/s".replace(",", " ")






def add_bar_labels(fig, orientation: str = "v"):
    """Apply data labels to Plotly bar charts in a consistent executive format."""
    if orientation == "h":
        fig.update_traces(texttemplate="%{x:.2f}", textposition="outside", cliponaxis=False)
    else:
        fig.update_traces(texttemplate="%{y:.2f}", textposition="outside", cliponaxis=False)
    fig.update_layout(uniformtext_minsize=8, uniformtext_mode="hide", margin=dict(r=30))
    return fig


def add_count_labels(fig, orientation: str = "v"):
    if orientation == "h":
        fig.update_traces(texttemplate="%{x:.0f}", textposition="outside", cliponaxis=False)
    else:
        fig.update_traces(texttemplate="%{y:.0f}", textposition="outside", cliponaxis=False)
    fig.update_layout(uniformtext_minsize=8, uniformtext_mode="hide", margin=dict(r=30))
    return fig


def extract_expected_flow(row: pd.Series) -> float:
    """Flow used for analytical capacity impact: expected / definitive flow only."""
    exp = pd.to_numeric(row.get("expectativa_caudal_lps"), errors="coerce")
    if pd.notna(exp) and exp > 0:
        return float(exp)
    return 0.0


def extract_effect_year(row: pd.Series) -> int | None:
    """Resolve the year when a project starts to affect the cluster summary."""
    anio = pd.to_numeric(row.get("anio_efecto"), errors="coerce")
    if pd.notna(anio) and 2024 <= int(anio) <= 2040:
        return int(anio)
    text = str(row.get("anio_incorporacion_texto", ""))
    matches = re.findall(r"20\d{2}", text)
    for item in matches:
        year = int(item)
        if 2024 <= year <= 2040:
            return year
    return None


def safe_float(value: object, default: float = 0.0) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return default
    return float(numeric)




def parse_coordinate(value: object, coord_type: str) -> float | None:
    '''Parse lat/long values coming from Excel/PDF-style tables.'''
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    text = text.replace("−", "-").replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    if text.count(".") > 1:
        first, rest = text.split(".", 1)
        text = first + "." + rest.replace(".", "")
    try:
        number = float(text)
    except Exception:
        return None
    if coord_type == "lon" and 82 <= number <= 86:
        number = -number
    if coord_type == "lat" and 8 <= number <= 12:
        return number
    if coord_type == "lon" and -86 <= number <= -82:
        return number
    return None

def extract_project_flow(row: pd.Series) -> float:
    temp = pd.to_numeric(row.get("caudal_temporal_lps"), errors="coerce")
    exp = pd.to_numeric(row.get("expectativa_caudal_lps"), errors="coerce")
    if pd.notna(temp) and temp > 0:
        return float(temp)
    if pd.notna(exp) and exp > 0:
        return float(exp)
    return 0.0


def ensure_columns(df: pd.DataFrame, columns: Iterable[str], default: object = "") -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = default
    return out


def apply_filters(df: pd.DataFrame, key_prefix: str, filter_columns: list[str]) -> pd.DataFrame:
    filtered = df.copy()
    with st.expander("Filtros", expanded=True):
        cols = st.columns(min(4, max(1, len(filter_columns))))
        for i, col in enumerate(filter_columns):
            if col not in df.columns:
                continue
            options = sorted([x for x in df[col].dropna().astype(str).unique() if x.strip()])
            selected = cols[i % len(cols)].multiselect(col.replace("_", " ").title(), options, key=f"{key_prefix}_{col}")
            if selected:
                filtered = filtered[filtered[col].astype(str).isin(selected)]
    return filtered


def styled_balance(df: pd.DataFrame):
    def color(v):
        try:
            value = float(v)
        except Exception:
            return ""
        if value < 0:
            return "background-color:#FDECEC;color:#B00020;font-weight:600;"
        return "background-color:#EAF7ED;color:#0B6B2A;font-weight:600;"

    numeric_cols = [
        c
        for c in df.columns
        if str(c).isdigit()
        or c in {"balance_lps", "balance_base_lps", "balance_con_mejoras_lps", "efecto_proyectos_lps"}
    ]
    styler = df.style
    # Pandas 2.1+ usa Styler.map; versiones anteriores usaban applymap.
    if hasattr(styler, "map"):
        return styler.map(color, subset=numeric_cols)
    return styler.applymap(color, subset=numeric_cols)


def save_edited_rows(table: str, edited: pd.DataFrame, success_message: str) -> None:
    if edited.empty:
        st.info("No hay registros para guardar.")
        return
    upsert_rows(table, edited)
    st.success(success_message)
    st.rerun()


def system_maps(sistemas: pd.DataFrame) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    if sistemas.empty:
        return {}, {}, {}, {}
    sistemas = ensure_columns(sistemas, ["sistema_nombre", "sistema_codigo", "cluster", "sistema_codigo_formal"])
    by_name_code = dict(zip(sistemas["sistema_nombre"].astype(str), sistemas["sistema_codigo"].astype(str)))
    by_name_cluster = dict(zip(sistemas["sistema_nombre"].astype(str), sistemas["cluster"].astype(str)))
    by_code_name = dict(zip(sistemas["sistema_codigo"].astype(str), sistemas["sistema_nombre"].astype(str)))
    by_code_cluster = dict(zip(sistemas["sistema_codigo"].astype(str), sistemas["cluster"].astype(str)))
    return by_name_code, by_name_cluster, by_code_name, by_code_cluster




def canonical_cluster_from_system_or_code(system_name: object = None, system_code: object = None, current: object = "") -> str:
    name = "" if system_name is None or pd.isna(system_name) else str(system_name).strip()
    code = "" if system_code is None or pd.isna(system_code) else str(system_code).strip()
    if name in SYSTEM_TO_CLUSTER:
        return SYSTEM_TO_CLUSTER[name]
    if code in CODE_TO_CLUSTER:
        return CODE_TO_CLUSTER[code]
    text = "" if current is None or pd.isna(current) else str(current).strip()
    if "NO INTER" in text.upper():
        return "CLUSTER C-6"
    return text


def apply_canonical_clusters(df: pd.DataFrame, system_col: str = "sistema_nombre", code_col: str = "sistema_codigo", cluster_col: str = "cluster") -> pd.DataFrame:
    out = df.copy()
    if cluster_col not in out.columns:
        out[cluster_col] = ""
    if system_col not in out.columns:
        out[system_col] = ""
    if code_col not in out.columns:
        out[code_col] = ""
    out[cluster_col] = out.apply(lambda r: canonical_cluster_from_system_or_code(r.get(system_col), r.get(code_col), r.get(cluster_col)), axis=1)
    return out


def cluster_systems_text(cluster: object) -> str:
    raw = canonical_cluster_from_system_or_code(current=cluster)
    sistemas = CLUSTER_SYSTEMS.get(raw, [])
    return "; ".join(sistemas)


def cluster_representative(cluster: object) -> str:
    raw = canonical_cluster_from_system_or_code(current=cluster)
    return CLUSTER_REPRESENTATIVO.get(raw, "")


def normalize_import_columns(df: pd.DataFrame, target: str) -> pd.DataFrame:
    """Normalize XLSX column names from Spanish headers into app/internal columns."""
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]

    def norm(text: str) -> str:
        text = text.strip().lower()
        trans = str.maketrans("áéíóúüñ°º³", "aeiouunoo3")
        text = text.translate(trans)
        text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
        return text

    if target == "proyectos":
        mapping = {
            "accion": "accion",
            "n_bpip": "bpip", "no_bpip": "bpip", "bpip": "bpip",
            "proyecto": "proyecto",
            "descripcion": "descripcion",
            "latitud": "latitud", "longitud": "longitud",
            "estado_de_la_iniciativa": "estado_iniciativa", "estado_iniciativa": "estado_iniciativa",
            "inicio_de_perforacion": "inicio_perforacion", "fin_de_perforacion": "fin_perforacion",
            "tipo_de_incorporacion": "tipo_incorporacion", "tipo_incorporacion": "tipo_incorporacion",
            "expectativa_de_caudal_l_s": "expectativa_caudal_lps", "expectativa_caudal_lps": "expectativa_caudal_lps",
            "caudal_incorporado_temporal_l_s": "caudal_temporal_lps", "caudal_temporal_lps": "caudal_temporal_lps",
            "poblacion_beneficiada_estimada": "poblacion_beneficiada_estimada",
            "estimacion_de_ano_de_incorporacion": "anio_incorporacion_texto", "ano_efecto": "anio_efecto", "anio_efecto": "anio_efecto",
            "codigo_de_sistema": "sistema_codigo", "codigo_sistema": "sistema_codigo", "cod": "sistema_codigo",
            "sistema_de_abastecimiento_beneficiado": "sistema_nombre", "sistema_nombre": "sistema_nombre", "sistema": "sistema_nombre",
            "cluster_de_sistemas_de_abastecimiento_beneficiados": "cluster", "cluster": "cluster",
            "beneficios": "beneficios", "impacto": "impacto",
            "actividades_criticas_para_su_avance": "actividades_criticas", "actividades_criticas": "actividades_criticas",
            "dependencia_responsable": "dependencia_responsable",
            "cuenta_con_estudio_hidrogeologico": "estudio_hidrogeologico", "estudio_hidrogeologico": "estudio_hidrogeologico",
            "situacion_de_terrenos": "situacion_terrenos", "situacion_terrenos": "situacion_terrenos",
            "observaciones_comentarios": "observaciones", "observacion": "observaciones", "observaciones": "observaciones",
        }
    else:
        mapping = {
            "objetivo_de_la_iniciativa": "objetivo_de_la_iniciativa", "objetivo": "objetivo_de_la_iniciativa",
            "breve_descripcion": "breve_descripcion", "descripcion": "breve_descripcion",
            "tipo_de_proyecto": "tipo_de_proyecto",
            "codigo_de_sistema": "codigo_de_sistema", "codigo_sistema": "codigo_de_sistema", "cod": "codigo_de_sistema",
            "sistema_de_abastecimiento": "sistema_de_abastecimiento", "sistema": "sistema_de_abastecimiento",
            "principal_reto_por_superar": "principal_reto_por_superar", "principal_reto": "principal_reto_por_superar",
            "observacion": "observacion", "observaciones": "observacion",
            "clasificacion_de_atencion": "responsabilidad_atencion", "responsabilidad_atencion": "responsabilidad_atencion",
            "caudal_estimado_que_aporta_la_iniciativa_l_s": "caudal_estimado_lps", "caudal_estimado_l_s": "caudal_estimado_lps", "caudal_estimado_lps": "caudal_estimado_lps",
            "volumen_estimado_que_aporta_la_iniciativa_m3": "volumen_estimado_m3", "volumen_estimado_m3": "volumen_estimado_m3",
            "km_estimado_que_aporta_la_iniciativa_km": "km_estimado", "km_estimado": "km_estimado",
        }
    rename = {col: mapping.get(norm(col), col) for col in out.columns}
    out = out.rename(columns=rename)
    for col in ["id"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    return out


def xlsx_importer(table: str, target: str, sistemas: pd.DataFrame, key: str) -> None:
    """Reusable XLSX import widget for projects/needs."""
    with st.expander("Importación masiva desde Excel (.xlsx)", expanded=False):
        st.caption("Puede cargar un archivo Excel con encabezados similares a los de la tabla. Si incluye ID se actualiza; si no incluye ID se agregan registros nuevos.")
        uploaded = st.file_uploader("Archivo Excel", type=["xlsx"], key=f"{key}_xlsx")
        if uploaded is None:
            return
        try:
            xls = pd.ExcelFile(uploaded)
            sheet = st.selectbox("Hoja a importar", xls.sheet_names, key=f"{key}_sheet")
            imported = xls.parse(sheet)
            imported = normalize_import_columns(imported, target)
            if target == "proyectos":
                imported = ensure_columns(imported, [
                    "accion", "bpip", "proyecto", "descripcion", "latitud", "longitud", "estado_iniciativa",
                    "inicio_perforacion", "fin_perforacion", "tipo_incorporacion", "expectativa_caudal_lps",
                    "caudal_temporal_lps", "poblacion_beneficiada_estimada", "anio_incorporacion_texto", "anio_efecto",
                    "sistema_codigo", "sistema_nombre", "cluster", "beneficios", "impacto", "actividades_criticas",
                    "dependencia_responsable", "estudio_hidrogeologico", "situacion_terrenos", "observaciones",
                ])
                imported = apply_canonical_clusters(imported, "sistema_nombre", "sistema_codigo", "cluster")
            else:
                imported = ensure_columns(imported, ["id", *NECESIDAD_VISIBLE_COLS, "activo"])
                imported = normalize_need_rows(imported, sistemas)
                imported["activo"] = imported.get("activo", True)
            st.write("Vista previa de importación")
            st.dataframe(imported.head(20), use_container_width=True, hide_index=True)
            if st.button(f"Importar {len(imported)} registros", type="primary", key=f"{key}_import_btn"):
                upsert_rows(table, imported)
                st.success(f"Se importaron/actualizaron {len(imported)} registros en {table}.")
                st.rerun()
        except Exception as exc:
            st.error(f"No se pudo leer el Excel: {exc}")

def normalize_project_rows(df: pd.DataFrame, sistemas: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    by_name_code, by_name_cluster, _, _ = system_maps(sistemas)
    if "sistema_nombre" in out.columns:
        names = out["sistema_nombre"].astype(str)
        if "sistema_codigo" in out.columns:
            mapped_code = names.map(by_name_code)
            out.loc[mapped_code.notna(), "sistema_codigo"] = mapped_code[mapped_code.notna()]
        if "cluster" in out.columns:
            mapped_cluster = names.map(by_name_cluster)
            out.loc[mapped_cluster.notna(), "cluster"] = mapped_cluster[mapped_cluster.notna()]
    out = apply_canonical_clusters(out, "sistema_nombre", "sistema_codigo", "cluster")
    return out


def read_catalogo_actividades_local() -> pd.DataFrame:
    """
    Lee el catálogo de actividades críticas desde el CSV del repositorio.

    Esto permite que la app use la columna concatenada:
    Traba_Riesgo_Concatenado

    Aunque la app esté conectada a Supabase, este catálogo se toma del archivo:
    data/catalogo_actividades_criticas.csv
    """
    path = Path(__file__).resolve().parent / "data" / "catalogo_actividades_criticas.csv"

    if path.exists():
        return pd.read_csv(path, dtype=str, keep_default_na=False)

    return read_table("catalogo_actividades_criticas")


def get_actividades_criticas_options(catalogo_act: pd.DataFrame) -> list[str]:
    """
    Devuelve las opciones del desplegable de actividades críticas.

    Prioriza la columna concatenada:
    Traba_Riesgo_Concatenado
    """
    if catalogo_act.empty:
        return []

    # Normaliza nombres por si vienen con espacios.
    catalogo_act = catalogo_act.copy()
    catalogo_act.columns = [str(c).strip() for c in catalogo_act.columns]

    preferred_cols = [
        "Traba_Riesgo_Concatenado",
        "traba_riesgo_concatenado",
        "Traba / Riesgo Concatenado",
        "Traba_Riesgo",
        "Actividad_Concatenada",
    ]

    for col in preferred_cols:
        if col in catalogo_act.columns:
            return clean_options(catalogo_act[col], include_blank=False)

    # Si no encuentra el nombre exacto, busca cualquier columna que tenga "concat".
    for col in catalogo_act.columns:
        if "concat" in str(col).lower():
            return clean_options(catalogo_act[col], include_blank=False)

    # Respaldo: usa la segunda columna del catálogo.
    if catalogo_act.shape[1] >= 2:
        return clean_options(catalogo_act.iloc[:, 1], include_blank=False)

    # Último respaldo: usa la primera columna.
    return clean_options(catalogo_act.iloc[:, 0], include_blank=False)


def vista_proyectos() -> None:
    st.subheader("Vista 1 · Gestión de proyectos")
    proyectos = read_table("proyectos")
    sistemas = read_table("sistemas_clusters")
    catalogo_bi = read_table("catalogo_beneficios_impactos")
    catalogo_act = read_catalogo_actividades_local()
    catalogo_terrenos = read_table("catalogo_situacion_terrenos")

    if proyectos.empty:
        st.warning("No hay proyectos cargados.")
        return

    proyectos = ensure_columns(
        proyectos,
        [
            "id",
            "accion",
            "bpip",
            "proyecto",
            "descripcion",
            "latitud",
            "longitud",
            "estado_iniciativa",
            "inicio_perforacion",
            "fin_perforacion",
            "tipo_incorporacion",
            "expectativa_caudal_lps",
            "caudal_temporal_lps",
            "poblacion_beneficiada_estimada",
            "anio_incorporacion_texto",
            "anio_efecto",
            "sistema_codigo",
            "sistema_nombre",
            "cluster",
            "beneficios",
            "impacto",
            "actividades_criticas",
            "dependencia_responsable",
            "estudio_hidrogeologico",
            "situacion_terrenos",
            "activo_en_capacidad",
            "observaciones",
        ],
    )
    proyectos = normalize_project_rows(proyectos, sistemas)

    sistema_options = clean_options(sistemas.get("sistema_nombre", pd.Series(dtype=str)), proyectos.get("sistema_nombre", pd.Series(dtype=str)), include_blank=True)
    sistema_codigo_options = clean_options(sistemas.get("sistema_codigo", pd.Series(dtype=str)), proyectos.get("sistema_codigo", pd.Series(dtype=str)), include_blank=True)
    cluster_options = clean_options(sistemas.get("cluster", pd.Series(dtype=str)), proyectos.get("cluster", pd.Series(dtype=str)), include_blank=True)
    dependencia_options = clean_options(
        proyectos.get("dependencia_responsable", pd.Series(dtype=str)),
        [
            "Planificación",
            "Auditoría",
            "Jurídica",
            "Cooperación y Asuntos Internacionales",
            "Laboratorio Nacional de Aguas",
            "Gestión Tarifaria",
            "Comunicación Institucional",
            "Asesor o apoyo Presidencia",
            "UTSAPS",
            "Programa Agua Potable y Saneamiento (PAPS)",
            "Asesor o apoyo Gerencia o Subgerencia",
            "Contraloría de Servicios",
            "Igualdad de Género e Interculturalidad",
            "Salud Ocupacional",
            "UEN Investigación y Desarrollo",
            "UEN Programación y Control",
            "UEN Administración de Proyectos",
            "UEN Gestión Ambiental",
            "Asesor o Apoyo Subgerencia",
            "Recolección y Tratamiento GAM",
            "UEN Producción y Distribución",
            "UEN Optimización de Sistemas",
            "UEN Servicio al Cliente",
            "Región Brunca",
            "Región Central Oeste",
            "Región Chorotega",
            "Región Huétar Caribe",
            "Región Pacífico Central",
            "UEN Recolección y Tratamiento",
            "UEN Gestión de Acueductos Rurales",
            "Otra",
            "Programas y proyectos",
            "Preinversión y Construcción",
            "Ampliación Acueducto Metropolitano",
            "RANC-EE",
            "Finanzas",
            "Centro de Servicios de Apoyo",
            "Sistemas de Información",
            "Proveeduría",
            "Gestión Capital Humano",
            "Por definir",
        ],
    )
    terrenos_options = clean_options(
    catalogo_terrenos.iloc[:, 0] if not catalogo_terrenos.empty else pd.Series(dtype=str),
    proyectos.get("situacion_terrenos", pd.Series(dtype=str)),
    include_blank=True,
)

beneficios_options = clean_options(
    catalogo_bi.get("Beneficios", pd.Series(dtype=str)),
    parse_options(proyectos.get("beneficios", pd.Series(dtype=str))),
)

impactos_options = clean_options(
    catalogo_bi.get("Impacto", pd.Series(dtype=str)),
    parse_options(proyectos.get("impacto", pd.Series(dtype=str))),
)

actividades_options = get_actividades_criticas_options(catalogo_act)

    st.markdown(
        """
        **Definiciones de uso:** un **proyecto** es una iniciativa u obra con capacidad de generar beneficio operativo, hidráulico o de gestión.
        El **caudal esperado** corresponde al caudal de diseño o aporte esperado de la iniciativa y es el valor utilizado en la Vista 2 para el resumen por cluster.
        El **caudal temporal** representa una condición provisional o transitoria de operación; se conserva para trazabilidad, pero no afecta el balance hídrico de la Vista 2.
        """
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Proyectos", f"{len(proyectos):,}")
    c2.metric("Caudal temporal", format_lps(pd.to_numeric(proyectos.get("caudal_temporal_lps"), errors="coerce").sum()))
    c3.metric("Caudal esperado", format_lps(pd.to_numeric(proyectos.get("expectativa_caudal_lps"), errors="coerce").sum()))
    c4.metric("Clusters", proyectos.get("cluster", pd.Series(dtype=str)).nunique())

    tab_graficos, tab_mapa, tab_lista, tab_detalle, tab_nuevo = st.tabs(["Gráficos", "Mapa", "Lista editable", "Editar detalle", "Agregar proyecto"])

    with tab_lista:
        xlsx_importer("proyectos", "proyectos", sistemas, "proyectos")
        filtered = apply_filters(proyectos, "proy", ["cluster", "sistema_nombre", "accion", "estado_iniciativa", "tipo_incorporacion"])
        choice_cols = [
            "accion", "estado_iniciativa", "tipo_incorporacion", "sistema_nombre", "sistema_codigo",
            "cluster", "beneficios", "impacto", "actividades_criticas", "dependencia_responsable",
            "estudio_hidrogeologico", "situacion_terrenos",
        ]
        for choice_col in choice_cols:
            if choice_col in filtered.columns:
                filtered[choice_col] = filtered[choice_col].fillna("").astype(str)
        project_editor_columns = [
            "id", "accion", "bpip", "proyecto", "descripcion", "latitud", "longitud",
            "estado_iniciativa", "inicio_perforacion", "fin_perforacion", "tipo_incorporacion",
            "expectativa_caudal_lps", "caudal_temporal_lps", "poblacion_beneficiada_estimada",
            "anio_incorporacion_texto", "anio_efecto", "sistema_codigo", "sistema_nombre",
            "cluster", "beneficios", "impacto", "actividades_criticas", "dependencia_responsable",
            "estudio_hidrogeologico", "situacion_terrenos", "observaciones",
        ]
        project_editor_columns = [col for col in project_editor_columns if col in filtered.columns]
        st.caption("Edite directamente la tabla. Los campos principales son desplegables; los cambios se guardan en Supabase o en CSV local.")
        column_config = {
    "id": st.column_config.NumberColumn("ID", disabled=True),
    "accion": st.column_config.SelectboxColumn(
        "Acción",
        options=clean_options(proyectos.get("accion", pd.Series(dtype=str)), ACCION_OPTIONS),
    ),
    "estado_iniciativa": st.column_config.SelectboxColumn(
        "Estado de la iniciativa",
        options=clean_options(proyectos.get("estado_iniciativa", pd.Series(dtype=str)), ESTADO_INICIATIVA_OPTIONS),
    ),
    "tipo_incorporacion": st.column_config.SelectboxColumn(
        "Tipo de incorporación",
        options=clean_options(proyectos.get("tipo_incorporacion", pd.Series(dtype=str)), TIPO_INCORPORACION_OPTIONS),
    ),
    "sistema_nombre": st.column_config.SelectboxColumn("Sistema beneficiado", options=sistema_options),
    "sistema_codigo": st.column_config.SelectboxColumn("Código sistema", options=sistema_codigo_options),
    "cluster": st.column_config.SelectboxColumn("Cluster", options=cluster_options),
    "beneficios": st.column_config.SelectboxColumn(
        "Beneficios",
        options=clean_options(proyectos.get("beneficios", pd.Series(dtype=str)), beneficios_options, include_blank=True),
    ),
    "impacto": st.column_config.SelectboxColumn(
        "Impacto",
        options=clean_options(proyectos.get("impacto", pd.Series(dtype=str)), impactos_options, include_blank=True),
    ),
    "actividades_criticas": st.column_config.SelectboxColumn(
        "Actividades críticas",
        options=["", *actividades_options],
    ),
    "dependencia_responsable": st.column_config.SelectboxColumn(
        "Dependencia responsable",
        options=dependencia_options,
    ),
    "estudio_hidrogeologico": st.column_config.SelectboxColumn(
        "Estudio hidrogeológico",
        options=clean_options(proyectos.get("estudio_hidrogeologico", pd.Series(dtype=str)), ESTUDIO_OPTIONS, include_blank=True),
    ),
    "situacion_terrenos": st.column_config.SelectboxColumn(
        "Situación de terrenos",
        options=terrenos_options,
    ),
    "anio_efecto": st.column_config.NumberColumn("Año efecto", min_value=2024, max_value=2040, step=1),
    "latitud": st.column_config.NumberColumn("Latitud", format="%.7f"),
    "longitud": st.column_config.NumberColumn("Longitud", format="%.7f"),
    "expectativa_caudal_lps": st.column_config.NumberColumn("Expectativa L/s", format="%.2f"),
    "caudal_temporal_lps": st.column_config.NumberColumn("Caudal temporal L/s", format="%.2f"),
}
        edited = st.data_editor(
            filtered,
            use_container_width=True,
            num_rows="dynamic",
            column_config=column_config,
            key="editor_proyectos",
            height=520,
            hide_index=True,
            column_order=project_editor_columns,
        )
        left, right = st.columns([1, 2])
        if left.button("Guardar cambios", type="primary", key="guardar_proyectos"):
            edited = normalize_project_rows(edited, sistemas)
            save_edited_rows("proyectos", edited, "Proyectos actualizados.")
        ids = right.multiselect("Eliminar proyectos por ID", sorted(proyectos["id"].dropna().astype(int).unique().tolist())) if "id" in proyectos.columns else []
        if right.button("Eliminar seleccionados", type="secondary", disabled=not ids):
            delete_rows("proyectos", ids)
            st.success("Proyectos eliminados.")
            st.rerun()

    with tab_detalle:
        st.caption("Use este formulario cuando requiera editar campos tipo Choice o selección múltiple: beneficios, impacto y actividades críticas.")
        if "id" not in proyectos.columns:
            st.info("No hay columna ID para editar el detalle del proyecto.")
        else:
            project_ids = sorted(proyectos["id"].dropna().astype(int).unique().tolist())
            labels = {int(row["id"]): f'{int(row["id"])} · {row.get("proyecto", "Sin nombre")}' for _, row in proyectos.dropna(subset=["id"]).iterrows()}
            selected_id = st.selectbox("Proyecto a editar", project_ids, format_func=lambda x: labels.get(int(x), str(x)))
            row = proyectos[proyectos["id"].astype("Int64").eq(int(selected_id))].iloc[0].copy()
            with st.form("form_editar_detalle_proyecto"):
                col_a, col_b, col_c = st.columns(3)
                proyecto = col_a.text_input("Proyecto", value=str(row.get("proyecto", "")))
                bpip = col_b.text_input("N° BPIP", value=str(row.get("bpip", "")))
                accion_opts = clean_options(proyectos.get("accion", pd.Series(dtype=str)), ACCION_OPTIONS)
                accion = col_c.selectbox("Acción", accion_opts, index=option_index(accion_opts, row.get("accion")))
                descripcion = st.text_area("Descripción", value=str(row.get("descripcion", "")), height=130)
                col1, col2, col3, col4 = st.columns(4)
                lat = col1.number_input("Latitud", value=safe_float(row.get("latitud")), format="%.7f")
                lon = col2.number_input("Longitud", value=safe_float(row.get("longitud")), format="%.7f")
                expectativa = col3.number_input("Expectativa de caudal (L/s)", min_value=0.0, value=safe_float(row.get("expectativa_caudal_lps")), step=1.0)
                temporal = col4.number_input("Caudal incorporado temporal (L/s)", min_value=0.0, value=safe_float(row.get("caudal_temporal_lps")), step=1.0)
                col5, col6, col7, col8 = st.columns(4)
                anio_val = pd.to_numeric(row.get("anio_efecto"), errors="coerce")
                anio = col5.number_input("Año efecto", min_value=2024, max_value=2040, value=int(anio_val) if pd.notna(anio_val) else 2026, step=1)
                tipo_opts = clean_options(proyectos.get("tipo_incorporacion", pd.Series(dtype=str)), TIPO_INCORPORACION_OPTIONS)
                tipo = col6.selectbox("Tipo incorporación", tipo_opts, index=option_index(tipo_opts, row.get("tipo_incorporacion")))
                estado_opts = clean_options(proyectos.get("estado_iniciativa", pd.Series(dtype=str)), ESTADO_INICIATIVA_OPTIONS)
                estado = col7.selectbox("Estado de la iniciativa", estado_opts, index=option_index(estado_opts, row.get("estado_iniciativa")))
                sistema_opts = clean_options(sistemas.get("sistema_nombre", pd.Series(dtype=str)), proyectos.get("sistema_nombre", pd.Series(dtype=str)))
                sistema_nombre = col8.selectbox("Sistema", sistema_opts, index=option_index(sistema_opts, row.get("sistema_nombre")))
                by_name_code, by_name_cluster, _, _ = system_maps(sistemas)
                sistema_codigo = by_name_code.get(str(sistema_nombre), str(row.get("sistema_codigo", "")))
                cluster = by_name_cluster.get(str(sistema_nombre), str(row.get("cluster", "")))
                st.info(f"Código sistema: **{sistema_codigo or '—'}** · Cluster: **{cluster or '—'}**")
                col9, col10, col11 = st.columns(3)
                dependencia_opts = clean_options(proyectos.get("dependencia_responsable", pd.Series(dtype=str)), dependencia_options)
                dependencia = col9.selectbox("Dependencia responsable", dependencia_opts, index=option_index(dependencia_opts, row.get("dependencia_responsable")))
                estudio_opts = clean_options(proyectos.get("estudio_hidrogeologico", pd.Series(dtype=str)), ESTUDIO_OPTIONS, include_blank=True)
                estudio = col10.selectbox("Estudio hidrogeológico", estudio_opts, index=option_index(estudio_opts, row.get("estudio_hidrogeologico")))
                terrenos_opts = clean_options(catalogo_terrenos.iloc[:, 0] if not catalogo_terrenos.empty else pd.Series(dtype=str), proyectos.get("situacion_terrenos", pd.Series(dtype=str)), include_blank=True)
                terrenos = col11.selectbox("Situación de terrenos", terrenos_opts, index=option_index(terrenos_opts, row.get("situacion_terrenos")))
                col12, col13 = st.columns(2)
                beneficios = col12.multiselect("Beneficios", beneficios_options, default=[x for x in split_multi(row.get("beneficios")) if x in beneficios_options])
                impacto = col13.multiselect("Impacto", impactos_options, default=[x for x in split_multi(row.get("impacto")) if x in impactos_options])
                actividades = st.multiselect("Actividades críticas / riesgos", actividades_options, default=[x for x in split_multi(row.get("actividades_criticas")) if x in actividades_options])
                observaciones = st.text_area("Observaciones", value=str(row.get("observaciones", "")), height=110)
                submitted = st.form_submit_button("Guardar detalle del proyecto", type="primary")
                if submitted:
                    updated = row.to_dict()
                    updated.update(
                        {
                            "proyecto": proyecto,
                            "bpip": bpip,
                            "accion": accion,
                            "descripcion": descripcion,
                            "latitud": lat,
                            "longitud": lon,
                            "estado_iniciativa": estado,
                            "tipo_incorporacion": tipo,
                            "expectativa_caudal_lps": expectativa,
                            "caudal_temporal_lps": temporal,
                            "poblacion_beneficiada_estimada": math.ceil(float(temporal) * 79.6 * 3.1) if temporal else row.get("poblacion_beneficiada_estimada"),
                            "anio_incorporacion_texto": str(anio),
                            "anio_efecto": int(anio),
                            "sistema_codigo": sistema_codigo,
                            "sistema_nombre": sistema_nombre,
                            "cluster": cluster,
                            "beneficios": join_multi(beneficios),
                            "impacto": join_multi(impacto),
                            "actividades_criticas": join_multi(actividades),
                            "dependencia_responsable": dependencia,
                            "estudio_hidrogeologico": estudio,
                            "situacion_terrenos": terrenos,
                            "observaciones": observaciones,
                        }
                    )
                    upsert_rows("proyectos", pd.DataFrame([updated]))
                    st.success("Detalle del proyecto actualizado.")
                    st.rerun()

    with tab_nuevo:
        with st.form("form_nuevo_proyecto", clear_on_submit=True):
            col_a, col_b, col_c = st.columns(3)
            proyecto = col_a.text_input("Proyecto")
            bpip = col_b.text_input("N° BPIP")
            accion = col_c.selectbox("Acción", ACCION_OPTIONS, index=0)
            descripcion = st.text_area("Descripción")
            col1, col2, col3, col4 = st.columns(4)
            lat = col1.number_input("Latitud", value=9.9000000, format="%.7f")
            lon = col2.number_input("Longitud", value=-84.0000000, format="%.7f")
            expectativa = col3.number_input("Expectativa de caudal (L/s)", min_value=0.0, value=0.0, step=1.0)
            temporal = col4.number_input("Caudal incorporado temporal (L/s)", min_value=0.0, value=0.0, step=1.0)
            col5, col6, col7 = st.columns(3)
            anio = col5.number_input("Año efecto", min_value=2024, max_value=2040, value=2026, step=1)
            tipo = col6.selectbox("Tipo incorporación", TIPO_INCORPORACION_OPTIONS)
            sistema_nombre = col7.selectbox("Sistema", sistema_options) if sistema_options else col7.text_input("Sistema")
            by_name_code, by_name_cluster, _, _ = system_maps(sistemas)
            sistema_codigo = by_name_code.get(str(sistema_nombre), "")
            cluster = by_name_cluster.get(str(sistema_nombre), "")
            col8, col9 = st.columns(2)
            beneficios = col8.multiselect("Beneficios", beneficios_options)
            impacto = col9.multiselect("Impacto", impactos_options)
            actividades = st.multiselect("Actividades críticas / riesgos", actividades_options)
            col10, col11, col12 = st.columns(3)
            dependencia = col10.selectbox("Dependencia responsable", dependencia_options) if dependencia_options else col10.text_input("Dependencia responsable")
            estudio = col11.selectbox("Estudio hidrogeológico", ESTUDIO_OPTIONS)
            terrenos = col12.selectbox("Situación de terrenos", terrenos_options) if terrenos_options else col12.text_input("Situación de terrenos")
            observaciones = st.text_area("Observaciones")
            submitted = st.form_submit_button("Agregar proyecto", type="primary")
            if submitted:
                poblacion = math.ceil(float(temporal) * 79.6 * 3.1) if temporal else 0
                new_row = pd.DataFrame(
                    [
                        {
                            "accion": accion,
                            "bpip": bpip,
                            "proyecto": proyecto,
                            "descripcion": descripcion,
                            "latitud": lat,
                            "longitud": lon,
                            "estado_iniciativa": "Nuevo registro",
                            "tipo_incorporacion": tipo,
                            "expectativa_caudal_lps": expectativa,
                            "caudal_temporal_lps": temporal,
                            "poblacion_beneficiada_estimada": poblacion,
                            "anio_incorporacion_texto": str(anio),
                            "anio_efecto": int(anio),
                            "sistema_codigo": sistema_codigo,
                            "sistema_nombre": sistema_nombre,
                            "cluster": cluster,
                            "beneficios": join_multi(beneficios),
                            "impacto": join_multi(impacto),
                            "actividades_criticas": join_multi(actividades),
                            "dependencia_responsable": dependencia,
                            "estudio_hidrogeologico": estudio,
                            "situacion_terrenos": terrenos,
                            "observaciones": observaciones,
                        }
                    ]
                )
                upsert_rows("proyectos", new_row)
                st.success("Proyecto agregado.")
                st.rerun()


    with tab_mapa:
        st.markdown("#### Ubicación de proyectos")
        st.caption(
            "Mapa referencial con los proyectos que cuentan con latitud y longitud válidas. "
            "Ubicación estimada y centroidal de los proyectos."
        )
        map_df = proyectos.copy()
        map_df["lat"] = map_df.get("latitud", pd.Series(dtype=object)).apply(lambda v: parse_coordinate(v, "lat"))
        map_df["lon"] = map_df.get("longitud", pd.Series(dtype=object)).apply(lambda v: parse_coordinate(v, "lon"))
        map_df = map_df.dropna(subset=["lat", "lon"])
        map_df = map_df[(map_df["lat"].between(8, 12)) & (map_df["lon"].between(-86, -82))]
        if not map_df.empty:
            map_df["caudal_esperado_lps"] = map_df.apply(extract_expected_flow, axis=1)
            if pd.to_numeric(map_df["caudal_esperado_lps"], errors="coerce").fillna(0).max() <= 0:
                map_df["tamano_mapa"] = 8
            else:
                map_df["tamano_mapa"] = pd.to_numeric(map_df["caudal_esperado_lps"], errors="coerce").fillna(0).clip(lower=1)
        if map_df.empty:
            st.info("No hay proyectos con coordenadas válidas para mostrar en el mapa.")
        else:
            center_lat = float(map_df["lat"].mean())
            center_lon = float(map_df["lon"].mean())
            hover_data = {"caudal_esperado_lps": ":.2f", "lat": ":.6f", "lon": ":.6f"}
            if "sistema_nombre" in map_df.columns:
                hover_data["sistema_nombre"] = True
            if "cluster" in map_df.columns:
                hover_data["cluster"] = True
            fig_map = px.scatter_mapbox(
                map_df,
                lat="lat",
                lon="lon",
                color="cluster" if "cluster" in map_df.columns else None,
                size="tamano_mapa",
                size_max=18,
                zoom=8.5,
                center={"lat": center_lat, "lon": center_lon},
                hover_name="proyecto" if "proyecto" in map_df.columns else None,
                hover_data=hover_data,
                title=f"Proyectos georreferenciados ({len(map_df)})",
            )
            fig_map.update_layout(
                mapbox_style="open-street-map",
                height=430,
                margin={"r": 0, "t": 45, "l": 0, "b": 0},
                legend_title_text="Cluster",
            )
            st.plotly_chart(fig_map, use_container_width=True)
            with st.expander("Ver proyectos ubicados en el mapa", expanded=False):
                cols = [c for c in ["proyecto", "sistema_nombre", "cluster", "lat", "lon", "expectativa_caudal_lps"] if c in map_df.columns]
                st.dataframe(map_df[cols], use_container_width=True, hide_index=True, height=260)

    with tab_graficos:
        g1, g2 = st.columns(2)
        if "sistema_nombre" in proyectos.columns:
            count_system = proyectos.groupby("sistema_nombre", dropna=False).size().reset_index(name="cantidad").sort_values("cantidad", ascending=False)
            fig = px.bar(
                count_system,
                x="cantidad",
                y="sistema_nombre",
                orientation="h",
                color="sistema_nombre",
                text="cantidad",
                title="Cantidad de proyectos por sistema",
            )
            g1.plotly_chart(add_count_labels(fig, "h"), use_container_width=True)
        if "cluster" in proyectos.columns:
            flow_cluster = proyectos.assign(caudal=proyectos.apply(extract_expected_flow, axis=1)).groupby("cluster", dropna=False)["caudal"].sum().reset_index().sort_values("caudal", ascending=False)
            fig = px.bar(
                flow_cluster,
                x="cluster",
                y="caudal",
                color="cluster",
                text="caudal",
                title="Caudal esperado por cluster (L/s)",
            )
            g2.plotly_chart(add_bar_labels(fig, "v"), use_container_width=True)
        g3, g4 = st.columns(2)
        if "accion" in proyectos.columns:
            count_action = proyectos.groupby("accion", dropna=False).size().reset_index(name="cantidad")
            fig = px.pie(count_action, names="accion", values="cantidad", title="Proyectos por acción")
            fig.update_traces(textinfo="label+value+percent")
            g3.plotly_chart(fig, use_container_width=True)
        if "sistema_nombre" in proyectos.columns:
            flow_system = proyectos.assign(caudal=proyectos.apply(extract_expected_flow, axis=1)).groupby("sistema_nombre", dropna=False)["caudal"].sum().reset_index().sort_values("caudal", ascending=False).head(15)
            fig = px.bar(
                flow_system,
                x="caudal",
                y="sistema_nombre",
                orientation="h",
                color="sistema_nombre",
                text="caudal",
                title="Top sistemas por caudal esperado",
            )
            g4.plotly_chart(add_bar_labels(fig, "h"), use_container_width=True)




def project_effect_items(proyectos: pd.DataFrame) -> pd.DataFrame:
    """Return one row per project that can improve the cluster balance.

    Vista 2 intentionally uses only `expectativa_caudal_lps`. The temporary flow
    is kept as operational context in Vista 1 and must not change the executive
    capacity reading.
    """
    columns = [
        "cluster",
        "sistema_nombre",
        "anio_efecto",
        "proyecto",
        "caudal_esperado_lps",
    ]
    if proyectos.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for _, row in proyectos.iterrows():
        anio = extract_effect_year(row)
        flow = extract_expected_flow(row)
        if anio is None or flow <= 0:
            continue
        proyecto = str(row.get("proyecto") or "Proyecto sin nombre").strip() or "Proyecto sin nombre"
        rows.append(
            {
                "cluster": canonical_cluster_from_system_or_code(row.get("sistema_nombre"), row.get("sistema_codigo"), row.get("cluster")) or "Sin cluster",
                "sistema_nombre": str(row.get("sistema_nombre") or "Sin sistema").strip() or "Sin sistema",
                "anio_efecto": int(anio),
                "proyecto": proyecto,
                "caudal_esperado_lps": round(float(flow), 2),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def compute_project_effects(proyectos: pd.DataFrame, years: Iterable[int]) -> pd.DataFrame:
    """Return cumulative expected project effects by cluster and year."""
    columns = ["cluster", "sistema_nombre", "anio", "proyecto", "anio_efecto", "efecto_proyectos_lps"]
    items = project_effect_items(proyectos)
    if items.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for _, row in items.iterrows():
        for year in years:
            if int(year) >= int(row["anio_efecto"]):
                rows.append(
                    {
                        "cluster": row["cluster"],
                        "sistema_nombre": row["sistema_nombre"],
                        "anio": int(year),
                        "proyecto": row["proyecto"],
                        "anio_efecto": int(row["anio_efecto"]),
                        "efecto_proyectos_lps": float(row["caudal_esperado_lps"]),
                    }
                )
    return pd.DataFrame(rows, columns=columns)


def build_project_cluster_summary(proyectos: pd.DataFrame, clusters: list[str] | None = None) -> pd.DataFrame:
    """Summarize how many projects improve each cluster, in which years, and which projects."""
    items = project_effect_items(proyectos)
    if clusters and not items.empty:
        items = items[items["cluster"].astype(str).isin(clusters)]
    if items.empty:
        return pd.DataFrame(
            columns=[
                "Cluster",
                "Proyectos de mejora",
                "Años de incorporación",
                "Primer año",
                "Aporte total esperado L/s",
                "Proyectos principales",
            ]
        )

    def project_list(group: pd.DataFrame) -> str:
        ordered = group.sort_values(["anio_efecto", "caudal_esperado_lps"], ascending=[True, False])
        labels = [f"{r.proyecto} ({int(r.anio_efecto)}, {r.caudal_esperado_lps:g} L/s)" for r in ordered.itertuples()]
        text = "; ".join(labels[:6])
        if len(labels) > 6:
            text += f"; +{len(labels) - 6} adicionales"
        return text

    summary = (
        items.groupby("cluster", as_index=False)
        .apply(
            lambda g: pd.Series(
                {
                    "Proyectos de mejora": int(g["proyecto"].nunique()),
                    "Años de incorporación": ", ".join(map(str, sorted(g["anio_efecto"].astype(int).unique()))),
                    "Primer año": int(g["anio_efecto"].min()),
                    "Aporte total esperado L/s": round(float(g["caudal_esperado_lps"].sum()), 2),
                    "Proyectos principales": project_list(g),
                }
            )
        )
        .reset_index(drop=True)
    )
    summary["Cluster"] = summary["cluster"].apply(cluster_label)
    summary = summary.sort_values("cluster", key=lambda s: s.map(cluster_sort_key))
    return summary[
        [
            "Cluster",
            "Proyectos de mejora",
            "Años de incorporación",
            "Primer año",
            "Aporte total esperado L/s",
            "Proyectos principales",
        ]
    ]


def official_balance_pivot(cap: pd.DataFrame, escenario: str, years: list[int], clusters: list[str] | None = None, systems: list[str] | None = None) -> pd.DataFrame:
    base = cap[(cap["escenario"].astype(str) == escenario) & (cap["anio"].astype(int).isin(years))].copy()
    if clusters:
        base = base[base["cluster"].astype(str).isin(clusters)]
    if systems:
        base = base[base["sistema"].astype(str).isin(systems)]
    pivot = base.pivot_table(index=["cod", "sistema"], columns="anio", values="balance_lps", aggfunc="sum").reset_index()
    pivot = pivot.rename(columns={"cod": "COD", "sistema": "SISTEMA"})
    ordered = ["COD", "SISTEMA"] + [y for y in years if y in pivot.columns]
    return pivot[ordered]


def cluster_label(cluster: str) -> str:
    text = canonical_cluster_from_system_or_code(current=cluster)
    if text in CLUSTER_DISPLAY:
        return CLUSTER_DISPLAY[text]
    match = re.search(r"C-\s*(\d+)", str(text), flags=re.IGNORECASE)
    if match:
        return f"Cluster {match.group(1)}"
    if "NO INTER" in str(text).upper():
        return "Cluster 6"
    return str(text)


def cluster_sort_key(cluster: object) -> tuple[int, str]:
    text = canonical_cluster_from_system_or_code(current=cluster)
    match = re.search(r"C-\s*(\d+)", str(text), flags=re.IGNORECASE)
    if match:
        return (int(match.group(1)), str(text))
    if "PAAM" in str(text).upper():
        return (100, str(text))
    return (50, str(text))


def build_cluster_yearly_analysis(cap: pd.DataFrame, proyectos: pd.DataFrame, years: list[int], clusters: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create an executive analytical layer by cluster.

    The official SIN_PAAM/CON_PAAM tables are not modified. This layer summarizes
    the signed base balance, the expected contribution from projects, the signed
    adjusted balance and the remaining deficit, when it exists.
    """
    base = cap[(cap["escenario"].astype(str) == "SIN_PAAM") & (cap["anio"].astype(int).isin(years))].copy()
    base = base[base["cluster"].astype(str) != "PAAM / RESERVA"]
    if clusters:
        base = base[base["cluster"].astype(str).isin(clusters)]

    systems_by_cluster = (
        base.groupby("cluster")["cod"].nunique().reset_index(name="sistemas_considerados")
        if not base.empty
        else pd.DataFrame(columns=["cluster", "sistemas_considerados"])
    )
    system_names_by_cluster = (
        base.groupby("cluster")["sistema"].apply(lambda s: "; ".join(sorted(s.dropna().astype(str).unique()))).reset_index(name="sistemas_asociados")
        if not base.empty and "sistema" in base.columns
        else pd.DataFrame(columns=["cluster", "sistemas_asociados"])
    )
    cluster_base = base.groupby(["cluster", "anio"], as_index=False)["balance_lps"].sum().rename(columns={"balance_lps": "balance_base_lps"})

    effects_detail = compute_project_effects(proyectos, years)
    if clusters and not effects_detail.empty:
        effects_detail = effects_detail[effects_detail["cluster"].astype(str).isin(clusters)]
    effects = (
        effects_detail.groupby(["cluster", "anio"], as_index=False)["efecto_proyectos_lps"].sum()
        if not effects_detail.empty
        else pd.DataFrame(columns=["cluster", "anio", "efecto_proyectos_lps"])
    )

    yearly = cluster_base.merge(effects, on=["cluster", "anio"], how="left")
    yearly = yearly.merge(systems_by_cluster, on="cluster", how="left")
    yearly = yearly.merge(system_names_by_cluster, on="cluster", how="left")
    yearly["efecto_proyectos_lps"] = pd.to_numeric(yearly["efecto_proyectos_lps"], errors="coerce").fillna(0.0)
    yearly["balance_ajustado_lps"] = yearly["balance_base_lps"] + yearly["efecto_proyectos_lps"]
    yearly["brecha_base_lps"] = (-yearly["balance_base_lps"]).clip(lower=0)
    yearly["brecha_remanente_lps"] = (-yearly["balance_ajustado_lps"]).clip(lower=0)
    yearly["excedente_lps"] = yearly["balance_ajustado_lps"].clip(lower=0)
    yearly["mejora_lps"] = yearly["brecha_base_lps"] - yearly["brecha_remanente_lps"]
    yearly["mitigacion_brecha_pct"] = yearly.apply(
        lambda r: min(max((r["mejora_lps"] / r["brecha_base_lps"]) * 100, 0), 100) if r["brecha_base_lps"] > 0 else (100 if r["balance_ajustado_lps"] >= 0 else 0),
        axis=1,
    )
    yearly["cluster_label"] = yearly["cluster"].apply(cluster_label)
    yearly = yearly.sort_values(by=["cluster"], key=lambda s: s.map(cluster_sort_key)).sort_values(["cluster", "anio"], key=lambda s: s.map(cluster_sort_key) if s.name == "cluster" else s)
    return yearly, effects_detail


def executive_status(row: pd.Series) -> str:
    balance_2032 = safe_float(row.get("Balance con proyectos 2032"))
    mitigacion = safe_float(row.get("Mitigación 2032 (%)"))
    aporte = safe_float(row.get("Aporte esperado 2032"))
    if balance_2032 >= 0:
        return "Balance positivo al 2032"
    if mitigacion >= 50:
        return "Mejora relevante; balance aún negativo"
    if aporte > 0:
        return "Mejora parcial; requiere complemento"
    return "Balance negativo sin mejora cargada"


def executive_message(row: pd.Series) -> str:
    balance_2032 = safe_float(row.get("Balance con proyectos 2032"))
    brecha_2032 = safe_float(row.get("Brecha remanente 2032"))
    mitigacion = safe_float(row.get("Mitigación 2032 (%)"))
    aporte = safe_float(row.get("Aporte esperado 2032"))
    if balance_2032 >= 0:
        return "Con los proyectos de análisis, el cluster alcanza balance positivo al 2032."
    if aporte > 0:
        return f"Se mitiga aproximadamente {mitigacion:.0f}% de la brecha al 2032; el balance ajustado sigue en {balance_2032:.1f} L/s y queda una brecha de {brecha_2032:.1f} L/s."
    return "No se registran aportes de proyectos de análisis en el cluster; el balance sigue negativo y requiere gestión complementaria."


def build_executive_cluster_table(yearly: pd.DataFrame, project_summary: pd.DataFrame | None = None) -> pd.DataFrame:
    if yearly.empty:
        return pd.DataFrame()

    years_available = sorted(yearly["anio"].dropna().astype(int).unique().tolist())
    y0 = 2025 if 2025 in years_available else years_available[0]
    y_mid = 2032 if 2032 in years_available else years_available[min(len(years_available) - 1, len(years_available) // 2)]

    rows = []
    for cluster, group in yearly.groupby("cluster", sort=False):
        group = group.set_index("anio")
        def value(year: int, col: str) -> float:
            return round(float(group.loc[year, col]), 2) if year in group.index else 0.0
        sistemas_asociados = ""
        if "sistemas_asociados" in group.columns and not group["sistemas_asociados"].dropna().empty:
            sistemas_asociados = str(group["sistemas_asociados"].dropna().iloc[0])
        row = {
            "Cluster": cluster_label(cluster),
            "Sistemas": int(group["sistemas_considerados"].dropna().iloc[0]) if "sistemas_considerados" in group and not group["sistemas_considerados"].dropna().empty else 0,
            "Sistema Más Representativo del Cluster": cluster_representative(cluster),
            "Sistemas asociados": cluster_systems_text(cluster) or sistemas_asociados,
            "Balance base 2025": value(y0, "balance_base_lps"),
            "Balance base 2032": value(y_mid, "balance_base_lps"),
            "Aporte esperado 2032": value(y_mid, "efecto_proyectos_lps"),
            "Balance con proyectos 2032": value(y_mid, "balance_ajustado_lps"),
            "Brecha remanente 2032": value(y_mid, "brecha_remanente_lps"),
            "Mitigación 2032 (%)": round(value(y_mid, "mitigacion_brecha_pct"), 1),
        }
        row["Condición ejecutiva"] = executive_status(pd.Series(row))
        row["Lectura ejecutiva"] = executive_message(pd.Series(row))
        rows.append(row)
    out = pd.DataFrame(rows)
    if project_summary is not None and not project_summary.empty:
        out = out.merge(project_summary, on="Cluster", how="left")
    else:
        out["Proyectos de mejora"] = 0
        out["Años de incorporación"] = "—"
        out["Primer año"] = "—"
        out["Aporte total esperado L/s"] = 0.0
        out["Proyectos principales"] = "Sin proyectos de mejora cargados"
    out["Proyectos de mejora"] = pd.to_numeric(out["Proyectos de mejora"], errors="coerce").fillna(0).astype(int)
    out["Años de incorporación"] = out["Años de incorporación"].fillna("—")
    out["Primer año"] = out["Primer año"].fillna("—")
    out["Aporte total esperado L/s"] = pd.to_numeric(out["Aporte total esperado L/s"], errors="coerce").fillna(0.0)
    out["Proyectos principales"] = out["Proyectos principales"].fillna("Sin proyectos de mejora cargados")
    out["Sistemas asociados"] = out["Sistemas asociados"].fillna("")
    front = [
        "Cluster",
        "Sistema Más Representativo del Cluster",
        "Condición ejecutiva",
        "Lectura ejecutiva",
        "Proyectos de mejora",
        "Años de incorporación",
        "Proyectos principales",
    ]
    rest = [c for c in out.columns if c not in front]
    return out[front + rest]


def style_executive_table(df: pd.DataFrame):
    def style_status(value):
        text = str(value)
        if "positivo" in text:
            return "background-color:#DFF3E5;color:#0B6B2A;font-weight:700;"
        if "Mejora" in text or "parcial" in text:
            return "background-color:#FFF3CD;color:#6B4E00;font-weight:700;"
        return "background-color:#F4E7E7;color:#7A1D1D;font-weight:700;"

    def style_gap(value):
        try:
            val = float(value)
        except Exception:
            return ""
        if val <= 0:
            return "background-color:#EAF7ED;color:#0B6B2A;font-weight:600;"
        if val < 50:
            return "background-color:#FFF8E1;color:#6B4E00;font-weight:600;"
        return "background-color:#FDECEC;color:#8A1C1C;font-weight:600;"

    def style_signed_balance(value):
        try:
            val = float(value)
        except Exception:
            return ""
        if val >= 0:
            return "background-color:#EAF7ED;color:#0B6B2A;font-weight:600;"
        return "background-color:#FDECEC;color:#B00020;font-weight:600;"

    gap_cols = [c for c in df.columns if "Brecha remanente" in str(c)]
    balance_cols = [c for c in df.columns if str(c).startswith("Balance")]
    styler = df.style
    if hasattr(styler, "map"):
        styler = styler.map(style_status, subset=["Condición ejecutiva"])
        if gap_cols:
            styler = styler.map(style_gap, subset=gap_cols)
        if balance_cols:
            styler = styler.map(style_signed_balance, subset=balance_cols)
        return styler.format(precision=1)
    styler = styler.applymap(style_status, subset=["Condición ejecutiva"])
    if gap_cols:
        styler = styler.applymap(style_gap, subset=gap_cols)
    if balance_cols:
        styler = styler.applymap(style_signed_balance, subset=balance_cols)
    return styler.format(precision=1)



def adjusted_cluster_balance_pivot(yearly: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    """Signed annual balance by cluster after applying expected project flows."""
    if yearly.empty:
        return pd.DataFrame()
    base = yearly[yearly["anio"].astype(int).isin(years)].copy()
    pivot = base.pivot_table(index="cluster_label", columns="anio", values="balance_ajustado_lps", aggfunc="sum").reset_index()
    pivot = pivot.rename(columns={"cluster_label": "Cluster"})
    year_cols = [y for y in years if y in pivot.columns]
    pivot = pivot[["Cluster"] + year_cols]
    order_map = {cluster_label(c): cluster_sort_key(c) for c in yearly["cluster"].dropna().astype(str).unique()}
    pivot = pivot.sort_values("Cluster", key=lambda s: s.map(lambda x: order_map.get(x, (50, str(x)))))
    return pivot

def vista_capacidad() -> None:
    st.subheader("Vista 2 · Capacidad hídrica GAM")
    cap = read_table("capacidad_base")
    proyectos = read_table("proyectos")
    if cap.empty:
        st.warning("No hay tabla de capacidad base cargada.")
        return

    cap = ensure_columns(cap, ["escenario", "cluster", "cod", "sistema", "anio", "balance_lps"])
    cap = apply_canonical_clusters(cap, "sistema", "cod", "cluster")
    proyectos = normalize_project_rows(proyectos, read_table("sistemas_clusters"))
    cap["anio"] = pd.to_numeric(cap["anio"], errors="coerce").astype("Int64")
    cap["balance_lps"] = pd.to_numeric(cap["balance_lps"], errors="coerce")
    cap = cap.dropna(subset=["anio"])
    cap["anio"] = cap["anio"].astype(int)

    st.info(
        "Lectura ejecutiva: el balance por cluster se muestra como valor firmado. Un balance negativo indica déficit; "
        "un balance positivo indica superávit operativo del cluster para el año analizado. La brecha remanente es solo una traducción "
        "del déficit pendiente: si el balance con proyectos sigue negativo, la brecha remanente es ese faltante expresado en positivo; "
        "si el balance queda positivo, la brecha remanente es 0. Las tablas oficiales SIN PAAM y CON PAAM se mantienen abajo como respaldo técnico, sin alterarse."
    )

    c1, c2 = st.columns([2, 3])
    year_range = c1.slider("Años a mostrar en tablas oficiales", min_value=2025, max_value=2040, value=(2025, 2040), step=1)
    years = list(range(year_range[0], year_range[1] + 1))

    clusters = sorted(
        [x for x in cap["cluster"].dropna().astype(str).unique().tolist() if x.strip() and x != "PAAM / RESERVA"],
        key=cluster_sort_key,
    )
    selected_clusters = c2.multiselect("Cluster", clusters, format_func=cluster_label)

    # The executive summary is based on 2025-2040. El año 2024 se mantiene fuera del visor ejecutivo.
    full_years = ANALYSIS_YEARS
    yearly, effects_detail = build_cluster_yearly_analysis(
        cap=cap,
        proyectos=proyectos,
        years=full_years,
        clusters=selected_clusters,
    )
    project_summary = build_project_cluster_summary(proyectos, selected_clusters)
    exec_table = build_executive_cluster_table(yearly, project_summary)

    st.markdown("#### Resumen ejecutivo por cluster · proyectos que mejoran capacidad")
    st.caption(
        "Lectura para gerencia: cuántos proyectos mejoran cada cluster, desde qué años se incorporan, cuáles son los proyectos principales, "
        "cuánto aportan y qué brecha queda por gestionar. El caudal temporal no se usa en este cálculo; solo se usa el caudal esperado."
    )

    if exec_table.empty:
        st.warning("No hay datos suficientes para construir el resumen ejecutivo por cluster.")
    else:
        total_balance_base_2032 = exec_table["Balance base 2032"].sum()
        total_balance_ajustado_2032 = exec_table["Balance con proyectos 2032"].sum()
        total_brecha_base_2032 = (-exec_table["Balance base 2032"]).clip(lower=0).sum()
        total_brecha_rem_2032 = exec_table["Brecha remanente 2032"].sum()
        total_aporte_2032 = exec_table["Aporte esperado 2032"].sum()
        mitigacion_global = ((total_brecha_base_2032 - total_brecha_rem_2032) / total_brecha_base_2032 * 100) if total_brecha_base_2032 > 0 else 100
        clusters_mejoran = int((exec_table["Aporte esperado 2032"] > 0).sum())
        clusters_balance_positivo = int((exec_table["Balance con proyectos 2032"] >= 0).sum())

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Balance base 2032", format_lps(total_balance_base_2032))
        m2.metric("Aporte esperado 2032", format_lps(total_aporte_2032))
        m3.metric("Balance con proyectos 2032", format_lps(total_balance_ajustado_2032), delta=f"{mitigacion_global:.1f}% de brecha mitigada")
        m4.metric("Clusters con balance positivo", f"{clusters_balance_positivo} de {len(exec_table)}", delta=f"{clusters_mejoran} con mejora")

        st.markdown("##### Resumen de mejora por cluster")
        st.caption("Pase el mouse sobre las barras para ver los sistemas de abastecimiento asociados a cada cluster y los proyectos principales.")
        mejora_plot = exec_table.copy()
        mejora_plot["Etiqueta"] = mejora_plot["Proyectos de mejora"].astype(str) + " proyectos"
        fig_mejora = px.bar(
            mejora_plot.sort_values("Cluster"),
            x="Cluster",
            y="Aporte esperado 2032",
            color="Condición ejecutiva",
            text="Etiqueta",
            custom_data=["Sistemas asociados", "Proyectos principales", "Balance con proyectos 2032", "Brecha remanente 2032"],
            title="Resumen de mejora por cluster · aporte esperado al 2032",
        )
        fig_mejora.update_traces(
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Aporte esperado 2032: %{y:.1f} L/s<br>"
                "Balance con proyectos 2032: %{customdata[2]:.1f} L/s<br>"
                "Brecha remanente 2032: %{customdata[3]:.1f} L/s<br>"
                "<br><b>Sistemas asociados</b><br>%{customdata[0]}<br>"
                "<br><b>Proyectos principales</b><br>%{customdata[1]}<extra></extra>"
            )
        )
        fig_mejora.update_layout(xaxis_tickangle=-25)
        st.plotly_chart(add_bar_labels(fig_mejora, "v"), use_container_width=True)

        cols = st.columns(3)
        for i, row in exec_table.iterrows():
            sistemas_tooltip = html.escape(str(row.get("Sistemas asociados", "")))
            with cols[i % 3]:
                st.markdown(
                    f"""
                    <div class="aya-card" title="Sistemas asociados: {sistemas_tooltip}">
                        <div style="font-size:.82rem;color:#5b6472;">{row['Cluster']}</div>
                        <div style="font-size:1.45rem;font-weight:800;color:#001b44;">{int(row['Proyectos de mejora'])} proyectos</div>
                        <div style="font-size:.90rem;margin-top:.25rem;"><b>Años:</b> {row['Años de incorporación']}</div>
                        <div style="font-size:.90rem;"><b>Aporte 2032:</b> {format_lps(row['Aporte esperado 2032'])}</div>
                        <div style="font-size:.90rem;"><b>Balance 2032:</b> {format_lps(row['Balance con proyectos 2032'])}</div>
                        <div style="font-size:.84rem;margin-top:.45rem;color:#344054;">{row['Lectura ejecutiva']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        status_counts = exec_table.groupby("Condición ejecutiva", dropna=False).size().reset_index(name="cantidad")
        c_status, c_gap = st.columns([1, 2])
        fig_status = px.bar(
            status_counts.sort_values("cantidad", ascending=True),
            x="cantidad",
            y="Condición ejecutiva",
            orientation="h",
            color="Condición ejecutiva",
            text="cantidad",
            title="Semáforo ejecutivo por cluster",
        )
        c_status.plotly_chart(add_count_labels(fig_status, "h"), use_container_width=True)

        gap_plot = exec_table[["Cluster", "Balance base 2032", "Balance con proyectos 2032"]].melt(
            id_vars="Cluster",
            var_name="Indicador",
            value_name="Balance L/s",
        )
        fig_gap = px.bar(
            gap_plot,
            x="Cluster",
            y="Balance L/s",
            color="Indicador",
            barmode="group",
            text="Balance L/s",
            title="Balance base vs balance con proyectos · horizonte 2032",
        )
        fig_gap.add_hline(y=0, line_dash="dash", line_color="#667085")
        fig_gap.update_layout(xaxis_tickangle=-25)
        c_gap.plotly_chart(add_bar_labels(fig_gap, "v"), use_container_width=True)

        st.markdown("##### Tabla Resumen por Clúster en sistemas más representativos")
        visible_exec_table = exec_table.drop(columns=["Sistemas asociados"], errors="ignore")
        st.dataframe(
            style_executive_table(visible_exec_table),
            use_container_width=True,
            hide_index=True,
            height=360,
            column_config={
                "Mitigación 2032 (%)": st.column_config.ProgressColumn("Mitigación 2032 (%)", min_value=0, max_value=100, format="%.1f%%"),
                "Lectura ejecutiva": st.column_config.TextColumn("Lectura ejecutiva", width="large"),
                "Proyectos principales": st.column_config.TextColumn("Proyectos principales", width="large"),
            },
        )

        st.markdown("##### Balance anual por cluster con proyectos esperados")
        st.caption("Resumen firmado por cluster: valores negativos indican déficit y valores positivos indican balance favorable. Esta tabla aplica únicamente el caudal esperado de los proyectos de análisis.")
        cluster_pivot = adjusted_cluster_balance_pivot(yearly, full_years)
        st.dataframe(styled_balance(cluster_pivot), use_container_width=True, hide_index=True, height=300)

        with st.expander("¿Qué significa brecha remanente?", expanded=False):
            st.markdown(
                "La **brecha remanente** es el faltante que queda después de sumar el caudal esperado de los proyectos al balance base del cluster. "
                "No es un nuevo balance, sino el déficit pendiente expresado en positivo para facilitar la lectura gerencial. "
                "Ejemplo: si un cluster tiene balance base de -100 L/s y los proyectos aportan 40 L/s, el balance con proyectos queda en -60 L/s y la brecha remanente es 60 L/s. "
                "Si el balance con proyectos queda en +10 L/s, la brecha remanente es 0 L/s."
            )

    with st.expander("Detalle de proyectos de análisis considerados", expanded=False):
        detail = project_effect_items(proyectos)
        if selected_clusters and not detail.empty:
            detail = detail[detail["cluster"].astype(str).isin(selected_clusters)]
        if not detail.empty:
            detail = detail.sort_values(["cluster", "anio_efecto", "caudal_esperado_lps"], ascending=[True, True, False])
            detail["cluster"] = detail["cluster"].apply(cluster_label)
            detail = detail.rename(
                columns={
                    "cluster": "Cluster",
                    "sistema_nombre": "Sistema beneficiado",
                    "anio_efecto": "Año en que mejora",
                    "proyecto": "Proyecto",
                    "caudal_esperado_lps": "Caudal esperado L/s",
                }
            )
            st.dataframe(detail, use_container_width=True, height=320, hide_index=True)
        else:
            st.info("No hay proyectos con caudal esperado y año de efecto/incorporación válido para los filtros seleccionados.")

    st.markdown("#### Balance de escenario base · SIN incorporación de proyectos")
    st.caption("Tabla oficial informativa. No se modifica con los proyectos de análisis.")
    sin_pivot = official_balance_pivot(cap, "SIN_PAAM", years, selected_clusters, None)
    st.dataframe(styled_balance(sin_pivot), use_container_width=True, height=390, hide_index=True)

    st.markdown("#### Balance CON PAAM · 2032 en adelante")
    st.caption("Tabla oficial informativa. No se modifica con los proyectos de análisis.")
    con_pivot = official_balance_pivot(cap, "CON_PAAM", years, selected_clusters, None)
    st.dataframe(styled_balance(con_pivot), use_container_width=True, height=390, hide_index=True)



CAUDAL_NEED_CATEGORIES = {
    "aumento de recurso hidrico",
    "mejora en trasvase de agua entre sistemas de abastecimiento",
}
VOLUMEN_NEED_CATEGORIES = {"mejora en almacenamiento"}
KM_NEED_CATEGORIES = {"sustitucion de tuberias"}


def normalize_category_name(value: object) -> str:
    text = "" if value is None or pd.isna(value) else str(value).strip().lower()
    trans = str.maketrans("áéíóúüñ", "aeiouun")
    text = text.translate(trans)
    text = re.sub(r"\s+", " ", text)
    return text


def value_for_need_category(group: pd.DataFrame, category: str) -> str:
    cat = normalize_category_name(category)
    if cat in CAUDAL_NEED_CATEGORIES:
        value = pd.to_numeric(group.get("caudal_estimado_lps", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
        return f"{value:,.1f} L/s".replace(",", " ") if value else "—"
    if cat in VOLUMEN_NEED_CATEGORIES:
        value = pd.to_numeric(group.get("volumen_estimado_m3", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
        return f"{value:,.0f} m³".replace(",", " ") if value else "—"
    if cat in KM_NEED_CATEGORIES:
        value = pd.to_numeric(group.get("km_estimado", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
        return f"{value:,.2f} km".replace(",", " ") if value else "—"
    count = len(group)
    return f"{count} iniciativas" if count else "—"


def build_needs_summary_table(necesidades: pd.DataFrame, tipo_options: list[str]) -> pd.DataFrame:
    if necesidades.empty:
        return pd.DataFrame()
    df = ensure_columns(necesidades, ["sistema_de_abastecimiento", "tipo_de_proyecto", "caudal_estimado_lps", "volumen_estimado_m3", "km_estimado"])
    sistemas = sorted([x for x in df["sistema_de_abastecimiento"].dropna().astype(str).unique() if x.strip()])
    categorias = [x for x in tipo_options if str(x).strip()]
    for cat in df["tipo_de_proyecto"].dropna().astype(str).unique():
        if cat.strip() and cat not in categorias:
            categorias.append(cat)
    rows = []
    for sistema in sistemas:
        row = {"Sistema de Abastecimiento": sistema}
        sub = df[df["sistema_de_abastecimiento"].astype(str).eq(sistema)]
        for cat in categorias:
            group = sub[sub["tipo_de_proyecto"].astype(str).eq(cat)]
            row[cat] = value_for_need_category(group, cat) if not group.empty else "—"
        rows.append(row)
    return pd.DataFrame(rows)

def vista_necesidades() -> None:
    st.subheader("Vista 3 · Gestión y clasificación de necesidades")
    necesidades = read_table("necesidades")
    tipos = read_table("catalogo_tipos_proyecto")
    sistemas = read_table("sistemas_clusters")
    if necesidades.empty:
        st.warning("No hay necesidades cargadas.")
        return

    necesidades = ensure_columns(necesidades, ["id", *NECESIDAD_VISIBLE_COLS, "activo"])
    tipo_options = clean_options(tipos.iloc[:, 0] if not tipos.empty else pd.Series(dtype=str), necesidades.get("tipo_de_proyecto", pd.Series(dtype=str)))
    sistema_options = clean_options(sistemas.get("sistema_nombre", pd.Series(dtype=str)), necesidades.get("sistema_de_abastecimiento", pd.Series(dtype=str)))
    codigo_options = clean_options(sistemas.get("sistema_codigo", pd.Series(dtype=str)), necesidades.get("codigo_de_sistema", pd.Series(dtype=str)))

    tab_resumen, tab_editor, tab_nueva = st.tabs(["Resumen gráfico", "Tabla editable", "Agregar necesidad"])
    with tab_resumen:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Necesidades", f"{len(necesidades):,}")
        c2.metric("Sistemas impactados", necesidades.get("sistema_de_abastecimiento", pd.Series(dtype=str)).nunique())
        c3.metric("Tipos de proyecto", necesidades.get("tipo_de_proyecto", pd.Series(dtype=str)).nunique())
        c4.metric("Sin clasificar", int(necesidades.get("responsabilidad_atencion", pd.Series(dtype=str)).astype(str).str.strip().eq("").sum()))
        g1, g2 = st.columns(2)
        by_type = (
            necesidades
            .groupby("tipo_de_proyecto", dropna=False)
            .size()
            .reset_index(name="Cantidad")
            .rename(columns={"tipo_de_proyecto": "Categoría"})
            .sort_values("Cantidad", ascending=False)
        )
        
        by_type["Categoría"] = (
            by_type["Categoría"]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace({"": "Sin clasificar"})
        )

        fig_type = px.bar(
            by_type,
            x="Cantidad",
            y="Categoría",
            orientation="h",
            color="Categoría",
            text="Cantidad",
            title="Cantidad de necesidades por tipo de proyecto",
        )

        g1.plotly_chart(add_count_labels(fig_type, "h"), use_container_width=True)
        by_resp = necesidades.groupby("responsabilidad_atencion", dropna=False).size().reset_index(name="cantidad").sort_values("cantidad", ascending=False)
        by_resp["responsabilidad_atencion"] = by_resp["responsabilidad_atencion"].replace({"": "Sin clasificar"}).fillna("Sin clasificar")
        fig_resp = px.bar(
            by_resp,
            x="cantidad",
            y="responsabilidad_atencion",
            orientation="h",
            color="responsabilidad_atencion",
            text="cantidad",
            title="Clasificación de atención",
        )
        g2.plotly_chart(add_count_labels(fig_resp, "h"), use_container_width=True)

        st.markdown("#### Tabla resumen por sistema y categoría")
        st.caption(
            "Para Aumento de Recurso Hídrico y Trasvases se suma el caudal estimado (L/s); "
            "para Almacenamiento se suma volumen (m³); para Sustitución de tuberías se suma longitud (km); "
            "en las demás categorías se cuenta la cantidad de iniciativas."
        )
        summary_needs = build_needs_summary_table(necesidades, tipo_options)
        if summary_needs.empty:
            st.info("No hay datos suficientes para construir la tabla resumen.")
        else:
            st.dataframe(summary_needs, use_container_width=True, hide_index=True, height=360)

    with tab_editor:
        xlsx_importer("necesidades", "necesidades", sistemas, "necesidades")
        filtered = apply_filters(necesidades, "nec", ["tipo_de_proyecto", "codigo_de_sistema", "sistema_de_abastecimiento", "responsabilidad_atencion"])
        display_cols = ["id", *NECESIDAD_VISIBLE_COLS]
        editor_df = filtered[display_cols].copy()
        if "id" in editor_df.columns:
            editor_df = editor_df.set_index("id")
        column_config = {
            "objetivo_de_la_iniciativa": st.column_config.TextColumn(NECESIDAD_LABELS["objetivo_de_la_iniciativa"], width="large"),
            "breve_descripcion": st.column_config.TextColumn(NECESIDAD_LABELS["breve_descripcion"], width="large"),
            "tipo_de_proyecto": st.column_config.SelectboxColumn(NECESIDAD_LABELS["tipo_de_proyecto"], options=tipo_options, required=False),
            "codigo_de_sistema": st.column_config.SelectboxColumn(NECESIDAD_LABELS["codigo_de_sistema"], options=codigo_options, required=False),
            "sistema_de_abastecimiento": st.column_config.SelectboxColumn(NECESIDAD_LABELS["sistema_de_abastecimiento"], options=sistema_options, required=False),
            "principal_reto_por_superar": st.column_config.TextColumn(NECESIDAD_LABELS["principal_reto_por_superar"], width="large"),
            "observacion": st.column_config.TextColumn(NECESIDAD_LABELS["observacion"], width="large"),
            "caudal_estimado_lps": st.column_config.NumberColumn(NECESIDAD_LABELS["caudal_estimado_lps"], min_value=0.0, step=1.0, format="%.2f"),
            "volumen_estimado_m3": st.column_config.NumberColumn(NECESIDAD_LABELS["volumen_estimado_m3"], min_value=0.0, step=10.0, format="%.2f"),
            "km_estimado": st.column_config.NumberColumn(NECESIDAD_LABELS["km_estimado"], min_value=0.0, step=0.1, format="%.3f"),
            "responsabilidad_atencion": st.column_config.SelectboxColumn(NECESIDAD_LABELS["responsabilidad_atencion"], options=ATENCION_NECESIDAD_OPTIONS, required=False),
        }
        edited = st.data_editor(
            editor_df,
            use_container_width=True,
            num_rows="fixed",
            height=560,
            column_config=column_config,
            key="editor_necesidades",
        )
        edited = edited.reset_index()
        col1, col2 = st.columns([1, 2])
        if col1.button("Guardar cambios", type="primary", key="guardar_necesidades"):
            edited = normalize_need_rows(edited, sistemas)
            upsert_rows("necesidades", edited)
            st.success("Necesidades actualizadas.")
            st.rerun()
        id_label = "Eliminar necesidades por ID"
        ids = col2.multiselect(id_label, sorted(necesidades["id"].dropna().astype(int).unique().tolist())) if "id" in necesidades.columns else []
        if col2.button("Eliminar seleccionadas", disabled=not ids):
            delete_rows("necesidades", ids)
            st.success("Necesidades eliminadas.")
            st.rerun()
        export_df = filtered[[*NECESIDAD_VISIBLE_COLS]].copy()
        export_df = export_df.rename(columns=NECESIDAD_LABELS)
        st.download_button("Exportar necesidades filtradas a CSV", export_df.to_csv(index=False).encode("utf-8-sig"), "necesidades_filtradas.csv", "text/csv")

    with tab_nueva:
        with st.form("form_necesidad", clear_on_submit=True):
            objetivo = st.text_area("Objetivo de la iniciativa")
            descripcion = st.text_area("Breve descripción")
            col1, col2, col3 = st.columns(3)
            tipo = col1.selectbox("Tipo de proyecto", tipo_options) if tipo_options else col1.text_input("Tipo de proyecto")
            sistema = col2.selectbox("Sistema de Abastecimiento", sistema_options) if sistema_options else col2.text_input("Sistema de Abastecimiento")
            by_name_code, _, _, _ = system_maps(sistemas)
            codigo_sugerido = by_name_code.get(str(sistema), "")
            codigo = col3.selectbox("Código de Sistema", codigo_options, index=option_index(codigo_options, codigo_sugerido)) if codigo_options else col3.text_input("Código de Sistema", value=codigo_sugerido)
            reto = st.text_area("Principal reto por superar")
            observacion = st.text_area("Observación")
            q1, q2, q3 = st.columns(3)
            caudal_estimado = q1.number_input("Caudal estimado que aporta la iniciativa (L/s)", min_value=0.0, value=0.0, step=1.0)
            volumen_estimado = q2.number_input("Volumen estimado que aporta la iniciativa (m³)", min_value=0.0, value=0.0, step=10.0)
            km_estimado = q3.number_input("Km estimados que aporta la iniciativa (km)", min_value=0.0, value=0.0, step=0.1)
            responsabilidad = st.selectbox("Clasificación de atención", ATENCION_NECESIDAD_OPTIONS[1:])
            submitted = st.form_submit_button("Agregar necesidad", type="primary")
            if submitted:
                new_row = pd.DataFrame(
                    [
                        {
                            "objetivo_de_la_iniciativa": objetivo,
                            "breve_descripcion": descripcion,
                            "tipo_de_proyecto": tipo,
                            "codigo_de_sistema": codigo,
                            "sistema_de_abastecimiento": sistema,
                            "principal_reto_por_superar": reto,
                            "observacion": observacion,
                            "caudal_estimado_lps": caudal_estimado,
                            "volumen_estimado_m3": volumen_estimado,
                            "km_estimado": km_estimado,
                            "responsabilidad_atencion": responsabilidad,
                            "activo": True,
                        }
                    ]
                )
                new_row = normalize_need_rows(new_row, sistemas)
                upsert_rows("necesidades", new_row)
                st.success("Necesidad agregada.")
                st.rerun()



def get_secret_or_env(name: str, default: str = "") -> str:
    """Lee secretos desde Streamlit Cloud o variables de entorno locales."""
    try:
        value = st.secrets.get(name, "")
        if value:
            return str(value)
    except Exception:
        pass

    return os.getenv(name, default)


@st.cache_resource(show_spinner=False)
def supabase_storage_client():
    """
    Cliente Supabase para Storage.

    Usa SUPABASE_SERVICE_ROLE_KEY si existe.
    Si no existe, usa SUPABASE_KEY, pero en ese caso el bucket debe tener políticas
    que permitan administrar objetos con la llave anon.
    """
    url = get_secret_or_env("SUPABASE_URL")
    key = get_secret_or_env("SUPABASE_SERVICE_ROLE_KEY") or get_secret_or_env("SUPABASE_KEY")

    if not url or not key:
        raise RuntimeError(
            "No se encontraron SUPABASE_URL ni SUPABASE_SERVICE_ROLE_KEY/SUPABASE_KEY "
            "en los secrets de Streamlit."
        )

    return create_client(url, key)


def safe_filename(name: str) -> str:
    """Limpia nombres de archivo para evitar caracteres problemáticos en Supabase Storage."""
    name = re.sub(r"[^A-Za-z0-9_. -]", "_", str(name)).strip()
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name or "leccion_aprendida.pdf"


def storage_pdf_path(filename: str) -> str:
    """
    Genera una ruta única dentro del bucket.
    Ejemplo:
    pdfs/20260625_195500_analisis_ofertas.pdf
    """
    safe_name = safe_filename(filename)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{PDF_FOLDER}/{stamp}_{safe_name}"


def list_supabase_pdfs() -> list[dict]:
    """
    Lista PDFs almacenados en Supabase Storage.

    Retorna:
    [
        {
            "name": nombre visible,
            "path": ruta dentro del bucket,
            "size": tamaño,
            "updated_at": fecha
        }
    ]
    """
    client = supabase_storage_client()

    try:
        files = client.storage.from_(PDF_BUCKET).list(
            PDF_FOLDER,
            {
                "limit": 1000,
                "offset": 0,
                "sortBy": {"column": "name", "order": "asc"},
            },
        )
    except Exception as exc:
        st.error(
            "No se pudo listar el bucket de PDFs. Verifique que exista el bucket "
            f"`{PDF_BUCKET}` en Supabase Storage. Detalle: {exc}"
        )
        return []

    out: list[dict] = []

    for item in files or []:
        name = item.get("name", "")
        if not name.lower().endswith(".pdf"):
            continue

        metadata = item.get("metadata") or {}

        out.append(
            {
                "name": name,
                "path": f"{PDF_FOLDER}/{name}",
                "size": metadata.get("size"),
                "updated_at": item.get("updated_at") or item.get("created_at") or "",
            }
        )

    return out


def upload_pdf_to_supabase(uploaded_file) -> str:
    """Sube un PDF a Supabase Storage y retorna la ruta creada."""
    client = supabase_storage_client()
    path = storage_pdf_path(uploaded_file.name)
    data = uploaded_file.getvalue()

    if not data:
        raise RuntimeError(f"El archivo {uploaded_file.name} está vacío o no se pudo leer.")

    file_options_variants = [
        {"content-type": "application/pdf", "upsert": "false"},
        {"contentType": "application/pdf", "upsert": "false"},
    ]

    last_error = None
    for file_options in file_options_variants:
        try:
            response = client.storage.from_(PDF_BUCKET).upload(
                path,
                data,
                file_options=file_options,
            )

            # Algunas versiones retornan dict con error en lugar de lanzar excepción.
            if isinstance(response, dict) and response.get("error"):
                raise RuntimeError(str(response.get("error")))

            return path

        except TypeError as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise last_error

    return path


def delete_pdf_from_supabase(path: str) -> None:
    """Elimina un PDF desde Supabase Storage."""
    client = supabase_storage_client()
    client.storage.from_(PDF_BUCKET).remove([path])


def download_pdf_from_supabase(path: str) -> bytes:
    """Descarga bytes del PDF desde Supabase Storage."""
    client = supabase_storage_client()
    data = client.storage.from_(PDF_BUCKET).download(path)

    if isinstance(data, bytes):
        return data

    if hasattr(data, "read"):
        return data.read()

    return bytes(data)


def signed_pdf_url(path: str, expires_in: int = 3600) -> str:
    """
    Genera URL temporal para visualizar PDF.
    Funciona con bucket privado.
    """
    client = supabase_storage_client()
    result = client.storage.from_(PDF_BUCKET).create_signed_url(path, expires_in)

    if isinstance(result, dict):
        return (
            result.get("signedURL")
            or result.get("signedUrl")
            or result.get("signed_url")
            or ""
        )

    return ""


def render_supabase_pdf(path: str, height: int = 780) -> None:
    """
    Visualizador PDF desde Supabase Storage.

    En lugar de incrustar el PDF con iframe/object, se descarga desde Supabase
    y se renderiza cada página como imagen. Esto evita bloqueos del navegador
    dentro de Streamlit Cloud.
    """
    try:
        pdf_bytes = download_pdf_from_supabase(path)

        if not pdf_bytes:
            st.warning("El PDF se descargó vacío desde Supabase.")
            return

        signed_url = signed_pdf_url(path)

        if signed_url:
            st.link_button(
                "Abrir PDF en nueva pestaña",
                signed_url,
                use_container_width=False,
            )

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = doc.page_count

        if total_pages <= 0:
            st.warning("El archivo PDF no contiene páginas visibles.")
            doc.close()
            return

        st.caption(
            f"Visualización renderizada como imagen · {total_pages} página(s). "
            "Para texto seleccionable, use abrir en nueva pestaña o descargar."
        )

        col_a, col_b = st.columns([1, 3])

        with col_a:
            page_number = st.number_input(
                "Página",
                min_value=1,
                max_value=total_pages,
                value=1,
                step=1,
                key=f"pdf_page_{path}",
            )

        with col_b:
            zoom = st.slider(
                "Zoom de visualización",
                min_value=1.0,
                max_value=2.5,
                value=1.6,
                step=0.1,
                key=f"pdf_zoom_{path}",
            )

        page = doc.load_page(int(page_number) - 1)

        matrix = fitz.Matrix(float(zoom), float(zoom))
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        image_bytes = pix.tobytes("png")

        st.image(
            image_bytes,
            caption=f"Página {page_number} de {total_pages}",
            use_container_width=True,
        )

        doc.close()

    except Exception as exc:
        st.error(f"No se pudo visualizar el PDF desde Supabase: {exc}")


def format_file_size(size: object) -> str:
    try:
        size = float(size)
    except Exception:
        return "—"

    if size < 1024:
        return f"{size:.0f} B"
    if size < 1024**2:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024**2:.1f} MB"


def vista_lecciones() -> None:
    st.subheader("Vista 4 · Lecciones aprendidas y experiencias realizadas")
    st.caption(
        "Repositorio institucional de PDFs almacenado en Supabase Storage. "
        "Desde esta vista se pueden cargar, visualizar, descargar y eliminar archivos."
    )

    if not is_supabase_enabled():
        st.warning(
            "La administración de PDFs en Supabase requiere que la app esté conectada a Supabase. "
            "Revise los secrets SUPABASE_URL y SUPABASE_KEY."
        )
        return

    service_role_ok = bool(get_secret_or_env("SUPABASE_SERVICE_ROLE_KEY"))
    if not service_role_ok:
        st.warning(
            "No se detecta `SUPABASE_SERVICE_ROLE_KEY` en los secrets de Streamlit. "
            "Si el bucket es privado, la carga y el borrado pueden fallar por permisos. "
            "Agregue esa clave en Streamlit Cloud → Manage app → Settings → Secrets."
        )

    with st.expander("Diagnóstico de Supabase Storage", expanded=False):
        st.write(f"**Bucket:** `{PDF_BUCKET}`")
        st.write(f"**Carpeta:** `{PDF_FOLDER}`")
        st.write(f"**Service role configurado:** {'Sí' if service_role_ok else 'No'}")
        if st.button("Probar conexión con Storage", use_container_width=True):
            try:
                test_files = list_supabase_pdfs()
                st.success(f"Conexión correcta. PDFs encontrados: {len(test_files)}")
            except Exception as exc:
                st.error(f"Error de conexión con Supabase Storage: {exc}")

    with st.expander("Cargar nuevos PDFs", expanded=True):
        uploaded_files = st.file_uploader(
            "Seleccione uno o varios PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            key="pdf_upload_supabase",
        )

        if uploaded_files:
            st.caption(
                f"Archivos seleccionados: {len(uploaded_files)}. "
                "Presione el botón para cargarlos en Supabase Storage."
            )

            if st.button("Subir PDFs a Supabase", type="primary", use_container_width=True):
                ok_paths: list[str] = []
                errors: list[str] = []

                with st.spinner("Subiendo PDFs a Supabase Storage..."):
                    for uploaded_file in uploaded_files:
                        try:
                            created_path = upload_pdf_to_supabase(uploaded_file)
                            ok_paths.append(created_path)
                        except Exception as exc:
                            errors.append(f"{uploaded_file.name}: {exc}")

                if ok_paths:
                    st.success(f"Se cargaron {len(ok_paths)} PDF en Supabase Storage.")
                    with st.expander("Rutas cargadas", expanded=False):
                        for path in ok_paths:
                            st.write(f"- `{path}`")

                if errors:
                    st.error("Algunos archivos no pudieron cargarse. Detalle:")
                    for err in errors:
                        st.write(f"- {err}")
                    st.info(
                        "Si el error indica permisos, revise que exista el bucket "
                        f"`{PDF_BUCKET}` y que `SUPABASE_SERVICE_ROLE_KEY` esté configurado en Streamlit Secrets."
                    )

    files = list_supabase_pdfs()

    if not files:
        st.info("No hay PDFs almacenados en Supabase Storage.")
        return

    col_list, col_view = st.columns([1, 2])

    with col_list:
        st.markdown("#### Archivos PDF en Supabase")

        selected = st.selectbox(
            "Seleccione un PDF",
            files,
            format_func=lambda x: x["name"],
            label_visibility="collapsed",
            key="selected_pdf_supabase",
        )

        if selected is None:
            st.info("Seleccione un PDF.")
            return

        st.write(f"**Archivo:** {selected['name']}")
        st.caption(f"Ruta Supabase: `{selected['path']}`")
        st.caption(f"Tamaño: {format_file_size(selected.get('size'))}")

        try:
            pdf_bytes = download_pdf_from_supabase(selected["path"])
            st.download_button(
                "Descargar PDF seleccionado",
                data=pdf_bytes,
                file_name=selected["name"],
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as exc:
            st.warning(f"No se pudo preparar la descarga: {exc}")

        st.divider()

        st.markdown("##### Eliminar PDF")

        confirm_delete = st.checkbox(
            "Confirmo que deseo eliminar este PDF de Supabase",
            key=f"confirm_delete_supabase_{selected['path']}",
        )

        if st.button(
            "Eliminar PDF seleccionado",
            type="secondary",
            disabled=not confirm_delete,
            use_container_width=True,
            key=f"delete_pdf_supabase_{selected['path']}",
        ):
            try:
                delete_pdf_from_supabase(selected["path"])
                st.success("PDF eliminado correctamente de Supabase. Actualice o cambie de vista para refrescar la lista.")
            except Exception as exc:
                st.error(f"No se pudo eliminar el PDF: {exc}")

    with col_view:
        st.markdown(f"#### Visualizador · {selected['name']}")
        render_supabase_pdf(selected["path"])


def admin_sidebar() -> None:
    st.sidebar.markdown("### Configuración")

    mode = "Supabase" if is_supabase_enabled() else "Local CSV"
    st.sidebar.info(f"Modo de datos: **{mode}**")

    with st.sidebar.expander("Carga inicial / mantenimiento"):
        st.caption(
            "Use esta opción después de crear las tablas en Supabase. "
            "No publique claves en GitHub."
        )

        overwrite = st.checkbox("Sobrescribir datos existentes", value=False)

        if st.button("Cargar datos base a Supabase", disabled=not is_supabase_enabled()):
            try:
                result = seed_supabase(overwrite=overwrite)
                st.success(
                    "Datos base cargados: "
                    + ", ".join([f"{k}={v}" for k, v in result.items()])
                )
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo cargar datos base: {exc}")

        if st.button("Restablecer CSV local", disabled=is_supabase_enabled()):
            deleted = reset_local_runtime()

            if deleted:
                st.success("Datos locales restablecidos: " + ", ".join(deleted))
            else:
                st.info("No había archivos locales por restablecer.")

            st.rerun()


def main() -> None:
    title()
    admin_sidebar()

    view = st.sidebar.radio(
        "Vista",
        [
            "1. Gestión de proyectos",
            "2. Capacidad hídrica GAM",
            "3. Necesidades de inversión",
            "4. Lecciones aprendidas",
        ],
    )

    if view.startswith("1"):
        vista_proyectos()
    elif view.startswith("2"):
        vista_capacidad()
    elif view.startswith("3"):
        vista_necesidades()
    else:
        vista_lecciones()


if __name__ == "__main__":
    main()
