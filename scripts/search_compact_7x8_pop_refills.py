#!/usr/bin/env python3
"""Refill owner-approved 7x8 geometries with fresh, lightly pop-cultural words."""
from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

from bitset_grid_filler import fill_bitset
from search_compact_7x8_batch import (
    AVOID,
    GRAMMAR_ANSWERS,
    POP_CLUES,
    central_index,
    excluded_answers,
    expand_unavailable_by_family,
)
from search_compact_grid_pilot import build_slots, normalized


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=ROOT / "src/data/grid.catalog.json")
    parser.add_argument("--exclude-catalog", type=Path, action="append", default=[])
    parser.add_argument("--allow-repeat-answer", action="append", default=[])
    parser.add_argument(
        "--allow-active-answer-max-length",
        type=int,
        default=0,
        help=(
            "Autorise comme charnières les réponses actives de cette longueur "
            "maximale lorsqu'elles n'apparaissent qu'une fois."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=int, default=12)
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--shape-seconds", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=2026071910)
    parser.add_argument("--wordfreq-minimum", type=float, default=2.6)
    parser.add_argument(
        "--lexicon-scope",
        choices=("central", "central-large", "central-hybrid", "lexical-full", "full"),
        default="full",
    )
    parser.add_argument("--maximum-grammar-answers", type=int, default=2)
    parser.add_argument("--maximum-undesirable-answers", type=int, default=1)
    parser.add_argument("--maximum-active-repeats", type=int, default=0)
    parser.add_argument("--anchors-per-shape", type=int, default=14)
    parser.add_argument("--pop-answer", action="append", default=[])
    parser.add_argument("--allow-plain", action="store_true")
    return parser.parse_args()


def approved_shapes(catalog: dict) -> list[dict]:
    frame = {(0, column) for column in range(7)} | {(row, 0) for row in range(1, 8)}
    result: list[dict] = []
    seen: set[tuple[tuple[int, int], ...]] = set()
    for grid in catalog.get("grids", []):
        pivots = sorted(
            tuple(cell) for cell in grid.get("clueCells", [])
            if tuple(cell) not in frame
        )
        fingerprint = tuple(pivots)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        clue_cells, raw_slots, slots = build_slots(7, 8, set(pivots))
        result.append({
            "sourceShapeId": grid["id"],
            "pivots": pivots,
            "clueCells": clue_cells,
            "rawSlots": raw_slots,
            "slots": slots,
        })
    return result


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    rng = random.Random(args.seed)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    active_answer_counts = Counter(
        str(word.get("answer", ""))
        for grid in catalog.get("grids", [])
        for word in grid.get("words", [])
        if word.get("answer")
    )
    active_answers = set(active_answer_counts)
    # Keep active answers available to the CSP only as a tightly bounded
    # fallback. They are marked undesirable below and reported explicitly;
    # the preferred result remains zero repeat.
    unavailable = excluded_answers(args.exclude_catalog)
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    unavailable.update(blacklist.get("rejectedAnswers", []))
    unavailable.update(
        item.get("answer", "") if isinstance(item, dict) else str(item)
        for item in blacklist.get("rotationCooldownAnswers", [])
    )
    blocked_by_policy = set(AVOID)
    blocked_by_policy.update(blacklist.get("rejectedAnswers", []))
    blocked_by_policy.update(
        item.get("answer", "") if isinstance(item, dict) else str(item)
        for item in blacklist.get("rotationCooldownAnswers", [])
    )
    allowed_repeats = {
        normalized(answer)
        for answer in args.allow_repeat_answer
        if normalized(answer) and normalized(answer) not in blocked_by_policy
    }
    if args.allow_active_answer_max_length > 0:
        allowed_repeats.update(
            answer
            for answer, count in active_answer_counts.items()
            if count == 1
            and len(answer) <= args.allow_active_answer_max_length
            and answer not in blocked_by_policy
        )
    unavailable.difference_update(allowed_repeats)
    unavailable.discard("")
    indexes, metadata, family_answers, all_families = central_index(
        unavailable, args.wordfreq_minimum, args.lexicon_scope
    )
    families = indexes[3]
    unavailable = expand_unavailable_by_family(
        unavailable, {**families, **all_families}, family_answers
    )

    shapes = approved_shapes(catalog)
    rng.shuffle(shapes)
    requested_anchors = [answer.upper() for answer in args.pop_answer]
    unknown_anchors = sorted(set(requested_anchors) - set(POP_CLUES))
    if unknown_anchors:
        raise ValueError(f"Références pop inconnues: {unknown_anchors}")
    anchors = [
        answer for answer in (requested_anchors or list(POP_CLUES))
        if answer not in unavailable
    ]
    accepted: list[dict] = []
    used_shape_ids: set[str] = set()
    rejection_counts: dict[str, int] = defaultdict(int)
    for round_index in range(4):
        if len(accepted) >= args.target or time.monotonic() - started >= args.seconds:
            break
        for shape in shapes:
            if len(accepted) >= args.target or time.monotonic() - started >= args.seconds:
                break
            if shape["sourceShapeId"] in used_shape_ids:
                continue
            slots = shape["slots"]
            variants: list[tuple[int | None, str | None]] = []
            anchor_order = anchors[:]
            rng.shuffle(anchor_order)
            for answer in anchor_order:
                matching = [
                    index for index, slot in enumerate(slots)
                    if len(slot.cells) == len(answer)
                ]
                rng.shuffle(matching)
                variants.extend((index, answer) for index in matching[:2])
                if len(variants) >= args.anchors_per_shape:
                    break
            rng.shuffle(variants)
            selected_variants = variants[: args.anchors_per_shape]
            if args.allow_plain:
                selected_variants.append((None, None))
            solution = None
            chosen_anchor = None
            last_telemetry: dict = {}
            for slot_index, anchor in selected_variants:
                if time.monotonic() - started >= args.seconds:
                    break
                last_telemetry = {}
                solution = fill_bitset(
                    slots,
                    indexes,
                    rng,
                    None,
                    unavailable_answers=unavailable,
                    max_grammar_answers=args.maximum_grammar_answers,
                    grammar_answers=GRAMMAR_ANSWERS,
                    max_seconds=args.shape_seconds,
                    node_limit=5_000_000,
                    require_image=False,
                    fixed_answers={slot_index: anchor} if slot_index is not None else {},
                    prefer_constraint_support=True,
                    constraint_support_bucket_size=3,
                    branching_strategy="cell",
                    quality_scores=indexes[2],
                    answer_families=families,
                    undesirable_answers=active_answers | {
                        answer for answer, item in metadata.items()
                        if item.get("wordfreqZipf", 0.0) < 2.5 and answer not in POP_CLUES
                    },
                    max_undesirable_answers=(
                        args.maximum_undesirable_answers + args.maximum_active_repeats
                    ),
                    solution_limit=192,
                    explore_randomly=True,
                    telemetry=last_telemetry,
                )
                if solution is not None:
                    chosen_anchor = anchor
                    break
            if solution is None:
                rejection_counts[last_telemetry.get("reason", "no-anchor-fit")] += 1
                continue

            answer_values = [solution[index] for index in sorted(solution)]
            solution_families = [families.get(answer, answer) for answer in answer_values]
            if len(set(solution_families)) != len(answer_values):
                rejection_counts["family-repeat"] += 1
                continue
            answers = [
                {"slotIndex": index, "answer": solution[index], **metadata[solution[index]]}
                for index in sorted(solution)
            ]
            active_repeats = sorted(set(answer_values) & active_answers)
            non_allowed_active_repeats = sorted(
                set(active_repeats) - allowed_repeats
            )
            if len(non_allowed_active_repeats) > args.maximum_active_repeats:
                rejection_counts["too-many-active-repeats"] += 1
                continue
            accepted.append({
                "id": f"compact-7x8-young-raw-{len(accepted) + 1:02d}",
                "columns": 7,
                "rows": 8,
                "sourceShapeId": shape["sourceShapeId"],
                "sourceShapePivots": [list(cell) for cell in shape["pivots"]],
                "clueCells": shape["clueCells"],
                "rawSlots": shape["rawSlots"],
                "answers": answers,
                "fixedPopAnswer": chosen_anchor,
                "activeRepeats": active_repeats,
                "nonAllowedActiveRepeats": non_allowed_active_repeats,
                "solverTelemetry": last_telemetry,
            })
            used_shape_ids.add(shape["sourceShapeId"])
            for answer, family in zip(answer_values, solution_families, strict=True):
                unavailable.update(family_answers.get(family, {answer}))
            anchors = [answer for answer in anchors if answer not in unavailable]

    payload = {
        "version": 1,
        "kind": "compact-7x8-approved-shape-pop-refills",
        "complete": len(accepted) >= args.target,
        "catalogModified": False,
        "acceptedCount": len(accepted),
        "allowedRepeatAnswers": sorted(allowed_repeats),
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
            {
                "shape": grid["sourceShapeId"],
                "pop": grid["fixedPopAnswer"],
                "answers": [item["answer"] for item in grid["answers"]],
            }
            for grid in accepted
        ],
    }, ensure_ascii=False, indent=2))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
