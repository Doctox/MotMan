#!/usr/bin/env python3
"""Word-first 9x10 search with row words and pivots chosen together.

Each interior row is either one 8-letter answer, a 3-letter answer followed by
a double-definition pivot and a 4-letter answer, or the symmetric 4+3 form.
Vertical answers are validated incrementally against the same reviewed corpus.
This construction makes every letter part of a declared across and down entry.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_flexible_batch_candidates import load_lemma_map  # noqa: E402
from craft_flexible_common_grid import load_candidates  # noqa: E402


@dataclass(frozen=True)
class RowOption:
    pattern: str
    answers: tuple[str, ...]
    families: tuple[str, ...]
    priority: float
    images: int
    shorts: int


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=240.0)
    parser.add_argument("--seed", type=int, default=719600)
    parser.add_argument("--minimum-zipf", type=float, default=2.0)
    parser.add_argument("--exclude-active", action="store_true")
    parser.add_argument("--exclude-from", action="append", type=Path, default=[])
    parser.add_argument("--minimum-images", type=int, default=3)
    return parser.parse_args()


def grid_answers(path: Path) -> set[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if path.name == "grid.catalog.json":
        return {
            str(item.get("answer", "")).upper()
            for grid in document.get("grids", [])
            for item in grid.get("words", [])
            if item.get("answer")
        }
    grid = document.get("grid")
    if not isinstance(grid, dict):
        grids = document.get("grids") or []
        grid = grids[0] if grids else document
    return {
        str(item.get("answer", "")).upper()
        for item in grid.get("answers") or grid.get("words") or []
        if item.get("answer")
    }


def main() -> int:
    args = arguments()
    started = time.monotonic()
    rng = random.Random(args.seed)
    lemmas = load_lemma_map()
    excluded_answers: set[str] = set()
    for path in args.exclude_from:
        excluded_answers.update(grid_answers(path))
    if args.exclude_active:
        excluded_answers.update(grid_answers(ROOT / "src/data/grid.catalog.json"))
    blocked_families = {lemmas.get(answer, answer) for answer in excluded_answers}
    by_length, scores, _ = load_candidates(
        args.minimum_zipf,
        excluded_answers,
        include_child_forms=False,
    )
    for length in by_length:
        by_length[length] = tuple(
            answer for answer in by_length[length]
            if lemmas.get(answer, answer) not in blocked_families
        )

    image_doc = json.loads(
        (ROOT / "src/data/crossword.images-reviewed.json").read_text(encoding="utf-8")
    )
    image_answers = {
        item["answer"] for item in image_doc.get("entries", [])
        if isinstance(item.get("image"), dict)
    }

    valid_words = {word for words in by_length.values() for word in words}
    prefixes: dict[str, set[str]] = {}
    for word in valid_words:
        for size in range(len(word)):
            prefixes.setdefault(word[:size], set()).add(word[size])

    options: list[RowOption] = []
    for word in by_length[8]:
        family = lemmas.get(word, word)
        options.append(RowOption(
            word, (word,), (family,), scores[word] + (4 if word in image_answers else 0),
            int(word in image_answers), 0,
        ))
    for left_size in (2, 3, 4, 5):
        right_size = 7 - left_size
        for left in by_length[left_size]:
            left_family = lemmas.get(left, left)
            for right in by_length[right_size]:
                right_family = lemmas.get(right, right)
                if left == right or left_family == right_family:
                    continue
                pattern = left + "#" + right
                images = int(left in image_answers) + int(right in image_answers)
                options.append(RowOption(
                    pattern,
                    (left, right),
                    (left_family, right_family),
                    (scores[left] + scores[right]) / 2 + images * 4,
                    images,
                    int(left_size == 2) + int(right_size == 2),
                ))
    options.sort(key=lambda item: item.priority, reverse=True)

    char_masks: list[dict[str, int]] = [dict() for _ in range(8)]
    full_row_mask = 0
    for index, option in enumerate(options):
        bit = 1 << index
        if "#" not in option.pattern:
            full_row_mask |= bit
        for position, char in enumerate(option.pattern):
            char_masks[position][char] = char_masks[position].get(char, 0) | bit
    all_mask = (1 << len(options)) - 1
    nodes = 0
    solution: tuple[list[RowOption], list[list[str]]] | None = None

    def search(
        row_index: int,
        current: tuple[str, ...],
        chosen: list[RowOption],
        families: set[str],
        vertical_words: list[list[str]],
        short_count: int,
        image_count: int,
    ) -> bool:
        nonlocal nodes, solution
        nodes += 1
        if nodes % 1024 == 0 and time.monotonic() - started >= args.seconds:
            return False
        if row_index == 9:
            completed = [list(words) for words in vertical_words]
            final_families = set(families)
            final_short = short_count
            final_images = image_count
            for column, word in enumerate(current):
                if word not in valid_words:
                    return False
                family = lemmas.get(word, word)
                if family in final_families:
                    return False
                final_families.add(family)
                completed[column].append(word)
                final_short += int(len(word) == 2)
                final_images += int(word in image_answers)
            if final_short > 2 or final_images < args.minimum_images:
                return False
            solution = (list(chosen), completed)
            return True

        mask = full_row_mask if row_index >= 7 else all_mask
        for position, prefix in enumerate(current):
            allowed_mask = 0
            for letter in prefixes.get(prefix, ()):
                allowed_mask |= char_masks[position].get(letter, 0)
            if prefix in valid_words and len(prefix) >= 2 and short_count + int(len(prefix) == 2) <= 2:
                allowed_mask |= char_masks[position].get("#", 0)
            mask &= allowed_mask
            if not mask:
                return False

        candidate_indexes: list[int] = []
        while mask and len(candidate_indexes) < 5000:
            bit = mask & -mask
            candidate_indexes.append(bit.bit_length() - 1)
            mask ^= bit
        # Options were pre-sorted by editorial/image priority. Slightly vary
        # the first page between seeds without preferring rare tail entries.
        head = candidate_indexes[:80]
        rng.shuffle(head)
        candidate_indexes[:80] = head
        candidate_indexes.sort(
            key=lambda index: options[index].priority + rng.random() * 0.05,
            reverse=True,
        )
        for index in candidate_indexes:
            option = options[index]
            if any(family in families for family in option.families):
                continue
            next_current: list[str] = []
            next_vertical = [list(words) for words in vertical_words]
            next_families = set(families) | set(option.families)
            next_short = short_count
            next_short += option.shorts
            next_images = image_count + option.images
            valid = True
            for column, char in enumerate(option.pattern):
                if char == "#":
                    word = current[column]
                    family = lemmas.get(word, word)
                    if word not in valid_words or family in next_families:
                        valid = False
                        break
                    next_families.add(family)
                    next_vertical[column].append(word)
                    next_short += int(len(word) == 2)
                    next_images += int(word in image_answers)
                    next_current.append("")
                else:
                    next_current.append(current[column] + char)
            if not valid or next_short > 2:
                continue
            if search(
                row_index + 1,
                tuple(next_current),
                chosen + [option],
                next_families,
                next_vertical,
                next_short,
                next_images,
            ):
                return True
            if time.monotonic() - started >= args.seconds:
                return False
        return False

    search(0, ("",) * 8, [], set(), [[] for _ in range(8)], 0, 0)
    payload: dict = {
        "version": 1,
        "kind": "agent-word-first-dynamic-pivots",
        "columns": 9,
        "rows": 10,
        "catalogModified": False,
        "publicationEligible": False,
        "complete": solution is not None,
        "minimumZipf": args.minimum_zipf,
        "candidateCounts": {str(k): len(v) for k, v in by_length.items()},
        "rowOptionCount": len(options),
        "nodesVisited": nodes,
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "grid": None,
    }
    if solution:
        rows, vertical_by_column = solution
        clue_cells = {(0, column) for column in range(9)} | {
            (row, 0) for row in range(1, 10)
        }
        raw_answers = []
        vertical_starts: list[tuple[int, int, str]] = []
        for column, words in enumerate(vertical_by_column, start=1):
            row = 1
            for word in words:
                vertical_starts.append((row - 1, column, word))
                row += len(word) + 1
        for row_index, option in enumerate(rows, start=1):
            if "#" not in option.pattern:
                raw_answers.append(("across", (row_index, 0), option.answers[0]))
            else:
                pivot_column = option.pattern.index("#") + 1
                clue_cells.add((row_index, pivot_column))
                raw_answers.append(("across", (row_index, 0), option.answers[0]))
                raw_answers.append(("across", (row_index, pivot_column), option.answers[1]))
        raw_answers.extend(("down", (row, column), word) for row, column, word in vertical_starts)
        answers = []
        for index, (direction, clue_cell, answer) in enumerate(raw_answers):
            dr, dc = ((0, 1) if direction == "across" else (1, 0))
            cells = [
                [clue_cell[0] + dr * step, clue_cell[1] + dc * step]
                for step in range(1, len(answer) + 1)
            ]
            answers.append({
                "slotIndex": index,
                "slotId": f"slot-{index + 1:02d}",
                "direction": direction,
                "clueCell": list(clue_cell),
                "cells": cells,
                "answer": answer,
                "spelling": answer.lower(),
                "zipf": scores[answer],
                "activeUses": 0,
            })
        payload["grid"] = {
            "id": f"agent-dynamic-pivots-{args.seed}",
            "sourceShapeGridId": "word-first-dynamic",
            "clueCells": [list(cell) for cell in sorted(clue_cells)],
            "internalClueCells": [
                list(cell) for cell in sorted(clue_cells)
                if cell[0] > 0 and cell[1] > 0
            ],
            "answers": answers,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "complete": payload["complete"],
        "nodesVisited": nodes,
        "rowOptionCount": len(options),
        "answers": [item["answer"] for item in payload["grid"]["answers"]] if payload["grid"] else None,
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if solution else 2


if __name__ == "__main__":
    raise SystemExit(main())
