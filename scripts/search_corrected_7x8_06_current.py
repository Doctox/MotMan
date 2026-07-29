#!/usr/bin/env python3
"""One bounded, indexed search for a fresh ``corrected-7x8-06`` fill."""
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
from search_compact_grid_pilot import rotation_cooldown_usage
from strict_ribbon_row_dfs import (
    PrefixTrie,
    SearchResult,
    WordDomain,
    WordRecord,
    _load_forbidden,
    load_records,
)


ROOT = Path(__file__).resolve().parents[1]
SHAPE_ID = "corrected-7x8-06"
DEFAULT_SHAPE_LIBRARY = (
    ROOT / "output/quality/corrected-7x8-shapes/corrected-shape-library.json"
)
EXPECTED_LENGTHS_BY_SHAPE = {
    "corrected-7x8-05": (7, 7, 7, 3, 7, 3, 6, 6, 6, 3, 3, 3, 6, 6, 6),
    "corrected-7x8-06": (7, 7, 7, 3, 3, 7, 6, 6, 6, 3, 3, 3, 6, 6, 6),
}
EXPECTED_LENGTHS = EXPECTED_LENGTHS_BY_SHAPE[SHAPE_ID]

CURRENT = {
    "BOT", "BOX", "BUG", "FAN", "FAQ", "GIF", "GPS", "JOB", "KIT", "LOL", "POP", "RAP", "TGV", "WEB", "ZEN",
    "BLOG", "CAFE", "CHAT", "CLIP", "CODE", "COOL", "DATA", "FILM", "FLOW", "FUNK", "GEEK", "JAZZ", "KPOP", "LIVE", "LOOK", "MAIL", "MEME", "MOTO", "QUIZ", "ROCK", "TAXI", "TEAM", "VELO", "WIFI", "YOGA",
    "BAGAGE", "BALLON", "BANANE", "BARBIE", "BASKET", "BATEAU", "BOULOT", "BRUNCH", "BURGER", "BUREAU", "CAMERA", "CASQUE", "CINEMA", "COOKIE", "DISNEY", "EMOJIS", "EMPLOI", "EQUIPE", "GAMING", "MOBILE", "PIMENT", "PROFIL", "REPLAY", "SERIES", "SELFIE", "STREAM", "STUDIO", "TWITCH", "VALISE", "VOYAGE",
    "ARTISTE", "AUBERGE", "BITCOIN", "CAMPING", "CLAVIER", "CONCERT", "CONSOLE", "COSPLAY", "CUISINE", "DANSEUR", "FITNESS", "FROMAGE", "GUITARE", "JOGGING", "KARAOKE", "MESSAGE", "MUSIQUE", "NETFLIX", "PISCINE", "PODCAST", "POKEMON", "RAPPEUR", "RECETTE", "RESEAUX", "SCOOTER", "SPOTIFY", "TRAMWAY", "VOITURE", "WEEKEND", "YOUTUBE",
    # Réponses déjà relues dans le réservoir MotMan mais omises du premier
    # set 16–45. Elles sont autonomes et réellement employées aujourd'hui.
    "APPLIS", "AVATAR", "BEREAL", "CAPCUT", "CHROME", "GITHUB", "GOOGLE",
    "IPHONE", "MARVEL", "ONLINE", "OPENAI", "PIXELS", "PSEUDO", "REBOOT",
    "ROBLOX", "SHORTS", "SWITCH", "TIKTOK", "TINDER", "UPDATE", "UPLOAD",
    "VIDEOS", "WEBCAM", "WIDGET",
    "AIRPODS", "ANDROID", "CHATGPT", "DEEZER", "DISCORD", "FALLOUT",
    "FIREFOX", "HASHTAG", "REDDIT", "STICKER", "THREADS", "WARZONE",
    "WINDOWS",
}
STRONG = {
    "BOX", "BUG", "GIF", "RAP", "WEB", "BLOG", "CLIP", "LIVE", "MEME", "WIFI",
    "BARBIE", "BRUNCH", "BURGER", "CINEMA", "DISNEY", "SELFIE", "STREAM", "TWITCH",
    "CONCERT", "CONSOLE", "NETFLIX", "PODCAST", "POKEMON", "SPOTIFY", "YOUTUBE",
    "AVATAR", "CAPCUT", "CHATGPT", "DISCORD", "GOOGLE", "IPHONE", "MARVEL",
    "ROBLOX", "SWITCH", "TIKTOK",
}


@dataclass(frozen=True)
class Policy:
    seconds: float = 45.0
    solution_limit: int = 8
    minimum_current: int = 2
    minimum_strong: int = 1
    minimum_familiarity_zipf: float = 3.0
    maximum_unfamiliar: int = 3
    maximum_grammar: int = 1


@dataclass(frozen=True)
class Selection:
    answers: frozenset[str] = frozenset()
    families: frozenset[str] = frozenset()
    unfamiliar: int = 0
    grammar: int = 0
    current: int = 0
    strong: int = 0


def load_shape(path: Path, shape_id: str = SHAPE_ID) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    shape = next(
        (item for item in document.get("shapes", []) if item.get("shapeId") == shape_id),
        None,
    )
    if shape is None:
        raise ValueError(f"Silhouette absente: {shape_id}")
    actual = tuple(int(slot["length"]) for slot in shape.get("slots", []))
    if actual != EXPECTED_LENGTHS_BY_SHAPE[shape_id]:
        raise ValueError(f"Ordre de slots inattendu: {actual}")
    return shape


class CurrentShape06Search:
    def __init__(
        self,
        *,
        six: Sequence[WordRecord],
        seven: Sequence[WordRecord],
        short: Sequence[WordRecord],
        active_usage: Counter[str],
        cooldown_answers: set[str] | None = None,
        policy: Policy,
        seed: int,
        shape_id: str = SHAPE_ID,
    ) -> None:
        self.shape_id = shape_id
        self.policy = policy
        self.active_usage = active_usage
        self.started = time.monotonic()
        self.deadline = self.started + max(0.0, policy.seconds)
        self.timed_out = False
        self.nodes = 0
        self.complete_stems = 0
        self.band_pairs = 0
        self.last_column_matches = 0
        self.rejections: Counter[str] = Counter()
        self.depth_visits: Counter[int] = Counter()
        self.candidates: list[dict] = []
        self.candidate_keys: set[tuple[str, ...]] = set()
        self.stop_reason = "not-started"

        cooldown_answers = cooldown_answers or set()

        def prepared(records: Sequence[WordRecord]) -> list[WordRecord]:
            result = []
            for record in records:
                # A published answer remains usable with the score penalty
                # already applied by load_records. Only an explicit editorial
                # cooldown is a hard exclusion.
                if record.answer in cooldown_answers:
                    continue
                bonus = 1000.0 if record.answer in CURRENT else 0.0
                bonus += 500.0 if record.answer in STRONG else 0.0
                result.append(WordRecord(
                    answer=record.answer, score=record.score + bonus,
                    zipf=record.zipf, family=record.family, image=record.image,
                    grammar=record.grammar,
                ))
            return result

        self.six = prepared(six)
        self.seven = prepared(seven)
        self.short = prepared(short)
        self.records = {
            record.answer: record
            for group in (self.six, self.seven, self.short)
            for record in group
        }
        self.seven_domain = WordDomain(self.seven, seed)
        self.short_domain = WordDomain(self.short, seed + 1)
        self.six_trie = PrefixTrie(record.answer for record in self.six)
        self.short_trie = PrefixTrie(record.answer for record in self.short)
        self.short_by_answer = {record.answer: record for record in self.short}
        self.six_suffix: dict[tuple[str, str, str], dict[str, WordRecord]] = defaultdict(dict)
        self.allowed_second_chars: dict[tuple[str, str], set[str]] = defaultdict(set)
        for record in self.six:
            if self.shape_id == "corrected-7x8-06":
                second_char, signature_char = record.answer[4], record.answer[5]
            else:
                second_char, signature_char = record.answer[5], record.answer[4]
            key = (record.answer[:3], record.answer[3], second_char)
            self.six_suffix[key][signature_char] = record
            self.allowed_second_chars[(record.answer[:3], record.answer[3])].add(second_char)
        self.seven_by_signature: dict[str, list[WordRecord]] = defaultdict(list)
        for record in self.seven_domain.records:
            signature = "".join(record.answer[index] for index in (0, 1, 2, 4, 5, 6))
            self.seven_by_signature[signature].append(record)

    def _add(self, selection: Selection, records: Iterable[WordRecord]) -> Selection | None:
        answers = set(selection.answers)
        families = set(selection.families)
        unfamiliar = selection.unfamiliar
        grammar = selection.grammar
        current = selection.current
        strong = selection.strong
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
                record.answer not in CURRENT
                and record.zipf < self.policy.minimum_familiarity_zipf
            )
            grammar += int(record.grammar)
            current += int(record.answer in CURRENT)
            strong += int(record.answer in STRONG)
        if unfamiliar > self.policy.maximum_unfamiliar:
            self.rejections["too-many-unfamiliar"] += 1
            return None
        if grammar > self.policy.maximum_grammar:
            self.rejections["too-many-grammar"] += 1
            return None
        return Selection(
            frozenset(answers), frozenset(families), unfamiliar, grammar,
            current, strong,
        )

    def solve(self) -> tuple[SearchResult, list[dict]]:
        tries = (
            self.six_trie, self.six_trie, self.six_trie, self.short_trie,
            self.six_trie, self.six_trie, self.six_trie,
        )
        self.stop_reason = "searching"
        exhausted = self._columns(
            depth=0, nodes=(0, 0, 0, 0, 0, 0, 0), verticals=(),
            selection=Selection(), tries=tries,
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
        *, depth: int, nodes: tuple[int, ...], verticals: tuple[str, ...],
        selection: Selection, tries: tuple[PrefixTrie, ...],
    ) -> bool:
        self.nodes += 1
        self.depth_visits[depth] += 1
        if time.monotonic() >= self.deadline:
            self.timed_out = True
            return False
        if len(self.candidates) >= self.policy.solution_limit:
            return False
        if depth == 3:
            self.complete_stems += 1
            self._close(nodes, verticals, selection, tries)
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
                depth=depth + 1, nodes=tuple(next_nodes),
                verticals=verticals + (record.answer,),
                selection=next_selection, tries=tries,
            )
            fully_explored &= child_exhausted
            if self.timed_out or len(self.candidates) >= self.policy.solution_limit:
                return False
        return fully_explored

    def _close(
        self, nodes: tuple[int, ...], verticals: tuple[str, ...],
        selection: Selection, tries: tuple[PrefixTrie, ...],
    ) -> None:
        stems = tuple(trie.prefix[node] for trie, node in zip(tries, nodes))
        middle = self.short_by_answer.get(stems[3])
        if middle is None:
            self.rejections["missing-middle"] += 1
            return
        with_middle = self._add(selection, (middle,))
        if with_middle is None:
            return
        top = self._band_options(stems, (0, 1, 2))
        if not top:
            self.rejections["no-top-band"] += 1
            return
        bottom = self._band_options(stems, (4, 5, 6))
        if not bottom:
            self.rejections["no-bottom-band"] += 1
            return
        for top_a, top_b, top_sig, top_rows in top:
            for bottom_a, bottom_b, bottom_sig, bottom_rows in bottom:
                self.band_pairs += 1
                for last in self.seven_by_signature.get(top_sig + bottom_sig, ()):
                    selected = self._add(with_middle, (top_a, top_b, last))
                    if selected is None:
                        continue
                    self.last_column_matches += 1
                    after_rows = self._add(selected, top_rows)
                    if after_rows is None:
                        continue
                    final = self._add(after_rows, (bottom_a, bottom_b, *bottom_rows))
                    if final is None:
                        continue
                    if final.current < self.policy.minimum_current:
                        self.rejections["not-enough-current"] += 1
                        continue
                    if final.strong < self.policy.minimum_strong:
                        self.rejections["no-strong-anchor"] += 1
                        continue
                    if self.shape_id == "corrected-7x8-06":
                        answers = (
                            *verticals, top_a.answer, top_b.answer, last.answer,
                            *(record.answer for record in top_rows), middle.answer,
                            bottom_a.answer, bottom_b.answer,
                            *(record.answer for record in bottom_rows),
                        )
                    else:
                        answers = (
                            *verticals, top_a.answer, last.answer, top_b.answer,
                            *(record.answer for record in top_rows), middle.answer,
                            bottom_a.answer, bottom_b.answer,
                            *(record.answer for record in bottom_rows),
                        )
                    if answers in self.candidate_keys:
                        self.rejections["duplicate-fill"] += 1
                        continue
                    self.candidate_keys.add(answers)
                    self.candidates.append(self._payload(
                        answers, verticals + (last.answer,), top_rows, middle,
                        bottom_rows, final,
                    ))
                    if len(self.candidates) >= self.policy.solution_limit:
                        return

    def _band_options(
        self, stems: tuple[str, ...], rows: tuple[int, int, int]
    ) -> list[tuple[WordRecord, WordRecord, str, tuple[WordRecord, ...]]]:
        result = []
        for first in self.short_domain.records:
            mask = self.short_domain.full_mask
            for offset, row in enumerate(rows):
                allowed = self.allowed_second_chars.get(
                    (stems[row], first.answer[offset]), set()
                )
                allowed_mask = 0
                for char in allowed:
                    allowed_mask |= self.short_domain.masks[offset].get(char, 0)
                mask &= allowed_mask
                if not mask:
                    break
            remaining = mask
            while remaining:
                bit = remaining & -remaining
                second = self.short_domain.records[bit.bit_length() - 1]
                remaining ^= bit
                suffix_maps = tuple(
                    self.six_suffix.get(
                        (stems[row], first.answer[offset], second.answer[offset]), {}
                    )
                    for offset, row in enumerate(rows)
                )
                if not all(suffix_maps):
                    continue
                for suffixes in itertools.product(
                    *(tuple(mapping) for mapping in suffix_maps)
                ):
                    result.append((
                        first, second, "".join(suffixes),
                        tuple(
                            mapping[suffix]
                            for mapping, suffix in zip(suffix_maps, suffixes)
                        ),
                    ))
        return result

    def _payload(
        self, answers: tuple[str, ...], verticals: tuple[str, ...],
        top_rows: tuple[WordRecord, ...], middle: WordRecord,
        bottom_rows: tuple[WordRecord, ...], selection: Selection,
    ) -> dict:
        matrix = [record.answer for record in top_rows]
        if self.shape_id == "corrected-7x8-06":
            matrix.append(middle.answer + "##" + verticals[3][3])
            vertical_columns = (0, 1, 2, 5)
        else:
            matrix.append(middle.answer + "#" + verticals[3][3] + "#")
            vertical_columns = (0, 1, 2, 4)
        matrix.extend(record.answer for record in bottom_rows)
        crossing_ok = all(
            "".join(matrix[row][column] for row in range(7)) == verticals[index]
            for index, column in enumerate(vertical_columns)
        )
        current_answers = [answer for answer in answers if answer in CURRENT]
        strong_answers = [answer for answer in answers if answer in STRONG]
        return {
            "candidateId": f"{self.shape_id}:current:{len(self.candidates) + 1:02d}",
            "shapeId": self.shape_id,
            "answers": list(answers),
            "slotAnswers": {str(index): answer for index, answer in enumerate(answers)},
            "matrix": matrix,
            "currentAnswers": current_answers,
            "strongAnswers": strong_answers,
            "score": round(sum(self.records[answer].score for answer in answers), 3),
            "audit": {
                "valid": crossing_ok,
                "crossingLettersMatch": crossing_ok,
                "currentAnswerCount": len(current_answers),
                "strongAnswerCount": len(strong_answers),
                "unfamiliarAnswerCount": selection.unfamiliar,
                "grammarAnswerCount": selection.grammar,
                "activeAnswerCount": sum(
                    int(self.active_usage.get(answer, 0) > 0) for answer in answers
                ),
                "uniqueFamilyCount": len({family_key(answer) for answer in answers}),
            },
        }

    def telemetry(self, result: SearchResult) -> dict:
        return {
            "status": result.value,
            "stopReason": self.stop_reason,
            "elapsedSeconds": round(time.monotonic() - self.started, 3),
            "nodes": self.nodes,
            "depthVisits": {str(k): v for k, v in sorted(self.depth_visits.items())},
            "completeStemSets": self.complete_stems,
            "bandPairsChecked": self.band_pairs,
            "lastColumnMatches": self.last_column_matches,
            "candidateCount": len(self.candidates),
            "rejections": dict(sorted(self.rejections.items())),
            "proof": (
                "bounded cutoff; no infeasibility claim" if result is SearchResult.CUTOFF
                else "complete current-life candidates found" if result is SearchResult.FOUND
                else "all structural branches exhausted"
            ),
        }


def ensure_current_records(
    pools: dict[int, list[WordRecord]], forbidden: set[str], active: Counter[str],
    cooldown_answers: set[str],
) -> None:
    for answer in sorted(CURRENT):
        length = len(answer)
        if length not in pools or answer in forbidden or answer in cooldown_answers:
            continue
        if any(record.answer == answer for record in pools[length]):
            continue
        pools[length].append(WordRecord(
            answer=answer, score=95.0 - 12.0 * active.get(answer, 0),
            zipf=float(zipf_frequency(answer.lower(), "fr")),
            family=family_key(answer),
        ))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shape-library", type=Path, default=DEFAULT_SHAPE_LIBRARY)
    parser.add_argument(
        "--shape-id", choices=tuple(EXPECTED_LENGTHS_BY_SHAPE), default=SHAPE_ID
    )
    parser.add_argument("--seconds", type=float, default=45.0)
    parser.add_argument("--solution-limit", type=int, default=8)
    parser.add_argument("--minimum-current", type=int, default=2)
    parser.add_argument("--minimum-strong", type=int, default=1)
    parser.add_argument("--minimum-zipf", type=float, default=2.0)
    parser.add_argument("--minimum-constructor-score", type=float, default=5.0)
    parser.add_argument("--minimum-familiarity-zipf", type=float, default=3.0)
    parser.add_argument("--maximum-unfamiliar", type=int, default=3)
    parser.add_argument("--maximum-grammar", type=int, default=1)
    parser.add_argument("--seed", type=int, default=70600)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_shape(args.shape_library, args.shape_id)
    six, seven, short, _middle, source_counts = load_records(
        minimum_zipf=args.minimum_zipf,
        minimum_constructor_score=args.minimum_constructor_score,
        pilot_safe_short_only=True,
        short_minimum_zipf=2.0,
        short_minimum_constructor_score=5.0,
    )
    forbidden, active = _load_forbidden()
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    cooldown_answers = {
        str(answer).upper() for answer in rotation_cooldown_usage(blacklist)
    }
    pools = {3: short, 6: six, 7: seven}
    ensure_current_records(pools, forbidden, active, cooldown_answers)
    policy = Policy(
        seconds=args.seconds, solution_limit=args.solution_limit,
        minimum_current=args.minimum_current, minimum_strong=args.minimum_strong,
        minimum_familiarity_zipf=args.minimum_familiarity_zipf,
        maximum_unfamiliar=args.maximum_unfamiliar,
        maximum_grammar=args.maximum_grammar,
    )
    search = CurrentShape06Search(
        six=pools[6], seven=pools[7], short=pools[3], active_usage=active,
        cooldown_answers=cooldown_answers, policy=policy, seed=args.seed,
        shape_id=args.shape_id,
    )
    result, candidates = search.solve()
    payload = {
        "version": 1,
        "kind": "motman-corrected-7x8-06-current-life-search",
        "shapeId": args.shape_id,
        "catalogModified": False,
        "runtimeModified": False,
        "publicationEligible": False,
        "currentAnswerSet": sorted(CURRENT),
        "strongAnswerSet": sorted(STRONG),
        "policy": policy.__dict__,
        "activeRepeatPolicy": "score-penalty",
        "rotationCooldownPolicy": "hard-exclusion",
        "poolCounts": {str(k): len(v) for k, v in sorted(pools.items())},
        "sourcePoolCounts": source_counts,
        "telemetry": search.telemetry(result),
        "candidates": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "output": str(args.output), "status": result.value,
        "candidateCount": len(candidates), **payload["telemetry"],
    }, ensure_ascii=False, indent=2))
    return 0 if candidates else 2 if result is SearchResult.DEAD else 3


if __name__ == "__main__":
    raise SystemExit(main())
