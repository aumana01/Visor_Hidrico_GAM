from __future__ import annotations

import colorsys
import hashlib
import html
import json
import unicodedata
from pathlib import Path
from typing import Any, Iterable

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from branca.element import Element
from streamlit_folium import st_folium

from database import delete_rows, read_table, upsert_rows


BASE_DIR = Path(__file__).resolve().parent
GEO_DIR = BASE_DIR / "data" / "geoespacial"
LOCATION_TYPES = [
    "Ubicación precisa",
    "Ubicación general",
    "Ubicación institucional",
    "No aplica",
]
DEFAULT_CENTER = [9.96, -84.08]
DEFAULT_ZOOM = 10

INFRA_LAYERS = [
    {
        "filename": "plantas_potabilizadoras.json",
        "layer": "Plantas potabilizadoras",
        "name_field": "Nombre",
        "color": "green",
        "icon": "industry",
        "fields": ["Código", "Sistema", "Provincia", "Cantón", "Distrito", "CauMaxDise", "CauProOper"],
    },
    {
        "filename": "tanques_agua.json",
        "layer": "Tanques de agua",
        "name_field": "Nombre",
        "color": "blue",
        "icon": "database",
        "fields": ["Cod_Tanq", "Volumen", "Elevación", "Nombre_Sis", "Nom_Abast", "Estado"],
    },
    {
        "filename": "tomas_captaciones.json",
        "layer": "Tomas y captaciones",
        "name_field": "Nombre",
        "color": "darkblue",
        "icon": "tint",
        "fields": ["Codigo", "Tipo", "Sistema", "Provincia", "Canton", "Distrito", "CauInscrit", "CauOperati"],
    },
    {
        "filename": "estaciones_bombeo.json",
        "layer": "Estaciones de bombeo",
        "name_field": "Nombre_Est",
        "color": "orange",
        "icon": "cogs",
        "fields": ["Tipo", "Potencia", "Sistema", "Codigo_Sis", "Provincia", "Cantón", "Distrito", "Estado"],
    },
]


def ensure_columns(df: pd.DataFrame, columns: Iterable[str], default: object = "") -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = default
    return out


def clean_options(values: Iterable[object]) -> list[str]:
    options: list[str] = []
    for value in values:
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "<na>"} and text not in options:
            options.append(text)
    return sorted(options)


def safe_text(value: object, fallback: str = "—") -> str:
    if value is None or pd.isna(value):
        return fallback
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none", "<na>"} else fallback


def valid_lat_lon(lat: object, lon: object) -> bool:
    lat_num = pd.to_numeric(lat, errors="coerce")
    lon_num = pd.to_numeric(lon, errors="coerce")
    return (
        pd.notna(lat_num)
        and pd.notna(lon_num)
        and 8.0 <= float(lat_num) <= 12.0
        and -86.5 <= float(lon_num) <= -82.0
    )


def need_title(row: pd.Series | dict[str, Any]) -> str:
    title = safe_text(row.get("objetivo_de_la_iniciativa"), "")
    if title:
        return title
    description = safe_text(row.get("breve_descripcion"), "")
    return description if description else "Necesidad sin nombre"


def normalize_system_code(value: object) -> str:
    text = safe_text(value, "").upper().replace("-", "").replace(" ", "")
    if text.startswith("MEA"):
        digits = "".join(character for character in text[3:] if character.isdigit())
        if digits:
            return f"MEA{int(digits):02d}"
    return text


def system_color(code: object) -> str:
    normalized = normalize_system_code(code) or "SIN_SISTEMA"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    hue = (int(digest[:8], 16) % 360) / 360.0
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.67, 0.78)
    return f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"


@st.cache_data(show_spinner=False)
def load_system_geojson() -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for path in sorted(GEO_DIR.glob("sistemas_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        features.extend(payload.get("features", []))
    return {"type": "FeatureCollection", "features": features}


@st.cache_data(show_spinner=False)
def load_geojson(filename: str) -> dict[str, Any]:
    path = GEO_DIR / filename
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(path.read_text(encoding="utf-8"))


def system_style(feature: dict[str, Any], selected_codes: set[str]) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    code = normalize_system_code(properties.get("Codigo_Sis"))
    selected = not selected_codes or code in selected_codes
    return {
        "fillColor": system_color(code),
        "color": system_color(code),
        "weight": 2.4 if selected else 0.8,
        "fillOpacity": 0.28 if selected else 0.045,
        "opacity": 0.95 if selected else 0.25,
    }


def add_system_layer(
    map_object: folium.Map,
    selected_codes: Iterable[str] | None = None,
) -> None:
    selected = {normalize_system_code(code) for code in (selected_codes or []) if normalize_system_code(code)}
    systems = load_system_geojson()
    if not systems.get("features"):
        return
    tooltip = folium.GeoJsonTooltip(
        fields=["Codigo_Sis", "Nombre_Sis", "Codigo_Aba", "zonas", "Zona_Opera", "ICH"],
        aliases=["Código:", "Sistema:", "Zona de abastecimiento:", "Nombre de zona:", "Zona operativa:", "ICH:"],
        localize=True,
        sticky=False,
        labels=True,
        style=(
            "background-color:white;color:#1F2937;font-family:Arial;"
            "font-size:12px;padding:8px;border:1px solid #CBD5E1;"
        ),
    )
    folium.GeoJson(
        systems,
        name="Sistemas y zonas de abastecimiento",
        style_function=lambda feature: system_style(feature, selected),
        highlight_function=lambda feature: {
            "weight": 4,
            "fillOpacity": 0.38,
            "color": system_color((feature.get("properties") or {}).get("Codigo_Sis")),
        },
        tooltip=tooltip,
        smooth_factor=0.5,
    ).add_to(map_object)


def popup_table(title: str, properties: dict[str, Any], fields: Iterable[str]) -> str:
    rows = []
    for field in fields:
        value = safe_text(properties.get(field), "")
        if value:
            rows.append(
                "<tr>"
                f"<td style='padding:2px 8px 2px 0;color:#64748B'>{html.escape(field)}</td>"
                f"<td style='padding:2px 0'><b>{html.escape(value)}</b></td>"
                "</tr>"
            )
    return (
        f"<div style='min-width:230px'><h4 style='margin:0 0 7px;color:#002B5C'>{html.escape(title)}</h4>"
        f"<table>{''.join(rows)}</table></div>"
    )


def add_infrastructure_layers(map_object: folium.Map) -> None:
    for config in INFRA_LAYERS:
        feature_group = folium.FeatureGroup(name=config["layer"], show=False)
        payload = load_geojson(config["filename"])
        for feature in payload.get("features", []):
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates") or []
            if geometry.get("type") != "Point" or len(coordinates) < 2:
                continue
            lon, lat = coordinates[:2]
            if not valid_lat_lon(lat, lon):
                continue
            properties = feature.get("properties") or {}
            name = safe_text(properties.get(config["name_field"]), config["layer"])
            folium.Marker(
                [float(lat), float(lon)],
                tooltip=f"{config['layer']} · {name}",
                popup=folium.Popup(
                    popup_table(name, properties, config["fields"]),
                    max_width=380,
                ),
                icon=folium.Icon(
                    color=config["color"],
                    icon=config["icon"],
                    prefix="fa",
                ),
            ).add_to(feature_group)
            folium.Marker(
                [float(lat), float(lon)],
                icon=folium.DivIcon(
                    icon_size=(220, 20),
                    icon_anchor=(-9, 10),
                    html=f"<div class='infra-map-label'>{html.escape(name)}</div>",
                ),
            ).add_to(feature_group)
        feature_group.add_to(map_object)


def add_need_locations(
    map_object: folium.Map,
    needs: pd.DataFrame,
    locations: pd.DataFrame,
) -> list[list[float]]:
    bounds: list[list[float]] = []
    if needs.empty or locations.empty:
        return bounds
    need_columns = [
        "id",
        "objetivo_de_la_iniciativa",
        "breve_descripcion",
        "tipo_de_proyecto",
        "codigo_de_sistema",
        "sistema_de_abastecimiento",
        "costo",
    ]
    needs = ensure_columns(needs, need_columns)
    locations = ensure_columns(
        locations,
        ["id", "necesidad_id", "tipo_ubicacion", "latitud", "longitud", "nombre_ubicacion", "observacion"],
    )
    joined = locations.merge(
        needs[need_columns],
        left_on="necesidad_id",
        right_on="id",
        how="inner",
        suffixes=("_ubicacion", "_necesidad"),
    )
    feature_group = folium.FeatureGroup(name="Necesidades e iniciativas", show=True)
    for _, row in joined.iterrows():
        if not valid_lat_lon(row.get("latitud"), row.get("longitud")):
            continue
        lat = float(row["latitud"])
        lon = float(row["longitud"])
        title = need_title(row)
        location_name = safe_text(row.get("nombre_ubicacion"), title)
        code = row.get("codigo_de_sistema")
        color = system_color(code)
        popup = (
            "<div style='min-width:290px'>"
            f"<h4 style='margin:0 0 8px;color:#002B5C'>{html.escape(title)}</h4>"
            f"<b>Sistema:</b> {html.escape(safe_text(row.get('sistema_de_abastecimiento')))}<br>"
            f"<b>Código:</b> {html.escape(safe_text(code))}<br>"
            f"<b>Tipo de necesidad:</b> {html.escape(safe_text(row.get('tipo_de_proyecto')))}<br>"
            f"<b>Tipo de ubicación:</b> {html.escape(safe_text(row.get('tipo_ubicacion')))}<br>"
            f"<b>Referencia:</b> {html.escape(location_name)}<br>"
            f"<b>Costo:</b> {html.escape(safe_text(row.get('costo')))}<br>"
            f"<b>Observación:</b> {html.escape(safe_text(row.get('observacion')))}"
            "</div>"
        )
        folium.CircleMarker(
            [lat, lon],
            radius=8,
            color="#FFFFFF",
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=0.95,
            tooltip=f"{safe_text(row.get('sistema_de_abastecimiento'))} · {title}",
            popup=folium.Popup(popup, max_width=450),
        ).add_to(feature_group)
        folium.Marker(
            [lat, lon],
            icon=folium.DivIcon(
                icon_size=(260, 24),
                icon_anchor=(-10, 13),
                html=f"<div class='need-map-label'>{html.escape(title)}</div>",
            ),
        ).add_to(feature_group)
        bounds.append([lat, lon])
    feature_group.add_to(map_object)
    return bounds


def add_dynamic_label_behavior(map_object: folium.Map) -> None:
    map_name = map_object.get_name()
    style = """
    <style>
    .need-map-label,.infra-map-label{
        display:none;
        width:max-content;
        max-width:240px;
        overflow:hidden;
        text-overflow:ellipsis;
        white-space:nowrap;
        background:rgba(255,255,255,.92);
        border:1px solid rgba(15,23,42,.24);
        border-radius:5px;
        padding:2px 5px;
        color:#0F172A;
        font:600 11px/1.25 Arial,sans-serif;
        box-shadow:0 1px 3px rgba(15,23,42,.18);
        pointer-events:none;
    }
    .need-map-label{border-left:4px solid #C9A227;font-size:12px;}
    </style>
    """
    script = f"""
    <script>
    setTimeout(function(){{
        var mapObject = window["{map_name}"];
        if (!mapObject) return;
        function updateMapLabels(){{
            var zoom = mapObject.getZoom();
            document.querySelectorAll(".need-map-label").forEach(function(element){{
                element.style.display = zoom >= 12 ? "block" : "none";
            }});
            document.querySelectorAll(".infra-map-label").forEach(function(element){{
                element.style.display = zoom >= 14 ? "block" : "none";
            }});
        }}
        mapObject.on("zoomend overlayadd overlayremove", updateMapLabels);
        updateMapLabels();
    }}, 450);
    </script>
    """
    map_object.get_root().header.add_child(Element(style))
    map_object.get_root().html.add_child(Element(script))


def build_map(
    needs: pd.DataFrame,
    locations: pd.DataFrame,
    selected_codes: Iterable[str] | None = None,
    include_infrastructure: bool = True,
    allow_click: bool = False,
) -> folium.Map:
    map_object = folium.Map(
        location=DEFAULT_CENTER,
        zoom_start=DEFAULT_ZOOM,
        tiles="CartoDB positron",
        control_scale=True,
        prefer_canvas=True,
    )
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(map_object)
    add_system_layer(map_object, selected_codes)
    if include_infrastructure:
        add_infrastructure_layers(map_object)
    bounds = add_need_locations(map_object, needs, locations)
    if bounds:
        if len(bounds) == 1:
            map_object.location = bounds[0]
            map_object.options["zoom"] = 14
        else:
            map_object.fit_bounds(bounds, padding=(35, 35))
    if allow_click:
        folium.LatLngPopup().add_to(map_object)
    folium.LayerControl(collapsed=False, position="topright").add_to(map_object)
    add_dynamic_label_behavior(map_object)
    return map_object


def normalize_category(value: object) -> str:
    text = safe_text(value, "").lower()
    return "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if unicodedata.category(character) != "Mn"
    ).strip()


def initiative_measure(row: pd.Series) -> tuple[float | None, str]:
    category = normalize_category(row.get("tipo_de_proyecto"))
    if "trasvase" in category or "recurso hidrico" in category:
        value = pd.to_numeric(row.get("caudal_estimado_lps"), errors="coerce")
        return (float(value), "L/s") if pd.notna(value) and float(value) > 0 else (None, "L/s")
    if "sustitucion de tuberias" in category:
        value = pd.to_numeric(row.get("km_estimado"), errors="coerce")
        return (float(value), "km") if pd.notna(value) and float(value) > 0 else (None, "km")
    if "almacenamiento" in category:
        value = pd.to_numeric(row.get("volumen_estimado_m3"), errors="coerce")
        return (float(value), "m³") if pd.notna(value) and float(value) > 0 else (None, "m³")
    return None, ""


def coordinate_text(values: Iterable[object]) -> str:
    coordinates: list[str] = []
    for value in values:
        numeric = pd.to_numeric(value, errors="coerce")
        if pd.notna(numeric):
            text = f"{float(numeric):.6f}"
            if text not in coordinates:
                coordinates.append(text)
    return "; ".join(coordinates)


def consultation_table(needs: pd.DataFrame, locations: pd.DataFrame) -> pd.DataFrame:
    need_columns = [
        "id",
        "objetivo_de_la_iniciativa",
        "breve_descripcion",
        "tipo_de_proyecto",
        "sistema_de_abastecimiento",
        "costo",
        "caudal_estimado_lps",
        "volumen_estimado_m3",
        "km_estimado",
    ]
    work = ensure_columns(needs, need_columns).copy()
    locations = ensure_columns(locations, ["id", "necesidad_id", "latitud", "longitud"])
    valid_locations = locations[
        locations.apply(
            lambda row: valid_lat_lon(row.get("latitud"), row.get("longitud")),
            axis=1,
        )
    ].copy()
    if not valid_locations.empty:
        if "id" in valid_locations.columns:
            valid_locations = valid_locations.sort_values("id")
        coordinates = (
            valid_locations.groupby("necesidad_id", as_index=False)
            .agg(
                Latitud=("latitud", coordinate_text),
                Longitud=("longitud", coordinate_text),
            )
        )
        work = work.merge(
            coordinates,
            left_on="id",
            right_on="necesidad_id",
            how="left",
        )
    else:
        work["Latitud"] = ""
        work["Longitud"] = ""

    measures = work.apply(initiative_measure, axis=1)
    work["Valor estimado"] = [
        "" if value is None else f"{value:,.2f}"
        for value, _ in measures
    ]
    work["Unidad medible"] = [unit for _, unit in measures]
    work["Nombre de la iniciativa"] = work.apply(need_title, axis=1)
    work["Descripción"] = work["breve_descripcion"].map(
        lambda value: safe_text(value, "Sin descripción registrada")
    )
    work["Latitud"] = work["Latitud"].fillna("")
    work["Longitud"] = work["Longitud"].fillna("")
    work["Costo"] = work["costo"].map(lambda value: safe_text(value, "Sin estimar"))
    table = work[
        [
            "Nombre de la iniciativa",
            "Descripción",
            "Valor estimado",
            "Unidad medible",
            "tipo_de_proyecto",
            "sistema_de_abastecimiento",
            "Costo",
            "Latitud",
            "Longitud",
        ]
    ].rename(
        columns={
            "tipo_de_proyecto": "Categoría",
            "sistema_de_abastecimiento": "Sistema de abastecimiento",
        }
    )
    return table.sort_values(
        ["Sistema de abastecimiento", "Categoría", "Nombre de la iniciativa"],
        na_position="last",
    )


def numeric_sum(series: pd.Series) -> float:
    return float(pd.to_numeric(series, errors="coerce").fillna(0).sum())


def executive_need_metrics(needs: pd.DataFrame) -> dict[str, float]:
    work = ensure_columns(
        needs,
        [
            "tipo_de_proyecto",
            "caudal_estimado_lps",
            "km_estimado",
            "volumen_estimado_m3",
        ],
    ).copy()
    work["_category"] = work["tipo_de_proyecto"].map(normalize_category)
    transfer_mask = work["_category"].str.contains("trasvase", na=False)
    production_mask = work["_category"].str.contains("recurso hidrico", na=False)
    return {
        "total_flow": numeric_sum(work["caudal_estimado_lps"]),
        "count": float(len(work)),
        "transfer_flow": numeric_sum(work.loc[transfer_mask, "caudal_estimado_lps"]),
        "production_flow": numeric_sum(work.loc[production_mask, "caudal_estimado_lps"]),
        "network_km": numeric_sum(work["km_estimado"]),
        "storage_m3": numeric_sum(work["volumen_estimado_m3"]),
    }


def render_executive_metrics(needs: pd.DataFrame) -> None:
    metrics = executive_need_metrics(needs)
    st.markdown(
        """
        <style>
        div[data-testid="stMetric"]{min-height:112px;}
        div[data-testid="stMetricValue"]{font-size:1.65rem;}
        div[data-testid="stMetricLabel"]{font-size:.94rem;font-weight:650;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    columns = st.columns(6)
    columns[0].metric("Caudal total de necesidad", f"{metrics['total_flow']:,.1f} L/s")
    columns[1].metric("Cantidad total de necesidades", f"{int(metrics['count']):,}")
    columns[2].metric("Caudal por trasvase", f"{metrics['transfer_flow']:,.1f} L/s")
    columns[3].metric("Aumento de producción", f"{metrics['production_flow']:,.1f} L/s")
    columns[4].metric("Red adicional estimada", f"{metrics['network_km']:,.2f} km")
    columns[5].metric("Volumen estimado", f"{metrics['storage_m3']:,.0f} m³")


def category_pie_chart(needs: pd.DataFrame):
    category_data = (
        ensure_columns(needs, ["tipo_de_proyecto"])
        .assign(
            Categoría=lambda frame: (
                frame["tipo_de_proyecto"]
                .fillna("")
                .astype(str)
                .str.strip()
                .replace({"": "Sin categoría"})
            )
        )
        .groupby("Categoría", as_index=False)
        .size()
        .rename(columns={"size": "Cantidad"})
        .sort_values("Cantidad", ascending=False)
    )
    if category_data.empty:
        return None

    total_initiatives = int(category_data["Cantidad"].sum())
    figure = px.pie(
        category_data,
        names="Categoría",
        values="Cantidad",
        hole=0.28,
        color="Categoría",
        color_discrete_sequence=(
            px.colors.qualitative.Bold
            + px.colors.qualitative.Safe
            + px.colors.qualitative.Set3
        ),
        title="Cantidad de iniciativas por categoría",
    )
    figure.update_traces(
        domain=dict(x=[0.04, 0.96], y=[0.35, 0.98]),
        textposition="inside",
        texttemplate="%{percent:.1%}",
        hovertemplate="<b>%{label}</b><br>Iniciativas: %{value}<br>Porcentaje: %{percent}<extra></extra>",
        marker=dict(line=dict(color="white", width=1.8)),
        sort=True,
    )
    figure.add_annotation(
        x=0.5,
        y=0.665,
        text=f"<b>{total_initiatives}</b><br><span style='font-size:12px'>iniciativas</span>",
        showarrow=False,
        align="center",
        font=dict(size=22, color="#002B5C"),
    )
    figure.update_layout(
        height=700,
        showlegend=True,
        title=dict(x=0.5, xanchor="center", font=dict(size=18)),
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=0.24,
            yanchor="top",
            title=None,
            font=dict(size=10),
            entrywidth=145,
            entrywidthmode="pixels",
        ),
        uniformtext_minsize=9,
        uniformtext_mode="hide",
        margin=dict(l=5, r=5, t=65, b=5),
        paper_bgcolor="white",
    )
    return figure


def render_consultation(needs: pd.DataFrame, locations: pd.DataFrame) -> None:
    st.markdown("### Consulta geoespacial de necesidades e iniciativas")
    st.caption(
        "Filtre la información por sistema, tipo de necesidad o clase de ubicación. "
        "Las etiquetas de necesidades aparecen desde zoom 12 y las de infraestructura desde zoom 14."
    )
    filter_a, filter_b, filter_c = st.columns(3)
    systems = clean_options(needs.get("sistema_de_abastecimiento", pd.Series(dtype=str)))
    need_types = clean_options(needs.get("tipo_de_proyecto", pd.Series(dtype=str)))
    selected_systems = filter_a.multiselect("Sistema de abastecimiento", systems, key="geo_filter_system")
    selected_types = filter_b.multiselect("Tipo de necesidad", need_types, key="geo_filter_type")
    selected_location_types = filter_c.multiselect(
        "Tipo de ubicación",
        LOCATION_TYPES,
        key="geo_filter_location_type",
    )
    include_infrastructure = st.checkbox(
        "Incluir capas de infraestructura de referencia",
        value=True,
        key="geo_include_infrastructure",
    )

    filtered_needs = needs.copy()
    if selected_systems:
        filtered_needs = filtered_needs[
            filtered_needs["sistema_de_abastecimiento"].astype(str).isin(selected_systems)
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
            pd.to_numeric(
                filtered_locations.get("necesidad_id"),
                errors="coerce",
            )
            .dropna()
            .astype(int)
        )
        filtered_needs = filtered_needs[
            pd.to_numeric(filtered_needs["id"], errors="coerce").isin(matched_need_ids)
        ]

    st.markdown("#### Detalle descriptivo de necesidades e iniciativas")
    detail_table = consultation_table(filtered_needs, filtered_locations)
    st.dataframe(
        detail_table,
        use_container_width=True,
        hide_index=True,
        height=420,
        column_config={
            "Nombre de la iniciativa": st.column_config.TextColumn(width="large"),
            "Descripción": st.column_config.TextColumn(width="large"),
            "Valor estimado": st.column_config.TextColumn(width="small"),
            "Unidad medible": st.column_config.TextColumn(width="small"),
            "Categoría": st.column_config.TextColumn(width="medium"),
            "Sistema de abastecimiento": st.column_config.TextColumn(width="medium"),
            "Costo": st.column_config.TextColumn(width="large"),
            "Latitud": st.column_config.TextColumn(width="medium"),
            "Longitud": st.column_config.TextColumn(width="medium"),
        },
    )

    st.markdown("#### Indicadores consolidados")
    render_executive_metrics(filtered_needs)

    selected_codes = (
        clean_options(filtered_needs.get("codigo_de_sistema", pd.Series(dtype=str)))
        if selected_systems
        else []
    )
    map_object = build_map(
        filtered_needs,
        filtered_locations,
        selected_codes=selected_codes,
        include_infrastructure=include_infrastructure,
    )
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
        figure = category_pie_chart(filtered_needs)
        if figure is None:
            st.info("No hay iniciativas para construir el gráfico por categoría.")
        else:
            st.plotly_chart(figure, use_container_width=True)


def selected_need_row(needs: pd.DataFrame, need_id: int) -> pd.Series:
    match = needs[pd.to_numeric(needs["id"], errors="coerce").eq(int(need_id))]
    return match.iloc[0]


def render_editor(needs: pd.DataFrame, locations: pd.DataFrame) -> None:
    st.markdown("### Georreferenciar y editar ubicaciones")
    st.caption(
        "Seleccione una necesidad, haga clic en el mapa y registre el punto. "
        "Puede asociar varios pines a una misma necesidad o clasificarla como No aplica."
    )
    needs = ensure_columns(
        needs,
        [
            "id",
            "objetivo_de_la_iniciativa",
            "breve_descripcion",
            "sistema_de_abastecimiento",
            "codigo_de_sistema",
            "tipo_de_proyecto",
            "observacion",
        ],
    )
    valid_needs = needs[pd.to_numeric(needs["id"], errors="coerce").notna()].copy()
    valid_needs["id"] = pd.to_numeric(valid_needs["id"], errors="coerce").astype(int)
    if valid_needs.empty:
        st.info("No hay necesidades con ID disponible.")
        return

    georeferenced_ids: set[int] = set()
    if not locations.empty:
        valid_pin_mask = locations.apply(
            lambda row: valid_lat_lon(row.get("latitud"), row.get("longitud")),
            axis=1,
        )
        georeferenced_ids = set(
            pd.to_numeric(
                locations.loc[valid_pin_mask, "necesidad_id"],
                errors="coerce",
            )
            .dropna()
            .astype(int)
        )

    all_need_ids = set(valid_needs["id"].astype(int))
    status_labels = {
        "Todas": f"Todas ({len(all_need_ids)})",
        "Con georreferencia": f"Con georreferencia ({len(all_need_ids & georeferenced_ids)})",
        "Sin georreferencia": f"Sin georreferencia ({len(all_need_ids - georeferenced_ids)})",
    }
    georeference_status = st.selectbox(
        "Estado de georreferenciación",
        options=list(status_labels),
        format_func=lambda value: status_labels[value],
        key="geo_editor_status_filter",
    )
    st.caption(
        "Con georreferencia: posee al menos un pin con coordenadas válidas. "
        "No aplica se clasifica como sin georreferencia."
    )

    filtered_valid_needs = valid_needs.copy()
    if georeference_status == "Con georreferencia":
        filtered_valid_needs = filtered_valid_needs[
            filtered_valid_needs["id"].isin(georeferenced_ids)
        ]
    elif georeference_status == "Sin georreferencia":
        filtered_valid_needs = filtered_valid_needs[
            ~filtered_valid_needs["id"].isin(georeferenced_ids)
        ]

    if filtered_valid_needs.empty:
        st.info("No hay necesidades que coincidan con el estado seleccionado.")
        return

    labels = {
        int(row["id"]): (
            f"{int(row['id'])} · {need_title(row)} · "
            f"{safe_text(row.get('sistema_de_abastecimiento'), 'Sin sistema')}"
        )
        for _, row in filtered_valid_needs.iterrows()
    }
    need_id = st.selectbox(
        "Necesidad o iniciativa",
        options=list(labels),
        format_func=lambda value: labels[value],
        key="geo_selected_need",
    )
    need = selected_need_row(filtered_valid_needs, int(need_id))
    current_locations = (
        locations[
            pd.to_numeric(locations.get("necesidad_id"), errors="coerce").eq(int(need_id))
        ].copy()
        if not locations.empty
        else locations.copy()
    )
    pin_count = (
        int(
            current_locations.apply(
                lambda row: valid_lat_lon(row.get("latitud"), row.get("longitud")),
                axis=1,
            ).sum()
        )
        if not current_locations.empty
        else 0
    )
    georeference_label = "Con georreferencia" if pin_count else "Sin georreferencia"
    st.info(
        f"**Sistema asociado:** {safe_text(need.get('sistema_de_abastecimiento'))}  |  "
        f"**Código:** {safe_text(need.get('codigo_de_sistema'))}  |  "
        f"**Tipo:** {safe_text(need.get('tipo_de_proyecto'))}  |  "
        f"**Estado:** {georeference_label}  |  **Pines:** {pin_count}"
    )

    with st.expander("Descripción o detalle de la necesidad", expanded=True):
        st.write(safe_text(need.get("breve_descripcion"), "No se ha registrado una descripción."))
        observation = safe_text(need.get("observacion"), "")
        if observation:
            st.markdown("**Observación:**")
            st.write(observation)
    map_object = build_map(
        valid_needs[pd.to_numeric(valid_needs["id"], errors="coerce").eq(int(need_id))],
        current_locations,
        selected_codes=[need.get("codigo_de_sistema")],
        include_infrastructure=True,
        allow_click=True,
    )
    map_result = st_folium(
        map_object,
        height=650,
        use_container_width=True,
        returned_objects=["last_clicked"],
        key=f"needs_editor_map_{need_id}",
    )
    clicked = (map_result or {}).get("last_clicked")
    if clicked and valid_lat_lon(clicked.get("lat"), clicked.get("lng")):
        st.session_state[f"geo_last_lat_{need_id}"] = float(clicked["lat"])
        st.session_state[f"geo_last_lon_{need_id}"] = float(clicked["lng"])

    last_lat = st.session_state.get(f"geo_last_lat_{need_id}")
    last_lon = st.session_state.get(f"geo_last_lon_{need_id}")
    if valid_lat_lon(last_lat, last_lon):
        st.success(f"Último punto seleccionado: {float(last_lat):.6f}, {float(last_lon):.6f}")
    else:
        st.warning("Haga clic en el mapa para seleccionar una ubicación.")

    st.markdown("#### Agregar ubicación")
    add_a, add_b = st.columns(2)
    location_type = add_a.selectbox(
        "Tipo de ubicación",
        LOCATION_TYPES,
        key=f"geo_new_type_{need_id}",
    )
    location_name = add_b.text_input(
        "Nombre o referencia del punto",
        value=need_title(need),
        key=f"geo_new_name_{need_id}",
    )
    manual = st.checkbox(
        "Digitar o ajustar coordenadas manualmente",
        key=f"geo_manual_{need_id}",
        disabled=location_type == "No aplica",
    )
    selected_lat = last_lat
    selected_lon = last_lon
    if manual and location_type != "No aplica":
        coord_a, coord_b = st.columns(2)
        selected_lat = coord_a.number_input(
            "Latitud WGS84",
            min_value=8.0,
            max_value=12.0,
            value=float(last_lat) if valid_lat_lon(last_lat, last_lon) else 9.96,
            format="%.7f",
            key=f"geo_manual_lat_{need_id}",
        )
        selected_lon = coord_b.number_input(
            "Longitud WGS84",
            min_value=-86.5,
            max_value=-82.0,
            value=float(last_lon) if valid_lat_lon(last_lat, last_lon) else -84.08,
            format="%.7f",
            key=f"geo_manual_lon_{need_id}",
        )
    location_note = st.text_area(
        "Observación de la ubicación",
        key=f"geo_new_note_{need_id}",
        placeholder="Ejemplo: ubicación aproximada, punto de referencia o criterio utilizado.",
    )
    can_add = location_type == "No aplica" or valid_lat_lon(selected_lat, selected_lon)
    if st.button(
        "Agregar ubicación a la necesidad",
        type="primary",
        disabled=not can_add,
        key=f"geo_add_{need_id}",
    ):
        new_location = pd.DataFrame(
            [
                {
                    "necesidad_id": int(need_id),
                    "tipo_ubicacion": location_type,
                    "latitud": None if location_type == "No aplica" else float(selected_lat),
                    "longitud": None if location_type == "No aplica" else float(selected_lon),
                    "nombre_ubicacion": location_name.strip(),
                    "observacion": location_note.strip(),
                }
            ]
        )
        upsert_rows("necesidades_ubicaciones", new_location)
        st.success("Ubicación agregada correctamente.")
        st.rerun()

    st.markdown("#### Ubicaciones asociadas")
    if current_locations.empty:
        st.info("Esta necesidad todavía no tiene ubicaciones registradas.")
        return

    current_locations = ensure_columns(
        current_locations,
        ["id", "necesidad_id", "tipo_ubicacion", "latitud", "longitud", "nombre_ubicacion", "observacion"],
    )
    editor_columns = ["id", "tipo_ubicacion", "nombre_ubicacion", "latitud", "longitud", "observacion"]
    location_editor = current_locations[editor_columns].copy().set_index("id")
    edited = st.data_editor(
        location_editor,
        use_container_width=True,
        hide_index=False,
        num_rows="fixed",
        column_config={
            "tipo_ubicacion": st.column_config.SelectboxColumn(
                "Tipo de ubicación",
                options=LOCATION_TYPES,
                required=True,
            ),
            "nombre_ubicacion": st.column_config.TextColumn("Nombre o referencia", width="large"),
            "latitud": st.column_config.NumberColumn("Latitud", format="%.7f"),
            "longitud": st.column_config.NumberColumn("Longitud", format="%.7f"),
            "observacion": st.column_config.TextColumn("Observación", width="large"),
        },
        key=f"geo_locations_editor_{need_id}",
    ).reset_index()

    action_a, action_b = st.columns(2)
    if action_a.button("Guardar cambios de ubicaciones", type="primary", key=f"geo_save_{need_id}"):
        edited["necesidad_id"] = int(need_id)
        no_apply = edited["tipo_ubicacion"].astype(str).eq("No aplica")
        edited.loc[no_apply, ["latitud", "longitud"]] = None
        invalid = edited[
            ~no_apply
            & ~edited.apply(lambda row: valid_lat_lon(row.get("latitud"), row.get("longitud")), axis=1)
        ]
        if not invalid.empty:
            st.error("Todas las ubicaciones distintas de No aplica deben tener coordenadas WGS84 válidas.")
        else:
            upsert_rows("necesidades_ubicaciones", edited)
            st.success("Ubicaciones actualizadas.")
            st.rerun()

    location_ids = pd.to_numeric(current_locations["id"], errors="coerce").dropna().astype(int).tolist()
    delete_ids = action_b.multiselect(
        "Eliminar ubicaciones por ID",
        options=location_ids,
        key=f"geo_delete_ids_{need_id}",
    )
    if action_b.button(
        "Eliminar ubicaciones seleccionadas",
        disabled=not delete_ids,
        key=f"geo_delete_{need_id}",
    ):
        delete_rows("necesidades_ubicaciones", delete_ids)
        st.success("Ubicaciones eliminadas; la necesidad principal no fue modificada.")
        st.rerun()

    st.markdown("##### Mover un pin con el mapa")
    movable_ids = current_locations[
        ~current_locations["tipo_ubicacion"].astype(str).eq("No aplica")
    ]["id"]
    movable_ids = pd.to_numeric(movable_ids, errors="coerce").dropna().astype(int).tolist()
    move_a, move_b = st.columns([2, 1])
    move_id = move_a.selectbox(
        "Pin que desea mover",
        options=movable_ids,
        key=f"geo_move_id_{need_id}",
        disabled=not movable_ids,
    ) if movable_ids else None
    if move_b.button(
        "Mover al último clic",
        disabled=move_id is None or not valid_lat_lon(last_lat, last_lon),
        key=f"geo_move_{need_id}",
    ):
        row = current_locations[
            pd.to_numeric(current_locations["id"], errors="coerce").eq(int(move_id))
        ].iloc[[0]].copy()
        row["latitud"] = float(last_lat)
        row["longitud"] = float(last_lon)
        upsert_rows("necesidades_ubicaciones", row)
        st.success("Pin desplazado correctamente.")
        st.rerun()


def vista_mapa_necesidades() -> None:
    st.subheader("Vista 4 · Mapa de necesidades e iniciativas")
    st.caption(
        "Herramienta para análisis, ordenamiento, georreferenciación y consulta sencilla "
        "de necesidades e iniciativas de los sistemas GAM."
    )
    needs = read_table("necesidades")
    locations = read_table("necesidades_ubicaciones")
    if needs.empty:
        st.warning("No hay necesidades disponibles para visualizar.")
        return
    needs = ensure_columns(
        needs,
        [
            "id",
            "objetivo_de_la_iniciativa",
            "breve_descripcion",
            "tipo_de_proyecto",
            "codigo_de_sistema",
            "sistema_de_abastecimiento",
            "costo",
        ],
    )
    locations = ensure_columns(
        locations,
        [
            "id",
            "necesidad_id",
            "tipo_ubicacion",
            "latitud",
            "longitud",
            "nombre_ubicacion",
            "observacion",
        ],
    )
    tab_query, tab_edit = st.tabs(["Mapa de consulta", "Georreferenciar / editar"])
    with tab_query:
        render_consultation(needs, locations)
    with tab_edit:
        render_editor(needs, locations)
