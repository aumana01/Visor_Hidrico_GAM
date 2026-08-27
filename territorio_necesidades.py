from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

import folium
import pandas as pd
import streamlit as st
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union
from streamlit_folium import st_folium

import geo_necesidades_legacy as legacy
from database import get_supabase_client, read_table

BASE_DIR = Path(__file__).resolve().parent
GEO_DIR = BASE_DIR / "data" / "geoespacial"
DISTRICTS_FILE = GEO_DIR / "distritos.geojson"
MIN_ADMIN_COVERAGE_PCT = 10.0
AREA_CRS = "EPSG:5367"  # CRTM05, apropiado para medición de áreas en Costa Rica.

_PROVINCE_FIELDS = (
    "provincia", "Provincia", "PROVINCIA", "nom_prov", "NOM_PROV",
    "nombre_provincia", "NOMBRE_PROVINCIA",
)
_CANTON_FIELDS = (
    "canton", "Cantón", "Canton", "CANTON", "nom_canton", "NOM_CANTON",
    "nombre_canton", "NOMBRE_CANTON",
)
_DISTRICT_FIELDS = (
    "distrito", "Distrito", "DISTRITO", "nom_distrito", "NOM_DISTRITO",
    "nombre_distrito", "NOMBRE_DISTRITO",
)


def _property(properties: dict[str, Any], candidates: Iterable[str], fallback: str = "") -> str:
    for key in candidates:
        if key in properties:
            value = properties.get(key)
            if value is not None:
                text = str(value).strip()
                if text and text.lower() not in {"nan", "none", "<na>"}:
                    return text
    return fallback


def _clean_geometry(raw_geometry: dict[str, Any] | None):
    if not raw_geometry:
        return None
    try:
        geom = shape(raw_geometry)
        if geom.is_empty:
            return None
        if not geom.is_valid:
            geom = make_valid(geom)
        if geom.is_empty:
            return None
        return geom
    except Exception:
        return None


def _normalize_code(value: object) -> str:
    text = "" if value is None else str(value).upper().strip()
    text = re.sub(r"[^A-Z0-9]", "", text)
    if text.startswith("MEA"):
        digits = "".join(ch for ch in text[3:] if ch.isdigit())
        if digits:
            return f"MEA{int(digits):02d}"
    return text


def _admin_piece_label(level: str, value: str) -> str:
    text = str(value).strip()
    if re.fullmatch(r"\d+(?:\.0+)?", text):
        number = str(int(float(text)))
        return f"{'Cantón' if level == 'canton' else 'Distrito'} {number}"
    return text


def _canton_label(province: str, canton: str) -> str:
    return f"{province} · {_admin_piece_label('canton', canton)}"


def _district_label(province: str, canton: str, district: str) -> str:
    return (
        f"{province} · {_admin_piece_label('canton', canton)} · "
        f"{_admin_piece_label('distrito', district)}"
    )


@st.cache_data(show_spinner=False)
def load_admin_geojson() -> dict[str, Any]:
    if not DISTRICTS_FILE.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(DISTRICTS_FILE.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def territorial_crosswalk(min_coverage_pct: float = MIN_ADMIN_COVERAGE_PCT) -> pd.DataFrame:
    """Relate system coverage to cantons/districts by areal overlap.

    A canton is associated only when the system covers > min_coverage_pct of the
    canton. A district uses the same rule against the district area. This prevents
    a boundary touch or small sliver from producing a territorial association.
    """
    admin_payload = load_admin_geojson()
    admin_rows: list[dict[str, Any]] = []
    for feature in admin_payload.get("features", []):
        props = feature.get("properties") or {}
        geom = _clean_geometry(feature.get("geometry"))
        if geom is None:
            continue
        province = _property(props, _PROVINCE_FIELDS, "SIN PROVINCIA")
        canton = _property(props, _CANTON_FIELDS, "SIN CANTÓN")
        district = _property(props, _DISTRICT_FIELDS, "SIN DISTRITO")
        admin_rows.append(
            {
                "provincia": province,
                "canton": canton,
                "distrito": district,
                "geometry": geom,
            }
        )
    if not admin_rows:
        return pd.DataFrame(
            columns=[
                "sistema_codigo", "sistema_nombre", "nivel", "provincia",
                "canton", "distrito", "etiqueta", "porcentaje_cobertura",
                "umbral_pct",
            ]
        )

    district_groups: dict[tuple[str, str, str], list[Any]] = {}
    for row in admin_rows:
        key = (row["provincia"], row["canton"], row["distrito"])
        district_groups.setdefault(key, []).append(row["geometry"])
    districts: list[dict[str, Any]] = []
    for (province, canton, district), geoms in district_groups.items():
        districts.append(
            {
                "provincia": province,
                "canton": canton,
                "distrito": district,
                "geometry": unary_union(geoms),
            }
        )

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
    for path in sorted(GEO_DIR.glob("sistemas_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for feature in payload.get("features", []):
            props = feature.get("properties") or {}
            code = _normalize_code(props.get("Codigo_Sis"))
            geom = _clean_geometry(feature.get("geometry"))
            if not code or geom is None:
                continue
            entry = system_groups.setdefault(
                code,
                {
                    "sistema_nombre": str(props.get("Nombre_Sis") or code).strip(),
                    "geometries": [],
                },
            )
            entry["geometries"].append(geom)

    if not system_groups:
        return pd.DataFrame()

    to_area = Transformer.from_crs("EPSG:4326", AREA_CRS, always_xy=True).transform

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

    records: list[dict[str, Any]] = []
    threshold_ratio = float(min_coverage_pct) / 100.0
    for code, system_data in sorted(system_groups.items()):
        system_geom = unary_union(system_data["geometries"])
        if system_geom.is_empty:
            continue
        try:
            system_area_geom = transform(to_area, system_geom)
        except Exception:
            continue

        qualified_cantons: set[tuple[str, str]] = set()
        for admin in projected_admin["canton"]:
            admin_geom = admin["geometry_area"]
            if not system_area_geom.intersects(admin_geom):
                continue
            try:
                intersection_area = system_area_geom.intersection(admin_geom).area
            except Exception:
                continue
            ratio = intersection_area / admin_geom.area if admin_geom.area else 0.0
            if ratio <= threshold_ratio:
                continue
            province = admin["provincia"]
            canton = admin["canton"]
            qualified_cantons.add((province, canton))
            records.append(
                {
                    "sistema_codigo": code,
                    "sistema_nombre": system_data["sistema_nombre"],
                    "nivel": "canton",
                    "provincia": province,
                    "canton": canton,
                    "distrito": "",
                    "etiqueta": _canton_label(province, canton),
                    "porcentaje_cobertura": round(ratio * 100.0, 3),
                    "umbral_pct": float(min_coverage_pct),
                }
            )

        for admin in projected_admin["distrito"]:
            province = admin["provincia"]
            canton = admin["canton"]
            if (province, canton) not in qualified_cantons:
                continue
            admin_geom = admin["geometry_area"]
            if not system_area_geom.intersects(admin_geom):
                continue
            try:
                intersection_area = system_area_geom.intersection(admin_geom).area
            except Exception:
                continue
            ratio = intersection_area / admin_geom.area if admin_geom.area else 0.0
            if ratio <= threshold_ratio:
                continue
            district = admin["distrito"]
            records.append(
                {
                    "sistema_codigo": code,
                    "sistema_nombre": system_data["sistema_nombre"],
                    "nivel": "distrito",
                    "provincia": province,
                    "canton": canton,
                    "distrito": district,
                    "etiqueta": _district_label(province, canton, district),
                    "porcentaje_cobertura": round(ratio * 100.0, 3),
                    "umbral_pct": float(min_coverage_pct),
                }
            )
    return pd.DataFrame(records)


def _codes_from_need(row: pd.Series, name_to_code: dict[str, str]) -> list[str]:
    codes = [_normalize_code(value) for value in legacy.split_multi_values(row.get("codigo_de_sistema"))]
    codes = [code for code in codes if code]
    if codes:
        return list(dict.fromkeys(codes))
    for name in legacy.split_multi_values(row.get("sistema_de_abastecimiento")):
        code = name_to_code.get(str(name).strip().casefold(), "")
        if code:
            codes.append(code)
    return list(dict.fromkeys(codes))


def associate_needs(needs: pd.DataFrame, crosswalk: pd.DataFrame) -> tuple[pd.DataFrame, dict[int, dict[str, Any]]]:
    out = needs.copy()
    for column in ("provincias_asociadas", "cantones_asociados", "distritos_asociados"):
        if column not in out.columns:
            out[column] = [[] for _ in range(len(out))]

    if crosswalk.empty:
        return out, {}

    name_to_code = {
        str(row["sistema_nombre"]).strip().casefold(): str(row["sistema_codigo"])
        for _, row in crosswalk[["sistema_nombre", "sistema_codigo"]].drop_duplicates().iterrows()
    }
    by_code = {code: group.copy() for code, group in crosswalk.groupby("sistema_codigo")}
    detail_by_need: dict[int, dict[str, Any]] = {}

    for idx, row in out.iterrows():
        raw_id = pd.to_numeric(row.get("id"), errors="coerce")
        need_id = int(raw_id) if pd.notna(raw_id) else -1
        codes = _codes_from_need(row, name_to_code)
        parts = [by_code[code] for code in codes if code in by_code]
        assoc = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
        if assoc.empty:
            provinces: list[str] = []
            cantons: list[str] = []
            districts: list[str] = []
            detail: list[dict[str, Any]] = []
        else:
            provinces = sorted(assoc["provincia"].dropna().astype(str).unique().tolist())
            cantons = sorted(
                assoc.loc[assoc["nivel"].eq("canton"), "etiqueta"]
                .dropna().astype(str).unique().tolist()
            )
            districts = sorted(
                assoc.loc[assoc["nivel"].eq("distrito"), "etiqueta"]
                .dropna().astype(str).unique().tolist()
            )
            detail = assoc.to_dict(orient="records")
        out.at[idx, "provincias_asociadas"] = provinces
        out.at[idx, "cantones_asociados"] = cantons
        out.at[idx, "distritos_asociados"] = districts
        if need_id >= 0:
            detail_by_need[need_id] = {
                "codigos": codes,
                "provincias": provinces,
                "cantones": cantons,
                "distritos": districts,
                "detalle": detail,
            }
    return out, detail_by_need


def _list_contains(value: object, selected: Iterable[str]) -> bool:
    selected_set = set(selected)
    if not selected_set:
        return True
    if isinstance(value, (list, tuple, set)):
        values = {str(item) for item in value}
    else:
        values = set(legacy.split_multi_values(value))
    return bool(values & selected_set)


def _crosswalk_hash(crosswalk: pd.DataFrame) -> str:
    if crosswalk.empty:
        return "empty"
    cols = [
        "sistema_codigo", "sistema_nombre", "nivel", "provincia", "canton",
        "distrito", "etiqueta", "porcentaje_cobertura", "umbral_pct",
    ]
    payload = crosswalk[cols].sort_values(cols[:6]).to_json(
        orient="records", force_ascii=False, double_precision=6
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sync_crosswalk_to_supabase(crosswalk: pd.DataFrame) -> tuple[bool, str]:
    if crosswalk.empty:
        return False, "No hay relaciones territoriales para sincronizar."
    client = get_supabase_client()
    if client is None:
        return False, "Modo local: el geoproceso se usa en memoria."

    digest = _crosswalk_hash(crosswalk)
    if st.session_state.get("_territorial_crosswalk_synced") == digest:
        return True, "Sincronizado en esta sesión."

    records = crosswalk.where(pd.notna(crosswalk), None).to_dict(orient="records")
    try:
        client.rpc("replace_sistemas_territorios", {"p_rows": records}).execute()
    except Exception as exc:
        return False, (
            "El geoproceso funciona en memoria, pero la persistencia territorial "
            "en Supabase todavía no está disponible. Ejecute "
            "`sql/08_geoproceso_territorial.sql`. Detalle: "
            f"{exc}"
        )

    st.session_state["_territorial_crosswalk_synced"] = digest
    return True, "Relaciones sistema–territorio sincronizadas en Supabase."


def _geojson_for_admin(level: str) -> dict[str, Any]:
    payload = load_admin_geojson()
    if level == "distrito":
        return payload

    groups: dict[tuple[str, str], list[Any]] = {}
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        province = _property(props, _PROVINCE_FIELDS, "SIN PROVINCIA")
        canton = _property(props, _CANTON_FIELDS, "SIN CANTÓN")
        geom = _clean_geometry(feature.get("geometry"))
        if geom is not None:
            groups.setdefault((province, canton), []).append(geom)

    features = []
    for (province, canton), geoms in groups.items():
        geom = unary_union(geoms)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "provincia": province,
                    "canton": canton,
                    "etiqueta": _canton_label(province, canton),
                },
                "geometry": mapping(geom),
            }
        )
    return {"type": "FeatureCollection", "features": features}


def add_admin_layers(map_object: folium.Map) -> None:
    canton_payload = _geojson_for_admin("canton")
    district_payload = _geojson_for_admin("distrito")

    if canton_payload.get("features"):
        folium.GeoJson(
            canton_payload,
            name="Cantones",
            show=False,
            style_function=lambda _: {
                "color": "#334155", "weight": 1.3, "fillOpacity": 0.0, "opacity": 0.8
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["etiqueta"],
                aliases=["Cantón:"],
                sticky=False,
            ),
        ).add_to(map_object)

    if district_payload.get("features"):
        payload = json.loads(json.dumps(district_payload))
        for feature in payload.get("features", []):
            props = feature.setdefault("properties", {})
            province = _property(props, _PROVINCE_FIELDS, "SIN PROVINCIA")
            canton = _property(props, _CANTON_FIELDS, "SIN CANTÓN")
            district = _property(props, _DISTRICT_FIELDS, "SIN DISTRITO")
            props["etiqueta_territorial"] = _district_label(province, canton, district)
        folium.GeoJson(
            payload,
            name="Distritos",
            show=False,
            style_function=lambda _: {
                "color": "#94A3B8", "weight": 0.7, "fillOpacity": 0.0, "opacity": 0.65
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["etiqueta_territorial"],
                aliases=["Distrito:"],
                sticky=False,
            ),
        ).add_to(map_object)


def _territorial_consultation_table(
    needs: pd.DataFrame,
    locations: pd.DataFrame,
) -> pd.DataFrame:
    table = legacy.consultation_table(needs, locations).copy()

    territory = needs.copy()
    territory["Nombre de la iniciativa"] = territory.apply(legacy.need_title, axis=1)
    territory = territory[
        [
            "Nombre de la iniciativa",
            "provincias_asociadas",
            "cantones_asociados",
            "distritos_asociados",
        ]
    ].copy()
    for column in ("provincias_asociadas", "cantones_asociados", "distritos_asociados"):
        territory[column] = territory[column].apply(
            lambda value: "; ".join(value) if isinstance(value, (list, tuple, set)) else str(value or "")
        )
    territory = territory.rename(
        columns={
            "provincias_asociadas": "Provincia(s)",
            "cantones_asociados": "Cantón(es)",
            "distritos_asociados": "Distrito(s)",
        }
    )
    return table.merge(territory, on="Nombre de la iniciativa", how="left")


def render_consultation_territorial(
    needs: pd.DataFrame,
    locations: pd.DataFrame,
    crosswalk: pd.DataFrame,
) -> None:
    st.markdown("### Consulta geoespacial de necesidades e iniciativas")
    st.caption(
        "La asociación territorial se calcula por superposición de la cobertura de cada "
        "sistema con cantones y distritos. Se excluyen contactos marginales: la cobertura "
        f"debe ser **mayor a {MIN_ADMIN_COVERAGE_PCT:.0f}%** del área de la unidad administrativa."
    )

    row1 = st.columns(4)
    systems = legacy.clean_multi_options(
        needs.get("sistema_de_abastecimiento", pd.Series(dtype=str))
    )
    selected_systems = row1[0].multiselect(
        "Sistema de abastecimiento", systems, key="geo_filter_system"
    )
    selected_provinces = row1[1].multiselect(
        "Provincia",
        sorted({p for values in needs["provincias_asociadas"] for p in (values or [])}),
        key="geo_filter_province",
    )

    canton_options = sorted(
        {
            c
            for _, row in needs.iterrows()
            if not selected_provinces or _list_contains(row["provincias_asociadas"], selected_provinces)
            for c in (row["cantones_asociados"] or [])
        }
    )
    selected_cantons = row1[2].multiselect(
        "Cantón", canton_options, key="geo_filter_canton"
    )
    district_options = sorted(
        {
            d
            for _, row in needs.iterrows()
            if (not selected_provinces or _list_contains(row["provincias_asociadas"], selected_provinces))
            and (not selected_cantons or _list_contains(row["cantones_asociados"], selected_cantons))
            for d in (row["distritos_asociados"] or [])
        }
    )
    selected_districts = row1[3].multiselect(
        "Distrito", district_options, key="geo_filter_district"
    )

    row2 = st.columns(3)
    need_types = legacy.clean_options(needs.get("tipo_de_proyecto", pd.Series(dtype=str)))
    selected_types = row2[0].multiselect(
        "Tipo de necesidad", need_types, key="geo_filter_type"
    )
    selected_location_types = row2[1].multiselect(
        "Tipo de ubicación", legacy.LOCATION_TYPES, key="geo_filter_location_type"
    )
    include_infrastructure = row2[2].checkbox(
        "Incluir infraestructura de referencia",
        value=True,
        key="geo_include_infrastructure",
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
                lambda value: _list_contains(value, selected_provinces)
            )
        ]
    if selected_cantons:
        filtered_needs = filtered_needs[
            filtered_needs["cantones_asociados"].apply(
                lambda value: _list_contains(value, selected_cantons)
            )
        ]
    if selected_districts:
        filtered_needs = filtered_needs[
            filtered_needs["distritos_asociados"].apply(
                lambda value: _list_contains(value, selected_districts)
            )
        ]
    if selected_types:
        filtered_needs = filtered_needs[
            filtered_needs["tipo_de_proyecto"].astype(str).isin(selected_types)
        ]

    need_ids = set(
        pd.to_numeric(filtered_needs.get("id"), errors="coerce").dropna().astype(int)
    )
    filtered_locations = (
        locations[
            pd.to_numeric(locations.get("necesidad_id"), errors="coerce").isin(need_ids)
        ].copy()
        if not locations.empty
        else locations.copy()
    )
    if selected_location_types:
        filtered_locations = filtered_locations[
            filtered_locations["tipo_ubicacion"].astype(str).isin(selected_location_types)
        ]
        matched_need_ids = set(
            pd.to_numeric(filtered_locations.get("necesidad_id"), errors="coerce")
            .dropna().astype(int)
        )
        filtered_needs = filtered_needs[
            pd.to_numeric(filtered_needs["id"], errors="coerce").isin(matched_need_ids)
        ]

    st.markdown("#### Detalle descriptivo de necesidades e iniciativas")
    detail_table = _territorial_consultation_table(filtered_needs, filtered_locations)
    st.dataframe(
        detail_table,
        use_container_width=True,
        hide_index=True,
        height=440,
        column_config={
            "Nombre de la iniciativa": st.column_config.TextColumn(width="large"),
            "Descripción": st.column_config.TextColumn(width="large"),
            "Sistema de abastecimiento": st.column_config.TextColumn(width="medium"),
            "Provincia(s)": st.column_config.TextColumn(width="medium"),
            "Cantón(es)": st.column_config.TextColumn(width="large"),
            "Distrito(s)": st.column_config.TextColumn(width="large"),
        },
    )

    st.markdown("#### Indicadores consolidados")
    legacy.render_executive_metrics(filtered_needs)

    selected_codes = (
        legacy.clean_multi_options(filtered_needs.get("codigo_de_sistema", pd.Series(dtype=str)))
        if selected_systems or selected_provinces or selected_cantons or selected_districts
        else []
    )
    map_object = legacy.build_map(
        filtered_needs,
        filtered_locations,
        selected_codes=selected_codes,
        include_infrastructure=include_infrastructure,
    )
    add_admin_layers(map_object)

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
            "Porcentaje = área de intersección sistema/unidad administrativa ÷ área total "
            "de la unidad administrativa. Las áreas se calculan en CRTM05 (EPSG:5367)."
        )
        audit = crosswalk.copy()
        if not audit.empty:
            st.dataframe(
                audit.sort_values(
                    ["sistema_codigo", "nivel", "provincia", "canton", "distrito"]
                ),
                use_container_width=True,
                hide_index=True,
                height=360,
            )
        else:
            st.info("No se generaron relaciones territoriales.")


def vista_mapa_necesidades_territorial() -> None:
    st.subheader("Vista 3.2 · Mapa de Necesidades")
    st.caption(
        "Consulta territorial automática por sistema de abastecimiento, provincia, cantón "
        "y distrito, con exclusión de contactos geográficos marginales."
    )
    needs = read_table("necesidades")
    locations = read_table("necesidades_ubicaciones")
    if needs.empty:
        st.warning("No hay necesidades disponibles para visualizar.")
        return

    needs = legacy.ensure_columns(
        needs,
        [
            "id", "objetivo_de_la_iniciativa", "breve_descripcion", "tipo_de_proyecto",
            "codigo_de_sistema", "sistema_de_abastecimiento", "costo",
        ],
    )
    locations = legacy.ensure_columns(
        locations,
        [
            "id", "necesidad_id", "tipo_ubicacion", "latitud", "longitud",
            "nombre_ubicacion", "observacion",
        ],
    )

    try:
        crosswalk = territorial_crosswalk(MIN_ADMIN_COVERAGE_PCT)
        enriched_needs, _ = associate_needs(needs, crosswalk)
    except Exception as exc:
        st.error(
            "No fue posible ejecutar el geoproceso territorial. Se mantiene la consulta "
            f"anterior para no interrumpir el visor. Detalle: {exc}"
        )
        tab_query, tab_edit = st.tabs(["Mapa de consulta", "Georreferenciar / editar"])
        with tab_query:
            legacy.render_consultation(needs, locations)
        with tab_edit:
            legacy.render_editor(needs, locations)
        return

    synced, sync_message = sync_crosswalk_to_supabase(crosswalk)
    if synced:
        st.caption("✓ " + sync_message)
    else:
        st.caption(sync_message)

    tab_query, tab_edit = st.tabs(["Mapa de consulta", "Georreferenciar / editar"])
    with tab_query:
        render_consultation_territorial(enriched_needs, locations, crosswalk)
    with tab_edit:
        legacy.render_editor(needs, locations)
