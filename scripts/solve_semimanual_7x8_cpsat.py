#!/usr/bin/env python3
"""Propose one 7x8 fill with CP-SAT; editorial review remains mandatory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ortools.sat.python import cp_model

from construct_semimanual_7x8 import DEFAULT_CATALOG, DEFAULT_RESCUE, load_candidates


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHAPES = ROOT / "output/quality/corrected-7x8-shapes/corrected-shape-library.json"
DEFAULT_OUTPUT = ROOT / "output/quality/semi-manual-7x8-candidate/cpsat-proposal.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shape-file", type=Path, default=DEFAULT_SHAPES)
    parser.add_argument("--shape-id", default="corrected-7x8-05")
    parser.add_argument("--rescue", type=Path, default=DEFAULT_RESCUE)
    parser.add_argument("--reference-catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-zipf", type=float, default=2.3)
    parser.add_argument("--seconds", type=float, default=180.0)
    parser.add_argument("--minimum-current", type=int, default=2)
    parser.add_argument("--maximum-review-required", type=int, default=3)
    parser.add_argument("--seed", type=int, default=270722)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    shapes = json.loads(args.shape_file.read_text(encoding="utf-8"))["shapes"]
    shape = next(item for item in shapes if item["shapeId"] == args.shape_id)
    pools, current_answers, usage = load_candidates(args)
    lengths = sorted({int(slot["length"]) for slot in shape["slots"]})
    missing = [length for length in lengths if length not in pools]
    if missing:
        raise ValueError(f"Longueurs absentes du pool : {missing}")

    words_by_length = {
        length: sorted(pools[length], key=lambda word: (-pools[length][word]["score"], word))
        for length in lengths
    }
    model = cp_model.CpModel()
    cell_vars: dict[tuple[int, int], cp_model.IntVar] = {}
    for slot in shape["slots"]:
        for row, column in slot["cells"]:
            cell_vars.setdefault((row, column), model.new_int_var(0, 25, f"c_{row}_{column}"))

    slot_vars = []
    current_flags = []
    review_flags = []
    score_vars = []
    by_length_vars: dict[int, list[cp_model.IntVar]] = {length: [] for length in lengths}
    for slot in shape["slots"]:
        index = int(slot["slotIndex"])
        length = int(slot["length"])
        words = words_by_length[length]
        word_var = model.new_int_var(0, len(words) - 1, f"w_{index}")
        letters = [cell_vars[tuple(cell)] for cell in slot["cells"]]
        tuples = [
            [word_index, *[ord(letter) - 65 for letter in word]]
            for word_index, word in enumerate(words)
        ]
        model.add_allowed_assignments([word_var, *letters], tuples)
        by_length_vars[length].append(word_var)
        slot_vars.append((slot, word_var, words))

        current_values = [1 if word in current_answers else 0 for word in words]
        current_var = model.new_int_var(0, 1, f"current_{index}")
        model.add_element(word_var, current_values, current_var)
        current_flags.append(current_var)

        review_values = [
            1 if pools[length][word]["source"] in {
                "inflected-review-required", "proper-name-review-required"
            } else 0
            for word in words
        ]
        review_var = model.new_int_var(0, 1, f"review_{index}")
        model.add_element(word_var, review_values, review_var)
        review_flags.append(review_var)

        scores = [int(round(pools[length][word]["score"] * 10)) for word in words]
        score_var = model.new_int_var(min(scores), max(scores), f"score_{index}")
        model.add_element(word_var, scores, score_var)
        score_vars.append(score_var)

    for variables in by_length_vars.values():
        if len(variables) > 1:
            model.add_all_different(variables)
    model.add(sum(current_flags) >= args.minimum_current)
    model.add(sum(review_flags) <= args.maximum_review_required)
    model.maximize(sum(score_vars) + 2500 * sum(current_flags) - 1800 * sum(review_flags))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = args.seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = args.seed
    status = solver.solve(model)
    complete = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    answers = []
    if complete:
        for slot, word_var, words in slot_vars:
            answer = words[solver.value(word_var)]
            answers.append({
                "slotIndex": slot["slotIndex"],
                "answer": answer,
                "metadata": pools[len(answer)][answer],
            })
    payload = {
        "version": 1,
        "kind": "motman-cpsat-editorial-proposal",
        "shapeId": args.shape_id,
        "publicationEligible": False,
        "complete": complete,
        "status": solver.status_name(status),
        "objective": solver.objective_value if complete else None,
        "answers": answers,
        "stats": {
            "branches": solver.num_branches,
            "conflicts": solver.num_conflicts,
            "wallTime": solver.wall_time,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"complete": complete, "status": payload["status"], "answers": [item["answer"] for item in answers], "stats": payload["stats"], "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
