"""Beam-search crossword filler inspired by MotsFlex's MIT auto-fill worker.

The implementation is original Python code for MotMan's slot/index model.  It
adapts three ideas from MotsFlex (Leo-Nicolle, MIT): keep several promising
states, score whole-grid letter viability, and reject a state immediately when
any slot or crossing cell has no remaining support.
"""
from __future__ import annotations

import math
import random
import time
from collections import defaultdict
from dataclasses import dataclass


def _bit_indexes(bits: int):
    while bits:
        least = bits & -bits
        yield least.bit_length() - 1
        bits ^= least


@dataclass(frozen=True)
class BeamState:
    domains: tuple[int, ...]
    score: float
    progress: int


def fill_motsflex_beam(
    slots,
    indexes,
    rng: random.Random,
    *,
    unavailable_answers: set[str] | None = None,
    answer_usage: dict[str, int] | None = None,
    grammar_answers: set[str] | None = None,
    maximum_grammar_answers: int = 1,
    maximum_active_answers: int = 3,
    required_image_slots: set[int] | None = None,
    image_answers: set[str] | None = None,
    beam_width: int = 96,
    branch_width: int = 18,
    max_seconds: float = 45.0,
    state_limit: int = 160_000,
    telemetry: dict | None = None,
) -> dict[int, str] | None:
    """Fill a fixed topology with beam search and global viability scoring."""
    started = time.monotonic()
    deadline = started + max_seconds
    telemetry = telemetry if telemetry is not None else {}
    unavailable_answers = unavailable_answers or set()
    answer_usage = answer_usage or {}
    grammar_answers = grammar_answers or set()
    required_image_slots = required_image_slots or set()
    image_answers = image_answers or set()
    by_length, _, frequency, concept_group, semantic_conflicts, _difficulty, _images = indexes
    variables = [index for index, slot in enumerate(slots) if slot.cells]
    slot_count = len(slots)

    words_by_length = {length: list(words) for length, words in by_length.items()}
    word_indexes = {
        length: {word: index for index, word in enumerate(words)}
        for length, words in words_by_length.items()
    }
    answer_lengths = {
        answer: length for length, words in words_by_length.items() for answer in words
    }

    letter_masks = defaultdict(lambda: defaultdict(dict))
    grammar_masks: dict[int, int] = {}
    active_masks: dict[int, int] = {}
    concept_masks = defaultdict(lambda: defaultdict(int))
    for length, words in words_by_length.items():
        for position in range(length):
            for code in range(26):
                letter_masks[length][position][code] = 0
        grammar_mask = 0
        active_mask = 0
        for index, word in enumerate(words):
            bit = 1 << index
            for position, letter in enumerate(word):
                letter_masks[length][position][ord(letter) - 65] |= bit
            if word in grammar_answers:
                grammar_mask |= bit
            if answer_usage.get(word, 0):
                active_mask |= bit
            concept_masks[length][concept_group[word]] |= bit
        grammar_masks[length] = grammar_mask
        active_masks[length] = active_mask

    initial = [0] * slot_count
    for variable in variables:
        length = len(slots[variable].cells)
        words = words_by_length.get(length, [])
        domain = (1 << len(words)) - 1
        if variable in required_image_slots:
            image_domain = 0
            for answer in image_answers:
                answer_index = word_indexes.get(length, {}).get(answer)
                if answer_index is not None:
                    image_domain |= 1 << answer_index
            domain &= image_domain
        for answer in unavailable_answers:
            answer_index = word_indexes.get(length, {}).get(answer)
            if answer_index is not None:
                domain &= ~(1 << answer_index)
        if not domain:
            telemetry.update(reason="initial-zero-domain", zeroDomainSlot=variable)
            return None
        initial[variable] = domain

    cell_links = defaultdict(list)
    for variable in variables:
        for position, cell in enumerate(slots[variable].cells):
            cell_links[cell].append((variable, position))
    crossing_cells_with_links = [
        (cell, links) for cell, links in cell_links.items() if len(links) == 2
    ]
    crossing_links = [links for _cell, links in crossing_cells_with_links]
    neighbor_links = defaultdict(list)
    arcs = []
    for links in crossing_links:
        left, right = links
        arcs.append((left[0], left[1], right[0], right[1]))
        arcs.append((right[0], right[1], left[0], left[1]))
        neighbor_links[left[0]].append((left[1], right[0], right[1]))
        neighbor_links[right[0]].append((right[1], left[0], left[1]))

    same_length_groups = defaultdict(list)
    for variable in variables:
        same_length_groups[len(slots[variable].cells)].append(variable)

    counters = defaultdict(int)
    zero_domain_by_slot = defaultdict(int)
    heatmap_zero_by_cell = defaultdict(int)
    mrv_selections_by_slot = defaultdict(int)

    def mark_zero_domain(variable: int) -> None:
        counters["zeroDomainRejects"] += 1
        zero_domain_by_slot[variable] += 1

    def decode_singleton(variable: int, domain: int) -> str:
        length = len(slots[variable].cells)
        return words_by_length[length][domain.bit_length() - 1]

    def propagate(domains: list[int]) -> tuple[int, ...] | None:
        changed = True
        while changed:
            changed = False
            assigned_words = []
            assigned_concepts = []
            assigned_grammar = 0
            assigned_active = 0
            for variable in variables:
                domain = domains[variable]
                if not domain:
                    mark_zero_domain(variable)
                    return None
                if domain.bit_count() == 1:
                    word = decode_singleton(variable, domain)
                    assigned_words.append(word)
                    assigned_concepts.append(concept_group[word])
                    assigned_grammar += word in grammar_answers
                    assigned_active += bool(answer_usage.get(word, 0))
            if len(assigned_words) != len(set(assigned_words)):
                counters["duplicateAnswerRejects"] += 1
                return None
            if len(assigned_concepts) != len(set(assigned_concepts)):
                counters["duplicateConceptRejects"] += 1
                return None
            if assigned_grammar > maximum_grammar_answers or assigned_active > maximum_active_answers:
                counters["editorialCardinalityRejects"] += 1
                return None

            used_words = set(assigned_words)
            used_concepts = set(assigned_concepts)
            conflict_answers = set()
            for word in assigned_words:
                conflict_answers.update(semantic_conflicts[word])

            for variable in variables:
                domain = domains[variable]
                if domain.bit_count() == 1:
                    continue
                length = len(slots[variable].cells)
                revised = domain
                for word in used_words | conflict_answers:
                    word_index = word_indexes.get(length, {}).get(word)
                    if word_index is not None:
                        revised &= ~(1 << word_index)
                for concept in used_concepts:
                    revised &= ~concept_masks[length].get(concept, 0)
                if assigned_grammar == maximum_grammar_answers:
                    revised &= ~grammar_masks[length]
                if assigned_active == maximum_active_answers:
                    revised &= ~active_masks[length]
                if not revised:
                    mark_zero_domain(variable)
                    return None
                if revised != domain:
                    domains[variable] = revised
                    changed = True

            for left, left_position, right, right_position in arcs:
                right_domain = domains[right]
                right_length = len(slots[right].cells)
                allowed = 0
                for code in range(26):
                    if right_domain & letter_masks[right_length][right_position][code]:
                        left_length = len(slots[left].cells)
                        allowed |= letter_masks[left_length][left_position][code]
                revised = domains[left] & allowed
                if not revised:
                    mark_zero_domain(left)
                    return None
                if revised != domains[left]:
                    domains[left] = revised
                    changed = True
        return tuple(domains)

    def heatmap_score(domains: tuple[int, ...]) -> float | None:
        """MotsFlex-style global score from viable crossing-letter masses."""
        total = 0.0
        minimum_letters = 27
        for cell, links in crossing_cells_with_links:
            left, right = links
            left_var, left_position = left
            right_var, right_position = right
            left_domain = domains[left_var]
            right_domain = domains[right_var]
            left_length = len(slots[left_var].cells)
            right_length = len(slots[right_var].cells)
            supported_letters = 0
            support_mass = 0
            for code in range(26):
                left_count = (left_domain & letter_masks[left_length][left_position][code]).bit_count()
                right_count = (right_domain & letter_masks[right_length][right_position][code]).bit_count()
                if left_count and right_count:
                    supported_letters += 1
                    support_mass += min(left_count, right_count)
            if not support_mass:
                counters["heatmapZeroRejects"] += 1
                heatmap_zero_by_cell[cell] += 1
                return None
            minimum_letters = min(minimum_letters, supported_letters)
            total += math.log1p(support_mass) + 0.12 * supported_letters
        unresolved_entropy = sum(
            math.log1p(domains[variable].bit_count())
            for variable in variables if domains[variable].bit_count() > 1
        )
        progress = sum(domains[variable].bit_count() == 1 for variable in variables)
        # Progress mirrors MotsFlex's placed-word term; viability and a modest
        # entropy reward keep the beam away from fragile nearly-zero branches.
        return 120.0 * progress + total + 0.08 * unresolved_entropy + 0.4 * minimum_letters

    def choose_mrv(domains: tuple[int, ...]) -> int:
        unresolved = [variable for variable in variables if domains[variable].bit_count() > 1]

        def risk(variable: int):
            cell_letter_support = []
            length = len(slots[variable].cells)
            for own_position, neighbor, neighbor_position in neighbor_links[variable]:
                neighbor_length = len(slots[neighbor].cells)
                supported = sum(
                    bool(domains[variable] & letter_masks[length][own_position][code])
                    and bool(domains[neighbor] & letter_masks[neighbor_length][neighbor_position][code])
                    for code in range(26)
                )
                cell_letter_support.append(supported)
            return (
                domains[variable].bit_count(),
                min(cell_letter_support, default=26),
                -len(neighbor_links[variable]),
            )

        return min(unresolved, key=risk)

    def candidate_order(variable: int, domains: tuple[int, ...]) -> list[int]:
        length = len(slots[variable].cells)
        candidates = list(_bit_indexes(domains[variable]))
        rng.shuffle(candidates)

        def support(candidate_index: int):
            word = words_by_length[length][candidate_index]
            crossing_support = 0
            for own_position, neighbor, neighbor_position in neighbor_links[variable]:
                neighbor_length = len(slots[neighbor].cells)
                code = ord(word[own_position]) - 65
                crossing_support += (
                    domains[neighbor] & letter_masks[neighbor_length][neighbor_position][code]
                ).bit_count()
            return (
                answer_usage.get(word, 0),
                int(word in grammar_answers),
                -crossing_support,
                -float(frequency.get(word, 0)),
            )

        candidates.sort(key=support)
        return candidates[:branch_width]

    root_domains = propagate(initial)
    if root_domains is None:
        telemetry.update(reason="root-infeasible")
        return None
    root_score = heatmap_score(root_domains)
    if root_score is None:
        telemetry.update(reason="root-heatmap-zero")
        return None
    root_progress = sum(root_domains[variable].bit_count() == 1 for variable in variables)
    beam = [BeamState(root_domains, root_score, root_progress)]
    visited = {root_domains}
    best_state = beam[0]
    layers = 0
    timed_out = False

    while beam and counters["statesExpanded"] < state_limit:
        if time.monotonic() >= deadline:
            timed_out = True
            break
        layers += 1
        next_states = []
        for state in beam:
            if time.monotonic() >= deadline:
                timed_out = True
                break
            if state.progress == len(variables):
                best_state = state
                beam = []
                break
            counters["statesExpanded"] += 1
            variable = choose_mrv(state.domains)
            mrv_selections_by_slot[variable] += 1
            for candidate_index in candidate_order(variable, state.domains):
                counters["statesGenerated"] += 1
                domains = list(state.domains)
                domains[variable] = 1 << candidate_index
                propagated = propagate(domains)
                if propagated is None or propagated in visited:
                    continue
                score = heatmap_score(propagated)
                if score is None:
                    continue
                progress = sum(propagated[item].bit_count() == 1 for item in variables)
                candidate_state = BeamState(propagated, score, progress)
                visited.add(propagated)
                next_states.append(candidate_state)
                if (progress, score) > (best_state.progress, best_state.score):
                    best_state = candidate_state
                if progress == len(variables):
                    beam = []
                    next_states = [candidate_state]
                    break
            if next_states and next_states[-1].progress == len(variables):
                break
        if next_states and next_states[-1].progress == len(variables):
            best_state = next_states[-1]
            break
        next_states.sort(key=lambda state: (state.progress, state.score), reverse=True)
        beam = next_states[:beam_width]
        counters["maximumBeamSize"] = max(counters["maximumBeamSize"], len(beam))

    elapsed = round(time.monotonic() - started, 3)
    solved = best_state.progress == len(variables)
    telemetry.update(
        solver="motsflex-inspired-beam",
        source="research-mots-flex (MIT), concepts adapted",
        beamWidth=beam_width,
        branchWidth=branch_width,
        layers=layers,
        bestProgress=best_state.progress,
        slotCount=len(variables),
        elapsedSeconds=elapsed,
        reason="solved" if solved else ("timeout" if timed_out else "beam-exhausted"),
        **dict(counters),
    )
    telemetry["zeroDomainHotspots"] = [
        {
            "slotIndex": variable,
            "count": count,
            "direction": slots[variable].direction,
            "clueCell": list(slots[variable].clue),
            "length": len(slots[variable].cells),
            "cells": [list(cell) for cell in slots[variable].cells],
        }
        for variable, count in sorted(
            zero_domain_by_slot.items(), key=lambda item: (-item[1], item[0])
        )[:12]
    ]
    telemetry["heatmapZeroHotspots"] = [
        {"cell": list(cell), "count": count}
        for cell, count in sorted(
            heatmap_zero_by_cell.items(), key=lambda item: (-item[1], item[0])
        )[:12]
    ]
    telemetry["mrvHotspots"] = [
        {
            "slotIndex": variable,
            "count": count,
            "direction": slots[variable].direction,
            "clueCell": list(slots[variable].clue),
            "length": len(slots[variable].cells),
        }
        for variable, count in sorted(
            mrv_selections_by_slot.items(), key=lambda item: (-item[1], item[0])
        )[:12]
    ]
    if not solved:
        return None
    return {
        variable: decode_singleton(variable, best_state.domains[variable])
        for variable in variables
    }
