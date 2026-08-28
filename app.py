from __future__ import annotations

import streamlit as st

# El cuerpo histórico de la aplicación se conserva en app_core.py.
# Este punto de entrada mantiene las vistas existentes y agrega la Vista 3.4
# como módulo independiente, de forma que el cambio sea fácil de revertir.
import app_core as _app
import seguimiento_necesidades_v2 as _seguimiento
from territorio_seguimiento_patch import territory_by_need as _territory_by_need
from ajustes_vistas_32_33 import apply_patches as _apply_patches
import seguimiento_necesidades_v3 as _seguimiento_v3
import reagrupamiento_mideplan as _mideplan

# La Vista 3.3 consume primero el mismo geoproceso vivo de la Vista 3.2 y usa
# Supabase como respaldo.
_seguimiento._territory_by_need = _territory_by_need

# Ajustes consolidados de 3.2 y 3.3.
_apply_patches(_seguimiento)
_app.vista_seguimiento_necesidades = _seguimiento_v3.vista_seguimiento_necesidades


def main() -> None:
    """Navegación principal, extendida únicamente con la Vista 3.4."""
    _app.title()
    _app.admin_sidebar()

    if "vista_principal" not in st.session_state:
        st.session_state["vista_principal"] = "proyectos"

    st.sidebar.markdown("##### Vistas")

    def navigation_button(label: str, view_key: str) -> None:
        active = st.session_state["vista_principal"] == view_key
        if st.sidebar.button(
            label,
            use_container_width=True,
            type="primary" if active else "secondary",
            key=f"nav_{view_key}",
        ):
            if not active:
                st.session_state["vista_principal"] = view_key
                st.rerun()

    navigation_button("1. Gestión de Proyectos", "proyectos")
    navigation_button("2. Capacidad Hídrica GAM", "capacidad")

    st.sidebar.markdown("**3. Gestión de información de Necesidades de Inversión**")
    navigation_button("3.1 Generar / Administrar necesidades", "necesidades")
    navigation_button("3.2 Mapa de Necesidades", "mapa_necesidades")
    navigation_button("3.3 Seguimiento de Necesidades", "seguimiento_necesidades")
    navigation_button("3.4 Reagrupamiento Estratégico MIDEPLAN", "reagrupamiento_mideplan")

    st.sidebar.markdown("**4. Otros**")
    navigation_button(
        "4.1 Lecciones Aprendidas con Proyectos de Inversión",
        "lecciones",
    )

    view = st.session_state["vista_principal"]
    if view == "proyectos":
        _app.vista_proyectos()
    elif view == "capacidad":
        _app.vista_capacidad()
    elif view == "necesidades":
        _app.vista_necesidades()
    elif view == "mapa_necesidades":
        _app.vista_mapa_necesidades()
    elif view == "seguimiento_necesidades":
        _seguimiento_v3.vista_seguimiento_necesidades()
    elif view == "reagrupamiento_mideplan":
        _mideplan.vista_reagrupamiento_mideplan()
    else:
        _app.vista_lecciones()


if __name__ == "__main__":
    main()
