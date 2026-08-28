from __future__ import annotations

import re
from typing import Any

import pandas as pd
import streamlit.components.v1 as components

from database import read_optional_table, read_table
import territorio_necesidades_v2 as territorio_v2


# Orden solicitado expresamente para la tabla visible de la Vista 3.3.
STRICT_DISPLAY_COLUMNS = [
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


POSITIVE_PROGRESS_STATES = {
    "En Ejecución",
    "Incorporada al BPIP o convertida en proyecto",
    "Iniciativa enviada a la Dirección de Planificación",
    "Iniciativa trasladada a SAID",
    "Trasladado a Presidencia",
    "Trasladado a Subgerencia GAM",
    "Necesidad Resuelta",
}


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


def _has_progress_evidence(row: pd.Series) -> bool:
    state = _clean(row.get("estado_actual"))
    if state in POSITIVE_PROGRESS_STATES:
        return True

    text = " ".join(
        _clean(row.get(field))
        for field in (
            "detalle_accion",
            "observacion",
            "breve_descripcion",
            "principal_reto_por_superar",
        )
    ).casefold()
    terms = (
        "traslado formal",
        "remitido a planificación",
        "remitida a planificación",
        "enviado a planificación",
        "enviada a planificación",
        "trasladado a said",
        "trasladada a said",
        "incorporado al bpip",
        "incorporada al bpip",
        "proyecto en ejecución",
        "en ejecución",
        "licitación",
        "contratación",
        "diseño en proceso",
        "perforación",
        "ejecutado",
        "ejecutada",
        "matriz de la dirección de planeamiento",
        "unidad responsable de formulación",
    )
    return any(term in text for term in terms)


def _progress_description_for_row(
    need_row: pd.Series | None,
    tracking_row: pd.Series | None,
    output_row: pd.Series,
) -> str:
    existing = _clean(output_row.get("descripcion_avance"))
    if existing:
        return existing
    if _clean(output_row.get("proyecto_avance")).upper() != "SI":
        return ""

    need_row = need_row if need_row is not None else pd.Series(dtype=object)
    tracking_row = tracking_row if tracking_row is not None else pd.Series(dtype=object)

    detail = _clean(tracking_row.get("detalle_accion"))
    observation = _clean(need_row.get("observacion"))
    state = _clean(tracking_row.get("estado_actual"))
    memo = _clean(output_row.get("memo_formulario_necesidad"))

    # Cuando existe una trazabilidad documental, se conserva como principal
    # descripción del avance porque contiene la evidencia disponible.
    if detail:
        return detail

    if observation:
        return observation

    if state == "Iniciativa enviada a la Dirección de Planificación":
        return (
            f"Necesidad trasladada a la Dirección de Planificación mediante {memo}."
            if memo
            else "Necesidad trasladada a la Dirección de Planificación para continuar su formulación."
        )
    if state == "Iniciativa trasladada a SAID":
        return "Iniciativa trasladada a SAID para continuar estudios, diseño o formulación."
    if state == "Incorporada al BPIP o convertida en proyecto":
        return "Iniciativa incorporada al BPIP o convertida formalmente en proyecto."
    if state == "En Ejecución":
        return "Iniciativa con ejecución reportada en la información de seguimiento disponible."
    if state == "Trasladado a Presidencia":
        return "Iniciativa trasladada a Presidencia para seguimiento institucional."
    if state == "Trasladado a Subgerencia GAM":
        return "Iniciativa trasladada a la Subgerencia GAM para seguimiento institucional."
    if state == "Necesidad Resuelta":
        return "Necesidad reportada como resuelta en el seguimiento disponible."

    description = _clean(need_row.get("breve_descripcion"))
    if description:
        return f"Existe una alternativa técnica identificada y documentada: {description}"
    return "Se identifica avance de la iniciativa en la información disponible."


def _render_folium_map(map_object, height: int = 700, **_: Any):
    """Render robusto del mapa de consulta de 3.2.

    La Vista 3.2 no necesita devolver eventos del mapa; se renderiza directamente
    el HTML de Folium para evitar que una incompatibilidad de streamlit-folium deje
    el componente en blanco. La edición/georreferenciación conserva st_folium.
    """
    html = map_object.get_root().render()
    components.html(html, height=int(height), scrolling=False)
    return {}


def apply_patches(seguimiento_module) -> None:
    # 1) Orden visible estricto de las 24 columnas solicitadas.
    seguimiento_module.DISPLAY_COLUMNS = list(STRICT_DISPLAY_COLUMNS)

    original_infer_progress = seguimiento_module._infer_progress
    original_prepare_work = seguimiento_module._prepare_work
    original_save_tracking = seguimiento_module._save_tracking
    original_column_config = seguimiento_module._column_config

    def infer_progress(row: pd.Series) -> str:
        stored = seguimiento_module._normalize_yes_no(row.get("proyecto_avance"), "NO")
        if stored == "SI":
            return "SI"
        # El NO creado por defecto en Supabase no debe ocultar evidencia positiva
        # que ya exista en estado, memorandos, observaciones o detalle de acción.
        if _has_progress_evidence(row):
            return "SI"
        return original_infer_progress(row)

    seguimiento_module._infer_progress = infer_progress

    def prepare_work() -> pd.DataFrame:
        work = original_prepare_work()
        if work.empty:
            return work

        needs = read_table("necesidades")
        tracking = read_optional_table("necesidades_seguimiento")

        need_map: dict[int, pd.Series] = {}
        if not needs.empty and "id" in needs.columns:
            ids = pd.to_numeric(needs["id"], errors="coerce")
            for idx, raw_id in ids.items():
                if pd.notna(raw_id):
                    need_map[int(raw_id)] = needs.loc[idx]

        tracking_map: dict[int, pd.Series] = {}
        if not tracking.empty and "necesidad_id" in tracking.columns:
            ids = pd.to_numeric(tracking["necesidad_id"], errors="coerce")
            for idx, raw_id in ids.items():
                if pd.notna(raw_id):
                    tracking_map[int(raw_id)] = tracking.loc[idx]

        for idx, output_row in work.iterrows():
            raw_id = pd.to_numeric(output_row.get("necesidad_id"), errors="coerce")
            if pd.isna(raw_id):
                continue
            nid = int(raw_id)
            need_row = need_map.get(nid)
            track_row = tracking_map.get(nid)

            # Revalida el avance con toda la evidencia, incluso si Supabase tenía
            # un NO de default creado por SQL 09.
            evidence_row = pd.Series(dtype=object)
            if need_row is not None:
                evidence_row = need_row.copy()
            if track_row is not None:
                for key, value in track_row.items():
                    evidence_row[key] = value
            if _has_progress_evidence(evidence_row):
                work.at[idx, "proyecto_avance"] = "SI"
                output_row = work.loc[idx]

            work.at[idx, "descripcion_avance"] = _progress_description_for_row(
                need_row,
                track_row,
                output_row,
            )
        return work

    seguimiento_module._prepare_work = prepare_work

    def save_tracking(edited: pd.DataFrame) -> None:
        # Las columnas administrativas iniciales ya no se muestran, pero sus
        # valores se conservan al guardar para no borrar información previa.
        expanded = edited.copy()
        current = read_optional_table("necesidades_seguimiento")
        current_by_id: dict[int, pd.Series] = {}
        if not current.empty and "necesidad_id" in current.columns:
            ids = pd.to_numeric(current["necesidad_id"], errors="coerce")
            for idx, raw_id in ids.items():
                if pd.notna(raw_id):
                    current_by_id[int(raw_id)] = current.loc[idx]

        for column in seguimiento_module.TRACKING_FIELDS:
            if column in expanded.columns:
                continue
            values = []
            for raw_id in expanded.index:
                nid = int(raw_id)
                row = current_by_id.get(nid)
                values.append(row.get(column) if row is not None else pd.NA)
            expanded[column] = values
        original_save_tracking(expanded)

    seguimiento_module._save_tracking = save_tracking

    def column_config() -> dict[str, Any]:
        config = original_column_config()
        config["codigo_nombre_sistema"] = seguimiento_module.st.column_config.TextColumn(
            "Codigo y Nombre del Sistema", width="large"
        )
        return config

    seguimiento_module._column_config = column_config

    # 2) Restablece el mapa de consulta de 3.2 con un render HTML robusto.
    # Solo afecta territorio_necesidades_v2; el editor de puntos sigue usando
    # streamlit-folium y por tanto mantiene la captura de clics.
    territorio_v2.st_folium = _render_folium_map
