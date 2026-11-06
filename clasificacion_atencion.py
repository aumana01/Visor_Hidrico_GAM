"""Dominio único para clasificación de la atención de necesidades.

Se mantienen los valores institucionales vigentes y se homologan las etiquetas
históricas en lectura, edición, importación y filtros.
"""
from __future__ import annotations

import unicodedata

DOMINIO_ATENCION = [
    "Lo puede atender GAM",
    "Requiere apoyo de otras dependencias",
    "Ambos",
    "Sin clasificar",
]


def normalizar_atencion(value: object) -> str:
    """Devuelve exclusivamente una de las cuatro clasificaciones permitidas."""
    if value is None:
        return "Sin clasificar"
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "<na>", "nat", "null"}:
        return "Sin clasificar"
    key = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    key = " ".join(key.casefold().split())
    if key in {"lo puede atender gam", "lo puede atender el gam"}:
        return "Lo puede atender GAM"
    if key in {
        "requiere apoyo de otras dependencias",
        "se requiere apoyo de otras dependencias",
    }:
        return "Requiere apoyo de otras dependencias"
    if key == "ambos":
        return "Ambos"
    return "Sin clasificar"
