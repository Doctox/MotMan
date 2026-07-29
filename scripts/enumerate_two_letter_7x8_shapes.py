#!/usr/bin/env python3
"""Exhaustively enumerate the official 7x8 one/two-short-slot shapes.

The top row and left column are a complete clue frame. Answers only travel
right or down. Maximal runs of length 2+ are declared answers; a maximal
singleton is visually harmless only when its cell is covered by a declared
answer on the other axis. Exactly one or two declared answers have length two.
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

from pilot_two_letter_policy import (
    MAXIMUM_TWO_LETTER_ANSWERS,
    MINIMUM_TWO_LETTER_ANSWERS,
    valid_two_letter_answer_count,
)


ROOT = Path(__file__).resolve().parents[1]
COLUMNS = 7
ROWS = 8
WIDTH = COLUMNS - 1
HEIGHT = ROWS - 1
DEFAULT_OUTPUT_DIRECTORY = ROOT / "output/quality/new-two-letter-shapes"
ACTIVE_CATALOG = ROOT / "src/data/grid.catalog.json"
PREVIOUS_LIBRARIES = (
    ROOT / "src/data/grid-generation-handcrafted/pilot-7x8-shapes.json",
    ROOT / "output/quality/corrected-7x8-shapes/corrected-shape-library.json",
    ROOT / "output/quality/all-used-shapes-panel.json",
    ROOT / "src/data/grid-generation-handcrafted/reference-ribbon-band-03.shape.json",
    ROOT / "src/data/grid-generation-handcrafted/reference-ribbon-band-04.shape.json",
)


@dataclass(frozen=True)
class LineAudit:
    clues: tuple[bool, ...]
    runs: tuple[tuple[int, int], ...]
    covered: frozenset[int]
    internal_launchers: frozenset[int]
    two_letter_count: int
    singleton_count: int


def analyze_line(clues: tuple[bool, ...]) -> LineAudit | None:
    """Return the declared-run state for one line behind a frame clue."""
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
    # The border clue has no second possible direction: it must launch a
    # declared answer immediately. A singleton would leave it visually empty.
    if not runs or runs[0][0] != 0 or runs[0][1] < 2:
        return None
    declared = [(start, length) for start, length in runs if length >= 2]
    return LineAudit(
        clues=clues,
        runs=tuple(runs),
        covered=frozenset(
            cell
            for start, length in declared
            for cell in range(start, start + length)
        ),
        internal_launchers=frozenset(
            start - 1 for start, _length in declared if start > 0
        ),
        two_letter_count=sum(length == 2 for _start, length in declared),
        singleton_count=sum(length == 1 for _start, length in runs),
    )


@lru_cache(maxsize=None)
def valid_line_patterns(length: int) -> tuple[LineAudit, ...]:
    return tuple(
        audit
        for clues in itertools.product((False, True), repeat=length)
        if (audit := analyze_line(clues)) is not None
    )


def pattern_text(clues: tuple[bool, ...]) -> str:
    return "".join("#" if clue else "." for clue in clues)


def _frame() -> set[tuple[int, int]]:
    return (
        {(0, column) for column in range(COLUMNS)}
        | {(row, 0) for row in range(1, ROWS)}
    )


def shape_fingerprint(pivots: set[tuple[int, int]]) -> str:
    payload = {
        "columns": COLUMNS,
        "rows": ROWS,
        "pivots": sorted(pivots),
        "arrows": ["right", "down"],
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("ascii")
    return hashlib.sha256(raw).hexdigest()[:20]


def compatible_symmetry_fingerprints(
    pivots: set[tuple[int, int]],
) -> set[str]:
    """Return legal symmetry equivalents under the fixed directional frame.

    Horizontal/vertical reflection would move the clue frame or require
    left/up arrows. Transposition changes 7x8 into 8x7. The identity is thus
    the only product-compatible symmetry.
    """
    return {shape_fingerprint(pivots)}


def _slots(
    shape_id: str,
    row_audits: tuple[LineAudit, ...],
    column_audits: tuple[LineAudit, ...],
) -> list[dict]:
    pending: list[dict] = []
    for row, audit in enumerate(row_audits, start=1):
        for start, length in audit.runs:
            if length < 2:
                continue
            pending.append({
                "direction": "across",
                "arrow": "right",
                "clueCell": [row, start],
                "cells": [[row, column] for column in range(start + 1, start + length + 1)],
                "length": length,
            })
    for column, audit in enumerate(column_audits, start=1):
        for start, length in audit.runs:
            if length < 2:
                continue
            pending.append({
                "direction": "down",
                "arrow": "down",
                "clueCell": [start, column],
                "cells": [[row, column] for row in range(start + 1, start + length + 1)],
                "length": length,
            })
    pending.sort(key=lambda item: (
        item["clueCell"][0], item["clueCell"][1],
        0 if item["direction"] == "across" else 1,
    ))
    for index, slot in enumerate(pending):
        slot["slotIndex"] = index
        slot["slotId"] = f"{shape_id}:slot:{index:02d}"
    return pending


def _adjacency_metrics(pivots: set[tuple[int, int]]) -> tuple[int, int]:
    pairs = 0
    maximum_run = 0
    for direction in ((0, 1), (1, 0)):
        for row in range(1, ROWS):
            for column in range(1, COLUMNS):
                cell = (row, column)
                previous = (row - direction[0], column - direction[1])
                if cell not in pivots or previous in pivots:
                    continue
                run = 0
                current = cell
                while current in pivots:
                    run += 1
                    current = (current[0] + direction[0], current[1] + direction[1])
                maximum_run = max(maximum_run, run)
                pairs += max(0, run - 1)
    return pairs, maximum_run


def _build_shape(
    row_audits: tuple[LineAudit, ...],
    column_audits: tuple[LineAudit, ...],
) -> dict:
    pivots = {
        (row, column)
        for row, audit in enumerate(row_audits, start=1)
        for column, is_clue in enumerate(audit.clues, start=1)
        if is_clue
    }
    fingerprint = shape_fingerprint(pivots)
    shape_id = f"two-short-7x8-{fingerprint[:10]}"
    slots = _slots(shape_id, row_audits, column_audits)
    coverage: dict[tuple[int, int], set[str]] = defaultdict(set)
    clue_launches = Counter()
    for slot in slots:
        clue_launches[tuple(slot["clueCell"])] += 1
        for cell in slot["cells"]:
            coverage[tuple(cell)].add(slot["direction"])
    letter_cells = {
        (row, column)
        for row in range(1, ROWS)
        for column in range(1, COLUMNS)
        if (row, column) not in pivots
    }
    isolated = sorted(
        clue for clue in (_frame() | pivots) - {(0, 0)} if not clue_launches[clue]
    )
    orphan = sorted(letter_cells - set(coverage))
    if isolated or orphan:
        raise AssertionError(f"invalid accepted shape: isolated={isolated}, orphan={orphan}")
    lengths = [slot["length"] for slot in slots]
    histogram = Counter(lengths)
    if not valid_two_letter_answer_count(histogram[2]):
        raise AssertionError(f"invalid short-slot count: {histogram[2]}")
    double_covered = sum(coverage[cell] == {"across", "down"} for cell in letter_cells)
    single_axis = len(letter_cells) - double_covered
    crossing_ratio = double_covered / max(1, len(letter_cells))
    adjacency_pairs, maximum_adjacent_run = _adjacency_metrics(pivots)
    double_clues = sum(count == 2 for count in clue_launches.values())
    grammatical_cost = round(
        4.0 * histogram[2]
        + 1.5 * histogram[3]
        + 0.75 * single_axis,
        3,
    )
    length_diversity_score = round(
        12.0 * len(histogram)
        + 2.0 * sum(length >= 5 for length in lengths)
        + 2.5 * sum(length >= 6 for length in lengths)
        + sum(lengths) / max(1, len(lengths)),
        3,
    )
    crossing_potential_score = round(100.0 * crossing_ratio, 3)
    mobile_readability_score = round(max(
        0.0,
        100.0
        - 3.0 * len(pivots)
        - 9.0 * adjacency_pairs
        - 12.0 * max(0, maximum_adjacent_run - 2)
        + 2.0 * double_clues,
    ), 3)
    overall_score = round(
        0.32 * length_diversity_score
        + 0.28 * crossing_potential_score
        + 0.24 * mobile_readability_score
        - 0.16 * grammatical_cost,
        3,
    )
    cells = [{
        "cell": list(cell),
        "acrossSlotId": next((
            slot["slotId"] for slot in slots
            if slot["direction"] == "across" and list(cell) in slot["cells"]
        ), None),
        "downSlotId": next((
            slot["slotId"] for slot in slots
            if slot["direction"] == "down" and list(cell) in slot["cells"]
        ), None),
        "coveredAxes": len(coverage[cell]),
    } for cell in sorted(letter_cells)]
    return {
        "shapeId": shape_id,
        "fingerprint": fingerprint,
        "columns": COLUMNS,
        "rows": ROWS,
        "pivots": [list(cell) for cell in sorted(pivots)],
        "clueCells": [list(cell) for cell in sorted(_frame() | pivots)],
        "visualSignature": [
            "".join(
                "O" if (row, column) == (0, 0)
                else "D" if row == 0 or column == 0
                else "#" if (row, column) in pivots
                else "."
                for column in range(COLUMNS)
            )
            for row in range(ROWS)
        ],
        "slots": slots,
        "coverageAudit": {
            "valid": True,
            "letterCellCount": len(letter_cells),
            "coveredLetterCellCount": len(coverage),
            "orphanLetterCells": [],
            "isolatedClueCells": [],
            "doubleCoveredLetterCells": double_covered,
            "singleAxisLetterCells": single_axis,
            "cells": cells,
        },
        "metrics": {
            "internalClueCells": len(pivots),
            "answerCount": len(slots),
            "twoLetterAnswers": histogram[2],
            "threeLetterAnswers": histogram[3],
            "answersAtLeastFiveLetters": sum(length >= 5 for length in lengths),
            "answersAtLeastSixLetters": sum(length >= 6 for length in lengths),
            "distinctAnswerLengths": len(histogram),
            "averageAnswerLength": round(sum(lengths) / max(1, len(lengths)), 3),
            "lengthHistogram": {str(length): histogram[length] for length in sorted(histogram)},
            "doubleCoveredLetterCells": double_covered,
            "singleAxisLetterCells": single_axis,
            "crossingRatio": round(crossing_ratio, 3),
            "doubleDefinitionCells": double_clues,
            "adjacentInternalCluePairs": adjacency_pairs,
            "maximumAdjacentInternalClueRun": maximum_adjacent_run,
            "lengthDiversityScore": length_diversity_score,
            "crossingPotentialScore": crossing_potential_score,
            "mobileReadabilityScore": mobile_readability_score,
            "grammaticalCost": grammatical_cost,
            "overallScore": overall_score,
        },
    }


@lru_cache(maxsize=1)
def enumerate_shape_space() -> tuple[tuple[dict, ...], dict]:
    # A border clue must launch at least two letters. Consequently the first
    # two interior rows and columns are forced letters. Only the bottom-right
    # 5x4 rectangle can contain internal clues: exactly 20 independent bits.
    variable_positions = tuple(
        (row, column)
        for row in range(2, HEIGHT)
        for column in range(2, WIDTH)
    )
    enumerated_mask_count = 1 << len(variable_positions)
    row_audit_by_mask = {
        mask: analyze_line(tuple(bool(mask & (1 << column)) for column in range(WIDTH)))
        for mask in range(1 << WIDTH)
    }
    column_audit_by_mask = {
        mask: analyze_line(tuple(bool(mask & (1 << row)) for row in range(HEIGHT)))
        for mask in range(1 << HEIGHT)
    }
    accepted: list[dict] = []
    accepted_masks: list[int] = []
    rejected = Counter()
    structural_two_distribution = Counter()
    structurally_valid = 0

    for mask in range(enumerated_mask_count):
        row_masks = (0, 0) + tuple(
            ((mask >> (4 * row_offset)) & 0xF) << 2
            for row_offset in range(5)
        )
        column_masks = [0, 0]
        for column_offset in range(4):
            column_mask = 0
            for row_offset in range(5):
                if mask & (1 << (4 * row_offset + column_offset)):
                    column_mask |= 1 << (row_offset + 2)
            column_masks.append(column_mask)
        row_audits = tuple(row_audit_by_mask[item] for item in row_masks)
        column_audits = tuple(column_audit_by_mask[item] for item in column_masks)
        if any(audit is None for audit in (*row_audits, *column_audits)):
            raise AssertionError("forced frame letters did not produce valid lines")
        typed_rows = tuple(audit for audit in row_audits if audit is not None)
        typed_columns = tuple(audit for audit in column_audits if audit is not None)
        invalid_reason = None
        for row, row_audit in enumerate(typed_rows):
            for column, is_clue in enumerate(row_audit.clues):
                if is_clue:
                    if (
                        column not in row_audit.internal_launchers
                        and row not in typed_columns[column].internal_launchers
                    ):
                        invalid_reason = "isolated-internal-clue"
                        break
                elif (
                    column not in row_audit.covered
                    and row not in typed_columns[column].covered
                ):
                    invalid_reason = "orphan-singleton-letter"
                    break
            if invalid_reason:
                break
        if invalid_reason:
            rejected[invalid_reason] += 1
            continue
        structurally_valid += 1
        total_two = sum(
            audit.two_letter_count for audit in (*typed_rows, *typed_columns)
        )
        structural_two_distribution[total_two] += 1
        if not valid_two_letter_answer_count(total_two):
            rejected[f"two-letter-count-{total_two}"] += 1
            continue
        accepted.append(_build_shape(typed_rows, typed_columns))
        accepted_masks.append(mask)

    deduplicated = {shape["fingerprint"]: shape for shape in accepted}
    shapes = sorted(
        deduplicated.values(),
        key=lambda shape: (
            -shape["metrics"]["overallScore"],
            shape["metrics"]["grammaticalCost"],
            shape["fingerprint"],
        ),
    )
    for rank, shape in enumerate(shapes, start=1):
        shape["rank"] = rank
    assert sum(rejected.values()) + len(accepted) == enumerated_mask_count
    assert len(deduplicated) == len(accepted)
    accepted_mask_sha256 = hashlib.sha256("".join(
        f"{mask:05x}\n" for mask in accepted_masks
    ).encode("ascii")).hexdigest()
    stats = {
        "forcedLetterRows": [1, 2],
        "forcedLetterColumns": [1, 2],
        "variablePositionCount": len(variable_positions),
        "variablePositions": [[row + 1, column + 1] for row, column in variable_positions],
        "rawLayoutCount": enumerated_mask_count,
        "enumeratedMaskCount": enumerated_mask_count,
        "structurallyValidBeforeTwoLetterQuota": structurally_valid,
        "structuralTwoLetterDistribution": dict(sorted(structural_two_distribution.items())),
        "rejectedByReason": dict(sorted(rejected.items())),
        "acceptedBeforeDeduplication": len(accepted),
        "acceptedShapeCount": len(shapes),
        "duplicateFingerprintCount": len(accepted) - len(shapes),
        "acceptedPivotCountDistribution": dict(sorted(Counter(
            len(shape["pivots"]) for shape in shapes
        ).items())),
        "acceptedMaskSha256": accepted_mask_sha256,
        "symmetryPolicy": "identity-only: reflections require left/up arrows; transpose changes dimensions",
        "twoLetterDistribution": dict(sorted(Counter(
            shape["metrics"]["twoLetterAnswers"] for shape in shapes
        ).items())),
        "exhaustive": True,
    }
    return tuple(shapes), stats


def _candidate_records(document: object) -> list[dict]:
    if not isinstance(document, dict):
        return []
    records = []
    for key in ("shapes", "grids"):
        if isinstance(document.get(key), list):
            records.extend(item for item in document[key] if isinstance(item, dict))
    if not records and ("clueCells" in document or "pivots" in document):
        records.append(document)
    return records


def _record_pivots(record: dict) -> set[tuple[int, int]] | None:
    columns = int(record.get("columns", COLUMNS))
    rows = int(record.get("rows", ROWS))
    if (columns, rows) != (COLUMNS, ROWS):
        return None
    raw = record.get("pivots")
    if not isinstance(raw, list):
        raw = record.get("clueCells", [])
    return {
        (int(cell[0]), int(cell[1]))
        for cell in raw
        if isinstance(cell, list)
        and len(cell) == 2
        and int(cell[0]) > 0
        and int(cell[1]) > 0
    }


def comparison_index(path: Path) -> dict[str, list[str]]:
    if not path.is_file():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, list[str]] = defaultdict(list)
    for index, record in enumerate(_candidate_records(document), start=1):
        pivots = _record_pivots(record)
        if pivots is None:
            continue
        label = str(record.get("id") or record.get("shapeId") or f"record-{index}")
        result[shape_fingerprint(pivots)].append(label)
    return dict(result)


def _greedy_diverse_recommendations(shapes: list[dict], limit: int = 24) -> list[str]:
    if not shapes:
        return []
    selected = [shapes[0]]
    remaining = shapes[1:]
    while remaining and len(selected) < limit:
        def selection_score(shape: dict) -> tuple[float, float, str]:
            pivots = {tuple(cell) for cell in shape["pivots"]}
            distance = min(
                len(pivots ^ {tuple(cell) for cell in other["pivots"]})
                for other in selected
            )
            return (
                shape["metrics"]["overallScore"] + 2.5 * distance,
                shape["metrics"]["crossingPotentialScore"],
                shape["fingerprint"],
            )
        chosen = max(remaining, key=selection_score)
        selected.append(chosen)
        remaining = [shape for shape in remaining if shape is not chosen]
    return [shape["shapeId"] for shape in selected]


def build_payload() -> dict:
    shapes_tuple, stats = enumerate_shape_space()
    shapes = [json.loads(json.dumps(shape)) for shape in shapes_tuple]
    active = comparison_index(ACTIVE_CATALOG)
    previous_by_path = {
        str(path.relative_to(ROOT)): comparison_index(path)
        for path in PREVIOUS_LIBRARIES if path.is_file()
    }
    previous_combined: dict[str, list[str]] = defaultdict(list)
    for path, index in previous_by_path.items():
        for fingerprint, labels in index.items():
            previous_combined[fingerprint].extend(f"{path}::{label}" for label in labels)
    for shape in shapes:
        fingerprint = shape["fingerprint"]
        shape["comparison"] = {
            "activeGridIds": active.get(fingerprint, []),
            "previousLibraryReferences": previous_combined.get(fingerprint, []),
            "newVersusActiveCatalog": fingerprint not in active,
            "newVersusPreviousLibraries": fingerprint not in previous_combined,
        }
    recommended = _greedy_diverse_recommendations(shapes)
    return {
        "version": 1,
        "kind": "motman-7x8-one-or-two-two-letter-shape-library",
        "catalogModified": False,
        "runtimeModified": False,
        "publicationEligible": False,
        "contract": {
            "columns": COLUMNS,
            "rows": ROWS,
            "fullTopAndLeftClueFrame": True,
            "arrows": ["right", "down"],
            "minimumTwoLetterAnswers": MINIMUM_TWO_LETTER_ANSWERS,
            "maximumTwoLetterAnswers": MAXIMUM_TWO_LETTER_ANSWERS,
            "otherAnswerMinimumLength": 3,
            "perpendicularSingleton": "allowed-only-when-covered-by-the-other-axis",
            "orphanLetters": 0,
            "isolatedClues": 0,
        },
        "symmetry": {
            "compatibleOperations": ["identity"],
            "excludedOperations": {
                "horizontalReflection": "moves the left clue frame to the right and requires left arrows",
                "verticalReflection": "moves the top clue frame to the bottom and requires up arrows",
                "rotation180": "requires both left and up arrows",
                "transpose": "changes 7x8 into 8x7",
            },
        },
        "enumerationStats": stats,
        "comparison": {
            "activeCatalog": str(ACTIVE_CATALOG.relative_to(ROOT)),
            "active7x8GridCount": sum(len(labels) for labels in active.values()),
            "activeUniqueShapeCount": len(active),
            "matchedActiveShapeCount": sum(shape["fingerprint"] in active for shape in shapes),
            "newVersusActiveCount": sum(shape["fingerprint"] not in active for shape in shapes),
            "activeShapesOutsideNewContractCount": len(active) - sum(
                fingerprint in {shape["fingerprint"] for shape in shapes}
                for fingerprint in active
            ),
            "previousLibraries": {
                path: {
                    "recordCount": sum(len(labels) for labels in index.values()),
                    "uniqueShapeCount": len(index),
                    "matchedNewContractShapeCount": sum(
                        shape["fingerprint"] in index for shape in shapes
                    ),
                }
                for path, index in previous_by_path.items()
            },
            "newVersusEveryPreviousLibraryCount": sum(
                shape["fingerprint"] not in previous_combined for shape in shapes
            ),
        },
        "rankingPolicy": {
            "lengthDiversity": "distinct lengths plus answers of 5+ and 6+ letters",
            "crossingPotential": "ratio of letter cells covered on both axes",
            "mobileReadability": "penalises internal and adjacent clue cells",
            "grammaticalCost": "penalises 2-letter, 3-letter and single-axis cells; lower is better",
            "recommendedSelection": "greedy overall score plus pivot-set distance",
        },
        "recommendedShapeIds": recommended,
        "shapeCount": len(shapes),
        "shapes": shapes,
    }


def build_report(payload: dict) -> str:
    stats = payload["enumerationStats"]
    comparison = payload["comparison"]
    recommended = set(payload["recommendedShapeIds"])
    lines = [
        "# Silhouettes 7x8 avec une ou deux réponses de 2 lettres",
        "",
        "## Résultat certifié",
        "",
        f"- {stats['rawLayoutCount']:,} matrices brutes couvertes exhaustivement.".replace(",", " "),
        f"- {stats['enumeratedMaskCount']:,} masques réellement visités, sans cutoff.".replace(",", " "),
        f"- {stats['structurallyValidBeforeTwoLetterQuota']:,} formes passent couverture et définitions avant le quota court.".replace(",", " "),
        f"- Empreinte SHA-256 des 188 masques : `{stats['acceptedMaskSha256']}`.",
        f"- {payload['shapeCount']} silhouettes valides et {stats['duplicateFingerprintCount']} doublon exact.",
        f"- Répartition du nombre de réponses de 2 lettres : {stats['twoLetterDistribution']}.",
        "- Symétrie compatible : identité uniquement. Aucun miroir n'est fusionné, car il imposerait des flèches gauche/haut ou déplacerait le cadre.",
        "",
        "## Comparaison",
        "",
        f"- Catalogue actif : {comparison['active7x8GridCount']} grilles, {comparison['activeUniqueShapeCount']} empreintes.",
        f"- Silhouettes retrouvées dans l'actif : {comparison['matchedActiveShapeCount']}.",
        f"- Empreintes actives hors du nouveau contrat : {comparison['activeShapesOutsideNewContractCount']}.",
        f"- Silhouettes nouvelles face à l'actif : {comparison['newVersusActiveCount']}.",
        f"- Silhouettes absentes de toutes les anciennes bibliothèques : {comparison['newVersusEveryPreviousLibraryCount']}.",
        "",
        "|Ancienne bibliothèque|Entrées 7x8|Empreintes|Correspondances nouveau contrat|",
        "|---|---:|---:|---:|",
    ]
    lines.extend(
        f"|`{path}`|{metrics['recordCount']}|{metrics['uniqueShapeCount']}|{metrics['matchedNewContractShapeCount']}|"
        for path, metrics in comparison["previousLibraries"].items()
    )
    lines.extend([
        "",
        "## Classement",
        "",
        "Le score favorise les longueurs variées, les réponses longues, les vrais croisements et la lisibilité mobile. Le coût grammatical pénalise les réponses de 2/3 lettres et les cellules couvertes sur un seul axe.",
        "",
        "|Rang|ID|Pivots|Longueurs|2L|3L|≥5|Croisements|Mobile|Coût|Score|Ancienne ?|",
        "|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ])
    for shape in payload["shapes"]:
        metrics = shape["metrics"]
        marker = " ★" if shape["shapeId"] in recommended else ""
        old = "oui" if shape["comparison"]["previousLibraryReferences"] else "non"
        lines.append(
            f"|{shape['rank']}|{shape['shapeId']}{marker}|{len(shape['pivots'])}|"
            f"`{metrics['lengthHistogram']}`|{metrics['twoLetterAnswers']}|"
            f"{metrics['threeLetterAnswers']}|{metrics['answersAtLeastFiveLetters']}|"
            f"{metrics['crossingPotentialScore']:.1f}|{metrics['mobileReadabilityScore']:.1f}|"
            f"{metrics['grammaticalCost']:.1f}|{metrics['overallScore']:.1f}|{old}|"
        )
    lines.extend([
        "",
        "## Panel recommandé et diversifié",
        "",
    ])
    by_id = {shape["shapeId"]: shape for shape in payload["shapes"]}
    for shape_id in payload["recommendedShapeIds"]:
        shape = by_id[shape_id]
        lines.extend([
            f"### {shape_id} — rang {shape['rank']}",
            "",
            "```text",
            *shape["visualSignature"],
            "```",
            "",
            f"Pivots `{shape['pivots']}` — longueurs `{shape['metrics']['lengthHistogram']}` — score {shape['metrics']['overallScore']}.",
            "",
        ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    args = parser.parse_args()
    payload = build_payload()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    library = args.output_directory / "shape-library.json"
    report = args.output_directory / "report.md"
    library.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report.write_text(build_report(payload), encoding="utf-8")
    print(json.dumps({
        "library": str(library),
        "report": str(report),
        "shapeCount": payload["shapeCount"],
        "recommendedShapeIds": payload["recommendedShapeIds"],
        "comparison": payload["comparison"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
