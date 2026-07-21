#!/usr/bin/env python3
"""Exhaustively enumerate strict-frame 7x8 crossword silhouettes.

The playable interior is seven rows by six columns.  The top row and left
column are definition cells, arrows only run right or down, every answer has
at least three letters, and every letter belongs to exactly one across and one
down answer.

Those constraints are much tighter than they first appear.  There are only
four legal row masks, so all 4**7 = 16,384 possible layouts can be checked
exhaustively and deterministically.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

from search_compact_grid_pilot import build_slots


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT / "src/data/grid-generation-handcrafted/pilot-7x8-shapes.json"
)
COLUMNS = 7
ROWS = 8
INTERIOR_WIDTH = COLUMNS - 1
INTERIOR_HEIGHT = ROWS - 1
MINIMUM_SLOT_LENGTH = 3


def valid_row_patterns(width: int = INTERIOR_WIDTH) -> list[tuple[bool, ...]]:
    """Return every row mask compatible with the left definition frame.

    ``True`` denotes an internal definition cell.  The first interior cell
    must remain a letter, otherwise the definition on the left frame would be
    isolated.  Every visible letter run must contain at least three cells.
    """

    patterns = []
    for values in itertools.product((False, True), repeat=width):
        if values[0]:
            continue
        encoded = "".join("#" if is_clue else "." for is_clue in values)
        runs = [len(run) for run in encoded.split("#") if run]
        if all(length >= MINIMUM_SLOT_LENGTH for length in runs):
            patterns.append(values)
    return patterns


def pattern_text(pattern: tuple[bool, ...]) -> str:
    return "".join("#" if is_clue else "." for is_clue in pattern)


def shape_fingerprint(pivots: set[tuple[int, int]]) -> str:
    encoded = json.dumps(sorted(pivots), separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()[:16]


def visual_family(pivots: set[tuple[int, int]]) -> str:
    if not pivots:
        return "solid-interior"
    return "central-right-ribbon"


def render_shape(
    columns: int, rows: int, pivots: set[tuple[int, int]]
) -> list[str]:
    """Render a compact proof view: D=frame clue, #=internal clue, .=letter."""

    rendered = []
    for row in range(rows):
        cells = []
        for column in range(columns):
            if (row, column) == (0, 0):
                cells.append("O")
            elif row == 0 or column == 0:
                cells.append("D")
            elif (row, column) in pivots:
                cells.append("#")
            else:
                cells.append(".")
        rendered.append("".join(cells))
    return rendered


def audit_shape_contract(
    columns: int,
    rows: int,
    pivots: set[tuple[int, int]],
    clue_cells: list[list[int]],
    raw_slots: list[dict],
) -> dict:
    """Independently certify the hard topology contract for one shape."""

    frame = {(0, column) for column in range(columns)} | {
        (row, 0) for row in range(1, rows)
    }
    clues = {tuple(cell) for cell in clue_cells}
    if clues != frame | pivots:
        raise ValueError("Le jeu de cases-definition ne correspond pas au cadre et aux pivots")
    if any(int(slot["length"]) < MINIMUM_SLOT_LENGTH for slot in raw_slots):
        raise ValueError("Une reponse de moins de trois lettres a traverse l'audit")

    clue_to_slots: dict[tuple[int, int], list[str]] = defaultdict(list)
    coverage: dict[tuple[int, int], dict[str, list[str]]] = defaultdict(
        lambda: {"across": [], "down": []}
    )
    for slot in raw_slots:
        slot_id = str(slot["slotId"])
        direction = str(slot["direction"])
        clue = tuple(slot["clueCell"])
        clue_to_slots[clue].append(slot_id)
        for raw_cell in slot["cells"]:
            coverage[tuple(raw_cell)][direction].append(slot_id)

    isolated_clues = sorted(
        clue for clue in clues if clue != (0, 0) and not clue_to_slots.get(clue)
    )
    if isolated_clues:
        raise ValueError(f"Cases-definition isolees : {isolated_clues}")

    letter_cells = {
        (row, column)
        for row in range(1, rows)
        for column in range(1, columns)
        if (row, column) not in clues
    }
    if set(coverage) != letter_cells:
        missing = sorted(letter_cells - set(coverage))
        extra = sorted(set(coverage) - letter_cells)
        raise ValueError(f"Couverture incoherente, absentes={missing}, excedentaires={extra}")

    invalid_coverage = []
    cells = []
    for cell in sorted(letter_cells):
        across = coverage[cell]["across"]
        down = coverage[cell]["down"]
        if len(across) != 1 or len(down) != 1:
            invalid_coverage.append(cell)
        cells.append({
            "cell": list(cell),
            "acrossSlotId": across[0] if len(across) == 1 else None,
            "downSlotId": down[0] if len(down) == 1 else None,
        })
    if invalid_coverage:
        raise ValueError(f"Cases sans double couverture exacte : {invalid_coverage}")

    return {
        "valid": True,
        "frameClueCellCount": len(frame),
        "internalClueCellCount": len(pivots),
        "letterCellCount": len(letter_cells),
        "coveredExactlyOnceAcrossAndDown": len(letter_cells),
        "isolatedClueCells": [],
        "orphanLetterCells": [],
        "cells": cells,
    }


def rejection_reason(error: ValueError) -> str:
    message = str(error)
    if "moins de trois" in message:
        return "slot-shorter-than-three"
    if "sans fleche" in message or "isolees" in message:
        return "isolated-clue"
    if "non couvertes" in message:
        return "orphan-letter"
    if "horizontalement et verticalement" in message or "double couverture" in message:
        return "single-axis-letter"
    return "other-contract-error"


def pairwise_distances(shapes: list[dict]) -> list[dict]:
    result = []
    for left, right in itertools.combinations(shapes, 2):
        left_pivots = {tuple(cell) for cell in left["pivots"]}
        right_pivots = {tuple(cell) for cell in right["pivots"]}
        result.append({
            "leftShapeId": left["shapeId"],
            "rightShapeId": right["shapeId"],
            "differentInternalClueCells": len(left_pivots ^ right_pivots),
        })
    return result


def enumerate_shape_space() -> tuple[list[dict], dict]:
    shapes = []
    rejected = Counter()
    patterns = valid_row_patterns()
    raw_layout_count = len(patterns) ** INTERIOR_HEIGHT

    for rows in itertools.product(patterns, repeat=INTERIOR_HEIGHT):
        pivots = {
            (row_index, column_index)
            for row_index, pattern in enumerate(rows, start=1)
            for column_index, is_clue in enumerate(pattern, start=1)
            if is_clue
        }
        try:
            clue_cells, raw_slots, _ = build_slots(COLUMNS, ROWS, pivots)
            coverage_audit = audit_shape_contract(
                COLUMNS, ROWS, pivots, clue_cells, raw_slots
            )
        except ValueError as error:
            rejected[rejection_reason(error)] += 1
            continue

        lengths = sorted(int(slot["length"]) for slot in raw_slots)
        histogram = Counter(lengths)
        shape_id = f"pilot-7x8-strict-{len(shapes) + 1:02d}"
        shapes.append({
            "shapeId": shape_id,
            "fingerprint": shape_fingerprint(pivots),
            "visualFamily": visual_family(pivots),
            "columns": COLUMNS,
            "rows": ROWS,
            "pivots": [list(cell) for cell in sorted(pivots)],
            "visualSignature": render_shape(COLUMNS, ROWS, pivots),
            "clueCells": clue_cells,
            "slots": raw_slots,
            "coverageAudit": coverage_audit,
            "metrics": {
                "internalClueCells": len(pivots),
                "letterCells": INTERIOR_HEIGHT * INTERIOR_WIDTH - len(pivots),
                "answerCount": len(raw_slots),
                "minimumAnswerLength": min(lengths),
                "maximumAnswerLength": max(lengths),
                "threeLetterAnswers": histogram[3],
                "answersAtLeastFiveLetters": sum(
                    count for length, count in histogram.items() if length >= 5
                ),
                "lengthHistogram": {
                    str(length): histogram[length] for length in sorted(histogram)
                },
                "lengths": lengths,
            },
        })

    visual_families = sorted({shape["visualFamily"] for shape in shapes})
    stats = {
        "rowPatterns": [pattern_text(pattern) for pattern in patterns],
        "rowPatternCount": len(patterns),
        "rawLayoutCount": raw_layout_count,
        "acceptedShapeCount": len(shapes),
        "rejectedLayoutCount": raw_layout_count - len(shapes),
        "rejectedByReason": dict(sorted(rejected.items())),
        "visualFamilies": visual_families,
        "visualFamilyCount": len(visual_families),
        "pairwiseDistances": pairwise_distances(shapes),
        "allPivotSetsNested": all(
            {tuple(cell) for cell in left["pivots"]}.issubset(
                {tuple(cell) for cell in right["pivots"]}
            )
            for left, right in zip(shapes, shapes[1:])
        ),
    }
    return shapes, stats


def enumerate_shapes() -> list[dict]:
    """Backward-compatible entry point used by the pilot orchestrator."""

    return enumerate_shape_space()[0]


def mathematical_explanation() -> list[str]:
    return [
        "Chaque ligne intérieure commence par une lettre, sinon sa définition du cadre gauche serait isolée.",
        "Avec six cellules intérieures et une longueur minimale de trois, la première définition interne ne peut commencer qu'en colonne 4, 5 ou 6.",
        "Il reste alors moins de trois cellules à sa droite : toutes les cellules suivantes de la ligne doivent donc aussi être des définitions.",
        "Une définition placée dans ce suffixe n'a aucune réponse horizontale et doit donc lancer une réponse verticale d'au moins trois lettres.",
        "Elle doit aussi laisser au moins trois lettres au-dessus pour la réponse partie du cadre haut ; sur sept lignes intérieures, seule la ligne 4 laisse trois lettres de chaque côté.",
        "Tous les pivots sont donc sur la ligne 4 et forment un suffixe terminé en colonne 6 : zéro, un, deux ou trois pivots.",
    ]


def build_payload() -> dict:
    shapes, stats = enumerate_shape_space()
    return {
        "version": 2,
        "kind": "motman-strict-frame-7x8-shape-library",
        "exhaustive": True,
        "constraints": {
            "fullTopAndLeftDefinitionFrame": True,
            "supportedAnswerDirections": ["across", "down"],
            "minimumSlotLength": MINIMUM_SLOT_LENGTH,
            "letterCoverage": "exactly-one-across-and-one-down",
            "isolatedClues": 0,
            "orphanLetters": 0,
        },
        "mathematicalExplanation": mathematical_explanation(),
        "enumerationStats": stats,
        "shapeCount": len(shapes),
        "shapes": shapes,
    }


def build_markdown_report(payload: dict) -> str:
    stats = payload["enumerationStats"]
    lines = [
        "# Audit exhaustif des silhouettes strictes 7x8",
        "",
        "## Conclusion",
        "",
        (
            f"Le contrat dur autorise **{payload['shapeCount']} silhouettes mathématiques** "
            f"sur **{stats['rawLayoutCount']} agencements** examinés. Elles ne forment que "
            f"**{stats['visualFamilyCount']} familles visuelles** : une grille pleine et un ruban "
            "central collé au bord droit, en trois profondeurs."
        ),
        "",
        "Cette limite vient de la géométrie, pas du solveur ni du corpus.",
        "",
        "## Démonstration",
        "",
    ]
    lines.extend(f"{index}. {text}" for index, text in enumerate(
        payload["mathematicalExplanation"], start=1
    ))
    lines.extend([
        "",
        "## Espace énuméré",
        "",
        f"- Motifs de ligne admissibles : `{', '.join(stats['rowPatterns'])}`",
        f"- Agencements bruts : {stats['rawLayoutCount']}",
        f"- Silhouettes acceptées : {stats['acceptedShapeCount']}",
        f"- Agencements rejetés : {stats['rejectedLayoutCount']}",
        f"- Rejets agrégés : `{json.dumps(stats['rejectedByReason'], ensure_ascii=False)}`",
        "",
        "## Silhouettes certifiées",
        "",
        "Légende : `O` angle neutre, `D` définition du cadre, `#` définition interne, `.` lettre.",
        "",
    ])
    for shape in payload["shapes"]:
        metrics = shape["metrics"]
        lines.extend([
            f"### {shape['shapeId']}",
            "",
            "```text",
            *shape["visualSignature"],
            "```",
            "",
            (
                f"Pivots : `{shape['pivots']}` — {metrics['answerCount']} réponses — "
                f"longueurs `{metrics['lengthHistogram']}` — "
                f"{metrics['threeLetterAnswers']} réponses de 3 lettres."
            ),
            "",
        ])
    lines.extend([
        "## Conséquence produit",
        "",
        (
            "Il est impossible d'obtenir davantage de silhouettes visuellement distinctes en 7x8 "
            "sans changer au moins une hypothèse : autoriser des flèches vers la gauche ou le haut, "
            "tolérer une réponse de deux lettres, ne plus exiger une définition sur chaque cellule "
            "du cadre, ou augmenter une dimension de la grille."
        ),
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    payload = build_payload()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(build_markdown_report(payload), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "report": str(args.report) if args.report else None,
        "shapeCount": payload["shapeCount"],
        "visualFamilyCount": payload["enumerationStats"]["visualFamilyCount"],
        "rawLayoutCount": payload["enumerationStats"]["rawLayoutCount"],
        "pivots": [shape["pivots"] for shape in payload["shapes"]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
