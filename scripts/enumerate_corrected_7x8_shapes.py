#!/usr/bin/env python3
"""Exhaustively enumerate 7x8 silhouettes under the corrected MotMan contract.

The visible grid contains a complete clue frame on the top and left.  Interior
letter runs of length at least three become direct right/down slots.  A
one-cell run on one axis is permitted only when the cell is covered by a slot
on the other axis; two-cell runs are always rejected.

This module is deliberately independent from ``grid_topology.py`` so the
enumeration remains a separate mathematical certificate.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COLUMNS = 7
ROWS = 8
WIDTH = COLUMNS - 1
HEIGHT = ROWS - 1
MINIMUM_SLOT_LENGTH = 3
DEFAULT_OUTPUT_DIRECTORY = ROOT / "output/quality/corrected-7x8-shapes"


@dataclass(frozen=True)
class LineAudit:
    clues: tuple[bool, ...]
    runs: tuple[tuple[int, int], ...]
    covered: frozenset[int]
    internal_launchers: frozenset[int]

    @property
    def singleton_count(self) -> int:
        return sum(length == 1 for _, length in self.runs)


def analyze_line(clues: tuple[bool, ...]) -> LineAudit | None:
    """Validate one framed line and describe all its maximal letter runs."""

    runs: list[tuple[int, int]] = []
    position = 0
    while position < len(clues):
        if clues[position]:
            position += 1
            continue
        end = position
        while end < len(clues) and not clues[end]:
            end += 1
        runs.append((position, end - position))
        position = end
    # The frame clue must launch a real answer immediately: the first run
    # starts at the border and contains at least three letters.
    if not runs or runs[0][0] != 0 or runs[0][1] < MINIMUM_SLOT_LENGTH:
        return None
    if any(length == 2 for _, length in runs):
        return None
    covered = frozenset(
        cell
        for start, length in runs if length >= MINIMUM_SLOT_LENGTH
        for cell in range(start, start + length)
    )
    launchers = frozenset(
        start - 1
        for start, length in runs
        if start > 0 and length >= MINIMUM_SLOT_LENGTH
    )
    return LineAudit(clues, tuple(runs), covered, launchers)


def valid_line_patterns(length: int) -> tuple[LineAudit, ...]:
    return tuple(
        audit
        for clues in itertools.product((False, True), repeat=length)
        if (audit := analyze_line(clues)) is not None
    )


def pattern_text(clues: tuple[bool, ...]) -> str:
    return "".join("#" if clue else "." for clue in clues)


def fingerprint(pivots: tuple[tuple[int, int], ...]) -> str:
    raw = json.dumps(pivots, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(raw).hexdigest()[:16]


def _frame() -> set[tuple[int, int]]:
    return (
        {(0, column) for column in range(COLUMNS)}
        | {(row, 0) for row in range(1, ROWS)}
    )


def _slots(
    shape_id: str,
    row_audits: tuple[LineAudit, ...],
    column_audits: tuple[LineAudit, ...],
) -> list[dict]:
    pending: list[dict] = []
    for row_offset, audit in enumerate(row_audits, start=1):
        for start, length in audit.runs:
            if length < MINIMUM_SLOT_LENGTH:
                continue
            pending.append({
                "direction": "across",
                "arrow": "right",
                "clueCell": [row_offset, start],
                "cells": [
                    [row_offset, column]
                    for column in range(start + 1, start + length + 1)
                ],
                "length": length,
            })
    for column_offset, audit in enumerate(column_audits, start=1):
        for start, length in audit.runs:
            if length < MINIMUM_SLOT_LENGTH:
                continue
            pending.append({
                "direction": "down",
                "arrow": "down",
                "clueCell": [start, column_offset],
                "cells": [
                    [row, column_offset]
                    for row in range(start + 1, start + length + 1)
                ],
                "length": length,
            })
    pending.sort(key=lambda slot: (
        slot["clueCell"][0], slot["clueCell"][1],
        0 if slot["direction"] == "across" else 1,
    ))
    for index, slot in enumerate(pending):
        slot["slotIndex"] = index
        slot["slotId"] = f"{shape_id}:slot:{index:02d}"
    return pending


def _visual_signature(pivots: set[tuple[int, int]]) -> list[str]:
    result = []
    for row in range(ROWS):
        cells = []
        for column in range(COLUMNS):
            if (row, column) == (0, 0):
                cells.append("O")
            elif row == 0 or column == 0:
                cells.append("D")
            elif (row, column) in pivots:
                cells.append("#")
            else:
                cells.append(".")
        result.append("".join(cells))
    return result


def _visual_family(row_four: str) -> str:
    if "#" not in row_four:
        return "solid-interior"
    if row_four.endswith("#") and ".#." not in row_four:
        return "central-right-ribbon"
    return "central-broken-ribbon"


def _build_shape(
    sequence: int,
    row_audits: tuple[LineAudit, ...],
    column_audits: tuple[LineAudit, ...],
) -> dict:
    shape_id = f"corrected-7x8-{sequence:02d}"
    pivot_set = {
        (row, column)
        for row, audit in enumerate(row_audits, start=1)
        for column, is_clue in enumerate(audit.clues, start=1)
        if is_clue
    }
    pivots = tuple(sorted(pivot_set))
    slots = _slots(shape_id, row_audits, column_audits)
    clue_cells = [list(cell) for cell in sorted(_frame() | pivot_set)]
    coverage: dict[tuple[int, int], dict[str, list[str]]] = defaultdict(
        lambda: {"across": [], "down": []}
    )
    for slot in slots:
        for raw_cell in slot["cells"]:
            coverage[tuple(raw_cell)][slot["direction"]].append(slot["slotId"])
    letter_cells = {
        (row, column)
        for row in range(1, ROWS)
        for column in range(1, COLUMNS)
        if (row, column) not in pivot_set
    }
    clue_launches = Counter(tuple(slot["clueCell"]) for slot in slots)
    isolated = sorted(
        clue for clue in (_frame() | pivot_set) - {(0, 0)}
        if not clue_launches[clue]
    )
    orphan = sorted(cell for cell in letter_cells if not any(coverage[cell].values()))
    if isolated or orphan:
        raise AssertionError(f"invalid certified shape: isolated={isolated}, orphan={orphan}")
    length_histogram = Counter(slot["length"] for slot in slots)
    singleton_across = sum(audit.singleton_count for audit in row_audits)
    singleton_down = sum(audit.singleton_count for audit in column_audits)
    cells = []
    for cell in sorted(letter_cells):
        across = coverage[cell]["across"]
        down = coverage[cell]["down"]
        cells.append({
            "cell": list(cell),
            "acrossSlotId": across[0] if across else None,
            "downSlotId": down[0] if down else None,
            "coveredAxes": int(bool(across)) + int(bool(down)),
        })
    row_four = pattern_text(row_audits[3].clues)
    score = (
        len(slots)
        + 2.0 * len(length_histogram)
        - 2.5 * length_histogram[3]
        - 0.5 * (singleton_across + singleton_down)
    )
    return {
        "shapeId": shape_id,
        "fingerprint": fingerprint(pivots),
        "visualFamily": _visual_family(row_four),
        "columns": COLUMNS,
        "rows": ROWS,
        "pivots": [list(cell) for cell in pivots],
        "clueCells": clue_cells,
        "slots": slots,
        "visualSignature": _visual_signature(pivot_set),
        "coverageAudit": {
            "valid": True,
            "letterCellCount": len(letter_cells),
            "coveredLetterCellCount": len(letter_cells) - len(orphan),
            "orphanLetterCells": [],
            "isolatedClueCells": [],
            "singleAxisCells": sum(item["coveredAxes"] == 1 for item in cells),
            "doubleAxisCells": sum(item["coveredAxes"] == 2 for item in cells),
            "cells": cells,
        },
        "metrics": {
            "internalClueCells": len(pivots),
            "letterCells": len(letter_cells),
            "answerCount": len(slots),
            "minimumAnswerLength": min(length_histogram),
            "maximumAnswerLength": max(length_histogram),
            "threeLetterAnswers": length_histogram[3],
            "fourToSevenLetterAnswers": sum(
                count for length, count in length_histogram.items()
                if 4 <= length <= 7
            ),
            "singletonAcrossRuns": singleton_across,
            "singletonDownRuns": singleton_down,
            "lengthHistogram": {
                str(length): length_histogram[length]
                for length in sorted(length_histogram)
            },
            "editorialShapeScore": round(score, 3),
        },
    }


@lru_cache(maxsize=1)
def enumerate_shape_space() -> tuple[tuple[dict, ...], dict]:
    """Exhaust the 7**7 row layouts with prefix-safe column pruning."""

    row_patterns = valid_line_patterns(WIDTH)
    column_patterns = valid_line_patterns(HEIGHT)
    column_by_clues = {audit.clues: audit for audit in column_patterns}
    prefix_sets = [set() for _ in range(HEIGHT + 1)]
    for audit in column_patterns:
        for depth in range(HEIGHT + 1):
            prefix_sets[depth].add(audit.clues[:depth])

    accepted_rows: list[tuple[LineAudit, ...]] = []
    rejected = Counter()
    visited_nodes = 0
    compatible_leaves = 0
    pruned_raw_layouts = 0

    def visit(
        rows_so_far: tuple[LineAudit, ...],
        column_prefixes: tuple[tuple[bool, ...], ...],
    ) -> None:
        nonlocal visited_nodes, compatible_leaves, pruned_raw_layouts
        visited_nodes += 1
        depth = len(rows_so_far)
        if depth == HEIGHT:
            compatible_leaves += 1
            column_audits = tuple(column_by_clues[prefix] for prefix in column_prefixes)
            for row, row_audit in enumerate(rows_so_far):
                for column, is_clue in enumerate(row_audit.clues):
                    if is_clue:
                        if (
                            column not in row_audit.internal_launchers
                            and row not in column_audits[column].internal_launchers
                        ):
                            rejected["isolated-internal-clue"] += 1
                            return
                    elif (
                        column not in row_audit.covered
                        and row not in column_audits[column].covered
                    ):
                        rejected["orphan-singleton-letter"] += 1
                        return
            accepted_rows.append(rows_so_far)
            return

        remaining_after_choice = HEIGHT - depth - 1
        for row_audit in row_patterns:
            next_prefixes = tuple(
                column_prefixes[column] + (row_audit.clues[column],)
                for column in range(WIDTH)
            )
            if all(prefix in prefix_sets[depth + 1] for prefix in next_prefixes):
                visit(rows_so_far + (row_audit,), next_prefixes)
            else:
                pruned_raw_layouts += len(row_patterns) ** remaining_after_choice

    visit((), tuple(() for _ in range(WIDTH)))
    shapes = []
    for index, row_audits in enumerate(accepted_rows, start=1):
        column_audits = tuple(
            column_by_clues[tuple(row.clues[column] for row in row_audits)]
            for column in range(WIDTH)
        )
        shapes.append(_build_shape(index, row_audits, column_audits))

    raw_layout_count = len(row_patterns) ** HEIGHT
    assert pruned_raw_layouts + compatible_leaves == raw_layout_count
    assert compatible_leaves == len(shapes) + sum(rejected.values())
    stats = {
        "rowPatterns": [pattern_text(audit.clues) for audit in row_patterns],
        "columnPatterns": [pattern_text(audit.clues) for audit in column_patterns],
        "rowPatternCount": len(row_patterns),
        "columnPatternCount": len(column_patterns),
        "rawLayoutCount": raw_layout_count,
        "visitedSearchNodes": visited_nodes,
        "columnPrefixPrunedLayoutCount": pruned_raw_layouts,
        "columnCompatibleLayoutCount": compatible_leaves,
        "acceptedShapeCount": len(shapes),
        "rejectedByReason": dict(sorted(rejected.items())),
        "exhaustive": True,
        "independentInternalClueRows": sorted({
            row for shape in shapes for row, _ in map(tuple, shape["pivots"])
        }),
        "visualFamilies": sorted({shape["visualFamily"] for shape in shapes}),
    }
    return tuple(shapes), stats


def mathematical_proof() -> list[str]:
    return [
        "La définition du cadre gauche doit lancer au moins trois lettres : le premier pivot interne d’une ligne ne peut donc apparaître qu’à partir de la colonne 4.",
        "Dans un intérieur large de six cases, un pivot placé en colonne 4 ou plus laisse au maximum deux cases à droite : il ne peut lancer aucune réponse horizontale de longueur minimale trois.",
        "Chaque pivot interne doit donc lancer sa réponse vers le bas.",
        "La définition du cadre haut doit conserver au moins trois lettres avant ce pivot, donc le pivot est en ligne 4 ou plus.",
        "Le pivot doit également laisser trois lettres sous lui, donc il est en ligne 4 ou moins.",
        "Tous les pivots internes sont ainsi forcés sur la ligne 4. Les singleton autorisent sept motifs sur cette ligne, mais aucune autre ligne de pivots ni nouvelle famille générale.",
    ]


def build_payload() -> dict:
    shapes, stats = enumerate_shape_space()
    # Best editorial compromise: two short answers only, no axial singleton,
    # and a five-letter central answer (larger eligible pool than length four).
    recommended = "corrected-7x8-02"
    return {
        "version": 1,
        "kind": "motman-corrected-frame-7x8-shape-library",
        "columns": COLUMNS,
        "rows": ROWS,
        "catalogModified": False,
        "runtimeModified": False,
        "contract": {
            "fullTopAndLeftClueFrame": True,
            "arrows": ["right", "down"],
            "minimumSlotLength": MINIMUM_SLOT_LENGTH,
            "twoLetterRuns": "forbidden",
            "perpendicularSingleton": "allowed-only-when-covered-by-the-other-axis",
            "letterCoverage": "at-least-one-declared-slot",
            "everyNonNeutralClueLaunchesAResponse": True,
        },
        "mathematicalProof": mathematical_proof(),
        "enumerationStats": stats,
        "shapeCount": len(shapes),
        "genuinelyDiverseTripletExists": False,
        "diversityLimitation": "Every legal internal clue is forced onto row 4; the seven results are variants of the same central-band geometry.",
        "recommendedPilotShapeId": recommended,
        "recommendedPilotReason": (
            "One pivot at row 4, column 6 keeps only two three-letter answers, "
            "creates no axial singleton, and leaves a five-letter middle answer."
        ),
        "shapes": list(shapes),
    }


def build_report(payload: dict) -> str:
    stats = payload["enumerationStats"]
    lines = [
        "# Silhouettes 7×8 — contrat corrigé",
        "",
        "## Conclusion",
        "",
        (
            f"L’énumération exhaustive des **{stats['rawLayoutCount']:,}** agencements "
            f"de lignes produit exactement **{payload['shapeCount']} silhouettes légales**."
        ).replace(",", " "),
        "",
        "Il n’existe pas trois silhouettes réellement indépendantes sous ce contrat : tous les pivots sont forcés sur la ligne 4.",
        "",
        "## Preuve",
        "",
    ]
    lines.extend(f"{index}. {item}" for index, item in enumerate(payload["mathematicalProof"], 1))
    lines.extend([
        "",
        "## Recommandation pilote",
        "",
        f"**{payload['recommendedPilotShapeId']}** — {payload['recommendedPilotReason']}",
        "",
        "## Les sept silhouettes",
        "",
        "Légende : `O` angle neutre, `D` définition du cadre, `#` définition interne, `.` lettre.",
        "",
    ])
    for shape in payload["shapes"]:
        marker = " — recommandée" if shape["shapeId"] == payload["recommendedPilotShapeId"] else ""
        lines.extend([
            f"### {shape['shapeId']}{marker}", "", "```text",
            *shape["visualSignature"], "```", "",
            f"Longueurs : `{shape['metrics']['lengthHistogram']}` — "
            f"3 lettres : {shape['metrics']['threeLetterAnswers']} — "
            f"singleton axial : {shape['metrics']['singletonAcrossRuns'] + shape['metrics']['singletonDownRuns']}",
            "",
        ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_payload()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    json_path = args.output_directory / "corrected-shape-library.json"
    report_path = args.output_directory / "corrected-shape-report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(build_report(payload), encoding="utf-8")
    print(json.dumps({
        "json": str(json_path),
        "report": str(report_path),
        "rawLayoutCount": payload["enumerationStats"]["rawLayoutCount"],
        "shapeCount": payload["shapeCount"],
        "recommendedPilotShapeId": payload["recommendedPilotShapeId"],
        "genuinelyDiverseTripletExists": payload["genuinelyDiverseTripletExists"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
