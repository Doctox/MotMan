"""Publish the three owner-approved repetition renovations atomically."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

from grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "src/data/grid.catalog.json"
STAGING = ROOT / "src/data/grid-generation-handcrafted/repetition-renovation.review.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
APPROVED_ON = "2026-07-16"
EXPECTED_REPLACEMENTS = {
    "reference-standard-26": "repetition-renovation-26",
    "reference-standard-09": "repetition-renovation-09",
    "reference-standard-19": "repetition-renovation-19",
}


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


def prepare_publication(active: dict, staging: dict, feedback: dict) -> tuple[dict, dict, dict]:
    staged = staging.get("grids", [])
    staged_mapping = {
        grid.get("replacesGridId"): grid.get("id")
        for grid in staged
    }
    if staged_mapping != EXPECTED_REPLACEMENTS or len(staged) != 3:
        raise ValueError("Le staging ne contient pas exactement les trois remplacements approuves.")
    if staging.get("metrics", {}).get("replacements") != 7:
        raise ValueError("Le staging ne contient pas les sept corrections relues.")

    expected_by_old_id: dict[str, dict] = {}
    for grid in staged:
        grid_id = grid["id"]
        old_id = grid["replacesGridId"]
        if (grid.get("columns"), grid.get("rows")) != (9, 10):
            raise ValueError(f"{grid_id}: dimensions differentes de 9x10")
        if grid.get("publicationStatus") != "owner-review-required":
            raise ValueError(f"{grid_id}: statut de revue inattendu")
        images = sum(bool(word.get("image")) for word in grid.get("words", []))
        if images != 6:
            raise ValueError(f"{grid_id}: {images} images au lieu de 6")
        if any(not str(word.get("clue", "")).strip() and not word.get("image") for word in grid.get("words", [])):
            raise ValueError(f"{grid_id}: indice vide sans image")
        topology = audit_grid_topology(grid, enforce_layout=False)
        if not topology["valid"] or topology["orphanSegments"]:
            raise ValueError(f"{grid_id}: topologie invalide {topology['errorCounts']}")
        expected_by_old_id[old_id] = runtime_record(grid)

    published = copy.deepcopy(active)
    existing = published.get("grids", [])
    ids = [grid.get("id") for grid in existing]
    if len(ids) != len(set(ids)):
        raise ValueError("Le catalogue actif contient des IDs dupliques.")

    replacements = 0
    metadata_repairs = 0
    merged: list[dict] = []
    for current in existing:
        old_id = current.get("id")
        if old_id in expected_by_old_id:
            expected = expected_by_old_id[old_id]
            if expected["id"] in ids:
                raise ValueError(f"Les deux versions sont deja actives : {old_id}")
            merged.append(expected)
            replacements += 1
        else:
            merged.append(current)

    for old_id, new_id in EXPECTED_REPLACEMENTS.items():
        if old_id in ids:
            continue
        current = next((grid for grid in merged if grid.get("id") == new_id), None)
        if current is None:
            raise ValueError(f"Grille source absente : {old_id}")
        expected = expected_by_old_id[old_id]
        if gameplay_signature(current) != gameplay_signature(expected):
            raise ValueError(f"ID renove en conflit : {new_id}")
        if current != expected:
            merged[merged.index(current)] = expected
            metadata_repairs += 1

    merged_ids = [grid.get("id") for grid in merged]
    if len(merged_ids) != len(set(merged_ids)):
        raise ValueError("Le catalogue fusionne contient des IDs dupliques.")
    if len(merged) != len(existing):
        raise ValueError("Le remplacement doit conserver le nombre de grilles.")

    changed = bool(replacements or metadata_repairs)
    published["version"] = int(published.get("version", 0)) + int(changed)
    published["selectionPolicy"] = "active-standard-plus-owner-approved"
    source = "src/data/grid-generation-handcrafted/repetition-renovation.review.json"
    sources = list(published.get("additionalSources", []))
    if source not in sources:
        sources.append(source)
    published["additionalSources"] = sources
    published["grids"] = merged
    published["batchMetrics"] = {
        **published.get("batchMetrics", {}),
        "activeCatalogGrids": len(merged),
        "repetitionRenovatedGrids": 3,
        "repetitionSlotsRemoved": 7,
    }

    updated_feedback = copy.deepcopy(feedback)
    reviews = list(updated_feedback.get("positiveGridReviews", []))
    for old_id, new_id in EXPECTED_REPLACEMENTS.items():
        review = {
            "gridId": new_id,
            "rating": "positive",
            "difficultyFit": "motman-standard",
            "comment": (
                f"Remplace {old_id}; renovation anti-repetition validee par "
                "le proprietaire le 2026-07-16, avec six images."
            ),
        }
        previous = next((item for item in reviews if item.get("gridId") == new_id), None)
        if previous is not None and previous != review:
            raise ValueError(f"Retour positif en conflit pour {new_id}")
        if previous is None:
            reviews.append(review)
    updated_feedback["positiveGridReviews"] = reviews

    report = {
        "status": "published" if changed else "already-published",
        "replaced": replacements,
        "metadataRepairs": metadata_repairs,
        "preserved": len(merged) - replacements,
        "removedIds": list(EXPECTED_REPLACEMENTS),
        "addedIds": list(EXPECTED_REPLACEMENTS.values()),
        "total": len(merged),
        "version": published["version"],
    }
    return published, updated_feedback, report


def main() -> None:
    published, feedback, report = prepare_publication(
        read(ACTIVE), read(STAGING), read(BLACKLIST)
    )
    atomic_write(ACTIVE, published)
    atomic_write(BLACKLIST, feedback)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
