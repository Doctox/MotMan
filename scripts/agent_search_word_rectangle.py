#!/usr/bin/env python3
"""Bounded word-first search for a complete 9x10 arrowword grid.

The top row and left column are clue cells.  The 9x8 letter rectangle is
filled as nine horizontal eight-letter answers whose eight columns are valid
nine-letter answers.  This chooses the words before introducing any interior
pivot, and therefore cannot create orphan letters or undeclared visual runs.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_flexible_batch_candidates import load_lemma_map  # noqa: E402
from craft_flexible_common_grid import load_candidates  # noqa: E402


class TrieNode:
    __slots__ = ("children", "word")

    def __init__(self) -> None:
        self.children: dict[str, TrieNode] = {}
        self.word: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=240.0)
    parser.add_argument("--minimum-zipf", type=float, default=2.7)
    parser.add_argument("--seed", type=int, default=719220)
    parser.add_argument("--reference", action="append", type=Path, default=[])
    return parser.parse_args()


def extract_reference_answers(paths: list[Path]) -> set[str]:
    result: set[str] = set()
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        grid = document.get("grid")
        if not isinstance(grid, dict):
            grids = document.get("grids") or []
            grid = grids[0] if grids else document
        for item in grid.get("answers") or grid.get("words") or []:
            answer = str(item.get("answer", "")).upper()
            if answer:
                result.add(answer)
    return result


def build_trie(words: list[str]) -> TrieNode:
    root = TrieNode()
    for word in words:
        node = root
        for letter in word:
            node = node.children.setdefault(letter, TrieNode())
        node.word = word
    return root


def slots_and_answers(rows: list[str], columns: list[str], scores: dict[str, float]) -> dict:
    answers = []
    slot_index = 0
    for column, answer in enumerate(columns, start=1):
        answers.append({
            "slotIndex": slot_index,
            "slotId": f"slot-{slot_index + 1:02d}",
            "direction": "down",
            "clueCell": [0, column],
            "cells": [[row, column] for row in range(1, 10)],
            "answer": answer,
            "spelling": answer.lower(),
            "zipf": scores[answer],
            "activeUses": 0,
        })
        slot_index += 1
    for row, answer in enumerate(rows, start=1):
        answers.append({
            "slotIndex": slot_index,
            "slotId": f"slot-{slot_index + 1:02d}",
            "direction": "across",
            "clueCell": [row, 0],
            "cells": [[row, column] for column in range(1, 9)],
            "answer": answer,
            "spelling": answer.lower(),
            "zipf": scores[answer],
            "activeUses": 0,
        })
        slot_index += 1
    clue_cells = [[0, column] for column in range(9)] + [
        [row, 0] for row in range(1, 10)
    ]
    return {
        "id": "agent-word-first-free-01",
        "sourceShapeGridId": "full-word-rectangle-9x8",
        "clueCells": clue_cells,
        "internalClueCells": [],
        "lengthDistribution": {"8": 9, "9": 8},
        "geometryAudit": {"valid": True, "errors": []},
        "answers": answers,
    }


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    rng = random.Random(args.seed)
    lemmas = load_lemma_map()
    reference_answers = extract_reference_answers(args.reference)
    reference_families = {lemmas.get(answer, answer) for answer in reference_answers}
    excluded = set(reference_answers)
    by_length, scores, _spellings = load_candidates(
        args.minimum_zipf, excluded, include_child_forms=False
    )
    row_words = [
        word for word in by_length[8]
        if lemmas.get(word, word) not in reference_families
    ]
    column_words = [
        word for word in by_length[9]
        if lemmas.get(word, word) not in reference_families
    ]
    trie = build_trie(column_words)

    char_masks: list[dict[str, int]] = [dict() for _ in range(8)]
    for index, word in enumerate(row_words):
        bit = 1 << index
        for position, letter in enumerate(word):
            char_masks[position][letter] = char_masks[position].get(letter, 0) | bit
    all_mask = (1 << len(row_words)) - 1
    attempts = 0
    nodes_visited = 0
    solution_rows: list[str] | None = None
    solution_columns: list[str] | None = None

    def dfs(rows: list[str], column_nodes: list[TrieNode], used_families: set[str]) -> bool:
        nonlocal nodes_visited, solution_rows, solution_columns
        nodes_visited += 1
        if nodes_visited % 2048 == 0 and time.monotonic() - started >= args.seconds:
            return False
        if len(rows) == 9:
            columns = [node.word for node in column_nodes]
            if any(word is None for word in columns):
                return False
            completed = [str(word) for word in columns]
            families = [lemmas.get(word, word) for word in completed]
            if len(set(completed + rows)) != 17:
                return False
            if len(set(families) | used_families) != len(families) + len(used_families):
                return False
            solution_rows = list(rows)
            solution_columns = completed
            return True

        mask = all_mask
        for position, node in enumerate(column_nodes):
            allowed = 0
            for letter in node.children:
                allowed |= char_masks[position].get(letter, 0)
            mask &= allowed
            if not mask:
                return False
        candidates: list[int] = []
        while mask:
            least = mask & -mask
            candidates.append(least.bit_length() - 1)
            mask ^= least
        rng.shuffle(candidates)
        candidates.sort(key=lambda index: scores[row_words[index]], reverse=True)
        # Keep common words first, but vary enough to escape one deterministic
        # prefix basin on subsequent restarts.
        if len(candidates) > 48:
            head = candidates[:24]
            tail = candidates[24:]
            rng.shuffle(tail)
            candidates = head + tail
        for index in candidates:
            word = row_words[index]
            family = lemmas.get(word, word)
            if word in rows or family in used_families:
                continue
            next_nodes = [
                column_nodes[position].children[word[position]]
                for position in range(8)
            ]
            if dfs(rows + [word], next_nodes, used_families | {family}):
                return True
            if time.monotonic() - started >= args.seconds:
                return False
        return False

    while time.monotonic() - started < args.seconds and solution_rows is None:
        attempts += 1
        dfs([], [trie] * 8, set())

    payload = {
        "version": 1,
        "kind": "agent-word-first-full-rectangle",
        "columns": 9,
        "rows": 10,
        "catalogModified": False,
        "publicationEligible": False,
        "minimumZipf": args.minimum_zipf,
        "candidateCounts": {"8": len(row_words), "9": len(column_words)},
        "attempts": attempts,
        "nodesVisited": nodes_visited,
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "complete": solution_rows is not None,
        "grid": (
            slots_and_answers(solution_rows, solution_columns, scores)
            if solution_rows is not None and solution_columns is not None
            else None
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "complete": payload["complete"],
        "attempts": attempts,
        "nodesVisited": nodes_visited,
        "answers": (
            [item["answer"] for item in payload["grid"]["answers"]]
            if payload["grid"] else None
        ),
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if payload["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
