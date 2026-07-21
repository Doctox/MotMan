#!/usr/bin/env python3
"""Mutate clue cells around a fixed pop-culture answer, then refill from scratch."""
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
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--catalog", type=Path, default=ROOT / "src/data/grid.catalog.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=int, default=12)
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--shape-seconds", type=float, default=1.5)
    parser.add_argument("--mutations-per-anchor", type=int, default=80)
    parser.add_argument("--seed", type=int, default=2026071930)
    parser.add_argument("--wordfreq-minimum", type=float, default=2.7)
    parser.add_argument(
        "--lexicon-scope",
        choices=("central", "central-large", "central-hybrid", "full"),
        default="full",
    )
    return parser.parse_args()


def anchor_sources(paths: list[Path]) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple[str, tuple[tuple[int, int], ...]]] = set()
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        for grid in document.get("grids", []):
            answer = str(grid.get("fixedPopAnswer") or "")
            if answer not in POP_CLUES:
                continue
            item = next(
                (value for value in grid.get("answers", []) if value.get("answer") == answer),
                None,
            )
            if item is None:
                continue
            raw_slot = grid["rawSlots"][int(item["slotIndex"])]
            pivots = tuple(sorted(
                tuple(cell) for cell in grid.get("clueCells", [])
                if tuple(cell) not in FRAME
            ))
            key = (answer, pivots)
            if key in seen:
                continue
            seen.add(key)
            result.append({
                "answer": answer,
                "baseGridId": grid["id"],
                "baseSource": path.as_posix(),
                "basePivots": set(pivots),
                "direction": raw_slot["direction"],
                "clueCell": tuple(raw_slot["clueCell"]),
                "cells": tuple(tuple(cell) for cell in raw_slot["cells"]),
            })
    return result


def matching_anchor_slot(slots: list, anchor: dict) -> int | None:
    for index, slot in enumerate(slots):
        if (
            slot.direction == anchor["direction"]
            and slot.clue_cell == anchor["clueCell"]
            and slot.cells == anchor["cells"]
        ):
            return index
    return None


def acceptable_shape(clue_cells: list[list[int]], slots: list) -> bool:
    lengths = [len(slot.cells) for slot in slots]
    pivots = [tuple(cell) for cell in clue_cells if tuple(cell) not in FRAME]
    adjacent_pairs = sum(
        abs(first[0] - second[0]) + abs(first[1] - second[1]) == 1
        for first, second in itertools.combinations(pivots, 2)
    )
    return (
        12 <= len(slots) <= 22
        and lengths.count(2) <= 3
        and sum(length <= 3 for length in lengths) <= 8
        and adjacent_pairs <= 8
    )


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    rng = random.Random(args.seed)
    anchors = anchor_sources(args.input)
    rng.shuffle(anchors)

    unavailable = excluded_answers([args.catalog])
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
        unavailable, args.wordfreq_minimum, args.lexicon_scope
    )
    families = indexes[3]
    unavailable = expand_unavailable_by_family(
        unavailable, {**families, **all_families}, family_answers
    )

    accepted: list[dict] = []
    rejection_counts: dict[str, int] = defaultdict(int)
    seen_shapes: set[tuple[tuple[int, int], ...]] = set()
    used_pop: set[str] = set()
    for anchor in anchors:
        if len(accepted) >= args.target or time.monotonic() - started >= args.seconds:
            break
        if anchor["answer"] in used_pop:
            continue
        protected = set(anchor["cells"]) | {anchor["clueCell"]}
        removable = list(anchor["basePivots"] - {anchor["clueCell"]})
        addable = list(INTERIOR - protected - anchor["basePivots"])
        for _mutation in range(args.mutations_per_anchor):
            if len(accepted) >= args.target or time.monotonic() - started >= args.seconds:
                break
            pivots = set(anchor["basePivots"])
            if removable and rng.random() < 0.35:
                pivots.remove(rng.choice(removable))
            add_count = rng.choices((1, 2, 3, 4), weights=(2, 5, 4, 1), k=1)[0]
            pivots.update(rng.sample(addable, add_count))
            fingerprint = tuple(sorted(pivots))
            if fingerprint in seen_shapes:
                continue
            seen_shapes.add(fingerprint)
            try:
                clue_cells, raw_slots, slots = build_slots(7, 8, pivots)
            except ValueError:
                rejection_counts["invalid-shape"] += 1
                continue
            if not acceptable_shape(clue_cells, slots):
                rejection_counts["shape-policy"] += 1
                continue
            anchor_slot = matching_anchor_slot(slots, anchor)
            if anchor_slot is None:
                rejection_counts["anchor-path-changed"] += 1
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
                node_limit=4_000_000,
                require_image=False,
                fixed_answers={anchor_slot: anchor["answer"]},
                prefer_constraint_support=True,
                constraint_support_bucket_size=3,
                branching_strategy="cell",
                quality_scores=indexes[2],
                answer_families=families,
                undesirable_answers={
                    answer for answer, item in metadata.items()
                    if item.get("wordfreqZipf", 0.0) < 2.6 and answer not in POP_CLUES
                },
                max_undesirable_answers=1,
                solution_limit=192,
                explore_randomly=True,
                telemetry=telemetry,
            )
            if solution is None:
                rejection_counts[telemetry.get("reason", "fill-failed")] += 1
                continue
            answer_values = [solution[index] for index in sorted(solution)]
            solution_families = [families.get(answer, answer) for answer in answer_values]
            if len(solution_families) != len(set(solution_families)):
                rejection_counts["family-repeat"] += 1
                continue
            answers = [
                {"slotIndex": index, "answer": solution[index], **metadata[solution[index]]}
                for index in sorted(solution)
            ]
            accepted.append({
                "id": f"compact-7x8-young-mutated-{len(accepted) + 1:02d}",
                "columns": 7,
                "rows": 8,
                "sourceShapeId": f"pop-mutation-{anchor['answer'].lower()}",
                "sourceAnchor": {
                    "answer": anchor["answer"],
                    "baseGridId": anchor["baseGridId"],
                    "baseSource": anchor["baseSource"],
                    "direction": anchor["direction"],
                    "clueCell": list(anchor["clueCell"]),
                    "cells": [list(cell) for cell in anchor["cells"]],
                },
                "clueCells": clue_cells,
                "rawSlots": raw_slots,
                "answers": answers,
                "fixedPopAnswer": anchor["answer"],
                "solverTelemetry": telemetry,
            })
            used_pop.add(anchor["answer"])
            for answer, family in zip(answer_values, solution_families, strict=True):
                unavailable.update(family_answers.get(family, {answer}))
            break

    payload = {
        "version": 1,
        "kind": "compact-7x8-pop-shape-mutations",
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
        "grids": [
            {"pop": grid["fixedPopAnswer"], "answers": [x["answer"] for x in grid["answers"]]}
            for grid in accepted
        ],
    }, ensure_ascii=False, indent=2))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
