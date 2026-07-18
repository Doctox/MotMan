"""Publish the image-rich grid explicitly approved by the owner."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

from grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "src/data/grid.catalog.json"
STAGING = ROOT / "src/data/grid-generation-handcrafted/image-rich-checkpoint.review.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
EXPECTED_ID = "image-rich-review-01"
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
    """Fields whose change would alter the grid seen or solved by players."""
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
    grids = staging.get("grids", [])
    if len(grids) != 1 or grids[0].get("id") != EXPECTED_ID:
        raise SystemExit("Le staging ne contient pas uniquement la grille approuvée.")
    grid = grids[0]
    if (grid.get("columns"), grid.get("rows")) != (9, 10):
        raise SystemExit(f"{EXPECTED_ID}: dimensions différentes de 9x10")
    if sum(bool(word.get("image")) for word in grid["words"]) < 3:
        raise SystemExit(f"{EXPECTED_ID}: moins de trois indices-images")
    topology = audit_grid_topology(grid)
    if not topology["valid"]:
        raise SystemExit(f"{EXPECTED_ID}: topologie invalide {topology['errorCounts']}")

    expected = runtime_record(grid)
    existing = active.get("grids", [])
    current = next((item for item in existing if item.get("id") == EXPECTED_ID), None)
    repairs = 0
    if current is not None and current != expected:
        if gameplay_signature(current) != gameplay_signature(expected):
            raise SystemExit(f"ID actif en conflit : {EXPECTED_ID}")
        repairs = 1
    additions = [] if current is not None else [expected]
    merged = [
        expected if item.get("id") == EXPECTED_ID else item
        for item in existing
    ]
    merged.extend(additions)
    ids = [item.get("id") for item in merged]
    if len(ids) != len(set(ids)):
        raise SystemExit("Le catalogue fusionné contient des IDs dupliqués.")

    active["version"] = int(active.get("version", 0)) + int(bool(additions or repairs))
    active["selectionPolicy"] = "active-standard-plus-owner-approved"
    source = "src/data/grid-generation-handcrafted/image-rich-checkpoint.review.json"
    sources = list(active.get("additionalSources", []))
    if source not in sources:
        sources.append(source)
    active["additionalSources"] = sources
    active["grids"] = merged
    active["batchMetrics"] = {
        **active.get("batchMetrics", {}),
        "activeCatalogGrids": len(merged),
        "ownerApprovedImageRichGrids": 1,
    }

    feedback = read(BLACKLIST)
    reviews = list(feedback.get("positiveGridReviews", []))
    review = {
        "gridId": EXPECTED_ID,
        "rating": "positive",
        "difficultyFit": "motman-standard",
        "comment": (
            "Grille validée par le propriétaire le 2026-07-16 ; trois images, "
            "topologie et couples approuvés. Demande de réduire les petits mots "
            "dans les prochaines grilles."
        ),
    }
    previous = next((item for item in reviews if item.get("gridId") == EXPECTED_ID), None)
    if previous is not None and previous != review:
        raise SystemExit(f"Retour positif en conflit pour {EXPECTED_ID}")
    if previous is None:
        reviews.append(review)
    feedback["positiveGridReviews"] = reviews

    # MUR was absent from the active catalog before this publication, but the
    # owner remembers seeing it in older maps. Keep the approved occurrence and
    # put the answer on global cooldown so it cannot recur in future batches.
    cooldown = list(feedback.get("rotationCooldownAnswers", []))
    mur_record = {
        "answer": "MUR",
        "observedActiveUses": 1,
        "reason": "vigilance propriétaire : impression de répétition dans d'anciennes cartes",
        "addedOn": APPROVED_ON,
    }
    previous_mur = next((item for item in cooldown if item.get("answer") == "MUR"), None)
    if previous_mur is None:
        cooldown.append(mur_record)
    feedback["rotationCooldownAnswers"] = cooldown

    atomic_write(ACTIVE, active)
    atomic_write(BLACKLIST, feedback)
    print(json.dumps({
        "status": "published",
        "added": len(additions),
        "preserved": len(existing),
        "removed": 0,
        "provenanceRepairs": repairs,
        "total": len(merged),
        "version": active["version"],
        "ids": [EXPECTED_ID],
        "murActiveBeforePublish": 0,
        "murCooldownAdded": previous_mur is None,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
