from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st
from pyproj import Transformer
from shapely.ops import transform, unary_union
from streamlit_folium import st_folium

import geo_necesidades_legacy as legacy
import territorio_necesidades as base
from database import read_table
from dta_nombres_gam import canton_name, district_name, province_name

MIN_ADMIN_COVERAGE_PCT = 10.0
ALGORITHM_VERSION = "v2-system-footprint-clean-admin-names"


def clean_canton_label(province: str, canton: str) -> str:
    return canton_name(province, canton)


def clean_district_label(province: str, canton: str, district: str) -> str:
    return district_name(province, canton, district)


# También limpia los tooltips de las capas administrativas del mapa.
base._canton_label = clean_canton_label
base._district_label = clean_district_label


@st.cache_data(show_spinner=False)
def territorial_crosswalk(min_coverage_pct: float = MIN_ADMIN_COVERAGE_PCT) -> pd.DataFrame:
    """Cruza sistemas con cantones/distritos usando la huella del sistema como denominador.

    Regla: una unidad administrativa se asocia cuando contiene más del 10 % del área
    total del sistema. Así se excluyen contactos marginales y, al mismo tiempo, un
    sistema pequeño no queda sin cantón solo porque el cantón completo sea muy grande.
    """
    payload = base.load_admin_geojson()
    admin_rows: list[dict[str, Any]] = []

    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        geom = base._clean_geometry(feature.get("geometry"))
        if geom is None:
            continue
        raw_province = base._property(props, base._PROVINCE_FIELDS, "")
        raw_canton = base._property(props, base._CANTON_FIELDS, "")
        raw_district = base._property(props, base._DISTRICT_FIELDS, "")
        if not raw_province or not raw_canton or not raw_district:
            continue
        admin_rows.append(
            {
                "raw_provincia": raw_province,
                "raw_canton": raw_canton,
                "raw_distrito": raw_district,
                "provincia": province_name(raw_province),
                "canton": canton_name(raw_province, raw_canton),
                "distrito": district_name(raw_province, raw_canton, raw_district),
                "geometry": geom,
            }
        )

    if not admin_rows:
        return pd.DataFrame(columns=[
            "sistema_codigo", "sistema_nombre", "nivel", "provincia",
            "canton", "distrito", "etiqueta", "porcentaje_cobertura", "umbral_pct",
        ])

    district_groups: dict[tuple[str, str, str], list[Any]] = {}
    district_names: dict[tuple[str, str, str], tuple[str, str, str]] = {}
    for row in admin_rows:
        key = (row["raw_provincia"], row["raw_canton"], row["raw_distrito"])
        district_groups.setdefault(key, []).append(row["geometry"])
        district_names[key] = (row["provincia"], row["canton"], row["distrito"])

    districts: list[dict[str, Any]] = []
    for key, geoms in district_groups.items():
        province, canton, district = district_names[key]
        districts.append({
            "provincia": province,
            "canton": canton,
            "distrito": district,
            "geometry": unary_union(geoms),
        })

    canton_groups: dict[tuple[str, str], list[Any]] = {}
    for row in districts:
        canton_groups.setdefault((row["provincia"], row["canton"]), []).append(row["geometry"])
    cantons = [
        {
            "provincia": province,
            "canton": canton,
            "distrito": "",
            "geometry": unary_union(geoms),
        }
        for (province, canton), geoms in canton_groups.items()
    ]

    system_groups: dict[str, dict[str, Any]] = {}
    for path in sorted(base.GEO_DIR.glob("sistemas_*.json")):
        try:
            system_payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for feature in system_payload.get("features", []):
            props = feature.get("properties") or {}
            code = base._normalize_code(props.get("Codigo_Sis"))
            geom = base._clean_geometry(feature.get("geometry"))
            if not code or geom is None:
                continue
            entry = system_groups.setdefault(code, {
                "sistema_nombre": str(props.get("Nombre_Sis") or code).strip(),
                "geometries": [],
            })
            entry["geometries"].append(geom)

    if not system_groups:
        return pd.DataFrame()

    to_area = Transformer.from_crs("EPSG:4326", base.AREA_CRS, always_xy=True).transform
    projected_admin: dict[str, list[dict[str, Any]]] = {"canton": [], "distrito": []}
    for level, source in (("canton", cantons), ("distrito", districts)):
        for row in source:
            try:
                projected = transform(to_area, row["geometry"])
            except Exception:
                continue
            if projected.is_empty or projected.area <= 0:
                continue
            projected_admin[level].append({**row, "geometry_area": projected})

    threshold = float(min_coverage_pct)
    records: list[dict[str, Any]] = []

    for code, system_data in sorted(system_groups.items()):
        system_geom = unary_union(system_data["geometries"])
        if system_geom.is_empty:
            continue
        try:
            system_area_geom = transform(to_area, system_geom)
        except Exception:
            continue
        system_area = float(system_area_geom.area)
        if system_area <= 0:
            continue

        for level in ("canton", "distrito"):
            candidates: list[dict[str, Any]] = []
            for admin in projected_admin[level]:
                admin_geom = admin["geometry_area"]
                if not system_area_geom.intersects(admin_geom):
                    continue
                try:
                    overlap = float(system_area_geom.intersection(admin_geom).area)
                except Exception:
                    continue
                if overlap <= 0:
                    continue
                pct_of_system = overlap / system_area * 100.0
                candidates.append({**admin, "pct": pct_of_system})

            qualified = [row for row in candidates if row["pct"] > threshold]

            # Garantía territorial: si por fragmentación extrema ninguna unidad supera
            # el 10 %, conserva solo la unidad dominante. Esto evita sistemas sin
            # provincia/cantón/distrito por una división geométrica artificial.
            if not qualified and candidates:
                dominant = max(candidates, key=lambda row: row["pct"])
                qualified = [{**dominant, "dominant_fallback": True}]

            for admin in qualified:
                is_fallback = bool(admin.get("dominant_fallback"))
                pct = round(float(admin["pct"]), 3)
                # En fallback se conserva el porcentaje real y un umbral 0 únicamente
                # para que Supabase no descarte la unidad territorial dominante.
                row_threshold = 0.0 if is_fallback else threshold
                label = admin["canton"] if level == "canton" else admin["distrito"]
                records.append({
                    "sistema_codigo": code,
                    "sistema_nombre": system_data["sistema_nombre"],
                    "nivel": level,
                    "provincia": admin["provincia"],
                    "canton": admin["canton"],
                    "distrito": "" if level == "canton" else admin["distrito"],
                    "etiqueta": label,
                    "porcentaje_cobertura": pct,
                    "umbral_pct": row_threshold,
                })

    return pd.DataFrame(records)


def _join_names(value: object) -> str:
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value if str(item).strip())
    return str(value or "")


def _clean_detail_table(needs: pd.DataFrame, locations: pd.DataFrame) -> pd.DataFrame:
    table = base._territorial_consultation_table(needs, locations).copy()
    preferred = [
        "Nombre de la iniciativa",
        "Sistema de abastecimiento",
        "Provincia(s)",
        "Cantón(es)",
        "Distrito(s)",
        "Categoría",
        "Costo",
        "Valor estimado",
        "Unidad medible",
        "Latitud",
        "Longitud",
        "Descripción",
    ]
    columns = [c for c in preferred if c in table.columns]
    columns += [c for c in table.columns if c not in columns]
    return table[columns]


def render_consultation(
    needs: pd.DataFrame,
    locations: pd.DataFrame,
    crosswalk: pd.DataFrame,
) -> None:
    st.markdown("### Consulta geoespacial de necesidades e iniciativas")
    st.caption(
        "La relación territorial se obtiene por intersección de cada cobertura de sistema. "
        "Se asocia una unidad cuando contiene más del 10 % de la huella del sistema; "
        "si ninguna supera ese valor por fragmentación, se conserva únicamente la unidad dominante."
    )

    row1 = st.columns(4)
    systems = legacy.clean_multi_options(needs.get("sistema_de_abastecimiento", pd.Series(dtype=str)))
    selected_systems = row1[0].multiselect("Sistema de abastecimiento", systems, key="geo_filter_system")
    selected_provinces = row1[1].multiselect(
        "Provincia",
        sorted({p for values in needs["provincias_asociadas"] for p in (values or [])}),
        key="geo_filter_province",
    )
    canton_options = sorted({
        c for _, row in needs.iterrows()
        if not selected_provinces or base._list_contains(row["provincias_asociadas"], selected_provinces)
        for c in (row["cantones_asociados"] or [])
    })
    selected_cantons = row1[2].multiselect("Cantón", canton_options, key="geo_filter_canton")
    district_options = sorted({
        d for _, row in needs.iterrows()
        if (not selected_provinces or base._list_contains(row["provincias_asociadas"], selected_provinces))
        and (not selected_cantons or base._list_contains(row["cantones_asociados"], selected_cantons))
        for d in (row["distritos_asociados"] or [])
    })
    selected_districts = row1[3].multiselect("Distrito", district_options, key="geo_filter_district")

    row2 = st.columns(3)
    selected_types = row2[0].multiselect(
        "Tipo de necesidad",
        legacy.clean_options(needs.get("tipo_de_proyecto", pd.Series(dtype=str))),
        key="geo_filter_type",
    )
    selected_location_types = row2[1].multiselect(
        "Tipo de ubicación", legacy.LOCATION_TYPES, key="geo_filter_location_type"
    )
    include_infrastructure = row2[2].checkbox(
        "Incluir infraestructura de referencia", value=True, key="geo_include_infrastructure"
    )

    filtered_needs = needs.copy()
    if selected_systems:
        filtered_needs = filtered_needs[
            filtered_needs["sistema_de_abastecimiento"].apply(
                lambda value: legacy.has_any_system(value, selected_systems)
            )
        ]
    if selected_provinces:
        filtered_needs = filtered_needs[
            filtered_needs["provincias_asociadas"].apply(
                lambda value: base._list_contains(value, selected_provinces)
            )
        ]
    if selected_cantons:
        filtered_needs = filtered_needs[
            filtered_needs["cantones_asociados"].apply(
                lambda value: base._list_contains(value, selected_cantons)
            )
        ]
    if selected_districts:
        filtered_needs = filtered_needs[
            filtered_needs["distritos_asociados"].apply(
                lambda value: base._list_contains(value, selected_districts)
            )
        ]
    if selected_types:
        filtered_needs = filtered_needs[
            filtered_needs["tipo_de_proyecto"].astype(str).isin(selected_types)
        ]

    need_ids = set(pd.to_numeric(filtered_needs.get("id"), errors="coerce").dropna().astype(int))
    filtered_locations = (
        locations[pd.to_numeric(locations.get("necesidad_id"), errors="coerce").isin(need_ids)].copy()
        if not locations.empty else locations.copy()
    )
    if selected_location_types:
        filtered_locations = filtered_locations[
            filtered_locations["tipo_ubicacion"].astype(str).isin(selected_location_types)
        ]
        matched = set(pd.to_numeric(filtered_locations.get("necesidad_id"), errors="coerce").dropna().astype(int))
        filtered_needs = filtered_needs[pd.to_numeric(filtered_needs["id"], errors="coerce").isin(matched)]

    st.markdown("#### Detalle descriptivo de necesidades e iniciativas")
    detail = _clean_detail_table(filtered_needs, filtered_locations)
    st.dataframe(
        detail,
        use_container_width=True,
        hide_index=True,
        height=460,
        column_config={
            "Nombre de la iniciativa": st.column_config.TextColumn(width="large"),
            "Sistema de abastecimiento": st.column_config.TextColumn(width="medium"),
            "Provincia(s)": st.column_config.TextColumn(width="small"),
            "Cantón(es)": st.column_config.TextColumn(width="medium"),
            "Distrito(s)": st.column_config.TextColumn(width="large"),
            "Descripción": st.column_config.TextColumn(width="large"),
        },
    )

    st.markdown("#### Indicadores consolidados")
    legacy.render_executive_metrics(filtered_needs)

    selected_codes = (
        legacy.clean_multi_options(filtered_needs.get("codigo_de_sistema", pd.Series(dtype=str)))
        if selected_systems or selected_provinces or selected_cantons or selected_districts else []
    )
    map_object = legacy.build_map(
        filtered_needs,
        filtered_locations,
        selected_codes=selected_codes,
        include_infrastructure=include_infrastructure,
    )
    base.add_admin_layers(map_object)

    map_column, chart_column = st.columns([2.2, 1.25])
    with map_column:
        st.markdown("#### Localización geoespacial")
        st_folium(
            map_object,
            height=700,
            use_container_width=True,
            returned_objects=[],
            key="needs_consultation_map",
        )
    with chart_column:
        figure = legacy.category_pie_chart(filtered_needs)
        if figure is None:
            st.info("No hay iniciativas para construir el gráfico por categoría.")
        else:
            st.plotly_chart(figure, use_container_width=True)

    with st.expander("Auditoría del geoproceso territorial", expanded=False):
        st.caption(
            "Porcentaje mostrado = área de intersección con la unidad administrativa ÷ "
            "área total de la cobertura del sistema. Áreas calculadas en CRTM05 (EPSG:5367)."
        )
        if crosswalk.empty:
            st.info("No se generaron relaciones territoriales.")
        else:
            audit = crosswalk.copy().rename(columns={
                "sistema_codigo": "Código sistema",
                "sistema_nombre": "Sistema",
                "nivel": "Nivel",
                "provincia": "Provincia",
                "canton": "Cantón",
                "distrito": "Distrito",
                "porcentaje_cobertura": "% de la huella del sistema",
            })
            show_cols = [
                "Código sistema", "Sistema", "Nivel", "Provincia", "Cantón", "Distrito",
                "% de la huella del sistema",
            ]
            st.dataframe(audit[[c for c in show_cols if c in audit.columns]], use_container_width=True, hide_index=True)


def vista_mapa_necesidades_territorial() -> None:
    st.subheader("Vista 3.2 · Mapa de Necesidades")
    st.caption(
        "Consulta territorial automática por sistema de abastecimiento, provincia, cantón y distrito."
    )

    # Fuerza recálculo/sincronización una vez al cambiar de algoritmo.
    if st.session_state.get("_territorial_algorithm_version") != ALGORITHM_VERSION:
        territorial_crosswalk.clear()
        st.session_state.pop("_territorial_crosswalk_synced", None)
        st.session_state["_territorial_algorithm_version"] = ALGORITHM_VERSION

    needs = read_table("necesidades")
    locations = read_table("necesidades_ubicaciones")
    if needs.empty:
        st.warning("No hay necesidades disponibles para visualizar.")
        return

    needs = legacy.ensure_columns(needs, [
        "id", "objetivo_de_la_iniciativa", "breve_descripcion", "tipo_de_proyecto",
        "codigo_de_sistema", "sistema_de_abastecimiento", "costo",
    ])
    locations = legacy.ensure_columns(locations, [
        "id", "necesidad_id", "tipo_ubicacion", "latitud", "longitud",
        "nombre_ubicacion", "observacion",
    ])

    try:
        crosswalk = territorial_crosswalk(MIN_ADMIN_COVERAGE_PCT)
        enriched_needs, _ = base.associate_needs(needs, crosswalk)
    except Exception as exc:
        st.error(f"No fue posible ejecutar el geoproceso territorial: {exc}")
        tabs = st.tabs(["Mapa de consulta", "Georreferenciar / editar"])
        with tabs[0]:
            legacy.render_consultation(needs, locations)
        with tabs[1]:
            legacy.render_editor(needs, locations)
        return

    synced, message = base.sync_crosswalk_to_supabase(crosswalk)
    st.caption(("✓ " if synced else "") + message)

    tabs = st.tabs(["Mapa de consulta", "Georreferenciar / editar"])
    with tabs[0]:
        render_consultation(enriched_needs, locations, crosswalk)
    with tabs[1]:
        legacy.render_editor(needs, locations)
