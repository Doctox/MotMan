#!/usr/bin/env python3
"""Construct one 7x8 fill by alternating reviewed short anchors and word zones.

This is deliberately not a catalogue generator.  It targets the single-pivot
7x8 geometry, prunes every row as soon as one vertical prefix becomes dead,
and writes only the best complete fill found for later human review.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path

from wordfreq import iter_wordlist, zipf_frequency

from build_compact_7x8_review import family_key
from editorial_fill_quality import answer_usage
from scan_reviewed_single_anchor_7x8 import PILOT_EXCLUDED, next_pilot_exclusions
from search_compact_grid_pilot import (
    PILOT_REVIEWED_CURRENT_SHORT,
    PILOT_SAFE_SHORT,
    excluded_answers,
    load_editorial_rescue_entries,
    normalized,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESCUE = ROOT / "src/data/grid-generation/editorial-rescue.young-common.20260721.json"
DEFAULT_CATALOG = ROOT / "src/data/grid.catalog.json"
DEFAULT_OUTPUT = ROOT / "output/quality/semi-manual-7x8-candidate/zone-fill.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rescue", type=Path, default=DEFAULT_RESCUE)
    parser.add_argument("--reference-catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-zipf", type=float, default=2.5)
    parser.add_argument("--seconds", type=float, default=180.0)
    parser.add_argument("--row-limit", type=int, default=5000)
    parser.add_argument("--solution-limit", type=int, default=40)
    parser.add_argument("--top-short")
    parser.add_argument("--bottom-short")
    return parser.parse_args()


def load_candidates(args: argparse.Namespace):
    excluded = excluded_answers([]) | next_pilot_exclusions() | PILOT_EXCLUDED
    usage = answer_usage([args.reference_catalog])
    with gzip.open(ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8") as stream:
        large_entries = json.load(stream).get("entries", [])
    lexical = {}
    for item in large_entries:
        answer = normalized(str(item.get("answer", "")))
        if answer and answer not in lexical:
            lexical[answer] = item

    rescue_entries = load_editorial_rescue_entries(args.rescue)
    rescue = {item["answer"]: item for item in rescue_entries}
    current = {
        item["answer"] for item in rescue_entries
        if str(item.get("register") or "").startswith("current-")
    } | PILOT_REVIEWED_CURRENT_SHORT

    by_length: dict[int, dict[str, dict]] = {3: {}, 5: {}, 6: {}, 7: {}}
    for spelling in iter_wordlist("fr"):
        frequency = float(zipf_frequency(spelling, "fr"))
        if frequency < args.minimum_zipf:
            break
        if not spelling.isalpha():
            continue
        answer = normalized(spelling)
        if len(answer) not in by_length or answer in excluded or answer in by_length[len(answer)]:
            continue
        item = lexical.get(answer)
        if len(answer) == 3 and answer not in PILOT_SAFE_SHORT:
            continue
        is_inflected_verb = bool(
            item and item.get("partOfSpeech") == "verb" and item.get("formType") != "lemma"
        )
        is_unreviewed_proper = bool(
            item and item.get("partOfSpeech") == "proper-noun" and answer not in rescue
        )
        source = (
            "inflected-review-required"
            if is_inflected_verb
            else
            "proper-name-review-required"
            if is_unreviewed_proper
            else "large-attested"
            if item and item.get("attestedCommonForm") is True
            else "wordfreq-review-required"
        )
        score = 10.0 * frequency
        if source == "large-attested":
            score += 18.0
        elif source == "proper-name-review-required":
            score -= 30.0
        elif source == "inflected-review-required":
            score -= 45.0
        if answer in rescue:
            score += 70.0
        if answer in current:
            score += 35.0
        score -= min(36.0, 12.0 * usage.get(answer, 0))
        by_length[len(answer)][answer] = {
            "answer": answer,
            "spelling": spelling,
            "zipf": frequency,
            "score": score,
            "source": source,
            "partOfSpeech": (item or {}).get("partOfSpeech"),
            "formType": (item or {}).get("formType"),
            "register": (rescue.get(answer) or {}).get("register"),
        }

    for answer, item in rescue.items():
        if len(answer) not in by_length or answer in excluded:
            continue
        frequency = float(zipf_frequency(str(item.get("spelling") or answer).lower(), "fr"))
        by_length[len(answer)][answer] = {
            "answer": answer,
            "spelling": item.get("spelling") or answer.lower(),
            "zipf": frequency,
            "score": 120.0 + (35.0 if answer in current else 0.0) - min(36.0, 12.0 * usage.get(answer, 0)),
            "source": "human-reviewed-rescue",
            "partOfSpeech": item.get("partOfSpeech"),
            "formType": item.get("formType"),
            "register": item.get("register"),
        }
    return by_length, current, usage


def search(args: argparse.Namespace) -> dict:
    pools, current_answers, usage = load_candidates(args)
    columns = sorted(pools[7])
    prefix_sets = {length: {word[:length] for word in columns} for length in range(1, 8)}
    prefix_support = {
        length: Counter(word[:length] for word in columns)
        for length in range(1, 8)
    }
    by_answer = {length: pools[length] for length in pools}
    row5 = sorted(by_answer[5], key=lambda word: (-by_answer[5][word]["score"], word))[:args.row_limit]
    rows6_by_last: dict[str, list[str]] = defaultdict(list)
    for word, metadata in by_answer[6].items():
        rows6_by_last[word[-1]].append(word)
    for letter, words in rows6_by_last.items():
        words.sort(key=lambda word: (-by_answer[6][word]["score"], word))
        rows6_by_last[letter] = words[:args.row_limit]

    reviewed_current_short = sorted(
        answer for answer in current_answers if len(answer) == 3 and answer in by_answer[3]
    )
    daily_short = sorted(
        answer for answer in PILOT_SAFE_SHORT
        if len(answer) == 3 and answer in by_answer[3]
    )
    short_pairs = [
        (top, bottom)
        for top in daily_short for bottom in daily_short
        if top != bottom and family_key(top) != family_key(bottom)
    ]

    def pair_priority(pair: tuple[str, str]) -> tuple:
        top, bottom = pair
        feasibility = sum(
            math.log1p(len(rows6_by_last.get(letter, ())))
            for letter in top + bottom
        )
        current_count = int(top in current_answers) + int(bottom in current_answers)
        return (-(feasibility + 0.7 * current_count), -current_count, top, bottom)

    short_pairs.sort(key=pair_priority)
    if args.top_short or args.bottom_short:
        if not args.top_short or not args.bottom_short:
            raise ValueError("--top-short et --bottom-short doivent être fournis ensemble")
        requested_pair = (normalized(args.top_short), normalized(args.bottom_short))
        if any(answer not in daily_short for answer in requested_pair):
            raise ValueError(f"Couple court non relu ou indisponible : {requested_pair}")
        short_pairs = [requested_pair]

    deadline = time.perf_counter() + args.seconds
    explored = 0
    complete: list[dict] = []

    def recurse(depth: int, prefixes: tuple[str, ...], rows: list[str], used_families: set[str], top: str, bottom: str, pair_complete: list[int]):
        nonlocal explored
        if (
            time.perf_counter() >= deadline
            or len(complete) >= args.solution_limit
            or pair_complete[0] >= 3
        ):
            return
        if depth == 7:
            column_words = list(prefixes)
            answers = [*column_words, top, *rows, bottom]
            if len(set(answers)) != len(answers):
                return
            families = [family_key(answer) for answer in answers]
            if len(set(families)) != len(families):
                return
            current_hits = sorted(set(answers) & current_answers)
            score = sum(
                by_answer[len(answer)][answer]["score"]
                for answer in answers
            ) + 250.0 * len(current_hits)
            complete.append({
                "score": round(score, 3),
                "topShort": top,
                "bottomShort": bottom,
                "rows": list(rows),
                "columns": column_words,
                "currentAnswers": current_hits,
                "activeRepeats": sorted(answer for answer in answers if usage.get(answer, 0)),
            })
            pair_complete[0] += 1
            return

        if depth == 3:
            candidates = row5
        else:
            short = top if depth < 3 else bottom
            short_position = depth if depth < 3 else depth - 4
            candidates = rows6_by_last.get(short[short_position], [])
        viable = []
        target_length = depth + 1
        for word in candidates:
            family = family_key(word)
            if family in used_families:
                continue
            next_prefixes = tuple(prefixes[index] + word[index] for index in range(5))
            if any(prefix not in prefix_sets[target_length] for prefix in next_prefixes):
                continue
            supports = [prefix_support[target_length][prefix] for prefix in next_prefixes]
            viable.append((min(supports), sum(supports), by_answer[len(word)][word]["score"], word, family, next_prefixes))
        viable.sort(key=lambda item: (
            item[0], item[1], -item[2], item[3]
        ))
        branch_limit = 1400 if depth < 2 else 900
        for _minimum_support, _support_sum, _score, word, family, next_prefixes in viable[:branch_limit]:
            explored += 1
            recurse(
                depth + 1, next_prefixes, [*rows, word],
                used_families | {family}, top, bottom, pair_complete,
            )
            if (
                time.perf_counter() >= deadline
                or len(complete) >= args.solution_limit
                or pair_complete[0] >= 3
            ):
                return

    for top, bottom in short_pairs:
        pair_complete = [0]
        recurse(
            0, ("", "", "", "", ""), [],
            {family_key(top), family_key(bottom)}, top, bottom, pair_complete,
        )
        if time.perf_counter() >= deadline or len(complete) >= args.solution_limit:
            break

    complete.sort(key=lambda item: (
        -len(item["currentAnswers"]),
        len(item["activeRepeats"]),
        -item["score"],
        item["rows"],
    ))
    best = complete[0] if complete else None
    if best:
        all_answers = [*best["columns"], best["topShort"], *best["rows"], best["bottomShort"]]
        best["metadata"] = {
            answer: by_answer[len(answer)][answer] for answer in all_answers
        }
    return {
        "version": 1,
        "kind": "motman-semi-manual-zone-fill",
        "columns": 7,
        "rows": 8,
        "sourceShapeId": "corrected-7x8-02",
        "pivot": [4, 6],
        "catalogModified": False,
        "runtimeModified": False,
        "supabaseModified": False,
        "publicationEligible": False,
        "complete": best is not None,
        "best": best,
        "telemetry": {
            "elapsedSeconds": round(args.seconds - max(0.0, deadline - time.perf_counter()), 3),
            "exploredRows": explored,
            "completeFills": len(complete),
            "shortPairCount": len(short_pairs),
            "rowCandidateCounts": {str(length): len(pool) for length, pool in by_answer.items()},
        },
    }


def main() -> int:
    args = parse_args()
    payload = search(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "complete": payload["complete"],
        "best": payload["best"],
        "telemetry": payload["telemetry"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if payload["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
