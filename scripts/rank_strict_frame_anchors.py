#!/usr/bin/env python3
"""Rank strict-frame corner rectangles by real support in every boundary slot."""
from __future__ import annotations

import argparse
import gzip
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_large_lexical_batch import is_editorially_confirmed  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wordlist", type=Path, default=ROOT / "src/data/fill.wordlist.large.json.gz")
    parser.add_argument("--shapes", type=Path, required=True)
    parser.add_argument("--shape-id", required=True)
    parser.add_argument("--samples", type=int, default=500000)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--minimum-anchor-score", type=float, default=20.0)
    parser.add_argument("--maximum-unconfirmed-boundaries", type=int, default=2)
    parser.add_argument("--seed", type=int, default=724100)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def rank_candidates(
    entries: list[dict],
    raw_slots: list[dict],
    samples: int,
    minimum_anchor_score: float,
    maximum_unconfirmed_boundaries: int,
    rng: random.Random,
) -> list[dict]:
    confirmed = {
        entry["answer"]: entry
        for entry in entries
        if is_editorially_confirmed(entry["answer"], entry)
    }
    by_length_prefix: dict[int, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    all_by_length_prefix: dict[int, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for entry in entries:
        answer = entry["answer"]
        if 2 <= len(answer) <= 9:
            all_by_length_prefix[len(answer)][answer[:2]].append(answer)
    for answer, entry in confirmed.items():
        if 2 <= len(answer) <= 9:
            by_length_prefix[len(answer)][answer[:2]].append(answer)
    anchor8 = {
        prefix: [
            answer for answer in answers
            if float(confirmed[answer].get("constructorScore", 0.0))
            >= minimum_anchor_score
        ]
        for prefix, answers in by_length_prefix[8].items()
    }
    anchor9 = [
        answer for answer, entry in confirmed.items()
        if len(answer) == 9
        and float(entry.get("constructorScore", 0.0)) >= minimum_anchor_score
    ]
    index_by_launch = {
        (slot["direction"], tuple(slot["clueCell"]), slot["length"]): index
        for index, slot in enumerate(raw_slots)
    }
    required = {
        "across1": ("across", (1, 0), 8),
        "across2": ("across", (2, 0), 8),
        "down1": ("down", (0, 1), 9),
        "down2": ("down", (0, 2), 9),
    }
    if any(launch not in index_by_launch for launch in required.values()):
        return []
    boundary_slots = [
        (index, slot)
        for index, slot in enumerate(raw_slots)
        if (slot["direction"] == "down" and slot["clueCell"][0] == 0 and slot["clueCell"][1] >= 3)
        or (slot["direction"] == "across" and slot["clueCell"][1] == 0 and slot["clueCell"][0] >= 3)
    ]
    best: dict[tuple[str, ...], dict] = {}
    for _attempt in range(samples):
        down1 = rng.choice(anchor9)
        down2 = rng.choice(anchor9)
        if down1 == down2:
            continue
        across1_options = anchor8.get(down1[0] + down2[0], [])
        across2_options = anchor8.get(down1[1] + down2[1], [])
        if not across1_options or not across2_options:
            continue
        across1 = rng.choice(across1_options)
        across2 = rng.choice(across2_options)
        anchors = (across1, across2, down1, down2)
        if len(set(anchors)) != 4 or anchors in best:
            continue
        supports = []
        prefix_details = []
        unconfirmed_boundaries = 0
        viable = True
        for slot_index, slot in boundary_slots:
            row, column = slot["clueCell"]
            if slot["direction"] == "down":
                prefix = across1[column - 1] + across2[column - 1]
            else:
                prefix = down1[row - 1] + down2[row - 1]
            options = by_length_prefix[slot["length"]].get(prefix, [])
            options = [answer for answer in options if answer not in anchors]
            if not options:
                options = [
                    answer
                    for answer in all_by_length_prefix[slot["length"]].get(prefix, [])
                    if answer not in anchors
                ]
                unconfirmed_boundaries += 1
                if (
                    not options
                    or unconfirmed_boundaries > maximum_unconfirmed_boundaries
                ):
                    viable = False
                    break
            supports.append(len(options))
            prefix_details.append({
                "slotIndex": slot_index,
                "length": slot["length"],
                "prefix": prefix,
                "support": len(options),
                "confirmed": all(
                    answer in confirmed for answer in options
                ),
            })
        if not viable:
            continue
        score = (
            -unconfirmed_boundaries,
            min(supports),
            sum(math.log1p(value) for value in supports),
            sum(float(confirmed[word].get("constructorScore", 0.0)) for word in anchors),
        )
        best[anchors] = {
            "answers": {
                str(index_by_launch[required["across1"]]): across1,
                str(index_by_launch[required["across2"]]): across2,
                str(index_by_launch[required["down1"]]): down1,
                str(index_by_launch[required["down2"]]): down2,
            },
            "anchorWords": list(anchors),
            "unconfirmedBoundaries": unconfirmed_boundaries,
            "minimumBoundarySupport": score[1],
            "logBoundarySupport": round(score[2], 4),
            "anchorScoreTotal": round(score[3], 2),
            "prefixes": prefix_details,
            "_score": score,
        }
    ranked = sorted(best.values(), key=lambda item: item["_score"], reverse=True)
    for item in ranked:
        item.pop("_score", None)
    return ranked


def main() -> int:
    args = parse_args()
    with gzip.open(args.wordlist, "rt", encoding="utf-8") as handle:
        wordlist = json.load(handle)
    shapes = json.loads(args.shapes.read_text(encoding="utf-8"))
    shape = next(grid for grid in shapes["grids"] if grid["id"] == args.shape_id)
    ranked = rank_candidates(
        wordlist["entries"],
        shape["rawSlots"],
        args.samples,
        args.minimum_anchor_score,
        args.maximum_unconfirmed_boundaries,
        random.Random(args.seed),
    )[: args.limit]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "version": 1,
        "kind": "strict-frame-supported-anchor-candidates",
        "shapeId": args.shape_id,
        "samples": args.samples,
        "minimumAnchorScore": args.minimum_anchor_score,
        "maximumUnconfirmedBoundaries": args.maximum_unconfirmed_boundaries,
        "candidates": ranked,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "shapeId": args.shape_id,
        "ranked": len(ranked),
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if ranked else 1


if __name__ == "__main__":
    raise SystemExit(main())
