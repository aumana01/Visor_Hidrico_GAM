from __future__ import annotations

import re
from typing import Any

import pandas as pd

from database import read_optional_table
import territorio_necesidades as territorio_base
import territorio_necesidades_v2 as territorio_v2
import dta_nombres_extra as dta

# Asegura que la Vista 3.3 utilice exactamente los mismos nombres legibles de
# provincia/cantón/distrito que la Vista 3.2.
territorio_v2.province_name = dta.province_name
territorio_v2.canton_name = dta.canton_name
territorio_v2.district_name = dta.district_name


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "<na>", "nat"} else text


def _norm_code(value: object) -> str:
    text = re.sub(r"[^A-Z0-9]", "", _clean(value).upper())
    if text.startswith("MEA"):
        digits = "".join(ch for ch in text[3:] if ch.isdigit())
        if digits:
            return f"MEA{int(digits):02d}"
    return text


def _split_codes(value: object) -> list[str]:
    out: list[str] = []
    for part in re.split(r"[;|,]", _clean(value)):
        code = _norm_code(part)
        if code and code not in out:
            out.append(code)
    return out


def _as_list(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_clean(item) for item in value if _clean(item)]
    text = _clean(value)
    if not text:
        return []
    if text.startswith("{") and text.endswith("}"):
        text = text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [part.strip(" \"'") for part in re.split(r"\s*[;|]\s*|\s*,\s*(?=[A-ZÁÉÍÓÚÑ])", text) if part.strip(" \"'")]


def _persisted_territory() -> dict[int, dict[str, list[str]]]:
    result: dict[int, dict[str, list[str]]] = {}
    try:
        territory = read_optional_table("v_necesidades_territorios")
    except Exception:
        return result
    if territory.empty or "necesidad_id" not in territory.columns:
        return result

    territory = territory.copy()
    territory["necesidad_id"] = pd.to_numeric(territory["necesidad_id"], errors="coerce")
    for _, row in territory[territory["necesidad_id"].notna()].iterrows():
        nid = int(row["necesidad_id"])
        result[nid] = {
            "provincias": _as_list(row.get("provincias_asociadas")),
            "cantones": _as_list(row.get("cantones_asociados")),
            "distritos": _as_list(row.get("distritos_asociados")),
        }
    return result


def _inject_relation_codes(needs: pd.DataFrame) -> pd.DataFrame:
    work = needs.copy()
    if "codigo_de_sistema" not in work.columns:
        work["codigo_de_sistema"] = ""
    if "sistema_de_abastecimiento" not in work.columns:
        work["sistema_de_abastecimiento"] = ""

    try:
        relations = read_optional_table("necesidades_sistemas")
    except Exception:
        relations = pd.DataFrame()

    relation_codes: dict[int, list[str]] = {}
    relation_names: dict[int, list[str]] = {}
    if not relations.empty and "necesidad_id" in relations.columns:
        rel = relations.copy()
        rel["necesidad_id"] = pd.to_numeric(rel["necesidad_id"], errors="coerce")
        rel = rel[rel["necesidad_id"].notna()]
        for need_id, group in rel.groupby("necesidad_id"):
            codes: list[str] = []
            names: list[str] = []
            for _, row in group.iterrows():
                code = _norm_code(row.get("sistema_codigo"))
                name = _clean(row.get("sistema_nombre"))
                if code and code not in codes:
                    codes.append(code)
                if name and name not in names:
                    names.append(name)
            relation_codes[int(need_id)] = codes
            relation_names[int(need_id)] = names

    for idx, row in work.iterrows():
        raw_id = pd.to_numeric(row.get("id"), errors="coerce")
        if pd.isna(raw_id):
            continue
        nid = int(raw_id)
        codes = _split_codes(row.get("codigo_de_sistema"))
        for code in relation_codes.get(nid, []):
            if code not in codes:
                codes.append(code)
        if codes:
            work.at[idx, "codigo_de_sistema"] = "; ".join(codes)

        names = [_clean(part) for part in re.split(r"[;|]", _clean(row.get("sistema_de_abastecimiento"))) if _clean(part)]
        for name in relation_names.get(nid, []):
            if name not in names:
                names.append(name)
        if names:
            work.at[idx, "sistema_de_abastecimiento"] = "; ".join(names)
    return work


def territory_by_need(needs: pd.DataFrame) -> dict[int, dict[str, list[str]]]:
    """Territorio para 3.3 usando primero el mismo geoproceso vivo de 3.2.

    La vista persistida de Supabase queda como respaldo. De este modo, una falla
    temporal de sincronización no vuelve a dejar provincia/cantón/distrito vacíos
    en el Banco de Ideas.
    """
    persisted = _persisted_territory()

    # La vista de Supabase devuelve una fila por necesidad, incluso cuando una
    # de ellas todavía no tiene territorio asociado. Si el conjunto está
    # completo, reutilizarlo evita cargar GeoJSON y repetir intersecciones en
    # cada visita a 3.3. El geoproceso vivo queda como contingencia real.
    expected_ids = {
        int(raw_id)
        for raw_id in pd.to_numeric(needs.get("id"), errors="coerce").dropna()
    }
    if expected_ids and expected_ids.issubset(persisted):
        return {nid: persisted[nid] for nid in expected_ids}

    generated: dict[int, dict[str, list[str]]] = {}

    try:
        crosswalk = territorio_v2.territorial_crosswalk()
        work = _inject_relation_codes(needs)

        # Caso institucional: una necesidad asociada explícitamente a todos los
        # sistemas hereda todos los códigos cartografiados.
        all_codes = sorted(crosswalk.get("sistema_codigo", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
        if all_codes:
            for idx, row in work.iterrows():
                text = f"{_clean(row.get('codigo_de_sistema'))} {_clean(row.get('sistema_de_abastecimiento'))}".lower()
                if "todos los sistemas aya" in text:
                    work.at[idx, "codigo_de_sistema"] = "; ".join(all_codes)

        enriched, _ = territorio_base.associate_needs(work, crosswalk)
        for _, row in enriched.iterrows():
            raw_id = pd.to_numeric(row.get("id"), errors="coerce")
            if pd.isna(raw_id):
                continue
            nid = int(raw_id)
            generated[nid] = {
                "provincias": list(row.get("provincias_asociadas") or []),
                "cantones": list(row.get("cantones_asociados") or []),
                "distritos": list(row.get("distritos_asociados") or []),
            }
    except Exception:
        generated = {}

    result: dict[int, dict[str, list[str]]] = {}
    ids = set(persisted) | set(generated)
    for nid in ids:
        live = generated.get(nid, {"provincias": [], "cantones": [], "distritos": []})
        saved = persisted.get(nid, {"provincias": [], "cantones": [], "distritos": []})
        # Preferir 3.2 en memoria cuando produce información; usar Supabase solo
        # como respaldo para cada nivel individual.
        result[nid] = {
            "provincias": live["provincias"] or saved["provincias"],
            "cantones": live["cantones"] or saved["cantones"],
            "distritos": live["distritos"] or saved["distritos"],
        }
    return result
