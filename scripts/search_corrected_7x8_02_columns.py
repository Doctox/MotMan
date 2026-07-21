#!/usr/bin/env python3
"""Column-induced exact search for ``corrected-7x8-02``.

Five seven-letter columns induce seven five-letter row prefixes.  Rows 1-3
and 5-7 must extend to accepted six-letter words; row 4 must itself be an
accepted five-letter word.  The six extension letters form one accepted
three-letter word above the pivot and another below it.

The script only emits structural candidates for human review.  It never
publishes a grid or invents a definition.
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from build_compact_7x8_review import family_key
from strict_ribbon_row_dfs import (
    PrefixTrie,
    SearchResult,
    WordDomain,
    WordRecord,
    _load_forbidden,
    load_records,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHAPE_LIBRARY = (
    ROOT / "output/quality/corrected-7x8-shapes/corrected-shape-library.json"
)
SHAPE_ID = "corrected-7x8-02"


@dataclass(frozen=True)
class SearchPolicy:
    seconds: float = 120.0
    solution_limit: int = 12
    minimum_solution_distance: int = 4
    minimum_familiarity_zipf: float = 3.0
    maximum_unfamiliar_answers: int = 3
    maximum_grammar_answers: int = 1
    maximum_active_answers: int = 0


@dataclass(frozen=True)
class PartialSelection:
    answers: frozenset[str] = frozenset()
    families: frozenset[str] = frozenset()
    unfamiliar: int = 0
    grammar: int = 0
    active: int = 0


class CorrectedShape02ColumnSearch:
    def __init__(
        self,
        *,
        six: Sequence[WordRecord],
        seven: Sequence[WordRecord],
        short: Sequence[WordRecord],
        five: Sequence[WordRecord],
        active_usage: Counter[str] | None = None,
        policy: SearchPolicy = SearchPolicy(),
        seed: int = 20260721,
        shape: dict | None = None,
    ) -> None:
        self.policy = policy
        self.started = time.monotonic()
        self.deadline = self.started + max(0.0, policy.seconds)
        self.active_usage = active_usage or Counter()
        self.six_by_answer = {record.answer: record for record in six}
        self.five_by_answer = {record.answer: record for record in five}
        self.short = tuple(sorted(
            short,
            key=lambda record: (-record.score, record.answer),
        ))
        self.seven_domain = WordDomain(seven, seed)
        self.six_trie = PrefixTrie(self.six_by_answer)
        self.five_trie = PrefixTrie(self.five_by_answer)
        self.record_by_answer = {
            record.answer: record
            for records in (six, seven, short, five)
            for record in records
        }
        self.shape = shape
        self.candidates: list[dict] = []
        self.candidate_keys: set[tuple[str, ...]] = set()
        self.nodes = 0
        self.complete_prefixes = 0
        self.extension_pairs_checked = 0
        self.maximum_depth = 0
        self.depth_visits = Counter()
        self.domain_sizes = defaultdict(list)
        self.rejections = Counter()
        self.prefix_diagnostics: list[dict] = []
        self.timed_out = False
        self.stop_reason = "not-started"
        # If the same five-letter prefix has several metadata records, the
        # spelling still identifies exactly one horizontal answer.
        self.topology_expected_lengths = (7, 7, 7, 7, 7, 3, 6, 6, 6, 5, 3, 6, 6, 6)

    def _add(
        self, selection: PartialSelection, records: Iterable[WordRecord]
    ) -> PartialSelection | None:
        answers = set(selection.answers)
        families = set(selection.families)
        unfamiliar = selection.unfamiliar
        grammar = selection.grammar
        active = selection.active
        for record in records:
            if record.answer in answers:
                self.rejections["duplicate-answer"] += 1
                return None
            if record.family in families:
                self.rejections["duplicate-family"] += 1
                return None
            answers.add(record.answer)
            families.add(record.family)
            unfamiliar += int(record.zipf < self.policy.minimum_familiarity_zipf)
            grammar += int(record.grammar)
            active += int(self.active_usage.get(record.answer, 0) > 0)
        if unfamiliar > self.policy.maximum_unfamiliar_answers:
            self.rejections["too-many-unfamiliar"] += 1
            return None
        if grammar > self.policy.maximum_grammar_answers:
            self.rejections["too-many-grammar"] += 1
            return None
        if active > self.policy.maximum_active_answers:
            self.rejections["active-answer"] += 1
            return None
        return PartialSelection(
            frozenset(answers), frozenset(families), unfamiliar, grammar, active
        )

    def solve(self) -> tuple[SearchResult, list[dict]]:
        if self.policy.seconds <= 0:
            self.stop_reason = "deadline"
            self.timed_out = True
            return SearchResult.CUTOFF, []
        tries = (
            self.six_trie, self.six_trie, self.six_trie,
            self.five_trie,
            self.six_trie, self.six_trie, self.six_trie,
        )
        self.stop_reason = "searching"
        completed = self._columns(
            depth=0,
            row_nodes=(0, 0, 0, 0, 0, 0, 0),
            verticals=(),
            selection=PartialSelection(),
            tries=tries,
        )
        if self.candidates:
            self.stop_reason = (
                "solution-limit" if len(self.candidates) >= self.policy.solution_limit
                else "deadline-after-solutions" if self.timed_out
                else "exhausted-after-solutions"
            )
            return SearchResult.FOUND, self.candidates
        if self.timed_out:
            self.stop_reason = "deadline"
            return SearchResult.CUTOFF, []
        self.stop_reason = "exhausted"
        return SearchResult.DEAD if completed else SearchResult.CUTOFF, []

    def _columns(
        self,
        *,
        depth: int,
        row_nodes: tuple[int, ...],
        verticals: tuple[str, ...],
        selection: PartialSelection,
        tries: tuple[PrefixTrie, ...],
    ) -> bool:
        self.nodes += 1
        self.depth_visits[depth] += 1
        self.maximum_depth = max(self.maximum_depth, depth)
        if time.monotonic() >= self.deadline:
            self.timed_out = True
            return False
        if len(self.candidates) >= self.policy.solution_limit:
            return False
        if depth == 5:
            self.complete_prefixes += 1
            self._close_prefixes(row_nodes, verticals, selection)
            return True

        domain = self.seven_domain.matching(tries, row_nodes)
        domain_records = tuple(domain)
        self.domain_sizes[depth].append(len(domain_records))
        fully_explored = True
        for record in domain_records:
            next_selection = self._add(selection, (record,))
            if next_selection is None:
                continue
            next_nodes = []
            for row, trie in enumerate(tries):
                child = trie.advance(row_nodes[row], record.answer[row])
                if child is None:
                    break
                next_nodes.append(child)
            if len(next_nodes) != 7:
                continue
            child_explored = self._columns(
                depth=depth + 1,
                row_nodes=tuple(next_nodes),
                verticals=verticals + (record.answer,),
                selection=next_selection,
                tries=tries,
            )
            fully_explored &= child_explored
            if self.timed_out or len(self.candidates) >= self.policy.solution_limit:
                return False
        return fully_explored

    def _close_prefixes(
        self,
        row_nodes: tuple[int, ...],
        verticals: tuple[str, ...],
        selection: PartialSelection,
    ) -> None:
        prefixes = tuple(
            (self.five_trie if row == 3 else self.six_trie).prefix[node]
            for row, node in enumerate(row_nodes)
        )
        middle = self.five_by_answer.get(prefixes[3])
        if middle is None:
            self.rejections["missing-middle"] += 1
            return
        with_middle = self._add(selection, (middle,))
        if with_middle is None:
            return

        top_options = []
        bottom_options = []
        for short_record in self.short:
            top_rows = tuple(
                self.six_by_answer.get(prefixes[row] + short_record.answer[row])
                for row in range(3)
            )
            if all(top_rows):
                top_options.append((short_record, top_rows))
            bottom_rows = tuple(
                self.six_by_answer.get(prefixes[row + 4] + short_record.answer[row])
                for row in range(3)
            )
            if all(bottom_rows):
                bottom_options.append((short_record, bottom_rows))
        if not top_options:
            self.rejections["no-top-short-extension"] += 1
            self._record_prefix_diagnostic(prefixes, verticals, "top")
            return
        if not bottom_options:
            self.rejections["no-bottom-short-extension"] += 1
            self._record_prefix_diagnostic(prefixes, verticals, "bottom")
            return

        for top_short, top_rows in top_options:
            after_top = self._add(with_middle, (top_short, *top_rows))
            if after_top is None:
                continue
            for bottom_short, bottom_rows in bottom_options:
                self.extension_pairs_checked += 1
                final = self._add(after_top, (bottom_short, *bottom_rows))
                if final is None:
                    continue
                answers = (
                    *verticals,
                    top_short.answer,
                    *(record.answer for record in top_rows),
                    middle.answer,
                    bottom_short.answer,
                    *(record.answer for record in bottom_rows),
                )
                if any(
                    sum(left != right for left, right in zip(answers, existing["answers"]))
                    < self.policy.minimum_solution_distance
                    for existing in self.candidates
                ):
                    self.rejections["too-close-to-kept-candidate"] += 1
                    continue
                key = tuple(answers)
                if key in self.candidate_keys:
                    self.rejections["duplicate-fill"] += 1
                    continue
                self.candidate_keys.add(key)
                self.candidates.append(self._candidate_payload(
                    answers=answers,
                    verticals=verticals,
                    top_short=top_short,
                    top_rows=top_rows,
                    middle=middle,
                    bottom_short=bottom_short,
                    bottom_rows=bottom_rows,
                    selection=final,
                ))
                if len(self.candidates) >= self.policy.solution_limit:
                    return

    def _record_prefix_diagnostic(
        self, prefixes: tuple[str, ...], verticals: tuple[str, ...], failed_band: str,
    ) -> None:
        """Expose the exact three-letter strings needed by a near closure."""

        bands = {"top": (0, 1, 2), "bottom": (4, 5, 6)}
        details = {}
        accepted_short = {record.answer for record in self.short}
        for name, row_indexes in bands.items():
            options_by_row = []
            for row in row_indexes:
                choices = sorted(
                    record.answer
                    for record in self.six_by_answer.values()
                    if record.answer.startswith(prefixes[row])
                )
                options_by_row.append(choices)
            required = sorted({
                "".join(words[index][-1] for index in range(3))
                for words in itertools.product(*options_by_row)
            }) if all(options_by_row) else []
            details[name] = {
                "rowPrefixes": [prefixes[row] for row in row_indexes],
                "rowCompletionCounts": [len(options) for options in options_by_row],
                "requiredShortCount": len(required),
                "requiredShorts": required[:200],
                "acceptedRequiredShorts": [answer for answer in required if answer in accepted_short],
            }
        self.prefix_diagnostics.append({
            "failedBand": failed_band,
            "verticals": list(verticals),
            "rowPrefixes": list(prefixes),
            "middle": prefixes[3],
            "bands": details,
        })

    def _candidate_payload(
        self,
        *,
        answers: tuple[str, ...],
        verticals: tuple[str, ...],
        top_short: WordRecord,
        top_rows: tuple[WordRecord, ...],
        middle: WordRecord,
        bottom_short: WordRecord,
        bottom_rows: tuple[WordRecord, ...],
        selection: PartialSelection,
    ) -> dict:
        records = [self.record_by_answer[answer] for answer in answers]
        matrix = [record.answer for record in top_rows]
        matrix.append(middle.answer + "#")
        matrix.extend(record.answer for record in bottom_rows)
        crossing_ok = all(
            "".join(matrix[row][column] for row in range(7)) == verticals[column]
            for column in range(5)
        )
        extension_ok = (
            "".join(matrix[row][5] for row in range(3)) == top_short.answer
            and "".join(matrix[row][5] for row in range(4, 7)) == bottom_short.answer
        )
        topology_ok = True
        if self.shape is not None:
            topology_ok = (
                [slot["length"] for slot in self.shape["slots"]]
                == list(self.topology_expected_lengths)
            )
        score = sum(record.score for record in records)
        return {
            "candidateId": f"{SHAPE_ID}:candidate:{len(self.candidates) + 1:02d}",
            "shapeId": SHAPE_ID,
            "answers": list(answers),
            "slotAnswers": {str(index): answer for index, answer in enumerate(answers)},
            "verticals": list(verticals),
            "topShort": top_short.answer,
            "topRows": [record.answer for record in top_rows],
            "middle": middle.answer,
            "bottomShort": bottom_short.answer,
            "bottomRows": [record.answer for record in bottom_rows],
            "matrix": matrix,
            "score": round(score, 3),
            "audit": {
                "valid": crossing_ok and extension_ok and topology_ok,
                "crossingLettersMatch": crossing_ok,
                "shortExtensionsMatch": extension_ok,
                "shapeSlotLengthsMatch": topology_ok,
                "answerCount": len(answers),
                "uniqueAnswerCount": len(set(answers)),
                "uniqueFamilyCount": len({family_key(answer) for answer in answers}),
                "unfamiliarAnswerCount": selection.unfamiliar,
                "grammarAnswerCount": selection.grammar,
                "activeAnswerCount": selection.active,
                "unfamiliarAnswers": [
                    record.answer for record in records
                    if record.zipf < self.policy.minimum_familiarity_zipf
                ],
                "activeAnswers": [
                    record.answer for record in records
                    if self.active_usage.get(record.answer, 0) > 0
                ],
                "answerZipf": {
                    record.answer: round(record.zipf, 3) for record in records
                },
            },
        }

    def telemetry(self, result: SearchResult) -> dict:
        elapsed = time.monotonic() - self.started
        domain_stats = {}
        for depth, values in sorted(self.domain_sizes.items()):
            domain_stats[str(depth)] = {
                "visits": len(values),
                "minimum": min(values) if values else 0,
                "maximum": max(values) if values else 0,
                "average": round(sum(values) / len(values), 3) if values else 0,
            }
        return {
            "status": result.value,
            "stopReason": self.stop_reason,
            "elapsedSeconds": round(elapsed, 3),
            "nodes": self.nodes,
            "maximumDepth": self.maximum_depth,
            "depthVisits": {str(key): value for key, value in sorted(self.depth_visits.items())},
            "columnDomainSizes": domain_stats,
            "completePrefixSets": self.complete_prefixes,
            "extensionPairsChecked": self.extension_pairs_checked,
            "candidateCount": len(self.candidates),
            "rejections": dict(sorted(self.rejections.items())),
            "nearClosureDiagnostics": self.prefix_diagnostics,
            "proof": (
                "candidate limit reached" if self.stop_reason == "solution-limit"
                else "all column-prefix branches exhausted" if result is SearchResult.DEAD
                else "deadline reached; no infeasibility claim" if result is SearchResult.CUTOFF
                else "complete structural candidates audited"
            ),
        }


def load_shape(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    shape = next(
        (item for item in document.get("shapes", []) if item.get("shapeId") == SHAPE_ID),
        None,
    )
    if shape is None:
        raise ValueError(f"Silhouette {SHAPE_ID} absente de {path}")
    expected = [7, 7, 7, 7, 7, 3, 6, 6, 6, 5, 3, 6, 6, 6]
    actual = [int(slot["length"]) for slot in shape.get("slots", [])]
    if actual != expected:
        raise ValueError(f"Ordre de slots inattendu pour {SHAPE_ID}: {actual}")
    return shape


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shape-library", type=Path, default=DEFAULT_SHAPE_LIBRARY)
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--solution-limit", type=int, default=12)
    parser.add_argument("--minimum-solution-distance", type=int, default=4)
    parser.add_argument("--minimum-zipf", type=float, default=2.0)
    parser.add_argument("--minimum-constructor-score", type=float, default=5.0)
    parser.add_argument("--short-minimum-zipf", type=float, default=2.0)
    parser.add_argument("--short-minimum-constructor-score", type=float, default=5.0)
    parser.add_argument("--pilot-safe-short-only", action="store_true")
    parser.add_argument("--minimum-familiarity-zipf", type=float, default=3.0)
    parser.add_argument("--maximum-unfamiliar-answers", type=int, default=3)
    parser.add_argument("--maximum-grammar-answers", type=int, default=1)
    parser.add_argument("--maximum-active-answers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    shape = load_shape(args.shape_library)
    six, seven, short, middle, pool_counts = load_records(
        minimum_zipf=args.minimum_zipf,
        minimum_constructor_score=args.minimum_constructor_score,
        pilot_safe_short_only=args.pilot_safe_short_only,
        short_minimum_zipf=args.short_minimum_zipf,
        short_minimum_constructor_score=args.short_minimum_constructor_score,
    )
    _forbidden, active = _load_forbidden()
    policy = SearchPolicy(
        seconds=args.seconds,
        solution_limit=args.solution_limit,
        minimum_solution_distance=args.minimum_solution_distance,
        minimum_familiarity_zipf=args.minimum_familiarity_zipf,
        maximum_unfamiliar_answers=args.maximum_unfamiliar_answers,
        maximum_grammar_answers=args.maximum_grammar_answers,
        maximum_active_answers=args.maximum_active_answers,
    )
    search = CorrectedShape02ColumnSearch(
        six=six, seven=seven, short=short, five=middle[5],
        active_usage=active, policy=policy, seed=args.seed, shape=shape,
    )
    result, candidates = search.solve()
    payload = {
        "version": 1,
        "kind": "motman-corrected-7x8-02-column-induced-search",
        "shapeId": SHAPE_ID,
        "catalogModified": False,
        "runtimeModified": False,
        "publicationEligible": False,
        "policy": {
            "minimumZipf": args.minimum_zipf,
            "minimumConstructorScore": args.minimum_constructor_score,
            "shortMinimumZipf": args.short_minimum_zipf,
            "shortMinimumConstructorScore": args.short_minimum_constructor_score,
            "pilotSafeShortOnly": args.pilot_safe_short_only,
            "minimumFamiliarityZipf": policy.minimum_familiarity_zipf,
            "maximumUnfamiliarAnswers": policy.maximum_unfamiliar_answers,
            "maximumGrammarAnswers": policy.maximum_grammar_answers,
            "maximumActiveAnswers": policy.maximum_active_answers,
            "minimumSolutionDistance": policy.minimum_solution_distance,
        },
        "poolCounts": pool_counts,
        "telemetry": search.telemetry(result),
        "candidates": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "status": result.value,
        "candidateCount": len(candidates),
        **payload["telemetry"],
    }, ensure_ascii=False, indent=2))
    return 0 if candidates else 2 if result is SearchResult.DEAD else 3


if __name__ == "__main__":
    raise SystemExit(main())
