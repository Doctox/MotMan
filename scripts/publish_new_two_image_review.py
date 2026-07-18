"""Append the two owner-approved six-image grids to the active catalog."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

from grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "src/data/grid.catalog.json"
STAGING = ROOT / "src/data/grid-generation-handcrafted/new-two-image-rich.review.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
EXPECTED_IDS = ("image-rich-review-02", "image-rich-review-03")
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


def gameplay_signature(grid: dict) -> dict:
    return {
        "id": grid.get("id"),
        "columns": grid.get("columns"),
        "rows": grid.get("rows"),
        "clueCells": grid.get("clueCells"),
        "words": [{
            key: word.get(key)
            for key in (
                "answer", "clue", "image", "direction", "arrow",
                "clueCell", "cells",
            )
        } for word in grid.get("words", [])],
    }


def main() -> None:
    active = read(ACTIVE)
    staging = read(STAGING)
    staged = staging.get("grids", [])
    if tuple(grid.get("id") for grid in staged) != EXPECTED_IDS:
        raise SystemExit("Le staging ne contient pas exactement les deux grilles approuvées.")

    expected_by_id = {}
    staged_answers = []
    for grid in staged:
        grid_id = grid["id"]
        if (grid.get("columns"), grid.get("rows")) != (9, 10):
            raise SystemExit(f"{grid_id}: dimensions différentes de 9x10")
        images = sum(bool(word.get("image")) for word in grid.get("words", []))
        if images != 6:
            raise SystemExit(f"{grid_id}: {images} images au lieu de 6")
        topology = audit_grid_topology(grid, enforce_layout=False)
        if not topology["valid"]:
            raise SystemExit(f"{grid_id}: topologie invalide {topology['errorCounts']}")
        expected_by_id[grid_id] = runtime_record(grid)
        staged_answers.append({word["answer"] for word in grid["words"]})
    if staged_answers[0] & staged_answers[1]:
        raise SystemExit("Les deux grilles approuvées partagent une réponse.")

    existing = active.get("grids", [])
    additions = []
    repairs = 0
    for grid_id in EXPECTED_IDS:
        expected = expected_by_id[grid_id]
        current = next((grid for grid in existing if grid.get("id") == grid_id), None)
        if current is None:
            additions.append(expected)
        elif current != expected:
            if gameplay_signature(current) != gameplay_signature(expected):
                raise SystemExit(f"ID actif en conflit : {grid_id}")
            repairs += 1

    merged = [expected_by_id.get(grid.get("id"), grid) for grid in existing]
    merged.extend(additions)
    ids = [grid.get("id") for grid in merged]
    if len(ids) != len(set(ids)):
        raise SystemExit("Le catalogue fusionné contient des IDs dupliqués.")

    active["version"] = int(active.get("version", 0)) + int(bool(additions or repairs))
    active["selectionPolicy"] = "active-standard-plus-owner-approved"
    source = "src/data/grid-generation-handcrafted/new-two-image-rich.review.json"
    sources = list(active.get("additionalSources", []))
    if source not in sources:
        sources.append(source)
    active["additionalSources"] = sources
    active["grids"] = merged
    active["batchMetrics"] = {
        **active.get("batchMetrics", {}),
        "activeCatalogGrids": len(merged),
        "ownerApprovedImageRichGrids": 3,
    }

    feedback = read(BLACKLIST)
    reviews = list(feedback.get("positiveGridReviews", []))
    for grid_id in EXPECTED_IDS:
        review = {
            "gridId": grid_id,
            "rating": "positive",
            "difficultyFit": "motman-standard",
            "comment": (
                "Grille validée par le propriétaire le 2026-07-16 ; "
                "craft libre 9x10, six images et zéro lettre orpheline."
            ),
        }
        previous = next((item for item in reviews if item.get("gridId") == grid_id), None)
        if previous is not None and previous != review:
            raise SystemExit(f"Retour positif en conflit pour {grid_id}")
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
        "metadataRepairs": repairs,
        "total": len(merged),
        "version": active["version"],
        "ids": list(EXPECTED_IDS),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
