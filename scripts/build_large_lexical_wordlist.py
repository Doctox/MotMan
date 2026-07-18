#!/usr/bin/env python3
"""Build a definition-free constructor list from Morphalou and Lexique.

Every acceptable lexical form remains available for geometric closure.  Scores
only order the search; they never make a word publishable.  Definitions are a
separate post-fill editorial step.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MORPHALOU = ROOT / "src/data/crossword.morphalou.staging.json.gz"
LEXIQUE = ROOT / "src/data/lexique.lemmas.json"
CHILD_FORMS = ROOT / "src/data/lexique.child-forms.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
CATALOG = ROOT / "src/data/grid.catalog.json"
DEFAULT_OUTPUT = ROOT / "src/data/fill.wordlist.large.json.gz"
DEFAULT_SUMMARY = ROOT / "src/data/fill.wordlist.large.summary.json"
ALLOWED_POS = {"common-noun", "verb", "adjective", "adverb"}
CURATED_TWO_LETTER = {
    "AS", "AU", "BD", "CB", "CE", "DE", "DU", "EN", "ET", "EU",
    "IA", "IL", "LA", "LE", "LU", "ME", "NI", "ON", "OR", "OS",
    "OU", "PC", "SE", "SI", "TV", "UE", "UN", "VA", "VU", "WC",
}


def normalized(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.upper())
    return "".join(char for char in folded if "A" <= char <= "Z")


def lexical_score(
    source_frequency: float,
    school_frequency: float,
    *,
    form_type: str,
    part_of_speech: str,
    attested_common_form: bool = True,
) -> float:
    """Score commonness/ease while retaining every low-score reserve form."""
    score = 18.0 * math.log10(1.0 + max(0.0, source_frequency))
    score += 4.0 * math.log10(1.0 + max(0.0, school_frequency))
    if form_type == "lemma":
        score += 10.0
    else:
        score -= 4.0
        if not attested_common_form:
            score -= 30.0
    score += {
        "common-noun": 5.0,
        "verb": 4.0,
        "adjective": 2.0,
        "adverb": 1.0,
    }.get(part_of_speech, 0.0)
    if form_type == "inflected" and not attested_common_form:
        score = min(score, 19.0)
    return round(max(0.0, min(100.0, score)), 2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    rejected = set(blacklist.get("rejectedAnswers", []))
    rejected.update(blacklist.get("rejectedEasyAnswers", []))
    rejected.update(blacklist.get("rejectedNormalAnswers", []))
    rejected.update(
        str(item.get("answer", "")).upper()
        for item in blacklist.get("rotationCooldownAnswers", [])
        if item.get("answer")
    )

    lexique_document = json.loads(LEXIQUE.read_text(encoding="utf-8"))
    lemma_metadata = {
        entry["answer"]: entry for entry in lexique_document.get("entries", [])
    }
    child_document = json.loads(CHILD_FORMS.read_text(encoding="utf-8"))
    child_metadata = {
        entry["answer"]: entry for entry in child_document.get("entries", [])
    }
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    active_usage = Counter(
        word["answer"]
        for grid in catalog.get("grids", [])
        for word in grid.get("words", [])
    )

    with gzip.open(MORPHALOU, "rt", encoding="utf-8") as handle:
        morphalou = json.load(handle)

    entries_by_answer: dict[str, dict] = {}
    rejected_by_rule = Counter()
    for entry in morphalou.get("entries", []):
        raw_answer = str(entry.get("answer", ""))
        answer = normalized(raw_answer)
        if not raw_answer.isalpha() or not 3 <= len(answer) <= 9:
            rejected_by_rule["length-or-characters"] += 1
            continue
        if entry.get("partOfSpeech") not in ALLOWED_POS:
            rejected_by_rule["part-of-speech"] += 1
            continue
        if answer in rejected:
            rejected_by_rule["owner-blacklist-or-cooldown"] += 1
            continue
        lemma = str(entry.get("lemmaAnswer") or answer).upper()
        form_type = str(entry.get("formType", ""))
        common_form_evidence = child_metadata.get(answer)
        evidence = (
            common_form_evidence
            if form_type == "inflected" and common_form_evidence is not None
            else lemma_metadata.get(lemma, {})
        )
        source_frequency = float(evidence.get("sourceFrequency", 0.0) or 0.0)
        school_frequency = float(evidence.get("schoolFrequency", 0.0) or 0.0)
        score = lexical_score(
            source_frequency,
            school_frequency,
            form_type=form_type,
            part_of_speech=str(entry.get("partOfSpeech", "")),
            attested_common_form=(
                form_type == "lemma" or common_form_evidence is not None
            ),
        )
        candidate = {
            "answer": answer,
            "length": len(answer),
            "spelling": raw_answer.lower(),
            "lemma": lemma,
            "partOfSpeech": entry.get("partOfSpeech"),
            "formType": entry.get("formType"),
            "attestedCommonForm": (
                form_type == "lemma" or common_form_evidence is not None
            ),
            "sourceFrequency": round(source_frequency, 3),
            "schoolFrequency": round(school_frequency, 3),
            "constructorScore": score,
            "activeUses": int(active_usage.get(answer, 0)),
        }
        previous = entries_by_answer.get(answer)
        if previous is None or score > previous["constructorScore"]:
            entries_by_answer[answer] = candidate

    for answer in sorted(CURATED_TWO_LETTER - rejected):
        entries_by_answer[answer] = {
            "answer": answer,
            "length": 2,
            "spelling": answer.lower(),
            "lemma": answer,
            "partOfSpeech": "curated-short",
            "formType": "curated",
            "attestedCommonForm": True,
            "sourceFrequency": 0.0,
            "schoolFrequency": 0.0,
            "constructorScore": 50.0,
            "activeUses": int(active_usage.get(answer, 0)),
        }

    entries = sorted(
        entries_by_answer.values(), key=lambda item: (item["length"], item["answer"])
    )
    counts = {
        "answers": len(entries),
        "byLength": dict(sorted(Counter(item["length"] for item in entries).items())),
        "byPartOfSpeech": dict(sorted(Counter(
            item["partOfSpeech"] for item in entries
        ).items())),
        "byFormType": dict(sorted(Counter(
            item["formType"] for item in entries
        ).items())),
        "withLexiqueFrequency": sum(
            item["sourceFrequency"] > 0 or item["schoolFrequency"] > 0
            for item in entries
        ),
        "neverUsedInActiveCatalog": sum(item["activeUses"] == 0 for item in entries),
        "rejectedByRule": dict(sorted(rejected_by_rule.items())),
    }
    payload = {
        "version": 1,
        "kind": "motman-large-definition-free-constructor-wordlist",
        "policy": {
            "purpose": "geometric placement only",
            "definitionsUsedForPlacement": False,
            "definitionRequiredAfterCandidateSelection": True,
            "lowScoreReserveFormsRetained": True,
            "source": "Morphalou 3.1 + Lexique frequency metadata",
            "blacklistSha256": hashlib.sha256(BLACKLIST.read_bytes()).hexdigest(),
        },
        "counts": counts,
        "entries": entries,
    }
    summary = {
        "version": 1,
        "kind": payload["kind"] + "-summary",
        "output": str(args.output),
        "policy": payload["policy"],
        "counts": counts,
        "scoreBands": {
            "70plus": sum(item["constructorScore"] >= 70 for item in entries),
            "50to69": sum(50 <= item["constructorScore"] < 70 for item in entries),
            "30to49": sum(30 <= item["constructorScore"] < 50 for item in entries),
            "under30Reserve": sum(item["constructorScore"] < 30 for item in entries),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
