"""Exact separator search for the immutable reference-ribbon-a-01 shape.

The five 9-letter columns are the separator.  The upper component fixes their
four-letter prefixes; complete 9-letter corpus answers then fix five-letter
suffixes.  The lower component is closed with bitsets over the four remaining
8-letter rows.  No path, letter, or answer fragment is ever synthesized.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagnose_fixed_shape_corpus_gaps import (  # noqa: E402
    DEFAULT_SHAPES,
    load_expansion_words,
    load_shape,
    load_words,
)
from grid_topology import audit_grid_topology  # noqa: E402


SHAPE_ID = "reference-ribbon-a-01"
OUTPUT = ROOT / "output/quality/agent-b-ribbon-a01-fill.json"
TARGET_LENGTHS = (9, 9, 9, 3, 4, 9, 9, 3)
LONG_COLUMNS = (0, 1, 2, 5, 6)
LONG_SLOT_BY_COLUMN = {0: 0, 1: 1, 2: 2, 5: 5, 6: 6}
FIXED_HUMAN_TOP = None
FIXED_SLOT0 = "IDEOLOGIE"
NO_GOODS = {
    "DECREPANT", "ECRAMINER", "IEME", "ETIGEATES", "TTE", "IDEAIENT",
    "DECRETAT", "ECRAMINE", "ORA", "EGO", "LEMS", "OPIACAIS",
    "GANSETTE", "ETRESSES",
}
HUMAN_PREFERENCES = {FIXED_SLOT0}
BLACKLIST_PATH = ROOT / "src/data/editorial.blacklist.json"
LEXIQUE_PATH = ROOT / "src/data/lexique.lemmas.json"


def bit_indexes(bits: int):
    while bits:
        least = bits & -bits
        yield least.bit_length() - 1
        bits ^= least


class SeparatorSolver:
    def __init__(self, words, metadata, canonical, slots, *, seconds: float, seed: int):
        self.words = words
        self.metadata = metadata
        self.canonical = canonical
        self.slots = slots
        self.seed = seed
        self.rng = random.Random(seed)
        self.started = time.monotonic()
        self.deadline = self.started + seconds
        self.timed_out = False
        self.counts = Counter()
        self.max_top_depth = 0
        self.max_bottom_depth = 0
        self.best_partial = {}

        self.word_sets = {length: set(words[length]) for length in (3, 4, 5, 8, 9)}
        self.prefix_next = {}
        self.prefix_words = {}
        for length in (3, 4, 5, 9):
            next_letters = defaultdict(set)
            completions = defaultdict(list)
            for word in words[length]:
                for size in range(length):
                    next_letters[word[:size]].add(word[size])
                for size in (2, 3, 4):
                    if size <= length:
                        completions[word[:size]].append(word)
            self.prefix_next[length] = dict(next_letters)
            self.prefix_words[length] = dict(completions)

        self.w8 = words[8]
        self.w8_index = {word: index for index, word in enumerate(self.w8)}
        if FIXED_SLOT0 not in words[9]:
            raise ValueError(f"ancre propriétaire absente du pool humain: {FIXED_SLOT0}")
        self.all8 = (1 << len(self.w8)) - 1
        self.masks8 = [[0] * 26 for _ in range(8)]
        for index, word in enumerate(self.w8):
            bit = 1 << index
            for position, letter in enumerate(word):
                self.masks8[position][ord(letter) - 65] |= bit
        self.reviewed8 = 0
        self.preferred8 = 0
        for index, word in enumerate(self.w8):
            if word in canonical:
                self.reviewed8 |= 1 << index
            if word in HUMAN_PREFERENCES:
                self.preferred8 |= 1 << index

        self.w3 = words[3]
        self.all3 = (1 << len(self.w3)) - 1
        self.masks3 = [[0] * 26 for _ in range(3)]
        for index, word in enumerate(self.w3):
            bit = 1 << index
            for position, letter in enumerate(word):
                self.masks3[position][ord(letter) - 65] |= bit

        # A deterministic but editorially useful order.  It remains complete:
        # the order changes, never the domain.
        noise = {word: self.rng.random() for word in self.w8}
        self.first_row_order = sorted(
            bit_indexes(self.masks8[0][ord(FIXED_SLOT0[0]) - 65]),
            key=lambda index: (
                0 if self.w8[index] in canonical else 1,
                -float(metadata[self.w8[index]].get("sourceFrequency", 0) or 0),
                noise[self.w8[index]],
            ),
        )

    def expired(self) -> bool:
        if time.monotonic() >= self.deadline:
            self.timed_out = True
        return self.timed_out

    @staticmethod
    def union_masks(masks, position: int, letters) -> int:
        result = 0
        for letter in letters:
            result |= masks[position][ord(letter) - 65]
        return result

    def ordered8(self, domain: int):
        # Owner-human preferences first, then reviewed answers, then every
        # remaining structural answer. The three sets still cover the whole
        # domain exactly once.
        yield from bit_indexes(domain & self.preferred8)
        domain &= ~self.preferred8
        yield from bit_indexes(domain & self.reviewed8)
        yield from bit_indexes(domain & ~self.reviewed8)

    def next_row_domain(self, prefixes: list[str]) -> int:
        domain = self.all8
        for position, (prefix, length) in enumerate(zip(prefixes, TARGET_LENGTHS)):
            letters = self.prefix_next[length].get(prefix)
            if not letters:
                return 0
            domain &= self.union_masks(self.masks8, position, letters)
            if not domain:
                return 0
        return domain

    def small_across_domain(self, prefixes: tuple[str, str, str], lengths: tuple[int, int, int]) -> int:
        domain = self.all3
        for position, (prefix, length) in enumerate(zip(prefixes, lengths)):
            letters = self.prefix_next[length].get(prefix)
            if not letters:
                return 0
            domain &= self.union_masks(self.masks3, position, letters)
            if not domain:
                return 0
        return domain

    def restrict_bottom_rows(self, domains: tuple[int, ...], column: int, word9: str):
        revised = []
        for row_offset, domain in enumerate(domains):
            letter = word9[5 + row_offset]
            domain &= self.masks8[column][ord(letter) - 65]
            if not domain:
                self.counts[f"bottom-domain-empty-column-{column}"] += 1
                return None
            revised.append(domain)
        return tuple(revised)

    def close_bottom_rows(
        self,
        row_index: int,
        base_domains: tuple[int, ...],
        prefix3: str,
        prefix4: str,
        prefix7: str,
        used: set[str],
        chosen_rows: list[str],
    ):
        self.max_bottom_depth = max(self.max_bottom_depth, row_index)
        if self.expired():
            return None
        if row_index == 4:
            if (
                prefix3 not in self.word_sets[5]
                or prefix4 not in self.word_sets[4]
                or prefix7 not in self.word_sets[5]
            ):
                self.counts["bottom-terminal-column-reject"] += 1
                return None
            if len({prefix3, prefix4, prefix7, *chosen_rows}) != 7:
                self.counts["bottom-duplicate-reject"] += 1
                return None
            return chosen_rows[:], prefix3, prefix4, prefix7

        domain = base_domains[row_index]
        for column, prefix, length in ((3, prefix3, 5), (4, prefix4, 4), (7, prefix7, 5)):
            letters = self.prefix_next[length].get(prefix)
            if not letters:
                self.counts[f"bottom-prefix-empty-length-{length}"] += 1
                return None
            domain &= self.union_masks(self.masks8, column, letters)
            if not domain:
                self.counts[f"bottom-row-{row_index + 6}-empty"] += 1
                return None
        row_candidates = list(self.ordered8(domain))
        row_candidates.sort(key=lambda word_index: (
            0 if self.w8[word_index] in HUMAN_PREFERENCES else 1,
            0 if self.w8[word_index] in self.canonical else 1,
            self.w8[word_index],
        ))
        for word_index in row_candidates:
            self.counts["bottom-row-candidates"] += 1
            word = self.w8[word_index]
            if word in used or word in chosen_rows:
                self.counts["bottom-row-duplicate-skip"] += 1
                continue
            chosen_rows.append(word)
            result = self.close_bottom_rows(
                row_index + 1,
                base_domains,
                prefix3 + word[3],
                prefix4 + word[4],
                prefix7 + word[7],
                used,
                chosen_rows,
            )
            if result is not None:
                return result
            chosen_rows.pop()
            if self.timed_out:
                return None
        return None

    def close_bottom(self, long_prefixes: dict[int, str], top: dict[int, str]):
        completion_lists = {
            column: self.prefix_words[9].get(prefix, [])
            for column, prefix in long_prefixes.items()
        }
        completion_lists[0] = [
            answer for answer in completion_lists[0] if answer == FIXED_SLOT0
        ]
        if any(not values for values in completion_lists.values()):
            self.counts["long-prefix-domain-empty"] += 1
            return None

        chosen_long = {}
        initial_domains = (self.all8,) * 4
        top_used = set(top.values())

        def select_long(depth: int, domains: tuple[int, ...]):
            if self.expired():
                return None
            if depth == len(LONG_COLUMNS):
                left_prefix = "".join(chosen_long[column][4] for column in (0, 1, 2))
                right_prefix = "".join(chosen_long[column][4] for column in (5, 6))
                left_words = sorted(
                    self.prefix_words[4].get(left_prefix, []),
                    key=lambda answer: (
                        0 if answer in HUMAN_PREFERENCES else 1,
                        0 if answer in self.canonical else 1,
                        answer,
                    ),
                )
                right_words = sorted(
                    self.prefix_words[3].get(right_prefix, []),
                    key=lambda answer: (
                        0 if answer in HUMAN_PREFERENCES else 1,
                        0 if answer in self.canonical else 1,
                        answer,
                    ),
                )
                if not left_words:
                    self.counts["row5-left-domain-empty"] += 1
                    return None
                if not right_words:
                    self.counts["row5-right-domain-empty"] += 1
                    return None
                used = top_used | set(chosen_long.values())
                for left in left_words:
                    if left in used:
                        continue
                    for right in right_words:
                        if right in used or right == left:
                            continue
                        self.counts["bottom-separator-completions"] += 1
                        closed = self.close_bottom_rows(
                            0, domains, left[3], "", right[2], used | {left, right}, []
                        )
                        if closed is None:
                            if self.timed_out:
                                return None
                            continue
                        rows, down3, down4, down7 = closed
                        result = dict(top)
                        for column, answer in chosen_long.items():
                            result[LONG_SLOT_BY_COLUMN[column]] = answer
                        result[13] = down3
                        result[14] = down7
                        result[15] = left
                        result[16] = right
                        result[17] = down4
                        for offset, answer in enumerate(rows):
                            result[18 + offset] = answer
                        if len(result) == 22 and len(set(result.values())) == 22:
                            return result
                        self.counts["final-distinctness-reject"] += 1
                return None

            column = LONG_COLUMNS[depth]
            candidates = []
            for answer in completion_lists[column]:
                if answer in top_used or answer in chosen_long.values():
                    continue
                revised = self.restrict_bottom_rows(domains, column, answer)
                if revised is not None:
                    candidates.append((sum(value.bit_count() for value in revised), answer, revised))
            # Preserve broad row support first; this is ordering only.
            candidates.sort(
                key=lambda item: (
                    0 if item[1] in HUMAN_PREFERENCES else 1,
                    0 if item[1] in self.canonical else 1,
                    -item[0],
                )
            )
            if not candidates:
                self.counts[f"long-column-{column}-domain-empty"] += 1
                return None
            for _support, answer, revised in candidates:
                self.counts["long-answer-branches"] += 1
                chosen_long[column] = answer
                result = select_long(depth + 1, revised)
                if result is not None:
                    return result
                chosen_long.pop(column, None)
                if self.timed_out:
                    return None
            return None

        return select_long(0, initial_domains)

    def solve(self):
        for first_index in self.first_row_order:
            if self.expired():
                break
            first = self.w8[first_index]
            self.counts["top-row1"] += 1
            second_domain = self.next_row_domain(list(first))
            second_domain &= self.masks8[0][ord(FIXED_SLOT0[1]) - 65]
            if not second_domain:
                self.counts["top-row2-domain-empty"] += 1
                continue
            for second_index in self.ordered8(second_domain):
                if self.expired():
                    break
                second = self.w8[second_index]
                if second == first:
                    continue
                self.counts["top-row2"] += 1
                third_domain = self.next_row_domain([
                    first[position] + second[position] for position in range(8)
                ])
                third_domain &= self.masks8[0][ord(FIXED_SLOT0[2]) - 65]
                if not third_domain:
                    self.counts["top-row3-domain-empty"] += 1
                    continue
                for third_index in self.ordered8(third_domain):
                    if self.expired():
                        break
                    third = self.w8[third_index]
                    if third in {first, second}:
                        continue
                    self.counts["top-row3"] += 1
                    prefixes3 = tuple(
                        first[position] + second[position] + third[position]
                        for position in range(8)
                    )
                    left_domain = self.small_across_domain(
                        prefixes3[0:3], (9, 9, 9)
                    )
                    left_domain &= self.masks3[0][ord(FIXED_SLOT0[3]) - 65]
                    if not left_domain:
                        self.counts["row4-left-domain-empty"] += 1
                        continue
                    right_domain = self.small_across_domain(
                        (prefixes3[4], prefixes3[5], prefixes3[6]), (4, 9, 9)
                    )
                    if not right_domain:
                        self.counts["row4-right-domain-empty"] += 1
                        continue
                    small_down3 = prefixes3[3]
                    small_down7 = prefixes3[7]
                    row4_pairs = []
                    for left_index in bit_indexes(left_domain):
                        left = self.w3[left_index]
                        for right_index in bit_indexes(right_domain):
                            right = self.w3[right_index]
                            down4 = prefixes3[4] + right[0]
                            known = {first, second, third, left, right, small_down3, small_down7, down4}
                            if len(known) != 8:
                                self.counts["top-duplicate-reject"] += 1
                                continue
                            long_prefixes = {
                                0: prefixes3[0] + left[0],
                                1: prefixes3[1] + left[1],
                                2: prefixes3[2] + left[2],
                                5: prefixes3[5] + right[1],
                                6: prefixes3[6] + right[2],
                            }
                            cost = 1
                            for prefix in long_prefixes.values():
                                cost *= len(self.prefix_words[9].get(prefix, ()))
                            row4_pairs.append((cost, left, right, down4, long_prefixes))
                    row4_pairs.sort(key=lambda item: (
                        0 if item[1] in HUMAN_PREFERENCES else 1,
                        0 if item[2] in HUMAN_PREFERENCES else 1,
                        item[0],
                    ))
                    for _cost, left, right, down4, long_prefixes in row4_pairs:
                        self.counts["top-components"] += 1
                        top = {
                            3: small_down3,
                            4: down4,
                            7: small_down7,
                            8: first,
                            9: second,
                            10: third,
                            11: left,
                            12: right,
                        }
                        self.best_partial = top
                        result = self.close_bottom(long_prefixes, top)
                        if result is not None:
                            return result
                        if self.timed_out:
                            break
        return None

    def telemetry(self):
        return {
            "engine": "exact-five-column-separator-mitm-bitset",
            "elapsedSeconds": round(time.monotonic() - self.started, 3),
            "reason": "timeout" if self.timed_out else "exhausted",
            "seed": self.seed,
            "noBranchCaps": True,
            "fiveNineLetterColumnsAsSeparator": list(LONG_COLUMNS),
            "fixedHumanTop": None,
            "fixedSlot0": FIXED_SLOT0,
            "noGoods": sorted(NO_GOODS),
            "humanPreferences": sorted(HUMAN_PREFERENCES),
            "counters": dict(sorted(self.counts.items())),
            "maxBottomRowsClosed": self.max_bottom_depth,
            "bestPartial": [
                {"slotIndex": index, "slotId": self.slots[index].slot_id, "answer": answer}
                for index, answer in sorted(self.best_partial.items())
            ],
        }


def provenance(answer: str, metadata: dict, canonical: dict) -> dict:
    source = canonical.get(answer)
    if source is not None:
        return {
            "reviewTier": "central-reviewed-or-source-backed",
            "clue": source.get("clue", ""),
            "sourceId": source.get("sourceId"),
            "sourceUrl": source.get("sourceUrl"),
            "sourceType": source.get("sourceType"),
            "editorialStatus": source.get("editorialStatus"),
        }
    source = metadata[answer]
    return {
        "reviewTier": "structural-only-owner-review-required",
        "sourceId": source.get("sourceId") or source.get("source"),
        "partOfSpeech": source.get("partOfSpeech"),
        "formType": source.get("formType"),
        "lemmaAnswer": source.get("lemmaAnswer"),
        "editorialStatus": "unreviewed-structural",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=105.0)
    parser.add_argument("--seed", type=int, default=717221)
    args = parser.parse_args()

    shape, slots = load_shape(DEFAULT_SHAPES, SHAPE_ID)
    _central_words, canonical = load_words()
    words, metadata, corpus_stats = load_expansion_words(
        canonical, include_morphalou=False
    )
    blacklist = json.loads(BLACKLIST_PATH.read_text(encoding="utf-8"))
    rejected_answers = set(blacklist.get("rejectedAnswers", []))
    cooldown_answers = {
        item["answer"]
        for item in blacklist.get("rotationCooldownAnswers", [])
        if isinstance(item, dict) and item.get("answer")
    }
    lexique = json.loads(LEXIQUE_PATH.read_text(encoding="utf-8"))
    lexique_by_answer = {
        entry["answer"]: entry for entry in lexique.get("entries", [])
    }
    mutable_words = {length: set(answers) for length, answers in words.items()}
    cooldown_reintroduced = []
    for answer in sorted(cooldown_answers):
        entry = lexique_by_answer.get(answer) or canonical.get(answer)
        if (
            entry is None
            or answer in rejected_answers
            or answer in NO_GOODS
            or len(answer) not in {3, 4, 5, 8, 9}
        ):
            continue
        mutable_words.setdefault(len(answer), set()).add(answer)
        metadata.setdefault(answer, entry)
        cooldown_reintroduced.append(answer)
    words = {
        length: tuple(sorted(answer for answer in answers if answer not in NO_GOODS))
        for length, answers in mutable_words.items()
    }
    corpus_stats["rotationCooldownReintroduced"] = len(cooldown_reintroduced)
    corpus_stats["rotationCooldownAnswersReintroduced"] = cooldown_reintroduced
    corpus_stats["exclusionPolicyForThisRun"] = {
        "rejectedAnswers": len(rejected_answers),
        "artificialNoGoods": sorted(NO_GOODS),
        "rotationCooldownIsNotLexicalRejection": True,
    }
    solver = SeparatorSolver(
        words, metadata, canonical, slots, seconds=args.seconds, seed=args.seed
    )
    solution = solver.solve()
    telemetry = solver.telemetry()
    payload = {
        "version": 2,
        "kind": "agent-b-fixed-ribbon-a01-exact-separator-search",
        "generatedOn": str(date.today()),
        "shapeId": SHAPE_ID,
        "shapeModified": False,
        "catalogModified": False,
        "interfaceModified": False,
        "dimensions": {"columns": shape["columns"], "rows": shape["rows"]},
        "slotCount": len(slots),
        "fixedClueCells": shape["clueCells"],
        "corpusMetrics": {
            **corpus_stats,
            "countsByRequiredLength": {
                str(length): len(words[length]) for length in (3, 4, 5, 8, 9)
            },
        },
        "solverTelemetry": telemetry,
        "status": "complete-structural-owner-review-required" if solution else (
            "infeasible-exact-shape" if telemetry["reason"] == "exhausted"
            else "unresolved-time-limit"
        ),
        "publicationEligible": False,
    }
    if solution is None:
        payload["solution"] = None
        payload["blockingConclusion"] = (
            "Recherche exacte non fermée dans la limite; les compteurs donnent les domaines vides observés."
            if telemetry["reason"] == "timeout"
            else "Tous les domaines structurels filtrés ont été épuisés sans fermeture."
        )
    else:
        words_out = []
        for index, slot in enumerate(slots):
            answer = solution[index]
            words_out.append({
                "wordId": f"agent-b-ribbon-a01:word:{index + 1:02d}",
                "answer": answer,
                "clue": canonical.get(answer, {}).get("clue", ""),
                "direction": slot.direction,
                "arrow": shape["slots"][index]["arrow"],
                "clueCell": list(slot.clue_cell),
                "cells": [list(cell) for cell in slot.cells],
                "provenance": provenance(answer, metadata, canonical),
            })
        grid = {
            "id": "agent-b-ribbon-a01-structural",
            "columns": shape["columns"],
            "rows": shape["rows"],
            "clueCells": shape["clueCells"],
            "words": words_out,
            "publicationStatus": "owner-review-required",
        }
        audit = audit_grid_topology(grid, require_word_ids=True, enforce_layout=False)
        payload["solution"] = grid
        payload["topologyAudit"] = audit
        payload["answerCount"] = len(solution)
        payload["distinctAnswerCount"] = len(set(solution.values()))
        payload["unreviewedAnswers"] = [
            answer for answer in solution.values() if answer not in canonical
        ]
        if not audit["valid"] or len(solution) != 22 or len(set(solution.values())) != 22:
            payload["status"] = "rejected-strict-audit"

    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT),
        "status": payload["status"],
        "solverTelemetry": telemetry,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
