#!/usr/bin/env python3
"""CP-SAT feasibility search for the immutable reference-ribbon-a-01 grid.

Every letter cell is one shared integer variable.  Each answer slot is a
licensed local-corpus table constraint, so a crossing can never be forced to
a non-word.  ``wordfreq`` only ranks/filters structural candidates; it does
not supply clues.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ortools.sat.python import cp_model
from wordfreq import zipf_frequency


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagnose_fixed_shape_corpus_gaps import (  # noqa: E402
    DEFAULT_SHAPES,
    load_expansion_words,
    load_shape,
    load_words,
)
from fill_fixed_ribbon_a01 import validate_fixed_layout  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimum-zipf", type=float, default=1.5)
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--seed", type=int, default=717401)
    parser.add_argument(
        "--anchor-slot",
        type=int,
        choices=(0, 1, 2, 5, 6),
        help="Fixe IDEOLOGIE dans l'un des cinq slots verticaux de neuf lettres.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output/quality/reference-ribbon-a01-cpsat.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _shape, slots = load_shape(DEFAULT_SHAPES, "reference-ribbon-a-01")
    validate_fixed_layout(slots)
    _central_by_length, canonical = load_words()
    expanded, metadata, source_stats = load_expansion_words(
        canonical,
        permissive=False,
        include_morphalou=True,
    )

    scores: dict[str, float] = {}
    words: dict[int, tuple[str, ...]] = {}
    for length in (3, 4, 5, 8, 9):
        kept = []
        for answer in expanded.get(length, ()):
            score = zipf_frequency(answer.lower(), "fr")
            scores[answer] = score
            if answer in canonical or score >= args.minimum_zipf:
                kept.append(answer)
        # High-frequency candidates receive small indexes, which also gives
        # the default search a useful deterministic order.
        kept.sort(key=lambda answer: (
            answer not in canonical,
            -scores[answer],
            answer,
        ))
        words[length] = tuple(kept)

    model = cp_model.CpModel()
    letter_cells = sorted({cell for slot in slots for cell in slot.cells})
    letters = {
        cell: model.new_int_var(0, 25, f"r{cell[0]}c{cell[1]}")
        for cell in letter_cells
    }
    answer_indexes: dict[int, cp_model.IntVar] = {}
    indexes_by_length: dict[int, list[cp_model.IntVar]] = {}
    for slot in slots:
        candidates = words[slot.length]
        answer_index = model.new_int_var(
            0,
            len(candidates) - 1,
            f"slot_{slot.index:02d}",
        )
        answer_indexes[slot.index] = answer_index
        indexes_by_length.setdefault(slot.length, []).append(answer_index)
        table = [
            [index, *(ord(letter) - 65 for letter in answer)]
            for index, answer in enumerate(candidates)
        ]
        model.add_allowed_assignments(
            [answer_index, *(letters[cell] for cell in slot.cells)],
            table,
        )
    for same_length_indexes in indexes_by_length.values():
        if len(same_length_indexes) > 1:
            model.add_all_different(same_length_indexes)
    if args.anchor_slot is not None:
        try:
            anchor_index = words[9].index("IDEOLOGIE")
        except ValueError as error:
            raise ValueError("IDEOLOGIE absent du domaine 9 lettres") from error
        model.add(answer_indexes[args.anchor_slot] == anchor_index)
    model.add_decision_strategy(
        list(letters.values()),
        cp_model.CHOOSE_MIN_DOMAIN_SIZE,
        cp_model.SELECT_MIN_VALUE,
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = args.seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = args.seed
    # Large table presolve spent the whole budget without reaching search on
    # this dense grid. Native table propagation branches immediately.
    solver.parameters.cp_model_presolve = False
    solver.parameters.linearization_level = 0
    solver.parameters.randomize_search = True
    solver.parameters.log_search_progress = False
    status = solver.solve(model)
    complete = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    solution = None
    if complete:
        solution = []
        for slot in slots:
            answer = words[slot.length][solver.value(answer_indexes[slot.index])]
            solution.append({
                "slotIndex": slot.index,
                "slotId": slot.slot_id,
                "answer": answer,
                "zipf": scores[answer],
                "hasReviewedPair": answer in canonical,
            })

    document = {
        "version": 1,
        "kind": "immutable-a01-cpsat-closure",
        "shapeId": "reference-ribbon-a-01",
        "shapeModified": False,
        "complete": complete,
        "publicationEligible": False,
        "minimumZipf": args.minimum_zipf,
        "anchor": (
            {"slotIndex": args.anchor_slot, "answer": "IDEOLOGIE"}
            if args.anchor_slot is not None else None
        ),
        "candidateCounts": {str(k): len(v) for k, v in words.items()},
        "sourcePool": source_stats,
        "solverTelemetry": {
            "status": solver.status_name(status),
            "wallSeconds": solver.wall_time,
            "branches": solver.num_branches,
            "conflicts": solver.num_conflicts,
        },
        "solution": solution,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "complete": complete,
        "status": document["solverTelemetry"],
        "candidateCounts": document["candidateCounts"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
