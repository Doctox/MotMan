#!/usr/bin/env python3
"""Break rejected raw answers with clue cells while preserving the pop answer path."""
from __future__ import annotations

import argparse
import itertools
import json
import random
import time
from collections import defaultdict
from pathlib import Path

from bitset_grid_filler import fill_bitset
from search_compact_7x8_batch import (
    GRAMMAR_ANSWERS,
    POP_CLUES,
    central_index,
    excluded_answers,
    expand_unavailable_by_family,
)
from search_compact_grid_pilot import build_slots


ROOT = Path(__file__).resolve().parents[1]
FRAME = {(0, column) for column in range(7)} | {(row, 0) for row in range(1, 8)}
INTERIOR = {(row, column) for row in range(1, 8) for column in range(1, 7)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--grid-id", required=True)
    parser.add_argument("--bad-answer", action="append", default=[])
    parser.add_argument("--catalog", type=Path, default=ROOT / "src/data/grid.catalog.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=int, default=5)
    parser.add_argument("--attempts", type=int, default=600)
    parser.add_argument("--seconds", type=float, default=90.0)
    parser.add_argument("--shape-seconds", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=2026071990)
    return parser.parse_args()


def load_grid(path: Path, grid_id: str) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    grids = document.get("grids", [])
    matches = [grid for grid in grids if grid.get("id") == grid_id]
    if len(matches) != 1:
        raise ValueError(f"grille introuvable ou ambiguë: {grid_id}")
    return matches[0]


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    rng = random.Random(args.seed)
    source = load_grid(args.candidate, args.grid_id)
    pop_answer = str(source.get("fixedPopAnswer") or "")
    if pop_answer not in POP_CLUES:
        raise ValueError("la candidate ne contient pas d'ancre pop reconnue")
    answer_by_value = {item["answer"]: item for item in source["answers"]}
    pop_item = answer_by_value[pop_answer]
    pop_raw_slot = source["rawSlots"][int(pop_item["slotIndex"])]
    pop_clue = tuple(pop_raw_slot["clueCell"])
    pop_cells = tuple(tuple(cell) for cell in pop_raw_slot["cells"])
    protected = set(pop_cells) | {pop_clue}
    bad_values = set(args.bad_answer)
    missing = bad_values - set(answer_by_value)
    if missing:
        raise ValueError(f"réponses à réparer absentes: {sorted(missing)}")
    bad_slots = [
        source["rawSlots"][int(answer_by_value[answer]["slotIndex"])]
        for answer in sorted(bad_values)
    ]
    choices = []
    for slot in bad_slots:
        eligible = [
            tuple(cell) for cell in slot["cells"]
            if tuple(cell) not in protected
            and (cell[0] <= 5 or cell[1] <= 4)
        ]
        if not eligible:
            raise ValueError(f"aucune case cassable pour {slot['slotId']}")
        choices.append(eligible)

    unavailable = excluded_answers([args.catalog])
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    unavailable.update(blacklist.get("rejectedAnswers", []))
    unavailable.update(bad_values)
    unavailable.update(
        item.get("answer", "") if isinstance(item, dict) else str(item)
        for item in blacklist.get("rotationCooldownAnswers", [])
    )
    unavailable.discard("")
    indexes, metadata, family_answers, all_families = central_index(
        unavailable, 2.0, "full"
    )
    families = indexes[3]
    unavailable = expand_unavailable_by_family(
        unavailable, {**families, **all_families}, family_answers
    )

    base_pivots = {
        tuple(cell) for cell in source.get("clueCells", [])
        if tuple(cell) not in FRAME
    }
    accepted: list[dict] = []
    seen_shapes: set[tuple[tuple[int, int], ...]] = set()
    rejection_counts: dict[str, int] = defaultdict(int)
    for _attempt in range(args.attempts):
        if len(accepted) >= args.target or time.monotonic() - started >= args.seconds:
            break
        pivots = set(base_pivots)
        pivots.update(rng.choice(group) for group in choices)
        extras = list(INTERIOR - protected - pivots)
        if extras and rng.random() < 0.6:
            pivots.update(rng.sample(extras, rng.choice((1, 1, 2))))
        fingerprint = tuple(sorted(pivots))
        if fingerprint in seen_shapes:
            continue
        seen_shapes.add(fingerprint)
        try:
            clue_cells, raw_slots, slots = build_slots(7, 8, pivots)
        except ValueError:
            rejection_counts["invalid-shape"] += 1
            continue
        lengths = [len(slot.cells) for slot in slots]
        if (
            not 12 <= len(slots) <= 22
            or lengths.count(2) > 4
            or sum(length <= 3 for length in lengths) > 9
        ):
            rejection_counts["shape-policy"] += 1
            continue
        pop_slot = next((
            index for index, slot in enumerate(slots)
            if slot.clue_cell == pop_clue
            and slot.cells == pop_cells
            and slot.direction == pop_raw_slot["direction"]
        ), None)
        if pop_slot is None:
            rejection_counts["pop-path-changed"] += 1
            continue
        telemetry: dict = {}
        solution = fill_bitset(
            slots,
            indexes,
            rng,
            None,
            unavailable_answers=unavailable,
            max_grammar_answers=2,
            grammar_answers=GRAMMAR_ANSWERS,
            max_seconds=args.shape_seconds,
            node_limit=5_000_000,
            fixed_answers={pop_slot: pop_answer},
            prefer_constraint_support=True,
            constraint_support_bucket_size=3,
            branching_strategy="cell",
            quality_scores=indexes[2],
            answer_families=families,
            undesirable_answers={
                answer for answer, item in metadata.items()
                if item.get("wordfreqZipf", 0.0) < 2.4 and answer not in POP_CLUES
            },
            max_undesirable_answers=4,
            solution_limit=192,
            explore_randomly=True,
            telemetry=telemetry,
        )
        if solution is None:
            rejection_counts[telemetry.get("reason", "fill-failed")] += 1
            continue
        answers = [
            {"slotIndex": index, "answer": solution[index], **metadata[solution[index]]}
            for index in sorted(solution)
        ]
        accepted.append({
            "id": f"compact-7x8-pop-repaired-{len(accepted) + 1:02d}",
            "columns": 7,
            "rows": 8,
            "sourceShapeId": f"targeted-repair-{pop_answer.lower()}",
            "sourceCandidate": args.candidate.as_posix(),
            "sourceCandidateGridId": args.grid_id,
            "removedAnswers": sorted(bad_values),
            "clueCells": clue_cells,
            "rawSlots": raw_slots,
            "answers": answers,
            "fixedPopAnswer": pop_answer,
            "solverTelemetry": telemetry,
        })

    payload = {
        "version": 1,
        "kind": "compact-7x8-targeted-pop-repairs",
        "complete": len(accepted) >= args.target,
        "catalogModified": False,
        "acceptedCount": len(accepted),
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "rejectionCounts": dict(sorted(rejection_counts.items())),
        "grids": accepted,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "complete": payload["complete"],
        "acceptedCount": len(accepted),
        "elapsedSeconds": payload["elapsedSeconds"],
        "rejectionCounts": payload["rejectionCounts"],
        "answers": [[item["answer"] for item in grid["answers"]] for grid in accepted],
    }, ensure_ascii=False, indent=2))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
