#!/usr/bin/env python3
"""Refill one proven pop-culture geometry with selected answers excluded."""
from __future__ import annotations

import argparse
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--grid-id", required=True)
    parser.add_argument("--exclude-answer", action="append", default=[])
    parser.add_argument("--catalog", type=Path, default=ROOT / "src/data/grid.catalog.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=int, default=5)
    parser.add_argument("--attempts", type=int, default=30)
    parser.add_argument("--seconds", type=float, default=90.0)
    parser.add_argument("--attempt-seconds", type=float, default=4.0)
    parser.add_argument("--seed", type=int, default=2026072200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    document = json.loads(args.candidate.read_text(encoding="utf-8"))
    matches = [grid for grid in document.get("grids", []) if grid.get("id") == args.grid_id]
    if len(matches) != 1:
        raise ValueError(f"grille introuvable ou ambiguë: {args.grid_id}")
    source = matches[0]
    pop_answer = str(source.get("fixedPopAnswer") or "")
    if pop_answer not in POP_CLUES:
        raise ValueError("ancre pop absente")
    pop_item = next(item for item in source["answers"] if item["answer"] == pop_answer)
    pop_raw_slot = source["rawSlots"][int(pop_item["slotIndex"])]
    pivots = {
        tuple(cell) for cell in source["clueCells"] if tuple(cell) not in FRAME
    }
    clue_cells, raw_slots, slots = build_slots(7, 8, pivots)
    pop_slot = next(
        index for index, slot in enumerate(slots)
        if slot.clue_cell == tuple(pop_raw_slot["clueCell"])
        and slot.cells == tuple(tuple(cell) for cell in pop_raw_slot["cells"])
        and slot.direction == pop_raw_slot["direction"]
    )

    unavailable = excluded_answers([args.catalog])
    unavailable.update(args.exclude_answer)
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    unavailable.update(blacklist.get("rejectedAnswers", []))
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

    started = time.monotonic()
    accepted: list[dict] = []
    seen_answer_sets: set[tuple[str, ...]] = set()
    rejection_counts: dict[str, int] = defaultdict(int)
    for attempt in range(args.attempts):
        if len(accepted) >= args.target or time.monotonic() - started >= args.seconds:
            break
        telemetry: dict = {}
        solution = fill_bitset(
            slots,
            indexes,
            random.Random(args.seed + attempt),
            None,
            unavailable_answers=unavailable,
            max_grammar_answers=2,
            grammar_answers=GRAMMAR_ANSWERS,
            max_seconds=args.attempt_seconds,
            node_limit=8_000_000,
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
            max_undesirable_answers=5,
            solution_limit=512,
            explore_randomly=True,
            telemetry=telemetry,
        )
        if solution is None:
            rejection_counts[telemetry.get("reason", "fill-failed")] += 1
            continue
        values = tuple(solution[index] for index in sorted(solution))
        if values in seen_answer_sets:
            rejection_counts["duplicate-solution"] += 1
            continue
        seen_answer_sets.add(values)
        accepted.append({
            "id": f"compact-7x8-pop-refill-{len(accepted) + 1:02d}",
            "columns": 7,
            "rows": 8,
            "sourceShapeId": source.get("sourceShapeId", ""),
            "sourceCandidate": args.candidate.as_posix(),
            "sourceCandidateGridId": args.grid_id,
            "clueCells": clue_cells,
            "rawSlots": raw_slots,
            "answers": [
                {"slotIndex": index, "answer": solution[index], **metadata[solution[index]]}
                for index in sorted(solution)
            ],
            "fixedPopAnswer": pop_answer,
            "solverTelemetry": telemetry,
        })

    payload = {
        "version": 1,
        "kind": "compact-7x8-pop-candidate-refills",
        "complete": len(accepted) >= args.target,
        "catalogModified": False,
        "acceptedCount": len(accepted),
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "excludedAnswers": sorted(set(args.exclude_answer)),
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
