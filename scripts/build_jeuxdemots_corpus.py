"""Build the JeuxDeMots-only French editorial reservoir.

Relations are useful source evidence, not automatically playable clues.  This
file deliberately excludes DBnary and keeps several relations per answer so
the editorial team can choose a natural short clue instead of accepting the
first synonym encountered.
"""
from __future__ import annotations

import argparse
import gzip
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import build_open_synonym_corpus as lexical


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
DEFAULT_OUTPUT = DATA / "crossword.jeuxdemots.review.json.gz"
MINIMUM_FREQUENCY = 0.1
MAXIMUM_RELATIONS_PER_ANSWER = 16
MINIMUM_DISTINCT_ANSWERS = 14_000


def atomic_write_gzip_json(path: Path, document: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with gzip.open(temporary, "wt", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
        for attempt in range(6):
            try:
                temporary.replace(path)
                return
            except OSError:
                if attempt == 5:
                    raise
                time.sleep(0.5 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def relation_priority(entry: dict) -> tuple:
    return (
        int(entry.get("sourceRelationWeight", 0)),
        float(entry.get("minimumSourceFrequency", 0)),
        float(entry.get("clueSourceFrequency", 0)),
        -len(entry.get("clue", "")),
        entry.get("clue", "").casefold(),
    )


def select_relations(candidates: dict[str, dict[str, dict]]) -> tuple[list[dict], Counter]:
    metrics = Counter()
    selected = []
    for answer in sorted(candidates):
        choices = sorted(
            candidates[answer].values(), key=relation_priority, reverse=True
        )
        metrics["eligibleBeforeAnswerCap"] += len(choices)
        for entry in choices[:MAXIMUM_RELATIONS_PER_ANSWER]:
            selected.append({
                **entry,
                "confidence": "community-relation-not-clue",
                "editorialStatus": "jeuxdemots-review-required",
                "reviewRequired": True,
                "playableAsIs": False,
                "generatorEligible": False,
            })
        metrics["removedByAnswerCap"] += max(
            0, len(choices) - MAXIMUM_RELATIONS_PER_ANSWER
        )
    selected.sort(
        key=lambda entry: (entry["length"], entry["answer"], entry["clue"].casefold())
    )
    return selected, metrics


def build_document(entries: list[dict], source_metrics: Counter, selection: Counter) -> dict:
    answers = {entry["answer"] for entry in entries}
    by_length = {
        str(length): len({entry["answer"] for entry in entries if entry["length"] == length})
        for length in range(3, 9)
    }
    weight_bands = Counter()
    for entry in entries:
        weight = int(entry["sourceRelationWeight"])
        band = "25-49" if weight < 50 else "50-99" if weight < 100 else "100-299" if weight < 300 else "300+"
        weight_bands[band] += 1
    return {
        "version": 1,
        "kind": "jeuxdemots-central-editorial-reservoir",
        "publicationPolicy": "Chaque relation est une piste de redaction; aucune publication automatique.",
        "source": {
            "id": "jeuxdemots-r_syn",
            "url": "https://www.jeuxdemots.org/jdm-about.php",
            "download": lexical.JDM_URL,
            "license": "CC0 / domaine public",
            "relation": "r_syn (5)",
        },
        "eligibilityPolicy": {
            "minimumLexiqueFrequency": MINIMUM_FREQUENCY,
            "minimumRelationWeight": lexical.MINIMUM_JDM_WEIGHT,
            "maximumRelationsPerAnswer": MAXIMUM_RELATIONS_PER_ANSWER,
            "samePartOfSpeech": True,
            "blacklistAndRotationCooldownApplied": True,
            "visibleInflectionPairsRejected": True,
            "playableWithoutReview": False,
        },
        "metrics": {
            "milestoneReached": len(answers) >= MINIMUM_DISTINCT_ANSWERS,
            "distinctAnswers": len(answers),
            "retainedRelations": len(entries),
            "distinctAnswersByLength": by_length,
            "relationWeightBands": dict(weight_bands),
            "playablePairsWithoutReview": 0,
            "sourceProcessing": dict(source_metrics),
            "selection": dict(selection),
        },
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=Path, default=DATA / f"sources/{lexical.JDM_FILENAME}"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    # The generic synonym importer uses a conservative frequency for direct
    # clue candidates.  This JDM reservoir intentionally includes uncommon
    # attested words, while keeping every relation non-playable until review.
    lexical.MINIMUM_SOURCE_FREQUENCY = MINIMUM_FREQUENCY
    metadata, blocked_answers, blocked_pairs = lexical.load_context()
    candidates: dict[str, dict[str, dict]] = defaultdict(dict)
    source_metrics = lexical.add_jeuxdemots_candidates(
        candidates, metadata, blocked_answers, blocked_pairs, args.source
    )
    entries, selection = select_relations(candidates)
    document = build_document(entries, source_metrics, selection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_gzip_json(args.output, document)
    print(json.dumps(document["metrics"], ensure_ascii=False, indent=2))
    if not document["metrics"]["milestoneReached"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
