"""Find the smallest lexical gaps for a fixed MotMan arrowword topology.

This is a diagnostic, not a publisher or a grid generator.  It keeps every
clue cell and path fixed, temporarily removes one or more answer constraints,
and fills all remaining slots from the reviewed central corpus.  Letters
imposed on the removed slots become precise patterns for targeted corpus
enrichment.
"""
from __future__ import annotations

import argparse
import gzip
import itertools
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from ortools.sat.python import cp_model


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as generator  # noqa: E402
from motsflex_beam_filler import fill_motsflex_beam  # noqa: E402


DEFAULT_SHAPES = ROOT / "output/quality/reference-style-shapes-a.json"
DEFAULT_REPORT = ROOT / "output/quality/reference-ribbon-a01-corpus-gaps.json"
LEXIQUE = ROOT / "src/data/lexique.lemmas.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
MORPHALOU = ROOT / "src/data/crossword.morphalou.staging.json.gz"


@dataclass(frozen=True)
class Slot:
    index: int
    slot_id: str
    direction: str
    clue_cell: tuple[int, int]
    cells: tuple[tuple[int, int], ...]

    @property
    def length(self) -> int:
        return len(self.cells)

    @property
    def clue(self) -> tuple[int, int]:
        return self.clue_cell


def load_shape(path: Path, shape_id: str) -> tuple[dict, list[Slot]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    shape = next(item for item in document["shapes"] if item["id"] == shape_id)
    slots = [
        Slot(
            index=index,
            slot_id=item["slotId"],
            direction=item["direction"],
            clue_cell=tuple(item["clueCell"]),
            cells=tuple(tuple(cell) for cell in item["cells"]),
        )
        for index, item in enumerate(shape["slots"])
    ]
    return shape, slots


def load_words() -> tuple[dict[int, tuple[str, ...]], dict[str, dict]]:
    entries = generator.load_entries()
    canonical: dict[str, dict] = {}
    for entry in entries:
        canonical.setdefault(entry["answer"], entry)
    by_length: dict[int, list[str]] = defaultdict(list)
    for answer in canonical:
        by_length[len(answer)].append(answer)
    return (
        {length: tuple(sorted(words)) for length, words in by_length.items()},
        canonical,
    )


def load_expansion_words(
    central: dict[str, dict],
    *,
    permissive: bool = False,
    include_morphalou: bool = False,
) -> tuple[dict[int, tuple[str, ...]], dict[str, dict], dict]:
    lexique_document = json.loads(LEXIQUE.read_text(encoding="utf-8"))
    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    excluded = set(blacklist.get("rejectedAnswers", []))
    excluded.update(
        item["answer"] for item in blacklist.get("rotationCooldownAnswers", [])
    )
    allowed_pos = {"NOM", "ADJ", "VER", "ADV"}
    metadata: dict[str, dict] = {}
    rejected_by_rule = Counter()
    for entry in lexique_document["entries"]:
        answer = entry["answer"]
        if not 3 <= len(answer) <= 9:
            rejected_by_rule["length"] += 1
            continue
        if answer in excluded:
            rejected_by_rule["owner-blacklist-or-cooldown"] += 1
            continue
        if not permissive and entry.get("partOfSpeech") not in allowed_pos:
            rejected_by_rule["part-of-speech"] += 1
            continue
        frequency = float(entry.get("sourceFrequency", 0) or 0)
        school = float(entry.get("schoolFrequency", 0) or 0)
        threshold = 2.0 if len(answer) == 3 else (1.0 if len(answer) == 4 else 0.5)
        if not permissive and frequency < threshold and school < 100:
            rejected_by_rule["frequency"] += 1
            continue
        previous = metadata.get(answer)
        if previous is None or (
            frequency + school / 1000
            > float(previous.get("sourceFrequency", 0) or 0)
            + float(previous.get("schoolFrequency", 0) or 0) / 1000
        ):
            metadata[answer] = entry
    lexique_answers = set(metadata)
    central_answers = set(central)
    morphalou_added_answers: set[str] = set()
    morphalou_rejected = Counter()
    if include_morphalou:
        with gzip.open(MORPHALOU, "rt", encoding="utf-8") as handle:
            morphalou = json.load(handle)
        allowed_morphalou_pos = {"common-noun", "adjective", "verb", "adverb"}
        # Inflections are useful only when their base lemma has already passed
        # the central/Lexique commonness filter. This keeps ordinary plurals
        # and conjugations without opening the solver to every rare paradigm.
        common_lemma_answers = set(metadata)
        for entry in morphalou["entries"]:
            answer = entry["answer"]
            if answer in excluded:
                morphalou_rejected["owner-blacklist-or-cooldown"] += 1
                continue
            if entry["partOfSpeech"] not in allowed_morphalou_pos:
                morphalou_rejected["part-of-speech"] += 1
                continue
            if (
                entry.get("formType") == "inflected"
                and entry.get("lemmaAnswer") not in common_lemma_answers
            ):
                morphalou_rejected["inflected-lemma-not-common"] += 1
                continue
            if answer not in metadata:
                lemma_metadata = metadata.get(entry.get("lemmaAnswer", ""), {})
                metadata[answer] = {
                    **entry,
                    "sourceFrequency": float(
                        lemma_metadata.get("sourceFrequency", 0) or 0
                    ),
                    "schoolFrequency": float(
                        lemma_metadata.get("schoolFrequency", 0) or 0
                    ),
                    "difficulty": "unreviewed",
                }
                morphalou_added_answers.add(answer)

    metadata.update(
        {
            answer: {
                "answer": answer,
                "length": len(answer),
                "partOfSpeech": "CENTRAL",
                "sourceFrequency": float(entry.get("frequency", 0) or 0),
                "schoolFrequency": 0,
                "difficulty": entry.get("difficulty", "normal"),
            }
            for answer, entry in central.items()
        }
    )
    by_length: dict[int, list[str]] = defaultdict(list)
    for answer in metadata:
        by_length[len(answer)].append(answer)
    stats = {
        "centralAnswers": len(central),
        "lexiqueCandidatesAfterOwnerModel": len(lexique_answers),
        "lexiqueNewAnswersBeyondCentral": len(lexique_answers - central_answers),
        "combinedAnswers": len(metadata),
        "morphalouCandidatesAdded": len(morphalou_added_answers),
        "morphalouNewAnswersBeyondCentralAndLexique": len(
            morphalou_added_answers - central_answers - lexique_answers
        ),
        "morphalouRejectedByRule": dict(morphalou_rejected),
        "rejectedByRule": dict(rejected_by_rule),
        "policy": {
            "allowedPartOfSpeech": sorted(allowed_pos),
            "minimumSourceFrequency": {"3": 2.0, "4": 1.0, "5to9": 0.5},
            "schoolFrequencyOverride": 100,
            "ownerRejectedAndCooldownAnswersExcluded": True,
            "permissiveStructuralReservoir": permissive,
            "morphalouStructuralReservoirIncluded": include_morphalou,
        },
    }
    return (
        {length: tuple(sorted(words)) for length, words in by_length.items()},
        metadata,
        stats,
    )


def crossing_arcs(slots: list[Slot]) -> tuple[dict[tuple[int, int], list[tuple[int, int]]], dict[int, list[tuple[int, int, int]]]]:
    cell_links: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for slot in slots:
        for position, cell in enumerate(slot.cells):
            cell_links[cell].append((slot.index, position))
    neighbors: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for links in cell_links.values():
        if len(links) != 2:
            continue
        (left, left_position), (right, right_position) = links
        neighbors[left].append((right, left_position, right_position))
        neighbors[right].append((left, right_position, left_position))
    return cell_links, neighbors


def revise(
    domains: dict[int, set[str]],
    left: int,
    right: int,
    left_position: int,
    right_position: int,
) -> bool:
    supported = {word[right_position] for word in domains[right]}
    reduced = {word for word in domains[left] if word[left_position] in supported}
    if reduced == domains[left]:
        return False
    domains[left] = reduced
    return True


def enforce_arc_consistency(
    domains: dict[int, set[str]],
    active: set[int],
    neighbors: dict[int, list[tuple[int, int, int]]],
) -> bool:
    queue = deque(
        (left, right, left_position, right_position)
        for left in active
        for right, left_position, right_position in neighbors[left]
        if right in active
    )
    while queue:
        left, right, left_position, right_position = queue.popleft()
        if revise(domains, left, right, left_position, right_position):
            if not domains[left]:
                return False
            for previous, left_position_again, previous_position in neighbors[left]:
                if previous in active and previous != right:
                    queue.append(
                        (previous, left, previous_position, left_position_again)
                    )
    return True


def solve_subset(
    slots: list[Slot],
    words_by_length: dict[int, tuple[str, ...]],
    neighbors: dict[int, list[tuple[int, int, int]]],
    dropped: set[int],
    node_limit: int,
) -> tuple[dict[int, str] | None, dict]:
    active = {slot.index for slot in slots} - dropped
    domains = {
        index: set(words_by_length.get(slots[index].length, ())) for index in active
    }
    telemetry = {"nodes": 0, "domainWipeouts": Counter(), "nodeLimit": node_limit}
    if any(not domain for domain in domains.values()):
        return None, telemetry
    if not enforce_arc_consistency(domains, active, neighbors):
        return None, telemetry

    def search(current: dict[int, set[str]], used: set[str]) -> dict[int, str] | None:
        telemetry["nodes"] += 1
        if telemetry["nodes"] > node_limit:
            return None
        unresolved = [index for index in active if len(current[index]) > 1]
        if not unresolved:
            chosen = {index: next(iter(current[index])) for index in active}
            return chosen if len(set(chosen.values())) == len(chosen) else None
        index = min(
            unresolved,
            key=lambda item: (len(current[item]), -len(neighbors[item]), item),
        )
        for word in sorted(current[index]):
            if word in used:
                continue
            next_domains = {item: set(domain) for item, domain in current.items()}
            next_domains[index] = {word}
            valid = True
            for other in active:
                if other == index or len(next_domains[other]) == 1:
                    continue
                if word in next_domains[other]:
                    next_domains[other].remove(word)
                    if not next_domains[other]:
                        telemetry["domainWipeouts"][other] += 1
                        valid = False
                        break
            if valid and enforce_arc_consistency(next_domains, active, neighbors):
                solved = search(next_domains, used | {word})
                if solved is not None:
                    return solved
        return None

    solution = search(domains, set())
    telemetry["domainWipeouts"] = dict(telemetry["domainWipeouts"])
    return solution, telemetry


def solve_subset_cp_sat(
    slots: list[Slot],
    words_by_length: dict[int, tuple[str, ...]],
    dropped: set[int],
    max_seconds: float,
) -> tuple[dict[int, str] | None, dict]:
    active = [slot.index for slot in slots if slot.index not in dropped]
    model = cp_model.CpModel()
    all_cells = sorted({cell for slot in slots for cell in slot.cells})
    letters = {
        cell: model.new_int_var(0, 25, f"cell_{cell[0]}_{cell[1]}")
        for cell in all_cells
    }
    global_words = sorted({word for words in words_by_length.values() for word in words})
    word_ids = {word: index for index, word in enumerate(global_words)}
    answer_vars = []
    for index in active:
        slot = slots[index]
        candidates = words_by_length.get(slot.length, ())
        if not candidates:
            return None, {"status": "empty-domain", "slotIndex": index}
        answer_var = model.new_int_var(0, len(global_words) - 1, f"answer_{index}")
        answer_vars.append(answer_var)
        variables = [answer_var] + [letters[cell] for cell in slot.cells]
        tuples = [
            [word_ids[word]] + [ord(letter) - 65 for letter in word]
            for word in candidates
        ]
        model.add_allowed_assignments(variables, tuples)
    model.add_all_different(answer_vars)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 20260717
    status = solver.solve(model)
    telemetry = {
        "status": solver.status_name(status),
        "branches": solver.num_branches,
        "conflicts": solver.num_conflicts,
        "wallTimeSeconds": round(solver.wall_time, 4),
    }
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, telemetry
    id_to_word = {index: word for word, index in word_ids.items()}
    return (
        {
            index: id_to_word[solver.value(answer_vars[position])]
            for position, index in enumerate(active)
        },
        telemetry,
    )


def solve_maximum_coverage_cp_sat(
    slots: list[Slot],
    words_by_length: dict[int, tuple[str, ...]],
    max_seconds: float,
) -> tuple[dict[int, str], tuple[int, ...], dict]:
    model = cp_model.CpModel()
    all_cells = sorted({cell for slot in slots for cell in slot.cells})
    letters = {
        cell: model.new_int_var(0, 25, f"cell_{cell[0]}_{cell[1]}")
        for cell in all_cells
    }
    global_words = sorted({word for words in words_by_length.values() for word in words})
    word_ids = {word: index for index, word in enumerate(global_words)}
    id_to_word = {index: word for word, index in word_ids.items()}
    enabled_vars = []
    answer_vars = []
    first_dummy = len(global_words)
    for slot in slots:
        enabled = model.new_bool_var(f"enabled_{slot.index}")
        enabled_vars.append(enabled)
        answer_var = model.new_int_var(
            0, first_dummy + len(slots) - 1, f"answer_{slot.index}"
        )
        answer_vars.append(answer_var)
        candidates = words_by_length.get(slot.length, ())
        variables = [answer_var] + [letters[cell] for cell in slot.cells]
        tuples = [
            [word_ids[word]] + [ord(letter) - 65 for letter in word]
            for word in candidates
        ]
        model.add_allowed_assignments(variables, tuples).only_enforce_if(enabled)
        model.add(answer_var == first_dummy + slot.index).only_enforce_if(
            enabled.negated()
        )
    model.add_all_different(answer_vars)
    model.maximize(sum(enabled_vars))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 20260717
    status = solver.solve(model)
    telemetry = {
        "status": solver.status_name(status),
        "branches": solver.num_branches,
        "conflicts": solver.num_conflicts,
        "wallTimeSeconds": round(solver.wall_time, 4),
        "objective": solver.objective_value,
        "bestObjectiveBound": solver.best_objective_bound,
    }
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {}, tuple(range(len(slots))), telemetry
    solution = {
        slot.index: id_to_word[solver.value(answer_vars[slot.index])]
        for slot in slots
        if solver.value(enabled_vars[slot.index])
    }
    dropped = tuple(
        slot.index for slot in slots if not solver.value(enabled_vars[slot.index])
    )
    return solution, dropped, telemetry


def solve_minimum_expansion_cp_sat(
    slots: list[Slot],
    words_by_length: dict[int, tuple[str, ...]],
    central_answers: set[str],
    metadata: dict[str, dict],
    max_seconds: float,
) -> tuple[dict[int, str] | None, dict]:
    model = cp_model.CpModel()
    all_cells = sorted({cell for slot in slots for cell in slot.cells})
    letters = {
        cell: model.new_int_var(0, 25, f"cell_{cell[0]}_{cell[1]}")
        for cell in all_cells
    }
    global_words = sorted({word for words in words_by_length.values() for word in words})
    word_ids = {word: index for index, word in enumerate(global_words)}
    id_to_word = {index: word for word, index in word_ids.items()}
    answer_vars = []
    expansion_vars = []
    quality_vars = []

    def quality_penalty(answer: str) -> int:
        if answer in central_answers:
            return 0
        entry = metadata[answer]
        frequency = float(entry.get("sourceFrequency", 0) or 0)
        school = float(entry.get("schoolFrequency", 0) or 0)
        evidence = frequency + school / 500
        return max(0, min(20_000, int(12_000 - 2_000 * math.log1p(evidence))))

    for slot in slots:
        candidates = words_by_length.get(slot.length, ())
        answer_var = model.new_int_var(0, len(global_words) - 1, f"answer_{slot.index}")
        expansion_var = model.new_bool_var(f"expansion_{slot.index}")
        quality_var = model.new_int_var(0, 20_000, f"quality_{slot.index}")
        answer_vars.append(answer_var)
        expansion_vars.append(expansion_var)
        quality_vars.append(quality_var)
        variables = [answer_var, expansion_var, quality_var] + [
            letters[cell] for cell in slot.cells
        ]
        tuples = [
            [
                word_ids[word],
                int(word not in central_answers),
                quality_penalty(word),
            ]
            + [ord(letter) - 65 for letter in word]
            for word in candidates
        ]
        model.add_allowed_assignments(variables, tuples)
    model.add_all_different(answer_vars)
    model.minimize(1_000_000 * sum(expansion_vars) + sum(quality_vars))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 20260717
    status = solver.solve(model)
    telemetry = {
        "status": solver.status_name(status),
        "branches": solver.num_branches,
        "conflicts": solver.num_conflicts,
        "wallTimeSeconds": round(solver.wall_time, 4),
        "objective": solver.objective_value,
        "bestObjectiveBound": solver.best_objective_bound,
    }
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, telemetry
    return (
        {
            slot.index: id_to_word[solver.value(answer_vars[slot.index])]
            for slot in slots
        },
        telemetry,
    )


def solve_minimum_expansion_beam(
    slots: list[Slot],
    words_by_length: dict[int, tuple[str, ...]],
    central_answers: set[str],
    metadata: dict[str, dict],
    max_seconds: float,
    seed: int,
) -> tuple[dict[int, str] | None, dict]:
    by_length = {
        length: list(words) for length, words in words_by_length.items()
    }
    frequency = {
        answer: float(entry.get("sourceFrequency", 0) or 0)
        for answer, entry in metadata.items()
    }
    concept_group = {answer: answer for answer in metadata}
    semantic_conflicts = {answer: set() for answer in metadata}
    difficulty = {
        answer: entry.get("difficulty", "normal") for answer, entry in metadata.items()
    }
    indexes = (
        by_length,
        {},
        frequency,
        concept_group,
        semantic_conflicts,
        difficulty,
        set(),
    )
    answer_usage = {
        answer: int(answer not in central_answers) for answer in metadata
    }
    telemetry: dict = {}
    solution = fill_motsflex_beam(
        slots,
        indexes,
        random.Random(seed),
        answer_usage=answer_usage,
        maximum_active_answers=len(slots),
        maximum_grammar_answers=len(slots),
        beam_width=768,
        branch_width=96,
        max_seconds=max_seconds,
        state_limit=750_000,
        telemetry=telemetry,
    )
    return solution, telemetry


def solve_minimum_expansion_letters_cp_sat(
    slots: list[Slot],
    words_by_length: dict[int, tuple[str, ...]],
    central_answers: set[str],
    max_seconds: float,
) -> tuple[dict[int, str] | None, dict]:
    model = cp_model.CpModel()
    all_cells = sorted({cell for slot in slots for cell in slot.cells})
    letters = {
        cell: model.new_int_var(0, 25, f"cell_{cell[0]}_{cell[1]}")
        for cell in all_cells
    }
    expansion_vars = []
    for slot in slots:
        expansion = model.new_bool_var(f"expansion_{slot.index}")
        expansion_vars.append(expansion)
        variables = [expansion] + [letters[cell] for cell in slot.cells]
        tuples = [
            [int(word not in central_answers)]
            + [ord(letter) - 65 for letter in word]
            for word in words_by_length.get(slot.length, ())
        ]
        model.add_allowed_assignments(variables, tuples)
    model.minimize(sum(expansion_vars))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 20260717
    status = solver.solve(model)
    telemetry = {
        "status": solver.status_name(status),
        "branches": solver.num_branches,
        "conflicts": solver.num_conflicts,
        "wallTimeSeconds": round(solver.wall_time, 4),
        "objective": solver.objective_value,
        "bestObjectiveBound": solver.best_objective_bound,
    }
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, telemetry
    solution = {}
    for slot in slots:
        solution[slot.index] = "".join(
            chr(solver.value(letters[cell]) + 65) for cell in slot.cells
        )
    if len(set(solution.values())) != len(solution):
        telemetry["duplicateAnswers"] = [
            answer for answer, count in Counter(solution.values()).items() if count > 1
        ]
    return solution, telemetry


def solve_minimum_expansion_exact_bitset(
    slots: list[Slot],
    words_by_length: dict[int, tuple[str, ...]],
    central_answers: set[str],
    metadata: dict[str, dict],
    max_seconds: float,
    minimum_new: int = 2,
    maximum_new: int = 8,
    seed: int = 20260717,
) -> tuple[dict[int, str] | None, dict]:
    started = time.monotonic()
    deadline = started + max_seconds
    word_indexes = {
        length: {word: index for index, word in enumerate(words)}
        for length, words in words_by_length.items()
    }
    letter_masks: dict[int, list[list[int]]] = {}
    central_masks: dict[int, int] = {}
    for length, words in words_by_length.items():
        masks = [[0 for _ in range(26)] for _ in range(length)]
        central_mask = 0
        for word_index, word in enumerate(words):
            bit = 1 << word_index
            if word in central_answers:
                central_mask |= bit
            for position, letter in enumerate(word):
                masks[position][ord(letter) - 65] |= bit
        letter_masks[length] = masks
        central_masks[length] = central_mask

    _cell_links, neighbors = crossing_arcs(slots)
    arcs = [
        (left, right, left_position, right_position)
        for left in range(len(slots))
        for right, left_position, right_position in neighbors[left]
    ]
    same_length: dict[int, list[int]] = defaultdict(list)
    for slot in slots:
        same_length[slot.length].append(slot.index)

    counters = Counter()
    best_progress = 0
    best_domains: tuple[int, ...] | None = None
    timed_out = False
    rng = random.Random(seed)

    def decode(slot_index: int, domain: int) -> str:
        return words_by_length[slots[slot_index].length][domain.bit_length() - 1]

    def propagate(domains: list[int], maximum_expansions: int) -> tuple[int, ...] | None:
        nonlocal best_progress, best_domains
        changed = True
        while changed:
            if time.monotonic() >= deadline:
                return None
            changed = False
            singleton_words: dict[int, str] = {}
            new_count = 0
            for index, domain in enumerate(domains):
                if not domain:
                    counters["domainWipeouts"] += 1
                    return None
                if domain.bit_count() == 1:
                    word = decode(index, domain)
                    singleton_words[index] = word
                    new_count += word not in central_answers
            if len(set(singleton_words.values())) != len(singleton_words):
                counters["duplicateRejects"] += 1
                return None
            if new_count > maximum_expansions:
                counters["expansionBoundRejects"] += 1
                return None
            if new_count == maximum_expansions:
                for index, domain in enumerate(domains):
                    if domain.bit_count() == 1:
                        continue
                    revised = domain & central_masks[slots[index].length]
                    if not revised:
                        counters["expansionBoundRejects"] += 1
                        return None
                    if revised != domain:
                        domains[index] = revised
                        changed = True

            for index, word in singleton_words.items():
                length = slots[index].length
                bit = 1 << word_indexes[length][word]
                for other in same_length[length]:
                    if other == index or domains[other].bit_count() == 1:
                        continue
                    if domains[other] & bit:
                        domains[other] &= ~bit
                        if not domains[other]:
                            counters["duplicateRejects"] += 1
                            return None
                        changed = True

            for left, right, left_position, right_position in arcs:
                right_domain = domains[right]
                right_length = slots[right].length
                left_length = slots[left].length
                allowed = 0
                for code in range(26):
                    if right_domain & letter_masks[right_length][right_position][code]:
                        allowed |= letter_masks[left_length][left_position][code]
                revised = domains[left] & allowed
                if not revised:
                    counters["arcWipeouts"] += 1
                    return None
                if revised != domains[left]:
                    domains[left] = revised
                    changed = True

        progress = sum(domain.bit_count() == 1 for domain in domains)
        if progress > best_progress:
            best_progress = progress
            best_domains = tuple(domains)
        return tuple(domains)

    def bit_indexes(bits: int):
        while bits:
            least = bits & -bits
            yield least.bit_length() - 1
            bits ^= least

    def candidate_order(slot_index: int, domains: tuple[int, ...]) -> list[int]:
        length = slots[slot_index].length
        candidates = list(bit_indexes(domains[slot_index]))

        def score(word_index: int) -> tuple:
            word = words_by_length[length][word_index]
            support = 0
            for neighbor, own_position, neighbor_position in neighbors[slot_index]:
                neighbor_length = slots[neighbor].length
                code = ord(word[own_position]) - 65
                support += (
                    domains[neighbor]
                    & letter_masks[neighbor_length][neighbor_position][code]
                ).bit_count()
            entry = metadata[word]
            frequency = float(entry.get("sourceFrequency", 0) or 0) + float(
                entry.get("schoolFrequency", 0) or 0
            ) / 1000
            return (-support, word not in central_answers, -frequency)

        candidates.sort(key=score)
        # Rotate the strongest supported candidates between deterministic
        # seeds.  This preserves viability ranking while preventing every
        # run from spending its entire budget in the same attractive dead end.
        window = min(64, len(candidates))
        rotated = candidates[:window]
        rng.shuffle(rotated)
        candidates[:window] = rotated
        return candidates

    def search(domains: tuple[int, ...], maximum_expansions: int) -> dict[int, str] | None:
        nonlocal timed_out
        if time.monotonic() >= deadline:
            timed_out = True
            return None
        counters["nodes"] += 1
        unresolved = [
            index for index, domain in enumerate(domains) if domain.bit_count() > 1
        ]
        if not unresolved:
            return {index: decode(index, domain) for index, domain in enumerate(domains)}
        index = min(
            unresolved,
            key=lambda item: (
                domains[item].bit_count(),
                -len(neighbors[item]),
                item,
            ),
        )
        for word_index in candidate_order(index, domains):
            next_domains = list(domains)
            next_domains[index] = 1 << word_index
            propagated = propagate(next_domains, maximum_expansions)
            if propagated is None:
                if timed_out or time.monotonic() >= deadline:
                    timed_out = True
                    return None
                continue
            solution = search(propagated, maximum_expansions)
            if solution is not None:
                return solution
            if timed_out:
                return None
        return None

    initial = tuple(
        (1 << len(words_by_length[slot.length])) - 1 for slot in slots
    )
    solved = None
    solved_bound = None
    attempted_bounds = []
    for maximum_expansions in range(minimum_new, maximum_new + 1):
        if time.monotonic() >= deadline:
            timed_out = True
            break
        attempted_bounds.append(maximum_expansions)
        propagated = propagate(list(initial), maximum_expansions)
        if propagated is None:
            if time.monotonic() >= deadline:
                timed_out = True
                break
            continue
        solved = search(propagated, maximum_expansions)
        if solved is not None:
            solved_bound = maximum_expansions
            break
        if timed_out:
            break
    telemetry = {
        "solver": "exact-bitset-fixed-topology",
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "reason": "solved" if solved is not None else ("timeout" if timed_out else "exhausted"),
        "attemptedExpansionBounds": attempted_bounds,
        "solvedExpansionBound": solved_bound,
        "seed": seed,
        "bestProgress": best_progress,
        "slotCount": len(slots),
        **dict(counters),
    }
    if best_domains is not None:
        telemetry["bestSingletons"] = [
            {
                "slotIndex": index,
                "slotId": slots[index].slot_id,
                "answer": decode(index, domain),
            }
            for index, domain in enumerate(best_domains)
            if domain.bit_count() == 1
        ]
    return solved, telemetry


def build_word_automaton(words: tuple[str, ...]) -> tuple[int, list[int], list[tuple[int, int, int]]]:
    transitions_by_key: dict[tuple[int, int], int] = {}
    next_state = 1
    final_states = set()
    for word in words:
        state = 0
        for letter in word:
            code = ord(letter) - 65
            key = (state, code)
            target = transitions_by_key.get(key)
            if target is None:
                target = next_state
                next_state += 1
                transitions_by_key[key] = target
            state = target
        final_states.add(state)
    transitions = [
        (source, code, target)
        for (source, code), target in transitions_by_key.items()
    ]
    return 0, sorted(final_states), transitions


def solve_lexical_automaton_cp_sat(
    slots: list[Slot],
    words_by_length: dict[int, tuple[str, ...]],
    max_seconds: float,
    seed: int,
) -> tuple[dict[int, str] | None, dict]:
    model = cp_model.CpModel()
    all_cells = sorted({cell for slot in slots for cell in slot.cells})
    letters = {
        cell: model.new_int_var(0, 25, f"cell_{cell[0]}_{cell[1]}")
        for cell in all_cells
    }
    automata = {
        length: build_word_automaton(words)
        for length, words in words_by_length.items()
        if words
    }
    for slot in slots:
        start, finals, transitions = automata[slot.length]
        model.add_automaton(
            [letters[cell] for cell in slot.cells],
            start,
            finals,
            transitions,
        )
    model.add_decision_strategy(
        [letters[cell] for cell in all_cells],
        cp_model.CHOOSE_MIN_DOMAIN_SIZE,
        cp_model.SELECT_MIN_VALUE,
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = seed
    solver.parameters.search_branching = cp_model.PORTFOLIO_SEARCH
    status = solver.solve(model)
    telemetry = {
        "solver": "cp-sat-prefix-automata",
        "status": solver.status_name(status),
        "branches": solver.num_branches,
        "conflicts": solver.num_conflicts,
        "wallTimeSeconds": round(solver.wall_time, 4),
        "seed": seed,
        "automatonStatesByLength": {
            str(length): max(
                [target for _source, _code, target in transitions], default=0
            ) + 1
            for length, (_start, _finals, transitions) in automata.items()
        },
    }
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, telemetry
    solution = {
        slot.index: "".join(
            chr(solver.value(letters[cell]) + 65) for cell in slot.cells
        )
        for slot in slots
    }
    duplicates = [
        answer for answer, count in Counter(solution.values()).items() if count > 1
    ]
    if duplicates:
        telemetry["duplicateAnswers"] = duplicates
    return solution, telemetry


def solve_minimum_expansion_element_cp_sat(
    slots: list[Slot],
    words_by_length: dict[int, tuple[str, ...]],
    central_answers: set[str],
    max_seconds: float,
    seed: int,
) -> tuple[dict[int, str] | None, dict]:
    model = cp_model.CpModel()
    all_cells = sorted({cell for slot in slots for cell in slot.cells})
    letters = {
        cell: model.new_int_var(0, 25, f"cell_{cell[0]}_{cell[1]}")
        for cell in all_cells
    }
    word_vars = {}
    expansion_vars = []
    by_length_slot_vars: dict[int, list] = defaultdict(list)
    for slot in slots:
        words = words_by_length[slot.length]
        word_var = model.new_int_var(0, len(words) - 1, f"word_{slot.index}")
        word_vars[slot.index] = word_var
        by_length_slot_vars[slot.length].append(word_var)
        for position, cell in enumerate(slot.cells):
            model.add_element(
                word_var,
                [ord(word[position]) - 65 for word in words],
                letters[cell],
            )
        expansion = model.new_int_var(0, 1, f"expansion_{slot.index}")
        model.add_element(
            word_var,
            [int(word not in central_answers) for word in words],
            expansion,
        )
        expansion_vars.append(expansion)
    for variables in by_length_slot_vars.values():
        if len(variables) > 1:
            model.add_all_different(variables)
    model.minimize(sum(expansion_vars))
    model.add_decision_strategy(
        list(word_vars.values()),
        cp_model.CHOOSE_MIN_DOMAIN_SIZE,
        cp_model.SELECT_MIN_VALUE,
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = seed
    status = solver.solve(model)
    telemetry = {
        "solver": "cp-sat-word-index-elements",
        "status": solver.status_name(status),
        "branches": solver.num_branches,
        "conflicts": solver.num_conflicts,
        "wallTimeSeconds": round(solver.wall_time, 4),
        "objective": solver.objective_value,
        "bestObjectiveBound": solver.best_objective_bound,
        "seed": seed,
        "domainSizesByLength": {
            str(length): len(words) for length, words in words_by_length.items()
        },
    }
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, telemetry
    solution = {
        slot.index: words_by_length[slot.length][solver.value(word_vars[slot.index])]
        for slot in slots
    }
    return solution, telemetry


def imposed_patterns(
    slots: list[Slot],
    solution: dict[int, str],
    dropped: tuple[int, ...],
    cell_links: dict[tuple[int, int], list[tuple[int, int]]],
) -> list[dict]:
    items = []
    for index in dropped:
        letters = []
        for cell in slots[index].cells:
            letter = "?"
            for other, position in cell_links[cell]:
                if other in solution:
                    letter = solution[other][position]
                    break
            letters.append(letter)
        items.append(
            {
                "slotIndex": index,
                "slotId": slots[index].slot_id,
                "direction": slots[index].direction,
                "clueCell": list(slots[index].clue_cell),
                "length": slots[index].length,
                "pattern": "".join(letters),
            }
        )
    return items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shape-file", type=Path, default=DEFAULT_SHAPES)
    parser.add_argument("--shape-id", default="reference-ribbon-a-01")
    parser.add_argument("--min-dropped", type=int, default=0)
    parser.add_argument("--max-dropped", type=int, default=2)
    parser.add_argument("--solutions-per-level", type=int, default=30)
    parser.add_argument("--node-limit", type=int, default=500_000)
    parser.add_argument("--method", choices=("cp-sat", "backtracking"), default="cp-sat")
    parser.add_argument("--seconds-per-combination", type=float, default=8.0)
    parser.add_argument("--maximize-coverage", action="store_true")
    parser.add_argument("--maximum-coverage-seconds", type=float, default=90.0)
    parser.add_argument("--minimum-expansion", action="store_true")
    parser.add_argument("--minimum-expansion-seconds", type=float, default=180.0)
    parser.add_argument(
        "--minimum-expansion-method",
        choices=("beam", "cp-sat", "letters-cp-sat", "exact-bitset", "automaton", "element-cp-sat"),
        default="beam",
    )
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument("--minimum-new-answers", type=int, default=2)
    parser.add_argument("--maximum-new-answers", type=int, default=8)
    parser.add_argument("--permissive-lexique", action="store_true")
    parser.add_argument("--include-morphalou", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    shape, slots = load_shape(args.shape_file, args.shape_id)
    words_by_length, canonical = load_words()
    cell_links, neighbors = crossing_arcs(slots)

    if args.minimum_expansion:
        expansion_words, expansion_metadata, expansion_stats = load_expansion_words(
            canonical,
            permissive=args.permissive_lexique,
            include_morphalou=args.include_morphalou,
        )
        if args.minimum_expansion_method == "beam":
            solution, telemetry = solve_minimum_expansion_beam(
                slots,
                expansion_words,
                set(canonical),
                expansion_metadata,
                args.minimum_expansion_seconds,
                args.seed,
            )
        elif args.minimum_expansion_method == "cp-sat":
            solution, telemetry = solve_minimum_expansion_cp_sat(
                slots,
                expansion_words,
                set(canonical),
                expansion_metadata,
                args.minimum_expansion_seconds,
            )
        elif args.minimum_expansion_method == "letters-cp-sat":
            solution, telemetry = solve_minimum_expansion_letters_cp_sat(
                slots,
                expansion_words,
                set(canonical),
                args.minimum_expansion_seconds,
            )
        elif args.minimum_expansion_method == "exact-bitset":
            solution, telemetry = solve_minimum_expansion_exact_bitset(
                slots,
                expansion_words,
                set(canonical),
                expansion_metadata,
                args.minimum_expansion_seconds,
                minimum_new=args.minimum_new_answers,
                maximum_new=args.maximum_new_answers,
                seed=args.seed,
            )
        elif args.minimum_expansion_method == "automaton":
            solution, telemetry = solve_lexical_automaton_cp_sat(
                slots,
                expansion_words,
                args.minimum_expansion_seconds,
                args.seed,
            )
        else:
            solution, telemetry = solve_minimum_expansion_element_cp_sat(
                slots,
                expansion_words,
                set(canonical),
                args.minimum_expansion_seconds,
                args.seed,
            )
        selected = [] if solution is None else [
            {
                "slotIndex": index,
                "slotId": slots[index].slot_id,
                "answer": solution[index],
                "central": solution[index] in canonical,
                "clue": canonical.get(solution[index], {}).get("clue"),
                "lexique": expansion_metadata[solution[index]],
            }
            for index in sorted(solution)
        ]
        report = {
            "version": 1,
            "kind": "fixed-shape-minimum-targeted-corpus-expansion",
            "shapeId": shape["id"],
            "shapeModified": False,
            "slotCount": len(slots),
            "complete": solution is not None,
            "newAnswerCount": sum(not item["central"] for item in selected),
            "newAnswers": [item for item in selected if not item["central"]],
            "allAnswers": selected,
            "corpusFilter": expansion_stats,
            "solverTelemetry": telemetry,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "output": str(args.output),
            "complete": report["complete"],
            "newAnswerCount": report["newAnswerCount"],
            "newAnswers": report["newAnswers"],
            "solverTelemetry": telemetry,
            "corpusFilter": expansion_stats,
        }, ensure_ascii=False, indent=2))
        return

    if args.maximize_coverage:
        solution, dropped, telemetry = solve_maximum_coverage_cp_sat(
            slots, words_by_length, args.maximum_coverage_seconds
        )
        gap_patterns = imposed_patterns(slots, solution, dropped, cell_links)
        report = {
            "version": 1,
            "kind": "fixed-shape-maximum-reviewed-corpus-coverage",
            "shapeId": shape["id"],
            "shapeModified": False,
            "centralEligibleAnswers": len(canonical),
            "slotCount": len(slots),
            "filledSlotCount": len(solution),
            "droppedSlotCount": len(dropped),
            "droppedSlots": gap_patterns,
            "solverTelemetry": telemetry,
            "filledAnswers": [
                {
                    "slotIndex": index,
                    "slotId": slots[index].slot_id,
                    "answer": solution[index],
                    "clue": canonical[solution[index]]["clue"],
                }
                for index in sorted(solution)
            ],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    levels = []
    first_satisfiable_level = None

    for drop_count in range(args.min_dropped, args.max_dropped + 1):
        level = {
            "droppedSlotCount": drop_count,
            "combinationsTested": 0,
            "solutions": [],
            "nodeTotal": 0,
        }
        for dropped in itertools.combinations(range(len(slots)), drop_count):
            level["combinationsTested"] += 1
            if args.method == "cp-sat":
                solution, telemetry = solve_subset_cp_sat(
                    slots,
                    words_by_length,
                    set(dropped),
                    args.seconds_per_combination,
                )
                level["nodeTotal"] += telemetry.get("branches", 0)
            else:
                solution, telemetry = solve_subset(
                    slots,
                    words_by_length,
                    neighbors,
                    set(dropped),
                    args.node_limit,
                )
                level["nodeTotal"] += telemetry["nodes"]
            if solution is None:
                continue
            record = {
                "droppedSlots": imposed_patterns(
                    slots, solution, dropped, cell_links
                ),
                "filledAnswers": [
                    {
                        "slotIndex": index,
                        "slotId": slots[index].slot_id,
                        "answer": solution[index],
                        "clue": canonical[solution[index]]["clue"],
                    }
                    for index in sorted(solution)
                ],
                "solverTelemetry": telemetry,
            }
            level["solutions"].append(record)
            if len(level["solutions"]) >= args.solutions_per_level:
                break
        levels.append(level)
        if level["solutions"]:
            first_satisfiable_level = drop_count
            break

    pattern_counts = Counter(
        item["pattern"]
        for level in levels
        for solution in level["solutions"]
        for item in solution["droppedSlots"]
    )
    report = {
        "version": 1,
        "kind": "fixed-shape-targeted-corpus-gap-diagnostic",
        "shapeId": shape["id"],
        "shapeFile": str(args.shape_file.relative_to(ROOT)).replace("\\", "/"),
        "shapeModified": False,
        "centralEligibleAnswers": len(canonical),
        "slotCount": len(slots),
        "firstSatisfiableDroppedSlotCount": first_satisfiable_level,
        "patternCounts": [
            {"pattern": pattern, "count": count}
            for pattern, count in pattern_counts.most_common()
        ],
        "levels": levels,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "output": str(args.output),
        "firstSatisfiableDroppedSlotCount": first_satisfiable_level,
        "levels": [
            {
                "droppedSlotCount": level["droppedSlotCount"],
                "tested": level["combinationsTested"],
                "solutions": len(level["solutions"]),
                "nodes": level["nodeTotal"],
            }
            for level in levels
        ],
        "topPatterns": report["patternCounts"][:20],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
