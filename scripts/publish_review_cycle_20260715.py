"""Publish the three owner-approved July review grids without replacing v13."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "src/data/grid.catalog.json"
STAGING = ROOT / "src/data/grid-generation-handcrafted/review-cycle-20260715.staging.json"
AUDIT = ROOT / "output/quality/review-cycle-20260715-audit.json"
EXPECTED_IDS = {
    "review-20260715-01",
    "review-20260715-02",
    "review-20260715-03",
}


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    active = read(ACTIVE)
    staging = read(STAGING)
    audit = read(AUDIT)
    candidates = staging.get("grids", [])
    candidate_ids = {grid.get("id") for grid in candidates}
    if candidate_ids != EXPECTED_IDS:
        raise SystemExit(f"Lot inattendu : {sorted(candidate_ids)}")
    if not audit.get("valid") or audit.get("metrics", {}).get("grids") != 3:
        raise SystemExit("Publication bloquée : audit staging invalide.")
    if audit.get("metrics", {}).get("repeatedAnswersInsideCycle") != 0:
        raise SystemExit("Publication bloquée : répétition interne au lot.")

    promoted = []
    for source in candidates:
        report = audit_grid_topology(source, enforce_layout=False)
        if not report["valid"]:
            raise SystemExit(f"{source['id']}: topologie invalide")
        grid = copy.deepcopy(source)
        grid["publicationStatus"] = "owner-approved-active"
        grid["ownerApproval"] = "priority-3-20260717"
        for word in grid.get("words", []):
            word["manualReview"] = "owner-approved"
        promoted.append(grid)

    existing = {grid["id"]: grid for grid in active.get("grids", [])}
    for grid in promoted:
        existing[grid["id"]] = grid
    ordered = [
        *(grid for grid in active.get("grids", []) if grid["id"] not in EXPECTED_IDS),
        *promoted,
    ]
    active["version"] = max(14, int(active.get("version", 0)) + int(not EXPECTED_IDS.issubset(existing.keys())))
    active["selectionPolicy"] = "server-history-popularity-v1"
    active["publicationNote"] = "Trois grilles du cycle 20260715 approuvées pour la priorité 3."
    active["grids"] = ordered
    write(ACTIVE, active)
    print(json.dumps({
        "version": active["version"],
        "activeGrids": len(ordered),
        "published": sorted(EXPECTED_IDS),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
