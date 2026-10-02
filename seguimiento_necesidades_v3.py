from __future__ import annotations

import re

import pandas as pd
import streamlit as st

import seguimiento_necesidades_v2 as base
from ajustes_vistas_32_33 import STRICT_DISPLAY_COLUMNS
from database import clear_cache, data_revision


# Orden de la Vista 3.3. Se conservan las 24 columnas institucionales y se
# incorporan al inicio los campos de identificación/clasificación solicitados.
# Entre Categoría y Tipo de proyecto se restituyen las columnas del formato
# EST-02-02-F4 que ya existen en la estructura de seguimiento.
DISPLAY_COLUMNS = [
    "id_necesidad",
    "categoria_clasificacion",
    "tipo_licitacion",
    "codigo_interno",
    "unidad_solicitante",
    "unidad_formula_idea",
    "posible_fuente_financiamiento",
    "idea_proyecto",
    "descripcion_idea",
    *STRICT_DISPLAY_COLUMNS,
]

AUTOMATIC_COLUMNS = [
    "id_necesidad", "categoria_clasificacion", "idea_proyecto", "descripcion_idea",
    "ubicacion_provincia", "ubicacion_canton", "distritos", "poblacion_beneficiada",
    "codigo_nombre_sistema", "servicios_atendidos", "condicion_hidrica", "estado_sistema_bh",
]

SEARCH_COLUMNS = [
    "id_necesidad", "categoria_clasificacion", "tipo_licitacion", "codigo_interno",
    "unidad_solicitante", "unidad_formula_idea", "posible_fuente_financiamiento",
    "idea_proyecto", "descripcion_idea", "memo_formulario_necesidad",
    "ubicacion_provincia", "ubicacion_canton", "distritos", "comunidades",
    "codigo_nombre_sistema", "descripcion_avance",
]


_SYSTEM_CODE_RE = re.compile(
    r"\bME\s*-?\s*A\s*-?\s*(\d{1,2})\b|\bMEA\s*(\d{1,2})\b",
    flags=re.I,
)


def _unique_system_population(work: pd.DataFrame) -> tuple[float, list[str], list[str]]:
    """Suma la población una sola vez por código de sistema presente en el filtro."""
    codes: set[str] = set()
    labels = work.get("codigo_nombre_sistema", pd.Series(dtype=object))
    for value in labels.fillna("").astype(str):
        for match in _SYSTEM_CODE_RE.finditer(value):
            digits = match.group(1) or match.group(2)
            if digits:
                codes.add(f"MEA{int(digits):02d}")

    total = 0.0
    missing: list[str] = []
    for code in sorted(codes):
        system = base.SYSTEM_DATA.get(code)
        population = pd.to_numeric(
            system.get("poblacion") if isinstance(system, dict) else None,
            errors="coerce",
        )
        if pd.isna(population):
            missing.append(code)
            continue
        total += float(population)

    return total, sorted(codes), missing


@st.cache_data(show_spinner=False, ttl=120, max_entries=4)
def _prepare_work_cached(revision: int) -> pd.DataFrame:
    # ``revision`` forma parte de la llave de caché. La capa de datos la aumenta
    # después de cualquier inserción, edición o eliminación hecha por la app.
    del revision
    work = base._prepare_work()
    if work.empty:
        return work

    needs = base.read_table("necesidades")
    category_by_id: dict[int, str] = {}
    if not needs.empty and "id" in needs.columns:
        for _, row in needs.iterrows():
            raw_id = pd.to_numeric(row.get("id"), errors="coerce")
            if pd.isna(raw_id):
                continue
            nid = int(raw_id)
            category_by_id[nid] = base._clean_text(row.get("tipo_de_proyecto"))

    work = work.copy()
    work["id_necesidad"] = pd.to_numeric(work["necesidad_id"], errors="coerce").astype("Int64")
    work["categoria_clasificacion"] = work["necesidad_id"].map(category_by_id).fillna("")

    # Comunidades es un campo de ingreso manual. Ignorar las ubicaciones y
    # descripciones inferidas por la versión base; una celda sin dato guardado
    # queda en blanco y puede editarse, incluso para borrar un valor anterior.
    tracking = base.read_optional_table("necesidades_seguimiento")
    communities_by_id: dict[int, str] = {}
    if not tracking.empty and {"necesidad_id", "comunidades"}.issubset(tracking.columns):
        for record in tracking[["necesidad_id", "comunidades"]].to_dict("records"):
            nid = pd.to_numeric(record["necesidad_id"], errors="coerce")
            if pd.notna(nid):
                communities_by_id[int(nid)] = base._clean_text(record["comunidades"])
    work["comunidades"] = work["necesidad_id"].map(communities_by_id).fillna("")

    # La normalización del texto no depende del filtro: se hace una sola vez
    # por revisión, en vez de recorrer y normalizar toda la matriz al buscar.
    work["_search_text"] = (
        work[SEARCH_COLUMNS].fillna("").astype(str).agg(" ".join, axis=1)
        .map(base._normalize_text)
    )
    return work


def _prepare_work() -> pd.DataFrame:
    """Devuelve la matriz vigente conservando la interfaz usada por 3.3 y 3.4."""
    return _prepare_work_cached(data_revision())


def _column_config() -> dict:
    config = base._column_config()
    config["comunidades"] = st.column_config.TextColumn(
        "Comunidades", width="large",
        help="Ingreso manual de comunidades beneficiadas. Puede dejarse en blanco.",
    )
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
    # El editor de Streamlit dibuja la tabla en canvas y no admite estilos
    # de celda en columnas editables. Los indicadores de color del encabezado
    # identifican ambos grupos sin afectar la edición ni agregar otra tabla.
    for column in DISPLAY_COLUMNS:
        automatic = column in AUTOMATIC_COLUMNS
        definition = config[column]
        definition["label"] = f"{'🟦' if automatic else '🟩'} {definition['label']}"
        description = (
            "Campo automático. Solo lectura en esta vista."
            if automatic else "Campo editable. Guarde los cambios de seguimiento para conservarlos."
        )
        previous_help = definition.get("help")
        definition["help"] = f"{description} {previous_help}" if previous_help else description
        definition["disabled"] = automatic
    return config


def _changed_tracking_rows(edited: pd.DataFrame, original: pd.DataFrame) -> pd.DataFrame:
    """Envía solo filas editadas y compara únicamente campos persistidos."""
    columns = [column for column in base.TRACKING_FIELDS if column in edited.columns]
    before = original.reindex(edited.index)[columns].copy()
    after = edited[columns].copy()
    for column in columns:
        if column == "fecha_recurso_amparo":
            before[column] = pd.to_datetime(before[column], errors="coerce").dt.normalize()
            after[column] = pd.to_datetime(after[column], errors="coerce").dt.normalize()
        elif column in {"priorizacion_region", "estado_sistema_ba"}:
            before[column] = pd.to_numeric(before[column], errors="coerce")
            after[column] = pd.to_numeric(after[column], errors="coerce")
        else:
            before[column] = before[column].map(base._clean_text)
            after[column] = after[column].map(base._clean_text)
    equal = before.eq(after).fillna(False) | (before.isna() & after.isna())
    return edited.loc[~equal.all(axis=1)].copy()


def vista_seguimiento_necesidades() -> None:
    st.subheader("Vista 3.3 · Banco de Ideas de Proyectos AyA")
    st.caption(
        "Formato EST-02-02-F4 · Seguimiento de necesidades GAM. "
        "Incluye ID, categoría/clasificación y los campos institucionales del Banco de Ideas."
    )

    if st.button("Actualizar datos", key="banco_refresh_data"):
        clear_cache()
        _prepare_work_cached.clear()
        st.rerun()

    work = _prepare_work()
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
        filtered = filtered[
            filtered["_search_text"].str.contains(normalized_keyword, regex=False, na=False)
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
    unique_population, unique_system_codes, missing_population_codes = (
        _unique_system_population(filtered)
    )
    m4.metric(
        "Población asociada*",
        f"{unique_population:,.0f}",
        help=(
            f"Suma de {len(unique_system_codes)} sistema(s) único(s) presentes "
            "en el resultado filtrado."
        ),
    )

    st.caption(
        "* La población asociada se suma una sola vez por código de sistema único presente "
        "en el resultado filtrado; no se vuelve a sumar por cada necesidad. "
        "Comunidades es un campo de ingreso manual; permanece en blanco hasta registrar un valor."
    )
    if missing_population_codes:
        st.warning(
            "No se encontró población de referencia para: "
            + ", ".join(missing_population_codes)
            + ". Estos sistemas no se incluyeron en el total."
        )

    st.markdown("##### Banco de Ideas de Proyectos AyA")
    st.caption("🟦 Campos automáticos · Solo lectura     🟩 Campos editables · Ingreso o ajuste manual")
    editor = filtered[["necesidad_id", *DISPLAY_COLUMNS]].copy().set_index("necesidad_id")

    # El formulario agrupa las ediciones. Sin él, cada cambio de una celda
    # vuelve a ejecutar y renderizar toda la vista de más de treinta columnas.
    with st.form("form_banco_ideas_aya_v5", border=False):
        edited = st.data_editor(
            editor,
            use_container_width=True,
            hide_index=True,
            height=700,
            num_rows="fixed",
            disabled=AUTOMATIC_COLUMNS,
            column_config=_column_config(),
            key="editor_banco_ideas_aya_v5",
        )
        save_requested = st.form_submit_button(
            "Guardar cambios de seguimiento",
            type="primary",
        )

    if save_requested:
        changed = _changed_tracking_rows(edited, editor)
        if changed.empty:
            st.info("No hay cambios de seguimiento para guardar.")
            return
        try:
            base._save_tracking(changed)
        except Exception as exc:
            st.error(
                "No fue posible guardar el seguimiento. "
                "Verifique que `sql/09_formato_banco_ideas_seguimiento.sql` haya sido ejecutado. "
                f"Detalle: {exc}"
            )
        else:
            _prepare_work_cached.clear()
            st.success("Seguimiento del Banco de Ideas guardado correctamente.")
            st.rerun()
