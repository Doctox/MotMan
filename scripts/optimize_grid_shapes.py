"""Find clean rectangular arrowword silhouettes with explicit arrow policies.

Production uses ``only_direct_arrows``: an across answer starts immediately
right of its clue and a down answer immediately below it.  Bent arrows remain
modelled only so legacy grids can be diagnosed and rejected explicitly.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ortools.sat.python import cp_model


DEFAULT_COLUMNS = 9
DEFAULT_ROWS = 9
DIRECTIONS = {"across": (0, 1), "down": (1, 0)}


def optimize(
    timeout: float = 30,
    seed: int = 1,
    visible_clue_cells: int = 16,
    minimum_double_clues: int = 4,
    maximum_double_clues: int | None = None,
    maximum_adjacent_clues: int = 2,
    maximum_adjacent_pairs: int | None = None,
    only_direct_double_clues: bool = False,
    only_direct_arrows: bool = True,
    minimum_direct_double_clues: int = 0,
    maximum_length_eight_answers: int | None = None,
    maximum_length_two_answers: int | None = None,
    maximum_short_answers_2_to_4: int | None = None,
    minimum_border_clues: int = 2,
    maximum_top_border_clues: int | None = None,
    maximum_left_border_clues: int | None = None,
    maximum_border_adjacent_pairs: int | None = None,
    maximum_border_clue_run: int | None = None,
    required_lengths: tuple[int, ...] = (),
    require_length_bands: bool = True,
    enforce_length_balance: bool = True,
    enforce_clue_spacing: bool = True,
    enforce_interior_line_limits: bool | None = None,
    enforce_clue_triples: bool | None = None,
    enforce_solid_clue_blocks: bool | None = None,
    full_definition_frame: bool = False,
    position_penalties: dict[tuple[int, int], int] | None = None,
    previous_shapes: list[set[tuple[int, int]]] | None = None,
    maximum_shape_overlap: int | None = None,
    forbidden_clue_cells: set[tuple[int, int]] | None = None,
    columns: int = DEFAULT_COLUMNS,
    rows: int = DEFAULT_ROWS,
    maximum_answer_length: int | None = None,
    minimum_long_answer_advantage: int | None = None,
    maximum_crossing_letter_cells: int | None = None,
    crossing_cell_penalty: int = 0,
    short_answer_penalty: int = 10,
    answer_length_penalties: dict[int, int] | None = None,
    adjacent_pair_penalties: dict[tuple[tuple[int, int], tuple[int, int]], int] | None = None,
    required_adjacent_pairs: set[tuple[tuple[int, int], tuple[int, int]]] | None = None,
    forbidden_adjacent_pairs: set[tuple[tuple[int, int], tuple[int, int]]] | None = None,
) -> dict | None:
    model = cp_model.CpModel()
    maximum_answer_length = maximum_answer_length or (max(columns, rows) - 1)
    clue = {(r, c): model.new_bool_var(f"clue_{r}_{c}")
            for r in range(rows) for c in range(columns)}
    model.add(clue[0, 0] == 1)
    if full_definition_frame:
        for col in range(1, columns):
            model.add(clue[0, col] == 1)
        for row in range(1, rows):
            model.add(clue[row, 0] == 1)
    for cell in forbidden_clue_cells or set():
        if cell != (0, 0):
            model.add(clue[cell] == 0)
    runs = []
    arrows = []

    for direction, (dr, dc) in DIRECTIONS.items():
        for row in range(rows):
            for col in range(columns):
                for length in range(2, maximum_answer_length + 1):
                    cells = tuple((row + dr * offset, col + dc * offset)
                                  for offset in range(length))
                    if any(cell not in clue for cell in cells):
                        continue
                    before = (row - dr, col - dc)
                    after = (row + dr * length, col + dc * length)
                    run = model.new_bool_var(f"run_{direction}_{row}_{col}_{length}")
                    candidates = (
                        [((row, col - 1), "right"), ((row - 1, col), "downright")]
                        if direction == "across" else
                        [((row - 1, col), "down"), ((row, col - 1), "rightdown")]
                    )
                    choices = []
                    for definition, arrow in candidates:
                        if definition not in clue or definition == (0, 0):
                            continue
                        if only_direct_arrows and arrow not in {"right", "down"}:
                            continue
                        choice = model.new_bool_var(
                            f"arrow_{arrow}_{definition[0]}_{definition[1]}_{row}_{col}_{length}"
                        )
                        model.add_implication(choice, clue[definition])
                        choices.append(choice)
                        arrows.append((choice, definition, direction, arrow, cells, length))
                    if not choices:
                        model.add(run == 0)
                    else:
                        model.add(sum(choices) == run)
                    for cell in cells:
                        model.add_implication(run, clue[cell].Not())
                    if before in clue:
                        model.add_implication(run, clue[before])
                    if after in clue:
                        model.add_implication(run, clue[after])
                    runs.append((run, direction, cells, length))

    # Each visible adjacent letter pair belongs to exactly one declared run.
    for direction, (dr, dc) in DIRECTIONS.items():
        for row in range(rows):
            for col in range(columns):
                first, second = (row, col), (row + dr, col + dc)
                if second not in clue:
                    continue
                both_letters = model.new_bool_var(f"pair_{direction}_{row}_{col}")
                model.add(both_letters <= 1 - clue[first])
                model.add(both_letters <= 1 - clue[second])
                model.add(both_letters >= 1 - clue[first] - clue[second])
                covering = [var for var, run_direction, cells, _length in runs
                            if run_direction == direction and first in cells and second in cells]
                model.add(sum(covering) == both_letters)

    # Every letter participates in at least one answer and at most two. Keep an
    # explicit crossing variable so long-answer shapes can avoid turning every
    # cell into a doubly constrained word-square intersection.
    crossing_cells = []
    for cell in clue:
        covering = [var for var, _direction, cells, _length in runs if cell in cells]
        model.add(sum(covering) >= 1 - clue[cell])
        model.add(sum(covering) <= 2 * (1 - clue[cell]))
        crossing = model.new_bool_var(f"crossing_{cell[0]}_{cell[1]}")
        model.add(sum(covering) == 2).only_enforce_if(crossing)
        model.add(sum(covering) != 2).only_enforce_if(crossing.Not())
        crossing_cells.append(crossing)
    if maximum_crossing_letter_cells is not None:
        model.add(sum(crossing_cells) <= maximum_crossing_letter_cells)

    arrows_by_clue = defaultdict(list)
    arrows_by_clue_direction = defaultdict(list)
    for var, definition, direction, _arrow, _cells, _length in arrows:
        arrows_by_clue[definition].append(var)
        arrows_by_clue_direction[definition, direction].append(var)
    doubles = []
    direct_doubles = []
    for cell in clue:
        outgoing = arrows_by_clue[cell]
        if cell == (0, 0):
            model.add(sum(outgoing) == 0)
            continue
        model.add(sum(outgoing) >= clue[cell])
        model.add(sum(outgoing) <= 2 * clue[cell])
        for direction in DIRECTIONS:
            model.add(sum(arrows_by_clue_direction[cell, direction]) <= 1)
        double = model.new_bool_var(f"double_{cell[0]}_{cell[1]}")
        model.add(sum(outgoing) == 2).only_enforce_if(double)
        model.add(sum(outgoing) != 2).only_enforce_if(double.Not())
        direct = [
            var for var, definition, direction, arrow, _cells, _length in arrows
            if definition == cell and (
                (direction == "across" and arrow == "right")
                or (direction == "down" and arrow == "down")
            )
        ]
        direct_double = model.new_bool_var(f"direct_double_{cell[0]}_{cell[1]}")
        model.add(sum(direct) == 2).only_enforce_if(direct_double)
        model.add(sum(direct) != 2).only_enforce_if(direct_double.Not())
        if only_direct_double_clues:
            model.add_implication(double, direct_double)
        doubles.append(double)
        direct_doubles.append(direct_double)

    model.add(sum(clue.values()) == visible_clue_cells + 1)
    if maximum_length_eight_answers is not None:
        model.add(sum(var for var, _d, _c, length in runs if length == 8)
                  <= maximum_length_eight_answers)
    if maximum_length_two_answers is not None:
        model.add(sum(var for var, _d, _c, length in runs if length == 2)
                  <= maximum_length_two_answers)
    if maximum_short_answers_2_to_4 is not None:
        model.add(sum(var for var, _d, _c, length in runs if 2 <= length <= 4)
                  <= maximum_short_answers_2_to_4)
    selected_run_count = sum(var for var, _d, _c, _length in runs)
    if enforce_length_balance:
        for length in range(2, maximum_answer_length + 1):
            length_count = sum(var for var, _d, _c, run_length in runs
                               if run_length == length)
            model.add(100 * length_count <= 35 * selected_run_count)
    if require_length_bands:
        model.add(sum(var for var, _d, _c, length in runs if length in (2, 3)) >= 1)
        model.add(sum(var for var, _d, _c, length in runs if length in (4, 5)) >= 1)
        model.add(sum(var for var, _d, _c, length in runs if length >= 6) >= 1)
    if minimum_long_answer_advantage is not None:
        short_answers = sum(
            var for var, _direction, _cells, length in runs if 2 <= length <= 4
        )
        long_answers = sum(
            var for var, _direction, _cells, length in runs if 5 <= length <= 8
        )
        model.add(long_answers >= short_answers + minimum_long_answer_advantage)
    for required_length in required_lengths:
        model.add(sum(var for var, _d, _c, length in runs
                      if length == required_length) >= 1)
    model.add(sum(doubles) >= minimum_double_clues)
    if maximum_double_clues is not None:
        model.add(sum(doubles) <= maximum_double_clues)
    model.add(sum(direct_doubles) >= minimum_direct_double_clues)
    model.add(sum(clue[0, col] for col in range(1, columns)) >= minimum_border_clues)
    model.add(sum(clue[row, 0] for row in range(1, rows)) >= minimum_border_clues)
    if maximum_top_border_clues is not None:
        model.add(sum(clue[0, col] for col in range(1, columns))
                  <= maximum_top_border_clues)
    if maximum_left_border_clues is not None:
        model.add(sum(clue[row, 0] for row in range(1, rows))
                  <= maximum_left_border_clues)
    if maximum_border_clue_run is not None:
        window = maximum_border_clue_run + 1
        for start in range(1, columns - window + 1):
            model.add(sum(clue[0, col] for col in range(start, start + window))
                      <= maximum_border_clue_run)
        for start in range(1, rows - window + 1):
            model.add(sum(clue[row, 0] for row in range(start, start + window))
                      <= maximum_border_clue_run)

    # Library-wide diversity: a new mask may not reuse too much of any mask
    # already selected.  The neutral top-left corner is intentionally ignored.
    previous_shapes = previous_shapes or []
    if maximum_shape_overlap is not None:
        for index, shape in enumerate(previous_shapes):
            visible = set(shape) - {(0, 0)}
            model.add(sum(clue[cell] for cell in visible) <= maximum_shape_overlap)

    # The legacy umbrella flag remains the default for existing callers, while
    # corpus-aware construction can tune the three visual rules separately.
    if enforce_interior_line_limits is None:
        enforce_interior_line_limits = enforce_clue_spacing
    if enforce_clue_triples is None:
        enforce_clue_triples = enforce_clue_spacing
    if enforce_solid_clue_blocks is None:
        enforce_solid_clue_blocks = enforce_clue_spacing

    # No wall of three definitions in polished shapes. Consecutive clue cells
    # remain conventional on the top and left borders.
    if enforce_interior_line_limits or enforce_clue_triples:
        # Consecutive clue cells are conventional on the top and left borders:
        # they launch the vertical and horizontal entries.  The wall rule is
        # therefore limited to the interior, where it harms readability.
        for row in range(1, rows):
            if enforce_interior_line_limits:
                model.add(sum(clue[row, col] for col in range(columns)) <= 4)
            if enforce_clue_triples:
                for col in range(columns - 2):
                    model.add(sum(clue[row, col + offset] for offset in range(3)) <= 2)
        for col in range(1, columns):
            if enforce_interior_line_limits:
                model.add(sum(clue[row, col] for row in range(rows)) <= 4)
            if enforce_clue_triples:
                for row in range(rows - 2):
                    model.add(sum(clue[row + offset, col] for offset in range(3)) <= 2)
    adjacent_pairs = []
    interior_adjacent_pairs = []
    border_adjacent_pairs = []
    adjacent_pair_by_cells = {}
    for row in range(rows):
        for col in range(columns - 1):
            pair = {(row, col), (row, col + 1)} - {(0, 0)}
            if len(pair) < 2:
                continue
            together = model.new_bool_var(f"adjacent_h_{row}_{col}")
            first, second = pair
            model.add(together <= clue[first]); model.add(together <= clue[second])
            model.add(together >= clue[first] + clue[second] - 1)
            adjacent_pairs.append(together)
            if row > 0:
                interior_adjacent_pairs.append(together)
            else:
                border_adjacent_pairs.append(together)
            adjacent_pair_by_cells[tuple(sorted(pair))] = together
    for col in range(columns):
        for row in range(rows - 1):
            pair = {(row, col), (row + 1, col)} - {(0, 0)}
            if len(pair) < 2:
                continue
            together = model.new_bool_var(f"adjacent_v_{row}_{col}")
            first, second = pair
            model.add(together <= clue[first]); model.add(together <= clue[second])
            model.add(together >= clue[first] + clue[second] - 1)
            adjacent_pairs.append(together)
            if col > 0:
                interior_adjacent_pairs.append(together)
            else:
                border_adjacent_pairs.append(together)
            adjacent_pair_by_cells[tuple(sorted(pair))] = together
    if maximum_adjacent_clues == 1:
        model.add(sum(interior_adjacent_pairs) == 0)
    if maximum_adjacent_pairs is not None:
        model.add(sum(interior_adjacent_pairs) <= maximum_adjacent_pairs)
    if maximum_border_adjacent_pairs is not None:
        model.add(sum(border_adjacent_pairs) <= maximum_border_adjacent_pairs)
    for pair in required_adjacent_pairs or set():
        canonical = tuple(sorted(pair))
        if canonical not in adjacent_pair_by_cells:
            return None
        model.add(adjacent_pair_by_cells[canonical] == 1)
    for pair in forbidden_adjacent_pairs or set():
        canonical = tuple(sorted(pair))
        if canonical in adjacent_pair_by_cells:
            model.add(adjacent_pair_by_cells[canonical] == 0)
    if enforce_solid_clue_blocks:
        for row in range(rows - 1):
            for col in range(columns - 1):
                model.add(sum(clue[row + dr, col + dc]
                              for dr in (0, 1) for dc in (0, 1)) <= 3)

    # Favour useful double-definition cells, but charge repeatedly-used clue
    # positions.  Iterative library construction updates these costs after
    # every accepted silhouette, spreading structural anchors over the grid.
    position_penalties = position_penalties or {}
    repeated_position_cost = sum(
        position_penalties.get(cell, 0) * var
        for cell, var in clue.items() if cell != (0, 0)
    )
    adjacent_pair_penalties = adjacent_pair_penalties or {}
    repeated_pair_cost = sum(
        adjacent_pair_penalties.get(pair, 0) * var
        for pair, var in adjacent_pair_by_cells.items()
    )
    # Once the hard minimum of doubles is met, library diversity is more
    # valuable than squeezing one extra double into every mask.
    short_answer_cost = sum(
        (4 - length) * var for var, _direction, _cells, length in runs if length < 4
    )
    # Optional corpus-aware cost.  A caller can make structurally scarce
    # lengths expensive without banning them outright: this preserves
    # topology feasibility while steering silhouettes toward the vocabulary
    # the reviewed corpus can actually supply.
    answer_length_penalties = answer_length_penalties or {}
    corpus_length_cost = sum(
        answer_length_penalties.get(length, 0) * var
        for var, _direction, _cells, length in runs
    )
    model.maximize(20 * sum(doubles) + 5 * sum(direct_doubles)
                   - short_answer_penalty * short_answer_cost
                   - corpus_length_cost
                   - crossing_cell_penalty * sum(crossing_cells)
                   - 100 * repeated_position_cost - 250 * repeated_pair_cost)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout
    solver.parameters.num_search_workers = 8
    # OR-Tools stores this setting in a signed 32-bit integer.  Date-based
    # reproducible seeds used by the pipeline can be larger, so fold them
    # deterministically instead of failing before the search starts.
    solver.parameters.random_seed = seed % 2_000_000_000 or 1
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    clue_cells = sorted(cell for cell, var in clue.items() if solver.value(var))
    slots = [{
        "direction": direction, "arrow": arrow, "clue": list(definition),
        "cells": [list(cell) for cell in cells], "length": length,
    } for var, definition, direction, arrow, cells, length in arrows if solver.value(var)]
    length_counts = Counter(slot["length"] for slot in slots)
    short_answers = sum(length_counts[length] for length in range(2, 5))
    long_answers = sum(length_counts[length] for length in range(5, 9))
    return {
        "seed": seed,
        "columns": columns,
        "rows": rows,
        "requestedVisibleClueCells": visible_clue_cells,
        "clueCells": [list(cell) for cell in clue_cells],
        "slots": slots,
        "metrics": {
            "clueCells": len(clue_cells) - 1,
            "doubleClueCells": sum(solver.value(var) for var in doubles),
            "lengths": dict(sorted(length_counts.items())),
            "shortAnswers2To4": short_answers,
            "longAnswers5To8": long_answers,
            "longAnswerAdvantage": long_answers - short_answers,
            "crossingLetterCells": sum(solver.value(var) for var in crossing_cells),
            "arrows": dict(sorted(Counter(slot["arrow"] for slot in slots).items())),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--visible-clues", type=int, choices=range(10, 31), default=16)
    parser.add_argument("--minimum-doubles", type=int, default=4)
    parser.add_argument("--maximum-doubles", type=int)
    parser.add_argument("--maximum-adjacent", type=int, choices=(1, 2), default=2)
    parser.add_argument("--maximum-adjacent-pairs", type=int)
    parser.add_argument("--only-direct-doubles", action="store_true")
    arrow_policy = parser.add_mutually_exclusive_group()
    arrow_policy.add_argument(
        "--only-direct-arrows", dest="only_direct_arrows",
        action="store_true", default=True,
    )
    arrow_policy.add_argument(
        "--allow-bent-arrows", dest="only_direct_arrows", action="store_false",
        help="diagnostic legacy seulement ; impropre à la publication",
    )
    parser.add_argument("--minimum-direct-doubles", type=int, default=0)
    parser.add_argument("--maximum-length-eight", type=int)
    parser.add_argument("--maximum-length-two", type=int)
    parser.add_argument(
        "--maximum-short-answers-2-to-4", type=int,
        help="plafonne l'ensemble des réponses de 2, 3 et 4 lettres",
    )
    parser.add_argument("--minimum-border-clues", type=int, choices=(1, 2), default=2)
    parser.add_argument("--maximum-top-border-clues", type=int)
    parser.add_argument("--maximum-left-border-clues", type=int)
    parser.add_argument("--maximum-border-adjacent-pairs", type=int)
    parser.add_argument("--maximum-border-clue-run", type=int)
    parser.add_argument(
        "--required-lengths", default="",
        help="longueurs obligatoires dans cette silhouette (liste séparée par des virgules)",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--columns", type=int, default=DEFAULT_COLUMNS)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--maximum-answer-length", type=int)
    parser.add_argument(
        "--minimum-long-answer-advantage",
        type=int,
        help="impose au moins N réponses de 5 à 8 de plus que de 2 à 4",
    )
    parser.add_argument("--maximum-crossing-letter-cells", type=int)
    parser.add_argument("--crossing-cell-penalty", type=int, default=0)
    parser.add_argument(
        "--full-definition-frame", action="store_true",
        help="variante optionnelle observée chez certains éditeurs",
    )
    args = parser.parse_args()
    result = optimize(
        timeout=args.timeout,
        seed=args.seed,
        visible_clue_cells=args.visible_clues,
        minimum_double_clues=args.minimum_doubles,
        maximum_double_clues=args.maximum_doubles,
        maximum_adjacent_clues=args.maximum_adjacent,
        maximum_adjacent_pairs=args.maximum_adjacent_pairs,
        only_direct_double_clues=args.only_direct_doubles,
        only_direct_arrows=args.only_direct_arrows,
        minimum_direct_double_clues=args.minimum_direct_doubles,
        maximum_length_eight_answers=args.maximum_length_eight,
        maximum_length_two_answers=args.maximum_length_two,
        maximum_short_answers_2_to_4=args.maximum_short_answers_2_to_4,
        minimum_border_clues=args.minimum_border_clues,
        maximum_top_border_clues=args.maximum_top_border_clues,
        maximum_left_border_clues=args.maximum_left_border_clues,
        maximum_border_adjacent_pairs=args.maximum_border_adjacent_pairs,
        maximum_border_clue_run=args.maximum_border_clue_run,
        required_lengths=tuple(
            int(value) for value in args.required_lengths.split(",") if value
        ),
        full_definition_frame=args.full_definition_frame,
        columns=args.columns,
        rows=args.rows,
        maximum_answer_length=args.maximum_answer_length,
        minimum_long_answer_advantage=args.minimum_long_answer_advantage,
        maximum_crossing_letter_cells=args.maximum_crossing_letter_cells,
        crossing_cell_penalty=args.crossing_cell_penalty,
    )
    rendered = json.dumps(result or {"status": "infeasible"}, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    if result is None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
