#!/usr/bin/env python3
"""Exact row-first solver for MotMan strict ribbon silhouettes 02/03/04.

Unlike the historical band solver, this module never truncates a structural
domain.  A timeout is reported as ``cutoff`` and is never confused with a
proof of infeasibility.  Only fully exhausted states enter the optional
persistent dead-state cache.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import random
import sqlite3
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence

from wordfreq import zipf_frequency

from build_compact_7x8_review import family_key
from search_compact_grid_pilot import (
    GRAMMAR_ANSWERS,
    PILOT_REVIEWED_LONG,
    PILOT_REVIEWED_NATURAL_FORMS,
    PILOT_SAFE_SHORT,
    rotation_cooldown_usage,
)


ROOT = Path(__file__).resolve().parents[1]
SHAPES = {
    "pilot-7x8-strict-02": 5,
    "pilot-7x8-strict-03": 4,
    "pilot-7x8-strict-04": 3,
    "strict-02": 5,
    "strict-03": 4,
    "strict-04": 3,
}
SENSITIVE_SHORT = {"CON", "CUL", "GAY", "HIV", "HOT", "SEX", "SS", "WC"}
CURRENT_SHORT = {
    "ADO", "ALU", "ANE", "API", "APP", "BAC", "BIO", "BMX", "BOA", "BOB",
    "BOT", "BOX", "BTS", "BUG", "BUS", "BUT", "CAF", "CDI", "CPE", "FAC",
    "FAQ", "FAX", "FBI", "FIG", "FOX", "FUN", "GAG", "GEL", "GIF", "GPS",
    "GPU", "GTA", "HIT", "HUB", "IRM", "JOB", "KFC", "KID", "KIT", "LAB",
    "LAN", "LED", "LOL", "MDR", "MIA", "MIX", "MMO", "NBA", "NEM", "NID",
    "ONG", "PAN", "PDF", "PME", "POT", "QCM", "RAM", "RAP", "RAT", "RER",
    "RIB", "RIO", "ROC", "RPG", "RSA", "RTT", "SAM", "SET", "SIM", "SMS",
    "TAF", "TAG", "TGV", "TIC", "TNT", "TPE", "TTC", "TVA", "ULM", "USB",
    "URL", "VIP", "VPN", "VTT", "WEB", "WII", "WOK", "WOW", "YEN", "ZIP",
    "ZOO",
}
POP_LONG = (
    set(PILOT_REVIEWED_LONG)
    | set(PILOT_REVIEWED_NATURAL_FORMS)
    | {"AVATAR"}
)


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or "").upper())
    return "".join(char for char in text if unicodedata.category(char) != "Mn" and char.isalpha())


def parse_fixed_answer(value: str) -> tuple[int, str]:
    """Parse ``SLOT:WORD`` while preserving the grid's accentless convention."""

    slot_text, separator, raw_answer = value.partition(":")
    if not separator:
        raise argparse.ArgumentTypeError("Réponse imposée attendue sous la forme SLOT:MOT")
    try:
        slot = int(slot_text)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Le slot imposé doit être un entier") from error
    answer = normalize(raw_answer)
    if not answer:
        raise argparse.ArgumentTypeError("La réponse imposée ne peut pas être vide")
    return slot, answer


def slot_lengths(long_columns: int) -> tuple[int, ...]:
    """Return lengths in the stable order exported by ``_solution_payload``."""

    if long_columns not in {3, 4, 5}:
        raise ValueError("long_columns doit valoir 3, 4 ou 5")
    short_columns = 6 - long_columns
    return (
        *((7,) * long_columns),
        *((3,) * short_columns),
        6, 6, 6,
        long_columns,
        *((3,) * short_columns),
        6, 6, 6,
    )


def validate_fixed_answers(
    pairs: Sequence[tuple[int, str]],
    *,
    long_columns: int,
    six: Sequence[WordRecord],
    seven: Sequence[WordRecord],
    short: Sequence[WordRecord],
    middle: Sequence[WordRecord],
) -> dict[int, str]:
    """Validate forced answers against the exact eligible domain for each slot.

    Blacklisted or editorially excluded words are absent from these pools, so
    domain membership is also the hard blacklist gate.
    """

    lengths = slot_lengths(long_columns)
    short_columns = 6 - long_columns
    pools = {
        "six": {record.answer: record for record in six},
        "seven": {record.answer: record for record in seven},
        "short": {record.answer: record for record in short},
        "middle": {record.answer: record for record in middle},
    }

    def pool_for_slot(slot: int) -> dict[str, WordRecord]:
        if slot < long_columns:
            return pools["seven"]
        if slot < 6:
            return pools["short"]
        if slot < 9:
            return pools["six"]
        if slot == 9:
            return pools["middle"]
        if slot < 10 + short_columns:
            return pools["short"]
        return pools["six"]

    fixed: dict[int, str] = {}
    fixed_families: dict[str, int] = {}
    for slot, raw_answer in pairs:
        answer = normalize(raw_answer)
        if slot < 0 or slot >= len(lengths):
            raise ValueError(f"Slot imposé hors limites : {slot}")
        if slot in fixed:
            raise ValueError(f"Le slot {slot} est imposé plusieurs fois")
        expected_length = lengths[slot]
        if len(answer) != expected_length:
            raise ValueError(
                f"Longueur invalide pour le slot {slot} : "
                f"{answer} fait {len(answer)}, attendu {expected_length}"
            )
        record = pool_for_slot(slot).get(answer)
        if record is None:
            raise ValueError(
                f"{answer} n'appartient pas au domaine éligible du slot {slot} "
                "(qualité, forme ou blacklist)"
            )
        previous_slot = fixed_families.get(record.family)
        if previous_slot is not None:
            raise ValueError(
                f"Famille {record.family} imposée deux fois : "
                f"slots {previous_slot} et {slot}"
            )
        fixed[slot] = answer
        fixed_families[record.family] = slot
    return dict(sorted(fixed.items()))


@dataclass(frozen=True)
class WordRecord:
    answer: str
    score: float = 0.0
    zipf: float = 9.0
    family: str = ""
    image: bool = False
    grammar: bool = False

    def __post_init__(self) -> None:
        if not self.family:
            object.__setattr__(self, "family", family_key(self.answer))


class PrefixTrie:
    """Compact integer-node trie; insertion order is deterministic."""

    def __init__(self, words: Iterable[str]) -> None:
        self.children: list[dict[str, int]] = [{}]
        self.terminal: list[str | None] = [None]
        self.prefix: list[str] = [""]
        for word in sorted(set(words)):
            node = 0
            for char in word:
                child = self.children[node].get(char)
                if child is None:
                    child = len(self.children)
                    self.children[node][char] = child
                    self.children.append({})
                    self.terminal.append(None)
                    self.prefix.append(self.prefix[node] + char)
                node = child
            self.terminal[node] = word

    def advance(self, node: int, char: str) -> int | None:
        return self.children[node].get(char)


class WordDomain:
    def __init__(self, records: Sequence[WordRecord], seed: int = 0) -> None:
        rng = random.Random(seed)
        # Sort before consuming the PRNG: sets used by editorial reservoirs must
        # not make a seeded run depend on Python's per-process hash salt.
        keyed = [
            (record.score, rng.random(), record.answer, record)
            for record in sorted(records, key=lambda item: item.answer)
        ]
        keyed.sort(key=lambda item: (-item[0], item[1], item[2]))
        self.records = tuple(item[3] for item in keyed)
        self.by_answer = {record.answer: record for record in self.records}
        length = len(self.records[0].answer) if self.records else 0
        self.masks: list[dict[str, int]] = [defaultdict(int) for _ in range(length)]
        for index, record in enumerate(self.records):
            for position, char in enumerate(record.answer):
                self.masks[position][char] |= 1 << index
        self.full_mask = (1 << len(self.records)) - 1

    def matching(self, tries: Sequence[PrefixTrie], nodes: Sequence[int]) -> Iterable[WordRecord]:
        if not self.records or len(tries) != len(nodes) or len(nodes) != len(self.masks):
            return ()
        mask = self.full_mask
        for position, (trie, node) in enumerate(zip(tries, nodes)):
            allowed = 0
            for char in trie.children[node]:
                allowed |= self.masks[position].get(char, 0)
            mask &= allowed
            if not mask:
                return ()

        def emit() -> Iterable[WordRecord]:
            remaining = mask
            while remaining:
                bit = remaining & -remaining
                yield self.records[bit.bit_length() - 1]
                remaining ^= bit
        return emit()


class SearchResult(Enum):
    FOUND = "found"
    DEAD = "dead"
    CUTOFF = "cutoff"


class DeadStateCache:
    """Persistent cache scoped by a digest of every effective search input."""

    def __init__(self, path: Path | None, context_hash: str) -> None:
        self.path = path
        self.context_hash = context_hash
        self.connection: sqlite3.Connection | None = None
        self.states: set[str] = set()
        self.pending: list[str] = []
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=30)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS dead_states ("
            "context_hash TEXT NOT NULL, state_hash TEXT NOT NULL, "
            "PRIMARY KEY(context_hash, state_hash))"
        )
        self.states = {
            row[0] for row in self.connection.execute(
                "SELECT state_hash FROM dead_states WHERE context_hash = ?", (context_hash,)
            )
        }

    def contains(self, state_hash: str) -> bool:
        return state_hash in self.states

    def add(self, state_hash: str) -> None:
        if state_hash in self.states:
            return
        self.states.add(state_hash)
        self.pending.append(state_hash)
        if len(self.pending) >= 500:
            self.flush()

    def flush(self) -> None:
        if not self.pending or self.connection is None:
            self.pending.clear()
            return
        self.connection.executemany(
            "INSERT OR IGNORE INTO dead_states(context_hash, state_hash) VALUES (?, ?)",
            ((self.context_hash, item) for item in self.pending),
        )
        self.connection.commit()
        self.pending.clear()

    def close(self) -> None:
        self.flush()
        if self.connection is not None:
            self.connection.close()


@dataclass(frozen=True)
class Selection:
    answers: frozenset[str] = frozenset()
    families: frozenset[str] = frozenset()
    image_count: int = 0
    grammar_count: int = 0
    unfamiliar_count: int = 0


@dataclass(frozen=True)
class SearchConfig:
    long_columns: int
    seconds: float = 30.0
    minimum_images: int = 0
    maximum_images: int = 6
    maximum_grammar_answers: int = 1
    minimum_familiarity_zipf: float = 3.0
    maximum_unfamiliar_answers: int = 2
    minimum_solution_distance: int = 1
    checkpoint: Path | None = None


class RibbonRowSolver:
    def __init__(
        self,
        *,
        six: Sequence[WordRecord],
        seven: Sequence[WordRecord],
        short: Sequence[WordRecord],
        middle: Sequence[WordRecord],
        config: SearchConfig,
        seed: int = 0,
        avoid_fills: Sequence[Sequence[str]] = (),
        cache_path: Path | None = None,
        fixed_answers: dict[int, str] | None = None,
    ) -> None:
        self.config = config
        self.long_columns = config.long_columns
        if self.long_columns not in {3, 4, 5}:
            raise ValueError("long_columns doit valoir 3, 4 ou 5")
        self.short_columns = 6 - self.long_columns
        self.expected_answers = 19 - self.long_columns
        self.six = WordDomain(six, seed)
        self.middle = WordDomain(middle, seed + 1)
        self.seven_by_answer = {record.answer: record for record in seven}
        self.short_by_answer = {record.answer: record for record in short}
        self.seven_trie = PrefixTrie(self.seven_by_answer)
        self.short_trie = PrefixTrie(self.short_by_answer)
        self.record_by_answer = {
            record.answer: record for records in (six, seven, short, middle) for record in records
        }
        self.fixed_answers = validate_fixed_answers(
            list((fixed_answers or {}).items()),
            long_columns=self.long_columns,
            six=six,
            seven=seven,
            short=short,
            middle=middle,
        )
        self.avoid_fills = tuple(tuple(fill) for fill in avoid_fills if len(fill) == self.expected_answers)
        self.started = time.monotonic()
        self.deadline = self.started + max(0.0, config.seconds)
        self.solution: dict | None = None
        self.nodes = 0
        self.cache_hits = 0
        self.dead_added = 0
        self.last_stage = "initial"
        self.context_hash = self._context_hash(six, seven, short, middle)
        self.cache = DeadStateCache(cache_path, self.context_hash)
        self.loaded_dead_states = len(self.cache.states)
        self.last_checkpoint = self.started

    def _context_hash(self, *groups: Sequence[WordRecord]) -> str:
        payload = {
            "version": 3,
            "longColumns": self.long_columns,
            "filters": {
                "minimumImages": self.config.minimum_images,
                "maximumImages": self.config.maximum_images,
                "maximumGrammar": self.config.maximum_grammar_answers,
                "minimumZipf": self.config.minimum_familiarity_zipf,
                "maximumUnfamiliar": self.config.maximum_unfamiliar_answers,
                "minimumDistance": self.config.minimum_solution_distance,
            },
            "groups": [
                sorted((r.answer, r.family, r.image, r.grammar, r.zipf) for r in group)
                for group in groups
            ],
            "avoid": self.avoid_fills,
            "fixedAnswers": sorted(self.fixed_answers.items()),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _state_hash(
        self, stage: str, depth: int, long_nodes: Sequence[int], short_nodes: Sequence[int],
        selection: Selection, rows: Sequence[str], middle: str = "",
    ) -> str:
        payload = (
            stage, depth,
            tuple(self.seven_trie.prefix[node] for node in long_nodes),
            tuple(self.short_trie.prefix[node] for node in short_nodes),
            tuple(sorted(selection.families)), selection.image_count,
            selection.grammar_count, selection.unfamiliar_count,
            tuple(rows), middle,
        )
        return hashlib.sha1(repr(payload).encode("utf-8")).hexdigest()

    def _timed_out(self) -> bool:
        return time.monotonic() >= self.deadline

    def _checkpoint(self, status: str = "running", force: bool = False) -> None:
        path = self.config.checkpoint
        now = time.monotonic()
        if path is None or (not force and now - self.last_checkpoint < 10.0):
            return
        self.last_checkpoint = now
        payload = {
            "version": 1,
            "kind": "motman-strict-ribbon-row-dfs-checkpoint",
            "contextHash": self.context_hash,
            "status": status,
            "lastStage": self.last_stage,
            "elapsedSeconds": round(now - self.started, 3),
            "nodes": self.nodes,
            "cacheHits": self.cache_hits,
            "deadStates": len(self.cache.states),
            "fixedAnswers": {
                str(slot): answer for slot, answer in self.fixed_answers.items()
            },
            "solution": self.solution,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)

    def _add(self, selection: Selection, records: Iterable[WordRecord]) -> Selection | None:
        answers = set(selection.answers)
        families = set(selection.families)
        image_count = selection.image_count
        grammar_count = selection.grammar_count
        unfamiliar_count = selection.unfamiliar_count
        for record in records:
            if record.answer in answers or record.family in families:
                return None
            answers.add(record.answer)
            families.add(record.family)
            image_count += int(record.image)
            grammar_count += int(record.grammar)
            unfamiliar_count += int(record.zipf < self.config.minimum_familiarity_zipf)
        if image_count > self.config.maximum_images:
            return None
        if grammar_count > self.config.maximum_grammar_answers:
            return None
        if unfamiliar_count > self.config.maximum_unfamiliar_answers:
            return None
        return Selection(frozenset(answers), frozenset(families), image_count, grammar_count, unfamiliar_count)

    def _complete_nodes(self, trie: PrefixTrie, nodes: Sequence[int]) -> tuple[WordRecord, ...] | None:
        result = []
        source = self.seven_by_answer if trie is self.seven_trie else self.short_by_answer
        for node in nodes:
            answer = trie.terminal[node]
            if answer is None:
                return None
            result.append(source[answer])
        return tuple(result)

    def _advance_nodes(
        self, word: str, long_nodes: Sequence[int], short_nodes: Sequence[int],
    ) -> tuple[tuple[int, ...], tuple[int, ...]] | None:
        next_long = []
        for position, node in enumerate(long_nodes):
            child = self.seven_trie.advance(node, word[position])
            if child is None:
                return None
            next_long.append(child)
        next_short = []
        for offset, node in enumerate(short_nodes, self.long_columns):
            child = self.short_trie.advance(node, word[offset])
            if child is None:
                return None
            next_short.append(child)
        return tuple(next_long), tuple(next_short)

    def _dead_or_cached(self, state_hash: str) -> bool:
        if self.cache.contains(state_hash):
            self.cache_hits += 1
            return True
        return False

    def _mark_dead(self, state_hash: str) -> SearchResult:
        self.cache.add(state_hash)
        self.dead_added += 1
        return SearchResult.DEAD

    def _distance_ok(self, answers: Sequence[str]) -> bool:
        return all(
            sum(left != right for left, right in zip(answers, reference))
            >= self.config.minimum_solution_distance
            for reference in self.avoid_fills
        )

    def _answer_is_forced(self, slot: int, answer: str) -> bool:
        forced = self.fixed_answers.get(slot)
        return forced is None or forced == answer

    def _row_matches_fixed(self, stage: str, depth: int, answer: str) -> bool:
        """Reject a row as soon as it disagrees with any forced crossing."""

        if stage == "top":
            row_slot = 6 + depth
            vertical_offset = depth
            short_slot_start = self.long_columns
        else:
            row_slot = 10 + self.short_columns + depth
            vertical_offset = 4 + depth
            short_slot_start = 10
        if not self._answer_is_forced(row_slot, answer):
            return False
        for column in range(self.long_columns):
            forced = self.fixed_answers.get(column)
            if forced is not None and answer[column] != forced[vertical_offset]:
                return False
        for offset in range(self.short_columns):
            forced = self.fixed_answers.get(short_slot_start + offset)
            if forced is not None and answer[self.long_columns + offset] != forced[depth]:
                return False
        return True

    def solve(self) -> tuple[SearchResult, dict | None]:
        try:
            result = self._rows(
                stage="top", depth=0,
                long_nodes=(0,) * self.long_columns,
                short_nodes=(0,) * self.short_columns,
                selection=Selection(), top_rows=(), bottom_rows=(),
                top_shorts=(), middle="",
            )
            self._checkpoint(result.value, force=True)
            return result, self.solution
        finally:
            self.cache.close()

    def _rows(
        self, *, stage: str, depth: int, long_nodes: tuple[int, ...],
        short_nodes: tuple[int, ...], selection: Selection,
        top_rows: tuple[str, ...], bottom_rows: tuple[str, ...],
        top_shorts: tuple[str, ...], middle: str,
    ) -> SearchResult:
        self.nodes += 1
        self.last_stage = f"{stage}:{depth}"
        if self._timed_out():
            return SearchResult.CUTOFF
        self._checkpoint()
        all_rows = top_rows + bottom_rows
        state_hash = self._state_hash(stage, depth, long_nodes, short_nodes, selection, all_rows, middle)
        if self._dead_or_cached(state_hash):
            return SearchResult.DEAD

        if depth == 3:
            completed_short = self._complete_nodes(self.short_trie, short_nodes)
            if completed_short is None:
                return self._mark_dead(state_hash)
            short_slot_start = self.long_columns if stage == "top" else 10
            if any(
                not self._answer_is_forced(short_slot_start + offset, record.answer)
                for offset, record in enumerate(completed_short)
            ):
                return self._mark_dead(state_hash)
            after_short = self._add(selection, completed_short)
            if after_short is None:
                return self._mark_dead(state_hash)
            if stage == "top":
                return self._middle(
                    long_nodes=long_nodes, selection=after_short,
                    top_rows=top_rows,
                    top_shorts=tuple(record.answer for record in completed_short),
                )
            completed_long = self._complete_nodes(self.seven_trie, long_nodes)
            if completed_long is None:
                return self._mark_dead(state_hash)
            if any(
                not self._answer_is_forced(slot, record.answer)
                for slot, record in enumerate(completed_long)
            ):
                return self._mark_dead(state_hash)
            final_selection = self._add(after_short, completed_long)
            if final_selection is None:
                return self._mark_dead(state_hash)
            bottom_shorts = tuple(record.answer for record in completed_short)
            verticals = tuple(record.answer for record in completed_long)
            answers = (
                *verticals, *top_shorts, *top_rows, middle,
                *bottom_shorts, *bottom_rows,
            )
            if len(answers) != self.expected_answers or not self._distance_ok(answers):
                return self._mark_dead(state_hash)
            if not self.config.minimum_images <= final_selection.image_count <= self.config.maximum_images:
                return self._mark_dead(state_hash)
            self.solution = self._solution_payload(
                answers, verticals, top_shorts, top_rows, middle, bottom_shorts,
                bottom_rows, final_selection,
            )
            return SearchResult.FOUND

        tries = (self.seven_trie,) * self.long_columns + (self.short_trie,) * self.short_columns
        nodes = long_nodes + short_nodes
        for record in self.six.matching(tries, nodes):
            if not self._row_matches_fixed(stage, depth, record.answer):
                continue
            next_selection = self._add(selection, (record,))
            if next_selection is None:
                continue
            advanced = self._advance_nodes(record.answer, long_nodes, short_nodes)
            if advanced is None:
                continue
            next_long, next_short = advanced
            result = self._rows(
                stage=stage, depth=depth + 1,
                long_nodes=next_long, short_nodes=next_short,
                selection=next_selection,
                top_rows=top_rows + (record.answer,) if stage == "top" else top_rows,
                bottom_rows=bottom_rows + (record.answer,) if stage == "bottom" else bottom_rows,
                top_shorts=top_shorts, middle=middle,
            )
            if result is not SearchResult.DEAD:
                return result
        return self._mark_dead(state_hash)

    def _middle(
        self, *, long_nodes: tuple[int, ...], selection: Selection,
        top_rows: tuple[str, ...], top_shorts: tuple[str, ...],
    ) -> SearchResult:
        self.nodes += 1
        self.last_stage = "middle"
        if self._timed_out():
            return SearchResult.CUTOFF
        state_hash = self._state_hash("middle", 0, long_nodes, (), selection, top_rows)
        if self._dead_or_cached(state_hash):
            return SearchResult.DEAD
        tries = (self.seven_trie,) * self.long_columns
        for record in self.middle.matching(tries, long_nodes):
            if not self._answer_is_forced(9, record.answer):
                continue
            if any(
                (forced := self.fixed_answers.get(column)) is not None
                and record.answer[column] != forced[3]
                for column in range(self.long_columns)
            ):
                continue
            next_selection = self._add(selection, (record,))
            if next_selection is None:
                continue
            next_long = tuple(
                self.seven_trie.advance(node, record.answer[position])
                for position, node in enumerate(long_nodes)
            )
            if any(node is None for node in next_long):
                continue
            result = self._rows(
                stage="bottom", depth=0,
                long_nodes=tuple(int(node) for node in next_long),
                short_nodes=(0,) * self.short_columns,
                selection=next_selection,
                top_rows=top_rows, bottom_rows=(), top_shorts=top_shorts,
                middle=record.answer,
            )
            if result is not SearchResult.DEAD:
                return result
        return self._mark_dead(state_hash)

    def _solution_payload(
        self, answers: Sequence[str], verticals: Sequence[str], top_shorts: Sequence[str],
        top_rows: Sequence[str], middle: str, bottom_shorts: Sequence[str],
        bottom_rows: Sequence[str], selection: Selection,
    ) -> dict:
        score = sum(self.record_by_answer[answer].score for answer in answers)
        return {
            "answers": list(answers),
            "slotAnswers": {str(index): answer for index, answer in enumerate(answers)},
            "score": round(score, 3),
            "imageCount": selection.image_count,
            "grammarCount": selection.grammar_count,
            "unfamiliarCount": selection.unfamiliar_count,
            "verticals": list(verticals),
            "topBand": {"rows": list(top_rows), "shortColumns": list(top_shorts)},
            "middle": middle,
            "bottomBand": {"rows": list(bottom_rows), "shortColumns": list(bottom_shorts)},
            "geometry": ribbon_geometry(self.long_columns, answers),
        }

    def telemetry(self, result: SearchResult) -> dict:
        return {
            "status": result.value,
            "contextHash": self.context_hash,
            "elapsedSeconds": round(time.monotonic() - self.started, 3),
            "nodes": self.nodes,
            "cacheHits": self.cache_hits,
            "loadedDeadStates": self.loaded_dead_states,
            "deadStatesAdded": self.dead_added,
            "deadStateCount": len(self.cache.states),
            "fixedAnswers": {
                str(slot): answer for slot, answer in self.fixed_answers.items()
            },
            "lastStage": self.last_stage,
            "proof": (
                "all structural branches exhausted" if result is SearchResult.DEAD
                else "deadline reached; no infeasibility claim" if result is SearchResult.CUTOFF
                else "exact complete fill"
            ),
        }


def ribbon_geometry(long_columns: int, answers: Sequence[str]) -> dict:
    """Return the 7x8 clue/slot geometry in the solver's stable answer order."""
    short_columns = 6 - long_columns
    clue_cells = [[0, col] for col in range(7)] + [[row, 0] for row in range(1, 8)]
    clue_cells += [[4, col] for col in range(long_columns + 1, 7)]
    slots = []
    answer_index = 0

    def add(direction: str, clue: list[int], cells: list[list[int]]) -> None:
        nonlocal answer_index
        slots.append({
            "slotIndex": answer_index,
            "wordId": f"strict-ribbon:word:{answer_index:02d}",
            "answer": answers[answer_index] if answer_index < len(answers) else "",
            "direction": direction,
            "arrow": "right" if direction == "across" else "down",
            "clueCell": clue,
            "cells": cells,
        })
        answer_index += 1

    for col in range(1, long_columns + 1):
        add("down", [0, col], [[row, col] for row in range(1, 8)])
    for col in range(long_columns + 1, 7):
        add("down", [0, col], [[row, col] for row in range(1, 4)])
    for row in range(1, 4):
        add("across", [row, 0], [[row, col] for col in range(1, 7)])
    add("across", [4, 0], [[4, col] for col in range(1, long_columns + 1)])
    for col in range(long_columns + 1, 7):
        add("down", [4, col], [[row, col] for row in range(5, 8)])
    for row in range(5, 8):
        add("across", [row, 0], [[row, col] for col in range(1, 7)])
    assert answer_index == 19 - long_columns
    assert len(clue_cells) + 36 + long_columns == 56
    return {"columns": 7, "rows": 8, "clueCells": clue_cells, "slots": slots}


def _image_answers() -> set[str]:
    answers = set()
    root = ROOT / "public/assets/clues"
    if root.exists():
        for path in root.rglob("*"):
            if path.suffix.lower() in {".svg", ".png", ".webp"}:
                answer = normalize(path.stem)
                if answer:
                    answers.add(answer)
    return answers


def _load_forbidden() -> tuple[set[str], Counter[str]]:
    blacklist = json.loads((ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8"))
    forbidden = {normalize(item) for item in blacklist.get("rejectedAnswers", [])}
    brief_path = ROOT / "src/data/grid-generation-handcrafted/llm-first-unavailable-answers.json"
    if brief_path.exists():
        brief = json.loads(brief_path.read_text(encoding="utf-8"))
        forbidden.update(normalize(item) for item in brief.get("forbiddenAnswers", []))
    active = Counter()
    catalog = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    active.update(
        normalize(word.get("answer"))
        for grid in catalog.get("grids", []) for word in grid.get("words", [])
    )
    for answer, uses in rotation_cooldown_usage(blacklist).items():
        active[normalize(answer)] = max(active[normalize(answer)], uses)
    return forbidden, active


def load_records(
    *, minimum_zipf: float, minimum_constructor_score: float,
    pilot_safe_short_only: bool, short_minimum_zipf: float = 3.0,
    short_minimum_constructor_score: float = 20.0,
) -> tuple[list[WordRecord], list[WordRecord], list[WordRecord], dict[int, list[WordRecord]], dict]:
    forbidden, active = _load_forbidden()
    images = _image_answers()
    with gzip.open(ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8") as stream:
        entries = json.load(stream).get("entries", [])
    by_answer = {normalize(item.get("answer")): item for item in entries}

    def record(answer: str, item: dict | None = None, base_score: float | None = None) -> WordRecord:
        item = item or {}
        spelling = str(item.get("spelling") or answer).lower()
        zipf = float(zipf_frequency(spelling, "fr"))
        constructor = float(item.get("constructorScore") or 0.0)
        score = base_score if base_score is not None else constructor + 7.0 * zipf
        score -= 12.0 * active.get(answer, 0)
        return WordRecord(
            answer=answer, score=score, zipf=zipf, family=family_key(answer),
            image=answer in images, grammar=answer in GRAMMAR_ANSWERS,
        )

    pools: dict[int, dict[str, WordRecord]] = {3: {}, 4: {}, 5: {}, 6: {}, 7: {}}
    for item in entries:
        answer = normalize(item.get("answer"))
        if len(answer) not in pools or answer in forbidden:
            continue
        pos = item.get("partOfSpeech")
        form = item.get("formType")
        zipf = float(zipf_frequency(str(item.get("spelling") or answer).lower(), "fr"))
        constructor = float(item.get("constructorScore") or 0.0)
        natural_inflection = (
            form == "inflected" and pos in {"common-noun", "adjective"}
            and bool(item.get("attestedCommonForm")) and zipf >= 3.0 and constructor >= 15
        )
        if form != "lemma" and not natural_inflection:
            continue
        if pos not in {"common-noun", "adjective", "adverb", "verb"}:
            continue
        required_zipf = short_minimum_zipf if len(answer) == 3 else minimum_zipf
        required_constructor = (
            short_minimum_constructor_score if len(answer) == 3
            else minimum_constructor_score
        )
        if zipf < required_zipf or constructor < required_constructor:
            continue
        pools[len(answer)][answer] = record(answer, item)

    for answer in POP_LONG:
        answer = normalize(answer)
        if len(answer) in {6, 7} and answer not in forbidden:
            pools[len(answer)][answer] = record(answer, by_answer.get(answer), 95.0)
    safe_short = {
        normalize(answer) for answer in set(PILOT_SAFE_SHORT) | CURRENT_SHORT
        if len(normalize(answer)) == 3
    }
    pools[3] = {
        answer: record(answer, by_answer.get(answer), 70.0 if answer in CURRENT_SHORT else None)
        for answer in safe_short
        if answer not in forbidden and answer not in SENSITIVE_SHORT and answer not in GRAMMAR_ANSWERS
        and (not pilot_safe_short_only or answer in safe_short)
    } if pilot_safe_short_only else {
        **pools[3],
        **{
            answer: record(answer, by_answer.get(answer), 70.0 if answer in CURRENT_SHORT else None)
            for answer in safe_short
            if answer not in forbidden and answer not in SENSITIVE_SHORT and answer not in GRAMMAR_ANSWERS
        },
    }
    for answer in {"DOFUS", "MARIO"}:
        if answer not in forbidden:
            pools[5][answer] = record(answer, by_answer.get(answer), 95.0)

    result = {length: list(records.values()) for length, records in pools.items()}
    summary = {
        str(length): len(records) for length, records in result.items()
    }
    return result[6], result[7], result[3], {3: result[3], 4: result[4], 5: result[5]}, summary


def extract_avoid_fills(paths: Sequence[Path], expected: int) -> list[list[str]]:
    fills: list[list[str]] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            slot_answers = value.get("slotAnswers")
            if isinstance(slot_answers, dict):
                try:
                    ordered = [normalize(slot_answers[str(index)]) for index in range(expected)]
                except (KeyError, TypeError):
                    ordered = []
                if len(ordered) == expected and all(ordered):
                    fills.append(ordered)
            answers = value.get("answers")
            if isinstance(answers, list) and len(answers) == expected:
                normalized = [normalize(item.get("answer") if isinstance(item, dict) else item) for item in answers]
                if all(normalized):
                    fills.append(normalized)
            for child in value.values():
                if isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for path in paths:
        if path.exists():
            visit(json.loads(path.read_text(encoding="utf-8")))
    unique = []
    seen = set()
    for fill in fills:
        key = tuple(fill)
        if key not in seen:
            seen.add(key)
            unique.append(fill)
    return unique


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shape-id", choices=tuple(SHAPES), default="pilot-7x8-strict-02")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--minimum-zipf", type=float, default=2.0)
    parser.add_argument("--minimum-constructor-score", type=float, default=5.0)
    parser.add_argument("--short-minimum-zipf", type=float, default=3.0)
    parser.add_argument("--short-minimum-constructor-score", type=float, default=20.0)
    parser.add_argument("--minimum-familiarity-zipf", type=float, default=3.0)
    parser.add_argument("--maximum-unfamiliar-answers", type=int, default=2)
    parser.add_argument("--pilot-safe-short-only", action="store_true")
    parser.add_argument("--minimum-images", type=int, default=0)
    parser.add_argument("--maximum-images", type=int, default=6)
    parser.add_argument("--maximum-grammar-answers", type=int, default=1)
    parser.add_argument("--avoid-fill", action="append", type=Path, default=[])
    parser.add_argument("--minimum-solution-distance", type=int, default=1)
    parser.add_argument(
        "--fixed-answer",
        action="append",
        type=parse_fixed_answer,
        default=[],
        metavar="SLOT:MOT",
        help="Impose une réponse dans l'ordre stable de solution_payload",
    )
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    long_columns = SHAPES[args.shape_id]
    six, seven, short, middle_by_length, pool_counts = load_records(
        minimum_zipf=args.minimum_zipf,
        minimum_constructor_score=args.minimum_constructor_score,
        pilot_safe_short_only=args.pilot_safe_short_only,
        short_minimum_zipf=args.short_minimum_zipf,
        short_minimum_constructor_score=args.short_minimum_constructor_score,
    )
    expected = 19 - long_columns
    avoid = extract_avoid_fills(args.avoid_fill, expected)
    try:
        fixed_answers = validate_fixed_answers(
            args.fixed_answer,
            long_columns=long_columns,
            six=six,
            seven=seven,
            short=short,
            middle=middle_by_length[long_columns],
        )
    except ValueError as error:
        raise SystemExit(f"Réponse imposée invalide : {error}") from error
    config = SearchConfig(
        long_columns=long_columns,
        seconds=args.seconds,
        minimum_images=args.minimum_images,
        maximum_images=args.maximum_images,
        maximum_grammar_answers=args.maximum_grammar_answers,
        minimum_familiarity_zipf=args.minimum_familiarity_zipf,
        maximum_unfamiliar_answers=args.maximum_unfamiliar_answers,
        minimum_solution_distance=args.minimum_solution_distance,
        checkpoint=args.checkpoint,
    )
    solver = RibbonRowSolver(
        six=six, seven=seven, short=short, middle=middle_by_length[long_columns],
        config=config, seed=args.seed, avoid_fills=avoid, cache_path=args.cache,
        fixed_answers=fixed_answers,
    )
    result, solution = solver.solve()
    payload = {
        "version": 1,
        "kind": "motman-strict-ribbon-row-dfs",
        "shapeId": args.shape_id,
        "longColumns": long_columns,
        "catalogModified": False,
        "publicationEligible": False,
        "poolCounts": pool_counts,
        "avoidFillCount": len(avoid),
        "fixedAnswers": {str(slot): answer for slot, answer in fixed_answers.items()},
        "telemetry": solver.telemetry(result),
        "solution": solution,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output), "status": result.value,
        "poolCounts": pool_counts, **payload["telemetry"],
    }, ensure_ascii=False, indent=2))
    return 0 if result is SearchResult.FOUND else 2 if result is SearchResult.DEAD else 3


if __name__ == "__main__":
    raise SystemExit(main())
