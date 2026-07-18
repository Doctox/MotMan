"""Dynamically build one reference-style 9x10 arrowword, words first.

Rows are selected from the central corpus while vertical prefixes are still
live.  An internal clue cell is inserted only when it closes a complete
vertical answer.  Consequently the topology is a result of the selected
answers, not a mask imposed before fill.

This script writes review staging only.  It never edits the runtime catalog,
blacklist, or assets.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import random
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as generator  # noqa: E402
from grid_topology import audit_grid_topology  # noqa: E402


ROWS = 10
COLUMNS = 9
CENTRAL = ROOT / "src/data/crossword.central.json.gz"
CATALOG = ROOT / "src/data/grid.catalog.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
OUTPUT = ROOT / "output/quality/reference-style-filled-a.json"

# All row patterns start with a letter in column 1, so the left-border clue
# always launches an across answer.  Internal breaks preserve 3+ horizontal
# answers.  The right-edge variants can only occur before the last row because
# their clue must launch a down answer.
PATTERNS = (
    {"id": "band-8", "clues": (), "segments": ((1, 8),), "singletons": ()},
    {"id": "split-2-5", "clues": (3,), "segments": ((1, 2), (4, 8)), "singletons": ()},
    {"id": "split-3-4", "clues": (4,), "segments": ((1, 3), (5, 8)), "singletons": ()},
    {"id": "split-4-3", "clues": (5,), "segments": ((1, 4), (6, 8)), "singletons": ()},
    {"id": "split-5-2", "clues": (6,), "segments": ((1, 5), (7, 8)), "singletons": ()},
    {"id": "band-7-edge", "clues": (8,), "segments": ((1, 7),), "singletons": ()},
    {"id": "band-6-tail-single", "clues": (7,), "segments": ((1, 6),), "singletons": (8,)},
    {"id": "band-5-mid-single", "clues": (6, 8), "segments": ((1, 5),), "singletons": (7,)},
    {"id": "band-4-two-singles", "clues": (5, 7), "segments": ((1, 4),), "singletons": (6, 8)},
    {"id": "adjacent-2-4", "clues": (3, 4), "segments": ((1, 2), (5, 8)), "singletons": ()},
    {"id": "split-2-single-3", "clues": (3, 5), "segments": ((1, 2), (6, 8)), "singletons": (4,)},
    {"id": "split-2-2-2", "clues": (3, 6), "segments": ((1, 2), (4, 5), (7, 8)), "singletons": ()},
    {"id": "split-2-3-single", "clues": (3, 7), "segments": ((1, 2), (4, 6)), "singletons": (8,)},
    {"id": "split-2-4-edge", "clues": (3, 8), "segments": ((1, 2), (4, 7)), "singletons": ()},
    {"id": "adjacent-3-3", "clues": (4, 5), "segments": ((1, 3), (6, 8)), "singletons": ()},
    {"id": "split-3-single-2", "clues": (4, 6), "segments": ((1, 3), (7, 8)), "singletons": (5,)},
    {"id": "split-3-2-single", "clues": (4, 7), "segments": ((1, 3), (5, 6)), "singletons": (8,)},
    {"id": "split-3-3-edge", "clues": (4, 8), "segments": ((1, 3), (5, 7)), "singletons": ()},
    {"id": "adjacent-4-2", "clues": (5, 6), "segments": ((1, 4), (7, 8)), "singletons": ()},
    {"id": "split-4-2-edge", "clues": (5, 8), "segments": ((1, 4), (6, 7)), "singletons": ()},
    {"id": "adjacent-5-single", "clues": (6, 7), "segments": ((1, 5),), "singletons": (8,)},
    {"id": "adjacent-band-6", "clues": (7, 8), "segments": ((1, 6),), "singletons": ()},
    {"id": "hinge-even-3", "clues": (4, 6, 8), "segments": ((1, 3),), "singletons": (5, 7)},
    {"id": "hinge-odd-3", "clues": (3, 5, 7), "segments": ((1, 2),), "singletons": (4, 6, 8)},
    {"id": "hinge-mid-3", "clues": (4, 5, 7), "segments": ((1, 3),), "singletons": (6, 8)},
    {"id": "hinge-mixed-4", "clues": (3, 4, 6, 8), "segments": ((1, 2),), "singletons": (5, 7)},
)

# Populated after the first deterministic solution has been inspected.  A
# missing answer remains explicitly pending and prevents a publishable status.
PAIR_REVIEWS: dict[str, dict] = {}


def normalize(value: str) -> str:
    folded = "".join(
        char
        for char in unicodedata.normalize("NFD", value.upper())
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"[^A-Z]", "", folded)


def answer_family(answer: str) -> str:
    """Conservative repeat family for plural and close inflection variants."""
    if len(answer) >= 5 and answer.endswith("ES"):
        return answer[:-2]
    if len(answer) >= 4 and answer.endswith(("S", "X")):
        return answer[:-1]
    return answer


@dataclass(frozen=True)
class AnswerMeta:
    answer: str
    length: int
    generator_eligible: bool
    frequency: float
    concept_group: str
    entry: dict
    image: dict | None


@dataclass(frozen=True)
class SearchState:
    prefixes: tuple[str, ...]
    rows: tuple[dict, ...]
    used_answers: frozenset[str]
    used_families: frozenset[str]
    active_families: frozenset[str]
    noneligible_answers: frozenset[str]
    image_eligible_answers: frozenset[str]
    score: float


def pair_rank(entry: dict) -> tuple:
    clue = entry.get("clue", "").strip()
    return (
        0 if entry.get("canonicalForGenerator") else 1,
        0 if entry.get("generatorEligible") else 1,
        0 if entry.get("editorialStatus") in {"human-reviewed", "owner-approved"} else 1,
        0 if entry.get("playableAsIs") else 1,
        0 if entry.get("corpusStage") == "production-legacy" else 1,
        abs(len(clue) - 12),
        len(clue),
        clue.casefold(),
    )


def load_answer_meta() -> tuple[dict[str, AnswerMeta], dict]:
    with gzip.open(CENTRAL, "rt", encoding="utf-8") as handle:
        central = json.load(handle)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in central["entries"]:
        answer = entry["answer"]
        if 2 <= len(answer) <= 9 and answer.isascii() and answer.isalpha():
            grouped[answer].append(entry)

    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    blocked = set(blacklist.get("rejectedAnswers", []))
    blocked.update(blacklist.get("rejectedEasyAnswers", []))
    blocked.update(blacklist.get("rejectedNormalAnswers", []))
    blocked.update(item["answer"] for item in blacklist.get("rotationCooldownAnswers", []))
    blocked.update(generator.FORBIDDEN_ANSWERS)

    meta = {}
    for answer, entries in grouped.items():
        if answer in blocked:
            continue
        canonical = next(
            (entry for entry in entries if entry.get("canonicalForGenerator")), None
        )
        selected = canonical or min(entries, key=pair_rank)
        image_entry = next((entry for entry in entries if entry.get("image")), None)
        image = image_entry.get("image") if image_entry else selected.get("image")
        meta[answer] = AnswerMeta(
            answer=answer,
            length=len(answer),
            generator_eligible=canonical is not None,
            frequency=max(float(entry.get("frequency", 0)) for entry in entries),
            concept_group=(canonical or selected).get("conceptGroup", answer),
            entry=selected,
            image=image,
        )
    return meta, central


class WordIndex:
    def __init__(self, meta: dict[str, AnswerMeta], *, eligible_only: bool):
        self.meta = {
            answer: item
            for answer, item in meta.items()
            if not eligible_only or item.generator_eligible
        }
        self.complete = set(self.meta)
        self.next_letters: dict[str, set[str]] = defaultdict(set)
        self.prefix_support = Counter()
        self.words_by_length: dict[int, list[str]] = defaultdict(list)
        for answer in sorted(self.meta):
            self.words_by_length[len(answer)].append(answer)
            for size in range(len(answer)):
                prefix = answer[:size]
                self.next_letters[prefix].add(answer[size])
                self.prefix_support[prefix] += 1

        self.position_masks = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        self.all_masks = {}
        for length, words in self.words_by_length.items():
            self.all_masks[length] = (1 << len(words)) - 1
            for index, answer in enumerate(words):
                bit = 1 << index
                for position, letter in enumerate(answer):
                    self.position_masks[length][position][letter] |= bit

    def has_extension(self, prefix: str) -> bool:
        return bool(self.next_letters.get(prefix))

    def candidates(
        self,
        columns: tuple[int, ...],
        prefixes: tuple[str, ...],
        *,
        final_row: bool,
        used_families: frozenset[str],
        active_families: set[str],
        allow_active: int,
        current_active: frozenset[str],
        image_position: bool,
        images_needed: int,
        seed: int,
        limit: int,
    ) -> list[str]:
        length = len(columns)
        domain = self.all_masks.get(length, 0)
        if not domain:
            return []
        for position, column in enumerate(columns):
            prefix = prefixes[column - 1]
            allowed = (
                {
                    letter
                    for letter in self.next_letters.get(prefix, set())
                    if prefix + letter in self.complete
                }
                if final_row
                else self.next_letters.get(prefix, set())
            )
            allowed_mask = 0
            for letter in allowed:
                allowed_mask |= self.position_masks[length][position].get(letter, 0)
            domain &= allowed_mask
            if not domain:
                return []

        values = []
        while domain:
            least = domain & -domain
            index = least.bit_length() - 1
            domain ^= least
            answer = self.words_by_length[length][index]
            family = answer_family(answer)
            if family in used_families:
                continue
            if family in active_families and (
                family not in current_active and len(current_active) >= allow_active
            ):
                continue
            item = self.meta[answer]
            support = 0.0
            closure_hits = 0
            possible = True
            for position, column in enumerate(columns):
                new_prefix = prefixes[column - 1] + answer[position]
                if final_row:
                    if new_prefix not in self.complete:
                        possible = False
                        break
                elif not self.has_extension(new_prefix):
                    possible = False
                    break
                support += math.log1p(self.prefix_support[new_prefix])
                if len(new_prefix) >= 3 and new_prefix in self.complete:
                    closure_hits += 1
            if not possible:
                continue
            # Keep lookahead and actual expansion on exactly the same candidate
            # order.  The outer search seed still controls stage selection;
            # lexical ties are content-stable for reproducibility.
            stable_tie = hashlib.sha256(answer.encode()).hexdigest()
            values.append(
                (
                    0 if images_needed > 0 and image_position and item.image else 1,
                    0 if item.generator_eligible else 1,
                    1 if family in active_families else 0,
                    -closure_hits,
                    -support,
                    -item.frequency,
                    stable_tie,
                    answer,
                )
            )
        values.sort()
        return [value[-1] for value in values[:limit]]


def active_families_from_catalog() -> tuple[set[str], Counter]:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    usage = Counter(
        answer_family(word["answer"])
        for grid in catalog["grids"]
        for word in grid["words"]
    )
    return set(usage), usage


def add_answer(
    answer: str,
    *,
    state_answers: set[str],
    state_families: set[str],
    state_active: set[str],
    state_noneligible: set[str],
    state_images: set[str],
    meta: dict[str, AnswerMeta],
    active_families: set[str],
    allow_active: int,
    image_eligible: bool,
) -> bool:
    family = answer_family(answer)
    if answer in state_answers or family in state_families:
        return False
    if family in active_families:
        state_active.add(family)
        if len(state_active) > allow_active:
            return False
    state_answers.add(answer)
    state_families.add(family)
    if not meta[answer].generator_eligible:
        state_noneligible.add(answer)
    if image_eligible and meta[answer].image:
        state_images.add(answer)
    return True


def state_after_row(
    state: SearchState,
    pattern: dict,
    segment_answers: tuple[str, ...],
    singleton_letters: tuple[str, ...],
    row: int,
    index: WordIndex,
    active_families: set[str],
    allow_active: int,
) -> SearchState | None:
    final_row = row == ROWS - 1
    answers = set(state.used_answers)
    families = set(state.used_families)
    active = set(state.active_families)
    noneligible = set(state.noneligible_answers)
    images = set(state.image_eligible_answers)

    # A clue inserted in this row closes the vertical word immediately above.
    for column in pattern["clues"]:
        closed = state.prefixes[column - 1]
        start_row = row - len(closed)
        image_eligible = start_row == 0 or column == 8
        if not add_answer(
            closed,
            state_answers=answers,
            state_families=families,
            state_active=active,
            state_noneligible=noneligible,
            state_images=images,
            meta=index.meta,
            active_families=active_families,
            allow_active=allow_active,
            image_eligible=image_eligible,
        ):
            return None

    row_cells = ["#"] * COLUMNS
    row_cells[0] = "#"
    for segment_number, ((start, end), answer) in enumerate(
        zip(pattern["segments"], segment_answers, strict=True)
    ):
        image_eligible = segment_number == 0 or final_row
        if not add_answer(
            answer,
            state_answers=answers,
            state_families=families,
            state_active=active,
            state_noneligible=noneligible,
            state_images=images,
            meta=index.meta,
            active_families=active_families,
            allow_active=allow_active,
            image_eligible=image_eligible,
        ):
            return None
        for offset, column in enumerate(range(start, end + 1)):
            row_cells[column] = answer[offset]
    for column, letter in zip(
        pattern.get("singletons", ()), singleton_letters, strict=True
    ):
        row_cells[column] = letter

    prefixes = list(state.prefixes)
    for column in range(1, COLUMNS):
        if column in pattern["clues"]:
            prefixes[column - 1] = ""
        else:
            prefixes[column - 1] += row_cells[column]
            if final_row:
                if prefixes[column - 1] not in index.complete:
                    return None
            elif not index.has_extension(prefixes[column - 1]):
                return None

    if final_row:
        for column, answer in enumerate(prefixes, 1):
            start_row = row + 1 - len(answer)
            image_eligible = start_row == 0 or column == 8
            if not add_answer(
                answer,
                state_answers=answers,
                state_families=families,
                state_active=active,
                state_noneligible=noneligible,
                state_images=images,
                meta=index.meta,
                active_families=active_families,
                allow_active=allow_active,
                image_eligible=image_eligible,
            ):
                return None

    prefix_support = sum(
        math.log1p(index.prefix_support[prefix])
        for prefix in prefixes
        if prefix and not final_row
    )
    long_answers = sum(
        5 <= len(answer) <= 8 for answer in answers
    )
    short_answers = sum(len(answer) <= 4 for answer in answers)
    closure_options = 0
    complete_prefixes = 0
    if not final_row:
        complete_prefixes = sum(
            len(prefix) >= 3 and prefix in index.complete for prefix in prefixes
        )
        closure_options = sum(
            all(
                len(prefixes[column - 1]) >= 3
                and prefixes[column - 1] in index.complete
                for column in pattern_option["clues"]
            )
            for pattern_option in PATTERNS
            if pattern_option["clues"]
        )
    score = (
        115 * min(len(images), 8)
        + 95 * closure_options
        + 18 * complete_prefixes
        + 18 * long_answers
        - 12 * short_answers
        - 120 * len(noneligible)
        - 70 * len(active)
        + 4 * prefix_support
        + sum(min(index.meta[answer].frequency, 8) for answer in answers)
    )
    row_record = {
        "row": row,
        "pattern": pattern["id"],
        "clueColumns": list(pattern["clues"]),
        "answers": list(segment_answers),
        "singletonLetters": {
            str(column): letter
            for column, letter in zip(
                pattern.get("singletons", ()), singleton_letters, strict=True
            )
        },
        "cells": "".join(row_cells),
    }
    return SearchState(
        prefixes=tuple(prefixes),
        rows=state.rows + (row_record,),
        used_answers=frozenset(answers),
        used_families=frozenset(families),
        active_families=frozenset(active),
        noneligible_answers=frozenset(noneligible),
        image_eligible_answers=frozenset(images),
        score=score,
    )


def can_open_next_row(
    state: SearchState,
    row: int,
    index: WordIndex,
    active_families: set[str],
    allow_active: int,
    seed: int,
    depth: int = 1,
) -> SearchState | None:
    """Cheap one-row lexical lookahead used before beam truncation."""
    final_row = row == ROWS - 1
    for pattern_number, pattern in enumerate(PATTERNS):
        if final_row:
            segment_starts = {start for start, _end in pattern["segments"]}
            if any(
                column + 1 not in segment_starts for column in pattern["clues"]
            ):
                continue
        if any(
            len(state.prefixes[column - 1]) < 3
            or state.prefixes[column - 1] not in index.complete
            for column in pattern["clues"]
        ):
            continue
        closed = [state.prefixes[column - 1] for column in pattern["clues"]]
        closed_families = {answer_family(answer) for answer in closed}
        if len(closed_families) != len(closed) or closed_families & state.used_families:
            continue
        projected_active = set(state.active_families)
        projected_active.update(closed_families & active_families)
        if len(projected_active) > allow_active:
            continue
        segment_domains = []
        for segment_number, (start, end) in enumerate(pattern["segments"]):
            candidates = index.candidates(
                tuple(range(start, end + 1)),
                state.prefixes,
                final_row=final_row,
                used_families=(
                    state.used_families
                    | frozenset(closed_families)
                ),
                active_families=active_families,
                allow_active=allow_active,
                current_active=frozenset(projected_active),
                image_position=segment_number == 0 or final_row,
                images_needed=max(0, 6 - len(state.image_eligible_answers)),
                seed=seed + row * 1000 + pattern_number * 10 + segment_number,
                limit=12 if depth > 1 else 4,
            )
            if not candidates:
                break
            segment_domains.append(candidates)
        if len(segment_domains) != len(pattern["segments"]):
            continue
        answer_combinations = [()]
        for candidates in segment_domains:
            answer_combinations = [
                previous + (answer,)
                for previous in answer_combinations
                for answer in candidates
                if answer_family(answer) not in {
                    answer_family(value) for value in previous
                }
            ][:64 if depth > 1 else 16]
        singleton_combinations = [()]
        for singleton_number, column in enumerate(pattern.get("singletons", ())):
            prefix = state.prefixes[column - 1]
            letters = sorted(
                index.next_letters.get(prefix, set()),
                key=lambda letter: (
                    0 if prefix + letter in index.complete else 1,
                    -index.prefix_support[prefix + letter],
                    letter,
                ),
            )[:8 if depth > 1 else 4]
            if not letters:
                singleton_combinations = []
                break
            singleton_combinations = [
                previous + (letter,)
                for previous in singleton_combinations
                for letter in letters
            ][:64 if depth > 1 else 16]
        for answers in answer_combinations:
            for singleton_letters in singleton_combinations:
                preview = state_after_row(
                    state,
                    pattern,
                    answers,
                    singleton_letters,
                    row,
                    index,
                    active_families,
                    allow_active,
                )
                if preview is None:
                    continue
                if depth > 1 and row < ROWS - 1:
                    if can_open_next_row(
                        preview,
                        row + 1,
                        index,
                        active_families,
                        allow_active,
                        seed + 97,
                        depth - 1,
                    ) is None:
                        continue
                return preview
    return None


def search(
    index: WordIndex,
    active_families: set[str],
    *,
    seed: int,
    allow_active: int,
    seconds: float,
    beam_width: int,
    telemetry: dict,
) -> SearchState | None:
    started = time.monotonic()
    deadline = started + seconds
    beam = [
        SearchState(
            prefixes=("",) * 8,
            rows=(),
            used_answers=frozenset(),
            used_families=frozenset(),
            active_families=frozenset(),
            noneligible_answers=frozenset(),
            image_eligible_answers=frozenset(),
            score=0,
        )
    ]
    expanded = generated = zero_patterns = 0
    row_reports = []
    for row in range(1, ROWS):
        next_states = []
        pattern_counts = Counter()
        for state_number, state in enumerate(beam):
            if time.monotonic() >= deadline:
                break
            expanded += 1
            for pattern in PATTERNS:
                if row == 1 and pattern["clues"]:
                    continue
                segment_starts = {start for start, _end in pattern["segments"]}
                clues_requiring_down = {
                    column
                    for column in pattern["clues"]
                    if column + 1 not in segment_starts
                }
                if row == ROWS - 1 and clues_requiring_down:
                    continue
                if any(
                    len(state.prefixes[column - 1]) < 3
                    or state.prefixes[column - 1] not in index.complete
                    for column in pattern["clues"]
                ):
                    continue

                closed_families = {
                    answer_family(state.prefixes[column - 1])
                    for column in pattern["clues"]
                }
                if (
                    len(closed_families) != len(pattern["clues"])
                    or closed_families & state.used_families
                ):
                    continue
                projected_active = set(state.active_families)
                projected_active.update(closed_families & active_families)
                if len(projected_active) > allow_active:
                    continue

                segment_domains = []
                domain_failed = False
                for segment_number, (start, end) in enumerate(pattern["segments"]):
                    columns = tuple(range(start, end + 1))
                    image_position = segment_number == 0 or row == ROWS - 1
                    limit = (
                        1000
                        if row == 1 and len(pattern["segments"]) == 1
                        else (70 if len(pattern["segments"]) == 1 else 18)
                    )
                    candidates = index.candidates(
                        columns,
                        state.prefixes,
                        final_row=row == ROWS - 1,
                        used_families=state.used_families | frozenset(closed_families),
                        active_families=active_families,
                        allow_active=allow_active,
                        current_active=frozenset(projected_active),
                        image_position=image_position,
                        images_needed=max(0, 6 - len(state.image_eligible_answers)),
                        seed=seed + row * 100_000 + state_number * 100 + segment_number,
                        limit=limit,
                    )
                    if not candidates:
                        domain_failed = True
                        break
                    segment_domains.append(candidates)
                if domain_failed:
                    zero_patterns += 1
                    continue

                singleton_domains = []
                for singleton_number, column in enumerate(pattern.get("singletons", ())):
                    prefix = state.prefixes[column - 1]
                    allowed = [
                        letter
                        for letter in index.next_letters.get(prefix, set())
                        if (
                            row != ROWS - 1
                            or prefix + letter in index.complete
                        )
                    ]
                    allowed.sort(
                        key=lambda letter: (
                            0 if prefix + letter in index.complete else 1,
                            -index.prefix_support[prefix + letter],
                            letter,
                        )
                    )
                    if not allowed:
                        domain_failed = True
                        break
                    singleton_domains.append(allowed[:8])
                if domain_failed:
                    zero_patterns += 1
                    continue

                combinations = [()]
                for candidates in segment_domains:
                    combinations = [
                        previous + (answer,)
                        for previous in combinations
                        for answer in candidates
                        if answer_family(answer) not in {
                            answer_family(value) for value in previous
                        }
                    ]
                    combination_cap = (
                        1000 if row == 1 and len(pattern["segments"]) == 1 else 180
                    )
                    combinations = combinations[:combination_cap]
                singleton_combinations = [()]
                for letters in singleton_domains:
                    singleton_combinations = [
                        previous + (letter,)
                        for previous in singleton_combinations
                        for letter in letters
                    ][:64]
                for combination in combinations:
                    for singleton_letters in singleton_combinations:
                        generated += 1
                        candidate = state_after_row(
                            state,
                            pattern,
                            combination,
                            singleton_letters,
                            row,
                            index,
                            active_families,
                            allow_active,
                        )
                        if candidate is not None:
                            next_states.append(candidate)
                            pattern_counts[pattern["id"]] += 1

        if not next_states:
            telemetry.update(
                reason="timeout" if time.monotonic() >= deadline else "beam-exhausted",
                failedRow=row,
                elapsedSeconds=round(time.monotonic() - started, 3),
                expanded=expanded,
                generated=generated,
                zeroPatternDomains=zero_patterns,
                rows=row_reports,
            )
            return None
        lookahead_before = len(next_states)
        lookahead_witness = None
        if 5 <= row < ROWS - 1:
            lookahead_states = []
            for candidate_number, candidate in enumerate(next_states):
                preview = can_open_next_row(
                    candidate,
                    row + 1,
                    index,
                    active_families,
                    allow_active,
                    seed + candidate_number,
                    (ROWS - 1 - row) if row >= 6 else 1,
                )
                if preview is not None:
                    lookahead_states.append(candidate)
                    if lookahead_witness is None:
                        lookahead_witness = preview.rows[-1]
            if lookahead_states:
                next_states = lookahead_states
        next_states.sort(
            key=lambda state: (
                len(state.image_eligible_answers) >= 6,
                state.score,
                -len(state.noneligible_answers),
                -len(state.active_families),
            ),
            reverse=True,
        )
        # Keep different topology histories and prefix frontiers in the beam.
        deduplicated = {}
        for state in next_states:
            key = (
                state.prefixes,
                tuple(row["pattern"] for row in state.rows),
                len(state.image_eligible_answers),
                len(state.active_families),
            )
            deduplicated.setdefault(key, state)
            if len(deduplicated) >= beam_width:
                break
        beam = list(deduplicated.values())
        row_reports.append(
            {
                "row": row,
                "statesKept": len(beam),
                "statesGenerated": len(next_states),
                "statesBeforeLookahead": lookahead_before,
                "lookaheadWitness": lookahead_witness,
                "patterns": dict(pattern_counts),
                "bestImages": max(len(state.image_eligible_answers) for state in beam),
                "bestNoneligible": min(len(state.noneligible_answers) for state in beam),
            }
        )
        if row == ROWS - 1:
            final = [
                state
                for state in beam
                if len(state.image_eligible_answers) >= 6
                and sum(5 <= len(answer) <= 8 for answer in state.used_answers)
                > sum(len(answer) <= 4 for answer in state.used_answers)
                and len(state.active_families) <= allow_active
            ]
            if final:
                final.sort(
                    key=lambda state: (
                        len(state.noneligible_answers),
                        len(state.active_families),
                        -len(state.image_eligible_answers),
                        -state.score,
                    )
                )
                result = final[0]
                telemetry.update(
                    reason="solved",
                    elapsedSeconds=round(time.monotonic() - started, 3),
                    expanded=expanded,
                    generated=generated,
                    zeroPatternDomains=zero_patterns,
                    rows=row_reports,
                )
                return result
    telemetry.update(reason="no-final-state", rows=row_reports)
    return None


def derive_grid(state: SearchState, meta: dict[str, AnswerMeta]) -> tuple[dict, list[dict]]:
    clues = {(0, column) for column in range(COLUMNS)}
    clues.update((row, 0) for row in range(1, ROWS))
    letters = {}
    for record in state.rows:
        row = record["row"]
        clues.update((row, column) for column in record["clueColumns"])
        for column, value in enumerate(record["cells"]):
            if column and value != "#":
                letters[row, column] = value

    slots = []
    for clue in sorted(clues - {(0, 0)}):
        for direction, arrow, (dr, dc) in (
            ("across", "right", (0, 1)),
            ("down", "down", (1, 0)),
        ):
            cells = []
            row, column = clue[0] + dr, clue[1] + dc
            while (
                0 <= row < ROWS
                and 0 <= column < COLUMNS
                and (row, column) not in clues
            ):
                cells.append([row, column])
                row += dr
                column += dc
            if len(cells) < 2:
                continue
            answer = "".join(letters[tuple(cell)] for cell in cells)
            if answer not in meta:
                raise ValueError(f"derived answer absent from central corpus: {answer}")
            slots.append(
                {
                    "slotId": f"slot-{len(slots) + 1:02d}",
                    "answer": answer,
                    "direction": direction,
                    "arrow": arrow,
                    "clueCell": list(clue),
                    "cells": cells,
                    "length": len(cells),
                }
            )
    launches = Counter(tuple(slot["clueCell"]) for slot in slots)
    image_slots = [
        slot
        for slot in slots
        if launches[tuple(slot["clueCell"])] == 1 and meta[slot["answer"]].image
    ]
    image_slots.sort(
        key=lambda slot: (
            1 if answer_family(slot["answer"]) in active_families_from_catalog()[0] else 0,
            -slot["length"],
            slot["slotId"],
        )
    )
    selected_image_ids = {slot["slotId"] for slot in image_slots[:6]}
    words = []
    for number, slot in enumerate(slots, 1):
        item = meta[slot["answer"]]
        entry = item.entry
        review = PAIR_REVIEWS.get(slot["answer"], {})
        word = {
            "wordId": f"reference-style-filled-a-01:word:{number:02d}",
            "answer": slot["answer"],
            "clue": review.get("clue", entry.get("clue", "")),
            "sourceClue": entry.get("clue", ""),
            "sourceId": entry.get("sourceId"),
            "sourceUrl": entry.get("sourceUrl"),
            "sourceType": entry.get("sourceType"),
            "generatorEligible": item.generator_eligible,
            "editorialReview": review.get("status", "pending-manual-review"),
            "editorialReviewNote": review.get("note", "Couple à relire avant toute publication."),
            "conceptGroup": entry.get("conceptGroup", slot["answer"]),
            "semanticConflicts": entry.get("semanticConflicts", []),
            "direction": slot["direction"],
            "arrow": slot["arrow"],
            "clueCell": slot["clueCell"],
            "cells": slot["cells"],
        }
        if slot["slotId"] in selected_image_ids:
            word["image"] = {
                **item.image,
                "alt": item.image.get("alt", slot["answer"].title()),
            }
            word["clue"] = ""
            word["editorialReview"] = review.get("status", "image-association-reviewed")
        words.append(word)
    grid = {
        "id": "reference-style-filled-a-01",
        "columns": COLUMNS,
        "rows": ROWS,
        "clueCells": [list(cell) for cell in sorted(clues)],
        "words": words,
        "imageCount": len(selected_image_ids),
        "publicationStatus": "review-staging-not-published",
        "layoutProfile": "reference-ribbons-dynamic-words-first",
    }
    return grid, slots


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=731_500)
    parser.add_argument("--seconds", type=float, default=24)
    parser.add_argument("--beam", type=int, default=420)
    parser.add_argument(
        "--stage",
        choices=("all", "eligible-fresh", "eligible-up-to-3-active", "full-central-up-to-3-active"),
        default="all",
    )
    args = parser.parse_args()

    meta, central = load_answer_meta()
    active_families, active_usage = active_families_from_catalog()
    stages = (
        {"id": "eligible-fresh", "eligibleOnly": True, "active": 0},
        {"id": "eligible-up-to-3-active", "eligibleOnly": True, "active": 3},
        {"id": "full-central-up-to-3-active", "eligibleOnly": False, "active": 3},
    )
    if args.stage != "all":
        stages = tuple(stage for stage in stages if stage["id"] == args.stage)
    attempts = []
    solved = None
    solved_stage = None
    for stage_number, stage in enumerate(stages):
        index = WordIndex(meta, eligible_only=stage["eligibleOnly"])
        telemetry = {
            "stage": stage["id"],
            "answersIndexed": len(index.meta),
            "seed": args.seed + stage_number,
        }
        solved = search(
            index,
            active_families,
            seed=args.seed + stage_number,
            allow_active=stage["active"],
            seconds=args.seconds,
            beam_width=args.beam,
            telemetry=telemetry,
        )
        attempts.append(telemetry)
        if solved is not None:
            solved_stage = stage
            break

    if solved is None or solved_stage is None:
        document = {
            "version": 1,
            "kind": "reference-style-dynamic-fill-diagnostic",
            "status": "bounded-search-no-complete-grid",
            "attempts": attempts,
            "catalogModified": False,
            "blacklistModified": False,
            "grids": [],
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        raise SystemExit(2)

    grid, slots = derive_grid(solved, meta)
    topology = audit_grid_topology(grid, enforce_layout=False)
    lengths = Counter(slot["length"] for slot in slots)
    active_selected = sorted(
        family for family in solved.active_families
    )
    all_reviewed = all(
        word["editorialReview"] in {"human-reviewed-accepted", "image-association-reviewed"}
        for word in grid["words"]
    )
    noneligible_review = [
        {
            "answer": word["answer"],
            "clue": word["sourceClue"],
            "decision": word["editorialReview"],
            "note": word["editorialReviewNote"],
        }
        for word in grid["words"]
        if not word["generatorEligible"]
    ]
    document = {
        "version": 1,
        "kind": "reference-style-dynamic-words-first-grid",
        "status": "owner-review-ready" if all_reviewed else "manual-pair-review-required",
        "policy": {
            "method": "answers selected before clue-cell topology",
            "referenceStyle": "full top/left clue ribbons, long bands, sparse internal double clues",
            "columns": COLUMNS,
            "rows": ROWS,
            "minimumImages": 6,
            "maximumActiveFamilies": 3,
            "orphanSegmentsAllowed": 0,
            "catalogModified": False,
            "blacklistModified": False,
        },
        "corpus": {
            "centralDistinctAnswers": central["metrics"]["distinctAnswers"],
            "generatorEligibleDistinctAnswers": central["metrics"]["generatorEligibleDistinctAnswers"],
            "selectedStage": solved_stage["id"],
            "selectedNoneligibleAnswers": sorted(solved.noneligible_answers),
            "noneligiblePairReview": noneligible_review,
        },
        "attempts": attempts,
        "metrics": {
            "answers": len(grid["words"]),
            "images": grid["imageCount"],
            "lengthProfile": {str(length): count for length, count in sorted(lengths.items())},
            "shortAnswers2To4": sum(lengths[length] for length in range(2, 5)),
            "longAnswers5To8": sum(lengths[length] for length in range(5, 9)),
            "activeFamilies": active_selected,
            "activeFamilyUsesInCatalog": {
                family: active_usage[family] for family in active_selected
            },
            "internalClueCells": sum(
                row > 0 and column > 0 for row, column in map(tuple, grid["clueCells"])
            ),
            "doubleClueCells": sum(
                value == 2
                for value in Counter(tuple(word["clueCell"]) for word in grid["words"]).values()
            ),
            "topologyValid": topology["valid"],
            "topologyErrors": topology["errors"],
            "orphanSegments": topology["orphanSegments"],
            "allPairsManuallyReviewed": all_reviewed,
        },
        "constructionRows": list(solved.rows),
        "grid": grid,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "status": document["status"],
                "stage": solved_stage["id"],
                "answers": [word["answer"] for word in grid["words"]],
                "images": [word["answer"] for word in grid["words"] if word.get("image")],
                "lengthProfile": document["metrics"]["lengthProfile"],
                "activeFamilies": active_selected,
                "noneligible": sorted(solved.noneligible_answers),
                "topologyValid": topology["valid"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
