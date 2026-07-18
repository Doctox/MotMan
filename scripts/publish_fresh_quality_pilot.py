"""Publish the single fresh-quality grid explicitly approved by the owner.

The merge is append-only and idempotent. Existing catalog grids are preserved,
and a reused ID is accepted only if it still matches the reviewed staging grid.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

from grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "src/data/grid.catalog.json"
STAGING = ROOT / "src/data/grid-generation-handcrafted/fresh-quality-pilot.review.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
EXPECTED_ID = "fresh-quality-pilot-01"
APPROVED_ON = "2026-07-16"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, document: dict) -> None:
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def runtime_record(grid: dict) -> dict:
    result = copy.deepcopy(grid)
    result["publicationStatus"] = "owner-approved-runtime"
    result["manualReview"] = "owner-approved"
    result["approvedOn"] = APPROVED_ON
    for word in result["words"]:
        word["manualReview"] = "owner-approved"
    return result


def main() -> None:
    active = read(ACTIVE)
    staging = read(STAGING)
    reviewed = staging.get("grids", [])
    if len(reviewed) != 1 or reviewed[0].get("id") != EXPECTED_ID:
        raise SystemExit("Le staging ne contient pas uniquement la grille approuvée attendue.")

    grid = reviewed[0]
    if (grid.get("columns"), grid.get("rows")) != (9, 10):
        raise SystemExit(f"{EXPECTED_ID}: dimensions différentes de 9x10")
    topology = audit_grid_topology(grid)
    if not topology["valid"]:
        raise SystemExit(f"{EXPECTED_ID}: topologie invalide {topology['errorCounts']}")

    expected = runtime_record(grid)
    existing = active.get("grids", [])
    existing_by_id = {item.get("id"): item for item in existing}
    current = existing_by_id.get(EXPECTED_ID)
    if current is not None and current != expected:
        raise SystemExit(f"ID actif en conflit : {EXPECTED_ID}")
    additions = [] if current is not None else [expected]
    merged = [*existing, *additions]
    ids = [item.get("id") for item in merged]
    if len(ids) != len(set(ids)):
        raise SystemExit("Le catalogue fusionné contient des IDs dupliqués.")

    active["version"] = int(active.get("version", 0)) + (1 if additions else 0)
    active["selectionPolicy"] = "active-standard-plus-owner-approved"
    source = "src/data/grid-generation-handcrafted/fresh-quality-pilot.review.json"
    sources = list(active.get("additionalSources", []))
    if source not in sources:
        sources.append(source)
    active["additionalSources"] = sources
    active["grids"] = merged
    active["batchMetrics"] = {
        **active.get("batchMetrics", {}),
        "activeCatalogGrids": len(merged),
        "ownerApprovedFreshQualityGrids": 1,
    }

    feedback = read(BLACKLIST)
    reviews = list(feedback.get("positiveGridReviews", []))
    review = {
        "gridId": EXPECTED_ID,
        "rating": "positive",
        "difficultyFit": "motman-standard",
        "comment": (
            "Grille explicitement validée par le propriétaire le 2026-07-16; "
            "silhouette, couples et image approuvés pour le jeu."
        ),
    }
    previous = next((item for item in reviews if item.get("gridId") == EXPECTED_ID), None)
    if previous is not None and previous != review:
        raise SystemExit(f"Retour positif en conflit pour {EXPECTED_ID}")
    if previous is None:
        reviews.append(review)
    feedback["positiveGridReviews"] = reviews

    atomic_write(ACTIVE, active)
    atomic_write(BLACKLIST, feedback)
    print(json.dumps({
        "status": "published",
        "added": len(additions),
        "preserved": len(existing),
        "removed": 0,
        "total": len(merged),
        "version": active["version"],
        "ids": [EXPECTED_ID],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
