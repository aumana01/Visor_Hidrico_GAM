"""Pruebas de los criterios de ingreso y exclusión de proyectos PE de Vista 3.4."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd
import streamlit as st

from criterios_reagrupamiento import (
    RUTA_ESTRATEGICA, RUTA_OPERATIVA, RUTA_REVISION,
    clasificar_ruta_estrategica,
)
import reagrupamiento_mideplan_v2 as agrupamiento


class CriteriosReagrupamientoTests(unittest.TestCase):
    def test_solo_apoyo_externo_y_licitacion_mayor_ingresa_a_fichas(self):
        atenciones = [
            "Requiere apoyo de otras dependencias",
            "Lo puede atender GAM",
            "Ambos",
            "Sin clasificar",
        ]
        licitaciones = ["Licitación mayor", "Licitación menor", ""]
        for atencion in atenciones:
            for licitacion in licitaciones:
                with self.subTest(atencion=atencion, licitacion=licitacion):
                    route, _, _, _ = clasificar_ruta_estrategica(atencion, licitacion)
                    if (atencion, licitacion) == (
                        "Requiere apoyo de otras dependencias", "Licitación mayor"
                    ):
                        self.assertEqual(route, RUTA_ESTRATEGICA)
                    elif (atencion, licitacion) == (
                        "Lo puede atender GAM", "Licitación menor"
                    ):
                        self.assertEqual(route, RUTA_OPERATIVA)
                    else:
                        self.assertEqual(route, RUTA_REVISION)

    def test_normaliza_etiquetas_anteriores(self):
        route, _, atencion, licitacion = clasificar_ruta_estrategica(
            "Se requiere apoyo de otras dependencias", "Licitacion mayor"
        )
        self.assertEqual(route, RUTA_ESTRATEGICA)
        self.assertEqual(atencion, "Requiere apoyo de otras dependencias")
        self.assertEqual(licitacion, "Licitación mayor")

    def test_no_se_infiere_el_ingreso_desde_montos_de_costo(self):
        row = pd.Series({
            "tipo_licitacion": "",
            "responsabilidad_atencion": "Requiere apoyo de otras dependencias",
            "categoria_clasificacion": "Mejora en Almacenamiento",
            "idea_proyecto": "Construcción de un tanque",
            "descripcion_idea": "Nueva infraestructura de reserva",
        })
        raw = pd.Series({
            "costo": "CRC 2,000,000,000",
            "volumen_estimado_m3": 2000,
        })
        result = agrupamiento._classify_need(row, raw)
        self.assertEqual(result["route"], RUTA_REVISION)
        row["tipo_licitacion"] = "Licitación mayor"
        self.assertEqual(agrupamiento._classify_need(row, raw)["route"], RUTA_ESTRATEGICA)

    def test_lista_estrategica_no_incluye_operativos_ni_pendientes(self):
        # Evita geoprocesos pesados: se comprueba el motor con dos necesidades
        # idénticas, excepto los dos criterios de selección.
        data = pd.DataFrame([
            {
                "necesidad_id": 101, "id_necesidad": 101,
                "categoria_clasificacion": "Mejora en Almacenamiento",
                "idea_proyecto": "Nuevo tanque de almacenamiento",
                "descripcion_idea": "Tanque para reserva",
                "tipo_licitacion": "Licitación mayor",
                "responsabilidad_atencion": "Requiere apoyo de otras dependencias",
            },
            {
                "necesidad_id": 102, "id_necesidad": 102,
                "categoria_clasificacion": "Mejora en Almacenamiento",
                "idea_proyecto": "Mejorar tanque existente",
                "descripcion_idea": "Reparación menor",
                "tipo_licitacion": "Licitación menor",
                "responsabilidad_atencion": "Lo puede atender GAM",
            },
            {
                "necesidad_id": 103, "id_necesidad": 103,
                "categoria_clasificacion": "Mejora en Almacenamiento",
                "idea_proyecto": "Mejorar tanque auxiliar",
                "descripcion_idea": "Rehabilitación",
                "tipo_licitacion": "Licitación mayor",
                "responsabilidad_atencion": "Ambos",
            },
        ])
        raw = pd.DataFrame([
            {
                "id": 101, "costo": "", "responsabilidad_atencion": "Requiere apoyo de otras dependencias",
                "volumen_estimado_m3": 2000,
            },
            {
                "id": 102, "costo": "", "responsabilidad_atencion": "Lo puede atender GAM",
                "volumen_estimado_m3": 30,
            },
            {
                "id": 103, "costo": "", "responsabilidad_atencion": "Ambos",
                "volumen_estimado_m3": 50,
            },
        ])
        # El cálculo de dimensiones/territorio no es objeto de estas pruebas.
        with (
            patch.object(agrupamiento.base.seguimiento, "_prepare_work", return_value=data),
            patch.object(agrupamiento.base.seguimiento.base, "read_table", return_value=raw),
            patch.object(agrupamiento, "_build_project_row", side_effect=lambda rule, group, raw_by_id: {
                **agrupamiento._build_empty_project_row(rule),
                "ids_asociados": ", ".join(map(str, group["necesidad_id"].tolist())),
                "cantidad_necesidades": len(group),
            }),
        ):
            projects, trace = agrupamiento.build_groups()
        self.assertEqual(len(projects), 8)
        included = projects.loc[projects["cantidad_necesidades"].gt(0)]
        self.assertEqual(len(included), 1)
        self.assertEqual(included.iloc[0]["ids_asociados"], "101")
        self.assertEqual(set(trace["necesidad_id"]), {101, 102, 103})
        route_by_id = trace.set_index("necesidad_id")["ruta_modelo"].to_dict()
        self.assertEqual(route_by_id, {
            101: RUTA_ESTRATEGICA, 102: RUTA_OPERATIVA, 103: RUTA_REVISION,
        })


if __name__ == "__main__":
    unittest.main()
