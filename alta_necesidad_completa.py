"""Alta integral de necesidades desde la Vista 3.1.

Los datos se guardan en las mismas tablas utilizadas por las Vistas 3.2 y 3.3.
No introduce campos duplicados ni altera sus editores.
"""
from __future__ import annotations

import math

import pandas as pd
import streamlit as st

import seguimiento_necesidades_v2 as banco
from database import get_supabase_client, replace_need_systems, upsert_rows


def _texto(label: str, key: str, default: str = "", multiline: bool = False) -> str:
    widget = st.text_area if multiline else st.text_input
    return widget(label, value=default, key=key).strip()


def _validar_ubicaciones(ubicaciones: list[dict]) -> list[dict]:
    """Rechaza coordenadas incompletas, no numéricas o ajenas a Costa Rica."""
    rows = []
    for numero, item in enumerate(ubicaciones, 1):
        tipo = item["tipo_ubicacion"]
        row = {
            "tipo_ubicacion": tipo,
            "nombre_ubicacion": item["nombre_ubicacion"].strip(),
            "observacion": item["observacion"].strip(),
            "latitud": None,
            "longitud": None,
        }
        if tipo != "No aplica":
            raw_lat = item["latitud"].strip().replace(",", ".")
            raw_lon = item["longitud"].strip().replace(",", ".")
            if not raw_lat or not raw_lon:
                raise ValueError(
                    f"Ubicación {numero}: debe ingresar latitud y longitud; "
                    "si no conoce el punto, seleccione «No aplica» o reduzca "
                    "la cantidad de ubicaciones iniciales."
                )
            try:
                lat, lon = float(raw_lat), float(raw_lon)
            except ValueError as exc:
                raise ValueError(f"Ubicación {numero}: coordenadas no numéricas.") from exc
            if not (math.isfinite(lat) and math.isfinite(lon)
                    and 8.0 <= lat <= 12.0 and -86.5 <= lon <= -82.0):
                raise ValueError(
                    f"Ubicación {numero}: latitud debe estar entre 8 y 12, "
                    "y longitud entre -86.5 y -82 (WGS84)."
                )
            row.update(latitud=lat, longitud=lon)
        rows.append(row)
    return rows


def _verificar_tablas_supabase() -> None:
    """Detecta migraciones faltantes antes de crear el registro principal."""
    client = get_supabase_client()
    if client is None:
        return
    required = {
        "necesidades_ubicaciones": "necesidad_id,tipo_ubicacion,latitud,longitud,nombre_ubicacion,observacion",
        "necesidades_sistemas": "necesidad_id,sistema_nombre,sistema_codigo",
        "necesidades_seguimiento": ",".join([
            "necesidad_id", "estado_actual", "detalle_accion", *banco.TRACKING_FIELDS
        ]),
    }
    for table, columns in required.items():
        try:
            client.table(table).select(columns).limit(1).execute()
        except Exception as exc:
            raise RuntimeError(
                f"La tabla {table} no está disponible o le faltan columnas/permisos. "
                "Revise los scripts SQL 02, 03, 04, 06, 09 y 13 del repositorio "
                f"antes de crear la necesidad. Detalle: {exc}"
            ) from exc


def _guardar_alta(
    necesidad: dict,
    sistemas: pd.DataFrame,
    nombres_sistemas: list[str],
    ubicaciones: list[dict],
    seguimiento: dict,
) -> int:
    """Persiste alta y relaciones; permite reintentar sin duplicar ubicaciones."""
    from app_core import normalize_need_rows, resolve_system_selection

    nombres, codigos, unknown = resolve_system_selection(nombres_sistemas, sistemas)
    if unknown:
        raise ValueError("Sistemas no encontrados: " + ", ".join(unknown))
    if len(nombres) != len(codigos):
        raise ValueError("Uno o más sistemas seleccionados no tienen código asociado.")
    if not necesidad["objetivo_de_la_iniciativa"].strip():
        raise ValueError("El objetivo de la iniciativa es obligatorio.")
    if seguimiento["mandato_asociado"] != "No" and seguimiento["fecha_recurso_amparo"] is None:
        # Un mandato puede no tener una fecha de recurso; la fecha sigue siendo opcional.
        pass

    _verificar_tablas_supabase()
    pending = st.session_state.get("alta_necesidad_pendiente")
    # Las ubicaciones ya guardadas no se insertan de nuevo al reintentar
    # un error posterior (por ejemplo, un permiso en seguimiento).
    if pending is None:
        parent = normalize_need_rows(pd.DataFrame([necesidad]), sistemas)
        saved = upsert_rows("necesidades", parent)
        new_id = int(saved.iloc[0]["id"])
        pending = {"id": new_id, "sistemas": False, "ubicaciones": False, "seguimiento": False}
        st.session_state["alta_necesidad_pendiente"] = pending
    else:
        new_id = int(pending["id"])
        # Conserva los ajustes hechos por el usuario mientras resuelve el error.
        parent = normalize_need_rows(pd.DataFrame([{**necesidad, "id": new_id}]), sistemas)
        upsert_rows("necesidades", parent)

    if not pending["sistemas"]:
        replace_need_systems(new_id, nombres, sistemas)
        pending["sistemas"] = True
    if not pending["ubicaciones"]:
        if ubicaciones:
            upsert_rows(
                "necesidades_ubicaciones",
                pd.DataFrame([{**row, "necesidad_id": new_id} for row in ubicaciones]),
            )
        pending["ubicaciones"] = True
    if not pending["seguimiento"]:
        upsert_rows(
            "necesidades_seguimiento",
            pd.DataFrame([{**seguimiento, "necesidad_id": new_id}]),
        )
        pending["seguimiento"] = True

    st.session_state.pop("alta_necesidad_pendiente", None)
    return new_id


def render_alta_necesidad(
    tipo_options: list[str],
    sistema_options: list[str],
    sistemas: pd.DataFrame,
) -> None:
    """Formulario único: ficha general, georreferencia y banco de ideas."""
    from app_core import (
        ATENCION_NECESIDAD_OPTIONS, COSTO_NECESIDAD_OPTIONS,
        ESTADO_SEGUIMIENTO_OPTIONS, resolve_system_selection,
    )

    st.caption(
        "Registre aquí toda la información inicial. Los campos geográficos "
        "se podrán seguir editando en 3.2 y los del Banco de Ideas en 3.3. "
        "Los indicadores de población, servicios y condición hídrica se calculan automáticamente."
    )
    if st.session_state.get("alta_necesidad_pendiente"):
        st.warning(
            "Existe un alta parcialmente guardada con ID "
            f"{st.session_state['alta_necesidad_pendiente']['id']}. "
            "Revise el error anterior y vuelva a guardar: se reutilizará "
            "ese mismo ID, sin duplicar los puntos ya insertados."
        )

    cantidad = st.number_input(
        "Cantidad de ubicaciones iniciales (Vista 3.2)",
        min_value=0, max_value=10, value=1, step=1,
        key="alta_cantidad_ubicaciones",
        help="Puede registrar varios puntos ahora o elegir 0 y georreferenciar más adelante.",
    )
    nonce = st.session_state.get("alta_nonce", 0)
    def k(name: str) -> str:
        return f"alta_{nonce}_{name}"

    with st.form("form_necesidad", clear_on_submit=False):
        st.markdown("#### 1. Información general de la necesidad")
        objetivo = _texto("Objetivo de la iniciativa *", k("objetivo"), multiline=True)
        descripcion = _texto("Breve descripción", k("descripcion"), multiline=True)
        cat1, cat2 = st.columns([1, 2])
        tipo = cat1.selectbox("Tipo de proyecto / categoría", ["", *[t for t in tipo_options if t]], key=k("tipo"))
        seleccion = cat2.multiselect(
            "Sistemas de abastecimiento asociados", options=sistema_options,
            key=k("sistemas"), help="Se permite asociar varios sistemas a una necesidad.",
        )
        _, codigos, _ = resolve_system_selection(seleccion, sistemas)
        st.caption("Códigos automáticos: " + ("; ".join(codigos) if codigos else "Sin sistemas seleccionados"))

        c1, c2 = st.columns(2)
        costo = c1.selectbox("Estimación de costos", COSTO_NECESIDAD_OPTIONS, key=k("costo"))
        responsabilidad = c2.selectbox(
            "Clasificación de atención", ATENCION_NECESIDAD_OPTIONS, key=k("atencion")
        )
        reto = _texto("Principal reto por superar", k("reto"), multiline=True)
        observacion = _texto("Observación general", k("observacion"), multiline=True)
        a, b, c = st.columns(3)
        caudal = a.number_input("Caudal aportado (L/s)", min_value=0.0, value=0.0, step=1.0, key=k("caudal"))
        volumen = b.number_input("Volumen aportado (m³)", min_value=0.0, value=0.0, step=10.0, key=k("volumen"))
        km = c.number_input("Red o conducción (km)", min_value=0.0, value=0.0, step=0.1, key=k("km"))

        with st.expander("Otros campos generales de la ficha inicial", expanded=False):
            origen = _texto("Código o ID de origen", k("origen"))
            zona = _texto("Zona o sector", k("zona"))
            p1, p2, p3 = st.columns(3)
            prioridad = _texto("Prioridad", k("prioridad")) if False else p1.text_input("Prioridad", key=k("prioridad")).strip()
            plazo = p2.text_input("Plazo", key=k("plazo")).strip()
            estado_general = p3.text_input("Estado general", key=k("estado_general")).strip()

        st.markdown("#### 2. Ubicaciones iniciales (Vista 3.2)")
        st.caption("Coordenadas WGS84. Si necesita el mapa interactivo para colocar o mover puntos, continúe en la Vista 3.2.")
        ubicaciones = []
        for index in range(int(cantidad)):
            with st.expander(f"Ubicación {index + 1}", expanded=index == 0):
                loc_a, loc_b = st.columns([1, 2])
                loc_tipo = loc_a.selectbox(
                    "Tipo de ubicación",
                    ["Ubicación precisa", "Ubicación general", "Ubicación institucional", "No aplica"],
                    key=k(f"loc_tipo_{index}"),
                )
                loc_nombre = loc_b.text_input("Nombre o referencia", key=k(f"loc_nombre_{index}"))
                lat_col, lon_col = st.columns(2)
                lat = lat_col.text_input(
                    "Latitud WGS84", placeholder="9.935621",
                    disabled=loc_tipo == "No aplica", key=k(f"loc_lat_{index}"),
                )
                lon = lon_col.text_input(
                    "Longitud WGS84", placeholder="-84.082140",
                    disabled=loc_tipo == "No aplica", key=k(f"loc_lon_{index}"),
                )
                loc_observacion = st.text_input("Observación del punto", key=k(f"loc_obs_{index}"))
                ubicaciones.append({
                    "tipo_ubicacion": loc_tipo, "nombre_ubicacion": loc_nombre,
                    "latitud": lat, "longitud": lon, "observacion": loc_observacion,
                })

        st.markdown("#### 3. Banco de Ideas / Seguimiento (Vista 3.3)")
        st.caption("Los campos de seguimiento son opcionales, salvo las selecciones con valores iniciales institucionales.")
        t1, t2 = st.columns(2)
        seguimiento = {
            "codigo_interno": t1.text_input("Código interno", key=k("codigo_interno")).strip(),
            "unidad_solicitante": t2.text_input("Unidad solicitante", value="GAM", key=k("unidad_solicitante")).strip(),
        }
        t1, t2 = st.columns(2)
        seguimiento["unidad_formula_idea"] = t1.text_input("Unidad que formula la idea", key=k("unidad_formula")).strip()
        seguimiento["posible_fuente_financiamiento"] = t2.text_input(
            "Posible fuente de financiamiento", value="Pendiente", key=k("fuente")
        ).strip()
        t1, t2 = st.columns(2)
        seguimiento["tipo_licitacion"] = t1.selectbox("Tipo de licitación", banco.LICITACION_OPTIONS, key=k("licitacion"))
        seguimiento["tipo_proyecto_banco"] = t2.text_input(
            "Tipo de proyecto (Banco de Ideas)", value=banco.TIPO_PROYECTO_DEFAULT,
            key=k("tipo_banco"),
        ).strip()
        t1, t2 = st.columns(2)
        seguimiento["memo_formulario_necesidad"] = t1.text_input(
            "Memo formulario de necesidad", key=k("memo")
        ).strip()
        seguimiento["acuerdo_cdp"] = t2.selectbox(
            "Acuerdo del Comité Director de Proyectos", banco.SI_NO_OPTIONS, key=k("cdp")
        )
        t1, t2 = st.columns(2)
        seguimiento["region_aya"] = t1.text_input(
            "Región AyA", value=banco.REGION_DEFAULT, key=k("region")
        ).strip()
        seguimiento["estado_actual_aya"] = t2.selectbox(
            "Estado Actual (AyA)", banco.ESTADO_AYA_OPTIONS, key=k("estado_aya")
        )
        seguimiento["comunidades"] = _texto("Comunidades beneficiadas", k("comunidades"))
        t1, t2 = st.columns(2)
        seguimiento["mandato_asociado"] = t1.selectbox(
            "Recurso de amparo o mandato asociado", banco.MANDATO_OPTIONS, key=k("mandato")
        )
        fecha_amparo = t2.date_input(
            "Fecha de recurso de amparo (si corresponde)", value=None,
            format="DD/MM/YYYY", key=k("fecha_amparo"),
        )
        seguimiento["fecha_recurso_amparo"] = (
            fecha_amparo.isoformat() if fecha_amparo is not None else None
        )
        si_no_campos = [
            ("propuesta_solucion", "Se cuenta con propuesta de solución"),
            ("orden_desacato", "Orden de desacato"),
            ("compromiso_social", "Compromiso social"),
            ("estudios_terrenos", "Estudios o terrenos"),
            ("proyecto_avance", "¿El proyecto cuenta con algún avance?"),
        ]
        for start in range(0, len(si_no_campos), 2):
            cols = st.columns(2)
            for col, (field, label) in zip(cols, si_no_campos[start:start + 2]):
                seguimiento[field] = col.selectbox(label, banco.SI_NO_OPTIONS, key=k(field))
        seguimiento["descripcion_avance"] = _texto(
            "Descripción del avance", k("descripcion_avance"), multiline=True
        )
        t1, t2 = st.columns(2)
        seguimiento["priorizacion_region"] = t1.number_input(
            "Priorización regional (opcional)", value=None, min_value=0,
            step=1, key=k("priorizacion"),
        )
        seguimiento["estado_sistema_ba"] = t2.number_input(
            "Estado del sistema BA (opcional)", value=None,
            step=0.1, key=k("estado_ba"),
        )

        with st.expander("Seguimiento detallado de la necesidad", expanded=False):
            seguimiento["estado_actual"] = st.selectbox(
                "Estado de seguimiento de la iniciativa",
                ["", *ESTADO_SEGUIMIENTO_OPTIONS], key=k("estado_seguimiento"),
            ) or None
            seguimiento["detalle_accion"] = _texto(
                "Detalle de la acción / trazabilidad", k("detalle"), multiline=True
            )
        st.caption(
            "La idea de proyecto, descripción, categoría, sistemas, provincia, cantón, "
            "distritos, coordenadas y métricas calculadas se derivan de los datos anteriores."
        )
        enviar = st.form_submit_button("Guardar necesidad completa", type="primary")

    if not enviar:
        return
    try:
        coords = _validar_ubicaciones(ubicaciones)
        necesidad = {
            "id_origen": origen,
            "objetivo_de_la_iniciativa": objetivo,
            "breve_descripcion": descripcion,
            "tipo_de_proyecto": tipo,
            "sistema_de_abastecimiento": "; ".join(seleccion),
            "codigo_de_sistema": "; ".join(codigos),
            "zona": zona,
            "prioridad": prioridad,
            "plazo": plazo,
            "costo": costo,
            "estado": estado_general,
            "principal_reto_por_superar": reto,
            "observacion": observacion,
            "caudal_estimado_lps": caudal,
            "volumen_estimado_m3": volumen,
            "km_estimado": km,
            "responsabilidad_atencion": responsabilidad,
            "activo": True,
        }
        new_id = _guardar_alta(necesidad, sistemas, seleccion, coords, seguimiento)
    except (ValueError, RuntimeError, Exception) as exc:
        st.error(f"No se pudo completar el alta: {exc}")
        return

    st.session_state["alta_nonce"] = nonce + 1
    st.success(
        f"Necesidad ID {new_id} creada con los datos generales, "
        "sistemas, ubicaciones y seguimiento inicial. "
        "Puede ajustar cualquier información desde las Vistas 3.1, 3.2 y 3.3."
    )
