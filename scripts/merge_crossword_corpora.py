"""Merge source corpora while keeping exactly one sourced clue per answer."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from import_crossword_corpus import (
    ROOT, VULGAR_OR_SENSITIVE, image_for, normalize_answer, normalize_clue_key,
    pair_score,
)
from wordfreq import zipf_frequency

from editorial_quality import editorial_errors


DEFAULT_INPUTS = [
    ROOT / "src" / "data" / "crossword.ouestfrance.json",
    ROOT / "src" / "data" / "crossword.leparisien.json",
]
DEFAULT_OUTPUT = ROOT / "src" / "data" / "crossword.corpus.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="*", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    documents = [json.loads(path.read_text(encoding="utf-8")) for path in args.inputs]
    editorial = json.loads(
        (ROOT / "src" / "data" / "editorial.blacklist.json").read_text(encoding="utf-8")
    )
    rejected_answers = set(editorial.get("rejectedAnswers", []))
    rejected_pairs = {
        (item["answer"], item["clue"].casefold()) for item in editorial["rejectedPairs"]
    }
    by_answer = defaultdict(list)
    for document in documents:
        for entry in document["entries"]:
            if (entry["answer"] not in rejected_answers
                    and (entry["answer"], entry["clue"].casefold()) not in rejected_pairs
                    and not editorial_errors(entry, root=ROOT)):
                by_answer[entry["answer"]].append(entry)

    selected = {}
    for answer, entries in by_answer.items():
        selected[answer] = max(entries, key=lambda entry: (
            pair_score(answer, entry["sourceClue"]),
            2 if entry["sourceId"] == "leparisien-rcijeux" else 1,
            entry["frequency"],
        ))

    # The same clue and length cannot publish two possible answers.
    ambiguous = defaultdict(list)
    for answer, entry in selected.items():
        ambiguous[(len(answer), normalize_clue_key(entry["sourceClue"]))].append(answer)
    for key, answers in ambiguous.items():
        if len(answers) > 1:
            winner = max(answers, key=lambda answer: selected[answer]["frequency"])
            for answer in answers:
                if answer != winner:
                    selected.pop(answer, None)

    # Images are first-class clues. They do not need an invented textual
    # definition: the reviewed Twemoji illustration itself identifies the noun.
    image_dir = ROOT / "public" / "assets" / "clues" / "twemoji"
    for path in sorted(image_dir.glob("*.svg")):
        answer = normalize_answer(path.stem)
        if not 2 <= len(answer) <= 9 or answer in VULGAR_OR_SENSITIVE:
            continue
        image = image_for(answer)
        if answer in selected:
            selected[answer]["image"] = image
            continue
        selected[answer] = {
            "answer": answer,
            "clue": "Indice illustré",
            "sourceClue": "Indice illustré",
            "length": len(answer),
            "frequency": round(zipf_frequency(answer.lower(), "fr"), 3),
            "difficulty": "easy",
            "clueType": "image",
            "sourceType": "image",
            "sourceId": "twemoji",
            "sourceUrl": "https://github.com/jdecked/twemoji",
            "editorialStatus": "image-reviewed",
            "conceptGroup": answer,
            "semanticConflicts": [],
            "image": image,
        }

    entries = [selected[answer] for answer in sorted(selected)]
    difficulties = Counter(entry["difficulty"] for entry in entries)
    lengths = Counter(entry["length"] for entry in entries)
    sources = Counter(entry["sourceId"] for entry in entries)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.write_text(json.dumps({
        "version": 2,
        "format": "webcrow-cwdb-compatible",
        "publicationPolicy": "One answer, one exact source clue; no generated clue.",
        "sources": [document["source"] for document in documents],
        "counts": {
            "entries": len(entries),
            "bySource": dict(sorted(sources.items())),
            "byDifficulty": dict(sorted(difficulties.items())),
            "byLength": {str(length): count for length, count in sorted(lengths.items())},
            "withImage": sum("image" in entry for entry in entries),
        },
        "entries": entries,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "merged", "entries": len(entries), "bySource": dict(sources),
        "byDifficulty": dict(difficulties), "withImage": sum("image" in e for e in entries),
        "output": str(output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
