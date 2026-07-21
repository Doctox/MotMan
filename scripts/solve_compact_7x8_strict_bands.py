#!/usr/bin/env python3
"""Specialised exact solver for the strict 7×8 three-pivot silhouette.

The silhouette decomposes into two 3×6 bands, joined by one three-letter row
and three seven-letter columns. Exploiting that structure compares far more
complete fills than generic cell-by-cell backtracking in the same time.
"""
from __future__ import annotations

import argparse
import gzip
import heapq
import itertools
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from wordfreq import zipf_frequency

from build_compact_7x8_review import family_key
from search_compact_grid_pilot import (
    GRAMMAR_ANSWERS,
    PILOT_REVIEWED_LONG,
    PILOT_SAFE_SHORT,
    rotation_cooldown_usage,
)


ROOT = Path(__file__).resolve().parents[1]
POP_LONG = set(PILOT_REVIEWED_LONG) | {"AVATAR"}
SENSITIVE_OR_MISLEADING_SHORT = {
    "CON", "CUL", "GAY", "HIV", "HOT", "SEX", "SS", "WC",
}
CURRENT_COMMON_SHORT = {
    "API", "APP", "ARN", "BAC", "BIO", "BOT", "BOX", "BUG", "BUS",
    "BUT", "CDI", "CPE", "FAC", "FAQ", "GIF", "GPS", "GPU", "IRM",
    "JOB", "LAB", "LAN", "LED", "MDR", "PDF", "PME", "RAP", "RER",
    "RIB", "RPG", "SIM", "SMS", "TGV", "TPE", "TVA", "ULM", "USB",
    "URL", "VPN", "VTT", "WEB", "WII", "WOW", "ZOO",
    # Extensions relues pour le pilote 16-45 ans. Ce sont des mots, sigles ou
    # noms propres que l'on peut définir honnêtement en une case mobile. Leur
    # présence dans cette liste ne vaut pas validation automatique du couple.
    "ADO", "ALU", "ANE", "ARE", "AYA", "BMX", "BOA", "BOB", "BTS",
    "CAF", "CAM", "CEP", "CIL", "COL", "COQ", "EPI", "EVA", "FAC",
    "FAX", "FBI", "FIG", "FOX", "FUN", "GAG", "GEL", "GTA", "HIT",
    "HUB", "KFC", "KID", "KIT", "LEO", "LOL", "LOU", "MAT", "MIA",
    "MIX", "MMO", "NBA", "NEM", "NID", "NOE", "ONG", "PAN", "POT",
    "QCM", "RAM", "RAT", "RIO", "ROC", "ROM", "RSA", "SAM", "SET",
    "SVP", "TAF", "TAG", "TEE", "TIC", "TNT", "VIP", "WOK", "YEN",
    "ZIP", "ARA", "ENA", "KIR", "NEO", "OMS", "RTT", "TTC",
}


@dataclass(frozen=True)
class Band:
    rows: tuple[str, str, str]
    short_columns: tuple[str, str, str]
    first_columns: tuple[str, str, str]
    score: float


def build_bands(
    six_words: list[str], short_words: set[str], scores: dict[str, float], limit: int,
    *, long_columns: int = 3, row_choice_limit: int = 5,
    bands_per_prefix: int = 3,
) -> list[Band]:
    short_column_count = 6 - long_columns
    six_by_tail: dict[str, list[str]] = defaultdict(list)
    for word in six_words:
        six_by_tail[word[long_columns:]].append(word)
    for words in six_by_tail.values():
        words.sort(key=lambda word: (-scores[word], word))
    short_next: dict[str, set[str]] = defaultdict(set)
    for word in short_words:
        short_next[word[:2]].add(word[2])

    heaps_by_first: dict[tuple[str, str, str], list[tuple[float, int, Band]]] = defaultdict(list)
    serial = 0
    tails = sorted(six_by_tail)
    # Work on distinct row endings rather than all word pairs. Two
    # endings determine the allowed third letter in each short column; the
    # third ending is therefore a direct lookup.
    for first_tail in tails:
        for second_tail in tails:
            choices = [short_next.get(
                first_tail[pos] + second_tail[pos], set()
            ) for pos in range(short_column_count)]
            if any(not choice for choice in choices):
                continue
            for third_tail_tuple in itertools.product(*choices):
                third_tail = "".join(third_tail_tuple)
                if third_tail not in six_by_tail:
                    continue
                short_columns = tuple(
                    first_tail[pos] + second_tail[pos] + third_tail[pos]
                    for pos in range(short_column_count)
                )
                if len(set(short_columns)) != len(short_columns):
                    continue
                row_choices = (
                    six_by_tail[first_tail][:row_choice_limit],
                    six_by_tail[second_tail][:row_choice_limit],
                    six_by_tail[third_tail][:row_choice_limit],
                )
                for first, second, third in itertools.product(*row_choices):
                    if len({first, second, third}) != 3:
                        continue
                    rows = (first, second, third)
                    families = [family_key(word) for word in rows]
                    if len(set(families)) != 3:
                        continue
                    first_columns = tuple(
                        "".join(row[pos] for row in rows) for pos in range(long_columns)
                    )
                    score = sum(scores[word] for word in (*rows, *short_columns))
                    band = Band(rows, short_columns, first_columns, score)
                    serial += 1
                    item = (score, serial, band)
                    local = heaps_by_first[first_columns]
                    # Preserve structural diversity: bottom-band compatibility
                    # depends on these three prefixes, so a global top-N alone
                    # can erase every viable continuation.
                    if len(local) < bands_per_prefix:
                        heapq.heappush(local, item)
                    elif score > local[0][0]:
                        heapq.heapreplace(local, item)
    items = [item for local in heaps_by_first.values() for item in local]
    if len(items) > limit:
        items = heapq.nlargest(limit, items)
    else:
        items.sort(reverse=True)
    return [item[2] for item in items]


def solve_bands(
    bands: list[Band],
    middle_words: set[str],
    seven_words: list[str],
    scores: dict[str, float],
    *,
    solution_limit: int,
) -> list[dict]:
    bands_by_first: dict[tuple[str, str, str], list[Band]] = defaultdict(list)
    for band in bands:
        bands_by_first[band.first_columns].append(band)
    seven_by_top_middle: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for word in seven_words:
        seven_by_top_middle[(word[:3], word[3])].append((word[4:], word))

    heap: list[tuple[float, int, dict]] = []
    serial = 0
    for top in bands:
        for middle in middle_words:
            if middle in top.short_columns:
                continue
            vertical_choices = [
                seven_by_top_middle.get((prefix, middle[position]), [])
                for position, prefix in enumerate(top.first_columns)
            ]
            if any(not choices for choices in vertical_choices):
                continue
            for chosen in itertools.product(*vertical_choices):
                bottom_key = tuple(item[0] for item in chosen)
                for bottom in bands_by_first.get(bottom_key, []):
                    verticals = tuple(item[1] for item in chosen)
                    answers = (
                        *verticals,
                        *top.short_columns,
                        *top.rows,
                        middle,
                        *bottom.short_columns,
                        *bottom.rows,
                    )
                    if len(set(answers)) != len(answers):
                        continue
                    families = [family_key(answer) for answer in answers]
                    if len(set(families)) != len(families):
                        continue
                    score = sum(scores[answer] for answer in answers)
                    serial += 1
                    record = {
                        "answers": list(answers),
                        "score": round(score, 3),
                        "topBand": {
                            "rows": list(top.rows),
                            "shortColumns": list(top.short_columns),
                        },
                        "middle": middle,
                        "bottomBand": {
                            "rows": list(bottom.rows),
                            "shortColumns": list(bottom.short_columns),
                        },
                        "verticals": list(verticals),
                    }
                    item = (score, serial, record)
                    if len(heap) < solution_limit:
                        heapq.heappush(heap, item)
                    elif score > heap[0][0]:
                        heapq.heapreplace(heap, item)
    return [item[2] for item in sorted(heap, reverse=True)]


def load_pools() -> tuple[
    list[str], dict[int, set[str]], list[str], dict[str, float], dict[str, dict]
]:
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    blocked = {str(answer).upper() for answer in blacklist.get("rejectedAnswers", [])}
    active = Counter()
    catalog = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    active.update(
        str(word.get("answer", "")).upper()
        for grid in catalog.get("grids", []) for word in grid.get("words", [])
    )
    for answer, historical_uses in rotation_cooldown_usage(blacklist).items():
        active[answer] = max(active[answer], historical_uses)
    with gzip.open(ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8") as stream:
        entries = json.load(stream).get("entries", [])
    metadata = {str(item["answer"]): item for item in entries}
    scores: dict[str, float] = {}
    six_words = []
    seven_words = []
    for item in entries:
        answer = str(item["answer"])
        if answer in blocked or len(answer) not in {6, 7}:
            continue
        part_of_speech = item.get("partOfSpeech")
        form_type = item.get("formType")
        is_natural_plural_or_feminine = (
            form_type == "inflected"
            and part_of_speech in {"common-noun", "adjective"}
            and item.get("attestedCommonForm", False)
        )
        if (
            form_type != "lemma" and not is_natural_plural_or_feminine
        ) or part_of_speech not in {
            "common-noun", "adjective", "adverb", "verb",
        }:
            continue
        zipf = float(zipf_frequency(str(item.get("spelling") or answer).lower(), "fr"))
        constructor = float(item.get("constructorScore") or 0.0)
        if is_natural_plural_or_feminine:
            if zipf < 3.0 or constructor < 15:
                continue
        elif zipf < 2.0 or constructor < 5:
            continue
        scores[answer] = constructor + 7.0 * zipf - 12.0 * active.get(answer, 0)
        (six_words if len(answer) == 6 else seven_words).append(answer)
    for answer in POP_LONG:
        if answer in blocked or len(answer) not in {6, 7}:
            continue
        scores[answer] = max(scores.get(answer, 0.0), 95.0 - 12.0 * active.get(answer, 0))
        metadata.setdefault(answer, {
            "answer": answer,
            "spelling": answer.lower(),
            "partOfSpeech": "proper-noun",
            "formType": "lemma",
            "constructorScore": 65.0,
            "activeUses": active.get(answer, 0),
        })
        target = six_words if len(answer) == 6 else seven_words
        if answer not in target:
            target.append(answer)

    short_words = {
        answer for answer in PILOT_SAFE_SHORT
        if len(answer) == 3
        and answer not in blocked
        and answer not in GRAMMAR_ANSWERS
        and float(zipf_frequency(answer.lower(), "fr")) >= 2.6
    }
    short_words.update(
        str(item["answer"])
        for item in entries
        if item.get("length") == 3
        and item.get("formType") == "lemma"
        and item.get("partOfSpeech") in {"common-noun", "adjective", "adverb", "verb"}
        and float(item.get("constructorScore") or 0.0) >= 20
        and float(zipf_frequency(str(item.get("spelling") or item["answer"]).lower(), "fr")) >= 3.0
    )
    short_words.update(answer for answer in CURRENT_COMMON_SHORT if answer not in blocked)
    short_words.difference_update(blocked | GRAMMAR_ANSWERS | SENSITIVE_OR_MISLEADING_SHORT)
    for answer in short_words:
        item = metadata.get(answer, {})
        scores[answer] = max(
            70.0 if answer in CURRENT_COMMON_SHORT else 0.0,
            float(item.get("constructorScore") or 30.0)
            + 7.0 * float(zipf_frequency(answer.lower(), "fr"))
            - 12.0 * active.get(answer, 0)
        )
    middle_words: dict[int, set[str]] = {3: set(short_words), 4: set(), 5: set()}
    for item in entries:
        answer = str(item["answer"])
        length = len(answer)
        if length not in {4, 5} or answer in blocked:
            continue
        if item.get("formType") != "lemma" or item.get("partOfSpeech") not in {
            "common-noun", "adjective", "adverb", "verb",
        }:
            continue
        zipf = float(zipf_frequency(str(item.get("spelling") or answer).lower(), "fr"))
        constructor = float(item.get("constructorScore") or 0.0)
        if zipf < 3.0 or constructor < 20:
            continue
        scores[answer] = constructor + 7.0 * zipf - 12.0 * active.get(answer, 0)
        middle_words[length].add(answer)
    for answer in {"DOFUS", "MARIO"}:
        if answer not in blocked:
            scores[answer] = 95.0 - 12.0 * active.get(answer, 0)
            middle_words[5].add(answer)
    six_words.sort(key=lambda word: (-scores[word], word))
    seven_words.sort(key=lambda word: (-scores[word], word))
    return six_words, middle_words, seven_words, scores, metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--band-limit", type=int, default=20_000)
    parser.add_argument("--solution-limit", type=int, default=500)
    parser.add_argument("--row-choice-limit", type=int, default=5)
    parser.add_argument("--bands-per-prefix", type=int, default=3)
    parser.add_argument(
        "--shape-id",
        choices=("pilot-7x8-strict-02", "pilot-7x8-strict-03", "pilot-7x8-strict-04"),
        default="pilot-7x8-strict-04",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    six_words, middle_words, seven_words, scores, metadata = load_pools()
    long_columns = {
        "pilot-7x8-strict-02": 5,
        "pilot-7x8-strict-03": 4,
        "pilot-7x8-strict-04": 3,
    }[args.shape_id]
    short_words = middle_words[3]
    bands = build_bands(
        six_words, short_words, scores, args.band_limit,
        long_columns=long_columns,
        row_choice_limit=args.row_choice_limit,
        bands_per_prefix=args.bands_per_prefix,
    )
    solutions = solve_bands(
        bands, middle_words[long_columns], seven_words, scores,
        solution_limit=args.solution_limit,
    )
    payload = {
        "version": 1,
        "kind": "motman-strict-7x8-band-solver",
        "shapeId": args.shape_id,
        "catalogModified": False,
        "publicationEligible": False,
        "poolCounts": {
            "sixLetters": len(six_words),
            "threeLetters": len(short_words),
            "middleWords": len(middle_words[long_columns]),
            "sevenLetters": len(seven_words),
            "bandsKept": len(bands),
            "rowChoiceLimit": args.row_choice_limit,
            "bandsPerPrefix": args.bands_per_prefix,
        },
        "solutionCount": len(solutions),
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "solutions": solutions,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "output": str(args.output),
        "poolCounts": payload["poolCounts"],
        "solutionCount": len(solutions),
        "elapsedSeconds": payload["elapsedSeconds"],
    }, ensure_ascii=False, indent=2))
    return 0 if solutions else 2


if __name__ == "__main__":
    raise SystemExit(main())
