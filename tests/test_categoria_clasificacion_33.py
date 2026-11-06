"""Pruebas para la edición bidireccional de categoría desde Vista 3.3."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

import seguimiento_necesidades_v3 as view


class CategoriaClasificacionTests(unittest.TestCase):
    def test_categoria_es_editable_y_se_guarda_como_tipo_de_proyecto(self):
        self.assertIn("categoria_clasificacion", view.NEED_EDIT_FIELDS)
        self.assertNotIn("categoria_clasificacion", view.AUTOMATIC_COLUMNS)
        self.assertEqual(
            view.NEED_DB_FIELDS["categoria_clasificacion"], "tipo_de_proyecto"
        )

    def test_al_cambiar_categoria_solo_se_modifica_columna_original(self):
        original = pd.DataFrame(
            {
                "categoria_clasificacion": ["Optimización", "Aumento de Recurso Hídrico"],
                "costo": ["", ""],
                "caudal_estimado_lps": [0.0, 5.0],
                "volumen_estimado_m3": [0.0, 0.0],
                "km_estimado": [0.0, 0.0],
                "responsabilidad_atencion": ["", ""],
            },
            index=pd.Index([17, 23], name="necesidad_id"),
        )
        edited = original.copy()
        edited.loc[17, "categoria_clasificacion"] = "Mejora en Almacenamiento"
        changes = view._changed_need_values(edited, original)
        self.assertEqual(
            changes, {17: {"tipo_de_proyecto": "Mejora en Almacenamiento"}}
        )
        self.assertEqual(view._changed_need_values(original, original), {})

    def test_guardado_local_preserva_campos_no_editados(self):
        original = pd.DataFrame(
            [
                {
                    "id": 17,
                    "tipo_de_proyecto": "Optimización",
                    "objetivo_de_la_iniciativa": "Mejorar la capacidad operativa",
                    "caudal_estimado_lps": 12.0,
                }
            ]
        )
        with (
            patch.object(view, "get_supabase_client", return_value=None),
            patch.object(view.base, "read_table", return_value=original),
            patch.object(view, "upsert_rows") as save,
        ):
            view._save_need_changes({17: {"tipo_de_proyecto": "Mejora en Almacenamiento"}})
        table, updated = save.call_args.args
        self.assertEqual(table, "necesidades")
        self.assertEqual(updated["tipo_de_proyecto"].iloc[0], "Mejora en Almacenamiento")
        self.assertEqual(updated["objetivo_de_la_iniciativa"].iloc[0], "Mejorar la capacidad operativa")
        self.assertEqual(updated["caudal_estimado_lps"].iloc[0], 12.0)


if __name__ == "__main__":
    unittest.main()
