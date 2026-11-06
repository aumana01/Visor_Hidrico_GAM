"""Pruebas de validación para el alta integral de Vista 3.1."""
from __future__ import annotations

import unittest

from alta_necesidad_completa import _validar_ubicaciones


class AltaNecesidadCompletaTests(unittest.TestCase):
    def test_admite_varias_ubicaciones_wgs84(self):
        rows = _validar_ubicaciones([
            {
                "tipo_ubicacion": "Ubicación precisa", "nombre_ubicacion": "Tanque",
                "observacion": "Acceso norte", "latitud": "9.935621", "longitud": "-84.082140",
            },
            {
                "tipo_ubicacion": "Ubicación general", "nombre_ubicacion": "Red principal",
                "observacion": "", "latitud": "9,937", "longitud": "-84,083",
            },
        ])
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[0]["latitud"], 9.935621)
        self.assertAlmostEqual(rows[1]["longitud"], -84.083)

    def test_permite_no_aplica_sin_coordenadas(self):
        rows = _validar_ubicaciones([
            {
                "tipo_ubicacion": "No aplica", "nombre_ubicacion": "Impacto general",
                "observacion": "", "latitud": "", "longitud": "",
            },
        ])
        self.assertIsNone(rows[0]["latitud"])
        self.assertIsNone(rows[0]["longitud"])
        self.assertEqual(_validar_ubicaciones([]), [])

    def test_rechaza_coordenadas_incompletas_o_invalidas(self):
        base = {
            "tipo_ubicacion": "Ubicación precisa", "nombre_ubicacion": "",
            "observacion": "", "latitud": "9.9", "longitud": "",
        }
        for lat, lon in [
            ("9.9", ""), ("9.9", "-90"), ("nan", "-84.1"),
            ("abc", "-84.1"), ("", "-84.1"),
        ]:
            with self.subTest(lat=lat, lon=lon):
                with self.assertRaises(ValueError):
                    _validar_ubicaciones([{**base, "latitud": lat, "longitud": lon}])


if __name__ == "__main__":
    unittest.main()
