"""Recalcula el catálogo territorial después de actualizar mapas o nombres."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import geo_necesidades  # noqa: E402,F401 -- configura mapas y nombres vigentes
import territorio_necesidades_v2 as territory  # noqa: E402


def main() -> None:
    crosswalk = territory.territorial_crosswalk(use_precomputed=False)
    if crosswalk.empty:
        raise RuntimeError("El geoproceso no produjo relaciones territoriales.")
    path = territory.base.GEO_DIR / "territorios_sistemas.csv"
    crosswalk.to_csv(path, index=False, encoding="utf-8", float_format="%.3f")
    manifest = {
        "algorithm": territory.ALGORITHM_VERSION,
        "threshold": territory.MIN_ADMIN_COVERAGE_PCT,
        "sources": territory.territorial_source_hashes(),
        "csv_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    path.with_suffix(".meta.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"Catálogo territorial generado: {len(crosswalk)} relaciones.")


if __name__ == "__main__":
    main()
