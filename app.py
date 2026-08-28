from __future__ import annotations

# El cuerpo histórico de la aplicación se conserva en app_core.py.
# Este punto de entrada sustituye únicamente la Vista 3.3 por el formato
# institucional del Banco de Ideas de Proyectos AyA (EST-02-02-F4).
import app_core as _app
import seguimiento_necesidades_v2 as _seguimiento
from territorio_seguimiento_patch import territory_by_need as _territory_by_need
from ajustes_vistas_32_33 import apply_patches as _apply_patches
import seguimiento_necesidades_v3 as _seguimiento_v3

# La Vista 3.3 consume primero el mismo geoproceso vivo de la Vista 3.2 y usa
# Supabase como respaldo. Así provincia/cantón/distrito no dependen de que la
# sincronización territorial ya se haya completado en la sesión.
_seguimiento._territory_by_need = _territory_by_need

# Ajustes adicionales solicitados:
# - orden estricto de columnas de la Vista 3.3;
# - completar automáticamente Descripción del avance con evidencia disponible;
# - render robusto del mapa de consulta de la Vista 3.2.
_apply_patches(_seguimiento)

# La versión 3.3 agrega ID de necesidad, filtro por ID y la categoría/
# clasificación utilizada en la Vista 3.2, sin modificar el esquema de Supabase.
_app.vista_seguimiento_necesidades = _seguimiento_v3.vista_seguimiento_necesidades


if __name__ == "__main__":
    _app.main()
