#!/usr/bin/env python3
"""Specialized word-rectangle solver for reference-ribbon-band-04."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_reference_style_shapes_a import direct_slots, validate_geometry  # noqa: E402
from craft_flexible_common_grid import (  # noqa: E402
    active_usage,
    build_replacement_exclusions,
    load_candidates,
    load_lemma_families,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--shape",
        type=Path,
        default=ROOT
        / "src/data/grid-generation-handcrafted/reference-ribbon-band-04.shape.json",
    )
    parser.add_argument("--exclude-from", type=Path, action="append", default=[])
    parser.add_argument("--minimum-zipf", type=float, default=2.0)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--seed", type=int, default=2026071822)
    parser.add_argument("--allow-active", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    rng = random.Random(args.seed)
    shape = json.loads(args.shape.read_text(encoding="utf-8"))
    clues = {tuple(cell) for cell in shape["clueCells"]}
    raw_slots = direct_slots(clues)
    geometry = validate_geometry(shape["id"], clues, raw_slots)
    if not geometry["valid"]:
        raise SystemExit(f"Invalid shape: {geometry}")

    excluded, excluded_families = build_replacement_exclusions(
        set(), args.exclude_from, include_morphalou_forms=True
    )
    usage = active_usage()
    if not args.allow_active:
        excluded.update(usage)
    by_length, scores, spellings = load_candidates(
        args.minimum_zipf,
        excluded,
        include_child_forms=True,
        include_morphalou_forms=True,
    )
    families = load_lemma_families(True)
    words2 = tuple(by_length[2])
    words4 = tuple(by_length[4])
    words8 = tuple(by_length[8])
    words9 = tuple(by_length[9])
    prefix8: dict[str, list[str]] = defaultdict(list)
    for word in words8:
        prefix8[word[:2]].append(word)
    for words in prefix8.values():
        words.sort(key=lambda word: (-scores[word], word))
    prefix4 = {""}
    for word in words4:
        prefix4.update(word[:length] for length in range(1, 5))
    word4_set = set(words4)

    def family_unique(words: list[str]) -> bool:
        concepts = [families.get(word, word) for word in words]
        return len(concepts) == len(set(concepts))

    rectangle_nodes = 0

    def solve_rectangle(
        row_prefixes: list[str], blocked_words: set[str], blocked_families: set[str]
    ) -> tuple[list[str], list[str]] | None:
        nonlocal rectangle_nodes
        chosen_rows: list[str] = []
        column_prefixes = ["" for _ in range(6)]

        def search(row_index: int) -> tuple[list[str], list[str]] | None:
            nonlocal rectangle_nodes
            rectangle_nodes += 1
            if rectangle_nodes % 256 == 0 and time.monotonic() - started >= args.seconds:
                return None
            if row_index == 4:
                columns = list(column_prefixes)
                all_words = chosen_rows + columns
                if any(word not in word4_set for word in columns):
                    return None
                if len(set(all_words)) != len(all_words):
                    return None
                if any(families.get(word, word) in blocked_families for word in all_words):
                    return None
                if not family_unique(all_words):
                    return None
                return list(chosen_rows), columns
            candidates = prefix8.get(row_prefixes[row_index], [])
            # Frequency remains the main ordering. A small deterministic shuffle
            # inside equal-score slices makes separate seeds explore alternatives.
            for word in candidates:
                if word in blocked_words or families.get(word, word) in blocked_families:
                    continue
                if word in chosen_rows:
                    continue
                next_prefixes = [column_prefixes[index] + word[index + 2] for index in range(6)]
                if any(prefix not in prefix4 for prefix in next_prefixes):
                    continue
                previous = list(column_prefixes)
                column_prefixes[:] = next_prefixes
                chosen_rows.append(word)
                result = search(row_index + 1)
                if result is not None:
                    return result
                chosen_rows.pop()
                column_prefixes[:] = previous
                if time.monotonic() - started >= args.seconds:
                    return None
            return None

        return search(0)

    groups9: dict[str, list[str]] = defaultdict(list)
    for word in words9:
        groups9[word[4]].append(word)
    for words in groups9.values():
        words.sort(key=lambda word: (-scores[word], word))
    short_words = sorted(words2, key=lambda word: (-scores[word], word))
    pair_attempts = compatible_pairs = 0
    best_progress = 0

    # Rotate equally plausible starts across seeds without sacrificing lexical
    # quality: only the first 600 headwords of each middle-letter group are used
    # in the bounded review cycle.
    for short in short_words:
        left_group = groups9.get(short[0], [])[:600]
        right_group = groups9.get(short[1], [])[:600]
        if not left_group or not right_group:
            continue
        left_group = list(left_group)
        right_group = list(right_group)
        rng.shuffle(left_group)
        rng.shuffle(right_group)
        left_group.sort(key=lambda word: -int(scores[word] * 10))
        right_group.sort(key=lambda word: -int(scores[word] * 10))
        for left in left_group:
            for right in right_group:
                pair_attempts += 1
                if left == right or families.get(left, left) == families.get(right, right):
                    continue
                prefixes = [
                    left[position] + right[position]
                    for position in (0, 1, 2, 3, 5, 6, 7, 8)
                ]
                if any(prefix not in prefix8 for prefix in prefixes):
                    continue
                compatible_pairs += 1
                base_words = {left, right, short}
                base_families = {families.get(word, word) for word in base_words}
                top = solve_rectangle(prefixes[:4], base_words, base_families)
                if top is None:
                    if time.monotonic() - started >= args.seconds:
                        break
                    continue
                best_progress = max(best_progress, 1)
                top_words = set(top[0] + top[1])
                top_families = {families.get(word, word) for word in top_words}
                bottom = solve_rectangle(
                    prefixes[4:], base_words | top_words, base_families | top_families
                )
                if bottom is None:
                    if time.monotonic() - started >= args.seconds:
                        break
                    continue
                best_progress = 2
                # Map answers by the known slot order produced from the shape.
                top_rows, top_columns = top
                bottom_rows, bottom_columns = bottom
                answer_by_cells = {
                    tuple((row, column) for row in range(1, 10)): word
                    for column, word in ((1, left), (2, right))
                }
                for column, word in enumerate(top_columns, start=3):
                    answer_by_cells[tuple((row, column) for row in range(1, 5))] = word
                for column, word in enumerate(bottom_columns, start=3):
                    answer_by_cells[tuple((row, column) for row in range(6, 10))] = word
                for row, word in zip(range(1, 5), top_rows):
                    answer_by_cells[tuple((row, column) for column in range(1, 9))] = word
                answer_by_cells[((5, 1), (5, 2))] = short
                for row, word in zip(range(6, 10), bottom_rows):
                    answer_by_cells[tuple((row, column) for column in range(1, 9))] = word
                answers = []
                for slot_index, raw in enumerate(raw_slots):
                    cells = tuple(tuple(cell) for cell in raw["cells"])
                    answer = answer_by_cells[cells]
                    answers.append({
                        "slotIndex": slot_index,
                        "slotId": raw["slotId"],
                        "direction": raw["direction"],
                        "clueCell": raw["clueCell"],
                        "cells": raw["cells"],
                        "answer": answer,
                        "spelling": spellings[answer],
                        "zipf": scores[answer],
                        "activeUses": usage[answer],
                        "family": families.get(answer, answer),
                    })
                payload = {
                    "version": 1,
                    "kind": "specialized-two-bridge-ribbon-fill",
                    "complete": True,
                    "shapeId": shape["id"],
                    "columns": 9,
                    "rows": 10,
                    "clueCells": [list(cell) for cell in sorted(clues)],
                    "geometryAudit": geometry,
                    "lengthDistribution": {
                        str(length): sum(len(item["answer"]) == length for item in answers)
                        for length in (2, 4, 8, 9)
                    },
                    "answers": answers,
                    "telemetry": {
                        "pairAttempts": pair_attempts,
                        "compatiblePairs": compatible_pairs,
                        "rectangleNodes": rectangle_nodes,
                        "elapsedSeconds": round(time.monotonic() - started, 3),
                    },
                    "catalogModified": False,
                    "publicationEligible": False,
                }
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(json.dumps({
                    "complete": True,
                    "answers": [item["answer"] for item in answers],
                    "telemetry": payload["telemetry"],
                    "output": str(args.output),
                }, ensure_ascii=False, indent=2))
                return 0
            if time.monotonic() - started >= args.seconds:
                break
        if time.monotonic() - started >= args.seconds:
            break

    payload = {
        "version": 1,
        "kind": "specialized-two-bridge-ribbon-fill",
        "complete": False,
        "shapeId": shape["id"],
        "telemetry": {
            "pairAttempts": pair_attempts,
            "compatiblePairs": compatible_pairs,
            "rectangleNodes": rectangle_nodes,
            "bestProgress": best_progress,
            "elapsedSeconds": round(time.monotonic() - started, 3),
        },
        "catalogModified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
