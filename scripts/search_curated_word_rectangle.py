#!/usr/bin/env python3
"""Search a 7x8 frame grid as a curated 7-row by 6-column word rectangle.

The search only proposes geometry-compatible answer sets.  It deliberately
keeps words requiring editorial review in the report instead of turning the
first technical closure into a publishable grid.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict
from pathlib import Path

from build_compact_7x8_review import family_key
from construct_semimanual_7x8 import (
    DEFAULT_CATALOG,
    DEFAULT_RESCUE,
    load_candidates,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output/quality/semi-manual-7x8-candidate/curated-rectangle.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rescue", type=Path, default=DEFAULT_RESCUE)
    parser.add_argument("--reference-catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-zipf", type=float, default=3.2)
    parser.add_argument("--seconds", type=float, default=240.0)
    parser.add_argument("--row-limit", type=int, default=3200)
    parser.add_argument("--column-limit", type=int, default=3600)
    parser.add_argument("--branch-limit", type=int, default=260)
    parser.add_argument("--solution-limit", type=int, default=200)
    parser.add_argument("--seed", type=int, default=270722)
    return parser.parse_args()


def allowed_source(metadata: dict) -> bool:
    return metadata.get("source") not in {
        "inflected-review-required",
        "proper-name-review-required",
    }


def main() -> int:
    args = parse_args()
    pools, current_answers, usage = load_candidates(args)
    rows = [
        word for word, metadata in pools[6].items()
        if allowed_source(metadata)
    ]
    columns = [
        word for word, metadata in pools[7].items()
        if allowed_source(metadata)
    ]
    rows.sort(key=lambda word: (-pools[6][word]["score"], word))
    columns.sort(key=lambda word: (-pools[7][word]["score"], word))
    rows = rows[: args.row_limit]
    columns = columns[: args.column_limit]

    prefix_words: dict[int, dict[str, list[str]]] = {
        length: defaultdict(list) for length in range(8)
    }
    next_letters: dict[int, dict[str, set[str]]] = {
        length: defaultdict(set) for length in range(7)
    }
    for word in columns:
        for length in range(8):
            prefix_words[length][word[:length]].append(word)
        for length in range(7):
            next_letters[length][word[:length]].add(word[length])

    row_by_position_letter: dict[tuple[int, str], set[str]] = defaultdict(set)
    for word in rows:
        for position, letter in enumerate(word):
            row_by_position_letter[(position, letter)].add(word)

    rng = random.Random(args.seed)
    deadline = time.perf_counter() + args.seconds
    nodes = 0
    solutions: list[dict] = []

    def candidate_rows(depth: int, prefixes: tuple[str, ...]) -> list[str]:
        domains: list[set[str]] = []
        for position, prefix in enumerate(prefixes):
            letters = next_letters[depth].get(prefix, set())
            if not letters:
                return []
            domain: set[str] = set()
            for letter in letters:
                domain.update(row_by_position_letter[(position, letter)])
            domains.append(domain)
        domains.sort(key=len)
        result = set(domains[0])
        for domain in domains[1:]:
            result.intersection_update(domain)
            if not result:
                break
        return list(result)

    def recurse(depth: int, prefixes: tuple[str, ...], selected: list[str], families: set[str]) -> None:
        nonlocal nodes
        if time.perf_counter() >= deadline or len(solutions) >= args.solution_limit:
            return
        if depth == 7:
            column_words = list(prefixes)
            answers = [*selected, *column_words]
            if len(set(answers)) != len(answers):
                return
            answer_families = [family_key(answer) for answer in answers]
            if len(set(answer_families)) != len(answer_families):
                return
            current = sorted(set(answers) & current_answers)
            active_repeats = sorted(answer for answer in answers if usage.get(answer, 0))
            lexical_score = sum(pools[len(answer)][answer]["score"] for answer in answers)
            solutions.append({
                "score": round(lexical_score + 180.0 * len(current) - 24.0 * len(active_repeats), 3),
                "rows": list(selected),
                "columns": column_words,
                "currentAnswers": current,
                "activeRepeats": active_repeats,
            })
            return

        candidates = candidate_rows(depth, prefixes)
        ranked = []
        for word in candidates:
            family = family_key(word)
            if family in families:
                continue
            next_prefixes = tuple(prefixes[index] + word[index] for index in range(6))
            support = [len(prefix_words[depth + 1][prefix]) for prefix in next_prefixes]
            if min(support, default=0) == 0:
                continue
            current_bonus = 1 if word in current_answers else 0
            jitter = rng.random()
            ranked.append((
                -current_bonus,
                -min(support),
                -sum(support),
                -pools[6][word]["score"],
                jitter,
                word,
                family,
                next_prefixes,
            ))
        ranked.sort()
        limit = args.branch_limit if depth < 4 else max(args.branch_limit, 1000)
        for *_rank, word, family, next_prefixes in ranked[:limit]:
            nodes += 1
            recurse(depth + 1, next_prefixes, [*selected, word], families | {family})
            if time.perf_counter() >= deadline or len(solutions) >= args.solution_limit:
                return

    recurse(0, ("", "", "", "", "", ""), [], set())
    solutions.sort(key=lambda item: (-len(item["currentAnswers"]), len(item["activeRepeats"]), -item["score"]))
    for solution in solutions:
        answers = [*solution["rows"], *solution["columns"]]
        solution["metadata"] = {answer: pools[len(answer)][answer] for answer in answers}
    payload = {
        "version": 1,
        "kind": "motman-curated-word-rectangle-proposals",
        "columns": 7,
        "rows": 8,
        "sourceShapeId": "corrected-7x8-01",
        "publicationEligible": False,
        "complete": bool(solutions),
        "solutions": solutions,
        "telemetry": {
            "rowCount": len(rows),
            "columnCount": len(columns),
            "nodes": nodes,
            "solutionCount": len(solutions),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"complete": payload["complete"], "telemetry": payload["telemetry"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if solutions else 2


if __name__ == "__main__":
    raise SystemExit(main())
