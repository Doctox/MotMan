"""Append the five owner-approved 9x10 grids to the active runtime catalog.

Existing grids and identifiers are preserved verbatim.  Re-running the script
is idempotent and never duplicates the approved grids.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "src/data/grid.catalog.json"
STAGING = ROOT / "src/data/grid-generation-handcrafted/corpus-aware-five.review.json"
EXPECTED_IDS = {f"corpus-aware-review-{number:02d}" for number in range(1, 6)}
RUNTIME_VERSION = 5


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    active = read(ACTIVE)
    staging = read(STAGING)
    additions = copy.deepcopy(staging.get("grids", []))
    addition_ids = {grid.get("id") for grid in additions}
    if addition_ids != EXPECTED_IDS or len(additions) != len(EXPECTED_IDS):
        raise SystemExit(f"Lot approuvé incomplet ou inattendu : {sorted(addition_ids)}")
    if staging.get("batchMetrics", {}).get("repeatedAnswersInsideBatch") != 0:
        raise SystemExit("Le lot approuvé contient des réponses répétées.")
    if staging.get("batchMetrics", {}).get("singularPluralFamiliesInsideBatch") != 0:
        raise SystemExit("Le lot approuvé contient une famille singulier/pluriel répétée.")

    existing = active.get("grids", [])
    existing_by_id = {grid.get("id"): grid for grid in existing}
    conflicting = sorted(EXPECTED_IDS & existing_by_id.keys())
    if conflicting:
        # Idempotence is allowed only when the active record is exactly the
        # already-published approved record.
        for grid in additions:
            current = existing_by_id.get(grid["id"])
            if current is None:
                continue
            expected = copy.deepcopy(grid)
            expected["publicationStatus"] = "owner-approved-runtime"
            expected["manualReview"] = "owner-approved"
            expected["approvedOn"] = "2026-07-15"
            for word in expected["words"]:
                word["manualReview"] = "owner-approved"
            if current != expected:
                raise SystemExit(f"ID actif en conflit : {grid['id']}")
        additions = [grid for grid in additions if grid["id"] not in existing_by_id]

    for grid in additions:
        if (grid.get("columns"), grid.get("rows")) != (9, 10):
            raise SystemExit(f"{grid['id']}: dimensions différentes de 9x10")
        topology = audit_grid_topology(grid)
        if not topology["valid"]:
            raise SystemExit(f"{grid['id']}: topologie invalide {topology['errorCounts']}")
        grid["publicationStatus"] = "owner-approved-runtime"
        grid["manualReview"] = "owner-approved"
        grid["approvedOn"] = "2026-07-15"
        for word in grid["words"]:
            word["manualReview"] = "owner-approved"

    merged = [*existing, *additions]
    merged_ids = [grid.get("id") for grid in merged]
    if len(merged_ids) != len(set(merged_ids)):
        raise SystemExit("Le catalogue fusionné contient des IDs dupliqués.")
    for grid in merged:
        topology = audit_grid_topology(grid)
        # Quarantined legacy records remain preserved but are intentionally
        # filtered by gridCatalogPolicy at runtime.
        if grid.get("id") in EXPECTED_IDS and not topology["valid"]:
            raise SystemExit(f"La grille publiée {grid['id']} est devenue invalide.")

    active["version"] = max(int(active.get("version", 0)) + (1 if additions else 0), RUNTIME_VERSION)
    active["selectionPolicy"] = "active-standard-plus-owner-approved"
    sources = list(active.get("additionalSources", []))
    source = "src/data/grid-generation-handcrafted/corpus-aware-five.review.json"
    if source not in sources:
        sources.append(source)
    active["additionalSources"] = sources
    active["grids"] = merged
    active["batchMetrics"] = {
        **active.get("batchMetrics", {}),
        "activeCatalogGrids": len(merged),
        "ownerApprovedCorpusAwareGrids": len(EXPECTED_IDS),
    }
    ACTIVE.write_text(
        json.dumps(active, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "published",
        "added": len(additions),
        "preserved": len(existing),
        "total": len(merged),
        "version": active["version"],
        "ids": sorted(EXPECTED_IDS),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
