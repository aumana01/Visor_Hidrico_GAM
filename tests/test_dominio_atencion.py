"""Dominio de clasificación de atención compartido por Vistas 3.1 y 3.3."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from clasificacion_atencion import DOMINIO_ATENCION, normalizar_atencion
import seguimiento_necesidades_v3 as vista


class DominioAtencionTests(unittest.TestCase):
    def test_dominio_institucional_es_exactamente_el_solicitado(self):
        self.assertEqual(DOMINIO_ATENCION, [
            "Lo puede atender GAM",
            "Requiere apoyo de otras dependencias",
            "Ambos",
            "Sin clasificar",
        ])

    def test_homologa_variantes_historicas(self):
        cases = {
            "Lo puede atender el GAM": "Lo puede atender GAM",
            "Lo puede atender GAM": "Lo puede atender GAM",
            "Se requiere apoyo de otras dependencias": "Requiere apoyo de otras dependencias",
            "Requiere apoyo de otras dependencias": "Requiere apoyo de otras dependencias",
            "Ambos": "Ambos",
            "": "Sin clasificar",
            None: "Sin clasificar",
            "  ": "Sin clasificar",
        }
        for old, canonical in cases.items():
            with self.subTest(old=old):
                self.assertEqual(normalizar_atencion(old), canonical)

    def test_filtro_reconoce_datos_historicos_y_nuevos(self):
        needs = pd.DataFrame({"responsabilidad_atencion": [
            "Lo puede atender el GAM",
            "Lo puede atender GAM",
            "Se requiere apoyo de otras dependencias",
            "Ambos",
            None,
        ]})
        filtered = vista._filter_attention(needs, ["Lo puede atender GAM"])
        self.assertEqual(filtered.index.tolist(), [0, 1])
        filtered = vista._filter_attention(needs, ["Requiere apoyo de otras dependencias", "Sin clasificar"])
        self.assertEqual(filtered.index.tolist(), [2, 4])

    def test_cambio_en_33_usa_dominio_canonico(self):
        data = pd.DataFrame({
            "responsabilidad_atencion": ["Lo puede atender GAM"],
            "categoria_clasificacion": ["Optimización"],
            "costo": [""],
            "caudal_estimado_lps": [0.0],
            "volumen_estimado_m3": [0.0],
            "km_estimado": [0.0],
        }, index=pd.Index([44], name="necesidad_id"))
        new = data.copy()
        new.loc[44, "responsabilidad_atencion"] = "Requiere apoyo de otras dependencias"
        self.assertEqual(vista._changed_need_values(new, data), {
            44: {"responsabilidad_atencion": "Requiere apoyo de otras dependencias"}
        })


if __name__ == "__main__":
    unittest.main()
