#!/usr/bin/env python3
"""Publish the seven compact grids explicitly approved on 2026-07-20."""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

from build_compact_7x8_review import family_key
from grid_topology import audit_grid_topology
from publish_compact_7x8_pop_owner_batch import atomic_write, candidate_errors, read


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "src/data/grid.catalog.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
STAGING = ROOT / "output/quality/compact-7x8-young-feedback-staging.json"
SNAPSHOT = (
    ROOT
    / "src/data/grid-generation-handcrafted/compact-7x8-young-owner-approved-20260720.json"
)

APPROVED_SOURCE_IDS = {
    "compact-7x8-young-balanced-02",
    "compact-7x8-young-balanced-04",
    "compact-7x8-young-balanced-06",
    "compact-7x8-young-balanced-07",
    "compact-7x8-young-balanced-08",
    "compact-7x8-young-balanced-09",
    "compact-7x8-young-feedback-replacement-01",
}
RETIRED_ACTIVE_IDS = {
    "compact-7x8-agent-f-03": "contient ETC, refusé explicitement par le propriétaire",
}
GRAMMAR_FILLERS = {"IL", "ON", "TON", "TA", "MA", "LUI", "SE", "CE", "CA"}


def publication_grid(staged: dict) -> dict:
    published = copy.deepcopy(staged)
    published_id = str(staged["sourceGridId"])
    published["id"] = published_id
    published["sourceReviewId"] = staged["id"]
    published["publicationStatus"] = "owner-approved"
    published["ownerReview"] = {
        "status": "accepted",
        "reviewedOn": "2026-07-20",
        "profile": "motman-standard-young-balanced",
    }
    published.pop("catalogModified", None)
    for number, word in enumerate(published["words"], 1):
        word["wordId"] = f"{published_id}:word:{number:02d}"
        word["editorialStatus"] = "owner-approved"
    return published


def prepare_publication(active: dict, staging: dict, blacklist: dict) -> tuple[dict, dict]:
    staged_by_source = {
        str(grid.get("sourceGridId")): grid for grid in staging.get("grids", [])
    }
    if set(staged_by_source) != APPROVED_SOURCE_IDS:
        raise ValueError(
            "Le staging ne contient pas exactement les sept grilles validées: "
            f"{sorted(set(staged_by_source) ^ APPROVED_SOURCE_IDS)}"
        )

    all_existing = copy.deepcopy(active.get("grids", []))
    retired_ids = sorted(
        str(grid.get("id"))
        for grid in all_existing
        if str(grid.get("id")) in RETIRED_ACTIVE_IDS
    )
    existing = [
        grid for grid in all_existing
        if str(grid.get("id")) not in RETIRED_ACTIVE_IDS
    ]
    existing_ids = {str(grid.get("id")) for grid in all_existing}
    already_published = APPROVED_SOURCE_IDS & existing_ids
    updated_ids: list[str] = []
    if already_published:
        if already_published == APPROVED_SOURCE_IDS:
            refreshed_by_id = {
                source_id: publication_grid(staged_by_source[source_id])
                for source_id in APPROVED_SOURCE_IDS
            }
            active_by_id = {
                str(grid.get("id")): grid for grid in existing
            }
            updated_ids = sorted(
                source_id for source_id, refreshed in refreshed_by_id.items()
                if active_by_id.get(source_id) != refreshed
            )
            if not retired_ids and not updated_ids:
                return copy.deepcopy(active), {
                    "status": "already-published",
                    "added": 0,
                    "updated": [],
                    "removed": [],
                    "total": len(existing),
                    "version": active.get("version"),
                }
            existing = [
                refreshed_by_id.get(str(grid.get("id")), grid)
                for grid in existing
            ]
            additions = []
        else:
            raise ValueError(f"Publication partielle détectée: {sorted(already_published)}")
    else:
        additions = [
            publication_grid(staged_by_source[source_id])
            for source_id in sorted(APPROVED_SOURCE_IDS)
        ]
    refreshed_grids = [
        grid for grid in existing if str(grid.get("id")) in updated_ids
    ]
    for grid in [*additions, *refreshed_grids]:
        errors = candidate_errors(grid, blacklist)
        if errors:
            raise ValueError(f"{grid['id']}: {'; '.join(errors)}")

    addition_answers: dict[str, str] = {}
    addition_families: dict[str, tuple[str, str]] = {}
    for grid in additions:
        for word in grid["words"]:
            answer = word["answer"]
            if answer in addition_answers:
                raise ValueError(
                    f"réponse répétée dans le lot {answer}: "
                    f"{addition_answers[answer]}, {grid['id']}"
                )
            addition_answers[answer] = grid["id"]
            family = family_key(answer)
            previous_family = addition_families.get(family)
            if previous_family and previous_family[1] != answer:
                raise ValueError(
                    f"famille répétée dans le lot {family}: "
                    f"{previous_family}, {(grid['id'], answer)}"
                )
            addition_families[family] = (grid["id"], answer)

    active_answers = {
        word["answer"]: grid["id"]
        for grid in existing
        for word in grid["words"]
    }
    active_families = {
        family_key(word["answer"]): (grid["id"], word["answer"])
        for grid in existing
        for word in grid["words"]
    }
    accepted_exact_repeats = sorted(
        {
            answer: {"activeGridId": active_answers[answer], "newGridId": grid_id}
            for answer, grid_id in addition_answers.items()
            if answer in active_answers
        }.items()
    )
    accepted_family_repeats = sorted(
        {
            family: {
                "active": active_families[family],
                "new": addition_families[family],
            }
            for family in addition_families
            if family in active_families
            and active_families[family][1] != addition_families[family][1]
        }.items()
    )

    for grid in additions:
        grid["ownerReview"]["acceptedExistingAnswerRepeats"] = sorted(
            word["answer"] for word in grid["words"]
            if word["answer"] in active_answers
        )

    published = copy.deepcopy(active)
    published["version"] = int(active.get("version", 0)) + 1
    published["source"] = (
        "src/data/grid-generation-handcrafted/"
        "compact-7x8-young-owner-approved-20260720.json"
    )
    published["grids"] = [*existing, *additions]
    published["publicationNote"] = (
        f"{len(published['grids'])} grilles compactes 7x8 validées; "
        "sept grilles validées par le propriétaire le 2026-07-20; "
        "compact-7x8-agent-f-03 retirée car elle contenait ETC."
    )

    topology_reports = [
        audit_grid_topology(grid, enforce_layout=False) for grid in published["grids"]
    ]
    if not all(report["valid"] for report in topology_reports):
        raise ValueError("Le catalogue final contient une topologie invalide")
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
        "updated": updated_ids,
        "removed": retired_ids,
        "removedReasons": {
            grid_id: RETIRED_ACTIVE_IDS[grid_id] for grid_id in retired_ids
        },
        "preserved": len(existing),
        "total": len(published["grids"]),
        "version": published["version"],
        "acceptedExactRepeats": dict(accepted_exact_repeats),
        "acceptedFamilyRepeats": dict(accepted_family_repeats),
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
        snapshot["kind"] = "motman-compact-7x8-young-owner-approved-source"
        snapshot["catalogModified"] = False
        atomic_write(SNAPSHOT, snapshot)
        atomic_write(ACTIVE, published)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
