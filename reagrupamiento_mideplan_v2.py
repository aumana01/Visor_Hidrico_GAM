from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import pandas as pd
import streamlit as st

import reagrupamiento_mideplan as base


# Vista 3.4 - modelo compacto de cartera GAM.
#
# El modelo anterior segmentaba primero por cluster/sistema/categoria y podia
# producir decenas de propuestas. Esta version parte de familias de inversion
# transversales para toda la GAM, conserva cada ID de origen y separa las
# atenciones que razonablemente pueden tramitarse con presupuesto operativo.

MODEL_VERSION = "compacto-gam-2026.2"

THRESHOLDS_2026 = {
    "Bienes y servicios": {
        "mayor": 309_887_014.0,
        "menor": 77_471_753.0,
    },
    "Obras": {
        "mayor": 1_112_414_922.0,
        "menor": 278_103_730.0,
    },
}


@dataclass(frozen=True)
class PortfolioRule:
    key: str
    name: str
    family: str
    contract_nature: str
    process: str
    patterns: tuple[str, ...]
    description: str


# Una fila por familia equivale, como maximo, a un proyecto de inversion.
# El orden tambien funciona como prioridad de clasificacion para evitar que una
# necesidad termine simultaneamente en dos proyectos.
PORTFOLIO_RULES = (
    PortfolioRule(
        "almacenamiento_gam",
        "Construccion y ampliacion de tanques de almacenamiento y regulacion de agua potable en la GAM",
        "Almacenamiento y regulacion",
        "Obras",
        "Construccion / Ampliacion",
        (r"tanque", r"almacenamiento", r"volumen de reserva", r"regulacion"),
        "Integra las necesidades actuales y futuras de almacenamiento y regulacion de la GAM en una cartera programatica de tanques y obras complementarias.",
    ),
    PortfolioRule(
        "fuentes_produccion",
        "Ampliacion y mejoramiento de fuentes, captaciones y campos de pozos para abastecimiento de la GAM",
        "Fuentes, captaciones y produccion",
        "Obras",
        "Ampliacion / Mejoras",
        (
            r"pozo", r"naciente", r"captacion", r"fuente", r"aumento de recurso",
            r"increment.*produccion", r"perforacion", r"estudio hidrogeolog",
            r"investigacion hidrogeolog", r"prospeccion", r"exploracion.*acuifer",
            r"modelacion.*acuifer",
        ),
        "Consolida la identificacion, estudio, habilitacion, ampliacion, rehabilitacion y proteccion de fuentes, captaciones y campos de pozos para aumentar la seguridad hidrica de la GAM.",
    ),
    PortfolioRule(
        "aducciones_interconexiones",
        "Construccion y mejoramiento de aducciones, conducciones, interconexiones y trasvases estrategicos de la GAM",
        "Aducciones, conducciones e interconexiones",
        "Obras",
        "Construccion / Mejoras",
        (r"aduccion", r"conduccion", r"interconexion", r"trasvase", r"linea de impulsion", r"tuberia principal"),
        "Integra obras troncales actuales y futuras para transportar, interconectar y redistribuir recurso entre fuentes, plantas, tanques y sistemas de la GAM.",
    ),
    PortfolioRule(
        "potabilizacion",
        "Ampliacion y modernizacion de plantas potabilizadoras y procesos de tratamiento de agua potable de la GAM",
        "Potabilizacion, calidad y gestion de residuos de proceso",
        "Obras",
        "Ampliacion / Modernizacion",
        (
            r"planta potabil", r"potabilizacion", r"filtracion", r"floculacion",
            r"sedimentacion", r"desinfeccion", r"calidad de agua",
            r"lodo.*potabil", r"potabil.*lodo", r"agua residual.*potabil",
            r"potabil.*agua residual", r"recircul.*agua", r"lavado de filtro",
            r"residuo.*planta potabil",
        ),
        "Consolida la ampliacion y modernizacion de plantas potabilizadoras, incluyendo procesos de tratamiento, manejo de lodos, aguas residuales de proceso, recirculacion y obras de calidad asociadas.",
    ),
    PortfolioRule(
        "bombeo_electromecanico",
        "Mejoramiento de estaciones de bombeo, impulsiones y sistemas electromecanicos estrategicos de la GAM",
        "Bombeo, impulsiones y sistemas electromecanicos",
        "Obras",
        "Rehabilitacion / Mejoras",
        (r"estacion de bombeo", r"sistema de bombeo", r"rebombeo", r"booster", r"equipo de bombeo", r"electromecan", r"impulsion"),
        "Agrupa renovacion, ampliacion, respaldo y modernizacion de estaciones de bombeo, impulsiones y sistemas electromecanicos estrategicos.",
    ),
    PortfolioRule(
        "instrumentacion",
        "Instalacion de instrumentacion, sensores, medicion, telemetria y automatizacion para los sistemas de la GAM",
        "Instrumentacion, medicion, telemetria y automatizacion",
        "Bienes y servicios",
        "Equipamiento / Implementacion",
        (r"instrumentacion", r"sensor", r"telemet", r"scada", r"caudalimet", r"macromed", r"automatizacion", r"monitoreo en linea"),
        "Agrupa adquisicion, instalacion, integracion y puesta en marcha de instrumentacion, medicion, sensores, telemetria y automatizacion bajo estandares comunes para la GAM.",
    ),
    PortfolioRule(
        "propiedades_servidumbres",
        "Regularizacion de propiedades y servidumbres asociadas a infraestructura operativa de la GAM",
        "Regularizacion predial y servidumbres",
        "Bienes y servicios",
        "Regularizacion",
        (r"servidumbre", r"regulariz.*propiedad", r"regulariz.*terreno", r"derecho de paso", r"catastro.*propiedad", r"afectacion predial"),
        "Consolida levantamientos, expedientes y gestiones para regularizar propiedades, servidumbres y derechos de paso requeridos por infraestructura existente y futura.",
    ),
    PortfolioRule(
        "infraestructura_integral",
        "Programa integral de infraestructura prioritaria para sistemas de abastecimiento de la GAM",
        "Redes de distribucion y optimizacion de sistemas",
        "Obras",
        "Mejoras / Optimizacion",
        (
            r"red de distrib", r"sustitucion.*tuber", r"renovacion.*tuber",
            r"ampliacion.*red", r"sectorizacion", r"valvula reguladora",
            r"control de presion", r"vrp", r"optimiz", r"reduccion.*perdida",
            r"anc", r"continuidad", r"presion", r"estabilizacion",
            r"proteccion.*infraestructura", r"vulnerabilidad", r"amenaza",
            r"deslizamiento", r"socavacion", r"reforzamiento estructural",
        ),
        "Programa integral para renovar, ampliar, sectorizar y optimizar redes de distribucion y componentes asociados, incorporando necesidades actuales y futuras de capacidad, continuidad, presion, reduccion de perdidas y resiliencia.",
    ),
)

RULE_BY_KEY = {rule.key: rule for rule in PORTFOLIO_RULES}
PROJECT_ID_BY_RULE = {
    "almacenamiento_gam": "PE-001",
    "fuentes_produccion": "PE-002",
    "aducciones_interconexiones": "PE-003",
    "potabilizacion": "PE-005",
    "infraestructura_integral": "PE-006",
    "bombeo_electromecanico": "PE-007",
    "instrumentacion": "PE-008",
    "propiedades_servidumbres": "PE-009",
}
MAX_PROJECTS = len(PROJECT_ID_BY_RULE)

OPERATIONAL_CATEGORIES = (
    "mantenimiento correctivo preventivo",
    "mantenimiento correctivo y preventivo",
    "optimizacion",
    "relacion con asadas y terceros",
    "ordenamiento comercial",
)


def _fold(value: object) -> str:
    text = base._clean(value).lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _parse_number(token: str) -> float | None:
    value = token.replace(" ", "").strip(".,")
    if not value:
        return None
    if "," in value and "." in value:
        last_comma, last_dot = value.rfind(","), value.rfind(".")
        decimal = "," if last_comma > last_dot else "."
        thousands = "." if decimal == "," else ","
        tail = value.split(decimal)[-1]
        if len(tail) == 2:
            value = value.replace(thousands, "").replace(decimal, ".")
        else:
            value = value.replace(",", "").replace(".", "")
    elif "," in value:
        tail = value.split(",")[-1]
        value = value.replace(",", ".") if len(tail) == 2 else value.replace(",", "")
    elif "." in value:
        tail = value.split(".")[-1]
        value = value if len(tail) == 2 else value.replace(".", "")
    try:
        return float(value)
    except ValueError:
        return None


def _cost_bounds(value: object) -> tuple[float, float | None]:
    if isinstance(value, (int, float)) and not pd.isna(value):
        number = max(0.0, float(value))
        return number, number
    text = base._clean(value)
    if not text:
        return 0.0, None
    numbers = [
        number
        for number in (_parse_number(token) for token in re.findall(r"\d[\d., ]*", text))
        if number is not None
    ]
    if not numbers:
        return 0.0, None
    folded = _fold(text)
    if "mas de" in folded or "mayor de" in folded or ">" in text:
        return max(numbers), None
    if len(numbers) >= 2:
        return min(numbers), max(numbers)
    return numbers[0], numbers[0]


def _procurement_label(lower: float, upper: float | None, nature: str) -> str:
    thresholds = THRESHOLDS_2026[nature]
    major, minor = thresholds["mayor"], thresholds["menor"]
    if lower >= major:
        return "Licitacion mayor"
    if upper is not None and upper < minor:
        return "Licitacion reducida"
    if lower >= minor and (upper is None or upper < major):
        return "Licitacion menor" if upper is not None else "Licitacion menor o mayor - monto por precisar"
    if upper is not None and lower >= minor and upper >= major:
        return "Licitacion menor o mayor - rango cruza umbral"
    if upper is None:
        return "Por determinar - estimacion abierta"
    if upper >= minor:
        return "Licitacion reducida o menor - rango cruza umbral"
    return "Licitacion reducida"


def _threshold_text(nature: str) -> str:
    values = THRESHOLDS_2026[nature]
    return (
        f"{nature}: mayor desde CRC {values['mayor']:,.0f}; "
        f"menor desde CRC {values['menor']:,.0f}; reducida por debajo de ese monto"
    )


def _rule_for_text(text: str) -> PortfolioRule:
    # Las ocho familias son definitivas. PE-006 funciona ademas como cartera
    # integral de redes/optimizacion y como respaldo para necesidades de
    # abastecimiento que no encajen con suficiente certeza en otra familia.
    for rule in PORTFOLIO_RULES:
        if rule.patterns and any(re.search(pattern, text) for pattern in rule.patterns):
            return rule
    return RULE_BY_KEY["infraestructura_integral"]


def _raw_text(row: pd.Series, raw: pd.Series) -> str:
    fields = (
        row.get("categoria_clasificacion"), row.get("idea_proyecto"), row.get("descripcion_idea"),
        row.get("descripcion_avance"), raw.get("objetivo_de_la_iniciativa"), raw.get("breve_descripcion"),
        raw.get("principal_reto_por_superar"), raw.get("observacion"),
    )
    return _fold(" ".join(base._clean(value) for value in fields if base._clean(value)))


def _is_operational_category(category: object) -> bool:
    folded = _fold(category)
    return any(name in folded for name in OPERATIONAL_CATEGORIES)


def _has_explicit_investment_signal(rule: PortfolioRule, text: str, volume_m3: float | None) -> bool:
    if rule.key in {"fuentes_produccion", "potabilizacion", "instrumentacion", "propiedades_servidumbres"}:
        return True
    if rule.key == "almacenamiento_gam":
        return volume_m3 is None or volume_m3 >= 500 or any(word in text for word in ("construccion", "ampliacion", "nuevo tanque"))
    if rule.key == "infraestructura_integral" and any(
        word in text for word in (
            "red de distrib", "sectorizacion", "control de presion", "vrp",
            "optimiz", "reduccion de perdida", "anc", "continuidad",
            "presion", "vulnerabilidad", "resiliencia",
        )
    ):
        return True
    return any(word in text for word in ("construccion", "ampliacion", "sustitucion", "renovacion", "rehabilitacion", "mejoramiento"))


def _classify_need(row: pd.Series, raw: pd.Series) -> dict[str, object]:
    text = _raw_text(row, raw)
    rule = _rule_for_text(text)
    category = row.get("categoria_clasificacion")
    volume_raw = pd.to_numeric(raw.get("volumen_estimado_m3"), errors="coerce")
    volume = float(volume_raw) if pd.notna(volume_raw) and float(volume_raw) > 0 else None
    lower, upper = _cost_bounds(raw.get("costo"))
    procurement = _procurement_label(lower, upper, rule.contract_nature)
    major = procurement == "Licitacion mayor"

    operational_reason = ""
    if rule.key == "almacenamiento_gam" and volume is not None and volume < 500 and not major:
        operational_reason = "Almacenamiento local menor de 500 m3; revisar atencion con presupuesto operativo."
    elif _is_operational_category(category) and not major and not _has_explicit_investment_signal(rule, text, volume):
        operational_reason = (
            "Categoria susceptible de atencion operativa mediante licitacion menor o reducida; "
            "no se incorpora automaticamente a un proyecto de inversion."
        )

    if major:
        operational_reason = ""

    return {
        "rule": rule,
        "route": "Atencion operativa" if operational_reason else "Proyecto de inversion",
        "reason": operational_reason or (
            "La necesidad requiere licitacion mayor y debe formularse como proyecto de inversion."
            if major else rule.description
        ),
        "cost_lower": lower,
        "cost_upper": upper,
        "procurement": procurement,
        "volume": volume,
    }


def _format_cost_range(lower: float, upper: float | None) -> str:
    if upper is None:
        return f"Desde CRC {lower:,.0f}" if lower > 0 else "Sin estimacion suficiente"
    if abs(lower - upper) < 0.01:
        return f"CRC {lower:,.0f}"
    return f"CRC {lower:,.0f} a {upper:,.0f}"


def _build_project_row(
    rule: PortfolioRule,
    group: pd.DataFrame,
    raw_by_id: dict[int, pd.Series],
) -> dict[str, object]:
    labels, codes = base._system_names(group)
    population, services = base._beneficiaries(codes)
    themes: set[str] = set()
    for _, item in group.iterrows():
        text = " ".join([base._clean(item.get("idea_proyecto")), base._clean(item.get("descripcion_idea"))])
        themes |= base._themes(text, base._clean(item.get("categoria_clasificacion")))

    dims = {
        "caudal_lps": base._unique_dimension(group, raw_by_id, "caudal_estimado_lps"),
        "volumen_m3": base._unique_dimension(group, raw_by_id, "volumen_estimado_m3"),
        "km": base._unique_dimension(group, raw_by_id, "km_estimado"),
    }
    ids = sorted(pd.to_numeric(group["necesidad_id"], errors="coerce").dropna().astype(int).unique().tolist())
    provinces = base._join(v for value in group["ubicacion_provincia"] for v in base._split(value))
    cantons = base._join(v for value in group["ubicacion_canton"] for v in base._split(value))
    districts = base._join(v for value in group["distritos"] for v in base._split(value))
    communities = base._join((v for value in group["comunidades"] for v in base._split(value)), limit=10)
    bh = base._minimum_bh(group)
    ich = base._critical_ich(group)
    score, potential = base._potential_score(group, codes, themes, dims)

    bounds = [_cost_bounds(raw_by_id.get(nid, pd.Series(dtype=object)).get("costo")) for nid in ids]
    lower = sum(item[0] for item in bounds)
    upper = sum(item[1] for item in bounds) if bounds and all(item[1] is not None for item in bounds) else None
    procurement = _procurement_label(lower, upper, rule.contract_nature)
    categories = base._join(group["categoria_clasificacion"].fillna("").astype(str).tolist())

    return {
        "proyecto_id": PROJECT_ID_BY_RULE[rule.key],
        "nombre_proyecto": rule.name,
        "tipologia_mideplan": rule.process,
        "servicio": "Acueducto",
        "familia_estrategica": rule.family,
        "criterio_agrupamiento": "Cartera tematica transversal GAM",
        "categorias_agrupadas": categories or "Sin categoria registrada",
        "ruta_recomendada": "Proyecto de inversion",
        "naturaleza_contrato": rule.contract_nature,
        "procedimiento_estimado_2026": procurement,
        "rango_costo_registrado": _format_cost_range(lower, upper),
        "umbral_2026": _threshold_text(rule.contract_nature),
        "ids_asociados": ", ".join(map(str, ids)),
        "codigos_internos": base._join(group["codigo_interno"].fillna("").astype(str).tolist()),
        "cantidad_necesidades": len(ids),
        "sistemas_beneficiados": base._join(labels),
        "provincias": provinces,
        "cantones": cantons,
        "distritos": districts,
        "comunidades": communities,
        "problema_necesidad": base._problem_statement(group, themes),
        "descripcion": (
            f"{rule.description} Toma como contexto {len(ids)} necesidades actualmente registradas en el Banco de Ideas, "
            "sin limitar el alcance del proyecto a esas intervenciones. La formulacion se plantea con cobertura GAM y "
            "capacidad de incorporar, priorizar y ejecutar necesidades futuras compatibles durante el horizonte del proyecto, "
            "manteniendo la trazabilidad individual de cada actuacion."
        ),
        "alcance_componentes": base._scope(themes, dims),
        "objetivo_general": (
            f"Desarrollar e implementar de manera programatica las intervenciones de {rule.family.lower()} requeridas "
            "en los sistemas de abastecimiento de la GAM, atendiendo las necesidades actuales identificadas y permitiendo "
            "incorporar necesidades futuras de igual naturaleza, priorizadas segun criticidad, beneficio esperado, "
            "seguridad del abastecimiento y viabilidad tecnica."
        ),
        "objetivos_especificos": base._specific_objectives(themes, dims),
        "poblacion_referencia": round(population) if population else None,
        "servicios_referencia": round(services, 2) if services else None,
        "caudal_lps": round(dims["caudal_lps"], 2) if dims["caudal_lps"] else None,
        "volumen_m3": round(dims["volumen_m3"], 2) if dims["volumen_m3"] else None,
        "km_red": round(dims["km"], 3) if dims["km"] else None,
        "condicion_hidrica_critica": ich,
        "estado_bh_critico": round(bh, 3) if bh is not None else None,
        "potencial_puntos": score,
        "potencial": potential,
        "nivel_preinversion_sugerido": base._maturity(group),
        "informacion_faltante": base._missing_information(group, themes, dims),
    }


def build_groups() -> tuple[pd.DataFrame, pd.DataFrame]:
    work = base.seguimiento._prepare_work()
    if work.empty:
        st.session_state["mideplan_operational"] = pd.DataFrame()
        return pd.DataFrame(), pd.DataFrame()

    raw = base.seguimiento.base.read_table("necesidades")
    raw_by_id: dict[int, pd.Series] = {}
    if not raw.empty and "id" in raw.columns:
        for _, raw_row in raw.iterrows():
            nid = pd.to_numeric(raw_row.get("id"), errors="coerce")
            if pd.notna(nid):
                raw_by_id[int(nid)] = raw_row

    work = work.copy().reset_index(drop=True)
    for field in (
        "caudal_estimado_lps", "volumen_estimado_m3", "km_estimado", "principal_reto_por_superar",
        "observacion", "costo", "responsabilidad_atencion",
    ):
        work[field] = [raw_by_id.get(int(nid), pd.Series(dtype=object)).get(field) for nid in work["necesidad_id"]]

    project_positions: dict[str, list[int]] = {rule.key: [] for rule in PORTFOLIO_RULES}
    classifications: dict[int, dict[str, object]] = {}
    operational_rows: list[dict[str, object]] = []

    for position, row in work.iterrows():
        nid = int(row["necesidad_id"])
        raw_row = raw_by_id.get(nid, pd.Series(dtype=object))
        result = _classify_need(row, raw_row)
        rule = result["rule"]
        classifications[nid] = result
        if result["route"] == "Proyecto de inversion":
            project_positions[rule.key].append(position)
        else:
            operational_rows.append({
                "id_necesidad": nid,
                "categoria": base._clean(row.get("categoria_clasificacion")) or "Sin categoria",
                "necesidad": base._clean(row.get("idea_proyecto")),
                "sistemas": base._clean(row.get("codigo_nombre_sistema")),
                "ruta_recomendada": result["route"],
                "procedimiento_estimado_2026": result["procurement"],
                "naturaleza_contrato": rule.contract_nature,
                "costo_registrado": base._clean(raw_row.get("costo")) or "Sin dato",
                "justificacion": result["reason"],
            })

    rows: list[dict[str, object]] = []
    trace_parts: list[pd.DataFrame] = []
    for rule in PORTFOLIO_RULES:
        positions = project_positions[rule.key]
        if not positions:
            continue
        group = work.iloc[positions].copy()
        rows.append(_build_project_row(rule, group, raw_by_id))
        trace = group.copy()
        trace.insert(0, "proyecto_estrategico", PROJECT_ID_BY_RULE[rule.key])
        trace.insert(1, "nombre_proyecto_estrategico", rule.name)
        trace["ruta_modelo"] = "Proyecto de inversion"
        trace["familia_cartera"] = rule.family
        trace["procedimiento_estimado_2026"] = [classifications[int(nid)]["procurement"] for nid in trace["necesidad_id"]]
        trace["justificacion_modelo"] = [classifications[int(nid)]["reason"] for nid in trace["necesidad_id"]]
        trace_parts.append(trace)

    projects = pd.DataFrame(rows)
    operational = pd.DataFrame(operational_rows)
    st.session_state["mideplan_operational"] = operational

    if projects.empty:
        return projects, pd.DataFrame()

    if len(projects) > MAX_PROJECTS:
        raise RuntimeError(f"El modelo compacto excedio el maximo de {MAX_PROJECTS} proyectos.")

    projects = projects.sort_values(
        ["potencial_puntos", "cantidad_necesidades", "estado_bh_critico"],
        ascending=[False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    projects["orden_estrategico"] = range(1, len(projects) + 1)

    traceability = pd.concat(trace_parts, ignore_index=True) if trace_parts else pd.DataFrame()
    if not traceability.empty:
        names = dict(zip(projects["proyecto_id"], projects["nombre_proyecto"]))
        traceability["nombre_proyecto_estrategico"] = traceability["proyecto_estrategico"].map(names)

    # Las atenciones operativas tambien forman parte de la trazabilidad total,
    # pero no inflan el numero de proyectos propuestos.
    if not operational.empty:
        op_ids = set(operational["id_necesidad"].astype(int).tolist())
        op_trace = work[work["necesidad_id"].astype(int).isin(op_ids)].copy()
        op_trace.insert(0, "proyecto_estrategico", "OPERATIVO")
        op_trace.insert(1, "nombre_proyecto_estrategico", "Atencion con presupuesto operativo")
        op_trace["ruta_modelo"] = "Atencion operativa"
        op_trace["familia_cartera"] = "Gestion operativa"
        op_trace["procedimiento_estimado_2026"] = [classifications[int(nid)]["procurement"] for nid in op_trace["necesidad_id"]]
        op_trace["justificacion_modelo"] = [classifications[int(nid)]["reason"] for nid in op_trace["necesidad_id"]]
        traceability = pd.concat([traceability, op_trace], ignore_index=True)

    front = [
        "orden_estrategico", "proyecto_id", "nombre_proyecto", "familia_estrategica",
        "ruta_recomendada", "naturaleza_contrato", "procedimiento_estimado_2026",
        "rango_costo_registrado", "umbral_2026", "categorias_agrupadas", "tipologia_mideplan",
        "criterio_agrupamiento", "ids_asociados", "cantidad_necesidades", "sistemas_beneficiados",
        "provincias", "cantones", "distritos", "comunidades", "problema_necesidad", "descripcion",
        "alcance_componentes", "objetivo_general", "objetivos_especificos", "poblacion_referencia",
        "servicios_referencia", "caudal_lps", "volumen_m3", "km_red", "condicion_hidrica_critica",
        "estado_bh_critico", "potencial", "potencial_puntos", "nivel_preinversion_sugerido",
        "informacion_faltante", "servicio", "codigos_internos",
    ]
    return projects[front], traceability


def _project_column_config() -> dict:
    config = base._project_column_config_original()
    config.update({
        "familia_estrategica": st.column_config.TextColumn("Cartera tematica GAM", width="large"),
        "ruta_recomendada": st.column_config.TextColumn("Ruta recomendada", width="medium"),
        "naturaleza_contrato": st.column_config.TextColumn("Naturaleza contractual", width="medium"),
        "procedimiento_estimado_2026": st.column_config.TextColumn("Procedimiento estimado 2026", width="large"),
        "rango_costo_registrado": st.column_config.TextColumn("Rango agregado registrado", width="medium"),
        "umbral_2026": st.column_config.TextColumn("Umbral AyA 2026 aplicado", width="large"),
        "categorias_agrupadas": st.column_config.TextColumn("Categorias de origen", width="large"),
        "criterio_agrupamiento": st.column_config.TextColumn("Criterio de agrupamiento", width="large"),
    })
    return config


def _filter_projects(projects: pd.DataFrame) -> pd.DataFrame:
    f1, f2, f3, f4 = st.columns([1.1, 1.7, 1.6, 2.2])
    potential = f1.multiselect("Potencial", ["Muy alto", "Alto", "Medio", "Bajo"], key="compact_potential")
    families = sorted(projects["familia_estrategica"].dropna().astype(str).unique().tolist())
    selected_families = f2.multiselect("Cartera tematica", families, key="compact_family")
    procedures = sorted(projects["procedimiento_estimado_2026"].dropna().astype(str).unique().tolist())
    selected_procedures = f3.multiselect("Contratacion 2026", procedures, key="compact_procurement")
    search = f4.text_input("Buscar", placeholder="Proyecto, ID, sistema, categoria, canton...", key="compact_search")

    out = projects.copy()
    if potential:
        out = out[out["potencial"].isin(potential)]
    if selected_families:
        out = out[out["familia_estrategica"].isin(selected_families)]
    if selected_procedures:
        out = out[out["procedimiento_estimado_2026"].isin(selected_procedures)]
    query = base._norm(search)
    if query:
        columns = [
            "proyecto_id", "nombre_proyecto", "familia_estrategica", "categorias_agrupadas",
            "ids_asociados", "sistemas_beneficiados", "cantones", "distritos", "descripcion",
        ]
        searchable = out[columns].fillna("").astype(str).agg(" ".join, axis=1)
        out = out[searchable.apply(lambda value: query in base._norm(value))]
    return out


def _clear_stale_model() -> None:
    if st.session_state.get("mideplan_model_version") == MODEL_VERSION:
        return
    for key in ("mideplan_projects", "mideplan_trace", "mideplan_operational"):
        st.session_state.pop(key, None)
    st.session_state["mideplan_model_version"] = MODEL_VERSION


def vista_reagrupamiento_mideplan() -> None:
    _clear_stale_model()
    st.markdown("#### Modelo compacto de cartera GAM")
    st.info(
        f"El modelo consolida las necesidades en {MAX_PROJECTS} proyectos tematicos definitivos para toda la GAM, "
        "con codigos fijos PE-001, PE-002, PE-003, PE-005, PE-006, PE-007, PE-008 y PE-009. "
        "No se divide automaticamente por cluster o sistema. Las necesidades que correspondan a redes de distribucion, "
        "sectorizacion, control de presiones, reduccion de perdidas, resiliencia u optimizacion se integran en PE-006. "
        "Las atenciones estrictamente operativas pueden mantenerse fuera de la cartera cuando no contienen una inversion estrategica."
    )
    st.caption(
        "Reglas destacadas: PE-004 se integra definitivamente en PE-005, por lo que el manejo de lodos, aguas residuales "
        "de proceso y recirculacion en plantas potabilizadoras forma parte del proyecto de modernizacion de potabilizacion. "
        "Los estudios hidrogeologicos y acciones de identificacion de recurso se integran en PE-002. PE-006 se orienta a "
        "redes de distribucion y optimizacion integral de los sistemas, con alcance suficiente para incorporar necesidades futuras."
    )

    with st.expander("Umbrales de contratacion administrativa AyA 2026", expanded=False):
        st.dataframe(
            pd.DataFrame([
                {"Tipo": "Bienes y servicios", "Licitacion mayor": "Igual o mas de CRC 309,887,014", "Licitacion menor": "CRC 77,471,753 a menos de CRC 309,887,014", "Licitacion reducida": "Menos de CRC 77,471,753"},
                {"Tipo": "Obras", "Licitacion mayor": "Igual o mas de CRC 1,112,414,922", "Licitacion menor": "CRC 278,103,730 a menos de CRC 1,112,414,922", "Licitacion reducida": "Menos de CRC 278,103,730"},
            ]),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Los rangos de costo abiertos o insuficientes se marcan para validacion; no se presume un procedimiento "
            "sin respaldo numerico. Toda necesidad que por su monto minimo alcance licitacion mayor se dirige a proyecto de inversion."
        )

    base._original_view()

    operational = st.session_state.get("mideplan_operational")
    if isinstance(operational, pd.DataFrame) and not operational.empty:
        st.markdown("### Necesidades orientadas a atencion operativa")
        st.caption(
            "Estas necesidades permanecen trazables, pero no se cuentan como proyectos de inversion. "
            "La ruta es orientativa y debe confirmarse cuando se disponga de una estimacion de costo definitiva."
        )
        st.metric("Necesidades para presupuesto operativo", f"{len(operational):,}")
        st.dataframe(operational, use_container_width=True, hide_index=True, height=480)
        st.download_button(
            "Descargar necesidades de atencion operativa (CSV)",
            data=operational.to_csv(index=False).encode("utf-8-sig"),
            file_name="necesidades_atencion_operativa.csv",
            mime="text/csv",
        )


# Se conservan los componentes visuales y de trazabilidad de la Vista 3.4 base,
# reemplazando unicamente el motor de agrupamiento, filtros y columnas.
base._project_column_config_original = base._project_column_config
base._original_view = base.vista_reagrupamiento_mideplan
base.build_groups = build_groups
base._project_column_config = _project_column_config
base._filter_projects = _filter_projects
