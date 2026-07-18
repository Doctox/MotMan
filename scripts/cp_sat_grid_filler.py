"""Bounded CP-SAT filler for fully declared MotMan arrowword slots."""
from __future__ import annotations

import time
from collections import defaultdict


LEVEL_CODE = {"easy": 0, "normal": 1, "hard": 2}


def fill_cp_sat(
    slots,
    indexes,
    rng,
    target_mix: dict[str, int] | None,
    *,
    unavailable_answers: set[str] | None = None,
    answer_usage: dict[str, int] | None = None,
    max_grammar_answers: int = 1,
    grammar_answers: set[str] | None = None,
    max_seconds: float = 5.0,
    require_image: bool = True,
    minimum_images: int = 1,
    required_image_slots: set[int] | None = None,
    fixed_answers: dict[int, str] | None = None,
    undesirable_answers: set[str] | None = None,
    max_undesirable_answers: int | None = None,
    telemetry: dict | None = None,
) -> dict[int, str] | None:
    """Assign one sourced answer to every slot, or return None before deadline.

    Each slot is one integer variable selecting a word. Letter variables are
    derived with Element constraints and equated at crossings. This avoids the
    Python set copies that made the former backtracker unbounded in practice.
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        if telemetry is not None:
            telemetry.update(reason="ortools_missing", elapsedSeconds=0)
        return None

    started = time.monotonic()
    telemetry = telemetry if telemetry is not None else {}
    unavailable_answers = unavailable_answers or set()
    answer_usage = answer_usage or {}
    grammar_answers = grammar_answers or set()
    fixed_answers = fixed_answers or {}
    required_image_slots = required_image_slots or set()
    undesirable_answers = undesirable_answers or set()
    by_length, _, frequency, _, _, word_difficulty, image_answers = indexes
    variables = [index for index, slot in enumerate(slots) if slot.cells]

    candidates: dict[int, list[str]] = {}
    for index in variables:
        words = [
            word for word in by_length[len(slots[index].cells)]
            if word not in unavailable_answers
            and (index not in fixed_answers or word == fixed_answers[index])
        ]
        # Stable quality ordering makes local indices reproducible. CP-SAT still
        # receives a seed for alternative feasible fills.
        words.sort(key=lambda word: (-frequency[word], answer_usage.get(word, 0), word))
        if not words:
            telemetry.update(reason="empty_domain", slot=index, elapsedSeconds=0)
            return None
        candidates[index] = words

    model = cp_model.CpModel()
    word_vars = {}
    tier_vars = {}
    image_vars = {}
    grammar_vars = {}
    undesirable_vars = {}
    cell_letters = {
        cell: model.new_int_var(0, 25, f"cell_{cell[0]}_{cell[1]}")
        for index in variables for cell in slots[index].cells
    }
    quality_terms = []

    for index in variables:
        words = candidates[index]
        word_var = model.new_int_var(0, len(words) - 1, f"word_{index}")
        word_vars[index] = word_var

        tier = model.new_int_var(0, 2, f"tier_{index}")
        model.add_element(word_var, [LEVEL_CODE[word_difficulty[word]] for word in words], tier)
        tier_vars[index] = tier

        image = model.new_bool_var(f"image_{index}")
        model.add_element(word_var, [int(word in image_answers) for word in words], image)
        image_vars[index] = image

        grammar = model.new_bool_var(f"grammar_{index}")
        model.add_element(word_var, [int(word in grammar_answers) for word in words], grammar)
        grammar_vars[index] = grammar

        undesirable = model.new_bool_var(f"undesirable_{index}")
        model.add_element(
            word_var,
            [int(word in undesirable_answers) for word in words],
            undesirable,
        )
        undesirable_vars[index] = undesirable

        quality = model.new_int_var(0, 1000, f"quality_{index}")
        model.add_element(word_var, [max(0, round(frequency[word] * 100)) for word in words], quality)
        quality_terms.append(quality)

        # One compact extensional constraint links the selected word to all of
        # its letters. Crossing slots literally reuse the same cell variable.
        model.add_allowed_assignments(
            [word_var] + [cell_letters[cell] for cell in slots[index].cells],
            [
                [word_index] + [ord(letter) - 65 for letter in word]
                for word_index, word in enumerate(words)
            ],
        )

    # A word only competes with words of the same length; local indices are
    # shared because every slot of that length uses the same ordered list.
    by_length_vars = defaultdict(list)
    for index in variables:
        by_length_vars[len(slots[index].cells)].append(word_vars[index])
    for same_length in by_length_vars.values():
        if len(same_length) > 1:
            model.add_all_different(same_length)

    if target_mix is not None:
        for level, target in target_mix.items():
            matches = []
            code = LEVEL_CODE[level]
            for index in variables:
                match = model.new_bool_var(f"is_{level}_{index}")
                model.add(tier_vars[index] == code).only_enforce_if(match)
                model.add(tier_vars[index] != code).only_enforce_if(match.Not())
                matches.append(match)
            model.add(sum(matches) == target)

    if require_image:
        model.add(sum(image_vars.values()) >= minimum_images)
        model.add(sum(image_vars.values()) <= 6)
    for index in required_image_slots:
        if index not in image_vars:
            telemetry.update(reason="required_image_slot_missing", slot=index)
            return None
        model.add(image_vars[index] == 1)
    model.add(sum(grammar_vars.values()) <= max_grammar_answers)
    if max_undesirable_answers is not None:
        model.add(sum(undesirable_vars.values()) <= max_undesirable_answers)
    model.maximize(sum(quality_terms) - 1000 * sum(undesirable_vars.values()))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.05, max_seconds)
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = rng.randrange(1, 2_000_000_000)
    status = solver.solve(model)
    status_name = solver.status_name(status).lower()
    telemetry.update(
        reason="solved" if status in (cp_model.FEASIBLE, cp_model.OPTIMAL) else status_name,
        solver="cp-sat",
        status=status_name,
        branches=solver.num_branches,
        conflicts=solver.num_conflicts,
        elapsedSeconds=round(time.monotonic() - started, 3),
    )
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return None
    return {index: candidates[index][solver.value(word_vars[index])] for index in variables}
