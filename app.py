from __future__ import annotations

# El cuerpo histórico de la aplicación se conserva en app_core.py.
# Este punto de entrada sustituye únicamente la Vista 3.3 por el formato
# institucional del Banco de Ideas de Proyectos AyA (EST-02-02-F4).
import app_core as _app
from seguimiento_necesidades_v2 import vista_seguimiento_necesidades as _vista_seguimiento_necesidades

_app.vista_seguimiento_necesidades = _vista_seguimiento_necesidades


if __name__ == "__main__":
    _app.main()
