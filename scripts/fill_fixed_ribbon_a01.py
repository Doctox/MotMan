"""Fill the immutable ``reference-ribbon-a-01`` topology.

This is deliberately not a shape generator. It walks the fixed 9x10 grid
row by row while following one trie for every across and down answer. A
branch exists only when all partial strings can still become real corpus
answers. The solver never inserts a letter, changes a clue cell or shortens
an answer to repair a crossing.

The first pass is lexical: Morphalou and Lexique may prove that a complete
closure exists, but their entries are not publishable clues. The report
therefore separates answers which already have an owner-reviewed clue from
answers which still need a sourced editorial clue.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagnose_fixed_shape_corpus_gaps import (  # noqa: E402
    DEFAULT_SHAPES,
    crossing_arcs,
    load_expansion_words,
    load_shape,
    load_words,
)


DEFAULT_OUTPUT = ROOT / "output/quality/reference-ribbon-a01-fixed-fill.json"
OWNER_DECISIONS = (
    ROOT / "src/data/jeuxdemots.owner-decisions.json",
    ROOT / "src/data/jeuxdemots.owner-full-decisions.json",
)


@dataclass
class Trie:
    length: int
    children: list[dict[str, int]]
    terminal: list[str | None]

    @classmethod
    def build(cls, length: int, words: tuple[str, ...]) -> "Trie":
        children: list[dict[str, int]] = [{}]
        terminal: list[str | None] = [None]
        for word in words:
            if len(word) != length:
                raise ValueError(f"longueur incoherente: {word!r} pour {length}")
            node = 0
            for letter in word:
                target = children[node].get(letter)
                if target is None:
                    target = len(children)
                    children[node][letter] = target
                    children.append({})
                    terminal.append(None)
                node = target
            terminal[node] = word
        return cls(length=length, children=children, terminal=terminal)


@dataclass(frozen=True)
class Segment:
    slot_index: int
    columns: tuple[int, ...]


# Rows and columns below omit the outer clue ribbons. They therefore use
# logical letter columns 0..7 and board rows 1..9.
ROW_SEGMENTS: tuple[tuple[Segment, ...], ...] = (
    (Segment(8, tuple(range(8))),),
    (Segment(9, tuple(range(8))),),
    (Segment(10, tuple(range(8))),),
    (Segment(11, (0, 1, 2)), Segment(12, (4, 5, 6))),
    (Segment(15, (0, 1, 2, 3)), Segment(16, (5, 6, 7))),
    (Segment(18, tuple(range(8))),),
    (Segment(19, tuple(range(8))),),
    (Segment(20, tuple(range(8))),),
    (Segment(21, tuple(range(8))),),
)

# For each letter row and column: (down-answer length, zero-based position).
# ``None`` is a clue cell, never a letter.
VERTICAL_SPECS: tuple[tuple[tuple[int, int] | None, ...], ...] = (
    ((9, 0), (9, 0), (9, 0), (3, 0), (4, 0), (9, 0), (9, 0), (3, 0)),
    ((9, 1), (9, 1), (9, 1), (3, 1), (4, 1), (9, 1), (9, 1), (3, 1)),
    ((9, 2), (9, 2), (9, 2), (3, 2), (4, 2), (9, 2), (9, 2), (3, 2)),
    ((9, 3), (9, 3), (9, 3), None, (4, 3), (9, 3), (9, 3), None),
    ((9, 4), (9, 4), (9, 4), (5, 0), None, (9, 4), (9, 4), (5, 0)),
    ((9, 5), (9, 5), (9, 5), (5, 1), (4, 0), (9, 5), (9, 5), (5, 1)),
    ((9, 6), (9, 6), (9, 6), (5, 2), (4, 1), (9, 6), (9, 6), (5, 2)),
    ((9, 7), (9, 7), (9, 7), (5, 3), (4, 2), (9, 7), (9, 7), (5, 3)),
    ((9, 8), (9, 8), (9, 8), (5, 4), (4, 3), (9, 8), (9, 8), (5, 4)),
)


def load_owner_accepts() -> dict[str, list[dict]]:
    accepted: dict[str, list[dict]] = defaultdict(list)
    for path in OWNER_DECISIONS:
        if not path.exists():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        for decision in document.get("decisions", []):
            if decision.get("decision") != "accept":
                continue
            answer = str(decision.get("answer", "")).upper().strip()
            clue = str(decision.get("clue", "")).strip()
            if answer and clue:
                accepted[answer].append({
                    "answer": answer,
                    "clue": clue,
                    "source": path.name,
                    "ownerDecisionId": decision.get("id"),
                })
    return dict(accepted)


def validate_fixed_layout(slots) -> None:
    expected = [
        (segment.slot_index, len(segment.columns))
        for row in ROW_SEGMENTS for segment in row
    ]
    actual = [(index, slots[index].length) for index, _length in expected]
    if actual != expected:
        raise ValueError("reference-ribbon-a-01 ne correspond plus au plan fige")
    letter_cells = {cell for slot in slots for cell in slot.cells}
    if len(letter_cells) != 69:
        raise ValueError(f"couverture figee attendue: 69, obtenue: {len(letter_cells)}")


class FixedRibbonSolver:
    def __init__(
        self,
        *,
        slots,
        words_by_length: dict[int, tuple[str, ...]],
        metadata: dict[str, dict],
        canonical: dict[str, dict],
        owner_accepts: dict[str, list[dict]],
        seed: int,
        seconds: float,
    ) -> None:
        self.slots = slots
        self.words_by_length = words_by_length
        self.metadata = metadata
        self.canonical = canonical
        self.owner_accepts = owner_accepts
        self.rng = random.Random(seed)
        self.seed = seed
        self.started = time.monotonic()
        self.deadline = self.started + seconds
        self.tries = {
            length: Trie.build(length, words)
            for length, words in words_by_length.items()
            if length in {3, 4, 5, 8, 9}
        }
        self.word_priority = {}
        for words in words_by_length.values():
            for word in words:
                entry = metadata[word]
                frequency = float(entry.get("sourceFrequency", 0) or 0)
                school = float(entry.get("schoolFrequency", 0) or 0)
                reviewed_bonus = 0.18 if (
                    word in canonical or word in owner_accepts
                ) else 0
                central_bonus = 0.07 if word in canonical else 0
                frequency_bonus = min(0.10, (frequency + school / 1000) / 120)
                self.word_priority[word] = (
                    self.rng.random()
                    - reviewed_bonus
                    - central_bonus
                    - frequency_bonus
                )
        self.nodes = 0
        self.rows_reached = Counter()
        self.dead_states: set[tuple] = set()
        self.best_depth = 0
        self.best_partial: dict[int, str] = {}
        self.last_progress = self.started
        self.timed_out = False

    def quality_key(self, word: str) -> tuple:
        return (self.word_priority[word], word)

    def segment_candidates(
        self,
        row_index: int,
        segment: Segment,
        vertical_nodes: tuple[int | None, ...],
    ) -> list[tuple[str, tuple[int | None, ...]]]:
        slot = self.slots[segment.slot_index]
        across = self.tries[slot.length]
        candidates: list[tuple[str, tuple[int | None, ...]]] = []
        next_vertical = list(vertical_nodes)

        def visit(position: int, across_node: int) -> None:
            if position == len(segment.columns):
                word = across.terminal[across_node]
                if word is not None:
                    candidates.append((word, tuple(next_vertical)))
                return
            column = segment.columns[position]
            spec = VERTICAL_SPECS[row_index][column]
            if spec is None:
                raise ValueError("segment place sur une case-definition")
            down_length, down_position = spec
            down = self.tries[down_length]
            down_node = 0 if down_position == 0 else vertical_nodes[column]
            if down_node is None:
                return
            across_children = across.children[across_node]
            down_children = down.children[down_node]
            for letter, across_target in across_children.items():
                down_target = down_children.get(letter)
                if down_target is None:
                    continue
                if down_position == down_length - 1 and down.terminal[down_target] is None:
                    continue
                previous = next_vertical[column]
                next_vertical[column] = down_target
                visit(position + 1, across_target)
                next_vertical[column] = previous

        visit(0, 0)
        candidates.sort(key=lambda item: self.quality_key(item[0]))
        return candidates

    @staticmethod
    def state_key(
        row_index: int,
        segment_index: int,
        vertical_nodes: tuple[int | None, ...],
    ) -> tuple:
        return (row_index, segment_index, vertical_nodes)

    def search(
        self,
        row_index: int,
        segment_index: int,
        vertical_nodes: tuple[int | None, ...],
        chosen: dict[int, str],
    ) -> dict[int, str] | None:
        now = time.monotonic()
        if now >= self.deadline:
            self.timed_out = True
            return None
        self.nodes += 1
        self.rows_reached[row_index] += 1
        if len(chosen) > self.best_depth:
            self.best_depth = len(chosen)
            self.best_partial = dict(chosen)
        if now - self.last_progress >= 10:
            print(json.dumps({
                "event": "progress",
                "elapsedSeconds": round(now - self.started, 1),
                "nodes": self.nodes,
                "filledSlots": self.best_depth,
                "row": row_index + 1,
                "deadStates": len(self.dead_states),
            }), flush=True)
            self.last_progress = now
        if row_index == len(ROW_SEGMENTS):
            if len(set(chosen.values())) != len(chosen):
                return None
            return dict(chosen)

        state = self.state_key(row_index, segment_index, vertical_nodes)
        if state in self.dead_states:
            return None
        segments = ROW_SEGMENTS[row_index]
        segment = segments[segment_index]
        for word, next_vertical in self.segment_candidates(
            row_index, segment, vertical_nodes
        ):
            if word in chosen.values():
                continue
            chosen[segment.slot_index] = word
            if segment_index + 1 < len(segments):
                solved = self.search(
                    row_index, segment_index + 1, next_vertical, chosen
                )
            else:
                solved = self.search(row_index + 1, 0, next_vertical, chosen)
            if solved is not None:
                return solved
            chosen.pop(segment.slot_index, None)
            if self.timed_out:
                return None
        self.dead_states.add(state)
        return None

    def solve(self) -> tuple[dict[int, str] | None, dict]:
        solution = self.search(0, 0, (None,) * 8, {})
        return solution, {
            "solver": "fixed-ribbon-row-trie",
            "seed": self.seed,
            "elapsedSeconds": round(time.monotonic() - self.started, 3),
            "reason": "solved" if solution is not None else (
                "timeout" if self.timed_out else "exhausted"
            ),
            "nodes": self.nodes,
            "deadStates": len(self.dead_states),
            "bestFilledAcrossSlots": self.best_depth,
            "rowsReached": dict(sorted(self.rows_reached.items())),
            "bestPartial": [
                {
                    "slotIndex": index,
                    "slotId": self.slots[index].slot_id,
                    "answer": answer,
                }
                for index, answer in sorted(self.best_partial.items())
            ],
        }


class FixedRibbonArcSolver:
    """AC-3/bitset search dedicated to the 22 immutable A01 slots.

    Unlike the row solver, this propagates a letter chosen near the bottom to
    every compatible answer near the top immediately.  It is still exact:
    every bit in a domain is one complete corpus answer.
    """

    def __init__(
        self,
        *,
        slots,
        words_by_length: dict[int, tuple[str, ...]],
        metadata: dict[str, dict],
        canonical: dict[str, dict],
        owner_accepts: dict[str, list[dict]],
        seed: int,
        seconds: float,
        strategy: str = "information",
        preferred_answers: dict[int, str] | None = None,
    ) -> None:
        self.slots = slots
        self.words_by_length = words_by_length
        self.metadata = metadata
        self.canonical = canonical
        self.owner_accepts = owner_accepts
        self.seed = seed
        self.strategy = strategy
        # Search-order hint only: unlike fixed_answers this never removes a
        # candidate from any domain, so the search remains exact.
        self.preferred_answers = preferred_answers or {}
        self.started = time.monotonic()
        self.deadline = self.started + seconds
        self.rng = random.Random(seed)
        self.word_indexes = {
            length: {word: index for index, word in enumerate(words)}
            for length, words in words_by_length.items()
        }
        self.letter_masks: dict[int, list[list[int]]] = {}
        for length, words in words_by_length.items():
            if length not in {3, 4, 5, 8, 9}:
                continue
            masks = [[0] * 26 for _ in range(length)]
            for index, word in enumerate(words):
                bit = 1 << index
                for position, letter in enumerate(word):
                    masks[position][ord(letter) - 65] |= bit
            self.letter_masks[length] = masks
        _links, self.neighbors = crossing_arcs(slots)
        self.arcs = [
            (left, right, left_position, right_position)
            for left in range(len(slots))
            for right, left_position, right_position in self.neighbors[left]
        ]
        self.priority: dict[str, float] = {}
        for words in words_by_length.values():
            for word in words:
                entry = metadata[word]
                frequency = float(entry.get("sourceFrequency", 0) or 0)
                school = float(entry.get("schoolFrequency", 0) or 0)
                reviewed_bonus = 0.18 if (
                    word in canonical or word in owner_accepts
                ) else 0
                central_bonus = 0.07 if word in canonical else 0
                frequency_bonus = min(0.12, (frequency + school / 1000) / 100)
                self.priority[word] = (
                    self.rng.random()
                    - reviewed_bonus
                    - central_bonus
                    - frequency_bonus
                )
        self.support_cache: dict[tuple[int, int, int], int] = {}
        self.allowed_cache: dict[tuple[int, int, int], int] = {}
        self.dead_states: set[tuple[int, ...]] = set()
        self.nodes = 0
        self.arc_revisions = 0
        self.wipeouts = 0
        self.best_progress = 0
        self.best_domains: tuple[int, ...] | None = None
        self.last_progress = self.started
        self.timed_out = False

    def support_letters(self, length: int, position: int, domain: int) -> int:
        key = (length, position, domain)
        cached = self.support_cache.get(key)
        if cached is not None:
            return cached
        support = 0
        for code, mask in enumerate(self.letter_masks[length][position]):
            if domain & mask:
                support |= 1 << code
        if len(self.support_cache) > 400_000:
            self.support_cache.clear()
        self.support_cache[key] = support
        return support

    def allowed_words(self, length: int, position: int, support: int) -> int:
        key = (length, position, support)
        cached = self.allowed_cache.get(key)
        if cached is not None:
            return cached
        allowed = 0
        bits = support
        while bits:
            least = bits & -bits
            code = least.bit_length() - 1
            allowed |= self.letter_masks[length][position][code]
            bits ^= least
        self.allowed_cache[key] = allowed
        return allowed

    def revise(
        self,
        domains: list[int],
        left: int,
        right: int,
        left_position: int,
        right_position: int,
    ) -> bool:
        right_slot = self.slots[right]
        left_slot = self.slots[left]
        support = self.support_letters(
            right_slot.length, right_position, domains[right]
        )
        revised = domains[left] & self.allowed_words(
            left_slot.length, left_position, support
        )
        if revised == domains[left]:
            return False
        domains[left] = revised
        self.arc_revisions += 1
        return True

    def propagate(
        self,
        domains: list[int],
        initial_arcs=None,
    ) -> tuple[int, ...] | None:
        queue = deque(self.arcs if initial_arcs is None else initial_arcs)
        while queue:
            if time.monotonic() >= self.deadline:
                self.timed_out = True
                return None
            left, right, left_position, right_position = queue.popleft()
            if not self.revise(
                domains, left, right, left_position, right_position
            ):
                continue
            if not domains[left]:
                self.wipeouts += 1
                return None
            for previous, left_position_again, previous_position in self.neighbors[left]:
                if previous == right:
                    continue
                queue.append((
                    previous,
                    left,
                    previous_position,
                    left_position_again,
                ))
        singleton_words = []
        for index, domain in enumerate(domains):
            if domain.bit_count() != 1:
                continue
            singleton_words.append(self.decode(index, domain))
        if len(singleton_words) != len(set(singleton_words)):
            return None
        progress = len(singleton_words)
        if progress > self.best_progress:
            self.best_progress = progress
            self.best_domains = tuple(domains)
        return tuple(domains)

    def decode(self, slot_index: int, domain: int) -> str:
        return self.words_by_length[self.slots[slot_index].length][
            domain.bit_length() - 1
        ]

    @staticmethod
    def bit_indexes(bits: int):
        while bits:
            least = bits & -bits
            yield least.bit_length() - 1
            bits ^= least

    def candidate_order(self, slot_index: int, domains: tuple[int, ...]) -> list[int]:
        slot = self.slots[slot_index]
        words = self.words_by_length[slot.length]
        existing_singletons = {
            self.decode(index, domain)
            for index, domain in enumerate(domains)
            if index != slot_index and domain.bit_count() == 1
        }
        candidates = [
            index for index in self.bit_indexes(domains[slot_index])
            if words[index] not in existing_singletons
        ]

        def key(word_index: int) -> tuple:
            word = words[word_index]
            support = 0
            for neighbor, own_position, neighbor_position in self.neighbors[slot_index]:
                neighbor_slot = self.slots[neighbor]
                code = ord(word[own_position]) - 65
                support += (
                    domains[neighbor]
                    & self.letter_masks[neighbor_slot.length][neighbor_position][code]
                ).bit_count()
            return (
                0 if self.preferred_answers.get(slot_index) == word else 1,
                -support,
                self.priority[word],
                word,
            )

        candidates.sort(key=key)
        return candidates

    def search(self, domains: tuple[int, ...]) -> dict[int, str] | None:
        now = time.monotonic()
        if now >= self.deadline:
            self.timed_out = True
            return None
        self.nodes += 1
        if now - self.last_progress >= 10:
            print(json.dumps({
                "event": "progress",
                "solver": "fixed-ribbon-ac3-bitset",
                "elapsedSeconds": round(now - self.started, 1),
                "nodes": self.nodes,
                "bestFilledSlots": self.best_progress,
                "deadStates": len(self.dead_states),
                "arcRevisions": self.arc_revisions,
            }), flush=True)
            self.last_progress = now
        if domains in self.dead_states:
            return None
        unresolved = [
            index for index, domain in enumerate(domains)
            if domain.bit_count() > 1
        ]
        if not unresolved:
            return {
                index: self.decode(index, domain)
                for index, domain in enumerate(domains)
            }
        if self.strategy == "mrv":
            index = min(
                unresolved,
                key=lambda item: (
                    domains[item].bit_count(),
                    -len(self.neighbors[item]),
                    item,
                ),
            )
        else:
            # Domain size alone over-selects 3-letter slots.  Normalising its
            # logarithm by the number of crossings estimates information per
            # affected answer and favours the 8/9-letter structural anchors.
            index = min(
                unresolved,
                key=lambda item: (
                    math.log2(domains[item].bit_count())
                    / max(1, len(self.neighbors[item])),
                    domains[item].bit_count(),
                    item,
                ),
            )
        for word_index in self.candidate_order(index, domains):
            next_domains = list(domains)
            next_domains[index] = 1 << word_index
            impacted = [
                (neighbor, index, neighbor_position, own_position)
                for neighbor, own_position, neighbor_position in self.neighbors[index]
            ]
            propagated = self.propagate(next_domains, impacted)
            if propagated is None:
                if self.timed_out:
                    return None
                continue
            solution = self.search(propagated)
            if solution is not None:
                return solution
            if self.timed_out:
                return None
        if len(self.dead_states) < 500_000:
            self.dead_states.add(domains)
        return None

    def solve(
        self,
        fixed_answers: dict[int, str] | None = None,
    ) -> tuple[dict[int, str] | None, dict]:
        initial = [
            (1 << len(self.words_by_length[slot.length])) - 1
            for slot in self.slots
        ]
        fixed_answers = fixed_answers or {}
        for slot_index, answer in fixed_answers.items():
            length = self.slots[slot_index].length
            word_index = self.word_indexes[length].get(answer)
            if word_index is None:
                raise ValueError(f"ancre absente du corpus: {answer}")
            initial[slot_index] = 1 << word_index
        propagated = self.propagate(initial)
        solution = None if propagated is None else self.search(propagated)
        telemetry = {
            "solver": "fixed-ribbon-ac3-bitset",
            "seed": self.seed,
            "strategy": self.strategy,
            "fixedAnchorCount": len(fixed_answers),
            "elapsedSeconds": round(time.monotonic() - self.started, 3),
            "reason": "solved" if solution is not None else (
                "timeout" if self.timed_out else "exhausted"
            ),
            "nodes": self.nodes,
            "deadStates": len(self.dead_states),
            "arcRevisions": self.arc_revisions,
            "domainWipeouts": self.wipeouts,
            "bestFilledSlots": self.best_progress,
        }
        if self.best_domains is not None:
            telemetry["bestSingletons"] = [
                {
                    "slotIndex": index,
                    "slotId": self.slots[index].slot_id,
                    "answer": self.decode(index, domain),
                }
                for index, domain in enumerate(self.best_domains)
                if domain.bit_count() == 1
            ]
        return solution, telemetry


class FixedRibbonMinConflictsSolver:
    """Rotate complete corpus words until every crossing agrees.

    This stochastic solver is useful after exact propagation has identified
    a very dense but difficult search space.  It never edits letters inside a
    word: every move replaces one entire answer with another corpus answer of
    exactly the same length.
    """

    def __init__(
        self,
        *,
        slots,
        words_by_length: dict[int, tuple[str, ...]],
        metadata: dict[str, dict],
        canonical: dict[str, dict],
        owner_accepts: dict[str, list[dict]],
        seed: int,
        seconds: float,
        breakout: bool = False,
    ) -> None:
        self.slots = slots
        self.words_by_length = words_by_length
        self.metadata = metadata
        self.canonical = canonical
        self.owner_accepts = owner_accepts
        self.seed = seed
        self.breakout = breakout
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.started = time.monotonic()
        self.deadline = self.started + seconds
        self.matrices = {
            length: np.asarray(
                [[ord(letter) - 65 for letter in word] for word in words],
                dtype=np.uint8,
            )
            for length, words in words_by_length.items()
            if length in {3, 4, 5, 8, 9}
        }
        self.word_indexes = {
            length: {word: index for index, word in enumerate(words)}
            for length, words in words_by_length.items()
        }
        _cell_links, neighbors = crossing_arcs(slots)
        self.neighbors = neighbors
        self.crossings = []
        self.edge_for_slot_position = {}
        for left in range(len(slots)):
            for right, left_position, right_position in neighbors[left]:
                if left < right:
                    edge_index = len(self.crossings)
                    self.crossings.append(
                        (left, left_position, right, right_position)
                    )
                    self.edge_for_slot_position[(left, left_position)] = edge_index
                    self.edge_for_slot_position[(right, right_position)] = edge_index
        self.quality = {}
        for length, words in words_by_length.items():
            values = np.empty(len(words), dtype=np.float64)
            for index, word in enumerate(words):
                entry = metadata[word]
                frequency = float(entry.get("sourceFrequency", 0) or 0)
                school = float(entry.get("schoolFrequency", 0) or 0)
                reviewed = word in canonical or word in owner_accepts
                values[index] = (
                    (0.16 if reviewed else 0)
                    + min(0.10, (frequency + school / 1000) / 120)
                    + self.rng.random() * 0.02
                )
            self.quality[length] = values
        self.steps = 0
        self.restarts = 0
        self.best_conflicts = len(self.crossings) + 1
        self.best_assignment: list[int] | None = None
        self.last_progress = self.started

    def word(self, slot_index: int, word_index: int) -> str:
        return self.words_by_length[self.slots[slot_index].length][word_index]

    def conflict_edges(
        self,
        assignment: list[int],
        weights: np.ndarray | None = None,
    ):
        conflicts = []
        counts = np.zeros(len(self.slots), dtype=np.float64)
        for edge_index, (left, left_position, right, right_position) in enumerate(
            self.crossings
        ):
            left_word = self.word(left, assignment[left])
            right_word = self.word(right, assignment[right])
            if left_word[left_position] == right_word[right_position]:
                continue
            conflicts.append((edge_index, left, right))
            weight = 1.0 if weights is None else float(weights[edge_index])
            counts[left] += weight
            counts[right] += weight
        return conflicts, counts

    def initial_assignment(self) -> list[int]:
        assignment = []
        used_by_length: dict[int, set[int]] = defaultdict(set)
        for slot in self.slots:
            size = len(self.words_by_length[slot.length])
            # Mix the whole reservoir on every restart; reviewed words receive
            # a tie-break advantage later but are never a closed sub-pool.
            while True:
                index = self.rng.randrange(size)
                if index not in used_by_length[slot.length]:
                    used_by_length[slot.length].add(index)
                    assignment.append(index)
                    break
        return assignment

    def desired_letters(self, slot_index: int, assignment: list[int]) -> np.ndarray:
        desired = np.empty(self.slots[slot_index].length, dtype=np.uint8)
        for neighbor, own_position, neighbor_position in self.neighbors[slot_index]:
            neighbor_word = self.word(neighbor, assignment[neighbor])
            desired[own_position] = ord(neighbor_word[neighbor_position]) - 65
        return desired

    def replacement(
        self,
        slot_index: int,
        assignment: list[int],
        *,
        noisy: bool,
        tabu: set[tuple[int, int]],
        weights: np.ndarray,
    ) -> tuple[int, float, float]:
        slot = self.slots[slot_index]
        matrix = self.matrices[slot.length]
        desired = self.desired_letters(slot_index, assignment)
        matches = np.zeros(len(matrix), dtype=np.float64)
        for position in range(slot.length):
            edge_index = self.edge_for_slot_position[(slot_index, position)]
            matches += weights[edge_index] * (matrix[:, position] == desired[position])
        for other, other_index in enumerate(assignment):
            if other != slot_index and self.slots[other].length == slot.length:
                matches[other_index] = -1e9
        current = assignment[slot_index]
        current_score = float(matches[current])
        if current_score < float(weights[[
            self.edge_for_slot_position[(slot_index, position)]
            for position in range(slot.length)
        ]].sum()):
            matches[current] = -1e9
        best = float(matches.max())
        threshold = best - (1.0 if noisy else 0.0)
        pool = np.flatnonzero(matches >= threshold)
        if len(pool) == 0:
            return current, current_score, current_score
        if len(pool) > 512:
            pool = self.np_rng.choice(pool, size=512, replace=False)
        non_tabu = np.asarray(
            [index for index in pool if (slot_index, int(index)) not in tabu],
            dtype=np.int64,
        )
        if len(non_tabu):
            pool = non_tabu
        pool_matches = matches[pool]
        best_match = float(pool_matches.max())
        strongest = pool[pool_matches == best_match]
        qualities = self.quality[slot.length][strongest]
        top_quality = float(qualities.max())
        finalists = strongest[qualities >= top_quality - 0.015]
        return int(self.np_rng.choice(finalists)), best_match, current_score

    def solve(
        self,
        initial_answers: dict[int, str] | None = None,
    ) -> tuple[dict[int, str] | None, dict]:
        solution = None
        while time.monotonic() < self.deadline and solution is None:
            self.restarts += 1
            if self.restarts == 1 and initial_answers:
                assignment = [
                    self.word_indexes[slot.length][initial_answers[index]]
                    for index, slot in enumerate(self.slots)
                ]
            else:
                assignment = self.initial_assignment()
            weights = np.ones(len(self.crossings), dtype=np.float64)
            tabu_queue: deque[tuple[int, int]] = deque(maxlen=160)
            tabu: set[tuple[int, int]] = set()
            plateau = 0
            restart_best = len(self.crossings) + 1
            for _local_step in range(8_000):
                now = time.monotonic()
                if now >= self.deadline:
                    break
                self.steps += 1
                conflicts, counts = self.conflict_edges(assignment, weights)
                conflict_count = len(conflicts)
                if conflict_count < self.best_conflicts:
                    self.best_conflicts = conflict_count
                    self.best_assignment = list(assignment)
                if conflict_count == 0:
                    answers = {
                        index: self.word(index, word_index)
                        for index, word_index in enumerate(assignment)
                    }
                    if len(set(answers.values())) == len(answers):
                        solution = answers
                        break
                if conflict_count < restart_best:
                    restart_best = conflict_count
                    plateau = 0
                else:
                    plateau += 1
                max_conflicts = float(counts.max())
                hot = [
                    index for index, count in enumerate(counts)
                    if count == max_conflicts
                ]
                if plateau > 120:
                    _edge_index, left, right = self.rng.choice(conflicts)
                    slot_index = self.rng.choice((left, right))
                else:
                    slot_index = self.rng.choice(hot)
                old_index = assignment[slot_index]
                new_index, best_local_score, current_local_score = self.replacement(
                    slot_index,
                    assignment,
                    noisy=plateau > 60 or self.rng.random() < 0.04,
                    tabu=tabu,
                    weights=weights,
                )
                assignment[slot_index] = new_index
                if (
                    self.breakout
                    and best_local_score <= current_local_score
                    and plateau > 25
                ):
                    for edge_index, _left, _right in conflicts:
                        weights[edge_index] += 1.0
                item = (slot_index, old_index)
                if len(tabu_queue) == tabu_queue.maxlen:
                    tabu.discard(tabu_queue[0])
                tabu_queue.append(item)
                tabu.add(item)
                if plateau > 1_400:
                    break
                if now - self.last_progress >= 10:
                    print(json.dumps({
                        "event": "progress",
                        "solver": "fixed-ribbon-min-conflicts",
                        "elapsedSeconds": round(now - self.started, 1),
                        "steps": self.steps,
                        "restarts": self.restarts,
                        "bestCrossingConflicts": self.best_conflicts,
                    }), flush=True)
                    self.last_progress = now
        telemetry = {
            "solver": "fixed-ribbon-min-conflicts",
            "seed": self.seed,
            "breakout": self.breakout,
            "elapsedSeconds": round(time.monotonic() - self.started, 3),
            "reason": "solved" if solution is not None else "timeout",
            "steps": self.steps,
            "restarts": self.restarts,
            "crossingCount": len(self.crossings),
            "bestCrossingConflicts": self.best_conflicts,
        }
        if self.best_assignment is not None:
            telemetry["bestAssignment"] = [
                {
                    "slotIndex": index,
                    "slotId": self.slots[index].slot_id,
                    "answer": self.word(index, word_index),
                }
                for index, word_index in enumerate(self.best_assignment)
            ]
        return solution, telemetry


class FixedRibbonBandSolver:
    """Exact top/bottom band search for the fixed A01 layout.

    Across answers are selected in alternating top/bottom order. Every whole
    answer immediately filters the bitset of each crossing down answer, so a
    suffix chosen at the bottom constrains the prefix at the top before the
    middle rows are explored.
    """

    SLOT_ORDER = (8, 21, 9, 20, 10, 19, 18, 12, 11, 15, 16)

    def __init__(
        self,
        *,
        slots,
        words_by_length: dict[int, tuple[str, ...]],
        metadata: dict[str, dict],
        canonical: dict[str, dict],
        owner_accepts: dict[str, list[dict]],
        seed: int,
        seconds: float,
    ) -> None:
        self.slots = slots
        self.words_by_length = words_by_length
        self.metadata = metadata
        self.canonical = canonical
        self.owner_accepts = owner_accepts
        self.seed = seed
        self.rng = random.Random(seed)
        self.started = time.monotonic()
        self.deadline = self.started + seconds
        self.word_indexes = {
            length: {word: index for index, word in enumerate(words)}
            for length, words in words_by_length.items()
        }
        self.letter_masks = {}
        for length, words in words_by_length.items():
            if length not in {3, 4, 5, 8, 9}:
                continue
            masks = [[0] * 26 for _ in range(length)]
            for index, word in enumerate(words):
                bit = 1 << index
                for position, letter in enumerate(word):
                    masks[position][ord(letter) - 65] |= bit
            self.letter_masks[length] = masks
        cell_links, _neighbors = crossing_arcs(slots)
        self.down_slots = [
            slot.index for slot in slots if slot.direction == "down"
        ]
        self.down_position = {
            slot_index: position for position, slot_index in enumerate(self.down_slots)
        }
        self.crossings_by_across = {}
        for slot_index in self.SLOT_ORDER:
            links = []
            for own_position, cell in enumerate(slots[slot_index].cells):
                other = [item for item in cell_links[cell] if item[0] != slot_index]
                if len(other) != 1:
                    raise ValueError(f"croisement A01 ambigu a {cell}")
                down_slot, down_word_position = other[0]
                links.append((
                    own_position,
                    self.down_position[down_slot],
                    down_slot,
                    down_word_position,
                ))
            self.crossings_by_across[slot_index] = tuple(links)
        self.priority = {}
        for words in words_by_length.values():
            for word in words:
                entry = metadata[word]
                frequency = float(entry.get("sourceFrequency", 0) or 0)
                school = float(entry.get("schoolFrequency", 0) or 0)
                reviewed_bonus = 0.18 if (
                    word in canonical or word in owner_accepts
                ) else 0
                central_bonus = 0.07 if word in canonical else 0
                frequency_bonus = min(0.10, (frequency + school / 1000) / 120)
                self.priority[word] = (
                    self.rng.random()
                    - reviewed_bonus
                    - central_bonus
                    - frequency_bonus
                )
        self.support_cache = {}
        self.allowed_cache = {}
        self.dead_states: set[tuple] = set()
        self.nodes = 0
        self.best_depth = 0
        self.best_partial = {}
        self.wipeouts = 0
        self.last_progress = self.started
        self.timed_out = False

    def support_letters(self, length: int, position: int, domain: int) -> int:
        key = (length, position, domain)
        cached = self.support_cache.get(key)
        if cached is not None:
            return cached
        result = 0
        for code, mask in enumerate(self.letter_masks[length][position]):
            if domain & mask:
                result |= 1 << code
        if len(self.support_cache) > 350_000:
            self.support_cache.clear()
        self.support_cache[key] = result
        return result

    def allowed_words(self, length: int, position: int, letters: int) -> int:
        key = (length, position, letters)
        cached = self.allowed_cache.get(key)
        if cached is not None:
            return cached
        result = 0
        bits = letters
        while bits:
            least = bits & -bits
            result |= self.letter_masks[length][position][least.bit_length() - 1]
            bits ^= least
        self.allowed_cache[key] = result
        return result

    def across_domain(
        self,
        slot_index: int,
        down_domains: tuple[int, ...],
    ) -> int:
        slot = self.slots[slot_index]
        domain = (1 << len(self.words_by_length[slot.length])) - 1
        for own_position, down_index, down_slot_index, down_word_position in (
            self.crossings_by_across[slot_index]
        ):
            down_slot = self.slots[down_slot_index]
            letters = self.support_letters(
                down_slot.length,
                down_word_position,
                down_domains[down_index],
            )
            domain &= self.allowed_words(slot.length, own_position, letters)
            if not domain:
                break
        return domain

    @staticmethod
    def bit_indexes(bits: int):
        while bits:
            least = bits & -bits
            yield least.bit_length() - 1
            bits ^= least

    def candidate_order(
        self,
        slot_index: int,
        domain: int,
        down_domains: tuple[int, ...],
    ) -> list[int]:
        words = self.words_by_length[self.slots[slot_index].length]
        candidates = list(self.bit_indexes(domain))

        def key(index: int) -> tuple:
            word = words[index]
            support = 0.0
            for own_position, down_index, down_slot_index, down_word_position in (
                self.crossings_by_across[slot_index]
            ):
                down_length = self.slots[down_slot_index].length
                code = ord(word[own_position]) - 65
                remaining = (
                    down_domains[down_index]
                    & self.letter_masks[down_length][down_word_position][code]
                ).bit_count()
                support += math.log1p(remaining)
            return (-support, self.priority[word], word)

        candidates.sort(key=key)
        return candidates

    def apply_answer(
        self,
        slot_index: int,
        word: str,
        down_domains: tuple[int, ...],
    ) -> tuple[int, ...] | None:
        revised = list(down_domains)
        for own_position, down_index, down_slot_index, down_word_position in (
            self.crossings_by_across[slot_index]
        ):
            down_length = self.slots[down_slot_index].length
            code = ord(word[own_position]) - 65
            revised[down_index] &= self.letter_masks[down_length][down_word_position][code]
            if not revised[down_index]:
                self.wipeouts += 1
                return None
        return tuple(revised)

    def search(
        self,
        depth: int,
        down_domains: tuple[int, ...],
        chosen: dict[int, str],
    ) -> dict[int, str] | None:
        now = time.monotonic()
        if now >= self.deadline:
            self.timed_out = True
            return None
        self.nodes += 1
        if depth > self.best_depth:
            self.best_depth = depth
            self.best_partial = dict(chosen)
        if now - self.last_progress >= 10:
            print(json.dumps({
                "event": "progress",
                "solver": "fixed-ribbon-top-bottom-bitset",
                "elapsedSeconds": round(now - self.started, 1),
                "nodes": self.nodes,
                "bestAcrossSlots": self.best_depth,
                "deadStates": len(self.dead_states),
            }), flush=True)
            self.last_progress = now
        if depth == len(self.SLOT_ORDER):
            down_answers = {}
            for domain_index, domain in enumerate(down_domains):
                if domain.bit_count() != 1:
                    return None
                slot_index = self.down_slots[domain_index]
                word_index = domain.bit_length() - 1
                down_answers[slot_index] = self.words_by_length[
                    self.slots[slot_index].length
                ][word_index]
            complete = {**chosen, **down_answers}
            if len(set(complete.values())) != len(complete):
                return None
            return complete
        state = (depth, down_domains)
        if state in self.dead_states:
            return None
        slot_index = self.SLOT_ORDER[depth]
        domain = self.across_domain(slot_index, down_domains)
        if not domain:
            self.wipeouts += 1
            return None
        for word_index in self.candidate_order(slot_index, domain, down_domains):
            word = self.words_by_length[self.slots[slot_index].length][word_index]
            if word in chosen.values():
                continue
            revised = self.apply_answer(slot_index, word, down_domains)
            if revised is None:
                continue
            # Forward-check every remaining band. A choice near the top can
            # make the last bottom row impossible several levels later; there
            # is no reason to descend through that already-dead branch.
            future_impossible = False
            for future_slot in self.SLOT_ORDER[depth + 1:]:
                if not self.across_domain(future_slot, revised):
                    self.wipeouts += 1
                    future_impossible = True
                    break
            if future_impossible:
                continue
            chosen[slot_index] = word
            solution = self.search(depth + 1, revised, chosen)
            if solution is not None:
                return solution
            chosen.pop(slot_index, None)
            if self.timed_out:
                return None
        if len(self.dead_states) < 750_000:
            self.dead_states.add(state)
        return None

    def solve(self) -> tuple[dict[int, str] | None, dict]:
        initial = tuple(
            (1 << len(self.words_by_length[self.slots[index].length])) - 1
            for index in self.down_slots
        )
        solution = self.search(0, initial, {})
        return solution, {
            "solver": "fixed-ribbon-top-bottom-bitset",
            "seed": self.seed,
            "elapsedSeconds": round(time.monotonic() - self.started, 3),
            "reason": "solved" if solution is not None else (
                "timeout" if self.timed_out else "exhausted"
            ),
            "slotOrder": list(self.SLOT_ORDER),
            "nodes": self.nodes,
            "deadStates": len(self.dead_states),
            "domainWipeouts": self.wipeouts,
            "bestAcrossSlots": self.best_depth,
            "bestPartial": [
                {
                    "slotIndex": index,
                    "slotId": self.slots[index].slot_id,
                    "answer": answer,
                }
                for index, answer in sorted(self.best_partial.items())
            ],
        }


def recover_down_answers(slots, across: dict[int, str]) -> dict[int, str]:
    letters: dict[tuple[int, int], str] = {}
    for slot_index, answer in across.items():
        for cell, letter in zip(slots[slot_index].cells, answer):
            previous = letters.setdefault(cell, letter)
            if previous != letter:
                raise ValueError(f"croisement incoherent a {cell}")
    result = {}
    for slot in slots:
        if slot.direction != "down":
            continue
        result[slot.index] = "".join(letters[cell] for cell in slot.cells)
    return result


def selected_clue(
    answer: str,
    canonical: dict[str, dict],
    owner_accepts: dict[str, list[dict]],
) -> dict | None:
    if answer in canonical:
        entry = canonical[answer]
        return {
            "clue": entry.get("clue"),
            "source": entry.get("sourceId") or entry.get("sourceType"),
            "status": "central-canonical-reviewed",
        }
    if answer in owner_accepts:
        entry = owner_accepts[answer][0]
        return {
            "clue": entry["clue"],
            "source": entry["source"],
            "status": "owner-accepted",
        }
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shape-file", type=Path, default=DEFAULT_SHAPES)
    parser.add_argument("--shape-id", default="reference-ribbon-a-01")
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--seed", type=int, default=20260717)
    parser.add_argument(
        "--solver",
        choices=("band", "local", "arc", "row"),
        default="band",
    )
    parser.add_argument(
        "--strategy",
        choices=("information", "mrv"),
        default="information",
    )
    parser.add_argument(
        "--breakout",
        action="store_true",
        help="Active la ponderation reactive des croisements pour le solveur local.",
    )
    parser.add_argument(
        "--anchor-report",
        type=Path,
        help=(
            "Rapport local precedent: conserve les slots sans conflit et "
            "relache seulement les extremites des croisements faux."
        ),
    )
    parser.add_argument(
        "--anchor-reviewed-only",
        action="store_true",
        help="Parmi les ancres sans conflit, ne garde que les reponses deja relues.",
    )
    parser.add_argument(
        "--release-anchor-slot",
        action="append",
        type=int,
        default=[],
        help="Slot explicitement retiré des ancres de voisinage (option répétable).",
    )
    parser.add_argument(
        "--initial-report",
        type=Path,
        help="Meilleur etat local precedent a reprendre au premier redemarrage.",
    )
    parser.add_argument(
        "--preferred-report",
        type=Path,
        help=(
            "Rapport min-conflicts utilise uniquement pour ordonner les "
            "valeurs du solveur arc exact; aucune reponse n'est fixee."
        ),
    )
    parser.add_argument("--permissive-lexique", action="store_true")
    parser.add_argument(
        "--exclude-answer",
        action="append",
        default=[],
        help="Réponse retirée de tous les domaines (option répétable).",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    shape, slots = load_shape(args.shape_file, args.shape_id)
    if shape["id"] != "reference-ribbon-a-01":
        raise ValueError("ce solveur est volontairement limite a reference-ribbon-a-01")
    validate_fixed_layout(slots)
    _central_words, canonical = load_words()
    words_by_length, metadata, corpus_stats = load_expansion_words(
        canonical,
        permissive=args.permissive_lexique,
        include_morphalou=True,
    )
    excluded_answers = {answer.upper() for answer in args.exclude_answer}
    if excluded_answers:
        words_by_length = {
            length: tuple(
                word for word in words if word not in excluded_answers
            )
            for length, words in words_by_length.items()
        }
        corpus_stats["explicitSolverExclusions"] = sorted(excluded_answers)
    owner_accepts = load_owner_accepts()
    solver_class = {
        "band": FixedRibbonBandSolver,
        "local": FixedRibbonMinConflictsSolver,
        "arc": FixedRibbonArcSolver,
        "row": FixedRibbonSolver,
    }[args.solver]
    solver_options = {
        "slots": slots,
        "words_by_length": words_by_length,
        "metadata": metadata,
        "canonical": canonical,
        "owner_accepts": owner_accepts,
        "seed": args.seed,
        "seconds": args.seconds,
    }
    if args.solver == "arc":
        solver_options["strategy"] = args.strategy
        if args.preferred_report:
            preferred_document = json.loads(
                args.preferred_report.read_text(encoding="utf-8")
            )
            preferred_records = (
                preferred_document.get("solverTelemetry", {}).get(
                    "bestAssignment", []
                )
                or preferred_document.get("grid", {}).get("words", [])
            )
            solver_options["preferred_answers"] = {
                int(item["slotIndex"]): item["answer"]
                for item in preferred_records
            }
    elif args.solver == "local":
        solver_options["breakout"] = args.breakout
    solver = solver_class(**solver_options)
    fixed_answers = None
    if args.anchor_report:
        if args.solver != "arc":
            raise ValueError("--anchor-report exige --solver arc")
        anchor_document = json.loads(args.anchor_report.read_text(encoding="utf-8"))
        records = (
            anchor_document.get("solverTelemetry", {}).get("bestAssignment", [])
            or anchor_document.get("grid", {}).get("words", [])
        )
        anchored = {int(item["slotIndex"]): item["answer"] for item in records}
        cell_links, _neighbors = crossing_arcs(slots)
        conflicted_slots = set()
        for links in cell_links.values():
            if len(links) != 2:
                continue
            (left, left_position), (right, right_position) = links
            if anchored[left][left_position] != anchored[right][right_position]:
                conflicted_slots.update((left, right))
        fixed_answers = {
            index: answer for index, answer in anchored.items()
            if index not in conflicted_slots
        }
        if args.anchor_reviewed_only:
            fixed_answers = {
                index: answer for index, answer in fixed_answers.items()
                if answer in canonical or answer in owner_accepts
            }
        for slot_index in args.release_anchor_slot:
            fixed_answers.pop(slot_index, None)
    initial_answers = None
    if args.initial_report:
        if args.solver != "local":
            raise ValueError("--initial-report exige --solver local")
        initial_document = json.loads(args.initial_report.read_text(encoding="utf-8"))
        initial_answers = {
            int(item["slotIndex"]): item["answer"]
            for item in initial_document["solverTelemetry"]["bestAssignment"]
        }
    if args.solver == "arc":
        solved_answers, telemetry = solver.solve(fixed_answers=fixed_answers)
    elif args.solver == "local":
        solved_answers, telemetry = solver.solve(initial_answers=initial_answers)
    else:
        solved_answers, telemetry = solver.solve()
    solution = None
    if solved_answers is not None:
        if args.solver == "row":
            all_answers = {
                **solved_answers,
                **recover_down_answers(slots, solved_answers),
            }
        else:
            all_answers = solved_answers
        if len(all_answers) != len(slots):
            raise ValueError("la fermeture n'a pas produit les 22 reponses")
        selected = []
        for index, answer in sorted(all_answers.items()):
            clue = selected_clue(answer, canonical, owner_accepts)
            selected.append({
                "slotIndex": index,
                "slotId": slots[index].slot_id,
                "answer": answer,
                "direction": slots[index].direction,
                "length": slots[index].length,
                "reviewedClue": clue,
                "needsEditorialClue": clue is None,
                "lexicalSource": metadata[answer].get("source")
                    or metadata[answer].get("partOfSpeech"),
            })
        solution = {
            "answers": selected,
            "reviewedClueCount": sum(not item["needsEditorialClue"] for item in selected),
            "needsEditorialClueCount": sum(item["needsEditorialClue"] for item in selected),
        }
    report = {
        "version": 1,
        "kind": "immutable-fixed-shape-lexical-closure",
        "shapeId": shape["id"],
        "shapeModified": False,
        "columns": shape["columns"],
        "rows": shape["rows"],
        "slotCount": len(slots),
        "complete": solution is not None,
        "publicationEligible": bool(
            solution is not None and solution["needsEditorialClueCount"] == 0
        ),
        "publicationPolicy": (
            "Une fermeture lexicale n'est jamais publiee avant validation de "
            "chaque couple mot-definition et audit topologique."
        ),
        "ownerDecisionTraining": {
            "acceptedAnswersAvailable": len(owner_accepts),
            "files": [path.name for path in OWNER_DECISIONS if path.exists()],
        },
        "corpusFilter": corpus_stats,
        "solverTelemetry": telemetry,
        "solution": solution,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "event": "finished",
        "output": str(args.output),
        "complete": report["complete"],
        "publicationEligible": report["publicationEligible"],
        "solverTelemetry": telemetry,
        "solution": solution,
    }, ensure_ascii=False, indent=2))
    return 0 if solution is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
