#!/usr/bin/env python3
"""Sample a broad strict-frame mask pool before expensive lexical filling."""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import craft_flexible_common_grid as craft  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=723500)
    parser.add_argument("--samples", type=int, default=100000)
    parser.add_argument("--limit", type=int, default=800)
    parser.add_argument("--minimum-internal", type=int, default=4)
    parser.add_argument("--maximum-internal", type=int, default=10)
    parser.add_argument("--maximum-two-letter", type=int, default=2)
    parser.add_argument("--maximum-three-letter", type=int, default=6)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def sample_pool(
    rng: random.Random,
    samples: int,
    minimum_internal: int,
    maximum_internal: int,
    maximum_two_letter: int,
    maximum_three_letter: int,
) -> list[tuple[tuple, set, list, dict]]:
    free_zone = [
        (row, column)
        for row in range(3, craft.ROWS)
        for column in range(3, craft.COLUMNS)
    ]
    candidates: dict[tuple, tuple[tuple, set, list, dict]] = {}
    for _attempt in range(samples):
        count = rng.randint(minimum_internal, maximum_internal)
        internal = set(rng.sample(free_zone, count))
        clues = craft.FRAME | internal
        fingerprint = tuple(sorted(clues))
        if fingerprint in candidates:
            continue
        raw_slots = craft.direct_slots(clues)
        lengths = [slot["length"] for slot in raw_slots]
        if (
            not lengths
            or min(lengths) < 2
            or lengths.count(2) > maximum_two_letter
            or lengths.count(3) > maximum_three_letter
        ):
            continue
        audit = craft.validate_geometry("strict-frame-search", clues, raw_slots)
        if not audit.get("valid"):
            continue
        adjacency = sum(
            (row + 1, column) in internal
            or (row, column + 1) in internal
            for row, column in internal
        )
        long_answers = sum(length >= 5 for length in lengths)
        length_variety = len(set(lengths))
        score = (
            lengths.count(2),
            lengths.count(3),
            adjacency,
            abs(len(internal) - 7),
            -long_answers,
            -length_variety,
            fingerprint,
        )
        candidates[fingerprint] = (score, clues, raw_slots, audit)
    return sorted(candidates.values(), key=lambda item: item[0])


def main() -> int:
    args = parse_args()
    sampled = sample_pool(
        random.Random(args.seed),
        args.samples,
        args.minimum_internal,
        args.maximum_internal,
        args.maximum_two_letter,
        args.maximum_three_letter,
    )
    by_internal_count: dict[int, list] = {}
    for item in sampled:
        by_internal_count.setdefault(len(item[1] - craft.FRAME), []).append(item)
    pool = []
    counts = sorted(by_internal_count)
    while len(pool) < args.limit and any(by_internal_count.values()):
        for count in counts:
            if by_internal_count[count] and len(pool) < args.limit:
                pool.append(by_internal_count[count].pop(0))
    grids = []
    for index, (_score, clues, raw_slots, audit) in enumerate(pool, 1):
        shape_id = f"strict-frame-search-{index:04d}"
        grids.append({
            "id": shape_id,
            "columns": craft.COLUMNS,
            "rows": craft.ROWS,
            "clueCells": [list(cell) for cell in sorted(clues)],
            "rawSlots": raw_slots,
            "geometryAudit": {**audit, "sourceShapeId": shape_id},
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({
            "version": 1,
            "kind": "strict-frame-search-pool",
            "seed": args.seed,
            "policy": {
                "topRowAllDefinitions": True,
                "leftColumnAllDefinitions": True,
                "maximumTwoLetterAnswers": args.maximum_two_letter,
                "maximumThreeLetterAnswers": args.maximum_three_letter,
                "orphanLettersAllowed": False,
            },
            "grids": grids,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "validSampled": len(pool),
        "byInternalCount": {
            str(count): sum(
                len(item[1] - craft.FRAME) == count for item in pool
            )
            for count in counts
        },
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if pool else 1


if __name__ == "__main__":
    raise SystemExit(main())
