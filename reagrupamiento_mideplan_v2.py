from __future__ import annotations

from collections import defaultdict

import pandas as pd
import streamlit as st

import reagrupamiento_mideplan as base


# Segunda iteración del motor 3.4.
# Regla principal: una agrupación estratégica NO puede cruzar libremente entre
# clusters. Dentro del cluster, el usuario decide si exige coincidencia de
# sistema, categoría, o ambos. Esto evita proyectos excesivamente amplios.

GROUPING_MODES = {
    "Estricto · Cluster + sistema + categoría": "strict",
    "Balanceado · Cluster + categoría o sistema": "balanced",
    "Por sistema · Cluster + sistema": "system",
    "Por categoría · Cluster + categoría": "category",
}
DEFAULT_MODE_LABEL = "Estricto · Cluster + sistema + categoría"

CLUSTER_BY_CODE = {
    "MEA01": "Cluster C-1", "MEA02": "Cluster C-1", "MEA04": "Cluster C-1",
    "MEA08": "Cluster C-1", "MEA10": "Cluster C-1", "MEA13": "Cluster C-1",
    "MEA20": "Cluster C-1", "MEA22": "Cluster C-1", "MEA28": "Cluster C-1",
    "MEA15": "Cluster C-2", "MEA17": "Cluster C-2",
    "MEA03": "Cluster C-3", "MEA06": "Cluster C-3", "MEA07": "Cluster C-3",
    "MEA09": "Cluster C-3", "MEA16": "Cluster C-3", "MEA19": "Cluster C-3",
    "MEA23": "Cluster C-3", "MEA25": "Cluster C-3",
    "MEA14": "Cluster C-4", "MEA21": "Cluster C-4",
    "MEA12": "Cluster C-5", "MEA26": "Cluster C-5", "MEA31": "Cluster C-5",
    "MEA05": "Cluster C-6", "MEA11": "Cluster C-6", "MEA18": "Cluster C-6",
    "MEA24": "Cluster C-6", "MEA27": "Cluster C-6", "MEA29": "Cluster C-6",
    "MEA30": "Cluster C-6",
}

_ORIGINAL_NEED_FEATURES = base._need_features
_ORIGINAL_PAIR_SCORE = base._pair_score
_ORIGINAL_BUILD_GROUPS = base.build_groups
_ORIGINAL_PROJECT_CONFIG = base._project_column_config
_ORIGINAL_FILTER_PROJECTS = base._filter_projects
_ORIGINAL_VIEW = base.vista_reagrupamiento_mideplan

# Metadatos del cálculo vigente, indexados por ID de necesidad.
_META_BY_ID: dict[int, dict[str, object]] = {}


def _mode() -> str:
    label = st.session_state.get("mideplan_grouping_mode", DEFAULT_MODE_LABEL)
    return GROUPING_MODES.get(label, "strict")


def _category_key(value: object) -> str:
    return base._norm(value)


def _clusters_for_systems(systems: set[str]) -> frozenset[str]:
    clusters = {CLUSTER_BY_CODE[code] for code in systems if code in CLUSTER_BY_CODE}
    return frozenset(clusters)


def _need_features(work: pd.DataFrame, raw_by_id: dict[int, pd.Series]):
    features = _ORIGINAL_NEED_FEATURES(work, raw_by_id)
    _META_BY_ID.clear()
    work_reset = work.reset_index(drop=True)
    for feature in features:
        row = work_reset.iloc[feature.idx]
        category_display = base._clean(row.get("categoria_clasificacion"))
        _META_BY_ID[feature.need_id] = {
            "clusters": _clusters_for_systems(feature.systems),
            "category_key": _category_key(category_display),
            "category_display": category_display or "Sin categoría",
        }
    return features


def _same_geographic_context(a, b) -> bool:
    return bool(
        (a.districts & b.districts)
        or (a.cantons & b.cantons)
        or (a.communities & b.communities)
    )


def _pair_score(a, b) -> float:
    if a.service != b.service:
        return -100.0

    ma = _META_BY_ID.get(a.need_id, {})
    mb = _META_BY_ID.get(b.need_id, {})
    clusters_a = ma.get("clusters", frozenset())
    clusters_b = mb.get("clusters", frozenset())
    category_a = str(ma.get("category_key", ""))
    category_b = str(mb.get("category_key", ""))
    same_title = bool(a.title_norm and b.title_norm and a.title_norm == b.title_norm)
    system_overlap = bool(a.systems & b.systems)
    same_category = bool(category_a and category_b and category_a == category_b)

    # SEGREGACIÓN DURA POR CLUSTER.
    # Una necesidad multisistema solo se compara con otra que tenga exactamente
    # el mismo conjunto de clusters; así se evita el efecto puente del Union-Find.
    if clusters_a != clusters_b:
        return -100.0

    # Cuando no existe sistema/cluster, no se permite una agrupación GAM-global:
    # debe existir territorio compartido o tratarse de la misma idea.
    if not clusters_a and not clusters_b and not same_title and not _same_geographic_context(a, b):
        return -100.0

    mode = _mode()
    if mode == "strict":
        # Duplicados textuales dentro del mismo cluster pueden consolidarse aun
        # si se registraron para sistemas distintos; fuera de ese caso se exige
        # misma categoría Y al menos un sistema compartido.
        if not same_title and not (same_category and system_overlap):
            return -100.0
    elif mode == "system":
        if not same_title and not system_overlap:
            return -100.0
    elif mode == "category":
        if not same_title and not same_category:
            return -100.0
    else:  # balanced
        if not same_title and not (same_category or system_overlap):
            return -100.0

    score = _ORIGINAL_PAIR_SCORE(a, b)

    # Se eleva la exigencia mínima. La coincidencia de cluster es una condición,
    # no puntos extra; aún debe existir coherencia temática/territorial/textual.
    if same_category:
        score += 1.0
    if system_overlap:
        score += 0.5
    return score


def _group_indices(features) -> list[list[int]]:
    # Umbrales más conservadores que la versión inicial.
    threshold = {
        "strict": 8.5,
        "balanced": 9.0,
        "system": 8.5,
        "category": 9.0,
    }.get(_mode(), 8.5)

    uf = base._UnionFind(len(features))
    for i in range(len(features)):
        for j in range(i + 1, len(features)):
            if _pair_score(features[i], features[j]) >= threshold:
                uf.union(i, j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(features)):
        groups[uf.find(i)].append(i)
    return list(groups.values())


def _clusters_from_labels(values: pd.Series) -> str:
    clusters: list[str] = []
    seen: set[str] = set()
    for value in values.fillna("").astype(str):
        for code in base._codes(value):
            cluster = CLUSTER_BY_CODE.get(code)
            if cluster and cluster not in seen:
                seen.add(cluster)
                clusters.append(cluster)
    return ", ".join(sorted(clusters)) or "Sin cluster definido"


def build_groups() -> tuple[pd.DataFrame, pd.DataFrame]:
    projects, trace = _ORIGINAL_BUILD_GROUPS()
    if projects.empty:
        return projects, trace

    projects = projects.copy()
    if isinstance(trace, pd.DataFrame) and not trace.empty:
        cluster_map: dict[str, str] = {}
        category_map: dict[str, str] = {}
        for project_id, group in trace.groupby("proyecto_estrategico"):
            cluster_map[str(project_id)] = _clusters_from_labels(group["codigo_nombre_sistema"])
            categories = [
                base._clean(value)
                for value in group.get("categoria_clasificacion", pd.Series(dtype=object)).tolist()
                if base._clean(value)
            ]
            category_map[str(project_id)] = base._join(categories) or "Sin categoría"
        projects["cluster_agrupacion"] = projects["proyecto_id"].astype(str).map(cluster_map).fillna("Sin cluster definido")
        projects["categorias_agrupadas"] = projects["proyecto_id"].astype(str).map(category_map).fillna("Sin categoría")
    else:
        projects["cluster_agrupacion"] = "Sin cluster definido"
        projects["categorias_agrupadas"] = "Sin categoría"

    projects["criterio_agrupamiento"] = st.session_state.get("mideplan_grouping_mode", DEFAULT_MODE_LABEL)

    front = [
        "orden_estrategico", "proyecto_id", "nombre_proyecto", "cluster_agrupacion",
        "categorias_agrupadas", "tipologia_mideplan", "familia_estrategica",
        "criterio_agrupamiento",
    ]
    rest = [c for c in projects.columns if c not in front]
    return projects[front + rest], trace


def _project_column_config() -> dict:
    config = _ORIGINAL_PROJECT_CONFIG()
    config.update(
        {
            "cluster_agrupacion": st.column_config.TextColumn("Cluster", width="medium"),
            "categorias_agrupadas": st.column_config.TextColumn("Categoría(s) 3.2", width="large"),
            "criterio_agrupamiento": st.column_config.TextColumn("Criterio de agrupamiento", width="large"),
        }
    )
    return config


def _filter_projects(projects: pd.DataFrame) -> pd.DataFrame:
    # Primera línea: filtros de segregación que ahora son centrales.
    f1, f2, f3 = st.columns([1.2, 2.0, 2.4])
    clusters = sorted(projects["cluster_agrupacion"].dropna().astype(str).unique().tolist())
    selected_clusters = f1.multiselect("Cluster", clusters, key="mideplan_cluster_v2")
    categories = sorted({
        item.strip()
        for value in projects["categorias_agrupadas"].fillna("")
        for item in str(value).split(",")
        if item.strip()
    })
    selected_categories = f2.multiselect("Categoría 3.2", categories, key="mideplan_category_v2")
    search = f3.text_input(
        "Buscar",
        placeholder="Proyecto, ID, sistema, categoría, cantón, distrito…",
        key="mideplan_search_v2",
    )

    f4, f5, f6 = st.columns([1.1, 1.7, 1.5])
    potential = f4.multiselect("Potencial", ["Muy alto", "Alto", "Medio", "Bajo"], key="mideplan_potential_v2")
    families = sorted(projects["familia_estrategica"].dropna().astype(str).unique().tolist())
    selected_families = f5.multiselect("Familia estratégica", families, key="mideplan_family_v2")
    provinces = sorted({x for value in projects["provincias"].fillna("") for x in base._split(value)})
    selected_provinces = f6.multiselect("Provincia", provinces, key="mideplan_province_v2")

    out = projects.copy()
    if selected_clusters:
        out = out[out["cluster_agrupacion"].isin(selected_clusters)]
    if selected_categories:
        selected_norm = {base._norm(x) for x in selected_categories}
        out = out[out["categorias_agrupadas"].apply(
            lambda value: bool(selected_norm & {base._norm(v) for v in str(value).split(",") if v.strip()})
        )]
    if potential:
        out = out[out["potencial"].isin(potential)]
    if selected_families:
        out = out[out["familia_estrategica"].isin(selected_families)]
    if selected_provinces:
        selected = {base._norm(x) for x in selected_provinces}
        out = out[out["provincias"].apply(lambda x: bool(selected & {base._norm(v) for v in base._split(x)}))]
    q = base._norm(search)
    if q:
        cols = [
            "proyecto_id", "nombre_proyecto", "cluster_agrupacion", "categorias_agrupadas",
            "ids_asociados", "sistemas_beneficiados", "cantones", "distritos",
            "comunidades", "descripcion",
        ]
        searchable = out[cols].fillna("").astype(str).agg(" ".join, axis=1)
        out = out[searchable.apply(lambda x: q in base._norm(x))]
    return out


def _clear_previous_result() -> None:
    st.session_state.pop("mideplan_projects", None)
    st.session_state.pop("mideplan_trace", None)


def vista_reagrupamiento_mideplan() -> None:
    st.markdown("#### Nivel de segregación del reagrupamiento")
    st.selectbox(
        "Criterio",
        list(GROUPING_MODES.keys()),
        index=list(GROUPING_MODES.keys()).index(
            st.session_state.get("mideplan_grouping_mode", DEFAULT_MODE_LABEL)
            if st.session_state.get("mideplan_grouping_mode", DEFAULT_MODE_LABEL) in GROUPING_MODES
            else DEFAULT_MODE_LABEL
        ),
        key="mideplan_grouping_mode",
        on_change=_clear_previous_result,
        help=(
            "Estricto es el recomendado: nunca mezcla clusters y, salvo duplicados evidentes, "
            "exige compartir sistema y categoría. Los otros modos permiten explorar agrupaciones "
            "más amplias sin cruzar clusters."
        ),
    )
    st.caption(
        "Regla fija: ninguna propuesta cruza clusters de abastecimiento. En necesidades sin cluster, "
        "solo se permite agrupar cuando comparten territorio o son claramente la misma idea."
    )
    _ORIGINAL_VIEW()


# Parches sobre el módulo original. build_groups() mantiene toda la generación
# MIDEPLAN existente, pero utiliza estas nuevas reglas de segregación.
base._need_features = _need_features
base._pair_score = _pair_score
base._group_indices = _group_indices
base.build_groups = build_groups
base._project_column_config = _project_column_config
base._filter_projects = _filter_projects
