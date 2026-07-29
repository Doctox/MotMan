#!/usr/bin/env python3
"""Build one full 7x8 word rectangle from compatible reviewed current words."""
from __future__ import annotations

import argparse
import json
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
DEFAULT_OUTPUT = ROOT / "output/quality/semi-manual-7x8-candidate/full-rectangle-fill.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rescue", type=Path, default=DEFAULT_RESCUE)
    parser.add_argument("--reference-catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-zipf", type=float, default=2.5)
    parser.add_argument("--seconds", type=float, default=180.0)
    parser.add_argument("--row-limit", type=int, default=7000)
    parser.add_argument("--solution-limit", type=int, default=30)
    parser.add_argument("--seconds-per-placement", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pools, current_answers, usage = load_candidates(args)
    rows = sorted(pools[6], key=lambda word: (-pools[6][word]["score"], word))[:args.row_limit]
    columns = sorted(pools[7])
    prefix_sets = {length: {word[:length] for word in columns} for length in range(1, 8)}
    row_index = defaultdict(list)
    column_index = defaultdict(list)
    for word in rows:
        for position, letter in enumerate(word):
            row_index[(position, letter)].append(word)
    for word in columns:
        for position, letter in enumerate(word):
            column_index[(position, letter)].append(word)

    current_rows = sorted(set(rows) & current_answers)
    current_columns = sorted(set(columns) & current_answers)
    placements = []
    for row_answer in current_rows:
        for column_answer in current_columns:
            if family_key(row_answer) == family_key(column_answer):
                continue
            for row_position in range(7):
                for column_position in range(6):
                    if row_answer[column_position] != column_answer[row_position]:
                        continue
                    widths = [
                        len(row_index[(column_position, column_answer[index])])
                        for index in range(7) if index != row_position
                    ] + [
                        len(column_index[(row_position, row_answer[index])])
                        for index in range(6) if index != column_position
                    ]
                    if not widths or min(widths) == 0:
                        continue
                    placements.append({
                        "rowAnswer": row_answer,
                        "columnAnswer": column_answer,
                        "rowPosition": row_position,
                        "columnPosition": column_position,
                        "minimumDomain": min(widths),
                        "domainSum": sum(widths),
                    })
    placements.sort(key=lambda item: (
        -item["minimumDomain"], -item["domainSum"],
        item["rowAnswer"], item["columnAnswer"],
    ))

    deadline = time.perf_counter() + args.seconds
    solutions = []
    explored = 0
    attempted = 0

    for placement in placements:
        if time.perf_counter() >= deadline or len(solutions) >= args.solution_limit:
            break
        attempted += 1
        branch_deadline = min(deadline, time.perf_counter() + args.seconds_per_placement)
        fixed_row = placement["rowAnswer"]
        fixed_column = placement["columnAnswer"]
        fixed_row_position = placement["rowPosition"]
        fixed_column_position = placement["columnPosition"]

        def recurse(depth: int, prefixes: tuple[str, ...], selected_rows: list[str], used_families: set[str]):
            nonlocal explored
            if time.perf_counter() >= branch_deadline or len(solutions) >= args.solution_limit:
                return
            if depth == 7:
                column_words = list(prefixes)
                answers = [*column_words, *selected_rows]
                if len(set(answers)) != len(answers):
                    return
                families = [family_key(answer) for answer in answers]
                if len(set(families)) != len(families):
                    return
                current_hits = sorted(set(answers) & current_answers)
                if len(current_hits) < 2:
                    return
                score = sum(pools[len(answer)][answer]["score"] for answer in answers)
                solutions.append({
                    "score": round(score + 250.0 * len(current_hits), 3),
                    "rows": list(selected_rows),
                    "columns": column_words,
                    "currentAnswers": current_hits,
                    "activeRepeats": sorted(answer for answer in answers if usage.get(answer, 0)),
                    "seedPlacement": placement,
                })
                return
            if depth == fixed_row_position:
                candidates = [fixed_row]
            else:
                candidates = row_index[(fixed_column_position, fixed_column[depth])]
            for word in candidates:
                explored += 1
                family = family_key(word)
                if family in used_families:
                    continue
                next_prefixes = tuple(prefixes[index] + word[index] for index in range(6))
                target_length = depth + 1
                if next_prefixes[fixed_column_position] != fixed_column[:target_length]:
                    continue
                if any(prefix not in prefix_sets[target_length] for prefix in next_prefixes):
                    continue
                recurse(
                    depth + 1, next_prefixes, [*selected_rows, word],
                    used_families | {family},
                )

        recurse(0, ("", "", "", "", "", ""), [], set())

    solutions.sort(key=lambda item: (
        -len(item["currentAnswers"]), len(item["activeRepeats"]),
        -item["score"], item["rows"],
    ))
    best = solutions[0] if solutions else None
    if best:
        answers = [*best["columns"], *best["rows"]]
        best["metadata"] = {answer: pools[len(answer)][answer] for answer in answers}
    payload = {
        "version": 1,
        "kind": "motman-semi-manual-full-rectangle",
        "columns": 7,
        "rows": 8,
        "sourceShapeId": "corrected-7x8-01",
        "catalogModified": False,
        "runtimeModified": False,
        "supabaseModified": False,
        "publicationEligible": False,
        "complete": best is not None,
        "best": best,
        "telemetry": {
            "reviewedCurrentRowCount": len(current_rows),
            "reviewedCurrentColumnCount": len(current_columns),
            "compatiblePlacementCount": len(placements),
            "attemptedPlacementCount": attempted,
            "exploredRows": explored,
            "completeFillCount": len(solutions),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"complete": payload["complete"], "best": best, "telemetry": payload["telemetry"], "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0 if best else 2


if __name__ == "__main__":
    raise SystemExit(main())
