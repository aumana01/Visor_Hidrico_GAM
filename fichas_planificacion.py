from __future__ import annotations

import hashlib
import io
import re
import shutil
import subprocess
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import xlrd
import xlwt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xlutils.copy import copy as copy_xls

from database import read_optional_table
from dta_nombres_gam import CANTONS as DTA_CANTONS, DISTRICTS as DTA_DISTRICTS
import reagrupamiento_mideplan_v2 as regroup


DEFAULT_TEMPLATE_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "Plant_Necesidad_Inversion_Acueducto.xls"
)
FICHA_MODEL_VERSION = "ficha35-2026.4"

GAM_SYSTEMS = [
    ("MEA01", "ME-A-01 Tres Ríos"),
    ("MEA02", "ME-A-02 Guadalupe"),
    ("MEA03", "ME-A-03 El Llano"),
    ("MEA04", "ME-A-04 Los Sitios"),
    ("MEA05", "ME-A-05 Salitral"),
    ("MEA06", "ME-A-06 San Juan de Dios"),
    ("MEA07", "ME-A-07 San Antonio de Escazú"),
    ("MEA08", "ME-A-08 Los Cuadros"),
    ("MEA09", "ME-A-09 Alajuelita"),
    ("MEA10", "ME-A-10 Mata de Plátano"),
    ("MEA11", "ME-A-11 Guatuso Patarrá"),
    ("MEA12", "ME-A-12 Quitirrisí (Ciudad Colón)"),
    ("MEA13", "ME-A-13 San Jerónimo de Moravia"),
    ("MEA14", "ME-A-14 San Rafael de Coronado"),
    ("MEA15", "ME-A-15 San Pablo"),
    ("MEA16", "ME-A-16 Potrerillos-San Antonio (incluye antiguo ME-A-23 Barrio España)"),
    ("MEA17", "ME-A-17 La Valencia"),
    ("MEA18", "ME-A-18 Sur Alajuelita"),
    ("MEA19", "ME-A-19 Puente Mulas"),
    ("MEA20", "ME-A-20 Padre Carazo"),
    ("MEA21", "ME-A-21 Chiverrales"),
    ("MEA22", "ME-A-22 Pizote"),
    ("MEA24", "ME-A-24 Matinilla"),
    ("MEA25", "ME-A-25 Sur de Escazú"),
    ("MEA26", "ME-A-26 Ticufres-Quebrada Honda"),
    ("MEA27", "ME-A-27 El Guarco"),
    ("MEA28", "ME-A-28 Vista de Mar"),
    ("MEA29", "ME-A-29 Lajas"),
    ("MEA30", "ME-A-30 Jericó"),
    ("MEA31", "ME-A-31 Puriscal"),
]
GAM_SYSTEM_CODES = [code for code, _ in GAM_SYSTEMS]
GAM_SYSTEMS_TEXT = "; ".join(name for _, name in GAM_SYSTEMS)
GAM_CODES_TEXT = ", ".join(GAM_SYSTEM_CODES)
GAM_PROVINCES_TEXT = "San José; Alajuela; Cartago; Heredia"
GAM_MAJOR_COMMUNITIES_TEXT = (
    "San José centro, Pavas, Hatillo, Uruca, San Sebastián, Desamparados, San Juan de Dios, "
    "Alajuelita, Escazú, San Rafael de Escazú, Santa Ana, Pozos, Ciudad Colón, Puriscal, "
    "Guadalupe, Ipís, Purral, Mata de Plátano, Tibás, Moravia, San Pedro, Curridabat, "
    "Tres Ríos, Cartago, Paraíso, El Tejar, Alajuela, San Rafael de Alajuela, Belén, "
    "Heredia, San Pablo, Santo Domingo, San Rafael de Heredia y demás comunidades urbanas "
    "y periurbanas atendidas por los sistemas GAM."
)
PROVINCE_BY_CODE = {"1": "San José", "2": "Alajuela", "3": "Cartago", "4": "Heredia"}
PURISCAL_DISTRICTS = (
    "Santiago", "Mercedes Sur", "Barbacoas", "Grifo Alto", "San Rafael",
    "Candelarita", "Desamparaditos", "San Antonio", "Chires",
)

POPULATION_BY_SYSTEM = {
    "MEA01": 464344.592,
    "MEA02": 64236.1811,
    "MEA03": 605.751864,
    "MEA04": 142972.675,
    "MEA05": 5383.32679,
    "MEA06": 37338.181,
    "MEA07": 8530.00102,
    "MEA08": 42526.2107,
    "MEA09": 10488.8686,
    "MEA10": 2945.73469,
    "MEA11": 3825.0447,
    "MEA12": 4132.50467,
    "MEA13": 7036.20768,
    "MEA14": 9708.27742,
    "MEA15": 38318.549,
    "MEA16": 55456.4658,
    "MEA17": 244816.892,
    "MEA18": 17.3045127,
    "MEA19": 251299.91,
    "MEA20": 4830.11347,
    "MEA21": 2914.42071,
    "MEA22": 8775.52054,
    "MEA24": 234.02814,
    "MEA25": 32.2226993,
    "MEA26": 320.59518,
    "MEA27": 26535.5207,
    "MEA28": 1892.89767,
    "MEA29": 119.446597,
    "MEA30": 1115.32725,
    "MEA31": 40230.8352,
}

ANC_BY_SYSTEM = {
    "MEA01": 54.0,
    "MEA02": 23.0,
    "MEA03": 88.0,
    "MEA04": 59.0,
    "MEA05": 64.0,
    "MEA06": 75.0,
    "MEA07": 68.0,
    "MEA08": 48.0,
    "MEA09": 73.0,
    "MEA10": 43.0,
    "MEA11": 37.0,
    "MEA12": 37.0,
    "MEA13": 46.0,
    "MEA14": 46.0,
    "MEA15": 56.0,
    "MEA16": 43.0,
    "MEA17": 63.0,
    "MEA18": 63.0,
    "MEA19": 66.0,
    "MEA20": 49.0,
    "MEA21": 61.0,
    "MEA22": 51.0,
    "MEA24": 68.0,
    "MEA25": 79.0,
    "MEA26": 48.0,
    "MEA27": 30.0,
    "MEA28": 67.0,
    "MEA29": 72.0,
    "MEA30": 59.0,
    "MEA31": 51.0,
}

ZONE_BY_SYSTEM = {
    "MEA01": ("Zona 1", "Zona 2", "Zona 4"),
    "MEA02": ("Zona 4",),
    "MEA03": ("Zona 1",),
    "MEA04": ("Zona 4",),
    "MEA05": ("Zona 3",),
    "MEA06": ("Zona 2",),
    "MEA07": ("Zona 3",),
    "MEA08": ("Zona 4",),
    "MEA09": ("Zona 1",),
    "MEA10": ("Zona 4",),
    "MEA11": ("Zona 2",),
    "MEA12": ("Zona 3",),
    "MEA13": ("Zona 4",),
    "MEA14": ("Zona 4",),
    "MEA15": ("Zona 4",),
    "MEA16": ("Zona 3",),
    "MEA17": ("Zona 1",),
    "MEA18": ("Zona 1",),
    "MEA19": ("Zona 1", "Zona 2", "Zona 3"),
    "MEA20": ("Zona 2",),
    "MEA21": ("Zona 4",),
    "MEA22": ("Zona 4",),
    "MEA24": ("Zona 3",),
    "MEA25": ("Zona 3",),
    "MEA26": ("Zona 3",),
    "MEA27": ("Zona 5",),
    "MEA28": ("Zona 4",),
    "MEA29": ("Zona 3",),
    "MEA30": ("Zona 2",),
    "MEA31": ("Zona 6",),
}

COST_OPTIONS = [
    "Entre ¢0.00 y ¢100,000.00",
    "Entre ¢100,001.00 y ¢500,000.00",
    "Entre ¢500,001.00 y ¢1,000,000.00",
    "Entre ¢1,000,001.00 y ¢5,000,000.00",
    "Más de ¢5,000,000.00",
]

FIELD_LABELS = {
    "necesidad_descripcion": "Descripción de la necesidad u oportunidad (Especifique)",
    "provincia": "Provincia",
    "canton": "Cantón",
    "distrito": "Distrito",
    "comunidad": "Comunidad",
    "sistemas": "Sistema",
    "codigos_sistema": "Código del sistema",
    "subgerencia": "Subgerencia",
    "direccion_uen": "Dirección o UEN",
    "region_zona": "Región o Zona",
    "cantonal": "Cantonal",
    "latitudes": "Latitud",
    "longitudes": "Longitud",
    "cuenta_sistema_agua": "Cuenta la población con sistema para el suministro de agua potable",
    "disponibilidad_recurso": "Cuenta la comunidad con disponibilidad del recurso hídrico",
    "poblacion_atendida": "Población atendida mediante el sistema de acueducto",
    "poblacion_afectada": "Población afectada con la problemática",
    "calidad_aceptada": "Cumple la calidad del agua suministrada con los niveles aceptados",
    "horas_servicio": "Horas que se brinda el servicio (diario)",
    "anc_porcentaje": "Porcentaje de Agua No Contabilizada",
    "deficiencia_produccion": "Deficiencia en la producción, con respecto a la demanda",
    "deficiencia_produccion_observacion": "Observación de la deficiencia en la producción",
    "infraestructura_condicion": "Infraestructura y equipos en condiciones para la prestación del servicio",
    "infraestructura_observacion": "Observación de infraestructura y equipos",
    "exposicion_danos": "Equipos e infraestructura expuestos a daños de terceros y eventos naturales",
    "exposicion_observacion": "Observación de exposición a daños",
    "calidad_riesgo_salud": "La calidad del agua suministrada pone en riesgo la salud de los usuarios",
    "relacion_niveles_servicio": "Existe relación del servicio con continuidad, cantidad y costos",
    "sector_desarrollo_nacional": "Necesidad de inversión ubicada en sector de desarrollo nacional",
    "canton_prioritario_irs": "Necesidad de inversión en cantones prioritarios para el país (MIDEPLAN) IRS",
    "vida_util": "Cumplimiento de la vida útil de servicio del sistema",
    "afectacion_eventos_naturales": "Afectación del servicio a raíz de eventos naturales",
    "alto_grado_inseguridad": "Infraestructura y equipos ubicados en sectores con alto grado de inseguridad",
    "mandato": "Necesidad de inversión por Mandato Judicial / Orden Sanitaria / Otro",
    "idea_solucion": "Idea de proyecto que da solución a la necesidad u oportunidad (Especifique)",
    "estudios_basicos": "Se cuenta con recursos o estudios básicos necesarios para llevar a cabo la idea de proyecto",
    "rango_costos": "Estimación de costos de la posible alternativa de solución",
    "unidad_organizacional": "Unidad Organizacional que plantea la necesidad u oportunidad",
    "encargado_unidad": "Encargado Unidad Organizacional que plantea la necesidad u oportunidad",
    "patrocinador": "Patrocinador de la Iniciativa",
    "fecha": "Fecha",
}

TEMPLATE_MARKERS = {
    "necesidad_descripcion": (
        "descripcion de la necesidad u oportunidad",
        "descripción de la necesidad u oportunidad",
    ),
    "subgerencia": ("subgerencia",),
    "direccion_uen": ("direccion o uen", "dirección o uen"),
    "region_zona": ("region o zona", "región o zona"),
    "cantonal": ("cantonal",),
    "provincia": ("provincia",),
    "canton": ("canton", "cantón"),
    "distrito": ("distrito",),
    "comunidad": ("comunidad",),
    "codigos_sistema": ("codigo del sistema", "código del sistema", "codigo sis"),
    "sistemas": ("sistema de abastecimiento",),
    "latitudes": ("latitud",),
    "longitudes": ("longitud",),
    "cuenta_sistema_agua": ("cuenta la poblacion con sistema", "cuenta la población con sistema"),
    "disponibilidad_recurso": ("cuenta la comunidad con disponibilidad",),
    "poblacion_atendida": ("poblacion atendida mediante", "población atendida mediante"),
    "poblacion_afectada": ("poblacion afectada", "población afectada"),
    "calidad_aceptada": ("cumple la calidad del agua",),
    "horas_servicio": ("horas que se brinda el servicio",),
    "anc_porcentaje": ("porcentaje agua no contabilizada", "porcentaje de agua no contabilizada"),
    "deficiencia_produccion": ("deficiencia en la produccion", "deficiencia en la producción"),
    "infraestructura_condicion": ("infraestructura y equipos en condiciones",),
    "exposicion_danos": ("equipos e infraestructura expuestos",),
    "calidad_riesgo_salud": ("pone en riesgo la salud",),
    "relacion_niveles_servicio": ("existe relacion del servicio", "existe relación del servicio"),
    "sector_desarrollo_nacional": ("sector de desarrollo nacional",),
    "canton_prioritario_irs": ("cantones prioritarios",),
    "vida_util": ("cumplimiento de la vida util", "cumplimiento de la vida útil"),
    "afectacion_eventos_naturales": ("afectacion del servicio a raiz", "afectación del servicio a raíz"),
    "alto_grado_inseguridad": ("alto grado de inseguridad",),
    "mandato": ("mandato judicial",),
    "idea_solucion": ("idea de proyecto que da solucion", "idea de proyecto que da solución"),
    "estudios_basicos": ("se cuenta con recursos u estudios", "se cuenta con recursos o estudios"),
    "rango_costos": ("estimacion de costos de la posible alternativa", "estimación de costos de la posible alternativa"),
    "unidad_organizacional": ("unidad organizacional que plantea",),
    "encargado_unidad": ("encargado unidad organizacional",),
    "patrocinador": ("patrocinador de la iniciativa",),
    "fecha": ("fecha",),
}

OBSERVATION_ANCHORS = {
    "deficiencia_produccion_observacion": "deficiencia_produccion",
    "infraestructura_observacion": "infraestructura_condicion",
    "exposicion_observacion": "exposicion_danos",
}


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", _clean(value).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean(value)
        key = _norm(text)
        if text and key and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _system_codes(value: object) -> list[str]:
    text = _clean(value).upper().replace("ME-A-", "MEA").replace("ME-A", "MEA")
    numbers = [int(item) for item in re.findall(r"\bMEA(\d{1,2})\b", text)]
    codes = {f"MEA{number:02d}" for number in numbers if number != 32}
    # ME-A-23 Barrio España fue integrado al sistema ME-A-16 Potrerillos-San Antonio.
    if "MEA23" in codes:
        codes.remove("MEA23")
        codes.add("MEA16")
    return sorted(codes)


def _parse_ids(value: object) -> list[int]:
    return sorted({int(item) for item in re.findall(r"\d+", _clean(value))})


def _gam_cantons_text() -> str:
    entries: list[str] = []
    for (province_code, _canton_code), canton in sorted(
        DTA_CANTONS.items(),
        key=lambda item: (int(item[0][0]), int(item[0][1])),
    ):
        province = PROVINCE_BY_CODE.get(province_code)
        if province:
            entries.append(f"{canton} ({province})")
    if "Puriscal (San José)" not in entries:
        entries.append("Puriscal (San José)")
    return "; ".join(_unique(entries))


def _gam_districts_text() -> str:
    grouped: dict[tuple[str, str], list[str]] = {}
    for (province_code, canton_code, _district_code), district in sorted(
        DTA_DISTRICTS.items(),
        key=lambda item: (int(item[0][0]), int(item[0][1]), int(item[0][2])),
    ):
        province = PROVINCE_BY_CODE.get(province_code)
        canton = DTA_CANTONS.get((province_code, canton_code))
        if province and canton:
            grouped.setdefault((province, canton), []).append(district)

    blocks = [
        f"{canton} ({province}): {', '.join(_unique(districts))}"
        for (province, canton), districts in grouped.items()
    ]
    blocks.append(f"Puriscal (San José): {', '.join(PURISCAL_DISTRICTS)}")
    return "; ".join(blocks)


GAM_CANTONS_TEXT = _gam_cantons_text()
GAM_DISTRICTS_TEXT = _gam_districts_text()


def _zones(codes: list[str]) -> str:
    zones = {
        zone
        for code in codes
        for zone in ZONE_BY_SYSTEM.get(code, ())
    }
    return ", ".join(sorted(zones, key=lambda item: int(re.search(r"\d+", item).group())))


def _population(codes: list[str]) -> float:
    return sum(POPULATION_BY_SYSTEM.get(code, 0.0) for code in set(codes))


def _weighted_anc(codes: list[str]) -> float:
    weighted = [
        (POPULATION_BY_SYSTEM[code], ANC_BY_SYSTEM[code])
        for code in set(codes)
        if code in POPULATION_BY_SYSTEM and code in ANC_BY_SYSTEM
    ]
    total_population = sum(population for population, _ in weighted)
    if total_population <= 0:
        return 0.0
    return sum(population * anc for population, anc in weighted) / total_population


def _project_trace(project_id: str) -> pd.DataFrame:
    trace = st.session_state.get("mideplan_trace")
    if not isinstance(trace, pd.DataFrame) or trace.empty:
        return pd.DataFrame()
    if "proyecto_estrategico" not in trace.columns:
        return pd.DataFrame()
    return trace[trace["proyecto_estrategico"].astype(str).eq(project_id)].copy()


def _coordinate_values(need_ids: list[int]) -> tuple[str, str]:
    locations = read_optional_table("necesidades_ubicaciones")
    if locations.empty or "necesidad_id" not in locations.columns:
        return "", ""
    work = locations.copy()
    work["necesidad_id"] = pd.to_numeric(work["necesidad_id"], errors="coerce")
    work = work[work["necesidad_id"].isin(need_ids)]
    if work.empty:
        return "", ""

    latitude_values: list[str] = []
    longitude_values: list[str] = []
    for _, row in work.iterrows():
        latitude = pd.to_numeric(row.get("latitud"), errors="coerce")
        longitude = pd.to_numeric(row.get("longitud"), errors="coerce")
        location = _clean(row.get("nombre_ubicacion"))
        suffix = f" ({location})" if location else ""
        if pd.notna(latitude):
            latitude_values.append(f"{float(latitude):.6f}{suffix}")
        if pd.notna(longitude):
            longitude_values.append(f"{float(longitude):.6f}{suffix}")
    return "; ".join(_unique(latitude_values)), "; ".join(_unique(longitude_values))


def _context(trace: pd.DataFrame, terms: tuple[str, ...], fallback: str) -> str:
    if trace.empty:
        return fallback
    columns = [
        "idea_proyecto",
        "descripcion_idea",
        "principal_reto_por_superar",
        "observacion",
        "descripcion_avance",
        "problema_necesidad",
    ]
    selected: list[str] = []
    for column in columns:
        if column not in trace.columns:
            continue
        for value in trace[column].tolist():
            text = _clean(value)
            folded = _norm(text)
            if text and any(_norm(term) in folded for term in terms):
                selected.append(text)
    joined = "; ".join(_unique(selected))
    return joined[:1800] if joined else fallback


def _current_need_context(trace: pd.DataFrame, limit: int = 6) -> str:
    if trace.empty:
        return ""
    items: list[str] = []
    for column in ("categoria_clasificacion", "idea_proyecto", "descripcion_idea", "principal_reto_por_superar"):
        if column not in trace.columns:
            continue
        for value in trace[column].tolist():
            text = _clean(value)
            if text:
                items.append(text.rstrip("."))
    unique = _unique(items)
    if not unique:
        return ""
    selected = unique[:limit]
    suffix = "; entre otros antecedentes" if len(unique) > limit else ""
    return "; ".join(selected) + suffix


def _general_need_description(project: pd.Series, trace: pd.DataFrame) -> str:
    name = _clean(project.get("nombre_proyecto")) or "Proyecto integral para los sistemas de la GAM"
    family = _clean(project.get("familia_estrategica")) or "infraestructura de abastecimiento"
    context = _current_need_context(trace)
    current_count = len(_parse_ids(project.get("ids_asociados")))

    text = (
        f"Los 30 sistemas de abastecimiento que conforman el ámbito de gestión GAM requieren una estrategia "
        f"programática e integral de {family.lower()} que permita atender brechas de capacidad, confiabilidad, "
        "continuidad, eficiencia, seguridad operativa y resiliencia, de acuerdo con la condición particular de cada "
        "sistema y con la evolución de la demanda. "
    )
    if current_count:
        text += (
            f"Como punto de partida, la Vista 3.4 agrupa {current_count} necesidades actualmente registradas"
            + (f", entre ellas: {context}. " if context else ". ")
        )
    text += (
        f"El proyecto «{name}» no se limita a esas necesidades iniciales: se formula con cobertura para toda la GAM "
        "y con un alcance suficientemente flexible para incorporar durante su horizonte nuevas intervenciones de la "
        "misma naturaleza que resulten de balances oferta-demanda, crecimiento poblacional y urbano, envejecimiento "
        "de activos, cambios en la operación, reducción de pérdidas, variabilidad climática, eventos naturales, "
        "afectaciones de terceros o nuevas prioridades institucionales. La necesidad se concibe, por tanto, como una "
        "cartera de inversión escalable y priorizable, capaz de resolver condiciones actuales y de anticipar "
        "requerimientos futuros sin tener que formular un proyecto independiente para cada actuación."
    )
    return text


def _general_service_observations(project: pd.Series, trace: pd.DataFrame) -> tuple[str, str, str]:
    context = _current_need_context(trace, limit=4)
    context_sentence = f" Entre los antecedentes actuales se identifican: {context}." if context else ""
    family = _clean(project.get("familia_estrategica")).lower() or "infraestructura de abastecimiento"

    production = (
        "Los sistemas de la GAM presentan condiciones heterogéneas entre oferta y demanda, con sectores que pueden "
        "operar con déficit, márgenes reducidos, dependencia de fuentes o trasvases, variación estacional de caudales "
        "y crecimiento sostenido de la demanda. La formulación debe considerar balances hídricos actualizados y "
        "proyecciones de demanda para priorizar incorporaciones de recurso, redistribuciones, mejoras operativas y "
        "obras que aumenten el margen de seguridad del abastecimiento."
        + context_sentence
        + " El alcance debe permitir incorporar nuevas brechas de producción o capacidad que se identifiquen durante "
        "la vida del proyecto, sin restringirse a los déficits actualmente documentados."
    )
    infrastructure = (
        "La infraestructura de los 30 sistemas GAM presenta edades, capacidades, materiales, niveles de redundancia "
        "y condiciones de operación diferentes. El proyecto debe permitir rehabilitar, sustituir, ampliar, modernizar "
        f"y estandarizar los componentes de {family} que resulten prioritarios, atendiendo fallas o limitaciones actuales "
        "y reservando capacidad para incorporar intervenciones futuras asociadas con crecimiento de la demanda, "
        "obsolescencia, eficiencia energética, reducción de pérdidas, continuidad y mejora del desempeño hidráulico."
        + context_sentence
    )
    exposure = (
        "La infraestructura de abastecimiento de la GAM se distribuye en zonas urbanas y periurbanas con exposición "
        "variable a obras de terceros, tránsito y desarrollo vial, vandalismo o accesos no controlados, así como a "
        "sismos, inundaciones, deslizamientos, erosión, socavación, caída de materiales y otros eventos naturales. "
        "La formulación integral debe incorporar criterios de protección física, redundancia, accesibilidad, "
        "estabilización, seguridad, adaptación y recuperación, y permitir sumar en el tiempo nuevos activos o sitios "
        "que requieran medidas de resiliencia."
        + context_sentence
    )
    return production, infrastructure, exposure


def _solution_profile(project: pd.Series) -> tuple[str, str]:
    """Devuelve los componentes técnicos y el propósito según la cartera 3.4."""
    family = _norm(project.get("familia_estrategica"))

    profiles = [
        (
            ("gestion ambiental", "lodos", "plantas potabilizadoras"),
            (
                "la construcción y puesta en operación de obras para recolectar y tratar las aguas residuales "
                "del proceso de potabilización, manejar y disponer adecuadamente los lodos generados y recuperar "
                "o recircular el agua técnicamente aprovechable",
                "reducir los impactos ambientales de la operación de las plantas, mejorar el aprovechamiento del "
                "agua y asegurar una gestión controlada de los residuos del proceso",
            ),
        ),
        (
            ("almacenamiento", "regulacion"),
            (
                "la construcción, ampliación o rehabilitación de tanques de almacenamiento, junto con sus obras "
                "de conexión, control, medición y seguridad operativa",
                "incrementar la reserva y la capacidad de regulación, mejorar la continuidad del servicio y brindar "
                "mayor flexibilidad ante variaciones de producción, demanda o contingencias",
            ),
        ),
        (
            ("estudios para seguridad hidrica", "hidrogeolog"),
            (
                "la ejecución coordinada de estudios hidrogeológicos, prospecciones, análisis de disponibilidad, "
                "evaluaciones de calidad y demás investigaciones requeridas para identificar nuevas fuentes",
                "reducir la incertidumbre técnica sobre el recurso disponible y sustentar la selección de alternativas "
                "para aumentar la seguridad hídrica de los sectores críticos",
            ),
        ),
        (
            ("fuentes y produccion",),
            (
                "el desarrollo, rehabilitación o ampliación de fuentes, captaciones y campos de pozos, incluyendo "
                "las obras hidráulicas, electromecánicas, eléctricas, de control y protección necesarias",
                "incorporar o recuperar capacidad de producción y disminuir la brecha entre la oferta disponible y "
                "la demanda de los sistemas beneficiados",
            ),
        ),
        (
            ("infraestructura troncal", "interconexion"),
            (
                "la construcción o mejora de aducciones, conducciones, interconexiones y trasvases, con sus accesorios, "
                "válvulas, estructuras de control y obras complementarias",
                "transportar y redistribuir el recurso con mayor confiabilidad, aprovechar excedentes disponibles y "
                "aumentar la redundancia entre fuentes, plantas, tanques y sistemas",
            ),
        ),
        (
            ("bombeo", "energia"),
            (
                "la rehabilitación, ampliación o sustitución de estaciones de bombeo y sus sistemas electromecánicos, "
                "eléctricos, de respaldo, automatización, protección y control",
                "mejorar la confiabilidad y eficiencia del bombeo, reducir el riesgo de interrupciones y asegurar la "
                "entrega de caudal y presión requeridos",
            ),
        ),
        (
            ("potabilizacion", "calidad", "gestion de residuos"),
            (
                "la ampliación y modernización de los procesos y unidades de tratamiento, incluyendo obras civiles, "
                "equipamiento, dosificación, desinfección, control de calidad, instrumentación, tratamiento de aguas "
                "residuales del proceso, manejo de lodos y recirculación de agua técnicamente aprovechable",
                "aumentar la capacidad y confiabilidad de la potabilización, asegurar el cumplimiento sostenido de "
                "los parámetros de calidad y mejorar la gestión ambiental y el aprovechamiento del agua dentro de las plantas",
            ),
        ),
        (
            ("redes y continuidad", "redes de distribucion", "optimizacion"),
            (
                "la ampliación, renovación, sustitución, mallado, sectorización y optimización hidráulica de redes de "
                "distribución, incluyendo tuberías primarias, secundarias y terciarias, válvulas, regulación y control "
                "de presión, interconexiones, distritos de medición y demás elementos requeridos para su operación",
                "incrementar la capacidad hidráulica y la flexibilidad de las redes, mejorar continuidad y presión, "
                "reducir fugas y Agua No Contabilizada, aumentar la redundancia y disminuir la vulnerabilidad operativa",
            ),
        ),
        (
            ("inteligencia operacional",),
            (
                "la adquisición, instalación e integración de macromedidores, sensores, telemetría, automatización, "
                "sistemas de supervisión y plataformas para el análisis operacional",
                "fortalecer el conocimiento en tiempo real de los sistemas, mejorar el control operativo y sustentar "
                "decisiones sobre producción, distribución, presiones y pérdidas de agua",
            ),
        ),
        (
            ("habilitacion legal", "predial"),
            (
                "el levantamiento, diagnóstico y regularización de propiedades, servidumbres y derechos de paso "
                "asociados con infraestructura existente o requerida",
                "brindar seguridad jurídica y disponibilidad predial a las obras, disminuir restricciones para su "
                "operación y facilitar la formulación y ejecución de futuras inversiones",
            ),
        ),
        (
            ("recoleccion de aguas residuales",),
            (
                "la construcción, ampliación o rehabilitación de redes sanitarias, colectores, interceptores, "
                "estaciones y obras complementarias de conducción",
                "ampliar la cobertura y confiabilidad de la recolección de aguas residuales y reducir los riesgos "
                "sanitarios y ambientales en las áreas beneficiadas",
            ),
        ),
        (
            ("tratamiento de aguas residuales",),
            (
                "la construcción, ampliación o rehabilitación de plantas y sistemas para el tratamiento y disposición "
                "de aguas residuales, incluyendo sus procesos, equipos y obras auxiliares",
                "mejorar el desempeño sanitario y ambiental, aumentar la capacidad de tratamiento y asegurar una "
                "disposición final conforme con la normativa aplicable",
            ),
        ),
        (
            ("resiliencia",),
            (
                "la rehabilitación, estabilización y protección de infraestructura estratégica expuesta a amenazas "
                "naturales, fallas estructurales o daños de terceros",
                "reducir la vulnerabilidad de los activos, preservar la continuidad del servicio y aumentar la "
                "capacidad de respuesta y recuperación ante eventos adversos",
            ),
        ),
    ]

    for terms, profile in profiles:
        if any(_norm(term) in family for term in terms):
            return profile

    return (
        "la formulación y ejecución coordinada de las obras, equipos, estudios y acciones complementarias "
        "identificadas para los sistemas asociados",
        "resolver de manera integral las restricciones técnicas registradas, fortalecer la prestación del servicio "
        "y disponer de infraestructura con mayor capacidad, confiabilidad y resiliencia",
    )


def _project_solution(project: pd.Series) -> str:
    """Redacta una solución integral GAM, usando las necesidades actuales como contexto y no como límite."""
    name = _clean(project.get("nombre_proyecto")) or "Proyecto de inversión para los sistemas de la GAM"
    action, purpose = _solution_profile(project)
    trace = _project_trace(_clean(project.get("proyecto_id")))
    context = _current_need_context(trace)
    current_count = len(_parse_ids(project.get("ids_asociados")))

    paragraphs = [
        (
            f"Se propone desarrollar el proyecto «{name}» como una cartera integral y programática para los 30 sistemas "
            f"de abastecimiento de la GAM, mediante {action}. La ejecución podrá organizarse por componentes, paquetes "
            "de obra, sistemas o etapas, de acuerdo con la prioridad técnica y presupuestaria de cada intervención."
        )
    ]
    if current_count:
        paragraphs.append(
            f"Las {current_count} necesidades agrupadas actualmente en la Vista 3.4 constituyen el contexto inicial "
            "para orientar la formulación"
            + (f"; entre los antecedentes se encuentran: {context}." if context else ".")
            + " Estas referencias sirven para identificar patrones y componentes recurrentes, pero no delimitan el "
            "alcance territorial ni temporal del proyecto."
        )
    paragraphs.append(
        f"El propósito del proyecto es {purpose}. Su diseño deberá permitir atender las brechas actuales y, al mismo "
        "tiempo, incorporar nuevas necesidades de igual naturaleza que surjan por crecimiento de la demanda, cambios "
        "en la producción, envejecimiento u obsolescencia de activos, reducción de pérdidas, optimización hidráulica, "
        "nuevos riesgos, variabilidad climática o prioridades institucionales durante el horizonte de inversión."
    )
    paragraphs.append(
        "La selección y secuencia de las intervenciones se realizará mediante criterios de criticidad, población "
        "beneficiada, seguridad del abastecimiento, impacto en continuidad y calidad, reducción de vulnerabilidad, "
        "eficiencia, costo y viabilidad técnica. El dimensionamiento, localización y presupuesto de cada componente "
        "se precisarán en las etapas de preinversión y diseño, manteniendo una única formulación integral con capacidad "
        "de crecimiento y actualización para toda la GAM."
    )
    return "\n\n".join(paragraphs)


def _defaults(project: pd.Series) -> dict[str, object]:
    project_id = _clean(project.get("proyecto_id"))
    trace = _project_trace(project_id)

    # Las fichas 3.5 son proyectos integrales GAM: la lista territorial y de
    # sistemas es fija y no se reduce a los registros actualmente asociados.
    codes = list(GAM_SYSTEM_CODES)
    population = _population(codes)
    affected = population * 0.20
    production_context, infrastructure_context, exposure_context = _general_service_observations(project, trace)

    return {
        "proyecto_id": project_id,
        "nombre_proyecto": _clean(project.get("nombre_proyecto")),
        "necesidad_descripcion": _general_need_description(project, trace),
        "provincia": GAM_PROVINCES_TEXT,
        "canton": GAM_CANTONS_TEXT,
        "distrito": GAM_DISTRICTS_TEXT,
        "comunidad": GAM_MAJOR_COMMUNITIES_TEXT,
        "sistemas": GAM_SYSTEMS_TEXT,
        "codigos_sistema": GAM_CODES_TEXT,
        "subgerencia": "Sistemas GAM",
        "direccion_uen": "UEN Optimización de Sistemas",
        "region_zona": "Gran Área Metropolitana y sistemas GAM - Zonas operativas 1, 2, 3, 4, 5 y 6",
        "cantonal": "Cobertura multicanonal GAM",
        "latitudes": "Múltiples ubicaciones; se definirán por componente durante la preinversión y el diseño",
        "longitudes": "Múltiples ubicaciones; se definirán por componente durante la preinversión y el diseño",
        "cuenta_sistema_agua": "SI",
        "disponibilidad_recurso": "SI",
        "poblacion_atendida": round(population),
        "poblacion_afectada": round(affected),
        "calidad_aceptada": "SI",
        "horas_servicio": 24.0,
        "anc_porcentaje": round(_weighted_anc(codes), 2),
        "deficiencia_produccion": "SI",
        "deficiencia_produccion_observacion": production_context,
        "infraestructura_condicion": "R",
        "infraestructura_observacion": infrastructure_context,
        "exposicion_danos": "SI",
        "exposicion_observacion": exposure_context,
        "calidad_riesgo_salud": "NO",
        "relacion_niveles_servicio": "SI",
        "sector_desarrollo_nacional": "SI",
        "canton_prioritario_irs": "NO",
        "vida_util": 0.0,
        "afectacion_eventos_naturales": "SI",
        "alto_grado_inseguridad": "SI",
        "mandato": "NO",
        "idea_solucion": _project_solution(project),
        "estudios_basicos": (
            "La iniciativa se formula como un proyecto integral para la GAM y se encuentra en etapa de identificación "
            "y preparación del perfil conforme al proceso de preinversión de MIDEPLAN. Los estudios, diseños, terrenos, "
            "servidumbres, permisos, diagnósticos, alternativas, costos y cronogramas se completarán de forma progresiva "
            "por componente. La formulación deberá mantener mecanismos para incorporar nuevas intervenciones compatibles "
            "que se identifiquen durante el horizonte del proyecto, sin perder la trazabilidad de cada actuación."
        ),
        "rango_costos": "Más de ¢5,000,000.00",
        "unidad_organizacional": "UEN OPTIMIZACIÓN DE SISTEMAS GAM",
        "encargado_unidad": "GERARDO RIVAS RIVAS",
        "patrocinador": "RANDALL CAMPOS ROJAS",
        "fecha": datetime.now(ZoneInfo("America/Costa_Rica")).strftime("%d/%m/%Y"),
        "_missing_population": "",
        "_missing_anc": "",
    }


def _signature(project: pd.Series) -> str:
    source = "|".join(
        [
            _clean(project.get("proyecto_id")),
            _clean(project.get("ids_asociados")),
            _clean(project.get("descripcion")),
            regroup.MODEL_VERSION,
            FICHA_MODEL_VERSION,
        ]
    )
    return hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]


def _select_index(options: list[str], value: object, default: int = 0) -> int:
    text = _clean(value)
    return options.index(text) if text in options else default


def _fields_for_export(data: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in data.items() if not key.startswith("_")}


def _xls_style(workbook: xlwt.Workbook, *, header: bool = False, section: bool = False) -> xlwt.XFStyle:
    style = xlwt.XFStyle()
    font = xlwt.Font()
    font.name = "Arial"
    font.height = 180
    font.bold = header or section
    font.colour_index = xlwt.Style.colour_map.get("white", 1) if section else 0
    style.font = font

    alignment = xlwt.Alignment()
    alignment.wrap = 1
    alignment.vert = xlwt.Alignment.VERT_CENTER
    alignment.horz = xlwt.Alignment.HORZ_CENTER if header else xlwt.Alignment.HORZ_LEFT
    style.alignment = alignment

    borders = xlwt.Borders()
    borders.left = borders.right = borders.top = borders.bottom = xlwt.Borders.THIN
    style.borders = borders

    if section:
        pattern = xlwt.Pattern()
        pattern.pattern = xlwt.Pattern.SOLID_PATTERN
        pattern.pattern_fore_colour = xlwt.Style.colour_map.get("dark_blue", 18)
        style.pattern = pattern
    elif header:
        pattern = xlwt.Pattern()
        pattern.pattern = xlwt.Pattern.SOLID_PATTERN
        pattern.pattern_fore_colour = xlwt.Style.colour_map.get("gray25", 22)
        style.pattern = pattern
    return style


def _fallback_xls(fields: dict[str, object]) -> bytes:
    workbook = xlwt.Workbook(encoding="utf-8")
    sheet = workbook.add_sheet("Ficha de necesidad")
    sheet.col(0).width = 15000
    sheet.col(1).width = 23000

    title_style = _xls_style(workbook, section=True)
    label_style = _xls_style(workbook, header=True)
    value_style = _xls_style(workbook)

    sheet.write_merge(0, 1, 0, 1, "FICHA DE NECESIDAD DE INVERSIÓN - ACUEDUCTO", title_style)
    row = 2
    sections = [
        ("IDENTIFICACIÓN Y LOCALIZACIÓN", [
            "nombre_proyecto", "necesidad_descripcion", "subgerencia", "direccion_uen", "region_zona",
            "cantonal", "provincia", "canton", "distrito", "comunidad", "sistemas", "codigos_sistema",
            "latitudes", "longitudes",
        ]),
        ("CONDICIONES DEL SERVICIO", [
            "cuenta_sistema_agua", "disponibilidad_recurso", "poblacion_atendida", "poblacion_afectada",
            "calidad_aceptada", "horas_servicio", "anc_porcentaje", "deficiencia_produccion",
            "deficiencia_produccion_observacion", "infraestructura_condicion", "infraestructura_observacion",
            "exposicion_danos", "exposicion_observacion", "calidad_riesgo_salud", "relacion_niveles_servicio",
            "sector_desarrollo_nacional", "canton_prioritario_irs", "vida_util",
            "afectacion_eventos_naturales", "alto_grado_inseguridad", "mandato",
        ]),
        ("ALTERNATIVA Y RESPONSABLES", [
            "idea_solucion", "estudios_basicos", "rango_costos", "unidad_organizacional",
            "encargado_unidad", "patrocinador", "fecha",
        ]),
    ]
    for section_name, keys in sections:
        sheet.write_merge(row, row, 0, 1, section_name, title_style)
        row += 1
        for key in keys:
            sheet.write(row, 0, FIELD_LABELS.get(key, key), label_style)
            sheet.write(row, 1, _clean(fields.get(key)), value_style)
            lines = max(1, len(_clean(fields.get(key))) // 95 + 1)
            sheet.row(row).height = min(1800, 300 * lines)
            row += 1

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def _merged_top_left(sheet: xlrd.sheet.Sheet, row: int, col: int) -> tuple[int, int]:
    for row_low, row_high, col_low, col_high in sheet.merged_cells:
        if row_low <= row < row_high and col_low <= col < col_high:
            return row_low, col_low
    return row, col


def _merged_end_col(sheet: xlrd.sheet.Sheet, row: int, col: int) -> int:
    for row_low, row_high, col_low, col_high in sheet.merged_cells:
        if row_low <= row < row_high and col_low <= col < col_high:
            return col_high
    return col + 1


def _target_cell(sheet: xlrd.sheet.Sheet, label_row: int, label_col: int) -> tuple[int, int]:
    start_col = _merged_end_col(sheet, label_row, label_col)
    max_col = max(sheet.ncols + 4, start_col + 1)

    for col in range(start_col, max_col):
        top_row, top_col = _merged_top_left(sheet, label_row, col)
        if (top_row, top_col) != (label_row, col):
            continue
        value = sheet.cell_value(label_row, col) if col < sheet.ncols else ""
        if not _clean(value):
            return label_row, col

    for row in range(label_row + 1, min(sheet.nrows, label_row + 4)):
        for col in range(label_col, max_col):
            top_row, top_col = _merged_top_left(sheet, row, col)
            if (top_row, top_col) != (row, col):
                continue
            value = sheet.cell_value(row, col) if col < sheet.ncols else ""
            if not _clean(value):
                return row, col
    return label_row, start_col


def _write_preserving_style(
    read_book: xlrd.book.Book,
    read_sheet: xlrd.sheet.Sheet,
    write_book: xlwt.Workbook,
    write_sheet: xlwt.Worksheet,
    row: int,
    col: int,
    value: object,
) -> None:
    source_row, source_col = _merged_top_left(read_sheet, row, col)
    style = None
    if source_row < read_sheet.nrows and source_col < read_sheet.ncols:
        try:
            xf_index = read_sheet.cell(source_row, source_col).xf_index
            style = write_book._Workbook__styles[xf_index]
        except Exception:
            style = None
    write_sheet._cell_overwrite_ok = True
    if style is None:
        write_sheet.write(row, col, value)
    else:
        write_sheet.write(row, col, value, style)


def _template_xls(template_bytes: bytes, fields: dict[str, object]) -> tuple[bytes, int]:
    read_book = xlrd.open_workbook(file_contents=template_bytes, formatting_info=True)
    write_book = copy_xls(read_book)
    mapped = 0

    normalized_markers = {
        key: tuple(_norm(marker) for marker in markers)
        for key, markers in TEMPLATE_MARKERS.items()
    }

    for sheet_index in range(read_book.nsheets):
        read_sheet = read_book.sheet_by_index(sheet_index)
        write_sheet = write_book.get_sheet(sheet_index)
        used_targets: set[tuple[int, int]] = set()

        for key, markers in normalized_markers.items():
            if key not in fields:
                continue
            found: tuple[int, int] | None = None
            for row in range(read_sheet.nrows):
                for col in range(read_sheet.ncols):
                    cell_text = _norm(read_sheet.cell_value(row, col))
                    if cell_text and any(marker in cell_text for marker in markers):
                        found = (row, col)
                        break
                if found:
                    break
            if not found:
                continue

            target = _target_cell(read_sheet, *found)
            if target in used_targets:
                continue
            used_targets.add(target)
            _write_preserving_style(
                read_book,
                read_sheet,
                write_book,
                write_sheet,
                target[0],
                target[1],
                fields[key],
            )
            mapped += 1

        # Algunas fichas ubican una celda de observación inmediatamente debajo
        # o a la derecha del criterio. Se completa únicamente cuando la etiqueta
        # "Observación" puede localizarse sin ambigüedad cerca de su pregunta.
        for observation_key, anchor_key in OBSERVATION_ANCHORS.items():
            anchor_markers = normalized_markers.get(anchor_key, ())
            anchor_position: tuple[int, int] | None = None
            for row in range(read_sheet.nrows):
                for col in range(read_sheet.ncols):
                    cell_text = _norm(read_sheet.cell_value(row, col))
                    if cell_text and any(marker in cell_text for marker in anchor_markers):
                        anchor_position = (row, col)
                        break
                if anchor_position:
                    break
            if not anchor_position:
                continue

            observation_label: tuple[int, int] | None = None
            start_row, start_col = anchor_position
            for row in range(start_row, min(read_sheet.nrows, start_row + 5)):
                for col in range(start_col, read_sheet.ncols):
                    if "observacion" in _norm(read_sheet.cell_value(row, col)):
                        observation_label = (row, col)
                        break
                if observation_label:
                    break
            if not observation_label:
                continue

            target = _target_cell(read_sheet, *observation_label)
            if target in used_targets:
                continue
            used_targets.add(target)
            _write_preserving_style(
                read_book,
                read_sheet,
                write_book,
                write_sheet,
                target[0],
                target[1],
                fields.get(observation_key, ""),
            )
            mapped += 1

    output = io.BytesIO()
    write_book.save(output)
    return output.getvalue(), mapped


def _pdf_from_fields(fields: dict[str, object]) -> bytes:
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title="Ficha de necesidad de inversión",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "FichaTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=colors.HexColor("#006A8E"),
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    label = ParagraphStyle(
        "FichaLabel",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9,
        alignment=TA_LEFT,
    )
    value = ParagraphStyle(
        "FichaValue",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        alignment=TA_LEFT,
    )
    section = ParagraphStyle(
        "FichaSection",
        parent=label,
        textColor=colors.white,
        alignment=TA_CENTER,
    )

    story = [
        Paragraph("FICHA DE NECESIDAD DE INVERSIÓN – ACUEDUCTO", title),
        Paragraph(_clean(fields.get("nombre_proyecto")), title),
        Spacer(1, 3 * mm),
    ]

    sections = [
        ("IDENTIFICACIÓN Y LOCALIZACIÓN", [
            "necesidad_descripcion", "subgerencia", "direccion_uen", "region_zona", "cantonal",
            "provincia", "canton", "distrito", "comunidad", "sistemas", "codigos_sistema",
            "latitudes", "longitudes",
        ]),
        ("CONDICIONES DEL SERVICIO", [
            "cuenta_sistema_agua", "disponibilidad_recurso", "poblacion_atendida", "poblacion_afectada",
            "calidad_aceptada", "horas_servicio", "anc_porcentaje", "deficiencia_produccion",
            "deficiencia_produccion_observacion", "infraestructura_condicion", "infraestructura_observacion",
            "exposicion_danos", "exposicion_observacion", "calidad_riesgo_salud", "relacion_niveles_servicio",
            "sector_desarrollo_nacional", "canton_prioritario_irs", "vida_util",
            "afectacion_eventos_naturales", "alto_grado_inseguridad", "mandato",
        ]),
        ("ALTERNATIVA Y RESPONSABLES", [
            "idea_solucion", "estudios_basicos", "rango_costos", "unidad_organizacional",
            "encargado_unidad", "patrocinador", "fecha",
        ]),
    ]

    for section_name, keys in sections:
        rows = [[Paragraph(section_name, section), ""]]
        for key in keys:
            rows.append(
                [
                    Paragraph(FIELD_LABELS.get(key, key), label),
                    Paragraph(_clean(fields.get(key)).replace("\n", "<br/>"), value),
                ]
            )
        table = Table(rows, colWidths=[92 * mm, 170 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("SPAN", (0, 0), (1, 0)),
                    ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#006A8E")),
                    ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#D9EAF2")),
                    ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#666666")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.extend([table, Spacer(1, 4 * mm)])
        if section_name != sections[-1][0]:
            story.append(PageBreak())

    document.build(story)
    return output.getvalue()


def _libreoffice_pdf(xls_bytes: bytes) -> bytes | None:
    executable = shutil.which("libreoffice") or shutil.which("soffice")
    if not executable:
        return None
    with tempfile.TemporaryDirectory(prefix="ficha35_") as temporary:
        source = Path(temporary) / "ficha.xls"
        source.write_bytes(xls_bytes)
        try:
            subprocess.run(
                [
                    executable,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    temporary,
                    str(source),
                ],
                check=True,
                timeout=45,
                capture_output=True,
            )
        except Exception:
            return None
        pdf_path = Path(temporary) / "ficha.pdf"
        return pdf_path.read_bytes() if pdf_path.exists() else None


def _safe_filename(value: object) -> str:
    text = _norm(value).replace(" ", "_")
    return re.sub(r"[^a-z0-9_]+", "", text)[:80] or "proyecto"


def _ensure_projects() -> tuple[pd.DataFrame, pd.DataFrame]:
    regroup._clear_stale_model()
    projects = st.session_state.get("mideplan_projects")
    trace = st.session_state.get("mideplan_trace")
    if isinstance(projects, pd.DataFrame) and not projects.empty:
        return projects, trace if isinstance(trace, pd.DataFrame) else pd.DataFrame()
    return pd.DataFrame(), pd.DataFrame()


def vista_fichas_planificacion() -> None:
    st.subheader("Vista 3.5 · Confección de Fichas para Priorización")
    st.caption(
        "Genera una ficha editable por cada proyecto de inversión de la Vista 3.4 para su presentación "
        "ante la Dirección de Planificación y el Comité Director."
    )
    st.info(
        "La Vista 3.5 utiliza la cartera temporal de la Vista 3.4. Los ajustes de la ficha se conservan "
        "durante la sesión y no modifican las necesidades originales ni escriben información en Supabase."
    )

    projects, _ = _ensure_projects()
    if projects.empty:
        st.warning("Aún no existe un resultado vigente de la Vista 3.4.")
        if st.button(
            "Generar cartera compacta y continuar",
            type="primary",
            use_container_width=True,
            key="ficha35_generate_projects",
        ):
            with st.spinner("Generando proyectos estratégicos desde el Banco de Ideas…"):
                projects, trace = regroup.build_groups()
                st.session_state["mideplan_projects"] = projects
                st.session_state["mideplan_trace"] = trace
            st.rerun()
        return

    project_options = {
        f"{row['proyecto_id']} · {row['nombre_proyecto']}": index
        for index, row in projects.iterrows()
    }
    selected_label = st.selectbox(
        "Proyecto de la Vista 3.4",
        list(project_options.keys()),
        key="ficha35_project_selection",
    )
    project = projects.loc[project_options[selected_label]]
    signature = _signature(project)
    data_key = f"ficha35_data_{signature}"
    prefix = f"ficha35_{signature}"

    if data_key not in st.session_state:
        st.session_state[data_key] = _defaults(project)
    data = dict(st.session_state[data_key])

    codes = _system_codes(data.get("codigos_sistema"))
    source_ids = _parse_ids(project.get("ids_asociados"))
    metric_columns = st.columns(4)
    metric_columns[0].metric("Proyecto", _clean(project.get("proyecto_id")))
    metric_columns[1].metric("Necesidades agrupadas", len(source_ids))
    metric_columns[2].metric("Sistemas únicos", len(codes))
    metric_columns[3].metric("Población calculada", f"{float(data.get('poblacion_atendida') or 0):,.0f}")

    if data.get("_missing_population"):
        st.warning(
            "Sin población parametrizada para: "
            + _clean(data.get("_missing_population"))
            + ". El valor puede completarse manualmente."
        )
    if data.get("_missing_anc"):
        st.warning(
            "Sin ANC parametrizada para: "
            + _clean(data.get("_missing_anc"))
            + ". El porcentaje puede completarse manualmente."
        )

    if st.button("Restablecer valores calculados", key=f"{prefix}_reset"):
        st.session_state.pop(data_key, None)
        for key in list(st.session_state.keys()):
            if str(key).startswith(prefix + "_"):
                st.session_state.pop(key, None)
        st.rerun()

    with st.form(f"{prefix}_form"):
        st.markdown("#### 1. Identificación y localización")
        name = st.text_area(
            "Nombre del proyecto",
            value=_clean(data.get("nombre_proyecto")),
            height=90,
            key=f"{prefix}_nombre_proyecto",
        )
        need_description = st.text_area(
            "Descripción de la necesidad u oportunidad",
            value=_clean(data.get("necesidad_descripcion")),
            height=150,
            key=f"{prefix}_necesidad_descripcion",
        )

        organization_columns = st.columns(3)
        submanagement = organization_columns[0].text_input(
            "Subgerencia",
            value=_clean(data.get("subgerencia")),
            key=f"{prefix}_subgerencia",
        )
        direction = organization_columns[1].text_input(
            "Dirección o UEN",
            value=_clean(data.get("direccion_uen")),
            key=f"{prefix}_direccion_uen",
        )
        zone = organization_columns[2].text_input(
            "Región o Zona",
            value=_clean(data.get("region_zona")),
            key=f"{prefix}_region_zona",
        )

        territorial_columns = st.columns(2)
        province = territorial_columns[0].text_area(
            "Provincia(s)",
            value=_clean(data.get("provincia")),
            key=f"{prefix}_provincia",
        )
        canton = territorial_columns[1].text_area(
            "Cantón(es)",
            value=_clean(data.get("canton")),
            key=f"{prefix}_canton",
        )
        district = territorial_columns[0].text_area(
            "Distrito(s)",
            value=_clean(data.get("distrito")),
            key=f"{prefix}_distrito",
        )
        community = territorial_columns[1].text_area(
            "Comunidad(es)",
            value=_clean(data.get("comunidad")),
            key=f"{prefix}_comunidad",
        )
        cantonal = territorial_columns[0].text_input(
            "Cantonal",
            value=_clean(data.get("cantonal")),
            key=f"{prefix}_cantonal",
            help="Para proyectos GAM se deja en blanco por defecto.",
        )
        systems = territorial_columns[1].text_area(
            "Sistemas asociados",
            value=_clean(data.get("sistemas")),
            key=f"{prefix}_sistemas",
        )
        system_codes = territorial_columns[0].text_area(
            "Códigos de sistema",
            value=_clean(data.get("codigos_sistema")),
            key=f"{prefix}_codigos_sistema",
        )
        latitudes = territorial_columns[0].text_area(
            "Latitudes de las necesidades agrupadas",
            value=_clean(data.get("latitudes")),
            key=f"{prefix}_latitudes",
        )
        longitudes = territorial_columns[1].text_area(
            "Longitudes de las necesidades agrupadas",
            value=_clean(data.get("longitudes")),
            key=f"{prefix}_longitudes",
        )

        st.markdown("#### 2. Condiciones del servicio")
        service_columns = st.columns(3)
        has_system = service_columns[0].selectbox(
            "Cuenta con sistema de agua potable",
            ["SI", "NO"],
            index=_select_index(["SI", "NO"], data.get("cuenta_sistema_agua")),
            key=f"{prefix}_cuenta_sistema_agua",
        )
        has_resource = service_columns[1].selectbox(
            "Disponibilidad del recurso hídrico",
            ["SI", "NO"],
            index=_select_index(["SI", "NO"], data.get("disponibilidad_recurso")),
            key=f"{prefix}_disponibilidad_recurso",
        )
        quality_ok = service_columns[2].selectbox(
            "Cumple niveles de calidad",
            ["SI", "NO"],
            index=_select_index(["SI", "NO"], data.get("calidad_aceptada")),
            key=f"{prefix}_calidad_aceptada",
        )

        population_served = service_columns[0].number_input(
            "Población atendida",
            min_value=0.0,
            value=float(data.get("poblacion_atendida") or 0),
            step=1.0,
            key=f"{prefix}_poblacion_atendida",
            help="Suma cada código de sistema una sola vez.",
        )
        population_affected = service_columns[1].number_input(
            "Población afectada",
            min_value=0.0,
            value=float(data.get("poblacion_afectada") or 0),
            step=1.0,
            key=f"{prefix}_poblacion_afectada",
            help="20 % de la población atendida por defecto.",
        )
        service_hours = service_columns[2].number_input(
            "Horas de servicio diario",
            min_value=0.0,
            max_value=24.0,
            value=float(data.get("horas_servicio") or 24),
            step=1.0,
            key=f"{prefix}_horas_servicio",
        )
        anc = service_columns[0].number_input(
            "Agua No Contabilizada (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(data.get("anc_porcentaje") or 0),
            step=0.1,
            key=f"{prefix}_anc_porcentaje",
            help="Promedio ponderado por la población de cada sistema asociado.",
        )

        diagnosis_columns = st.columns(3)
        production_deficit = diagnosis_columns[0].selectbox(
            "Deficiencia producción/demanda",
            ["SI", "NO"],
            index=_select_index(["SI", "NO"], data.get("deficiencia_produccion")),
            key=f"{prefix}_deficiencia_produccion",
        )
        infrastructure_condition = diagnosis_columns[1].selectbox(
            "Condición de infraestructura",
            ["R", "B", "M"],
            index=_select_index(["R", "B", "M"], data.get("infraestructura_condicion")),
            key=f"{prefix}_infraestructura_condicion",
            help="R: regular; B: buena; M: mala.",
        )
        exposure = diagnosis_columns[2].selectbox(
            "Exposición a daños",
            ["SI", "NO"],
            index=_select_index(["SI", "NO"], data.get("exposicion_danos")),
            key=f"{prefix}_exposicion_danos",
        )
        production_observation = st.text_area(
            "Observación sobre producción y demanda",
            value=_clean(data.get("deficiencia_produccion_observacion")),
            height=110,
            key=f"{prefix}_deficiencia_produccion_observacion",
        )
        infrastructure_observation = st.text_area(
            "Observación sobre infraestructura y equipos",
            value=_clean(data.get("infraestructura_observacion")),
            height=110,
            key=f"{prefix}_infraestructura_observacion",
        )
        exposure_observation = st.text_area(
            "Observación sobre exposición a daños",
            value=_clean(data.get("exposicion_observacion")),
            height=110,
            key=f"{prefix}_exposicion_observacion",
        )

        validation_columns = st.columns(3)
        health_risk = validation_columns[0].selectbox(
            "Calidad pone en riesgo la salud",
            ["SI", "NO"],
            index=_select_index(["SI", "NO"], data.get("calidad_riesgo_salud"), 1),
            key=f"{prefix}_calidad_riesgo_salud",
        )
        service_relation = validation_columns[1].selectbox(
            "Relación con niveles de servicio",
            ["SI", "NO"],
            index=_select_index(["SI", "NO"], data.get("relacion_niveles_servicio")),
            key=f"{prefix}_relacion_niveles_servicio",
        )
        national_development = validation_columns[2].selectbox(
            "Sector de desarrollo nacional",
            ["SI", "NO"],
            index=_select_index(["SI", "NO"], data.get("sector_desarrollo_nacional")),
            key=f"{prefix}_sector_desarrollo_nacional",
        )
        priority_canton = validation_columns[0].selectbox(
            "Cantón prioritario MIDEPLAN/IRS",
            ["SI", "NO"],
            index=_select_index(["SI", "NO"], data.get("canton_prioritario_irs"), 1),
            key=f"{prefix}_canton_prioritario_irs",
        )
        useful_life = validation_columns[1].number_input(
            "Cumplimiento vida útil (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(data.get("vida_util") or 0),
            step=1.0,
            key=f"{prefix}_vida_util",
        )
        natural_events = validation_columns[2].selectbox(
            "Afectación por eventos naturales",
            ["SI", "NO"],
            index=_select_index(["SI", "NO"], data.get("afectacion_eventos_naturales")),
            key=f"{prefix}_afectacion_eventos_naturales",
        )
        insecurity = validation_columns[0].selectbox(
            "Sectores con alto grado de inseguridad",
            ["SI", "NO"],
            index=_select_index(["SI", "NO"], data.get("alto_grado_inseguridad")),
            key=f"{prefix}_alto_grado_inseguridad",
        )
        mandate = validation_columns[1].selectbox(
            "Mandato judicial / orden sanitaria / otro",
            ["SI", "NO"],
            index=_select_index(["SI", "NO"], data.get("mandato"), 1),
            key=f"{prefix}_mandato",
        )

        st.markdown("#### 3. Alternativa de solución y responsables")
        solution = st.text_area(
            "Idea de proyecto que da solución a la necesidad",
            value=_clean(data.get("idea_solucion")),
            height=260,
            key=f"{prefix}_idea_solucion",
        )
        studies = st.text_area(
            "Recursos o estudios básicos disponibles",
            value=_clean(data.get("estudios_basicos")),
            height=150,
            key=f"{prefix}_estudios_basicos",
        )
        cost_range = st.selectbox(
            "Rango de costos",
            COST_OPTIONS,
            index=_select_index(COST_OPTIONS, data.get("rango_costos"), 2),
            key=f"{prefix}_rango_costos",
        )
        responsibility_columns = st.columns(3)
        organizational_unit = responsibility_columns[0].text_input(
            "Unidad organizacional",
            value=_clean(data.get("unidad_organizacional")),
            key=f"{prefix}_unidad_organizacional",
        )
        unit_manager = responsibility_columns[1].text_input(
            "Encargado de la unidad",
            value=_clean(data.get("encargado_unidad")),
            key=f"{prefix}_encargado_unidad",
        )
        sponsor = responsibility_columns[2].text_input(
            "Patrocinador",
            value=_clean(data.get("patrocinador")),
            key=f"{prefix}_patrocinador",
        )
        form_date = responsibility_columns[0].text_input(
            "Fecha",
            value=_clean(data.get("fecha")),
            key=f"{prefix}_fecha",
        )

        submitted = st.form_submit_button(
            "Guardar ajustes de la ficha",
            type="primary",
            use_container_width=True,
        )

    current = {
        **data,
        "nombre_proyecto": name,
        "necesidad_descripcion": need_description,
        "subgerencia": submanagement,
        "direccion_uen": direction,
        "region_zona": zone,
        "cantonal": cantonal,
        "provincia": province,
        "canton": canton,
        "distrito": district,
        "comunidad": community,
        "sistemas": systems,
        "codigos_sistema": system_codes,
        "latitudes": latitudes,
        "longitudes": longitudes,
        "cuenta_sistema_agua": has_system,
        "disponibilidad_recurso": has_resource,
        "poblacion_atendida": population_served,
        "poblacion_afectada": population_affected,
        "calidad_aceptada": quality_ok,
        "horas_servicio": service_hours,
        "anc_porcentaje": anc,
        "deficiencia_produccion": production_deficit,
        "deficiencia_produccion_observacion": production_observation,
        "infraestructura_condicion": infrastructure_condition,
        "infraestructura_observacion": infrastructure_observation,
        "exposicion_danos": exposure,
        "exposicion_observacion": exposure_observation,
        "calidad_riesgo_salud": health_risk,
        "relacion_niveles_servicio": service_relation,
        "sector_desarrollo_nacional": national_development,
        "canton_prioritario_irs": priority_canton,
        "vida_util": useful_life,
        "afectacion_eventos_naturales": natural_events,
        "alto_grado_inseguridad": insecurity,
        "mandato": mandate,
        "idea_solucion": solution,
        "estudios_basicos": studies,
        "rango_costos": cost_range,
        "unidad_organizacional": organizational_unit,
        "encargado_unidad": unit_manager,
        "patrocinador": sponsor,
        "fecha": form_date,
    }
    if submitted:
        st.session_state[data_key] = current
        st.success("Ajustes guardados durante la sesión. Ya puede exportar la ficha.")

    st.markdown("### Exportación")
    bundled_template = DEFAULT_TEMPLATE_PATH.read_bytes() if DEFAULT_TEMPLATE_PATH.exists() else None
    uploaded_template = st.file_uploader(
        "Plantilla institucional .xls",
        type=["xls"],
        key=f"{prefix}_template",
        help=(
            "La plantilla conserva sus hojas, combinaciones de celdas, tamaños, colores y tipografías. "
            "Si el archivo institucional se incorpora posteriormente al repositorio, se cargará automáticamente."
        ),
        disabled=bundled_template is not None,
    )
    template_bytes = bundled_template or (
        uploaded_template.getvalue() if uploaded_template is not None else None
    )

    export_fields = _fields_for_export(current)
    try:
        if template_bytes:
            xls_bytes, mapped_fields = _template_xls(template_bytes, export_fields)
            st.caption(
                f"Plantilla institucional aplicada: {mapped_fields} campos localizados y completados automáticamente."
            )
        else:
            xls_bytes = _fallback_xls(export_fields)
            st.warning(
                "No hay una plantilla institucional incorporada en el repositorio. Se generará una ficha estructurada "
                "de respaldo. Para conservar exactamente el formato oficial, cargue el archivo .xls original."
            )
    except Exception as exc:
        xls_bytes = _fallback_xls(export_fields)
        st.warning(
            "No fue posible completar automáticamente la plantilla aportada; se generó la ficha de respaldo. "
            f"Detalle: {exc}"
        )

    pdf_bytes = _libreoffice_pdf(xls_bytes)
    exact_pdf = pdf_bytes is not None
    if pdf_bytes is None:
        pdf_bytes = _pdf_from_fields(export_fields)

    safe_name = _safe_filename(current.get("nombre_proyecto"))
    download_columns = st.columns(2)
    download_columns[0].download_button(
        "Descargar ficha XLS",
        data=xls_bytes,
        file_name=f"Ficha_{safe_name}.xls",
        mime="application/vnd.ms-excel",
        use_container_width=True,
    )
    download_columns[1].download_button(
        "Descargar ficha PDF",
        data=pdf_bytes,
        file_name=f"Ficha_{safe_name}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
    if exact_pdf:
        st.caption("El PDF fue convertido directamente desde la ficha XLS completada.")
    else:
        st.caption(
            "El servidor no dispone de LibreOffice; el PDF se generó con el mismo contenido en formato institucional de respaldo."
        )
