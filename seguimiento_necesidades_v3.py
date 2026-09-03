from __future__ import annotations

import re
from typing import Iterable

import pandas as pd
import streamlit as st

import seguimiento_necesidades_v2 as base
from ajustes_vistas_32_33 import STRICT_DISPLAY_COLUMNS
from database import data_revision


# Orden de la Vista 3.3. Se conservan las 24 columnas institucionales y se
# incorporan al inicio los campos de identificación/clasificación solicitados.
# Entre Categoría y Tipo de proyecto se restituyen las columnas del formato
# EST-02-02-F4 que ya existen en la estructura de seguimiento.
DISPLAY_COLUMNS = [
    "id_necesidad",
    "categoria_clasificacion",
    "codigo_interno",
    "unidad_solicitante",
    "unidad_formula_idea",
    "posible_fuente_financiamiento",
    "idea_proyecto",
    *STRICT_DISPLAY_COLUMNS,
]


_COMMUNITY_PREFIX_RE = re.compile(
    r"\b(?:Calle|Barrio|Urbanizaci[oó]n|Urb\.?|Residencial|Comunidad)\s+"
    r"([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9'’.-]*"
    r"(?:\s+(?:de|del|la|las|los|el|y|[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ0-9'’.-]*)){0,5})",
    flags=re.I,
)
_DIRECTION_PLACE_RE = re.compile(
    r"\b(?:hacia|desde|en|para)\s+(?:el\s+|la\s+|los\s+|las\s+)?"
    r"((?:[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ'’.-]*|de|del|la|las|los|el)"
    r"(?:\s+(?:[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ'’.-]*|de|del|la|las|los|el|y)){0,4})"
)
_GENERIC_COMMUNITY_RE = re.compile(
    r"^(?:zona\s*\d+|zona|sector|sector alto|sector bajo|parte alta|parte baja|"
    r"todos los sistemas aya|acueducto metropolitano)$",
    flags=re.I,
)
_INFRA_PREFIX_RE = re.compile(
    r"^(?:TA|TQ|PP|PTAR|Planta(?:\s+Potabilizadora)?|Tanque|Pozo|Fuente|"
    r"Captaci[oó]n|Estaci[oó]n(?:\s+de\s+Bombeo)?|Desarenador)\s+",
    flags=re.I,
)
_PROSE_TERMS = {
    "fase", "responsable", "puntaje", "horizonte", "ruta propuesta", "impacto principal",
    "ejecución", "ejecucion", "proyecto", "iniciativa", "necesidad", "diseño", "diseno",
    "construcción", "construccion", "contratación", "contratacion", "licitación", "licitacion",
    "validar", "definir", "confirmar", "mejorar", "incrementar", "implementar", "incorporar",
}


def _clean_candidate(value: object) -> str:
    text = base._clean_text(value)
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip(" ,;:.-")
    text = re.sub(r"^(?:sector(?:es)?\s+(?:de\s+|del\s+)?)", "", text, flags=re.I).strip()
    text = _INFRA_PREFIX_RE.sub("", text).strip()
    text = re.sub(r"\s+(?:para|mediante|debido|porque|con el fin|con la finalidad)\b.*$", "", text, flags=re.I).strip()
    text = re.sub(r"\s+y$", "", text, flags=re.I).strip()
    if not text or _GENERIC_COMMUNITY_RE.match(text):
        return ""
    if len(text) > 55 or len(text.split()) > 7:
        return ""
    normalized = base._normalize_text(text)
    if any(term in normalized for term in _PROSE_TERMS):
        return ""
    return text


def _unique(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_candidate(value)
        key = base._normalize_text(text)
        if text and key and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _extract_community_names(text: object) -> list[str]:
    source = base._clean_text(text)
    if not source:
        return []
    candidates: list[str] = []

    # Nombres explícitos: Calle La Mina, Urbanización Leiva Urcuyo, Barrio X, etc.
    for match in _COMMUNITY_PREFIX_RE.finditer(source):
        full = match.group(0).strip(" ,;:.-")
        candidates.append(full)

    # Referencias direccionales suelen contener el sector beneficiado:
    # "hacia San Bosco", "en Rancho Redondo", "desde Ciudad Colón".
    for match in _DIRECTION_PLACE_RE.finditer(source):
        candidates.append(match.group(1))

    return _unique(candidates)


def _compact_communities(existing: object, need_row: pd.Series | None, geo_row: pd.Series) -> str:
    candidates: list[str] = []

    # Primero se aprovechan comunidades/ubicaciones ya registradas, pero nunca
    # se conserva una frase larga como comunidad.
    existing_text = base._clean_text(existing)
    if existing_text:
        for part in re.split(r"\s*[;|,]\s*", existing_text):
            candidates.append(part)
        candidates.extend(_extract_community_names(existing_text))

    if need_row is not None:
        for field in (
            "objetivo_de_la_iniciativa",
            "breve_descripcion",
            "observacion",
            "principal_reto_por_superar",
            "zona",
        ):
            candidates.extend(_extract_community_names(need_row.get(field)))

    cleaned = _unique(candidates)

    # Provincia, cantón y distrito ya tienen columnas propias; no se repiten
    # como comunidad cuando el texto recuperado coincide exactamente con ellos.
    administrative = {
        base._normalize_text(item)
        for field in ("ubicacion_provincia", "ubicacion_canton", "distritos")
        for item in re.split(r"\s*[,;]\s*", base._clean_text(geo_row.get(field)))
        if base._clean_text(item)
    }
    cleaned = [item for item in cleaned if base._normalize_text(item) not in administrative]

    return ", ".join(cleaned[:8])


@st.cache_data(show_spinner=False, ttl=120)
def _prepare_work(revision: int) -> pd.DataFrame:
    # ``revision`` forma parte de la llave de caché. La capa de datos la aumenta
    # después de cualquier inserción, edición o eliminación hecha por la app.
    del revision
    work = base._prepare_work()
    if work.empty:
        return work

    needs = base.read_table("necesidades")
    category_by_id: dict[int, str] = {}
    need_by_id: dict[int, pd.Series] = {}
    if not needs.empty and "id" in needs.columns:
        for _, row in needs.iterrows():
            raw_id = pd.to_numeric(row.get("id"), errors="coerce")
            if pd.isna(raw_id):
                continue
            nid = int(raw_id)
            need_by_id[nid] = row
            category_by_id[nid] = base._clean_text(row.get("tipo_de_proyecto"))

    work = work.copy()
    work["id_necesidad"] = pd.to_numeric(work["necesidad_id"], errors="coerce").astype("Int64")
    work["categoria_clasificacion"] = work["necesidad_id"].map(category_by_id).fillna("")

    # Comunidades: solo nombres cortos y específicos. Se descarta prosa de
    # seguimiento y se intenta recuperar automáticamente nombres desde la
    # descripción/objetivo/observaciones de la necesidad.
    for idx, row in work.iterrows():
        raw_id = pd.to_numeric(row.get("necesidad_id"), errors="coerce")
        if pd.isna(raw_id):
            continue
        nid = int(raw_id)
        work.at[idx, "comunidades"] = _compact_communities(
            row.get("comunidades"),
            need_by_id.get(nid),
            row,
        )

    return work


def _column_config() -> dict:
    config = base._column_config()
    config.update(
        {
            "id_necesidad": st.column_config.NumberColumn(
                "ID de la necesidad",
                format="%d",
                width="small",
            ),
            "categoria_clasificacion": st.column_config.TextColumn(
                "Categoría / clasificación",
                width="large",
                help="Clasificación de la necesidad utilizada en la Vista 3.2.",
            ),
        }
    )
    return config


def vista_seguimiento_necesidades() -> None:
    st.subheader("Vista 3.3 · Banco de Ideas de Proyectos AyA")
    st.caption(
        "Formato EST-02-02-F4 · Seguimiento de necesidades GAM. "
        "Incluye ID, categoría/clasificación y los campos institucionales del Banco de Ideas."
    )

    work = _prepare_work(data_revision())
    if work.empty:
        st.warning("No hay necesidades disponibles para seguimiento.")
        return

    st.markdown("##### Filtros")
    f1, f2, f3 = st.columns([1.0, 1.6, 1.4])
    id_options = sorted(
        pd.to_numeric(work["id_necesidad"], errors="coerce").dropna().astype(int).unique().tolist()
    )
    selected_ids = f1.multiselect(
        "ID de necesidad",
        id_options,
        key="banco_filter_need_id",
        placeholder="Todos",
    )
    categories = sorted(
        {value for value in work["categoria_clasificacion"].fillna("").astype(str).str.strip() if value}
    )
    selected_categories = f2.multiselect(
        "Categoría / clasificación",
        categories,
        key="banco_filter_category",
        placeholder="Todas",
    )
    selected_states = f3.multiselect(
        "Estado Actual (AyA)",
        base.ESTADO_AYA_OPTIONS,
        key="banco_filter_state",
    )

    f4, f5, f6 = st.columns([1.3, 2.0, 2.4])
    provinces = sorted(
        {
            p.strip()
            for text in work["ubicacion_provincia"].fillna("")
            for p in str(text).split(",")
            if p.strip()
        }
    )
    selected_provinces = f4.multiselect(
        "Provincia",
        provinces,
        key="banco_filter_province",
    )
    systems = sorted(
        {
            label.strip()
            for text in work["codigo_nombre_sistema"].fillna("")
            for label in str(text).split(";")
            if label.strip()
        }
    )
    selected_systems = f5.multiselect(
        "Sistema",
        systems,
        key="banco_filter_system",
    )
    keyword = f6.text_input(
        "Buscar",
        placeholder="ID, código, idea, categoría, memo, comunidad, distrito, sistema…",
        key="banco_filter_text",
    )

    filtered = work.copy()
    if selected_ids:
        filtered = filtered[
            pd.to_numeric(filtered["id_necesidad"], errors="coerce").isin(selected_ids)
        ]
    if selected_categories:
        filtered = filtered[
            filtered["categoria_clasificacion"].isin(selected_categories)
        ]
    if selected_states:
        filtered = filtered[filtered["estado_actual_aya"].isin(selected_states)]
    if selected_provinces:
        selected = {item.casefold() for item in selected_provinces}
        filtered = filtered[
            filtered["ubicacion_provincia"].fillna("").apply(
                lambda text: bool(
                    selected
                    & {
                        p.strip().casefold()
                        for p in str(text).split(",")
                        if p.strip()
                    }
                )
            )
        ]
    if selected_systems:
        selected = set(selected_systems)
        filtered = filtered[
            filtered["codigo_nombre_sistema"].fillna("").apply(
                lambda text: bool(
                    selected
                    & {
                        p.strip()
                        for p in str(text).split(";")
                        if p.strip()
                    }
                )
            )
        ]

    normalized_keyword = base._normalize_text(keyword)
    if normalized_keyword:
        search_cols = [
            "id_necesidad",
            "categoria_clasificacion",
            "codigo_interno",
            "unidad_solicitante",
            "unidad_formula_idea",
            "posible_fuente_financiamiento",
            "idea_proyecto",
            "memo_formulario_necesidad",
            "ubicacion_provincia",
            "ubicacion_canton",
            "distritos",
            "comunidades",
            "codigo_nombre_sistema",
            "descripcion_avance",
        ]
        searchable = filtered[search_cols].fillna("").astype(str).agg(" ".join, axis=1)
        filtered = filtered[
            searchable.apply(lambda value: normalized_keyword in base._normalize_text(value))
        ]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ideas / necesidades", f"{len(filtered):,}")
    m2.metric(
        "En lista de espera",
        f"{int(filtered['estado_actual_aya'].eq('En lista de espera').sum()):,}",
    )
    m3.metric(
        "En formulación",
        f"{int(filtered['estado_actual_aya'].eq('Formulación de Iniciativa').sum()):,}",
    )
    with_population = pd.to_numeric(
        filtered["poblacion_beneficiada"], errors="coerce"
    ).fillna(0).sum()
    m4.metric("Población asociada*", f"{with_population:,.0f}")

    st.caption(
        "* Población y servicios se estiman con la información del sistema o sistemas asociados. "
        "Comunidades muestra únicamente nombres específicos recuperables de las ubicaciones o "
        "descripciones; no se asume que todas las comunidades de un distrito sean beneficiarias."
    )

    st.markdown("##### Banco de Ideas de Proyectos AyA")
    editor = filtered[["necesidad_id", *DISPLAY_COLUMNS]].copy().set_index("necesidad_id")

    disabled = [
        "id_necesidad",
        "categoria_clasificacion",
        "idea_proyecto",
        "ubicacion_provincia",
        "ubicacion_canton",
        "distritos",
        "poblacion_beneficiada",
        "codigo_nombre_sistema",
        "servicios_atendidos",
        "condicion_hidrica",
        "estado_sistema_bh",
    ]

    # El formulario agrupa las ediciones. Sin él, cada cambio de una celda
    # vuelve a ejecutar y renderizar toda la vista de más de treinta columnas.
    with st.form("form_banco_ideas_aya_v5", border=False):
        edited = st.data_editor(
            editor,
            use_container_width=True,
            hide_index=True,
            height=700,
            num_rows="fixed",
            disabled=disabled,
            column_config=_column_config(),
            key="editor_banco_ideas_aya_v5",
        )
        save_requested = st.form_submit_button(
            "Guardar cambios de seguimiento",
            type="primary",
        )

    if save_requested:
        try:
            base._save_tracking(edited)
        except Exception as exc:
            st.error(
                "No fue posible guardar el seguimiento. "
                "Verifique que `sql/09_formato_banco_ideas_seguimiento.sql` haya sido ejecutado. "
                f"Detalle: {exc}"
            )
        else:
            _prepare_work.clear()
            st.success("Seguimiento del Banco de Ideas guardado correctamente.")
            st.rerun()
