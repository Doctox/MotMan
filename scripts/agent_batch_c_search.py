#!/usr/bin/env python3
"""Search one full-frame 9x10 owner-review candidate with image answers.

This agent-owned helper never writes to the catalogue.  It reuses the exact
geometry and bitset filler used by the accepted flexible-grid prototype, while
requiring a distinct clue-cell fingerprint and at least three Twemoji answers.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bitset_grid_filler import fill_bitset  # noqa: E402
from craft_flexible_common_grid import (  # noqa: E402
    FRAME,
    Slot,
    active_usage,
    catalog_shape_candidates,
    load_candidates,
    shape_candidate,
)


def family(answer: str) -> str:
    """Conservative family key for the lemma-only placement pool."""
    return answer[:-1] if len(answer) >= 4 and answer.endswith(("S", "X")) else answer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=930_000)
    parser.add_argument("--seconds", type=float, default=300.0)
    parser.add_argument("--seconds-per-shape", type=float, default=6.0)
    parser.add_argument("--minimum-zipf", type=float, default=3.0)
    parser.add_argument("--minimum-images", type=int, default=3)
    parser.add_argument("--exclude-answer", action="append", default=[])
    args = parser.parse_args()

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    owner_audit = json.loads(
        (ROOT / "output/quality/owner-low-short-02.audit.json").read_text(encoding="utf-8")
    )
    owner_grid = owner_audit["grids"][0]
    owner_fingerprint = tuple(sorted(
        (cell["row"], cell["col"])
        for cell in owner_grid["cells"] if cell["kind"] in {"clue", "neutral"}
    ))

    usage = active_usage()
    explicit_exclusions = {
        answer.strip().upper() for answer in args.exclude_answer if answer.strip()
    }
    words_by_length, scores, spellings = load_candidates(
        args.minimum_zipf, explicit_exclusions, include_child_forms=False
    )
    asset_by_answer = {
        path.stem.upper(): f"/assets/clues/twemoji/{path.name}"
        for path in (ROOT / "public/assets/clues/twemoji").glob("*.svg")
    }
    image_answers = set(scores).intersection(asset_by_answer)
    indexes = (
        words_by_length,
        None,
        scores,
        {answer: answer for answer in scores},
        {answer: set() for answer in scores},
        {answer: "normal" for answer in scores},
        image_answers,
    )
    rng = random.Random(args.seed)
    started = time.monotonic()
    attempts = 0
    valid_shapes = 0
    rejections: Counter[str] = Counter()
    solution = None
    selected = None
    telemetry = {}

    bases = catalog_shape_candidates(rng)
    candidates = [
        (source_id, clues, raw_slots, slots, audit)
        for source_id, clues, raw_slots, slots, audit in bases
    ]

    while time.monotonic() - started < args.seconds:
        if candidates:
            source_id, clues, raw_slots, slots, audit = candidates.pop()
        else:
            candidate = shape_candidate(rng, attempts + 1)
            if candidate is None:
                attempts += 1
                rejections["geometry"] += 1
                continue
            clues, raw_slots, slots, audit = candidate
            source_id = None
        attempts += 1
        fingerprint = tuple(sorted(clues))
        if fingerprint == owner_fingerprint:
            rejections["owner-silhouette"] += 1
            continue
        lengths = [slot.length for slot in slots]
        if lengths.count(2) > 2:
            rejections["too-many-two-letter-slots"] += 1
            continue
        if any(not words_by_length.get(length) for length in lengths):
            rejections["missing-length-domain"] += 1
            continue
        image_lengths = Counter(len(answer) for answer in image_answers)
        if sum(image_lengths[length] > 0 for length in lengths) < args.minimum_images:
            rejections["insufficient-image-capable-slots"] += 1
            continue
        valid_shapes += 1
        current_telemetry: dict = {}
        result = fill_bitset(
            slots,
            indexes,
            random.Random(args.seed + attempts),
            None,
            answer_usage={
                answer: usage[answer] * 100_000 + int(1_000 - scores[answer] * 100)
                for answer in scores
            },
            max_grammar_answers=99,
            grammar_answers=set(),
            max_seconds=min(
                args.seconds_per_shape,
                max(0.05, args.seconds - (time.monotonic() - started)),
            ),
            node_limit=30_000_000,
            require_image=True,
            minimum_images=args.minimum_images,
            prefer_constraint_support=True,
            constraint_support_bucket_size=2,
            telemetry=current_telemetry,
        )
        telemetry = current_telemetry
        if result is None:
            rejections[f"fill-{current_telemetry.get('reason', 'failed')}"] += 1
            continue
        values = list(result.values())
        families = [family(answer) for answer in values]
        if len(families) != len(set(families)):
            rejections["morphological-family"] += 1
            continue
        selected_images = [answer for answer in values if answer in image_answers]
        if len(selected_images) < args.minimum_images:
            rejections["minimum-images"] += 1
            continue
        solution = result
        selected = (source_id, clues, raw_slots, slots, audit)
        break

    payload = {
        "version": 1,
        "kind": "agent-batch-c-image-grid-search",
        "catalogModified": False,
        "seed": args.seed,
        "minimumZipf": args.minimum_zipf,
        "minimumImages": args.minimum_images,
        "explicitExclusions": sorted(explicit_exclusions),
        "availableImageAnswers": len(image_answers),
        "attempts": attempts,
        "validShapesTried": valid_shapes,
        "rejectionCounts": dict(sorted(rejections.items())),
        "lastTelemetry": telemetry,
        "complete": solution is not None,
        "grid": None,
    }
    if solution is not None and selected is not None:
        source_id, clues, raw_slots, slots, audit = selected
        answers = [
            {
                "slotIndex": index,
                "slotId": slots[index].slot_id,
                "direction": slots[index].direction,
                "clueCell": list(slots[index].clue_cell),
                "cells": [list(cell) for cell in slots[index].cells],
                "answer": answer,
                "spelling": spellings[answer],
                "zipf": scores[answer],
                "activeUses": usage[answer],
                "image": asset_by_answer.get(answer),
            }
            for index, answer in sorted(solution.items())
        ]
        payload["grid"] = {
            "id": f"agent-batch-c-{args.seed}",
            "columns": 9,
            "rows": 10,
            "sourceShapeGridId": source_id,
            "clueCells": [list(cell) for cell in sorted(clues)],
            "internalClueCells": [list(cell) for cell in sorted(clues - FRAME)],
            "ownerSilhouetteDistinct": tuple(sorted(clues)) != owner_fingerprint,
            "lengthDistribution": dict(sorted(Counter(map(len, solution.values())).items())),
            "geometryAudit": audit,
            "rawSlots": raw_slots,
            "answers": answers,
        }
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "complete": payload["complete"],
        "attempts": attempts,
        "validShapesTried": valid_shapes,
        "answers": (
            [item["answer"] for item in payload["grid"]["answers"]]
            if payload["grid"] else None
        ),
        "images": (
            [item["answer"] for item in payload["grid"]["answers"] if item["image"]]
            if payload["grid"] else None
        ),
        "output": str(output),
    }, ensure_ascii=False, indent=2))
    return 0 if solution is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
