"""Publish the five owner-approved central-priority 9x10 grids.

The merge is idempotent: every existing catalog record is preserved verbatim,
and an already-published ID is accepted only when its content still matches the
reviewed staging record.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "src/data/grid.catalog.json"
STAGING = ROOT / "src/data/grid-generation-handcrafted/central-priority-five.review.json"
EXPECTED_IDS = {f"central-priority-review-{number:02d}" for number in range(1, 6)}
RUNTIME_VERSION = 6


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def runtime_record(grid: dict) -> dict:
    result = copy.deepcopy(grid)
    result["publicationStatus"] = "owner-approved-runtime"
    result["manualReview"] = "owner-approved"
    result["approvedOn"] = "2026-07-15"
    for word in result["words"]:
        word["manualReview"] = "owner-approved"
    return result


def main() -> None:
    active = read(ACTIVE)
    staging = read(STAGING)
    reviewed = staging.get("grids", [])
    reviewed_ids = {grid.get("id") for grid in reviewed}
    if reviewed_ids != EXPECTED_IDS or len(reviewed) != len(EXPECTED_IDS):
        raise SystemExit(f"Lot approuvé incomplet ou inattendu : {sorted(reviewed_ids)}")

    additions = []
    existing = active.get("grids", [])
    existing_by_id = {grid.get("id"): grid for grid in existing}
    for reviewed_grid in reviewed:
        if (reviewed_grid.get("columns"), reviewed_grid.get("rows")) != (9, 10):
            raise SystemExit(f"{reviewed_grid['id']}: dimensions différentes de 9x10")
        topology = audit_grid_topology(reviewed_grid)
        if not topology["valid"]:
            raise SystemExit(
                f"{reviewed_grid['id']}: topologie invalide {topology['errorCounts']}"
            )
        expected = runtime_record(reviewed_grid)
        current = existing_by_id.get(reviewed_grid["id"])
        if current is not None:
            if current != expected:
                raise SystemExit(f"ID actif en conflit : {reviewed_grid['id']}")
            continue
        additions.append(expected)

    merged = [*existing, *additions]
    merged_ids = [grid.get("id") for grid in merged]
    if len(merged_ids) != len(set(merged_ids)):
        raise SystemExit("Le catalogue fusionné contient des IDs dupliqués.")

    active["version"] = max(
        int(active.get("version", 0)) + (1 if additions else 0),
        RUNTIME_VERSION,
    )
    active["selectionPolicy"] = "active-standard-plus-owner-approved"
    sources = list(active.get("additionalSources", []))
    source = "src/data/grid-generation-handcrafted/central-priority-five.review.json"
    if source not in sources:
        sources.append(source)
    active["additionalSources"] = sources
    active["grids"] = merged
    active["batchMetrics"] = {
        **active.get("batchMetrics", {}),
        "activeCatalogGrids": len(merged),
        "ownerApprovedCentralPriorityGrids": len(EXPECTED_IDS),
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
