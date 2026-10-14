"""Indicadores territoriales únicos para la Vista 3.2.

Los cálculos usan las necesidades *ya filtradas* y el cruce geoespacial
sistema–cantón. No modifican ni consultan tablas adicionales en Supabase.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import pandas as pd
import streamlit as st

import geo_necesidades_legacy as legacy
import territorio_necesidades as territorio


def _text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    result = str(value).strip()
    return "" if result.casefold() in {"nan", "none", "<na>", "nat"} else result


def _keys(values: Iterable[str]) -> set[str]:
    return {_text(value).casefold() for value in values if _text(value)}


def consolidated_territory(
    needs: pd.DataFrame,
    crosswalk: pd.DataFrame,
    *,
    selected_systems: Iterable[str] = (),
    selected_provinces: Iterable[str] = (),
    selected_cantons: Iterable[str] = (),
    selected_districts: Iterable[str] = (),
) -> dict[str, pd.DataFrame]:
    """Consolidar sistemas, provincias y pares (provincia, cantón) sin duplicar.

    Un mismo sistema puede estar asociado a varias necesidades, pero aparece
    solo una vez en su indicador. Las relaciones administrativas se limitan
    a los filtros activos (incluido distrito) antes de consolidarse.
    """
    columns = {
        "sistemas": [
            "Código", "Sistema de abastecimiento", "Provincias",
            "Cantones", "Necesidades asociadas",
        ],
        "provincias": ["Provincia", "Cantones", "Sistemas", "Necesidades asociadas"],
        "cantones": ["Provincia", "Cantón", "Sistemas", "Necesidades asociadas"],
    }
    empty = {key: pd.DataFrame(columns=labels) for key, labels in columns.items()}
    if needs.empty:
        return empty

    needed = {
        "sistema_codigo", "sistema_nombre", "nivel", "provincia",
        "canton", "distrito", "etiqueta",
    }
    catalog = crosswalk.copy() if needed.issubset(crosswalk.columns) else pd.DataFrame(columns=sorted(needed))
    name_to_code: dict[str, str] = {}
    code_to_name: dict[str, str] = {}
    for _, rec in catalog.iterrows():
        code = territorio._normalize_code(rec.get("sistema_codigo"))
        name = _text(rec.get("sistema_nombre"))
        if code:
            code_to_name.setdefault(code, name or code)
            if name:
                name_to_code[name.casefold()] = code

    chosen_systems = _keys(selected_systems)
    chosen_codes = {name_to_code[name] for name in chosen_systems if name in name_to_code}
    chosen_provinces = _keys(selected_provinces)
    chosen_cantons = _keys(selected_cantons)
    chosen_districts = _keys(selected_districts)
    geography_filtered = bool(chosen_provinces or chosen_cantons or chosen_districts)

    # Los filtros de distrito usan la columna 'etiqueta', tal como la usa
    # associate_needs para crear distritos_asociados en la Vista 3.2.
    district_pairs = {
        (
            territorio._normalize_code(rec["sistema_codigo"]),
            _text(rec["provincia"]).casefold(),
            _text(rec["canton"]).casefold(),
        )
        for _, rec in catalog.loc[catalog["nivel"].eq("distrito")].iterrows()
        if _text(rec["etiqueta"]).casefold() in chosen_districts
    } if chosen_districts else set()

    territory_by_code: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for _, rec in catalog.loc[catalog["nivel"].eq("canton")].iterrows():
        code = territorio._normalize_code(rec["sistema_codigo"])
        province = _text(rec["provincia"])
        canton = _text(rec["canton"])
        label = _text(rec["etiqueta"]) or canton
        if not code or not province or not canton:
            continue
        if chosen_provinces and province.casefold() not in chosen_provinces:
            continue
        if chosen_cantons and label.casefold() not in chosen_cantons:
            continue
        if chosen_districts and (code, province.casefold(), canton.casefold()) not in district_pairs:
            continue
        territory_by_code[code].add((province, canton))

    systems: dict[str, dict] = {}
    # Relación única: necesidad, código, provincia y cantón.
    relations: set[tuple[str, str, str, str]] = set()
    for index, need in needs.iterrows():
        raw_id = pd.to_numeric(need.get("id"), errors="coerce")
        need_id = f"id:{int(raw_id)}" if pd.notna(raw_id) else f"fila:{index}"
        names = legacy.split_multi_values(need.get("sistema_de_abastecimiento"))
        codes = territorio._codes_from_need(need, name_to_code)
        if not codes:
            codes = [name_to_code.get(name.casefold(), f"NOMBRE:{name.casefold()}") for name in names]
        codes = list(dict.fromkeys(codes))
        positional_names = dict(zip(codes, names)) if len(codes) == len(names) else {}

        for code in codes:
            label = code_to_name.get(code) or positional_names.get(code) or code
            given_name = positional_names.get(code, "")
            if chosen_systems and not (
                code in chosen_codes
                or label.casefold() in chosen_systems
                or given_name.casefold() in chosen_systems
                or code.casefold() in chosen_systems
                or (len(codes) == 1 and any(name.casefold() in chosen_systems for name in names))
            ):
                continue

            areas = territory_by_code.get(code, set())
            if geography_filtered and not areas:
                continue
            entry = systems.setdefault(code, {"nombre": label, "necesidades": set()})
            entry["necesidades"].add(need_id)
            for province, canton in areas:
                relations.add((need_id, code, province, canton))

    system_rows = []
    for code, data in systems.items():
        areas = {(prov, canton) for _, system_code, prov, canton in relations if system_code == code}
        provinces = sorted({prov for prov, _ in areas})
        cantons = sorted({f"{prov} · {canton}" for prov, canton in areas})
        system_rows.append({
            "Código": "" if code.startswith("NOMBRE:") else code,
            "Sistema de abastecimiento": data["nombre"].removeprefix("NOMBRE:"),
            "Provincias": "; ".join(provinces),
            "Cantones": "; ".join(cantons),
            "Necesidades asociadas": len(data["necesidades"]),
        })

    province_groups: dict[str, dict[str, set]] = defaultdict(
        lambda: {"cantones": set(), "sistemas": set(), "necesidades": set()}
    )
    canton_groups: dict[tuple[str, str], dict[str, set]] = defaultdict(
        lambda: {"sistemas": set(), "necesidades": set()}
    )
    for need_id, code, province, canton in relations:
        province_groups[province]["cantones"].add(canton)
        province_groups[province]["sistemas"].add(code)
        province_groups[province]["necesidades"].add(need_id)
        canton_groups[(province, canton)]["sistemas"].add(code)
        canton_groups[(province, canton)]["necesidades"].add(need_id)

    province_rows = [{
        "Provincia": province,
        "Cantones": len(data["cantones"]),
        "Sistemas": len(data["sistemas"]),
        "Necesidades asociadas": len(data["necesidades"]),
    } for province, data in province_groups.items()]
    canton_rows = [{
        "Provincia": province,
        "Cantón": canton,
        "Sistemas": len(data["sistemas"]),
        "Necesidades asociadas": len(data["necesidades"]),
    } for (province, canton), data in canton_groups.items()]
    tables = {
        "sistemas": pd.DataFrame(system_rows, columns=columns["sistemas"]),
        "provincias": pd.DataFrame(province_rows, columns=columns["provincias"]),
        "cantones": pd.DataFrame(canton_rows, columns=columns["cantones"]),
    }
    for key, table in tables.items():
        if not table.empty:
            tables[key] = table.sort_values(
                columns[key][:2] if key != "provincias" else ["Provincia"],
                kind="stable",
            ).reset_index(drop=True)
    return tables


def _quantity(number: int, singular: str, plural: str) -> str:
    """Expresar cantidades en español con concordancia gramatical."""
    return f"{number} {singular if number == 1 else plural}"


def _enumerate_names(names: list[str]) -> str:
    """Unir nombres en prosa (A, B y C) en lugar de una tabla o lista."""
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " y " + names[-1]


def _render_territorial_narrative(kind: str, tables: dict[str, pd.DataFrame]) -> None:
    """Detalle narrativo según las necesidades filtradas, sin tablas."""
    detail = tables[kind]
    if detail.empty:
        st.info("No hay registros asociados a los filtros seleccionados.")
        return

    count = len(detail)
    if kind == "sistemas":
        st.markdown(
            f"En la selección actual se identifican **"
            f"{_quantity(count, 'sistema de abastecimiento', 'sistemas de abastecimiento')}"
            "** distintos vinculados con necesidades de inversión. "
            "A continuación se indican sus nombres, la cantidad de necesidades "
            "asociadas a cada uno y las provincias relacionadas con su cobertura."
        )
        descriptions = []
        for _, item in detail.iterrows():
            code = _text(item["Código"])
            name = _text(item["Sistema de abastecimiento"])
            system_label = f"{code} — {name}" if code and code.casefold() != name.casefold() else (name or code)
            provinces = [
                part.strip() for part in _text(item["Provincias"]).split(";") if part.strip()
            ]
            territorial_phrase = (
                "con cobertura asociada en " + _enumerate_names(provinces)
                if provinces else "sin asociación provincial determinada"
            )
            needs_count = int(item["Necesidades asociadas"])
            descriptions.append(
                f"**{system_label}** ("
                f"{_quantity(needs_count, 'necesidad asociada', 'necesidades asociadas')}; "
                f"{territorial_phrase})"
            )
        # Párrafos acotados para que las selecciones numerosas sigan siendo legibles.
        for start in range(0, len(descriptions), 5):
            st.markdown(_enumerate_names(descriptions[start:start + 5]) + ".")

    elif kind == "provincias":
        st.markdown(
            f"Las necesidades consultadas tienen relación territorial con "
            f"**{_quantity(count, 'provincia', 'provincias')}**. "
            "El desglose considera únicamente las provincias asociadas "
            "a los sistemas incluidos en los filtros."
        )
        descriptions = []
        for _, item in detail.iterrows():
            descriptions.append(
                f"En **{item['Provincia']}** se identifican "
                f"**{_quantity(int(item['Cantones']), 'cantón', 'cantones')}**, "
                f"**{_quantity(int(item['Sistemas']), 'sistema de abastecimiento', 'sistemas de abastecimiento')}** "
                f"y **{_quantity(int(item['Necesidades asociadas']), 'necesidad vinculada', 'necesidades vinculadas')}**"
            )
        for start in range(0, len(descriptions), 3):
            st.markdown(". ".join(descriptions[start:start + 3]) + ".")

    elif kind == "cantones":
        st.markdown(
            f"El alcance territorial de las necesidades seleccionadas comprende "
            f"**{_quantity(count, 'cantón', 'cantones')}**. "
            "Cada cantón se considera una sola vez dentro de su provincia, "
            "aunque esté relacionado con varios sistemas o necesidades."
        )
        for province, group in detail.groupby("Provincia", sort=True):
            descriptions = []
            for _, item in group.iterrows():
                descriptions.append(
                    f"**{item['Cantón']}** ("
                    f"{_quantity(int(item['Sistemas']), 'sistema', 'sistemas')} y "
                    f"{_quantity(int(item['Necesidades asociadas']), 'necesidad', 'necesidades')})"
                )
            st.markdown(
                f"En la provincia de **{province}** se identifican "
                f"{_enumerate_names(descriptions)}."
            )


def render_territorial_counters(
    needs: pd.DataFrame,
    crosswalk: pd.DataFrame,
    *,
    selected_systems: Iterable[str] = (),
    selected_provinces: Iterable[str] = (),
    selected_cantons: Iterable[str] = (),
    selected_districts: Iterable[str] = (),
) -> None:
    """Mostrar tres KPI con un panel de detalle activado por clic."""
    tables = consolidated_territory(
        needs, crosswalk,
        selected_systems=selected_systems,
        selected_provinces=selected_provinces,
        selected_cantons=selected_cantons,
        selected_districts=selected_districts,
    )
    indicators = (
        ("sistemas", "Sistemas de abastecimiento"),
        ("provincias", "Provincias"),
        ("cantones", "Cantones"),
    )
    active_key = "_geo32_resumen_abierto"
    active = st.session_state.get(active_key)
    cols = st.columns(3)
    for col, (key, title) in zip(cols, indicators):
        with col:
            with st.container(border=True):
                st.metric(title, f"{len(tables[key]):,}")
                button_text = "Ocultar detalle" if active == key else "Ver detalle"
                if st.button(button_text, key=f"geo32_detalle_{key}", use_container_width=True):
                    active = None if active == key else key
                    st.session_state[active_key] = active

    if active in tables:
        title = dict(indicators)[active]
        with st.container(border=True):
            st.markdown(f"**Detalle consolidado · {title}**")
            st.caption(
                "Totales únicos según los filtros activos. Las necesidades asociadas "
                "se contabilizan una sola vez dentro de cada fila del resumen."
            )
            _render_territorial_narrative(active, tables)
