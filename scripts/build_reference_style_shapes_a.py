"""Build four deterministic 9x10 masks inspired by the supplied arrowword.

This is a geometry-only staging tool.  It never fills answers and never edits
the runtime catalog, blacklist, or clue assets.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology  # noqa: E402


ROWS = 10
COLUMNS = 9
OUTPUT = ROOT / "output/quality/reference-style-shapes-a.json"
CATALOG = ROOT / "src/data/grid.catalog.json"
REFERENCE_IMAGE = (
    r"C:\Users\peete\OneDrive\Images\Captures d'écran"
    r"\Capture d'écran 2026-07-17 003443.png"
)

FRAME = {
    *((0, column) for column in range(COLUMNS)),
    *((row, 0) for row in range(1, ROWS)),
}

# The masks are fixed after a bounded CP-SAT exploration.  Keeping the final
# cells here makes reproduction independent of solver worker scheduling.
SPECS = (
    {
        "id": "reference-ribbon-a-01",
        "name": "Cadre complet, pivots diagonaux",
        "sourceSeed": 717200,
        "design": "full-top-and-left-ribbons",
        "clues": FRAME | {(4, 4), (4, 8), (5, 5)},
    },
    {
        "id": "reference-ribbon-a-02",
        "name": "Cadre complet, rupture décalée",
        "sourceSeed": 727000,
        "design": "full-ribbons-offset-double-pivots",
        "clues": FRAME | {(4, 6), (4, 7), (5, 4), (6, 5)},
    },
    {
        "id": "reference-ribbon-a-03",
        "name": "Ruban supérieur ouvert",
        "sourceSeed": 725600,
        "design": "two-cell-top-ribbon-break",
        "clues": (
            FRAME - {(0, 4), (0, 5)}
            | {(1, 4), (1, 5), (4, 8), (6, 7), (8, 5)}
        ),
    },
    {
        "id": "reference-ribbon-a-04",
        "name": "Ruban gauche ouvert",
        "sourceSeed": 726720,
        "design": "two-cell-left-ribbon-break",
        "clues": (
            FRAME - {(7, 0), (8, 0)}
            | {(5, 8), (6, 5), (7, 1), (8, 1), (9, 4)}
        ),
    },
)


def direct_slots(clues: set[tuple[int, int]]) -> list[dict]:
    slots = []
    for clue in sorted(clues - {(0, 0)}):
        for direction, arrow, (dr, dc) in (
            ("across", "right", (0, 1)),
            ("down", "down", (1, 0)),
        ):
            cells = []
            row, column = clue[0] + dr, clue[1] + dc
            while (
                0 <= row < ROWS
                and 0 <= column < COLUMNS
                and (row, column) not in clues
            ):
                cells.append([row, column])
                row += dr
                column += dc
            if len(cells) >= 2:
                slots.append(
                    {
                        "slotId": f"slot-{len(slots) + 1:02d}",
                        "direction": direction,
                        "arrow": arrow,
                        "clueCell": list(clue),
                        "cells": cells,
                        "length": len(cells),
                    }
                )
    return slots


def maximal_visible_segments(
    clues: set[tuple[int, int]], direction: str
) -> list[tuple[tuple[int, int], ...]]:
    segments = []
    outer = range(ROWS) if direction == "across" else range(COLUMNS)
    limit = COLUMNS if direction == "across" else ROWS
    for fixed in outer:
        offset = 0
        while offset < limit:
            cell = (fixed, offset) if direction == "across" else (offset, fixed)
            if cell in clues:
                offset += 1
                continue
            start = offset
            while offset < limit:
                cell = (fixed, offset) if direction == "across" else (offset, fixed)
                if cell in clues:
                    break
                offset += 1
            segment = tuple(
                (fixed, value) if direction == "across" else (value, fixed)
                for value in range(start, offset)
            )
            if len(segment) >= 2:
                segments.append(segment)
    return segments


def template_grid(shape_id: str, clues: set[tuple[int, int]], slots: list[dict]) -> dict:
    return {
        "id": shape_id,
        "columns": COLUMNS,
        "rows": ROWS,
        "clueCells": [list(cell) for cell in sorted(clues)],
        "words": [
            {
                "wordId": f"{shape_id}:{slot['slotId']}",
                "answer": "X" * slot["length"],
                "clue": f"Gabarit {slot['length']}",
                "direction": slot["direction"],
                "arrow": slot["arrow"],
                "clueCell": slot["clueCell"],
                "cells": slot["cells"],
            }
            for slot in slots
        ],
    }


def validate_geometry(
    shape_id: str, clues: set[tuple[int, int]], slots: list[dict]
) -> dict:
    all_cells = {(row, column) for row in range(ROWS) for column in range(COLUMNS)}
    letters = all_cells - clues
    coverage = Counter(
        tuple(cell) for slot in slots for cell in slot["cells"]
    )
    uncovered = sorted(cell for cell in letters if coverage[cell] == 0)
    overcovered = sorted(cell for cell in letters if coverage[cell] > 2)
    declared = {
        direction: {
            tuple(tuple(cell) for cell in slot["cells"])
            for slot in slots
            if slot["direction"] == direction
        }
        for direction in ("across", "down")
    }
    orphan_segments = []
    for direction in ("across", "down"):
        for segment in maximal_visible_segments(clues, direction):
            if segment not in declared[direction]:
                orphan_segments.append(
                    {"direction": direction, "cells": [list(cell) for cell in segment]}
                )
    launches = Counter(tuple(slot["clueCell"]) for slot in slots)
    unused_clues = sorted(
        cell for cell in clues - {(0, 0)} if not 1 <= launches[cell] <= 2
    )
    ambiguous_paths = [
        slot["slotId"]
        for slot in slots
        if slot["arrow"] != ("right" if slot["direction"] == "across" else "down")
    ]
    audit = audit_grid_topology(
        template_grid(shape_id, clues, slots), enforce_layout=False
    )
    strict = audit_grid_topology(
        template_grid(shape_id, clues, slots), enforce_layout=True
    )
    valid = not (
        uncovered
        or overcovered
        or orphan_segments
        or unused_clues
        or ambiguous_paths
        or not audit["valid"]
    )
    return {
        "valid": valid,
        "letterCells": len(letters),
        "coveredLetterCells": len(letters) - len(uncovered),
        "uncoveredLetterCells": [list(cell) for cell in uncovered],
        "overcoveredLetterCells": [list(cell) for cell in overcovered],
        "orphanSegments": orphan_segments,
        "unusedOrOverloadedClueCells": [list(cell) for cell in unused_clues],
        "ambiguousPaths": ambiguous_paths,
        "neutralCells": [[0, 0]],
        "coreAuditErrors": audit["errors"],
        "strictLayoutWarnings": strict["errors"],
    }


def active_comparison(clues: set[tuple[int, int]], active_grids: list[dict]) -> dict:
    visible = clues - {(0, 0)}
    comparisons = []
    for grid in active_grids:
        other = {tuple(cell) for cell in grid["clueCells"]} - {(0, 0)}
        intersection = len(visible & other)
        union = len(visible | other)
        comparisons.append(
            {
                "gridId": grid["id"],
                "overlap": intersection,
                "symmetricDifference": len(visible ^ other),
                "jaccard": round(intersection / union, 4),
            }
        )
    nearest = sorted(
        comparisons,
        key=lambda item: (-item["jaccard"], item["symmetricDifference"], item["gridId"]),
    )[0]
    exact = [item["gridId"] for item in comparisons if item["symmetricDifference"] == 0]
    return {
        "activeGridCountCompared": len(active_grids),
        "exactActiveShapeMatches": exact,
        "differentFromAllActiveShapes": not exact,
        "nearestActiveShape": nearest,
        "minimumSymmetricDifference": min(
            item["symmetricDifference"] for item in comparisons
        ),
        "maximumJaccard": max(item["jaccard"] for item in comparisons),
    }


def image_candidates(slots: list[dict]) -> list[dict]:
    launches = Counter(tuple(slot["clueCell"]) for slot in slots)
    eligible = [
        {
            "slotId": slot["slotId"],
            "clueCell": slot["clueCell"],
            "direction": slot["direction"],
            "length": slot["length"],
        }
        for slot in slots
        if launches[tuple(slot["clueCell"])] == 1 and 3 <= slot["length"] <= 8
    ]
    # A stable spread: alternate top/left/bottom/right/interior candidates
    # instead of recommending six consecutive cells on the top ribbon.
    def zone(item: dict) -> int:
        row, column = item["clueCell"]
        if row == 0:
            return 0
        if column == 0:
            return 1
        if row == ROWS - 1:
            return 2
        if column == COLUMNS - 1:
            return 3
        return 4

    pools = defaultdict(list)
    for item in eligible:
        pools[zone(item)].append(item)
    spread = []
    while any(pools.values()):
        for zone_number in range(5):
            if pools[zone_number]:
                spread.append(pools[zone_number].pop(0))
    return spread


def shape_record(spec: dict, active_grids: list[dict]) -> dict:
    clues = set(spec["clues"])
    slots = direct_slots(clues)
    topology = validate_geometry(spec["id"], clues, slots)
    if not topology["valid"]:
        raise ValueError(f"{spec['id']}: invalid topology: {topology}")
    lengths = Counter(slot["length"] for slot in slots)
    minimum_length = min(lengths)
    long_answers = sum(lengths[length] for length in range(5, 9))
    short_answers = sum(lengths[length] for length in range(2, 5))
    launches = Counter(tuple(slot["clueCell"]) for slot in slots)
    candidates = image_candidates(slots)
    if len(candidates) < 6:
        raise ValueError(f"{spec['id']}: only {len(candidates)} image positions")
    internal = sorted(
        cell for cell in clues if cell[0] > 0 and cell[1] > 0
    )
    row_patterns = {
        "".join("D" if (row, column) in clues else "L" for column in range(COLUMNS))
        for row in range(ROWS)
    }
    rotational_mismatch = sum(
        ((row, column) in clues)
        != ((ROWS - 1 - row, COLUMNS - 1 - column) in clues)
        for row in range(ROWS)
        for column in range(COLUMNS)
    ) // 2
    return {
        "id": spec["id"],
        "name": spec["name"],
        "columns": COLUMNS,
        "rows": ROWS,
        "reproduction": {
            "builder": "scripts/build_reference_style_shapes_a.py",
            "fixedMaskDerivedFromSeed": spec["sourceSeed"],
            "designFamily": spec["design"],
        },
        "clueCells": [list(cell) for cell in sorted(clues)],
        "slots": slots,
        "metrics": {
            "visibleClueCells": len(clues) - 1,
            "internalClueCells": len(internal),
            "internalClueCoordinates": [list(cell) for cell in internal],
            "doubleRightDownClueCells": sum(value == 2 for value in launches.values()),
            "singleClueCells": sum(value == 1 for value in launches.values()),
            "slotCount": len(slots),
            "lengthProfile": {str(key): value for key, value in sorted(lengths.items())},
            "minimumAnswerLength": minimum_length,
            "answersLength2": lengths[2],
            "shortAnswers2To4": short_answers,
            "longAnswers5To8": long_answers,
            "longAnswerAdvantage": long_answers - short_answers,
            "answersLength9": lengths[9],
            "longBandsLength5Plus": sum(value for length, value in lengths.items() if length >= 5),
            "fullTopClueRibbon": all((0, column) in clues for column in range(COLUMNS)),
            "fullLeftClueRibbon": all((row, 0) in clues for row in range(ROWS)),
            "distinctRowPatterns": len(row_patterns),
            "rotationalSymmetryMismatch": rotational_mismatch,
            "imageSlotCapacity": len(candidates),
            "recommendedImageSlots": candidates[:6],
        },
        "topology": topology,
        "activeCatalogComparison": active_comparison(clues, active_grids),
    }


def pairwise_diversity(records: list[dict]) -> list[dict]:
    result = []
    for index, left in enumerate(records):
        left_cells = {tuple(cell) for cell in left["clueCells"]} - {(0, 0)}
        for right in records[index + 1 :]:
            right_cells = {tuple(cell) for cell in right["clueCells"]} - {(0, 0)}
            union = left_cells | right_cells
            result.append(
                {
                    "left": left["id"],
                    "right": right["id"],
                    "symmetricDifference": len(left_cells ^ right_cells),
                    "jaccard": round(len(left_cells & right_cells) / len(union), 4),
                }
            )
    return result


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    active_grids = [
        grid
        for grid in catalog["grids"]
        if grid.get("columns") == COLUMNS and grid.get("rows") == ROWS
    ]
    records = [shape_record(spec, active_grids) for spec in SPECS]
    pairwise = pairwise_diversity(records)
    document = {
        "version": 1,
        "kind": "reference-style-shape-breakthrough",
        "reference": {
            "image": REFERENCE_IMAGE,
            "observedDimensions": {
                "columns": 8,
                "rows": 10,
                "confidence": "visual estimate from supplied screenshot",
            },
            "observedPrinciples": [
                "continuous clue ribbon across the top edge",
                "continuous clue and image ribbon down the left edge",
                "long horizontal and vertical answer bands",
                "few internal clue cells relative to letter cells",
                "internal cells frequently launch both right and down answers",
                "asymmetrical interruptions rather than a repeated square motif",
                "images are used as ordinary clue cells, including on borders",
            ],
            "adaptation": (
                "The 8x10 visual grammar is adapted to MotMan's 9x10 board. "
                "Two masks keep the full top/left ribbons with no 2-letter entry; "
                "two deliberately break one ribbon to create a stronger silhouette, "
                "at the measured cost of one 2-letter border entry each."
            ),
        },
        "policy": {
            "columns": COLUMNS,
            "rows": ROWS,
            "neutralCells": [[0, 0]],
            "directArrowsOnly": True,
            "everyLetterCovered": True,
            "orphanSegmentsAllowed": 0,
            "minimumPreferredAnswerLength": 3,
            "majorityBand": [5, 8],
            "minimumImageSlots": 6,
            "catalogMutation": False,
            "blacklistMutation": False,
        },
        "shapes": records,
        "pairwiseDiversity": pairwise,
        "report": {
            "shapeCount": len(records),
            "allTopologyValid": all(record["topology"]["valid"] for record in records),
            "allDifferentFrom40Active": all(
                record["activeCatalogComparison"]["differentFromAllActiveShapes"]
                for record in records
            ),
            "allLongBandMajority": all(
                record["metrics"]["longAnswerAdvantage"] > 0 for record in records
            ),
            "allImageCapacityAtLeast6": all(
                record["metrics"]["imageSlotCapacity"] >= 6 for record in records
            ),
            "zeroTwoLetterShapeIds": [
                record["id"] for record in records if record["metrics"]["answersLength2"] == 0
            ],
            "oneTwoLetterBorderExceptionShapeIds": [
                record["id"] for record in records if record["metrics"]["answersLength2"] == 1
            ],
            "recommendation": (
                "Start fill tests with reference-ribbon-a-03: it has the strongest "
                "5-8 advantage and the top-ribbon break is the clearest visual departure. "
                "Use a-01 when a strict minimum length of three is preferred."
            ),
            "catalogTouched": False,
            "blacklistTouched": False,
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "shapes": len(records),
                "profiles": {
                    record["id"]: record["metrics"]["lengthProfile"] for record in records
                },
                "imageCapacity": {
                    record["id"]: record["metrics"]["imageSlotCapacity"] for record in records
                },
                "minimumActiveSymmetricDifference": {
                    record["id"]: record["activeCatalogComparison"]["minimumSymmetricDifference"]
                    for record in records
                },
                "pairwise": pairwise,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
