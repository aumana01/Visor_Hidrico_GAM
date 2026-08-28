from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

import pandas as pd
import streamlit as st

import seguimiento_necesidades_v3 as seguimiento


# Vista 3.4: pre-agrupamiento estratégico inspirado en la Guía MIDEPLAN/AyA.
# El motor es interno, determinista, explicable y reproducible: no envía datos
# a servicios de IA externos. Su propósito es convertir un banco de necesidades
# en propuestas de proyectos integrales para revisión técnica posterior.

WATER_CHAIN = {
    "recurso": "Fuentes y producción",
    "captacion": "Captación",
    "conduccion": "Aducción, conducción e interconexiones",
    "bombeo": "Bombeo e impulsión",
    "potabilizacion": "Potabilización y calidad",
    "almacenamiento": "Almacenamiento y regulación",
    "distribucion": "Redes y distribución",
    "instrumentacion": "Medición, automatización y control",
    "resiliencia": "Rehabilitación, estabilización y resiliencia",
    "regularizacion": "Terrenos, servidumbres y regularización",
    "gestion": "Gestión y fortalecimiento institucional",
    "saneamiento_recoleccion": "Recolección y transporte de aguas residuales",
    "saneamiento_tratamiento": "Tratamiento y disposición de aguas residuales",
}

THEME_ORDER = [
    "recurso", "captacion", "conduccion", "bombeo", "potabilizacion",
    "almacenamiento", "distribucion", "instrumentacion", "resiliencia",
    "regularizacion", "saneamiento_recoleccion", "saneamiento_tratamiento", "gestion",
]

STOPWORDS = {
    "de", "del", "la", "las", "los", "el", "y", "en", "para", "por", "con", "un", "una",
    "al", "a", "se", "sistema", "sistemas", "proyecto", "mejorar", "mejoras", "gam", "aya",
    "acueducto", "agua", "potable", "necesidad", "sector", "mediante", "nuevo", "nueva",
}


def _clean(value: object) -> str:
    return seguimiento.base._clean_text(value)


def _norm(value: object) -> str:
    return seguimiento.base._normalize_text(value)


def _split(value: object, separators: str = r"[;,|]") -> list[str]:
    text = _clean(value)
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in re.split(separators, text):
        item = item.strip()
        key = _norm(item)
        if item and key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _join(values: Iterable[str], limit: int | None = None) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = _clean(raw)
        key = _norm(text)
        if text and key and key not in seen:
            seen.add(key)
            out.append(text)
    if limit is not None and len(out) > limit:
        return ", ".join(out[:limit]) + f" y {len(out) - limit} más"
    return ", ".join(out)


def _codes(value: object) -> set[str]:
    return {m.group(0).upper() for m in re.finditer(r"\bMEA\d{1,2}\b", _clean(value).replace("-", ""), flags=re.I)}


def _tokens(value: object) -> set[str]:
    text = _norm(value)
    return {t for t in re.findall(r"[a-z0-9áéíóúñ]+", text) if len(t) >= 3 and t not in STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _service_type(text: str) -> str:
    n = _norm(text)
    sanitation = (
        "alcantarill", "agua residual", "aguas residuales", "ptar", "colector", "interceptor",
        "red sanitaria", "saneamiento", "lodos", "digestor", "emisario",
    )
    return "Alcantarillado sanitario" if any(term in n for term in sanitation) else "Acueducto"


def _themes(text: str, category: str) -> set[str]:
    n = _norm(f"{category} {text}")
    found: set[str] = set()
    rules = {
        "saneamiento_recoleccion": ("colector", "interceptor", "red sanitaria", "alcantarillado", "recoleccion"),
        "saneamiento_tratamiento": ("ptar", "aguas residuales", "tratamiento", "lodos", "digestor", "disposicion"),
        "recurso": ("pozo", "fuente", "naciente", "produccion", "recurso hidrico", "aforo", "perfor"),
        "captacion": ("captacion", "desarenador", "presediment"),
        "conduccion": ("conduccion", "aduccion", "interconexion", "trasvase", "tuberia principal"),
        "bombeo": ("bombeo", "impulsion", "rebombeo", "booster", "bomba"),
        "potabilizacion": ("potabil", "filtr", "flocul", "sediment", "clor", "desinfeccion", "calidad"),
        "almacenamiento": ("tanque", "almacenamiento", "regulacion", "reserva"),
        "distribucion": ("red de distrib", "redes", "sectorizacion", "valvula", "vrp", "presion", "tuberia de una"),
        "instrumentacion": ("telemet", "scada", "sensor", "medidor", "caudalimet", "monitoreo", "automat"),
        "resiliencia": ("rehabil", "estabiliz", "mantenimiento", "repar", "sustit", "renov", "vulnerab", "proteccion"),
        "regularizacion": ("servidumbre", "terreno", "propiedad", "regulariz", "derecho de paso"),
        "gestion": ("fortalecer procesos", "administrativ", "plan de contingencia", "equipamiento tecnico", "gestion"),
    }
    for theme, terms in rules.items():
        if any(term in n for term in terms):
            found.add(theme)

    cat = _norm(category)
    if "aumento de recurso" in cat:
        found.add("recurso")
    if "almacenamiento" in cat:
        found.add("almacenamiento")
    if "trasvase" in cat:
        found.add("conduccion")
    if "sustitucion" in cat:
        found.update({"distribucion", "resiliencia"})
    if "potabilizacion" in cat:
        found.add("potabilizacion")
    if "regularizacion" in cat:
        found.add("regularizacion")
    if "mantenimiento" in cat:
        found.add("resiliencia")
    if "asadas" in cat:
        found.add("gestion")
    if not found:
        found.add("gestion")
    return found


def _macro_theme(theme_set: set[str], service: str) -> str:
    if service == "Alcantarillado sanitario":
        return "Saneamiento integral y tratamiento" if "saneamiento_tratamiento" in theme_set else "Recolección y saneamiento"
    if "potabilizacion" in theme_set:
        return "Calidad y potabilización"
    if "regularizacion" in theme_set and not (theme_set & {"recurso", "conduccion", "bombeo", "almacenamiento", "distribucion"}):
        return "Regularización y habilitación de infraestructura"
    if theme_set & {"instrumentacion", "gestion"} and not (theme_set & {"recurso", "conduccion", "bombeo", "almacenamiento", "distribucion"}):
        return "Gestión inteligente y resiliencia operativa"
    if theme_set & {"recurso", "captacion", "conduccion", "bombeo", "almacenamiento"}:
        return "Seguridad hídrica e infraestructura troncal"
    if theme_set & {"distribucion", "resiliencia"}:
        return "Continuidad, redes y resiliencia"
    return "Mejoramiento integral del acueducto"


@dataclass
class NeedFeature:
    idx: int
    need_id: int
    service: str
    systems: set[str]
    cantons: set[str]
    districts: set[str]
    communities: set[str]
    themes: set[str]
    macro: str
    tokens: set[str]
    title_norm: str


def _need_features(work: pd.DataFrame, raw_by_id: dict[int, pd.Series]) -> list[NeedFeature]:
    features: list[NeedFeature] = []
    for idx, row in work.reset_index(drop=True).iterrows():
        nid = int(pd.to_numeric(row.get("necesidad_id"), errors="coerce"))
        raw = raw_by_id.get(nid, pd.Series(dtype=object))
        text = " ".join(
            _clean(v)
            for v in [
                row.get("idea_proyecto"), row.get("descripcion_idea"), row.get("categoria_clasificacion"),
                raw.get("principal_reto_por_superar"), raw.get("observacion"), row.get("descripcion_avance"),
            ]
            if _clean(v)
        )
        service = _service_type(text)
        themes = _themes(text, _clean(row.get("categoria_clasificacion")))
        features.append(
            NeedFeature(
                idx=idx,
                need_id=nid,
                service=service,
                systems=_codes(row.get("codigo_nombre_sistema")),
                cantons={_norm(v) for v in _split(row.get("ubicacion_canton"))},
                districts={_norm(v) for v in _split(row.get("distritos"))},
                communities={_norm(v) for v in _split(row.get("comunidades"))},
                themes=themes,
                macro=_macro_theme(themes, service),
                tokens=_tokens(text),
                title_norm=_norm(row.get("idea_proyecto")),
            )
        )
    return features


def _pair_score(a: NeedFeature, b: NeedFeature) -> float:
    if a.service != b.service:
        return -100.0
    if a.title_norm and b.title_norm and a.title_norm == b.title_norm:
        return 20.0

    score = 0.0
    sys_overlap = a.systems & b.systems
    if sys_overlap:
        score += 5.0
    elif a.systems and b.systems:
        score -= 0.5

    if a.macro == b.macro:
        score += 3.0
    elif a.service == "Acueducto" and a.themes & {"recurso", "conduccion", "bombeo", "almacenamiento"} and b.themes & {"recurso", "conduccion", "bombeo", "almacenamiento"}:
        score += 1.5

    if a.districts & b.districts:
        score += 1.5
    elif a.cantons & b.cantons:
        score += 0.8
    if a.communities & b.communities:
        score += 2.0

    score += min(3.0, _jaccard(a.tokens, b.tokens) * 8.0)
    if not sys_overlap and a.systems and b.systems and score < 8.0:
        return score - 2.0
    return score


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def _group_indices(features: list[NeedFeature]) -> list[list[int]]:
    uf = _UnionFind(len(features))
    for i in range(len(features)):
        for j in range(i + 1, len(features)):
            if _pair_score(features[i], features[j]) >= 7.0:
                uf.union(i, j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(features)):
        groups[uf.find(i)].append(i)
    return list(groups.values())


def _process_name(group: pd.DataFrame, themes: set[str], service: str) -> str:
    text = _norm(" ".join(group["idea_proyecto"].fillna("").astype(str).tolist()))
    if any(term in text for term in ("rehabil", "sustit", "renov", "repar", "estabiliz")):
        return "Rehabilitación"
    if any(term in text for term in ("ampli", "increment", "incorpor", "nuevo pozo", "nueva conduccion")):
        return "Ampliación"
    if "remodel" in text:
        return "Remodelación"
    if service == "Alcantarillado sanitario" and "constru" in text:
        return "Construcción"
    return "Mejoras"


def _system_names(group: pd.DataFrame) -> tuple[list[str], set[str]]:
    labels: list[str] = []
    codes: set[str] = set()
    for value in group["codigo_nombre_sistema"].fillna(""):
        for label in _split(value, r"[;]"):
            labels.append(label)
            codes |= _codes(label)
    return list(dict.fromkeys(labels)), codes


def _unique_dimension(group: pd.DataFrame, raw_by_id: dict[int, pd.Series], field: str) -> float:
    by_title: dict[str, float] = {}
    for _, row in group.iterrows():
        nid = int(row["necesidad_id"])
        raw = raw_by_id.get(nid, pd.Series(dtype=object))
        value = pd.to_numeric(raw.get(field), errors="coerce")
        if pd.isna(value) or float(value) <= 0:
            continue
        signature = _norm(row.get("idea_proyecto")) or f"id-{nid}"
        by_title[signature] = max(float(value), by_title.get(signature, 0.0))
    return sum(by_title.values())


def _beneficiaries(codes: set[str]) -> tuple[float, float]:
    population = 0.0
    services = 0.0
    data = seguimiento.base.SYSTEM_DATA
    for code in codes:
        if code in data:
            population += float(data[code].get("poblacion") or 0)
            services += float(data[code].get("servicios") or 0)
    return population, services


def _critical_ich(group: pd.DataFrame) -> str:
    rank = {"I": 1, "II": 2, "III": 3, "IV": 4}
    values = [_clean(v) for v in group["condicion_hidrica"] if _clean(v) in rank]
    return min(values, key=lambda v: rank[v]) if values else ""


def _minimum_bh(group: pd.DataFrame) -> float | None:
    values = pd.to_numeric(group["estado_sistema_bh"], errors="coerce").dropna()
    return float(values.min()) if not values.empty else None


def _potential_score(group: pd.DataFrame, codes: set[str], themes: set[str], dims: dict[str, float]) -> tuple[int, str]:
    population, _ = _beneficiaries(codes)
    bh = _minimum_bh(group)
    ich = _critical_ich(group)
    score = 0.0
    if bh is not None and bh < 0:
        score += min(30.0, abs(bh) / 5.0)
    elif bh is not None:
        score += 4.0

    if population >= 200_000:
        score += 20
    elif population >= 100_000:
        score += 17
    elif population >= 50_000:
        score += 14
    elif population >= 10_000:
        score += 10
    elif population > 0:
        score += 6

    score += min(15.0, len(group) * 2.0 + max(0, len(themes) - 1) * 1.5)
    score += {"I": 10, "II": 8, "III": 5, "IV": 2}.get(ich, 0)
    if any(_clean(v) != "No" for v in group["mandato_asociado"]):
        score += 8
    if any(_clean(v) == "SI" for v in group["proyecto_avance"]):
        score += 7
    if any(v > 0 for v in dims.values()):
        score += 5
    score = int(round(min(100.0, score)))
    label = "Muy alto" if score >= 80 else "Alto" if score >= 65 else "Medio" if score >= 45 else "Bajo"
    return score, label


def _maturity(group: pd.DataFrame) -> str:
    has_advance = any(_clean(v) == "SI" for v in group["proyecto_avance"])
    has_studies = any(_clean(v) == "SI" for v in group["estudios_terrenos"])
    has_solution = any(_clean(v) == "SI" for v in group["propuesta_solucion"])
    has_memo = any(bool(_clean(v)) for v in group["memo_formulario_necesidad"])
    if has_advance and has_studies and has_solution:
        return "Perfil preliminar con antecedentes"
    if has_advance or has_memo:
        return "Identificación avanzada / formulación"
    if has_solution:
        return "Identificación con alternativa conceptual"
    return "Identificación / idea"


def _group_name(group: pd.DataFrame, service: str, themes: set[str]) -> str:
    process = _process_name(group, themes, service)
    labels, _ = _system_names(group)
    cantons = _join(v for value in group["ubicacion_canton"] for v in _split(value))
    provinces = _join(v for value in group["ubicacion_provincia"] for v in _split(value))
    system_short = _join([re.sub(r"^MEA\d+\s*-\s*", "", x, flags=re.I) for x in labels], limit=3)
    location = cantons or provinces or "GAM"
    if process == "Mejoras":
        if service == "Alcantarillado sanitario":
            return f"Mejoras integrales del sistema de alcantarillado sanitario de {location}, AyA"
        object_name = f"los sistemas de acueducto {system_short}" if "," in system_short or " y " in system_short else f"el sistema de acueducto {system_short or location}"
        return f"Mejoras integrales de {object_name}, AyA, {location}"
    if service == "Alcantarillado sanitario":
        return f"{process} integral del sistema de alcantarillado sanitario de {location}, AyA"
    object_name = f"los sistemas de acueducto {system_short}" if "," in system_short or " y " in system_short else f"el sistema de acueducto {system_short or location}"
    return f"{process} integral de {object_name}, AyA, {location}"


def _problem_statement(group: pd.DataFrame, themes: set[str]) -> str:
    bh = _minimum_bh(group)
    ich = _critical_ich(group)
    issues: list[str] = []
    if bh is not None and bh < 0:
        issues.append(f"déficit hídrico de referencia de hasta {abs(bh):.1f} L/s")
    if ich:
        issues.append(f"condición hídrica crítica {ich}")
    if "resiliencia" in themes:
        issues.append("vulnerabilidad o deterioro de infraestructura existente")
    if "potabilizacion" in themes:
        issues.append("limitaciones de calidad o capacidad de potabilización")
    if "almacenamiento" in themes:
        issues.append("limitaciones de regulación y almacenamiento")
    if "distribucion" in themes:
        issues.append("restricciones en redes, presiones o continuidad")
    if not issues:
        issues.append("necesidades operativas y de capacidad identificadas en el área de influencia")
    return "; ".join(dict.fromkeys(issues))


def _scope(themes: set[str], dims: dict[str, float]) -> str:
    ordered = [WATER_CHAIN[t] for t in THEME_ORDER if t in themes]
    text = _join(ordered)
    quantified: list[str] = []
    if dims["caudal_lps"] > 0:
        quantified.append(f"aporte/recurso preliminar ≈ {dims['caudal_lps']:.1f} L/s")
    if dims["volumen_m3"] > 0:
        quantified.append(f"almacenamiento ≈ {dims['volumen_m3']:,.0f} m³")
    if dims["km"] > 0:
        quantified.append(f"red/conducción ≈ {dims['km']:.2f} km")
    return text + (". Dimensiones registradas: " + "; ".join(quantified) if quantified else ".")


def _general_objective(service: str, themes: set[str], population: float, location: str) -> str:
    if service == "Alcantarillado sanitario":
        return (
            f"Mejorar la capacidad, continuidad y desempeño sanitario de la recolección y tratamiento de aguas residuales "
            f"en {location}, beneficiando de forma directa o indirecta a la población del área de influencia."
        )
    outcomes: list[str] = []
    if themes & {"recurso", "captacion", "conduccion", "bombeo"}:
        outcomes.append("aumentar la seguridad hídrica y la capacidad de abastecimiento")
    if "potabilizacion" in themes:
        outcomes.append("mejorar la calidad y confiabilidad del tratamiento")
    if "almacenamiento" in themes:
        outcomes.append("incrementar la regulación y reserva operativa")
    if themes & {"distribucion", "resiliencia"}:
        outcomes.append("mejorar la continuidad y resiliencia de la infraestructura")
    if "instrumentacion" in themes:
        outcomes.append("fortalecer el control y monitoreo operacional")
    if not outcomes:
        outcomes.append("mejorar la prestación del servicio de agua potable")
    beneficiary = f" para una población de referencia de aproximadamente {population:,.0f} habitantes" if population > 0 else ""
    return f"{'; '.join(outcomes).capitalize()} en {location}{beneficiary}."


def _specific_objectives(themes: set[str], dims: dict[str, float]) -> str:
    objectives: list[str] = []
    if "recurso" in themes:
        suffix = f" en aproximadamente {dims['caudal_lps']:.1f} L/s" if dims["caudal_lps"] > 0 else ""
        objectives.append(f"Incrementar o asegurar la disponibilidad de recurso hídrico{suffix}")
    if themes & {"conduccion", "bombeo"}:
        objectives.append("Aumentar la capacidad de transporte e interconexión hidráulica entre fuentes, tanques y sectores")
    if "almacenamiento" in themes:
        suffix = f" mediante aproximadamente {dims['volumen_m3']:,.0f} m³ registrados" if dims["volumen_m3"] > 0 else ""
        objectives.append(f"Incrementar la regulación y reserva del sistema{suffix}")
    if "potabilizacion" in themes:
        objectives.append("Mejorar la capacidad y confiabilidad de los procesos de potabilización y control de calidad")
    if "distribucion" in themes:
        suffix = f" considerando aproximadamente {dims['km']:.2f} km registrados" if dims["km"] > 0 else ""
        objectives.append(f"Mejorar redes, presiones, sectorización y continuidad del servicio{suffix}")
    if "resiliencia" in themes:
        objectives.append("Reducir vulnerabilidades y rehabilitar componentes críticos de la infraestructura")
    if "regularizacion" in themes:
        objectives.append("Regularizar terrenos, servidumbres y derechos requeridos para ejecución y operación")
    if "instrumentacion" in themes:
        objectives.append("Incorporar medición, telemetría y control para apoyar la gestión operativa")
    if themes & {"saneamiento_recoleccion", "saneamiento_tratamiento"}:
        objectives.append("Mejorar la recolección, tratamiento y disposición de las aguas residuales conforme al alcance definido")
    return "; ".join(dict.fromkeys(objectives))


def _missing_information(group: pd.DataFrame, themes: set[str], dims: dict[str, float]) -> str:
    missing: list[str] = []
    if not any(_clean(v) == "SI" for v in group["estudios_terrenos"]):
        missing.append("confirmar estudios básicos, terrenos y servidumbres")
    if not any(v > 0 for v in dims.values()):
        missing.append("dimensionar hidráulicamente las obras y cuantificar metas")
    if not any(_clean(v) for v in group["posible_fuente_financiamiento"] if _clean(v).lower() != "pendiente"):
        missing.append("definir fuente de financiamiento")
    missing.extend(["validar alternativas técnicas", "preparar estimación de costos y cronograma"])
    return "; ".join(dict.fromkeys(missing))


def build_groups() -> tuple[pd.DataFrame, pd.DataFrame]:
    work = seguimiento._prepare_work()
    if work.empty:
        return pd.DataFrame(), pd.DataFrame()

    raw = seguimiento.base.read_table("necesidades")
    raw_by_id: dict[int, pd.Series] = {}
    if not raw.empty and "id" in raw.columns:
        for _, row in raw.iterrows():
            nid = pd.to_numeric(row.get("id"), errors="coerce")
            if pd.notna(nid):
                raw_by_id[int(nid)] = row

    work = work.copy().reset_index(drop=True)
    for field in ("caudal_estimado_lps", "volumen_estimado_m3", "km_estimado", "principal_reto_por_superar", "observacion"):
        work[field] = [raw_by_id.get(int(nid), pd.Series(dtype=object)).get(field) for nid in work["necesidad_id"]]

    features = _need_features(work, raw_by_id)
    grouped_positions = _group_indices(features)
    rows: list[dict[str, object]] = []
    trace_parts: list[pd.DataFrame] = []

    for serial, positions in enumerate(grouped_positions, start=1):
        group = work.iloc[positions].copy()
        feature_group = [features[p] for p in positions]
        service = feature_group[0].service
        themes = set().union(*(f.themes for f in feature_group))
        macro = _macro_theme(themes, service)
        labels, codes = _system_names(group)
        population, services = _beneficiaries(codes)
        dims = {
            "caudal_lps": _unique_dimension(group, raw_by_id, "caudal_estimado_lps"),
            "volumen_m3": _unique_dimension(group, raw_by_id, "volumen_estimado_m3"),
            "km": _unique_dimension(group, raw_by_id, "km_estimado"),
        }
        provinces = _join(v for value in group["ubicacion_provincia"] for v in _split(value))
        cantons = _join(v for value in group["ubicacion_canton"] for v in _split(value))
        districts = _join(v for value in group["distritos"] for v in _split(value))
        communities = _join((v for value in group["comunidades"] for v in _split(value)), limit=10)
        location = cantons or provinces or "la GAM"
        project_name = _group_name(group, service, themes)
        score, potential = _potential_score(group, codes, themes, dims)
        ids = sorted(pd.to_numeric(group["necesidad_id"], errors="coerce").dropna().astype(int).unique().tolist())
        internal_codes = _join(group["codigo_interno"].fillna("").astype(str).tolist())
        bh = _minimum_bh(group)
        ich = _critical_ich(group)

        rows.append({
            "proyecto_id": f"PE-{serial:03d}",
            "nombre_proyecto": project_name,
            "tipologia_mideplan": _process_name(group, themes, service),
            "servicio": service,
            "familia_estrategica": macro,
            "ids_asociados": ", ".join(map(str, ids)),
            "codigos_internos": internal_codes,
            "cantidad_necesidades": len(ids),
            "sistemas_beneficiados": _join(labels),
            "provincias": provinces,
            "cantones": cantons,
            "distritos": districts,
            "comunidades": communities,
            "problema_necesidad": _problem_statement(group, themes),
            "descripcion": (
                f"Propuesta integral que consolida {len(ids)} necesidades del Banco de Ideas asociadas a {(_join(labels, limit=4) or location)}. "
                f"El proyecto articula {(_join(WATER_CHAIN[t] for t in THEME_ORDER if t in themes))}. "
                f"La agrupación busca tratar las necesidades como componentes complementarios de una misma intervención, sujeto a validación técnica de alternativas."
            ),
            "alcance_componentes": _scope(themes, dims),
            "objetivo_general": _general_objective(service, themes, population, location),
            "objetivos_especificos": _specific_objectives(themes, dims),
            "poblacion_referencia": round(population) if population else None,
            "servicios_referencia": round(services, 2) if services else None,
            "caudal_lps": round(dims["caudal_lps"], 2) if dims["caudal_lps"] else None,
            "volumen_m3": round(dims["volumen_m3"], 2) if dims["volumen_m3"] else None,
            "km_red": round(dims["km"], 3) if dims["km"] else None,
            "condicion_hidrica_critica": ich,
            "estado_bh_critico": round(bh, 3) if bh is not None else None,
            "potencial_puntos": score,
            "potencial": potential,
            "nivel_preinversion_sugerido": _maturity(group),
            "informacion_faltante": _missing_information(group, themes, dims),
        })

        trace = group.copy()
        trace.insert(0, "proyecto_estrategico", f"PE-{serial:03d}")
        trace.insert(1, "nombre_proyecto_estrategico", project_name)
        trace_parts.append(trace)

    projects = pd.DataFrame(rows)
    if projects.empty:
        return projects, pd.DataFrame()

    projects = projects.sort_values(
        ["potencial_puntos", "cantidad_necesidades", "estado_bh_critico"],
        ascending=[False, False, True],
        na_position="last",
    ).reset_index(drop=True)
    projects["orden_estrategico"] = range(1, len(projects) + 1)

    remap = {old: f"PE-{i:03d}" for i, old in enumerate(projects["proyecto_id"], start=1)}
    projects["proyecto_id"] = projects["proyecto_id"].map(remap)
    traceability = pd.concat(trace_parts, ignore_index=True) if trace_parts else pd.DataFrame()
    if not traceability.empty:
        traceability["proyecto_estrategico"] = traceability["proyecto_estrategico"].map(remap)
        name_map = dict(zip(projects["proyecto_id"], projects["nombre_proyecto"]))
        traceability["nombre_proyecto_estrategico"] = traceability["proyecto_estrategico"].map(name_map)

    front = [
        "orden_estrategico", "proyecto_id", "nombre_proyecto", "tipologia_mideplan", "familia_estrategica",
        "ids_asociados", "cantidad_necesidades", "sistemas_beneficiados", "provincias", "cantones", "distritos",
        "comunidades", "problema_necesidad", "descripcion", "alcance_componentes", "objetivo_general",
        "objetivos_especificos", "poblacion_referencia", "servicios_referencia", "caudal_lps", "volumen_m3",
        "km_red", "condicion_hidrica_critica", "estado_bh_critico", "potencial", "potencial_puntos",
        "nivel_preinversion_sugerido", "informacion_faltante",
    ]
    return projects[front], traceability


def _project_column_config() -> dict:
    return {
        "orden_estrategico": st.column_config.NumberColumn("Orden", format="%d", width="small"),
        "proyecto_id": st.column_config.TextColumn("Proyecto estratégico", width="small"),
        "nombre_proyecto": st.column_config.TextColumn("Nombre propuesto (MIDEPLAN)", width="large"),
        "tipologia_mideplan": st.column_config.TextColumn("Tipología / proceso MIDEPLAN", width="medium"),
        "familia_estrategica": st.column_config.TextColumn("Familia estratégica", width="large"),
        "ids_asociados": st.column_config.TextColumn("ID de necesidades asociadas", width="large"),
        "cantidad_necesidades": st.column_config.NumberColumn("N.º necesidades", format="%d", width="small"),
        "sistemas_beneficiados": st.column_config.TextColumn("Sistemas beneficiados", width="large"),
        "provincias": st.column_config.TextColumn("Provincia(s)", width="medium"),
        "cantones": st.column_config.TextColumn("Cantón(es)", width="large"),
        "distritos": st.column_config.TextColumn("Distrito(s)", width="large"),
        "comunidades": st.column_config.TextColumn("Comunidades", width="large"),
        "problema_necesidad": st.column_config.TextColumn("Problema / necesidad consolidada", width="large"),
        "descripcion": st.column_config.TextColumn("Descripción integral", width="large"),
        "alcance_componentes": st.column_config.TextColumn("Alcance y componentes", width="large"),
        "objetivo_general": st.column_config.TextColumn("Objetivo general", width="large"),
        "objetivos_especificos": st.column_config.TextColumn("Objetivos específicos", width="large"),
        "poblacion_referencia": st.column_config.NumberColumn("Población de referencia", format="%.0f", width="medium"),
        "servicios_referencia": st.column_config.NumberColumn("Servicios de referencia", format="%.0f", width="medium"),
        "caudal_lps": st.column_config.NumberColumn("Caudal potencial (L/s)", format="%.2f", width="medium"),
        "volumen_m3": st.column_config.NumberColumn("Almacenamiento (m³)", format="%.0f", width="medium"),
        "km_red": st.column_config.NumberColumn("Red / conducción (km)", format="%.2f", width="medium"),
        "condicion_hidrica_critica": st.column_config.TextColumn("Condición hídrica crítica", width="small"),
        "estado_bh_critico": st.column_config.NumberColumn("Estado BH crítico (L/s)", format="%.3f", width="medium"),
        "potencial": st.column_config.TextColumn("Potencial estratégico", width="medium"),
        "potencial_puntos": st.column_config.ProgressColumn("Potencial (0-100)", min_value=0, max_value=100, format="%d", width="medium"),
        "nivel_preinversion_sugerido": st.column_config.TextColumn("Nivel de preinversión sugerido", width="large"),
        "informacion_faltante": st.column_config.TextColumn("Información / estudios por completar", width="large"),
    }


def _filter_projects(projects: pd.DataFrame) -> pd.DataFrame:
    f1, f2, f3, f4 = st.columns([1.1, 1.6, 1.6, 2.0])
    potential = f1.multiselect("Potencial", ["Muy alto", "Alto", "Medio", "Bajo"], key="mideplan_potential")
    families = sorted(projects["familia_estrategica"].dropna().astype(str).unique().tolist())
    selected_families = f2.multiselect("Familia estratégica", families, key="mideplan_family")
    provinces = sorted({x for value in projects["provincias"].fillna("") for x in _split(value)})
    selected_provinces = f3.multiselect("Provincia", provinces, key="mideplan_province")
    search = f4.text_input("Buscar", placeholder="Proyecto, ID, sistema, cantón, distrito…", key="mideplan_search")

    out = projects.copy()
    if potential:
        out = out[out["potencial"].isin(potential)]
    if selected_families:
        out = out[out["familia_estrategica"].isin(selected_families)]
    if selected_provinces:
        selected = {_norm(x) for x in selected_provinces}
        out = out[out["provincias"].apply(lambda x: bool(selected & {_norm(v) for v in _split(x)}))]
    q = _norm(search)
    if q:
        cols = ["proyecto_id", "nombre_proyecto", "ids_asociados", "sistemas_beneficiados", "cantones", "distritos", "comunidades", "descripcion"]
        searchable = out[cols].fillna("").astype(str).agg(" ".join, axis=1)
        out = out[searchable.apply(lambda x: q in _norm(x))]
    return out


def vista_reagrupamiento_mideplan() -> None:
    st.subheader("Vista 3.4 · Reagrupamiento Estratégico de Necesidades · MIDEPLAN")
    st.caption(
        "Pre-formulación inteligente de posibles proyectos integrales a partir de la totalidad del Banco de Ideas de la Vista 3.3. "
        "La agrupación conserva la trazabilidad de cada ID original."
    )

    st.info(
        "El motor de reagrupamiento es interno y explicable: combina sistema de abastecimiento, clasificación de 3.2, "
        "componentes hidráulicos, relación territorial y similitud textual. No envía información a un modelo de IA externo. "
        "El resultado es una propuesta de pre-formulación para revisión técnica; no sustituye un perfil, prefactibilidad o factibilidad formal."
    )

    c1, c2 = st.columns([1.2, 3.8])
    if c1.button("🧠 Reagrupar necesidades", type="primary", use_container_width=True, key="mideplan_regroup"):
        with st.spinner("Analizando relaciones hidráulicas, territoriales y temáticas…"):
            projects, trace = build_groups()
            st.session_state["mideplan_projects"] = projects
            st.session_state["mideplan_trace"] = trace
        st.success("Reagrupamiento recalculado con la información vigente de la Vista 3.3.")

    c2.caption(
        "El botón vuelve a calcular desde cero. No modifica ni elimina las necesidades originales ni escribe agrupaciones en Supabase."
    )

    projects = st.session_state.get("mideplan_projects")
    trace = st.session_state.get("mideplan_trace")
    if not isinstance(projects, pd.DataFrame) or projects.empty:
        st.markdown("### Cómo funciona")
        st.write(
            "Pulse **Reagrupar necesidades** para construir posibles proyectos estratégicos. Se propondrá nombre, problema consolidado, "
            "descripción, alcance, objetivos, sistemas y territorio beneficiado, dimensiones disponibles, potencial estratégico, orden de atención "
            "y los ID de necesidades que originan cada agrupación."
        )
        return

    filtered = _filter_projects(projects)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Necesidades originales", f"{len(trace) if isinstance(trace, pd.DataFrame) else 0:,}")
    m2.metric("Proyectos estratégicos propuestos", f"{len(projects):,}")
    reduction = (1 - len(projects) / max(1, len(trace))) * 100 if isinstance(trace, pd.DataFrame) and len(trace) else 0
    m3.metric("Consolidación", f"{reduction:.1f}%", help="Reducción del número de registros al pasar de necesidades individuales a agrupaciones propuestas.")
    m4.metric("Potencial alto / muy alto", f"{int(projects['potencial'].isin(['Alto', 'Muy alto']).sum()):,}")

    tab1, tab2, tab3 = st.tabs(["Proyectos estratégicos", "Trazabilidad de la Vista 3.3", "Criterios MIDEPLAN"])

    with tab1:
        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True,
            height=720,
            column_config=_project_column_config(),
        )
        st.download_button(
            "Descargar proyectos estratégicos (CSV)",
            data=filtered.to_csv(index=False).encode("utf-8-sig"),
            file_name="reagrupamiento_estrategico_mideplan.csv",
            mime="text/csv",
            use_container_width=False,
        )

        st.markdown("#### Ficha rápida por proyecto")
        for _, project in filtered.head(30).iterrows():
            with st.expander(
                f"{int(project['orden_estrategico'])}. {project['proyecto_id']} · {project['nombre_proyecto']} · {project['potencial']} ({int(project['potencial_puntos'])}/100)",
                expanded=False,
            ):
                st.markdown(f"**ID asociados:** {project['ids_asociados']}")
                st.markdown(f"**Problema / necesidad:** {project['problema_necesidad']}")
                st.markdown(f"**Objetivo general:** {project['objetivo_general']}")
                st.markdown(f"**Alcance:** {project['alcance_componentes']}")
                st.markdown(f"**Objetivos específicos:** {project['objetivos_especificos']}")
                st.markdown(f"**Sistemas:** {project['sistemas_beneficiados'] or 'Por definir'}")
                st.markdown(f"**Área de influencia:** {project['provincias']} · {project['cantones']} · {project['distritos']}")
                st.markdown(f"**Nivel de preinversión sugerido:** {project['nivel_preinversion_sugerido']}")
                st.markdown(f"**Información por completar:** {project['informacion_faltante']}")

    with tab2:
        if isinstance(trace, pd.DataFrame) and not trace.empty:
            project_ids = filtered["proyecto_id"].tolist()
            trace_filtered = trace[trace["proyecto_estrategico"].isin(project_ids)].copy()
            display_cols = [
                "proyecto_estrategico", "nombre_proyecto_estrategico", "id_necesidad", "categoria_clasificacion",
                "codigo_interno", "idea_proyecto", "tipo_proyecto_banco", "codigo_nombre_sistema", "ubicacion_provincia",
                "ubicacion_canton", "distritos", "comunidades", "poblacion_beneficiada", "estado_actual_aya",
                "mandato_asociado", "propuesta_solucion", "estudios_terrenos", "proyecto_avance", "descripcion_avance",
                "condicion_hidrica", "estado_sistema_bh", "caudal_estimado_lps", "volumen_estimado_m3", "km_estimado",
                "principal_reto_por_superar", "observacion",
            ]
            display_cols = [c for c in display_cols if c in trace_filtered.columns]
            st.dataframe(trace_filtered[display_cols], use_container_width=True, hide_index=True, height=720)
            st.download_button(
                "Descargar trazabilidad 3.3 → 3.4 (CSV)",
                data=trace_filtered[display_cols].to_csv(index=False).encode("utf-8-sig"),
                file_name="trazabilidad_necesidades_proyectos_mideplan.csv",
                mime="text/csv",
            )

    with tab3:
        st.markdown(
            """
            **Criterios aplicados por el motor interno**

            - **Identificación:** varias ideas o necesidades pueden originar una alternativa de proyecto común.
            - **Tipología:** diferencia acueducto y alcantarillado y propone procesos como Mejoras, Ampliación, Rehabilitación, Remodelación o Construcción.
            - **Nombre:** estructura una denominación con proceso, objeto, pertenencia institucional y localización.
            - **Área de influencia:** integra provincia, cantón, distrito y comunidades disponibles.
            - **Beneficiarios:** consolida población y servicios de los sistemas asociados sin duplicar un mismo sistema.
            - **Estudio técnico preliminar:** agrupa componentes de captación, recurso, conducción, bombeo, potabilización, almacenamiento, distribución, instrumentación, resiliencia y saneamiento.
            - **Tamaño / dimensiones:** resume caudal, almacenamiento y longitud de red cuando la necesidad original contiene esas magnitudes.
            - **Preinversión:** propone un nivel orientativo de identificación/formulación y enumera información faltante para avanzar.

            **Regla de agrupamiento:** una coincidencia temática por sí sola no es suficiente. Se exige una combinación fuerte de sistema, territorio, componente hidráulico y/o similitud textual. Las ideas duplicadas por sistema se consolidan automáticamente.
            """
        )
