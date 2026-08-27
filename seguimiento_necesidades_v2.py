from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

import pandas as pd
import streamlit as st

from database import read_optional_table, read_table, upsert_rows

TIPO_PROYECTO_DEFAULT = "Abastecimiento Agua Potable"
REGION_DEFAULT = "GAM"
FUENTE_FINANCIAMIENTO_DEFAULT = "Pendiente"
ESTADO_AYA_OPTIONS = ["En lista de espera", "Formulación de Iniciativa"]
SI_NO_OPTIONS = ["NO", "SI"]
MANDATO_OPTIONS = [
    "No",
    "Recurso de amparo",
    "Decreto de emergencia",
    "Orden Sanitaria",
    "Recurso de Amparo y Orden Sanitaria",
]

# Información suministrada para la Vista 3.3. Los valores representan la
# población/servicios atendidos por cada sistema y su condición hídrica vigente.
SYSTEM_DATA: dict[str, dict[str, Any]] = {
    "MEA01": {"nombre": "Tres Ríos", "servicios": 163056, "poblacion": 444713.1972, "factor": 3.042716135, "ich": "II", "bh": -302.5719962},
    "MEA02": {"nombre": "Guadalupe", "servicios": 23602, "poblacion": 64236.18108, "factor": 3.084422408, "ich": "III", "bh": 8.490302854},
    "MEA03": {"nombre": "El Llano", "servicios": 149, "poblacion": 446.9097825, "factor": 3.061025908, "ich": "III", "bh": 0.416962703},
    "MEA04": {"nombre": "Los Sitios", "servicios": 34577, "poblacion": 98833.05785, "factor": 3.073740681, "ich": "III", "bh": 7.470185226},
    "MEA05": {"nombre": "Salitral", "servicios": 1861, "poblacion": 5090.249248, "factor": 2.910376929, "ich": "II", "bh": -6.681834397},
    "MEA06": {"nombre": "San Juan de Dios", "servicios": 6344, "poblacion": 19553.20984, "factor": 3.218635365, "ich": "II", "bh": -8.101935989},
    "MEA07": {"nombre": "San Antonio de Escazú", "servicios": 2993, "poblacion": 8530.001025, "factor": 3.048606513, "ich": "II", "bh": -4.814970562},
    "MEA08": {"nombre": "Los Cuadros", "servicios": 10799, "poblacion": 31542.10649, "factor": 3.13883038, "ich": "II", "bh": -13.19049192},
    "MEA09": {"nombre": "Alajuelita", "servicios": 1074.84, "poblacion": 3287.057203, "factor": 3.375945858, "ich": "I", "bh": -10.60243749},
    "MEA10": {"nombre": "Mata de Plátano", "servicios": 992, "poblacion": 2945.734687, "factor": 3.091012263, "ich": "II", "bh": -1.728768989},
    "MEA11": {"nombre": "Guatuso de Patarrá", "servicios": 1357, "poblacion": 3825.044697, "factor": 3.236078424, "ich": "I", "bh": -3.329105497},
    "MEA12": {"nombre": "Quitirrisí", "servicios": 1411, "poblacion": 3826.171385, "factor": 2.909636034, "ich": "IV", "bh": 4.099275076},
    "MEA13": {"nombre": "San Jerónimo de Moravia", "servicios": 2109, "poblacion": 6298.93956, "factor": 3.087715471, "ich": "II", "bh": -1.794482642},
    "MEA14": {"nombre": "San Rafael de Coronado", "servicios": 2817, "poblacion": 8377.652393, "factor": 3.120168489, "ich": "II", "bh": -5.002415146},
    "MEA15": {"nombre": "San Pablo", "servicios": 12828, "poblacion": 36104.7575, "factor": 2.953112834, "ich": "IV", "bh": 19.88401362},
    "MEA16": {"nombre": "Potrerillos", "servicios": 18210, "poblacion": 52130.49615, "factor": 3.056431529, "ich": "II", "bh": -52.86987937},
    "MEA17": {"nombre": "La Valencia", "servicios": 69777, "poblacion": 193589.679, "factor": 3.088194985, "ich": "III", "bh": -58.24455794},
    "MEA18": {"nombre": "Lámparas", "servicios": 474, "poblacion": 17.30451273, "factor": 3.460902546, "ich": "I", "bh": -6.566900234},
    "MEA19": {"nombre": "Puente Mulas", "servicios": 56701, "poblacion": 167328.8169, "factor": 3.157484685, "ich": "II", "bh": -150.4328959},
    "MEA20": {"nombre": "Padre Carazo", "servicios": 1523, "poblacion": 4830.113466, "factor": 3.222223793, "ich": "III", "bh": 1.39431752},
    "MEA21": {"nombre": "Chiverrales", "servicios": 975, "poblacion": 2914.420711, "factor": 3.164409023, "ich": "II", "bh": -0.991089761},
    "MEA22": {"nombre": "Pizote", "servicios": 2451, "poblacion": 6962.928251, "factor": 2.917020633, "ich": "III", "bh": -1.431942152},
    "MEA24": {"nombre": "Matinilla", "servicios": 260, "poblacion": 234.0281399, "factor": 2.854001706, "ich": "I", "bh": -1.73357786},
    "MEA25": {"nombre": "Sur de Escazú", "servicios": 83, "poblacion": 32.22269928, "factor": 2.929336298, "ich": "I", "bh": -0.447181372},
    "MEA26": {"nombre": "Ticufres-Quebrada Honda", "servicios": 108, "poblacion": 320.5951802, "factor": 3.053287431, "ich": "I", "bh": -0.869421163},
    "MEA27": {"nombre": "El Guarco", "servicios": 9221, "poblacion": 26535.52067, "factor": 3.166907826, "ich": "II", "bh": -10.29494325},
    "MEA28": {"nombre": "Vista de Mar", "servicios": 606, "poblacion": 1892.897672, "factor": 3.246822765, "ich": "II", "bh": -1.707370223},
    "MEA29": {"nombre": "Lajas", "servicios": 383, "poblacion": 119.4465974, "factor": 2.913331644, "ich": "III", "bh": -0.234645895},
    "MEA30": {"nombre": "Jericó", "servicios": 402, "poblacion": 1115.327249, "factor": 3.319426336, "ich": "III", "bh": -0.276413623},
    "MEA31": {"nombre": "Puriscal", "servicios": 10103, "poblacion": 27055.30022, "factor": 2.922685559, "ich": "III", "bh": -3.890387264},
}
ICH_RANK = {"I": 1, "II": 2, "III": 3, "IV": 4}

TRACKING_FIELDS = [
    "codigo_interno",
    "unidad_solicitante",
    "unidad_formula_idea",
    "posible_fuente_financiamiento",
    "tipo_proyecto_banco",
    "memo_formulario_necesidad",
    "acuerdo_cdp",
    "region_aya",
    "comunidades",
    "estado_actual_aya",
    "mandato_asociado",
    "fecha_recurso_amparo",
    "propuesta_solucion",
    "orden_desacato",
    "compromiso_social",
    "estudios_terrenos",
    "proyecto_avance",
    "descripcion_avance",
    "priorizacion_region",
    "estado_sistema_ba",
]

DISPLAY_COLUMNS = [
    "codigo_interno",
    "unidad_solicitante",
    "unidad_formula_idea",
    "posible_fuente_financiamiento",
    "idea_proyecto",
    "descripcion_idea",
    "tipo_proyecto_banco",
    "memo_formulario_necesidad",
    "acuerdo_cdp",
    "region_aya",
    "ubicacion_provincia",
    "ubicacion_canton",
    "distritos",
    "comunidades",
    "poblacion_beneficiada",
    "estado_actual_aya",
    "codigo_nombre_sistema",
    "mandato_asociado",
    "fecha_recurso_amparo",
    "propuesta_solucion",
    "orden_desacato",
    "compromiso_social",
    "estudios_terrenos",
    "servicios_atendidos",
    "condicion_hidrica",
    "proyecto_avance",
    "descripcion_avance",
    "priorizacion_region",
    "estado_sistema_bh",
    "estado_sistema_ba",
]


def _ensure_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = pd.NA
    return out


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "<na>", "nat"} else text


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", _clean_text(value))
    text = text.encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"\s+", " ", text).strip()


def _normalize_code(value: object) -> str:
    raw = _clean_text(value).upper()
    match = re.search(r"\bME[-\s]?A[-\s]?0*(\d{1,2})\b|\bMEA0*(\d{1,2})\b", raw)
    if not match:
        return ""
    number = match.group(1) or match.group(2)
    return f"MEA{int(number):02d}"


def _extract_codes_from_text(value: object) -> list[str]:
    text = _clean_text(value).upper()
    codes: list[str] = []
    for match in re.finditer(r"\b(?:ME[-\s]?A[-\s]?|MEA)0*(\d{1,2})\b", text):
        code = f"MEA{int(match.group(1)):02d}"
        if code not in codes:
            codes.append(code)
    return codes


def _as_list(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_clean_text(item) for item in value if _clean_text(item)]
    text = _clean_text(value)
    if not text:
        return []
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    parts = re.split(r"\s*[;|]\s*|\s*,\s*(?=[A-ZÁÉÍÓÚÑ])", text)
    return [part.strip(" \"'") for part in parts if part.strip(" \"'")]


def _join_unique(values: Iterable[object]) -> str:
    out: list[str] = []
    for value in values:
        text = _clean_text(value)
        if text and text not in out:
            out.append(text)
    return ", ".join(out)


def _normalize_yes_no(value: object, default: str = "NO") -> str:
    text = _normalize_text(value)
    if text in {"si", "yes", "true", "1"}:
        return "SI"
    if text in {"no", "false", "0"}:
        return "NO"
    return default


def _system_relations(needs: pd.DataFrame, relations: pd.DataFrame) -> tuple[dict[int, list[str]], dict[int, list[str]]]:
    codes_by_need: dict[int, list[str]] = {}
    names_by_need: dict[int, list[str]] = {}

    if not relations.empty:
        rel = _ensure_columns(relations, ["necesidad_id", "sistema_codigo", "sistema_nombre"]).copy()
        rel["necesidad_id"] = pd.to_numeric(rel["necesidad_id"], errors="coerce")
        rel = rel[rel["necesidad_id"].notna()]
        for need_id, group in rel.groupby("necesidad_id"):
            nid = int(need_id)
            codes = []
            names = []
            for _, row in group.iterrows():
                code = _normalize_code(row.get("sistema_codigo"))
                name = _clean_text(row.get("sistema_nombre"))
                if code and code not in codes:
                    codes.append(code)
                if name and name not in names:
                    names.append(name)
            if codes:
                codes_by_need[nid] = codes
            if names:
                names_by_need[nid] = names

    for _, row in needs.iterrows():
        raw_id = pd.to_numeric(row.get("id"), errors="coerce")
        if pd.isna(raw_id):
            continue
        nid = int(raw_id)
        if nid not in codes_by_need:
            combined = " ".join([
                _clean_text(row.get("codigo_de_sistema")),
                _clean_text(row.get("sistema_de_abastecimiento")),
            ])
            codes = _extract_codes_from_text(combined)
            if not codes and "todos los sistemas aya" in _normalize_text(combined):
                codes = list(SYSTEM_DATA.keys())
            codes_by_need[nid] = codes
        if nid not in names_by_need:
            names_by_need[nid] = [
                SYSTEM_DATA[code]["nombre"]
                for code in codes_by_need.get(nid, [])
                if code in SYSTEM_DATA
            ]
    return codes_by_need, names_by_need


def _territory_by_need(needs: pd.DataFrame) -> dict[int, dict[str, list[str]]]:
    result: dict[int, dict[str, list[str]]] = {}
    territory = read_optional_table("v_necesidades_territorios")

    if not territory.empty and "necesidad_id" in territory.columns:
        territory = territory.copy()
        territory["necesidad_id"] = pd.to_numeric(territory["necesidad_id"], errors="coerce")
        for _, row in territory[territory["necesidad_id"].notna()].iterrows():
            nid = int(row["necesidad_id"])
            result[nid] = {
                "provincias": _as_list(row.get("provincias_asociadas")),
                "cantones": _as_list(row.get("cantones_asociados")),
                "distritos": _as_list(row.get("distritos_asociados")),
            }
        if result:
            return result

    # Contingencia: si la vista de Supabase todavía no está disponible, reutiliza
    # el geoproceso de la Vista 3.2 para no dejar la tabla sin ubicación.
    try:
        import territorio_necesidades as territory_base
        import territorio_necesidades_v2 as territory_v2

        crosswalk = territory_v2.territorial_crosswalk()
        enriched, _ = territory_base.associate_needs(needs, crosswalk)
        for _, row in enriched.iterrows():
            raw_id = pd.to_numeric(row.get("id"), errors="coerce")
            if pd.isna(raw_id):
                continue
            nid = int(raw_id)
            result[nid] = {
                "provincias": list(row.get("provincias_asociadas") or []),
                "cantones": list(row.get("cantones_asociados") or []),
                "distritos": list(row.get("distritos_asociados") or []),
            }
    except Exception:
        pass
    return result


def _communities_by_need(locations: pd.DataFrame, needs: pd.DataFrame) -> dict[int, str]:
    result: dict[int, list[str]] = {}
    if not locations.empty:
        loc = _ensure_columns(locations, ["necesidad_id", "tipo_ubicacion", "nombre_ubicacion"]).copy()
        loc["necesidad_id"] = pd.to_numeric(loc["necesidad_id"], errors="coerce")
        loc = loc[loc["necesidad_id"].notna()]
        for _, row in loc.iterrows():
            if _normalize_text(row.get("tipo_ubicacion")) == "no aplica":
                continue
            name = _clean_text(row.get("nombre_ubicacion"))
            if not name:
                continue
            nid = int(row["necesidad_id"])
            result.setdefault(nid, [])
            if name not in result[nid]:
                result[nid].append(name)

    for _, row in needs.iterrows():
        raw_id = pd.to_numeric(row.get("id"), errors="coerce")
        if pd.isna(raw_id):
            continue
        nid = int(raw_id)
        zone = _clean_text(row.get("zona"))
        if zone:
            result.setdefault(nid, [])
            if zone not in result[nid]:
                result[nid].insert(0, zone)

    return {nid: ", ".join(names) for nid, names in result.items()}


def _extract_internal_code(row: pd.Series) -> str:
    existing = _clean_text(row.get("codigo_interno"))
    if existing:
        return existing
    origin = _clean_text(row.get("id_origen"))
    if origin:
        return origin
    text = " ".join([
        _clean_text(row.get("detalle_accion")),
        _clean_text(row.get("observacion")),
    ])
    match = re.search(r"\b(GAM-[A-Z]-\d{1,3}|SD-GAM-[A-Z]-\d{1,3}|AB\s*\d{1,3})\b", text, flags=re.I)
    return match.group(1).upper().replace("  ", " ") if match else ""


def _extract_memo(row: pd.Series) -> str:
    existing = _clean_text(row.get("memo_formulario_necesidad"))
    if existing:
        return existing
    text = " ".join([
        _clean_text(row.get("detalle_accion")),
        _clean_text(row.get("observacion")),
    ])
    candidates = re.findall(r"\bUEN-[A-Z0-9-]*GAM-\d{4}-\d{5}\b", text.upper())
    return candidates[0] if candidates else ""


def _infer_formulation_unit(row: pd.Series) -> str:
    existing = _clean_text(row.get("unidad_formula_idea"))
    if existing:
        return existing
    text = _normalize_text(row.get("detalle_accion"))
    if "said como unidad responsable de formulacion" in text or "responsable: said" in text:
        return "SAID (PyC)"
    return ""


def _infer_cdp(row: pd.Series) -> str:
    existing = _clean_text(row.get("acuerdo_cdp"))
    if existing:
        return _normalize_yes_no(existing)
    text = _normalize_text(" ".join([
        _clean_text(row.get("detalle_accion")),
        _clean_text(row.get("observacion")),
        _clean_text(row.get("breve_descripcion")),
    ]))
    return "SI" if re.search(r"\bacuerdo\b.{0,80}\b(cdp|comite director)\b|\b(cdp|comite director)\b.{0,80}\bacuerdo\b", text) else "NO"


def _infer_mandate(row: pd.Series) -> str:
    existing = _clean_text(row.get("mandato_asociado"))
    if existing:
        return existing
    text = _normalize_text(" ".join([
        _clean_text(row.get("objetivo_de_la_iniciativa")),
        _clean_text(row.get("breve_descripcion")),
        _clean_text(row.get("observacion")),
        _clean_text(row.get("detalle_accion")),
    ]))
    has_amparo = "recurso de amparo" in text
    has_orden = "orden sanitaria" in text
    if has_amparo and ("no corresponde" in text or "no existe" in text):
        has_amparo = False
    if has_amparo and has_orden:
        return "Recurso de Amparo y Orden Sanitaria"
    if "decreto de emergencia" in text:
        return "Decreto de emergencia"
    if has_amparo:
        return "Recurso de amparo"
    if has_orden:
        return "Orden Sanitaria"
    return "No"


def _infer_solution(row: pd.Series) -> str:
    existing = _clean_text(row.get("propuesta_solucion"))
    if existing:
        return _normalize_yes_no(existing)
    text = _normalize_text(" ".join([
        _clean_text(row.get("objetivo_de_la_iniciativa")),
        _clean_text(row.get("breve_descripcion")),
    ]))
    solution_terms = (
        "constru", "perfor", "interconex", "impulsion", "conduccion", "captacion",
        "aduccion", "tanque", "pozo", "remodel", "rehabil", "sustit", "instal",
        "incorpor", "tratamiento", "moderniz", "ampli", "optim", "estabiliz", "diseno",
    )
    return "SI" if any(term in text for term in solution_terms) else "NO"


def _infer_social_commitment(row: pd.Series) -> str:
    existing = _clean_text(row.get("compromiso_social"))
    if existing:
        return _normalize_yes_no(existing)
    text = _normalize_text(" ".join([
        _clean_text(row.get("observacion")),
        _clean_text(row.get("detalle_accion")),
        _clean_text(row.get("principal_reto_por_superar")),
    ]))
    return "SI" if "compromiso social" in text or "compromiso con la comunidad" in text else "NO"


def _infer_studies_land(row: pd.Series) -> str:
    existing = _clean_text(row.get("estudios_terrenos"))
    if existing:
        return _normalize_yes_no(existing)
    text = _normalize_text(" ".join([
        _clean_text(row.get("breve_descripcion")),
        _clean_text(row.get("principal_reto_por_superar")),
        _clean_text(row.get("observacion")),
        _clean_text(row.get("detalle_accion")),
    ]))
    positive_patterns = (
        r"sitios? recomendados? por estudio",
        r"estudio.{0,50}(realizado|disponible|concluido|completado|recomienda|identifico)",
        r"(terreno|predio).{0,40}(adquirido|disponible|propiedad)",
        r"cuenta con.{0,40}(estudio|terreno|predio)",
    )
    return "SI" if any(re.search(pattern, text) for pattern in positive_patterns) else "NO"


def _infer_progress(row: pd.Series) -> str:
    existing = _clean_text(row.get("proyecto_avance"))
    if existing:
        return _normalize_yes_no(existing)
    state = _clean_text(row.get("estado_actual"))
    positive_states = {
        "En Ejecución",
        "Incorporada al BPIP o convertida en proyecto",
        "Iniciativa enviada a la Dirección de Planificación",
        "Iniciativa trasladada a SAID",
        "Trasladado a Presidencia",
        "Trasladado a Subgerencia GAM",
        "Necesidad Resuelta",
    }
    if state in positive_states:
        return "SI"
    text = _normalize_text(" ".join([
        _clean_text(row.get("observacion")),
        _clean_text(row.get("detalle_accion")),
    ]))
    if "no se identifico un oficio" in text and state == "Conceptualizado como una idea":
        return "NO"
    progress_terms = (
        "en ejecucion", "incorporado al bpip", "licitacion", "diseno en", "traslado formal",
        "remitido a planificacion", "remitida a planificacion", "ejecutado", "proyecto en ejecucion",
    )
    return "SI" if any(term in text for term in progress_terms) else "NO"


def _infer_aya_state(row: pd.Series) -> str:
    existing = _clean_text(row.get("estado_actual_aya"))
    if existing in ESTADO_AYA_OPTIONS:
        return existing
    old_state = _clean_text(row.get("estado_actual"))
    formulation_states = {
        "En Ejecución",
        "Incorporada al BPIP o convertida en proyecto",
        "Iniciativa enviada a la Dirección de Planificación",
        "Iniciativa trasladada a SAID",
        "Trasladado a Presidencia",
        "Trasladado a Subgerencia GAM",
        "Necesidad Resuelta",
    }
    return "Formulación de Iniciativa" if old_state in formulation_states else "En lista de espera"


def _critical_ich(codes: list[str]) -> str:
    values = [SYSTEM_DATA[c]["ich"] for c in codes if c in SYSTEM_DATA and SYSTEM_DATA[c].get("ich")]
    return min(values, key=lambda value: ICH_RANK.get(value, 99)) if values else ""


def _critical_bh(codes: list[str]) -> float | None:
    values = [float(SYSTEM_DATA[c]["bh"]) for c in codes if c in SYSTEM_DATA and SYSTEM_DATA[c].get("bh") is not None]
    return min(values) if values else None


def _system_label(codes: list[str], names: list[str]) -> str:
    labels: list[str] = []
    for code in codes:
        if code in SYSTEM_DATA:
            label = f"{code} - {SYSTEM_DATA[code]['nombre']}"
        else:
            label = code
        if label not in labels:
            labels.append(label)
    if not labels:
        labels = [name for name in names if name]
    return "; ".join(labels)


def _prepare_work() -> pd.DataFrame:
    needs = read_table("necesidades")
    if needs.empty:
        return pd.DataFrame()

    needs = _ensure_columns(needs, [
        "id", "id_origen", "objetivo_de_la_iniciativa", "breve_descripcion",
        "tipo_de_proyecto", "codigo_de_sistema", "sistema_de_abastecimiento",
        "zona", "principal_reto_por_superar", "observacion",
    ]).copy()
    needs["id"] = pd.to_numeric(needs["id"], errors="coerce")
    needs = needs[needs["id"].notna()].copy()
    needs["id"] = needs["id"].astype(int)

    relations = read_optional_table("necesidades_sistemas")
    locations = read_optional_table("necesidades_ubicaciones")
    following = read_optional_table("necesidades_seguimiento")
    following = _ensure_columns(following, ["necesidad_id", "estado_actual", "detalle_accion", *TRACKING_FIELDS])
    if not following.empty:
        following["necesidad_id"] = pd.to_numeric(following["necesidad_id"], errors="coerce")
        following = following[following["necesidad_id"].notna()].copy()
        following["necesidad_id"] = following["necesidad_id"].astype(int)
        following = following.drop_duplicates("necesidad_id", keep="last")
        needs = needs.merge(following, left_on="id", right_on="necesidad_id", how="left")
    else:
        for col in ["estado_actual", "detalle_accion", *TRACKING_FIELDS]:
            needs[col] = pd.NA

    codes_by_need, names_by_need = _system_relations(needs, relations)
    territory = _territory_by_need(needs)
    communities = _communities_by_need(locations, needs)

    rows: list[dict[str, Any]] = []
    for _, row in needs.iterrows():
        nid = int(row["id"])
        codes = codes_by_need.get(nid, [])
        names = names_by_need.get(nid, [])
        geo = territory.get(nid, {"provincias": [], "cantones": [], "distritos": []})

        services = sum(float(SYSTEM_DATA[c]["servicios"]) for c in codes if c in SYSTEM_DATA)
        population = sum(float(SYSTEM_DATA[c]["poblacion"]) for c in codes if c in SYSTEM_DATA)

        manual_communities = _clean_text(row.get("comunidades"))
        progress = _infer_progress(row)
        progress_description = _clean_text(row.get("descripcion_avance"))
        if not progress_description and progress == "SI":
            progress_description = _clean_text(row.get("detalle_accion")) or _clean_text(row.get("observacion"))

        ba_raw = pd.to_numeric(row.get("estado_sistema_ba"), errors="coerce")
        priority_raw = pd.to_numeric(row.get("priorizacion_region"), errors="coerce")
        date_raw = pd.to_datetime(row.get("fecha_recurso_amparo"), errors="coerce")

        display = {
            "necesidad_id": nid,
            "codigo_interno": _extract_internal_code(row),
            "unidad_solicitante": _clean_text(row.get("unidad_solicitante")) or "GAM",
            "unidad_formula_idea": _infer_formulation_unit(row),
            "posible_fuente_financiamiento": _clean_text(row.get("posible_fuente_financiamiento")) or FUENTE_FINANCIAMIENTO_DEFAULT,
            "idea_proyecto": _clean_text(row.get("objetivo_de_la_iniciativa")) or _clean_text(row.get("breve_descripcion")),
            "descripcion_idea": _clean_text(row.get("breve_descripcion")),
            "tipo_proyecto_banco": _clean_text(row.get("tipo_proyecto_banco")) or TIPO_PROYECTO_DEFAULT,
            "memo_formulario_necesidad": _extract_memo(row),
            "acuerdo_cdp": _infer_cdp(row),
            "region_aya": _clean_text(row.get("region_aya")) or REGION_DEFAULT,
            "ubicacion_provincia": _join_unique(geo.get("provincias", [])),
            "ubicacion_canton": _join_unique(geo.get("cantones", [])),
            "distritos": _join_unique(geo.get("distritos", [])),
            "comunidades": manual_communities or communities.get(nid, ""),
            "poblacion_beneficiada": round(population) if population > 0 else None,
            "estado_actual_aya": _infer_aya_state(row),
            "codigo_nombre_sistema": _system_label(codes, names),
            "mandato_asociado": _infer_mandate(row),
            "fecha_recurso_amparo": date_raw if pd.notna(date_raw) else pd.NaT,
            "propuesta_solucion": _infer_solution(row),
            "orden_desacato": _normalize_yes_no(row.get("orden_desacato"), "NO"),
            "compromiso_social": _infer_social_commitment(row),
            "estudios_terrenos": _infer_studies_land(row),
            "servicios_atendidos": round(services, 2) if services > 0 else None,
            "condicion_hidrica": _critical_ich(codes),
            "proyecto_avance": progress,
            "descripcion_avance": progress_description,
            "priorizacion_region": float(priority_raw) if pd.notna(priority_raw) else None,
            "estado_sistema_bh": _critical_bh(codes),
            "estado_sistema_ba": float(ba_raw) if pd.notna(ba_raw) else None,
        }
        rows.append(display)
    return pd.DataFrame(rows)


def _column_config() -> dict[str, Any]:
    return {
        "codigo_interno": st.column_config.TextColumn("Código interno", width="small"),
        "unidad_solicitante": st.column_config.TextColumn("Unidad solicitante", width="medium"),
        "unidad_formula_idea": st.column_config.TextColumn("Unidad que formula la idea", width="medium"),
        "posible_fuente_financiamiento": st.column_config.TextColumn("Posible fuente de financiamiento", width="medium"),
        "idea_proyecto": st.column_config.TextColumn("Idea de proyecto", width="large"),
        "descripcion_idea": st.column_config.TextColumn("Descripción de la idea", width="large"),
        "tipo_proyecto_banco": st.column_config.TextColumn("Tipo de proyecto", width="medium"),
        "memo_formulario_necesidad": st.column_config.TextColumn("Memo formulario de necesidad", width="medium"),
        "acuerdo_cdp": st.column_config.SelectboxColumn("Acuerdo de CDP", options=SI_NO_OPTIONS, width="small"),
        "region_aya": st.column_config.TextColumn("Región AyA", width="small"),
        "ubicacion_provincia": st.column_config.TextColumn("Ubicación (provincia)", width="medium"),
        "ubicacion_canton": st.column_config.TextColumn("Ubicación (cantón)", width="large"),
        "distritos": st.column_config.TextColumn("Distritos", width="large"),
        "comunidades": st.column_config.TextColumn("Comunidades", width="large"),
        "poblacion_beneficiada": st.column_config.NumberColumn("Población beneficiada", format="%.0f", width="medium"),
        "estado_actual_aya": st.column_config.SelectboxColumn("Estado Actual (AyA)", options=ESTADO_AYA_OPTIONS, width="medium"),
        "codigo_nombre_sistema": st.column_config.TextColumn("Código y Nombre del Sistema", width="large"),
        "mandato_asociado": st.column_config.SelectboxColumn("¿Existe Recurso de Amparo o Mandato asociado?", options=MANDATO_OPTIONS, width="large"),
        "fecha_recurso_amparo": st.column_config.DateColumn("Fecha de Recurso de Amparo", format="DD/MM/YYYY", width="medium"),
        "propuesta_solucion": st.column_config.SelectboxColumn("Se cuenta con propuesta de solución", options=SI_NO_OPTIONS, width="medium"),
        "orden_desacato": st.column_config.SelectboxColumn("Orden de desacato", options=SI_NO_OPTIONS, width="small"),
        "compromiso_social": st.column_config.SelectboxColumn("Compromiso social", options=SI_NO_OPTIONS, width="small"),
        "estudios_terrenos": st.column_config.SelectboxColumn("Estudios o terrenos", options=SI_NO_OPTIONS, width="small"),
        "servicios_atendidos": st.column_config.NumberColumn("Servicios Atendidos en el sistema", format="%.2f", width="medium"),
        "condicion_hidrica": st.column_config.TextColumn("Condición Hídrica del sistema (la más crítica en caso de varios sistemas)", width="large"),
        "proyecto_avance": st.column_config.SelectboxColumn("El proyecto cuenta con algún avance", options=SI_NO_OPTIONS, width="medium"),
        "descripcion_avance": st.column_config.TextColumn("Descripción del avance", width="large"),
        "priorizacion_region": st.column_config.NumberColumn("Priorización de región", min_value=0, step=1, format="%.0f", width="medium"),
        "estado_sistema_bh": st.column_config.NumberColumn("Estado Sistema BH", format="%.3f", width="medium"),
        "estado_sistema_ba": st.column_config.NumberColumn("Estado Sistema BA", format="%.3f", width="medium"),
    }


def _save_tracking(edited: pd.DataFrame) -> None:
    save = edited.reset_index().copy()
    save = save.rename(columns={"index": "necesidad_id"})
    if "necesidad_id" not in save.columns:
        raise ValueError("No se pudo recuperar el identificador de la necesidad.")

    keep = ["necesidad_id", *TRACKING_FIELDS]
    save = _ensure_columns(save, keep)[keep].copy()
    save["necesidad_id"] = pd.to_numeric(save["necesidad_id"], errors="raise").astype(int)

    for column in [
        "codigo_interno", "unidad_solicitante", "unidad_formula_idea",
        "posible_fuente_financiamiento", "tipo_proyecto_banco",
        "memo_formulario_necesidad", "region_aya", "comunidades",
        "descripcion_avance",
    ]:
        save[column] = save[column].apply(_clean_text)

    for column in [
        "acuerdo_cdp", "propuesta_solucion", "orden_desacato",
        "compromiso_social", "estudios_terrenos", "proyecto_avance",
    ]:
        save[column] = save[column].apply(_normalize_yes_no)

    save["estado_actual_aya"] = save["estado_actual_aya"].apply(
        lambda value: value if _clean_text(value) in ESTADO_AYA_OPTIONS else ESTADO_AYA_OPTIONS[0]
    )
    save["mandato_asociado"] = save["mandato_asociado"].apply(
        lambda value: value if _clean_text(value) in MANDATO_OPTIONS else "No"
    )

    dates = pd.to_datetime(save["fecha_recurso_amparo"], errors="coerce")
    save["fecha_recurso_amparo"] = dates.dt.strftime("%Y-%m-%d")
    save.loc[dates.isna(), "fecha_recurso_amparo"] = None

    save["priorizacion_region"] = pd.to_numeric(save["priorizacion_region"], errors="coerce")
    save["estado_sistema_ba"] = pd.to_numeric(save["estado_sistema_ba"], errors="coerce")

    upsert_rows("necesidades_seguimiento", save)


def vista_seguimiento_necesidades() -> None:
    st.subheader("Vista 3.3 · Banco de Ideas de Proyectos AyA")
    st.caption(
        "Formato EST-02-02-F4 · Seguimiento de necesidades GAM. "
        "Las columnas territoriales se alimentan del geoproceso de la Vista 3.2."
    )

    work = _prepare_work()
    if work.empty:
        st.warning("No hay necesidades disponibles para seguimiento.")
        return

    st.markdown("##### Filtros")
    f1, f2, f3, f4 = st.columns([1.2, 1.5, 2.1, 2.2])
    selected_states = f1.multiselect(
        "Estado Actual (AyA)", ESTADO_AYA_OPTIONS, key="banco_filter_state"
    )
    provinces = sorted({p.strip() for text in work["ubicacion_provincia"].fillna("") for p in text.split(",") if p.strip()})
    selected_provinces = f2.multiselect(
        "Provincia", provinces, key="banco_filter_province"
    )
    systems = sorted({
        label.strip()
        for text in work["codigo_nombre_sistema"].fillna("")
        for label in text.split(";")
        if label.strip()
    })
    selected_systems = f3.multiselect(
        "Sistema", systems, key="banco_filter_system"
    )
    keyword = f4.text_input(
        "Buscar", placeholder="Código, idea, memo, cantón, distrito…", key="banco_filter_text"
    )

    filtered = work.copy()
    if selected_states:
        filtered = filtered[filtered["estado_actual_aya"].isin(selected_states)]
    if selected_provinces:
        selected = {item.casefold() for item in selected_provinces}
        filtered = filtered[
            filtered["ubicacion_provincia"].fillna("").apply(
                lambda text: bool(selected & {p.strip().casefold() for p in text.split(",") if p.strip()})
            )
        ]
    if selected_systems:
        selected = set(selected_systems)
        filtered = filtered[
            filtered["codigo_nombre_sistema"].fillna("").apply(
                lambda text: bool(selected & {p.strip() for p in text.split(";") if p.strip()})
            )
        ]
    normalized_keyword = _normalize_text(keyword)
    if normalized_keyword:
        search_cols = [
            "codigo_interno", "idea_proyecto", "descripcion_idea",
            "memo_formulario_necesidad", "ubicacion_provincia", "ubicacion_canton",
            "distritos", "comunidades", "codigo_nombre_sistema", "descripcion_avance",
        ]
        searchable = filtered[search_cols].fillna("").astype(str).agg(" ".join, axis=1)
        filtered = filtered[
            searchable.apply(lambda value: normalized_keyword in _normalize_text(value))
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
    with_population = pd.to_numeric(filtered["poblacion_beneficiada"], errors="coerce").fillna(0).sum()
    m4.metric("Población asociada*", f"{with_population:,.0f}")

    st.caption(
        "* Población y servicios se estiman con la información del sistema o sistemas asociados. "
        "Para varios sistemas se suman población/servicios. La Condición Hídrica usa la categoría "
        "más crítica (I antes de II, III y IV) y Estado Sistema BH muestra el balance más bajo."
    )

    st.markdown("##### Banco de Ideas de Proyectos AyA")
    st.caption(
        "Los campos provenientes de la necesidad, del sistema y del geoproceso son de consulta. "
        "Los campos de seguimiento institucional pueden editarse y guardarse en Supabase."
    )

    editor = filtered[["necesidad_id", *DISPLAY_COLUMNS]].copy().set_index("necesidad_id")
    disabled = [
        "idea_proyecto",
        "descripcion_idea",
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
        key="editor_banco_ideas_aya",
    )

    if st.button(
        "Guardar cambios de seguimiento",
        type="primary",
        key="guardar_banco_ideas_aya",
    ):
        try:
            _save_tracking(edited)
        except Exception as exc:
            st.error(
                "No fue posible guardar el nuevo formato de seguimiento. "
                "Ejecute primero `sql/09_formato_banco_ideas_seguimiento.sql` en Supabase. "
                f"Detalle: {exc}"
            )
        else:
            st.success("Seguimiento del Banco de Ideas guardado correctamente.")
            st.rerun()
