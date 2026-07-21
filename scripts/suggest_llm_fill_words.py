#!/usr/bin/env python3
"""Suggest natural words for one letter pattern without filling a whole grid."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import unicodedata
from pathlib import Path

from build_compact_7x8_review import family_key


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BRIEF = (
    ROOT / "src/data/grid-generation-handcrafted/llm-first-unavailable-answers.json"
)


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.upper())
    return "".join(character for character in folded if "A" <= character <= "Z")


def compile_pattern(value: str) -> re.Pattern[str]:
    cleaned = "".join("?" if character in "?._-" else character for character in value.upper())
    if not cleaned or any(character != "?" and not "A" <= character <= "Z" for character in cleaned):
        raise ValueError("Le motif doit contenir seulement A-Z et ?")
    return re.compile("^" + cleaned.replace("?", ".") + "$")


def candidate_score(item: dict) -> float:
    return (
        float(item.get("constructorScore") or 0.0)
        + float(item.get("sourceFrequency") or 0.0) * 8.0
        + float(item.get("schoolFrequency") or 0.0) * 12.0
        + (8.0 if item.get("attestedCommonForm") is True else 0.0)
        + (4.0 if normalize(str(item.get("answer", ""))) == normalize(str(item.get("lemma", ""))) else 0.0)
    )


def suggestions(
    pattern: str, brief_path: Path, limit: int, minimum_score: float = 15.0
) -> list[dict]:
    matcher = compile_pattern(pattern)
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    forbidden = set(brief.get("forbiddenAnswers", []))
    forbidden_families = set(brief.get("activeFamilies", []))
    with gzip.open(ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8") as stream:
        entries = json.load(stream).get("entries", [])
    selected = []
    seen = set()
    for item in entries:
        answer = normalize(str(item.get("answer", "")))
        if (
            not answer
            or answer in seen
            or answer in forbidden
            or not matcher.fullmatch(answer)
            or str(item.get("partOfSpeech") or "") == "proper-noun"
        ):
            continue
        if family_key(answer) in forbidden_families:
            continue
        seen.add(answer)
        score = candidate_score(item)
        if score < minimum_score:
            continue
        selected.append({
            "answer": answer,
            "spelling": str(item.get("spelling") or answer.lower()),
            "lemma": normalize(str(item.get("lemma") or answer)),
            "partOfSpeech": str(item.get("partOfSpeech") or ""),
            "constructorScore": float(item.get("constructorScore") or 0.0),
            "sourceFrequency": float(item.get("sourceFrequency") or 0.0),
            "schoolFrequency": float(item.get("schoolFrequency") or 0.0),
            "attestedCommonForm": item.get("attestedCommonForm") is True,
            "suggestionScore": round(score, 3),
        })
    selected.sort(key=lambda item: (-item["suggestionScore"], item["answer"]))
    return selected[:limit]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pattern")
    parser.add_argument("--brief", type=Path, default=DEFAULT_BRIEF)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--minimum-score", type=float, default=15.0)
    args = parser.parse_args()
    print(json.dumps(
        suggestions(args.pattern, args.brief, args.limit, args.minimum_score),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
