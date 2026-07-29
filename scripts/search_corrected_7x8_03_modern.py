#!/usr/bin/env python3
"""Bounded column-induced search for a modern ``corrected-7x8-03`` fill.

The five seven-letter columns determine four-letter row stems plus the last
letter of each six-letter row.  The two three-letter answers provide the
missing fifth letters above and below the internal clue.  This decomposition
keeps the exact geometry fixed while enforcing a global quota of current,
owner-approved answers anywhere in the grid.
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from wordfreq import zipf_frequency

from build_compact_7x8_review import family_key
from strict_ribbon_row_dfs import (
    PrefixTrie,
    SearchResult,
    WordDomain,
    WordRecord,
    _load_forbidden,
    load_records,
    normalize,
)
from search_corrected_7x8_06_current import CURRENT, STRONG as CURRENT_STRONG


ROOT = Path(__file__).resolve().parents[1]
SHAPE_ID = "corrected-7x8-03"
DEFAULT_SHAPE_LIBRARY = (
    ROOT / "output/quality/corrected-7x8-shapes/corrected-shape-library.json"
)
DEFAULT_AVOID_FILL = (
    ROOT
    / "output/quality/pilot-agent-c-corrected7x8"
    / "corrected-03-large-seed-814300.json"
)
MODERN = set(CURRENT)
STRONG = set(CURRENT_STRONG)
# Marques/licences identifiables comme telles dans le réservoir actuel. Les
# termes génériques (STREAM, PODCAST, CONSOLE...) ne sont pas des marques.
BRANDS = {"BARBIE", "DISNEY", "NETFLIX", "POKEMON", "SPOTIFY", "TWITCH", "YOUTUBE"}
HARD_EXCLUDE = {"CIERGE", "ARDENT"}
ACTIVE_REPEAT_PENALTY = 60.0
EXPECTED_LENGTHS = (7, 7, 7, 7, 3, 7, 6, 6, 6, 4, 3, 6, 6, 6)


@dataclass(frozen=True)
class Policy:
    seconds: float = 60.0
    solution_limit: int = 8
    minimum_modern_answers: int = 1
    minimum_strong_answers: int = 1
    minimum_familiarity_zipf: float = 3.0
    maximum_unfamiliar_answers: int = 2
    maximum_grammar_answers: int = 1
    maximum_brand_answers: int = 2
    active_repeat_penalty: float = ACTIVE_REPEAT_PENALTY


@dataclass(frozen=True)
class Selection:
    answers: frozenset[str] = frozenset()
    families: frozenset[str] = frozenset()
    unfamiliar: int = 0
    grammar: int = 0
    modern: int = 0
    strong: int = 0
    brands: int = 0


def load_shape(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    shape = next(
        (item for item in document.get("shapes", []) if item.get("shapeId") == SHAPE_ID),
        None,
    )
    if shape is None:
        raise ValueError(f"Silhouette absente: {SHAPE_ID}")
    lengths = tuple(int(slot["length"]) for slot in shape.get("slots", []))
    if lengths != EXPECTED_LENGTHS:
        raise ValueError(f"Ordre de slots inattendu: {lengths}")
    return shape


def old_fill(path: Path | None) -> tuple[str, ...] | None:
    if path is None or not path.exists():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    alternatives = document.get("alternatives", [])
    if alternatives and isinstance(alternatives[0].get("answers"), dict):
        answers = alternatives[0]["answers"]
        return tuple(normalize(answers[str(index)]) for index in range(14))
    return None


class ModernShape03Search:
    def __init__(
        self,
        *,
        six: Sequence[WordRecord],
        seven: Sequence[WordRecord],
        short: Sequence[WordRecord],
        four: Sequence[WordRecord],
        active_usage: Counter[str],
        avoid: tuple[str, ...] | None,
        policy: Policy,
        seed: int,
        rotation_cooldown: set[str] | None = None,
    ) -> None:
        self.policy = policy
        self.active_usage = active_usage
        self.rotation_cooldown = rotation_cooldown or set()
        self.avoid = avoid
        self.started = time.monotonic()
        self.deadline = self.started + max(0.0, policy.seconds)
        self.timed_out = False
        self.stop_reason = "not-started"
        self.nodes = 0
        self.completed_vertical_sets = 0
        self.extension_pairs_checked = 0
        self.depth_visits: Counter[int] = Counter()
        self.rejections: Counter[str] = Counter()
        self.candidates: list[dict] = []
        self.candidate_keys: set[tuple[str, ...]] = set()

        def prepared(records: Sequence[WordRecord]) -> list[WordRecord]:
            result = []
            for record in records:
                if record.answer in HARD_EXCLUDE or record.answer in self.rotation_cooldown:
                    continue
                bonus = 1000.0 if record.answer in MODERN else 0.0
                bonus += 500.0 if record.answer in STRONG else 0.0
                repeat_penalty = (
                    policy.active_repeat_penalty * active_usage.get(record.answer, 0)
                )
                result.append(WordRecord(
                    answer=record.answer,
                    score=record.score + bonus - repeat_penalty,
                    zipf=record.zipf,
                    family=record.family,
                    image=record.image,
                    grammar=record.grammar,
                ))
            return result

        self.six = prepared(six)
        self.seven = prepared(seven)
        self.short = prepared(short)
        self.four = prepared(four)
        self.records = {
            record.answer: record
            for group in (self.six, self.seven, self.short, self.four)
            for record in group
        }
        self.seven_domain = WordDomain(self.seven, seed)
        self.six_trie = PrefixTrie(record.answer for record in self.six)
        self.four_trie = PrefixTrie(record.answer for record in self.four)
        self.four_by_answer = {record.answer: record for record in self.four}
        self.six_by_pattern: dict[tuple[str, str, str], WordRecord] = {}
        self.six_by_stem_extension: dict[
            tuple[str, str], dict[str, WordRecord]
        ] = defaultdict(dict)
        for record in self.six:
            self.six_by_pattern[(record.answer[:4], record.answer[4], record.answer[5])] = record
            self.six_by_stem_extension[(record.answer[:4], record.answer[4])][
                record.answer[5]
            ] = record
        self.seven_by_outer_signature: dict[str, list[WordRecord]] = defaultdict(list)
        for record in self.seven_domain.records:
            signature = "".join(record.answer[index] for index in (0, 1, 2, 4, 5, 6))
            self.seven_by_outer_signature[signature].append(record)

    def _add(self, selection: Selection, records: Iterable[WordRecord]) -> Selection | None:
        answers = set(selection.answers)
        families = set(selection.families)
        unfamiliar = selection.unfamiliar
        grammar = selection.grammar
        modern = selection.modern
        strong = selection.strong
        brands = selection.brands
        for record in records:
            if record.answer in answers:
                self.rejections["duplicate-answer"] += 1
                return None
            if record.family in families:
                self.rejections["duplicate-family"] += 1
                return None
            answers.add(record.answer)
            families.add(record.family)
            unfamiliar += int(
                record.answer not in MODERN
                and record.zipf < self.policy.minimum_familiarity_zipf
            )
            grammar += int(record.grammar)
            modern += int(record.answer in MODERN)
            strong += int(record.answer in STRONG)
            brands += int(record.answer in BRANDS)
        if unfamiliar > self.policy.maximum_unfamiliar_answers:
            self.rejections["too-many-unfamiliar"] += 1
            return None
        if grammar > self.policy.maximum_grammar_answers:
            self.rejections["too-many-grammar"] += 1
            return None
        if brands > self.policy.maximum_brand_answers:
            self.rejections["too-many-brands"] += 1
            return None
        return Selection(
            frozenset(answers), frozenset(families), unfamiliar, grammar, modern,
            strong, brands,
        )

    def solve(self) -> tuple[SearchResult, list[dict]]:
        tries = (
            self.six_trie, self.six_trie, self.six_trie, self.four_trie,
            self.six_trie, self.six_trie, self.six_trie,
        )
        self.stop_reason = "searching"
        exhausted = self._columns(
            depth=0,
            nodes=(0, 0, 0, 0, 0, 0, 0),
            verticals=(),
            selection=Selection(),
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
        return (SearchResult.DEAD if exhausted else SearchResult.CUTOFF), []

    def _columns(
        self,
        *,
        depth: int,
        nodes: tuple[int, ...],
        verticals: tuple[str, ...],
        selection: Selection,
        tries: tuple[PrefixTrie, ...],
    ) -> bool:
        self.nodes += 1
        self.depth_visits[depth] += 1
        if time.monotonic() >= self.deadline:
            self.timed_out = True
            return False
        if len(self.candidates) >= self.policy.solution_limit:
            return False
        if depth == 4:
            self._last_column(nodes, verticals, selection, tries)
            return not self.timed_out

        fully_explored = True
        for record in self.seven_domain.matching(tries, nodes):
            next_selection = self._add(selection, (record,))
            if next_selection is None:
                continue
            next_nodes = []
            for row, trie in enumerate(tries):
                child = trie.advance(nodes[row], record.answer[row])
                if child is None:
                    break
                next_nodes.append(child)
            if len(next_nodes) != 7:
                continue
            child_exhausted = self._columns(
                depth=depth + 1,
                nodes=tuple(next_nodes),
                verticals=verticals + (record.answer,),
                selection=next_selection,
                tries=tries,
            )
            fully_explored &= child_exhausted
            if self.timed_out or len(self.candidates) >= self.policy.solution_limit:
                return False
        return fully_explored

    def _last_column(
        self,
        nodes: tuple[int, ...],
        verticals: tuple[str, ...],
        selection: Selection,
        tries: tuple[PrefixTrie, ...],
    ) -> None:
        stems = tuple(trie.prefix[node] for trie, node in zip(tries, nodes))
        middle = self.four_by_answer.get(stems[3])
        if middle is None:
            self.rejections["missing-middle"] += 1
            return
        with_middle = self._add(selection, (middle,))
        if with_middle is None:
            return
        top = self._band_signature_options(stems, (0, 1, 2))
        if not top:
            self.rejections["no-top-short-extension"] += 1
            return
        bottom = self._band_signature_options(stems, (4, 5, 6))
        if not bottom:
            self.rejections["no-bottom-short-extension"] += 1
            return
        for top_short, top_signature, top_rows in top:
            for bottom_short, bottom_signature, bottom_rows in bottom:
                self.extension_pairs_checked += 1
                for last in self.seven_by_outer_signature.get(
                    top_signature + bottom_signature, ()
                ):
                    if time.monotonic() >= self.deadline:
                        self.timed_out = True
                        return
                    selected = self._add(with_middle, (last,))
                    if selected is None:
                        continue
                    self.completed_vertical_sets += 1
                    after_top = self._add(selected, (top_short, *top_rows))
                    if after_top is None:
                        continue
                    final = self._add(after_top, (bottom_short, *bottom_rows))
                    if final is None:
                        continue
                    if final.modern < self.policy.minimum_modern_answers:
                        self.rejections["not-enough-modern-answers"] += 1
                        continue
                    if final.strong < self.policy.minimum_strong_answers:
                        self.rejections["no-strong-anchor"] += 1
                        continue
                    answers = (
                        *verticals,
                        top_short.answer,
                        last.answer,
                        *(record.answer for record in top_rows),
                        middle.answer,
                        bottom_short.answer,
                        *(record.answer for record in bottom_rows),
                    )
                    # Slot order: 0..3 vertical, 4 top short, 5 last vertical,
                    # 6..8 top rows, 9 middle, 10 bottom short, 11..13 rows.
                    if self.avoid is not None and answers == self.avoid:
                        self.rejections["old-fill-no-good"] += 1
                        continue
                    if answers in self.candidate_keys:
                        self.rejections["duplicate-fill"] += 1
                        continue
                    self.candidate_keys.add(answers)
                    self.candidates.append(self._payload(
                        answers, verticals + (last.answer,), top_short, top_rows,
                        middle, bottom_short, bottom_rows, final,
                    ))
                    if len(self.candidates) >= self.policy.solution_limit:
                        return

    def _band_signature_options(
        self,
        stems: tuple[str, ...],
        rows: tuple[int, int, int],
    ) -> list[tuple[WordRecord, str, tuple[WordRecord, ...]]]:
        """Return short answer, last-column signature and completed rows."""

        result = []
        for short in self.short:
            suffix_maps = tuple(
                self.six_by_stem_extension.get((stems[row], short.answer[offset]), {})
                for offset, row in enumerate(rows)
            )
            if not all(suffix_maps):
                continue
            for suffixes in itertools.product(*(tuple(mapping) for mapping in suffix_maps)):
                result.append((
                    short,
                    "".join(suffixes),
                    tuple(mapping[suffix] for mapping, suffix in zip(suffix_maps, suffixes)),
                ))
        return result

    def _band_options(
        self,
        stems: tuple[str, ...],
        last: str,
        rows: tuple[int, int, int],
    ) -> list[tuple[WordRecord, tuple[WordRecord, ...]]]:
        result = []
        for short in self.short:
            row_records = tuple(
                self.six_by_pattern.get((stems[row], short.answer[offset], last[row]))
                for offset, row in enumerate(rows)
            )
            if all(row_records):
                result.append((short, row_records))
        return result

    def _payload(
        self,
        answers: tuple[str, ...],
        verticals: tuple[str, ...],
        top_short: WordRecord,
        top_rows: tuple[WordRecord, ...],
        middle: WordRecord,
        bottom_short: WordRecord,
        bottom_rows: tuple[WordRecord, ...],
        selection: Selection,
    ) -> dict:
        matrix = [record.answer for record in top_rows]
        matrix.append(middle.answer + "#" + verticals[4][3])
        matrix.extend(record.answer for record in bottom_rows)
        crossing_ok = all(
            "".join(matrix[row][column] for row in range(7)) == verticals[index]
            for index, column in enumerate((0, 1, 2, 3, 5))
        )
        modern_answers = [answer for answer in answers if answer in MODERN]
        strong_answers = [answer for answer in answers if answer in STRONG]
        brand_answers = [answer for answer in answers if answer in BRANDS]
        active_answers = [
            answer for answer in answers if self.active_usage.get(answer, 0) > 0
        ]
        active_repeat_occurrences = sum(
            self.active_usage[answer] for answer in active_answers
        )
        return {
            "candidateId": f"{SHAPE_ID}:modern:{len(self.candidates) + 1:02d}",
            "shapeId": SHAPE_ID,
            "answers": list(answers),
            "slotAnswers": {str(index): answer for index, answer in enumerate(answers)},
            "matrix": matrix,
            "modernAnswers": modern_answers,
            "strongAnswers": strong_answers,
            "brandAnswers": brand_answers,
            "score": round(sum(self.records[answer].score for answer in answers), 3),
            "audit": {
                "valid": (
                    crossing_ok
                    and len(modern_answers) >= self.policy.minimum_modern_answers
                    and len(strong_answers) >= self.policy.minimum_strong_answers
                ),
                "crossingLettersMatch": crossing_ok,
                "modernAnswerCount": len(modern_answers),
                "strongAnswerCount": len(strong_answers),
                "unfamiliarAnswerCount": selection.unfamiliar,
                "grammarAnswerCount": selection.grammar,
                "brandAnswerCount": selection.brands,
                "activeAnswers": active_answers,
                "activeRepeatOccurrences": active_repeat_occurrences,
                "activeRepeatPenalty": round(
                    self.policy.active_repeat_penalty * active_repeat_occurrences, 3
                ),
                "answerZipf": {
                    answer: round(self.records[answer].zipf, 3) for answer in answers
                },
            },
        }

    def telemetry(self, result: SearchResult) -> dict:
        return {
            "status": result.value,
            "stopReason": self.stop_reason,
            "elapsedSeconds": round(time.monotonic() - self.started, 3),
            "nodes": self.nodes,
            "depthVisits": {str(k): v for k, v in sorted(self.depth_visits.items())},
            "completedVerticalSets": self.completed_vertical_sets,
            "extensionPairsChecked": self.extension_pairs_checked,
            "candidateCount": len(self.candidates),
            "rejections": dict(sorted(self.rejections.items())),
            "proof": (
                "bounded cutoff; no infeasibility claim" if result is SearchResult.CUTOFF
                else "complete modern candidates found" if result is SearchResult.FOUND
                else "all structural branches exhausted"
            ),
        }


def ensure_modern_records(
    pools: dict[int, list[WordRecord]], forbidden: set[str],
    rotation_cooldown: set[str], active: Counter[str]
) -> None:
    for answer in sorted(MODERN):
        length = len(answer)
        if length not in pools or answer in forbidden or answer in rotation_cooldown:
            continue
        if any(record.answer == answer for record in pools[length]):
            continue
        pools[length].append(WordRecord(
            answer=answer,
            score=95.0,
            zipf=float(zipf_frequency(answer.lower(), "fr")),
            family=family_key(answer),
        ))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shape-library", type=Path, default=DEFAULT_SHAPE_LIBRARY)
    parser.add_argument("--avoid-fill", type=Path, default=DEFAULT_AVOID_FILL)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--solution-limit", type=int, default=8)
    parser.add_argument("--minimum-modern-answers", type=int, default=2)
    parser.add_argument("--minimum-strong-answers", type=int, default=1)
    parser.add_argument("--minimum-zipf", type=float, default=2.0)
    parser.add_argument("--minimum-constructor-score", type=float, default=5.0)
    parser.add_argument("--minimum-familiarity-zipf", type=float, default=3.0)
    parser.add_argument("--maximum-unfamiliar-answers", type=int, default=2)
    parser.add_argument("--maximum-grammar-answers", type=int, default=1)
    parser.add_argument("--maximum-brand-answers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=70370)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_shape(args.shape_library)
    six, seven, short, middle, pool_counts = load_records(
        minimum_zipf=args.minimum_zipf,
        minimum_constructor_score=args.minimum_constructor_score,
        pilot_safe_short_only=True,
        short_minimum_zipf=2.0,
        short_minimum_constructor_score=5.0,
    )
    forbidden, _ = _load_forbidden()
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    rotation_cooldown = {
        normalize(item.get("answer") if isinstance(item, dict) else item)
        for item in blacklist.get("rotationCooldownAnswers", [])
    }
    catalog = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    active = Counter(
        normalize(word.get("answer"))
        for grid in catalog.get("grids", []) for word in grid.get("words", [])
    )
    pools = {3: short, 4: middle[4], 6: six, 7: seven}
    ensure_modern_records(pools, forbidden, rotation_cooldown, active)
    policy = Policy(
        seconds=args.seconds,
        solution_limit=args.solution_limit,
        minimum_modern_answers=args.minimum_modern_answers,
        minimum_strong_answers=args.minimum_strong_answers,
        minimum_familiarity_zipf=args.minimum_familiarity_zipf,
        maximum_unfamiliar_answers=args.maximum_unfamiliar_answers,
        maximum_grammar_answers=args.maximum_grammar_answers,
        maximum_brand_answers=args.maximum_brand_answers,
    )
    search = ModernShape03Search(
        six=pools[6], seven=pools[7], short=pools[3], four=pools[4],
        active_usage=active, avoid=old_fill(args.avoid_fill), policy=policy,
        seed=args.seed, rotation_cooldown=rotation_cooldown,
    )
    result, candidates = search.solve()
    payload = {
        "version": 1,
        "kind": "motman-corrected-7x8-03-modern-column-search",
        "shapeId": SHAPE_ID,
        "catalogModified": False,
        "runtimeModified": False,
        "publicationEligible": False,
        "modernAnswerSet": sorted(MODERN),
        "hardExcludedAnswers": sorted(HARD_EXCLUDE),
        "strongAnswerSet": sorted(STRONG),
        "oldFillNoGoodLoaded": search.avoid is not None,
        "activeCatalogPolicy": {
            "mode": "score-penalty",
            "penaltyPerPreviousUse": policy.active_repeat_penalty,
        },
        "rotationCooldownPolicy": "hard-exclusion",
        "policy": policy.__dict__,
        "poolCounts": {
            str(length): len(records) for length, records in sorted(pools.items())
        },
        "sourcePoolCounts": pool_counts,
        "telemetry": search.telemetry(result),
        "candidates": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "output": str(args.output),
        "status": result.value,
        "candidateCount": len(candidates),
        **payload["telemetry"],
    }, ensure_ascii=False, indent=2))
    return 0 if candidates else 2 if result is SearchResult.DEAD else 3


if __name__ == "__main__":
    raise SystemExit(main())
