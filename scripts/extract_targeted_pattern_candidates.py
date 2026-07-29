#!/usr/bin/env python3
"""Find reviewed/natural words that repair observed crossing wipeouts."""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from wordfreq import zipf_frequency

from scan_reviewed_single_anchor_7x8 import strict_construction_indexes
from search_compact_grid_pilot import excluded_answers, normalized


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAMPAIGN = ROOT / "output/quality/semi-editorial-7x8-pilot/remaining-single-anchor-patterns.json"
DEFAULT_RESCUE = ROOT / "src/data/grid-generation/editorial-rescue.young-common.20260721.json"
DEFAULT_OUTPUT = ROOT / "output/quality/semi-editorial-7x8-pilot/targeted-pattern-candidates.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument("--rescue-file", type=Path, default=DEFAULT_RESCUE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-zipf", type=float, default=3.0)
    parser.add_argument("--maximum-results", type=int, default=250)
    return parser.parse_args()


def matches(pattern: str, answer: str) -> bool:
    return len(pattern) == len(answer) and all(
        expected == "?" or expected == actual
        for expected, actual in zip(pattern, answer)
    )


def aggregated_failures(campaign: dict) -> Counter[tuple]:
    failures: Counter[tuple] = Counter()
    for result in campaign.get("results", []):
        for item in result.get("telemetry", {}).get("failurePatterns", []):
            key = (
                item["leftPattern"], int(item["leftPosition"]),
                tuple(item.get("leftLetters", [])),
                item["rightPattern"], int(item["rightPosition"]),
                tuple(item.get("rightLetters", [])),
            )
            failures[key] += int(item.get("count", 1))
    return failures


def candidate_sources(minimum_zipf: float) -> dict[str, dict]:
    excluded = excluded_answers([])
    candidates: dict[str, dict] = {}
    with gzip.open(
        ROOT / "src/data/crossword.central.json.gz", "rt", encoding="utf-8"
    ) as stream:
        central = json.load(stream).get("entries", [])
    for item in central:
        answer = normalized(str(item.get("answer", "")))
        if (
            not 3 <= len(answer) <= 7
            or answer in excluded
            or item.get("editorialStatus") not in {"human-reviewed", "image-reviewed"}
            or item.get("generatorEligible") is not True
            or item.get("canonicalForGenerator") is not True
        ):
            continue
        current = candidates.get(answer)
        candidate = {
            "answer": answer,
            "spelling": item.get("answer"),
            "source": "central-human-reviewed",
            "editorialStatus": item.get("editorialStatus"),
            "clue": item.get("clue"),
            "sourceId": item.get("sourceId"),
            "partOfSpeech": item.get("partOfSpeech"),
            "formType": "editorial-reviewed",
            "wordfreqZipf": float(zipf_frequency(answer.lower(), "fr")),
            "constructorScore": None,
        }
        if current is None or current["source"] != "central-human-reviewed":
            candidates[answer] = candidate

    with gzip.open(
        ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8"
    ) as stream:
        large = json.load(stream).get("entries", [])
    for item in large:
        answer = normalized(str(item.get("answer", "")))
        spelling = str(item.get("spelling") or answer.lower())
        zipf = float(zipf_frequency(spelling, "fr"))
        if (
            answer in candidates
            or not 3 <= len(answer) <= 7
            or answer in excluded
            or item.get("attestedCommonForm") is not True
            or item.get("partOfSpeech") == "proper-noun"
            or (
                item.get("partOfSpeech") == "verb"
                and item.get("formType") != "lemma"
            )
            or zipf < minimum_zipf
        ):
            continue
        candidates[answer] = {
            "answer": answer,
            "spelling": spelling,
            "source": "large-frequent-lemma-review-required",
            "editorialStatus": "review-required",
            "clue": None,
            "sourceId": None,
            "partOfSpeech": item.get("partOfSpeech"),
            "formType": item.get("formType"),
            "wordfreqZipf": zipf,
            "constructorScore": float(item.get("constructorScore", 0.0)),
        }
    return candidates


def main() -> int:
    args = parse_args()
    campaign = json.loads(args.campaign.read_text(encoding="utf-8"))
    failures = aggregated_failures(campaign)
    lengths = {
        len(pattern)
        for key in failures for pattern in (key[0], key[3])
    }
    strict_indexes, _metadata, _rescue, _current = strict_construction_indexes(
        lengths, args.rescue_file, 3.2, 5.0
    )
    strict_answers = {
        answer for words in strict_indexes[0].values() for answer in words
    }
    candidates = candidate_sources(args.minimum_zipf)
    support_counts: Counter[str] = Counter()
    support_details: dict[str, list[dict]] = defaultdict(list)
    for key, occurrence_count in failures.items():
        left_pattern, left_position, left_letters = key[:3]
        right_pattern, right_position, right_letters = key[3:]
        for answer, metadata in candidates.items():
            if answer in strict_answers:
                continue
            repairs = []
            if (
                matches(left_pattern, answer)
                and answer[left_position] in right_letters
            ):
                repairs.append("left")
            if (
                matches(right_pattern, answer)
                and answer[right_position] in left_letters
            ):
                repairs.append("right")
            if not repairs:
                continue
            support_counts[answer] += occurrence_count
            if len(support_details[answer]) < 8:
                support_details[answer].append({
                    "occurrenceCount": occurrence_count,
                    "repairs": repairs,
                    "leftPattern": left_pattern,
                    "leftPosition": left_position,
                    "leftLetters": list(left_letters),
                    "rightPattern": right_pattern,
                    "rightPosition": right_position,
                    "rightLetters": list(right_letters),
                })

    ranked = sorted(
        support_counts,
        key=lambda answer: (
            -support_counts[answer],
            0 if candidates[answer]["source"] == "central-human-reviewed" else 1,
            -float(candidates[answer]["wordfreqZipf"]),
            answer,
        ),
    )
    results = [
        {
            **candidates[answer],
            "repairSupportCount": support_counts[answer],
            "supports": support_details[answer],
            "admitted": False,
            "reviewDecision": "pending",
        }
        for answer in ranked[:args.maximum_results]
    ]
    payload = {
        "version": 1,
        "kind": "motman-targeted-crossing-pattern-candidates",
        "campaign": str(args.campaign),
        "catalogModified": False,
        "publicationEligible": False,
        "failurePatternCount": len(failures),
        "failureEventCount": sum(failures.values()),
        "candidateCount": len(results),
        "policy": {
            "central": "human-reviewed/image-reviewed and generator canonical only",
            "large": "frequent attested lemmas only; still requires explicit review",
            "automaticAdmission": False,
        },
        "candidates": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "failurePatternCount": len(failures),
        "failureEventCount": sum(failures.values()),
        "candidateCount": len(results),
        "topCandidates": [
            {
                "answer": item["answer"],
                "source": item["source"],
                "wordfreqZipf": item["wordfreqZipf"],
                "repairSupportCount": item["repairSupportCount"],
                "clue": item["clue"],
            }
            for item in results[:40]
        ],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
