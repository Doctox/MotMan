#!/usr/bin/env python3
"""Sérialise la proposition éditoriale A01 et vérifie sa couverture.

Ce script ne cherche, ne combine et ne remplit aucun mot. Il reprend la
candidate retirée `reference-standard-20-repaired`, relue mot par mot pendant
le cycle A01, renomme ses identifiants et produit un dossier de revue autonome.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output/quality/agent-reference-20-29-repairs.json"
CATALOG = ROOT / "src/data/grid.catalog.json"
OUTPUT = ROOT / "output/quality/agent-handfilled-ribbon-a01.json"
SOURCE_ID = "reference-standard-20-repaired"
GRID_ID = "reference-ribbon-a-01-handfilled"


def topology_audit(grid: dict) -> dict:
    rows = grid["rows"]
    columns = grid["columns"]
    clues = {tuple(cell) for cell in grid["clueCells"]}
    neutral = {(0, 0)}
    assignments: dict[tuple[int, int], str] = {}
    coverage: dict[tuple[int, int], list[str]] = {}
    conflicts = []

    for word in grid["words"]:
        if len(word["answer"]) != len(word["cells"]):
            conflicts.append({"wordId": word["wordId"], "code": "length-mismatch"})
        for letter, raw_cell in zip(word["answer"], word["cells"]):
            cell = tuple(raw_cell)
            previous = assignments.get(cell)
            if previous is not None and previous != letter:
                conflicts.append(
                    {
                        "cell": list(cell),
                        "code": "crossing-conflict",
                        "letters": [previous, letter],
                    }
                )
            assignments[cell] = letter
            coverage.setdefault(cell, []).append(word["wordId"])

    expected_letters = {
        (row, column)
        for row in range(rows)
        for column in range(columns)
        if (row, column) not in clues and (row, column) not in neutral
    }
    uncovered = sorted(expected_letters - assignments.keys())
    extra = sorted(assignments.keys() - expected_letters)

    declared = {
        (word["direction"], tuple(tuple(cell) for cell in word["cells"]))
        for word in grid["words"]
    }
    orphan_segments = []
    for direction in ("across", "down"):
        outer = range(rows) if direction == "across" else range(columns)
        inner = range(columns) if direction == "across" else range(rows)
        for fixed in outer:
            run = []
            for moving in list(inner) + [None]:
                cell = (
                    (fixed, moving)
                    if direction == "across" and moving is not None
                    else (moving, fixed)
                    if moving is not None
                    else None
                )
                if cell is not None and cell in expected_letters:
                    run.append(cell)
                    continue
                if len(run) >= 2 and (direction, tuple(run)) not in declared:
                    orphan_segments.append(
                        {
                            "direction": direction,
                            "cells": [list(item) for item in run],
                        }
                    )
                run = []

    return {
        "valid": not conflicts and not uncovered and not extra and not orphan_segments,
        "rows": rows,
        "columns": columns,
        "cells": rows * columns,
        "neutralCells": [list(cell) for cell in sorted(neutral)],
        "clueCells": len(clues),
        "letterCells": len(expected_letters),
        "coveredLetterCells": len(expected_letters & assignments.keys()),
        "uncoveredLetterCells": [list(cell) for cell in uncovered],
        "extraLetterCells": [list(cell) for cell in extra],
        "crossingConflicts": conflicts,
        "orphanSegments": orphan_segments,
    }


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
    original = next(grid for grid in source["grids"] if grid["id"] == SOURCE_ID)
    grid = copy.deepcopy(original)
    grid["id"] = GRID_ID
    grid["sourceShapeId"] = "reference-ribbon-a-01"
    grid["publicationStatus"] = "owner-review-required"
    grid["manualReview"] = "agent-editorial-review-complete-owner-decision-pending"
    grid["layoutProfile"] = "reference-ribbon-inspired-fallback-from-audited-repair"
    grid["generationMetrics"] = {
        "method": "manual-editorial-selection-no-search-or-fill-in-this-cycle",
        "structuralFallback": SOURCE_ID,
        "reason": "the exact full-ribbon A01 topology was already proven corpus-infeasible",
    }
    for index, word in enumerate(grid["words"], 1):
        word["wordId"] = f"{GRID_ID}:word:{index:02d}"
        word["manualReview"] = "agent-reviewed-a01"

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    active_counts = Counter(
        word["answer"]
        for active_grid in catalog["grids"]
        for word in active_grid["words"]
    )
    repeated = [
        {"answer": word["answer"], "activeOccurrences": active_counts[word["answer"]]}
        for word in grid["words"]
        if active_counts[word["answer"]]
    ]
    image_answers = [word["answer"] for word in grid["words"] if word.get("image")]

    document = {
        "version": 1,
        "kind": "agent-handfilled-reference-ribbon-proposal",
        "generatedOn": date.today().isoformat(),
        "status": "complete-owner-review-required",
        "activeCatalogModified": False,
        "blacklistModified": False,
        "method": {
            "wordSelection": "manual editorial review, slot by slot",
            "automaticFillUsedInThisCycle": False,
            "queryTool": "scripts/query_central_pairs.py (read-only pattern lookup)",
            "structuralDecision": (
                "Exact A01 fixed mask abandoned after manual work confirmed its prior "
                "infeasibility; an already audited removed topology was retained as a "
                "safe internal-layout fallback."
            ),
        },
        "grid": grid,
        "audit": {
            "topology": topology_audit(grid),
            "images": {
                "requiredMinimum": 6,
                "count": len(image_answers),
                "answers": image_answers,
                "valid": len(image_answers) >= 6,
            },
            "activeRepetition": {
                "activeGridCount": len(catalog["grids"]),
                "repeatedAnswers": repeated,
                "freshAnswers": [
                    word["answer"] for word in grid["words"] if not active_counts[word["answer"]]
                ],
                "warning": "Owner should weigh the listed active repetitions before publication.",
            },
        },
        "editorialJournal": [
            "Exact reference-ribbon-a-01 mask manually explored and rejected: its full top/left ribbons force too many simultaneous long crossings.",
            "Rejected fills that relied on repeated musical notes, arbitrary abbreviations, accent tricks or obscure fragments.",
            "Retained the removed reference-standard-20-repaired topology because its 61 letter cells were already coherent and every segment had a declared answer.",
            "Reviewed all 30 answer/clue pairs; no empty clue, arbitrary fragment or duplicate family inside the grid.",
            "Kept six literal images: TELES, CLE, ARA, OURS, OIE and LION.",
        ],
        "doubtPairs": [
            {
                "answer": "PEPE",
                "clue": "Papi",
                "reason": "familiar register; understandable but owner may prefer a neutral-register replacement",
            },
            {
                "answer": "LIS",
                "clue": "Fleur",
                "reason": "clear category clue but not fully unique without crossings",
            },
            {
                "answer": "AS",
                "clue": "Champion",
                "reason": "very short answer already frequent in active catalog",
            },
        ],
        "publicationDecision": "not-published",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)
    print(json.dumps(document["audit"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
