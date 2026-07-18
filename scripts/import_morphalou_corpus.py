"""Import Morphalou 3.1 lemmas as a structural-only French reservoir.

Morphalou provides morphology, not crossword clues.  Imported answers are
therefore never generator-eligible by themselves.  A selected answer must
still receive a separately sourced, human-reviewed short clue before it can
join MotMan's central editorial corpus.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "src/data/sources/Morphalou3.1_formatCSV.zip"
DEFAULT_OUTPUT = ROOT / "src/data/crossword.morphalou.staging.json.gz"
SOURCE_URL = "https://hdl.handle.net/11403/morphalou/v3.1"
DOWNLOAD_URL = (
    "https://huggingface.co/datasets/datasets-CNRS/Morphalou/resolve/main/"
    "Morphalou3.1_formatCSV.zip"
)


def normalize_answer(value: str) -> str | None:
    value = value.strip().replace("œ", "oe").replace("Œ", "OE")
    value = value.replace("æ", "ae").replace("Æ", "AE")
    if not value or any(not (char.isalpha() or unicodedata.combining(char)) for char in value):
        return None
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    ).upper()
    if not normalized.isascii() or not normalized.isalpha():
        return None
    return normalized


def category_from_path(name: str) -> str:
    stem = Path(name).name.split("_Morphalou", 1)[0]
    return {
        "adjective": "adjective",
        "adverb": "adverb",
        "commonNoun": "common-noun",
        "grammaticalWords": "grammatical-word",
        "interjection": "interjection",
        "noCategory": "uncategorized",
        "verb": "verb",
    }.get(stem, stem)


def iter_forms(archive: zipfile.ZipFile):
    members = [
        name
        for name in archive.namelist()
        if name.lower().endswith(".csv")
        and "/fichiersPourDocumentationHTML/" not in name
    ]
    for member in sorted(members):
        category = category_from_path(member)
        with archive.open(member) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig"), delimiter=";")
            header_seen = False
            current: dict | None = None
            for row in reader:
                if not header_seen:
                    if row and row[0].strip() == "GRAPHIE":
                        header_seen = True
                    continue
                if len(row) < 18:
                    continue
                if row[0].strip():
                    lemma = row[0].strip()
                    lemma_answer = normalize_answer(lemma)
                    locution = row[4].strip()
                    current = {
                        "lemma": lemma,
                        "lemmaAnswer": lemma_answer,
                        "partOfSpeech": category,
                        "morphalouCategory": row[2].strip(),
                        "subcategory": row[3].strip() or None,
                        "gender": row[5].strip() or None,
                        "origins": sorted(set(row[8].strip().split())),
                        "valid": (
                            lemma_answer is not None
                            and locution in {"", "-", "0", "false", "False"}
                        ),
                    }
                    if not current["valid"]:
                        yield None, "non-simple-lemma-or-locution", "lemma"
                    elif 3 <= len(lemma_answer) <= 9:
                        yield {
                            "answer": lemma_answer,
                            "lemma": lemma,
                            "lemmaAnswer": lemma_answer,
                            "length": len(lemma_answer),
                            "partOfSpeech": category,
                            "morphalouCategory": current["morphalouCategory"],
                            "subcategory": current["subcategory"],
                            "gender": current["gender"],
                            "origins": current["origins"],
                            "formType": "lemma",
                            "inflection": None,
                            "source": "Morphalou 3.1",
                            "sourceUrl": SOURCE_URL,
                            "license": "LGPL-LR",
                            "editorialStatus": "structural-only-unreviewed",
                            "generatorEligible": False,
                        }, None, "lemma"
                    else:
                        yield None, "length", "lemma"

                if current is None or not current["valid"]:
                    continue
                raw_form = row[9].strip()
                form = normalize_answer(raw_form)
                if form is None:
                    yield None, "non-simple-orthography", "inflected"
                    continue
                if not 3 <= len(form) <= 9:
                    yield None, "length", "inflected"
                    continue
                if form == current["lemmaAnswer"]:
                    continue
                origins = sorted(set(row[17].strip().split()))
                yield {
                    "answer": form,
                    "lemma": current["lemma"],
                    "lemmaAnswer": current["lemmaAnswer"],
                    "length": len(form),
                    "partOfSpeech": category,
                    "morphalouCategory": current["morphalouCategory"],
                    "subcategory": current["subcategory"],
                    "gender": current["gender"],
                    "origins": origins or current["origins"],
                    "formType": "inflected",
                    "inflection": {
                        "number": row[11].strip() or None,
                        "mode": row[12].strip() or None,
                        "gender": row[13].strip() or None,
                        "tense": row[14].strip() or None,
                        "person": row[15].strip() or None,
                    },
                    "source": "Morphalou 3.1",
                    "sourceUrl": SOURCE_URL,
                    "license": "LGPL-LR",
                    "editorialStatus": "structural-only-unreviewed",
                    "generatorEligible": False,
                }, None, "inflected"


def build_document(source: Path) -> dict:
    selected: dict[str, dict] = {}
    rejected = Counter()
    source_counts = Counter()
    with zipfile.ZipFile(source) as archive:
        for entry, reason, row_kind in iter_forms(archive):
            source_counts[row_kind] += 1
            if entry is None:
                rejected[f"{row_kind}:{reason}"] += 1
                continue
            previous = selected.get(entry["answer"])
            preference = (
                entry["formType"] == "lemma",
                len(entry["origins"]),
                entry["partOfSpeech"] in {"common-noun", "adjective"},
            )
            previous_preference = (
                previous is not None and previous["formType"] == "lemma",
                len(previous["origins"]) if previous is not None else -1,
                previous is not None
                and previous["partOfSpeech"] in {"common-noun", "adjective"},
            )
            if previous is None or preference > previous_preference:
                selected[entry["answer"]] = entry
    entries = sorted(selected.values(), key=lambda item: (item["length"], item["answer"]))
    try:
        local_archive = str(source.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        local_archive = str(source)
    return {
        "version": 1,
        "kind": "morphalou-structural-only-staging",
        "publicationPolicy": (
            "Aucune entrée Morphalou n'est jouable sans définition courte "
            "séparément sourcée et validation éditoriale MotMan."
        ),
        "source": {
            "name": "Morphalou 3.1",
            "producer": "ATILF / CNRS / Université de Lorraine",
            "url": SOURCE_URL,
            "download": DOWNLOAD_URL,
            "license": "LGPL-LR",
            "localArchive": local_archive,
        },
        "metrics": {
            "sourceLemmaCandidates": source_counts["lemma"],
            "sourceInflectedCandidates": source_counts["inflected"],
            "retainedDistinctAnswers": len(entries),
            "retainedLemmas": sum(item["formType"] == "lemma" for item in entries),
            "retainedInflectedForms": sum(
                item["formType"] == "inflected" for item in entries
            ),
            "rejectedRows": sum(rejected.values()),
            "rejectedByReason": dict(rejected),
            "byLength": dict(sorted(Counter(item["length"] for item in entries).items())),
            "byPartOfSpeech": dict(
                sorted(Counter(item["partOfSpeech"] for item in entries).items())
            ),
        },
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    document = build_document(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({
        "output": str(args.output),
        "metrics": document["metrics"],
        "publicationPolicy": document["publicationPolicy"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
