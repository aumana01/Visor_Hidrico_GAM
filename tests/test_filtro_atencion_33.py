"""Pruebas del filtro de clasificación de atención en la Vista 3.3."""
from __future__ import annotations

import unittest

import pandas as pd

from seguimiento_necesidades_v3 import _filter_attention


class FiltroAtencionTests(unittest.TestCase):
    def setUp(self):
        self.needs = pd.DataFrame({
            "id_necesidad": [1, 2, 3, 4, 5],
            "responsabilidad_atencion": [
                "Lo puede atender el GAM",
                "Se requiere apoyo de otras dependencias",
                "Ambos",
                None,
                "  ",
            ],
            "estado_actual_aya": [
                "En lista de espera",
                "En lista de espera",
                "Formulación de Iniciativa",
                "En lista de espera",
                "Formulación de Iniciativa",
            ],
        })

    def test_sin_filtro_conserva_todos_los_registros(self):
        self.assertEqual(len(_filter_attention(self.needs, [])), 5)

    def test_filtra_por_una_clasificacion(self):
        result = _filter_attention(self.needs, ["Lo puede atender GAM"])
        self.assertEqual(result["id_necesidad"].tolist(), [1])

    def test_seleccion_multiple_es_inclusiva(self):
        result = _filter_attention(self.needs, ["Ambos", "Lo puede atender GAM"])
        self.assertEqual(result["id_necesidad"].tolist(), [1, 3])

    def test_sin_clasificar_incluye_nulos_y_blancos(self):
        result = _filter_attention(self.needs, ["Sin clasificar"])
        self.assertEqual(result["id_necesidad"].tolist(), [4, 5])

    def test_sin_clasificar_se_combina_con_otras_clasificaciones(self):
        result = _filter_attention(self.needs, ["Ambos", "Sin clasificar"])
        self.assertEqual(result["id_necesidad"].tolist(), [3, 4, 5])


if __name__ == "__main__":
    unittest.main()
