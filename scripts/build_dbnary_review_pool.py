"""Select familiar DBnary synonym pairs for human review, never publication."""
from __future__ import annotations

import gzip
import json
import math
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
MIN_FREQUENCY = 10.0


def main() -> None:
    with gzip.open(DATA / "crossword.dbnary.staging.json.gz", "rt", encoding="utf-8") as handle:
        staging = json.load(handle)["entries"]
    child_entries = json.loads((DATA / "lexique.child-forms.json").read_text(encoding="utf-8"))["entries"]
    familiar = {entry["answer"]: entry for entry in child_entries}
    blacklist = json.loads((DATA / "editorial.blacklist.json").read_text(encoding="utf-8"))
    rejected_answers = set(blacklist.get("rejectedAnswers", [])) | set(blacklist.get("rejectedEasyAnswers", []))
    rejected_pairs = {(item["answer"], item["clue"].casefold()) for item in blacklist.get("rejectedPairs", [])}
    grammar_words = {
        "ALORS", "APRES", "AVANT", "AVEC", "CAR", "CE", "CES", "COMME", "DANS", "DES",
        "DONC", "ELLE", "ELLES", "EN", "ET", "IL", "ILS", "JE", "LA", "LE", "LES",
        "MAIS", "NI", "NOUS", "ON", "OU", "PAR", "PAS", "POUR", "QUE", "QUI", "SA",
        "SES", "SI", "SUR", "TA", "TES", "TU", "UN", "UNE", "VOUS",
    }
    candidates = defaultdict(list)
    for entry in staging:
        answer = entry["answer"]
        clue_answer = entry["clue"].upper()
        if not 3 <= len(answer) <= 8 or not 3 <= len(clue_answer) <= 10:
            continue
        if answer not in familiar or clue_answer not in familiar:
            continue
        answer_meta, clue_meta = familiar[answer], familiar[clue_answer]
        minimum_frequency = min(answer_meta["sourceFrequency"], clue_meta["sourceFrequency"])
        if minimum_frequency < MIN_FREQUENCY:
            continue
        if answer_meta.get("lemma") == clue_meta.get("lemma"):
            continue
        if answer in rejected_answers or answer in grammar_words or clue_answer in grammar_words:
            continue
        if (answer, entry["clue"].casefold()) in rejected_pairs:
            continue
        school_evidence = sum(
            meta.get("audienceEvidence") == "eduscol-lemma-common-form"
            for meta in (answer_meta, clue_meta)
        )
        score = (school_evidence, math.log1p(minimum_frequency), -len(clue_answer), clue_answer)
        candidates[answer].append((score, entry, answer_meta, clue_meta))

    selected = []
    for answer, choices in candidates.items():
        _score, source, answer_meta, clue_meta = max(choices, key=lambda item: item[0])
        minimum_frequency = min(answer_meta["sourceFrequency"], clue_meta["sourceFrequency"])
        difficulty = (
            "easy" if minimum_frequency >= 20 or (
                answer_meta.get("audienceEvidence") == "eduscol-lemma-common-form"
                and clue_meta.get("audienceEvidence") == "eduscol-lemma-common-form"
            ) else "normal"
        )
        selected.append({
            **source,
            "sourceClue": source["clue"],
            "frequency": round(math.log10(minimum_frequency + 1) + 2, 3),
            "difficulty": difficulty,
            "sourceDifficulty": 1 if difficulty == "easy" else 2,
            "editorialStatus": "dictionary-derived",
            "reviewRequired": True,
            "audienceEvidence": [
                answer_meta.get("audienceEvidence"), clue_meta.get("audienceEvidence")
            ],
            "conceptGroup": f"dbnary:{answer}",
            "semanticConflicts": [],
        })
    selected.sort(key=lambda item: (item["length"], item["answer"]))
    output = DATA / "crossword.dbnary.review.json"
    output.write_text(json.dumps({
        "version": 1,
        "source": "DBnary French / Wiktionary",
        "license": "CC-BY-SA-3.0",
        "policy": "One-word direct synonyms with both terms attested as familiar; human review mandatory.",
        "minimumFrequency": MIN_FREQUENCY,
        "entries": selected,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"entries": len(selected), "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
