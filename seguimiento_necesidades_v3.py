from __future__ import annotations

import re

import pandas as pd
import streamlit as st

import seguimiento_necesidades_v2 as base
from ajustes_vistas_32_33 import STRICT_DISPLAY_COLUMNS
from app_core import ATENCION_NECESIDAD_OPTIONS, COSTO_NECESIDAD_OPTIONS, NECESIDAD_LABELS
from database import clear_cache, data_revision, get_supabase_client, upsert_rows


# Orden de la Vista 3.3. Se conservan las 24 columnas institucionales y se
# incorporan al inicio los campos de identificación/clasificación solicitados.
# Entre Categoría y Tipo de proyecto se restituyen las columnas del formato
# EST-02-02-F4 que ya existen en la estructura de seguimiento.
DISPLAY_COLUMNS = [
    "id_necesidad",
    "categoria_clasificacion",
    "tipo_licitacion",
    "costo",
    "caudal_estimado_lps",
    "volumen_estimado_m3",
    "km_estimado",
    "responsabilidad_atencion",
    "codigo_interno",
    "unidad_solicitante",
    "unidad_formula_idea",
    "posible_fuente_financiamiento",
    "idea_proyecto",
    "descripcion_idea",
    *STRICT_DISPLAY_COLUMNS,
]
# Las coordenadas corresponden a las ubicaciones de 3.2; se mantienen en
# solo lectura aquí porque una necesidad puede tener varios puntos.
DISPLAY_COLUMNS[DISPLAY_COLUMNS.index("comunidades"):DISPLAY_COLUMNS.index("comunidades")] = [
    "latitud", "longitud",
]
NEED_EDIT_FIELDS = (
    "categoria_clasificacion", "costo", "caudal_estimado_lps",
    "volumen_estimado_m3", "km_estimado", "responsabilidad_atencion",
)
# La columna visible tiene el mismo significado que tipo_de_proyecto de la Vista 3.1.
# Se persiste allí, nunca como una segunda categoría en necesidades_seguimiento.
NEED_DB_FIELDS = {"categoria_clasificacion": "tipo_de_proyecto"}
NEED_NUMERIC_FIELDS = ("caudal_estimado_lps", "volumen_estimado_m3", "km_estimado")

AUTOMATIC_COLUMNS = [
    "id_necesidad", "idea_proyecto", "descripcion_idea",
    "ubicacion_provincia", "ubicacion_canton", "distritos", "poblacion_beneficiada",
    "codigo_nombre_sistema", "servicios_atendidos", "condicion_hidrica", "estado_sistema_bh",
    "latitud", "longitud",
]

SEARCH_COLUMNS = [
    "id_necesidad", "categoria_clasificacion", "tipo_licitacion", "codigo_interno",
    "unidad_solicitante", "unidad_formula_idea", "posible_fuente_financiamiento",
    "idea_proyecto", "descripcion_idea", "memo_formulario_necesidad",
    "ubicacion_provincia", "ubicacion_canton", "distritos", "comunidades",
    "codigo_nombre_sistema", "descripcion_avance",
    *NEED_EDIT_FIELDS, "latitud", "longitud",
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
    work = work.copy()
    work["id_necesidad"] = pd.to_numeric(work["necesidad_id"], errors="coerce").astype("Int64")

    # Vinculación con los mismos datos persistidos y editables desde Vista 3.1.
    # Se leen de necesidades (no de necesidades_seguimiento) para evitar copias
    # inconsistentes y conservar la edición bidireccional entre ambas vistas.
    need_values = {}
    for _, record in needs.iterrows():
        raw_id = pd.to_numeric(record.get("id"), errors="coerce")
        if pd.notna(raw_id):
            need_values[int(raw_id)] = record
    for field in NEED_EDIT_FIELDS:
        source_field = NEED_DB_FIELDS.get(field, field)
        lookup = {
            nid: row.get(source_field) for nid, row in need_values.items()
        }
        work[field] = work["necesidad_id"].map(lookup)
        if field in NEED_NUMERIC_FIELDS:
            work[field] = pd.to_numeric(work[field], errors="coerce")
        else:
            work[field] = work[field].map(base._clean_text)

    # Coordenadas WGS84 de la vista 3.2: cada par corresponde al mismo punto.
    # Para varias ubicaciones se conservan en el mismo orden con separador ';'.
    locations = base.read_optional_table("necesidades_ubicaciones")
    points_by_need: dict[int, list[tuple[float, float]]] = {}
    if not locations.empty and {"necesidad_id", "latitud", "longitud"}.issubset(locations.columns):
        if "id" in locations.columns:
            locations = locations.sort_values("id", kind="stable")
        for _, point in locations.iterrows():
            nid = pd.to_numeric(point.get("necesidad_id"), errors="coerce")
            lat = pd.to_numeric(point.get("latitud"), errors="coerce")
            lon = pd.to_numeric(point.get("longitud"), errors="coerce")
            if pd.isna(nid) or pd.isna(lat) or pd.isna(lon):
                continue
            if not (8.0 <= float(lat) <= 12.0 and -86.5 <= float(lon) <= -82.0):
                continue
            pair = (round(float(lat), 7), round(float(lon), 7))
            pairs = points_by_need.setdefault(int(nid), [])
            if pair not in pairs:
                pairs.append(pair)
    work["latitud"] = work["necesidad_id"].map({
        nid: "; ".join(f"{lat:.7f}" for lat, _ in points)
        for nid, points in points_by_need.items()
    }).fillna("")
    work["longitud"] = work["necesidad_id"].map({
        nid: "; ".join(f"{lon:.7f}" for _, lon in points)
        for nid, points in points_by_need.items()
    }).fillna("")

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
    current_cost_values = base.read_table("necesidades").get("costo", pd.Series(dtype=object))
    cost_options = list(dict.fromkeys([
        *COSTO_NECESIDAD_OPTIONS,
        *(base._clean_text(value) for value in current_cost_values
          if base._clean_text(value)),
    ]))
    config.update({
        "costo": st.column_config.SelectboxColumn(
            NECESIDAD_LABELS["costo"], options=cost_options, required=False, width="large",
        ),
        "caudal_estimado_lps": st.column_config.NumberColumn(
            NECESIDAD_LABELS["caudal_estimado_lps"], min_value=0.0, step=1.0, format="%.2f",
        ),
        "volumen_estimado_m3": st.column_config.NumberColumn(
            NECESIDAD_LABELS["volumen_estimado_m3"], min_value=0.0, step=10.0, format="%.2f",
        ),
        "km_estimado": st.column_config.NumberColumn(
            NECESIDAD_LABELS["km_estimado"], min_value=0.0, step=0.1, format="%.3f",
        ),
        "responsabilidad_atencion": st.column_config.SelectboxColumn(
            "Clasificación de la atención",
            options=list(dict.fromkeys([
                *ATENCION_NECESIDAD_OPTIONS,
                *(base._clean_text(value) for value in
                  base.read_table("necesidades").get("responsabilidad_atencion", pd.Series(dtype=object))
                  if base._clean_text(value)),
            ])),
            required=False, width="large",
        ),
        "latitud": st.column_config.TextColumn(
            "Latitud (WGS84)", width="medium",
            help="Coordenadas registradas en Vista 3.2. Si hay varios puntos se muestran separados por punto y coma; para editarlos use Vista 3.2.",
        ),
        "longitud": st.column_config.TextColumn(
            "Longitud (WGS84)", width="medium",
            help="Se corresponde en orden con cada latitud. La modificación de puntos se realiza en Vista 3.2.",
        ),
    })
    catalogo = base.read_table("catalogo_tipos_proyecto")
    necesidades = base.read_table("necesidades")
    categorias_catalogo = (
        catalogo.iloc[:, 0] if not catalogo.empty else pd.Series(dtype=object)
    )
    categorias_actuales = necesidades.get("tipo_de_proyecto", pd.Series(dtype=object))
    category_options = list(dict.fromkeys([
        "",
        *(base._clean_text(v) for v in categorias_catalogo if base._clean_text(v)),
        *(base._clean_text(v) for v in categorias_actuales if base._clean_text(v)),
    ]))
    config.update(
        {
            "id_necesidad": st.column_config.NumberColumn(
                "ID de la necesidad",
                format="%d",
                width="small",
            ),
            "categoria_clasificacion": st.column_config.SelectboxColumn(
                "Categoría / clasificación",
                options=category_options,
                required=False,
                width="large",
                help=(
                    "Seleccione una categoría del catálogo institucional. "
                    "El cambio actualiza Tipo de proyecto en la Vista 3.1 "
                    "y los filtros de la Vista 3.2."
                ),
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


def _changed_need_values(
    edited: pd.DataFrame, original: pd.DataFrame,
) -> dict[int, dict[str, object]]:
    """Detectar ediciones de categoría y demás campos compartidos con 3.1."""
    changes: dict[int, dict[str, object]] = {}
    for nid, after in edited.iterrows():
        before = original.loc[nid]
        modified: dict[str, object] = {}
        for field in NEED_EDIT_FIELDS:
            old_value, new_value = before.get(field), after.get(field)
            if field in NEED_NUMERIC_FIELDS:
                old_num = pd.to_numeric(old_value, errors="coerce")
                new_num = pd.to_numeric(new_value, errors="coerce")
                if pd.isna(new_num) and base._clean_text(new_value):
                    raise ValueError(f"ID {nid}: valor numérico inválido para {field}.")
                if pd.notna(new_num) and not (0 <= float(new_num) < float("inf")):
                    raise ValueError(f"ID {nid}: {field} debe ser un número no negativo.")
                equal = (pd.isna(old_num) and pd.isna(new_num)) or (
                    pd.notna(old_num) and pd.notna(new_num)
                    and float(old_num) == float(new_num)
                )
                if not equal:
                    modified[field] = None if pd.isna(new_num) else float(new_num)
            else:
                old_text = base._clean_text(old_value)
                new_text = base._clean_text(new_value)
                if old_text != new_text:
                    modified[NEED_DB_FIELDS.get(field, field)] = new_text
        if modified:
            changes[int(nid)] = modified
    return changes


def _save_need_changes(changes: dict[int, dict[str, object]]) -> None:
    """Persistir solo los campos realmente editados en 3.1 / 3.3.

    En Supabase se hace PATCH por ID de necesidad, sin sobrescribir los demás
    campos ni marcas de tiempo. En CSV local, donde el upsert reemplaza filas,
    se combina con el registro completo antes de guardarlo.
    """
    if not changes:
        return

    client = get_supabase_client()
    if client is not None:
        saved_ids: list[int] = []
        try:
            for nid, fields in changes.items():
                client.table("necesidades").update(fields).eq("id", nid).execute()
                saved_ids.append(nid)
        except Exception as exc:
            if saved_ids:
                raise RuntimeError(
                    f"Guardado parcial: se actualizaron las necesidades "
                    f"{', '.join(map(str, saved_ids))} antes del error: {exc}"
                ) from exc
            raise
        finally:
            if saved_ids:
                clear_cache()
        return

    # Entorno local: un upsert con columnas parciales eliminaría el resto de la
    # fila CSV, por lo cual se integra el cambio en la fila completa vigente.
    latest = base.read_table("necesidades").copy()
    if latest.empty or "id" not in latest.columns:
        raise ValueError("No fue posible leer las necesidades actuales.")
    numeric_ids = pd.to_numeric(latest["id"], errors="coerce")
    wanted = set(changes)
    if not wanted.issubset(set(numeric_ids.dropna().astype(int))):
        raise ValueError("Algunas necesidades cambiaron o dejaron de existir; actualice los datos.")
    rows = latest.loc[numeric_ids.isin(wanted)].copy()
    for index, raw_id in numeric_ids.loc[rows.index].items():
        nid = int(raw_id)
        for field, value in changes[nid].items():
            rows.at[index, field] = value
    upsert_rows("necesidades", rows)


def _filter_attention(work: pd.DataFrame, selected: list[str]) -> pd.DataFrame:
    """Filtra por clasificación de atención; «Sin clasificar» incluye valores vacíos."""
    if not selected:
        return work
    expected = {"" if option == "Sin clasificar" else option for option in selected}
    actual = work["responsabilidad_atencion"].map(base._clean_text)
    return work.loc[actual.isin(expected)].copy()


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
    f1, f2, f_licitacion, f3 = st.columns([1.0, 1.6, 1.3, 1.4])
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
    selected_licitaciones = f_licitacion.multiselect(
        "Tipo de licitación",
        [option for option in base.LICITACION_OPTIONS if option] + ["Pendiente de definir"],
        key="banco_filter_licitacion",
        placeholder="Todas",
    )
    selected_states = f3.multiselect(
        "Estado Actual (AyA)",
        base.ESTADO_AYA_OPTIONS,
        key="banco_filter_state",
    )

    f_atencion, f4, f5, f6 = st.columns([1.8, 1.3, 2.0, 2.4])
    atenciones_registradas = {
        base._clean_text(value)
        for value in work["responsabilidad_atencion"]
        if base._clean_text(value)
    }
    opciones_atencion = list(dict.fromkeys([
        *[value for value in ATENCION_NECESIDAD_OPTIONS if value],
        *sorted(atenciones_registradas),
        "Sin clasificar",
    ]))
    selected_attention = f_atencion.multiselect(
        "Clasificación de la atención",
        opciones_atencion,
        key="banco_filter_atencion",
        placeholder="Todas",
        help="Permite filtrar por una o varias clasificaciones. «Sin clasificar» incluye necesidades sin clasificación registrada.",
    )
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
    filtered = _filter_attention(filtered, selected_attention)
    if selected_licitaciones:
        selected = ["" if value == "Pendiente de definir" else value for value in selected_licitaciones]
        filtered = filtered[filtered["tipo_licitacion"].fillna("").isin(selected)]
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

    m_menor, m_mayor = st.columns(2)
    m_menor.metric(
        "Licitación menor",
        f"{int(filtered['tipo_licitacion'].eq('Licitación menor').sum()):,}",
        help="Cantidad de ideas / necesidades con licitación menor en el resultado filtrado.",
    )
    m_mayor.metric(
        "Licitación mayor",
        f"{int(filtered['tipo_licitacion'].eq('Licitación mayor').sum()):,}",
        help="Cantidad de ideas / necesidades con licitación mayor en el resultado filtrado.",
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
    st.caption(
        "🟦 Campos automáticos · Solo lectura     🟩 Campos editables · Ingreso o ajuste manual. "
        "Categoría / clasificación y los campos de costos, caudal, volumen, km y atención se sincronizan con Vista 3.1. "
        "Las coordenadas se consultan aquí y se editan desde Vista 3.2 (una necesidad puede tener varios puntos)."
    )
    editor = filtered[["necesidad_id", *DISPLAY_COLUMNS]].copy().set_index("necesidad_id")

    # El formulario agrupa las ediciones. Sin él, cada cambio de una celda
    # vuelve a ejecutar y renderizar toda la vista de más de treinta columnas.
    with st.form("form_banco_ideas_aya_v6", border=False):
        edited = st.data_editor(
            editor,
            use_container_width=True,
            hide_index=True,
            height=700,
            num_rows="fixed",
            disabled=AUTOMATIC_COLUMNS,
            column_config=_column_config(),
            key="editor_banco_ideas_aya_v6",
        )
        save_requested = st.form_submit_button(
            "Guardar cambios de necesidades y seguimiento",
            type="primary",
        )

    if save_requested:
        try:
            changed_tracking = _changed_tracking_rows(edited, editor)
            changed_needs = _changed_need_values(edited, editor)
        except (ValueError, TypeError) as exc:
            st.error(f"No se guardaron cambios: {exc}")
            return

        if changed_tracking.empty and not changed_needs:
            st.info("No hay cambios para guardar.")
            return

        saved: list[str] = []
        errors: list[str] = []
        if changed_needs:
            try:
                _save_need_changes(changed_needs)
                saved.append("datos de necesidades (Vista 3.1)")
            except Exception as exc:
                errors.append(f"No se pudieron guardar los datos de necesidades: {exc}")
        if not changed_tracking.empty:
            try:
                base._save_tracking(changed_tracking)
                saved.append("datos de seguimiento (Vista 3.3)")
            except Exception as exc:
                errors.append(
                    "No se pudieron guardar los datos de seguimiento. "
                    "Verifique el esquema de necesidades_seguimiento (SQL 09). "
                    f"Detalle: {exc}"
                )

        if saved:
            _prepare_work_cached.clear()
            st.success("Cambios guardados: " + " y ".join(saved) + ".")
        if errors:
            st.error(" ".join(errors))
            if saved:
                st.warning(
                    "El guardado fue parcial. Los datos indicados como guardados "
                    "ya están persistidos; revise los errores antes de reintentar."
                )
        else:
            st.rerun()
