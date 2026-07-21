#!/usr/bin/env python3
"""Bounded 7x8 strict-frame search using the reviewed French construction lexicon."""

from __future__ import annotations

import argparse
import gzip
import json
import random
import time
import unicodedata
from pathlib import Path

from wordfreq import iter_wordlist, zipf_frequency

from build_compact_7x8_review import family_key


ROOT = Path(__file__).resolve().parents[1]


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.upper())
    return "".join(character for character in folded if "A" <= character <= "Z")


class TrieNode:
    __slots__ = ("children", "word")

    def __init__(self) -> None:
        self.children: dict[str, TrieNode] = {}
        self.word: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=45.0)
    parser.add_argument("--minimum-zipf", type=float, default=2.8)
    parser.add_argument("--minimum-constructor-score", type=float, default=15.0)
    parser.add_argument("--lexicon", choices=("large", "wordfreq"), default="large")
    parser.add_argument("--seed", type=int, default=719700)
    parser.add_argument("--reference", action="append", type=Path, default=[])
    return parser.parse_args()


def reference_answers(paths: list[Path]) -> set[str]:
    result: set[str] = set()
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        grids = document.get("grids")
        if not isinstance(grids, list):
            grids = [document.get("grid") or document]
        for grid in grids:
            for item in grid.get("words") or grid.get("answers") or []:
                answer = normalize(str(item.get("answer", "")))
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


def grid_payload(rows: list[str], columns: list[str], metadata: dict[str, dict]) -> dict:
    raw_slots = []
    answers = []
    for column, answer in enumerate(columns, 1):
        cells = [[row, column] for row in range(1, 8)]
        index = len(raw_slots)
        raw_slots.append({
            "slotId": f"slot-{index + 1:02d}", "direction": "down", "arrow": "down",
            "clueCell": [0, column], "cells": cells, "length": 7,
        })
        answers.append({"slotIndex": index, "answer": answer, **metadata[answer]})
    for row, answer in enumerate(rows, 1):
        cells = [[row, column] for column in range(1, 7)]
        index = len(raw_slots)
        raw_slots.append({
            "slotId": f"slot-{index + 1:02d}", "direction": "across", "arrow": "right",
            "clueCell": [row, 0], "cells": cells, "length": 6,
        })
        answers.append({"slotIndex": index, "answer": answer, **metadata[answer]})
    return {
        "columns": 7,
        "rows": 8,
        "sourceShapeId": "compact-7x8-strict-frame",
        "clueCells": [[0, column] for column in range(7)] + [[row, 0] for row in range(1, 8)],
        "rawSlots": raw_slots,
        "answers": answers,
    }


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    excluded = reference_answers(args.reference)
    blacklist = json.loads((ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8"))
    excluded.update(blacklist.get("rejectedAnswers", []))

    metadata: dict[str, dict] = {}
    families: dict[str, str] = {}
    if args.lexicon == "large":
        with gzip.open(ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8") as stream:
            entries = json.load(stream).get("entries", [])
        for item in entries:
            answer = normalize(str(item.get("answer", "")))
            if answer in metadata or answer in excluded or len(answer) not in {6, 7}:
                continue
            spelling = str(item.get("spelling") or answer.lower())
            frequency = float(zipf_frequency(spelling, "fr"))
            score = float(item.get("constructorScore", 0.0))
            if (
                not item.get("attestedCommonForm", False)
                or frequency < args.minimum_zipf
                or score < args.minimum_constructor_score
            ):
                continue
            lemma = normalize(str(item.get("lemma") or answer))
            metadata[answer] = {
                "spelling": spelling,
                "lemma": lemma,
                "wordfreqZipf": frequency,
                "constructorScore": score,
            }
            families[answer] = family_key(lemma)
    else:
        for spelling in iter_wordlist("fr"):
            frequency = float(zipf_frequency(spelling, "fr"))
            if frequency < args.minimum_zipf:
                break
            if not spelling.isalpha():
                continue
            answer = normalize(spelling)
            if answer in metadata or answer in excluded or len(answer) not in {6, 7}:
                continue
            metadata[answer] = {
                "spelling": spelling,
                "lemma": answer,
                "wordfreqZipf": frequency,
                "constructorScore": frequency,
            }
            families[answer] = family_key(answer)

    excluded_families = {family_key(answer) for answer in excluded}
    rows = [
        answer for answer in metadata
        if len(answer) == 6 and families[answer] not in excluded_families
    ]
    columns = [
        answer for answer in metadata
        if len(answer) == 7 and families[answer] not in excluded_families
    ]
    rng = random.Random(args.seed)
    rng.shuffle(rows)
    rows.sort(key=lambda answer: metadata[answer]["wordfreqZipf"], reverse=True)
    trie = build_trie(columns)

    char_masks: list[dict[str, int]] = [dict() for _ in range(6)]
    for index, word in enumerate(rows):
        bit = 1 << index
        for position, letter in enumerate(word):
            char_masks[position][letter] = char_masks[position].get(letter, 0) | bit
    all_mask = (1 << len(rows)) - 1
    nodes = 0
    solution_rows: list[str] | None = None
    solution_columns: list[str] | None = None

    def dfs(chosen: list[str], nodes_by_column: list[TrieNode], used_families: set[str]) -> bool:
        nonlocal nodes, solution_rows, solution_columns
        nodes += 1
        if nodes % 1024 == 0 and time.monotonic() - started >= args.seconds:
            return False
        if len(chosen) == 7:
            completed = [node.word for node in nodes_by_column]
            if any(word is None for word in completed):
                return False
            completed_words = [str(word) for word in completed]
            completed_families = [families[word] for word in completed_words]
            if len(set(completed_families) | used_families) != len(completed_families) + len(used_families):
                return False
            solution_rows = list(chosen)
            solution_columns = completed_words
            return True

        mask = all_mask
        for position, node in enumerate(nodes_by_column):
            allowed = 0
            for letter in node.children:
                allowed |= char_masks[position].get(letter, 0)
            mask &= allowed
            if not mask:
                return False
        candidates = []
        while mask:
            bit = mask & -mask
            candidates.append(bit.bit_length() - 1)
            mask ^= bit
        candidates.sort(
            key=lambda index: (
                metadata[rows[index]]["wordfreqZipf"],
                metadata[rows[index]]["constructorScore"],
                rng.random(),
            ),
            reverse=True,
        )
        for index in candidates:
            word = rows[index]
            family = families[word]
            if word in chosen or family in used_families:
                continue
            next_nodes = [nodes_by_column[position].children[word[position]] for position in range(6)]
            if dfs(chosen + [word], next_nodes, used_families | {family}):
                return True
            if time.monotonic() - started >= args.seconds:
                return False
        return False

    dfs([], [trie] * 6, set())
    complete = solution_rows is not None and solution_columns is not None
    payload = {
        "version": 1,
        "kind": "compact-7x8-strict-frame-search",
        "catalogModified": False,
        "publicationEligible": False,
        "complete": complete,
        "minimumZipf": args.minimum_zipf,
        "minimumConstructorScore": args.minimum_constructor_score,
        "lexicon": args.lexicon,
        "candidateCounts": {"6": len(rows), "7": len(columns)},
        "solverTelemetry": {
            "nodes": nodes,
            "elapsedSeconds": round(time.monotonic() - started, 3),
            "reason": "solved" if complete else "timeout-or-infeasible",
        },
    }
    if complete:
        payload.update(grid_payload(solution_rows, solution_columns, metadata))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "complete": complete,
        "answers": [item["answer"] for item in payload.get("answers", [])],
        "telemetry": payload["solverTelemetry"],
    }, ensure_ascii=False, indent=2))
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
