from __future__ import annotations

import pandas as pd
import streamlit as st

import seguimiento_necesidades_v2 as base
from ajustes_vistas_32_33 import STRICT_DISPLAY_COLUMNS


# La Vista 3.3 mantiene el orden institucional solicitado y agrega únicamente
# dos campos de consulta al inicio: ID de la necesidad y categoría/clasificación
# proveniente de la misma información utilizada en la Vista 3.2.
DISPLAY_COLUMNS = [
    "id_necesidad",
    "categoria_clasificacion",
    *STRICT_DISPLAY_COLUMNS,
]


def _prepare_work() -> pd.DataFrame:
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
            category_by_id[int(raw_id)] = base._clean_text(row.get("tipo_de_proyecto"))

    work = work.copy()
    work["id_necesidad"] = pd.to_numeric(work["necesidad_id"], errors="coerce").astype("Int64")
    work["categoria_clasificacion"] = work["necesidad_id"].map(category_by_id).fillna("")
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
        "Incluye el ID de la necesidad y la categoría/clasificación utilizada en la Vista 3.2."
    )

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
        placeholder="ID, categoría, memo, cantón, distrito, sistema…",
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
        "La categoría/clasificación corresponde a la clasificación operativa de la necesidad "
        "mostrada en la Vista 3.2."
    )

    st.markdown("##### Banco de Ideas de Proyectos AyA")
    editor = filtered[["necesidad_id", *DISPLAY_COLUMNS]].copy().set_index("necesidad_id")

    disabled = [
        "id_necesidad",
        "categoria_clasificacion",
        "ubicacion_provincia",
        "ubicacion_canton",
        "distritos",
        "poblacion_beneficiada",
        "codigo_nombre_sistema",
        "servicios_atendidos",
        "condicion_hidrica",
        "estado_sistema_bh",
    ]

    edited = st.data_editor(
        editor,
        use_container_width=True,
        hide_index=True,
        height=700,
        num_rows="fixed",
        disabled=disabled,
        column_config=_column_config(),
        key="editor_banco_ideas_aya_v3",
    )

    if st.button(
        "Guardar cambios de seguimiento",
        type="primary",
        key="guardar_banco_ideas_aya_v3",
    ):
        try:
            base._save_tracking(edited)
        except Exception as exc:
            st.error(
                "No fue posible guardar el seguimiento. "
                "Verifique que `sql/09_formato_banco_ideas_seguimiento.sql` haya sido ejecutado. "
                f"Detalle: {exc}"
            )
        else:
            st.success("Seguimiento del Banco de Ideas guardado correctamente.")
            st.rerun()
