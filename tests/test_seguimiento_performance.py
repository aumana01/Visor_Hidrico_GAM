from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import geo_necesidades  # configura nombres y archivos territoriales
import seguimiento_necesidades_v2 as base
import seguimiento_necesidades_v3 as view
import territorio_necesidades_v2 as territory
import territorio_seguimiento_patch as territory_patch
from ajustes_vistas_32_33 import apply_patches
from database import clear_cache, data_revision
from streamlit.testing.v1 import AppTest


class SeguimientoPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base._territory_by_need = territory_patch.territory_by_need
        apply_patches(base)

    def test_repeated_reruns_do_not_stack_patches(self):
        functions = (base._prepare_work, base._infer_progress, base._save_tracking, base._column_config)
        for _ in range(100):
            apply_patches(base)
        self.assertEqual(functions, (base._prepare_work, base._infer_progress, base._save_tracking, base._column_config))

    def test_precomputed_territory_matches_live_geometry(self):
        cached = territory._load_precomputed_crosswalk(territory.MIN_ADMIN_COVERAGE_PCT)
        self.assertIsNotNone(cached)
        live = territory.territorial_crosswalk(use_precomputed=False)
        pd.testing.assert_frame_equal(cached, live)
        self.assertIsNone(territory._load_precomputed_crosswalk(25.0))
        with patch.object(territory, "territorial_source_hashes", return_value={}):
            self.assertIsNone(territory._load_precomputed_crosswalk(10.0))

    def test_partial_territory_only_processes_missing_needs(self):
        needs = pd.DataFrame({"id": [1, 2], "codigo_de_sistema": ["MEA01", "MEA02"]})
        saved = {1: {"provincias": ["San José"], "cantones": ["San José"], "distritos": ["Pavas"]}}
        generated = pd.DataFrame({
            "id": [2], "provincias_asociadas": [["Heredia"]],
            "cantones_asociados": [["Heredia"]], "distritos_asociados": [["Ulloa"]],
        })
        with (
            patch.object(territory_patch, "_persisted_territory", return_value=saved),
            patch.object(territory_patch, "_inject_relation_codes", side_effect=lambda df: df),
            patch.object(territory, "territorial_crosswalk", return_value=pd.DataFrame()),
            patch.object(territory_patch.territorio_base, "associate_needs", return_value=(generated, {})) as associate,
        ):
            result = territory_patch.territory_by_need(needs)
            self.assertEqual(associate.call_args.args[0]["id"].tolist(), [2])
            self.assertEqual(result[1], saved[1])
            self.assertEqual(result[2]["distritos"], ["Ulloa"])
        with (
            patch.object(territory_patch, "_persisted_territory", return_value=result),
            patch.object(territory, "territorial_crosswalk") as geoprocess,
        ):
            self.assertEqual(territory_patch.territory_by_need(needs), result)
            geoprocess.assert_not_called()

    def test_cached_preparation_is_invalidated_after_writes(self):
        view._prepare_work_cached.clear()
        with patch.object(base, "_prepare_work", wraps=base._prepare_work) as prepare:
            first = view._prepare_work()
            second = view._prepare_work()
            self.assertEqual(prepare.call_count, 1)
            pd.testing.assert_frame_equal(first, second)
            clear_cache()
            view._prepare_work()
            self.assertEqual(prepare.call_count, 2)

    def test_only_changed_rows_are_saved(self):
        original = pd.DataFrame({
            "comunidades": ["Pavas", ""],
            "fecha_recurso_amparo": [pd.Timestamp("2026-09-01"), pd.NaT],
            "priorizacion_region": [1.0, None],
            "estado_sistema_ba": [None, 2.0],
            "idea_proyecto": ["A", "B"],
        }, index=pd.Index([10, 20], name="necesidad_id"))
        edited = original.copy()
        edited["fecha_recurso_amparo"] = [date(2026, 9, 1), None]
        edited["priorizacion_region"] = [1, pd.NA]
        edited.loc[20, "comunidades"] = None
        edited.loc[10, "idea_proyecto"] = "Columna derivada"
        self.assertTrue(view._changed_tracking_rows(edited, original).empty)
        edited.loc[20, "comunidades"] = "San Bosco"
        self.assertEqual(view._changed_tracking_rows(edited, original).index.tolist(), [20])

    def test_unique_population_counts_each_system_once(self):
        work = pd.DataFrame({"codigo_nombre_sistema": ["ME-A-01 Tres Ríos; MEA02 Guadalupe", "MEA01 Tres Ríos"]})
        total, codes, missing = view._unique_system_population(work)
        self.assertEqual(codes, ["MEA01", "MEA02"])
        self.assertEqual(missing, [])
        self.assertEqual(total, base.SYSTEM_DATA["MEA01"]["poblacion"] + base.SYSTEM_DATA["MEA02"]["poblacion"])

    def test_tipo_licitacion_follows_category_and_is_editable(self):
        category_index = view.DISPLAY_COLUMNS.index("categoria_clasificacion")
        self.assertEqual(view.DISPLAY_COLUMNS[category_index + 1], "tipo_licitacion")
        self.assertIn("tipo_licitacion", base.TRACKING_FIELDS)
        self.assertNotIn("tipo_licitacion", view.AUTOMATIC_COLUMNS)
        self.assertIn("tipo_licitacion", view._column_config())

    def test_app_filters_refresh_and_save_without_changes(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.session_state["vista_principal"] = "seguimiento_necesidades"
        app.run()
        self.assertEqual(list(app.exception), [])
        total = int(app.metric[0].value.replace(",", ""))
        self.assertGreater(total, 0)
        prepare = base._prepare_work
        app.multiselect(key="banco_filter_need_id").set_value([int(app.dataframe[0].value["id_necesidad"].iloc[0])]).run()
        self.assertEqual(app.metric[0].value, "1")
        app.multiselect(key="banco_filter_need_id").set_value([])
        app.text_input(key="banco_filter_text").set_value("zz_no_match_zz").run()
        self.assertEqual(app.metric[0].value, "0")
        app.text_input(key="banco_filter_text").set_value("").run()
        with patch.object(base, "_save_tracking") as save:
            next(b for b in app.button if b.label == "Guardar cambios de seguimiento").click().run()
            save.assert_not_called()
        first_id = int(app.dataframe[0].value.index[0])
        app.session_state["editor_banco_ideas_aya_v5"] = {
            "edited_rows": {0: {"comunidades": "Prueba de edición"}},
            "added_rows": [], "deleted_rows": [],
        }
        with patch.object(base, "_save_tracking") as save:
            next(b for b in app.button if b.label == "Guardar cambios de seguimiento").click().run()
            save.assert_called_once()
            self.assertEqual(save.call_args.args[0].index.tolist(), [first_id])
            self.assertEqual(save.call_args.args[0]["comunidades"].iloc[0], "Prueba de edición")
        revision = data_revision()
        app.button(key="banco_refresh_data").click().run()
        self.assertGreater(data_revision(), revision)
        self.assertIs(base._prepare_work, prepare)
        self.assertEqual(int(app.metric[0].value.replace(",", "")), total)
        self.assertEqual(list(app.exception), [])


if __name__ == "__main__":
    unittest.main()
