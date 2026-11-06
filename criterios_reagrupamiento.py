"""Criterios institucionales para decidir la ruta de las necesidades (Vista 3.4).

Solo se agrupan en proyectos estratégicos las iniciativas que, simultáneamente,
requieren apoyo de otras dependencias y tienen licitación mayor registrada
explícitamente en la Vista 3.3. No se deduce el procedimiento del costo.
"""
from __future__ import annotations

import unicodedata

from clasificacion_atencion import normalizar_atencion

RUTA_ESTRATEGICA = "Proyecto de inversion"
RUTA_OPERATIVA = "Atencion operativa"
RUTA_REVISION = "Pendiente de validacion"


def _normalizar_licitacion(value: object) -> str:
    text = "" if value is None else str(value).strip()
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    folded = " ".join(folded.casefold().split())
    if folded == "licitacion mayor":
        return "Licitación mayor"
    if folded == "licitacion menor":
        return "Licitación menor"
    return "Pendiente de definir"


def clasificar_ruta_estrategica(
    clasificacion_atencion: object,
    tipo_licitacion: object,
) -> tuple[str, str, str, str]:
    """Retorna ruta, explicación, atención normalizada y licitación normalizada."""
    atencion = normalizar_atencion(clasificacion_atencion)
    licitacion = _normalizar_licitacion(tipo_licitacion)

    if atencion == "Requiere apoyo de otras dependencias" and licitacion == "Licitación mayor":
        return (
            RUTA_ESTRATEGICA,
            "Cumple ambos criterios: requiere apoyo de otras dependencias y licitación mayor registrada en 3.3.",
            atencion,
            licitacion,
        )

    if atencion == "Lo puede atender GAM" and licitacion == "Licitación menor":
        return (
            RUTA_OPERATIVA,
            "Puede atenderse desde la operación GAM mediante licitación menor; no se agrupa en proyectos estratégicos.",
            atencion,
            licitacion,
        )

    if licitacion == "Pendiente de definir":
        reason = "Falta definir el tipo de licitación en la Vista 3.3."
    elif atencion == "Sin clasificar":
        reason = "Falta definir la clasificación de atención en la Vista 3.3."
    elif atencion == "Ambos":
        reason = "La clasificación «Ambos» requiere confirmar si la iniciativa debe ingresar a la cartera estratégica."
    elif atencion == "Requiere apoyo de otras dependencias":
        reason = "Requiere apoyo externo, pero no tiene licitación mayor: verificar la ruta de atención."
    else:
        reason = "La iniciativa no cumple simultáneamente los dos criterios de ingreso a proyectos estratégicos."
    return RUTA_REVISION, reason, atencion, licitacion
