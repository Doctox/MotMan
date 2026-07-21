#!/usr/bin/env python3
"""Publie uniquement les grilles 7x8 explicitement validées par le propriétaire."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from build_compact_7x8_review import family_key
from grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "src/data/grid.catalog.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
STAGING = ROOT / "output/quality/compact-7x8-pop-owner-review-staging.json"
SNAPSHOT = (
    ROOT
    / "src/data/grid-generation-handcrafted/compact-7x8-owner-approved-20260719.json"
)

APPROVED_SOURCE_IDS = {
    "compact-7x8-pop-owner-01",
    "compact-7x8-pop-owner-02",
    "compact-7x8-pop-owner-03",
    "compact-7x8-pop-owner-04",
    "compact-7x8-pop-owner-05",
    "compact-7x8-pop-owner-06",
    "compact-7x8-pop-owner-07",
    "compact-7x8-pop-owner-09",
    "compact-7x8-pop-owner-10",
}
REJECTED_SOURCE_IDS = {"compact-7x8-pop-owner-08"}
GRAMMAR_FILLERS = {"IL", "ON", "TON", "TA", "MA", "LUI", "SE", "CE", "CA"}


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def publication_grid(staged: dict) -> dict:
    published = copy.deepcopy(staged)
    published_id = str(staged["sourceGridId"])
    published["id"] = published_id
    published["sourceReviewId"] = staged["id"]
    published["publicationStatus"] = "owner-approved"
    published["ownerReview"] = {
        "status": "accepted",
        "reviewedOn": "2026-07-19",
        "profile": "motman-standard",
    }
    published.pop("catalogModified", None)
    for number, word in enumerate(published["words"], 1):
        word["wordId"] = f"{published_id}:word:{number:02d}"
        word["editorialStatus"] = "owner-approved"
    return published


def candidate_errors(grid: dict, blacklist: dict) -> list[str]:
    errors: list[str] = []
    report = audit_grid_topology(grid, enforce_layout=False)
    if not report["valid"] or report["orphanSegments"]:
        errors.append(f"topologie invalide: {report['errorCounts']}")
    if (grid.get("columns"), grid.get("rows")) != (7, 8):
        errors.append("dimensions autres que 7x8")
    image_count = sum(bool(word.get("image")) for word in grid["words"])
    minimum_images = int(grid.get("minimumImages", 4))
    if not minimum_images <= image_count <= 6:
        errors.append(f"nombre d'images hors plage: {image_count}")

    rejected_answers = set(blacklist.get("rejectedAnswers", []))
    rejected_pairs = {
        (str(item.get("answer", "")), str(item.get("clue", "")))
        for item in blacklist.get("rejectedPairs", [])
    }
    answers = {word["answer"] for word in grid["words"]}
    blocked_answers = sorted(answers & rejected_answers)
    if blocked_answers:
        errors.append(f"réponses blacklistées: {blocked_answers}")
    blocked_pairs = sorted(
        (word["answer"], word.get("clue", ""))
        for word in grid["words"]
        if (word["answer"], word.get("clue", "")) in rejected_pairs
    )
    if blocked_pairs:
        errors.append(f"couples blacklistés: {blocked_pairs}")
    for item in blacklist.get("rejectedCooccurrences", []):
        group = set(item.get("answers", []))
        if group and group <= answers:
            errors.append(f"cooccurrence blacklistée: {sorted(group)}")
    return errors


def prepare_publication(active: dict, staging: dict, blacklist: dict) -> tuple[dict, dict]:
    staged_by_source = {
        str(grid.get("sourceGridId")): grid for grid in staging.get("grids", [])
    }
    expected = APPROVED_SOURCE_IDS
    if set(staged_by_source) != expected:
        raise ValueError(
            "Le staging ne contient pas exactement les neuf grilles validées: "
            f"{sorted(set(staged_by_source) ^ expected)}"
        )

    existing = copy.deepcopy(active.get("grids", []))
    existing_ids = {str(grid.get("id")) for grid in existing}
    already_published = APPROVED_SOURCE_IDS & existing_ids
    if already_published:
        if already_published == APPROVED_SOURCE_IDS:
            return copy.deepcopy(active), {
                "status": "already-published",
                "added": 0,
                "total": len(existing),
                "version": active.get("version"),
            }
        raise ValueError(f"Publication partielle détectée: {sorted(already_published)}")

    additions = [
        publication_grid(staged_by_source[source_id])
        for source_id in sorted(APPROVED_SOURCE_IDS)
    ]
    for grid in additions:
        errors = candidate_errors(grid, blacklist)
        if errors:
            raise ValueError(f"{grid['id']}: {'; '.join(errors)}")

    seen_answers: dict[str, str] = {}
    seen_families: dict[str, tuple[str, str]] = {}
    for grid in [*existing, *additions]:
        for word in grid["words"]:
            answer = word["answer"]
            previous = seen_answers.get(answer)
            if previous and grid["id"] in APPROVED_SOURCE_IDS:
                raise ValueError(f"réponse répétée {answer}: {previous}, {grid['id']}")
            seen_answers.setdefault(answer, grid["id"])
            family = family_key(answer)
            previous_family = seen_families.get(family)
            if (
                previous_family
                and previous_family[1] != answer
                and grid["id"] in APPROVED_SOURCE_IDS
            ):
                raise ValueError(
                    f"famille répétée {family}: {previous_family}, {(grid['id'], answer)}"
                )
            seen_families.setdefault(family, (grid["id"], answer))

    published = copy.deepcopy(active)
    published["version"] = int(active.get("version", 0)) + 1
    published["source"] = (
        "src/data/grid-generation-handcrafted/"
        "compact-7x8-owner-approved-20260719.json"
    )
    published["grids"] = [*existing, *additions]
    published["publicationNote"] = (
        "19 grilles compactes 7x8 validées; neuf grilles ajoutées le 2026-07-19. "
        "La candidate 08 reste exclue à cause de la réponse VE."
    )

    topology_reports = [
        audit_grid_topology(grid, enforce_layout=False) for grid in published["grids"]
    ]
    published["batchMetrics"] = {
        "gridCount": len(published["grids"]),
        "columns": 7,
        "rows": 8,
        "letterCells": sum(
            sum(cell["kind"] == "letter" for cell in report["cells"])
            for report in topology_reports
        ),
        "answers": sum(len(grid["words"]) for grid in published["grids"]),
        "imageCount": sum(
            bool(word.get("image"))
            for grid in published["grids"]
            for word in grid["words"]
        ),
        "ownerApprovedBatchAdded": len(additions),
    }
    grammar_warnings = {
        grid["id"]: sorted(
            word["answer"] for word in grid["words"]
            if word["answer"] in GRAMMAR_FILLERS
        )
        for grid in additions
    }
    grammar_warnings = {
        grid_id: answers for grid_id, answers in grammar_warnings.items()
        if len(answers) >= 3
    }
    report = {
        "status": "published",
        "added": len(additions),
        "addedIds": [grid["id"] for grid in additions],
        "excludedIds": sorted(REJECTED_SOURCE_IDS),
        "preserved": len(existing),
        "total": len(published["grids"]),
        "version": published["version"],
        "grammarDensityWarnings": grammar_warnings,
        "lengthProfileAdded": dict(sorted(Counter(
            len(word["answer"]) for grid in additions for word in grid["words"]
        ).items())),
    }
    return published, report


def main() -> None:
    active = read(ACTIVE)
    staging = read(STAGING)
    blacklist = read(BLACKLIST)
    published, report = prepare_publication(active, staging, blacklist)
    if report["status"] == "published":
        snapshot = copy.deepcopy(published)
        snapshot["kind"] = "motman-compact-7x8-owner-approved-source"
        snapshot["catalogModified"] = False
        atomic_write(SNAPSHOT, snapshot)
        atomic_write(ACTIVE, published)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
