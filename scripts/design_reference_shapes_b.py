"""Design three reference-style 9x10 arrowword topologies.

The grammar intentionally does not reuse the historical MotMan masks.  It uses
a complete top/left clue border, long crossing bands and only a handful of
internal cells that can each carry both a right and a down clue.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from hotspot_mutate_b import maximal_runs, topology_errors
from motsflex_adapter_b import derive_slots

ROWS = 10
COLUMNS = 9
ACTIVE_REJECTION = 0.72
NEW_SHAPE_REJECTION = 0.76


def slot_signatures_from_grid(grid: dict):
    return {
        (word.get("direction"), tuple(map(tuple, word.get("cells", []))))
        for word in grid.get("words", [])
        if word.get("direction") in {"across", "down"}
    }


def slot_signatures_from_clues(clues):
    return {(slot.direction, tuple(slot.cells)) for slot in derive_slots(clues)}


def slot_profile(signatures):
    counts = Counter((direction, len(cells)) for direction, cells in signatures)
    return [counts[(direction, length)] for direction in ("across", "down") for length in range(2, 10)]


def cosine(left, right):
    dot = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return dot / denominator if denominator else 0.0


def shape_similarity(left_clues, left_slots, right_clues, right_slots):
    clue_union = left_clues | right_clues
    clue_jaccard = len(left_clues & right_clues) / max(1, len(clue_union))
    slot_union = left_slots | right_slots
    slot_jaccard = len(left_slots & right_slots) / max(1, len(slot_union))
    mask_agreement = 1 - len(left_clues ^ right_clues) / (ROWS * COLUMNS)
    profile_cosine = cosine(slot_profile(left_slots), slot_profile(right_slots))
    score = (
        0.40 * clue_jaccard
        + 0.30 * slot_jaccard
        + 0.15 * mask_agreement
        + 0.15 * profile_cosine
    )
    return {
        "score": round(score, 6),
        "clueCellJaccard": round(clue_jaccard, 6),
        "slotPathJaccard": round(slot_jaccard, 6),
        "maskAgreement": round(mask_agreement, 6),
        "slotProfileCosine": round(profile_cosine, 6),
    }


def geometry_report(clues):
    slots = derive_slots(clues)
    coverage = defaultdict(list)
    words_by_clue = defaultdict(list)
    for index, slot in enumerate(slots):
        words_by_clue[slot.clue].append(index)
        for position, cell in enumerate(slot.cells):
            coverage[cell].append({
                "slot": index,
                "direction": slot.direction,
                "position": position,
            })
    letters = {(row, col) for row in range(ROWS) for col in range(COLUMNS)} - clues
    uncovered = sorted(cell for cell in letters if not coverage[cell])
    overcovered = sorted(cell for cell in letters if len(coverage[cell]) > 2)
    orphan_segments = []
    declared = {
        direction: {tuple(slot.cells) for slot in slots if slot.direction == direction}
        for direction in ("across", "down")
    }
    for direction in ("across", "down"):
        for run in maximal_runs(clues, direction):
            if len(run) >= 2 and run not in declared[direction]:
                orphan_segments.append({"direction": direction, "cells": [list(cell) for cell in run]})
    ambiguous_arrows = []
    for index, slot in enumerate(slots):
        dr, dc = ((0, 1) if slot.direction == "across" else (1, 0))
        expected = (slot.clue[0] + dr, slot.clue[1] + dc)
        if not slot.cells or slot.cells[0] != expected:
            ambiguous_arrows.append(index)
    isolated_clues = sorted(clues - {(0, 0)} - set(words_by_clue))
    lengths = Counter(len(slot.cells) for slot in slots)
    double_clues = sorted(clue for clue, owners in words_by_clue.items() if len(owners) == 2)
    long_slots = [index for index, slot in enumerate(slots) if len(slot.cells) >= 5]
    return {
        "valid": not topology_errors(clues) and not uncovered and not overcovered
                 and not orphan_segments and not ambiguous_arrows and not isolated_clues,
        "errors": topology_errors(clues),
        "letterCells": len(letters),
        "coveredLetterCells": len(letters) - len(uncovered),
        "coverageRatio": round((len(letters) - len(uncovered)) / max(1, len(letters)), 6),
        "uncoveredCells": [list(cell) for cell in uncovered],
        "overcoveredCells": [list(cell) for cell in overcovered],
        "orphanSegments": orphan_segments,
        "ambiguousArrows": ambiguous_arrows,
        "isolatedClues": [list(cell) for cell in isolated_clues],
        "slotCount": len(slots),
        "slotLengths": {str(length): count for length, count in sorted(lengths.items())},
        "longSlotsAtLeast5": len(long_slots),
        "longSlotRatio": round(len(long_slots) / max(1, len(slots)), 6),
        "doubleClueCells": [list(cell) for cell in double_clues],
        "doubleClueCount": len(double_clues),
        "singleCoverageCells": sum(len(owners) == 1 for owners in coverage.values()),
        "crossedCells": sum(len(owners) == 2 for owners in coverage.values()),
    }


def style_score(report):
    lengths = {int(key): value for key, value in report["slotLengths"].items()}
    short_penalty = 1.8 * lengths.get(2, 0) + 0.45 * lengths.get(3, 0)
    return round(
        30 * report["longSlotRatio"]
        + 0.8 * report["longSlotsAtLeast5"]
        + 0.9 * report["doubleClueCount"]
        - short_penalty,
        6,
    )


def serialise_shape(shape_id, clues, report, nearest, active_scores, pairwise):
    slots = derive_slots(clues)
    return {
        "id": shape_id,
        "columns": COLUMNS,
        "rows": ROWS,
        "grammar": "complete-top-left-border-long-crossing-bands-sparse-internal-double-clues",
        "clueCells": [list(cell) for cell in sorted(clues)],
        "internalClueCells": [list(cell) for cell in sorted(clues) if cell[0] > 0 and cell[1] > 0],
        "slots": [
            {
                "slotId": f"{shape_id}:slot:{index + 1:02d}",
                "direction": slot.direction,
                "arrow": slot.arrow,
                "clueCell": list(slot.clue),
                "cells": [list(cell) for cell in slot.cells],
                "length": len(slot.cells),
            }
            for index, slot in enumerate(slots)
        ],
        "geometryAudit": report,
        "styleScore": style_score(report),
        "nearestActiveGrid": nearest,
        "topFiveActiveSimilarities": active_scores[:5],
        "pairwiseNewShapeSimilarities": pairwise,
        "accepted": report["valid"] and nearest["similarity"]["score"] < ACTIVE_REJECTION,
    }


def main():
    catalog = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    blacklist = json.loads((ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8"))
    quarantined = set(blacklist.get("quarantinedGridIds", []))
    active = [
        grid for grid in catalog["grids"]
        if grid["id"] not in quarantined
        and (grid.get("columns", grid.get("size")), grid.get("rows", grid.get("size"))) == (9, 10)
    ]
    active_shapes = [
        (grid["id"], set(map(tuple, grid["clueCells"])), slot_signatures_from_grid(grid))
        for grid in active
    ]

    border = {(0, col) for col in range(COLUMNS)} | {(row, 0) for row in range(ROWS)}
    # Internal double clues stay far enough from every edge to leave at least
    # two visible answer cells on both sides of a split.
    internal_positions = [(row, col) for row in range(3, 8) for col in range(3, 7)]
    candidates = []
    rejected = Counter()
    for internal_count in (3, 4, 5):
        for internal in itertools.combinations(internal_positions, internal_count):
            clues = border | set(internal)
            report = geometry_report(clues)
            if not report["valid"]:
                rejected["invalid-geometry"] += 1
                continue
            if report["doubleClueCount"] < 3:
                rejected["insufficient-double-clues"] += 1
                continue
            if report["longSlotRatio"] < 0.42:
                rejected["insufficient-long-bands"] += 1
                continue
            slots = slot_signatures_from_clues(clues)
            similarities = []
            for active_id, active_clues, active_slots in active_shapes:
                similarities.append({
                    "gridId": active_id,
                    "similarity": shape_similarity(clues, slots, active_clues, active_slots),
                })
            similarities.sort(key=lambda item: item["similarity"]["score"], reverse=True)
            if similarities and similarities[0]["similarity"]["score"] >= ACTIVE_REJECTION:
                rejected["too-similar-to-active"] += 1
                continue
            candidates.append({
                "clues": clues,
                "slots": slots,
                "report": report,
                "styleScore": style_score(report),
                "activeSimilarities": similarities,
            })

    candidates.sort(key=lambda item: item["styleScore"], reverse=True)
    selected = []
    while candidates and len(selected) < 3:
        best = None
        best_value = -math.inf
        for candidate in candidates:
            pair_scores = [
                shape_similarity(candidate["clues"], candidate["slots"], other["clues"], other["slots"])["score"]
                for other in selected
            ]
            if pair_scores and max(pair_scores) >= NEW_SHAPE_REJECTION:
                continue
            diversity_penalty = 8 * max(pair_scores, default=0)
            # Reward different internal clue counts as well as different masks.
            count_bonus = 1.2 if selected and len(candidate["clues"]) != len(selected[-1]["clues"]) else 0
            value = candidate["styleScore"] - diversity_penalty + count_bonus
            if value > best_value:
                best = candidate
                best_value = value
        if best is None:
            break
        selected.append(best)
        candidates.remove(best)

    shapes = []
    for index, candidate in enumerate(selected, 1):
        pairwise = []
        for other_index, other in enumerate(selected, 1):
            if index == other_index:
                continue
            pairwise.append({
                "shapeId": f"reference-style-b-{other_index:02d}",
                "similarity": shape_similarity(candidate["clues"], candidate["slots"], other["clues"], other["slots"]),
            })
        nearest_item = candidate["activeSimilarities"][0]
        shapes.append(serialise_shape(
            f"reference-style-b-{index:02d}", candidate["clues"], candidate["report"],
            nearest_item, candidate["activeSimilarities"], pairwise,
        ))

    output = ROOT / "output/quality/reference-style-shapes-b.json"
    output.write_text(json.dumps({
        "version": 1,
        "kind": "motman-reference-inspired-9x10-shape-library-b",
        "referencePrinciples": [
            "complete top and left definition border",
            "long horizontal and vertical crossing bands",
            "sparse internal definition cells",
            "internal cells preferentially carry both right and down clues",
            "no checkerboard rhythm",
        ],
        "similarityFormula": {
            "clueCellJaccard": 0.40,
            "slotPathJaccard": 0.30,
            "letterDefinitionMaskAgreement": 0.15,
            "slotLengthDirectionProfileCosine": 0.15,
            "activeRejectionThreshold": ACTIVE_REJECTION,
            "newShapePairRejectionThreshold": NEW_SHAPE_REJECTION,
        },
        "activeComparisonCount": len(active_shapes),
        "candidateSearch": {
            "internalPositions": len(internal_positions),
            "internalDefinitionCountsTried": [3, 4, 5],
            "acceptedBeforeDiversitySelection": len(candidates) + len(selected),
            "rejections": dict(rejected),
        },
        "shapes": shapes,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "activeCompared": len(active_shapes),
        "shapes": [
            {
                "id": shape["id"],
                "valid": shape["geometryAudit"]["valid"],
                "slots": shape["geometryAudit"]["slotCount"],
                "long": shape["geometryAudit"]["longSlotsAtLeast5"],
                "double": shape["geometryAudit"]["doubleClueCount"],
                "nearest": shape["nearestActiveGrid"],
            }
            for shape in shapes
        ],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
