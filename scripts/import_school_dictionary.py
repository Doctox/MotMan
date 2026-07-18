"""Build a short-clue corpus from Eduscol frequencies and WOLF synsets.

The clue is always a complete French synonym from the same WOLF synset.  No
dictionary sentence is shortened and no clue is inferred from a word fragment.
"""
from __future__ import annotations

import argparse
import bz2
import json
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EDUSCOL_XLS = (
    "https://eduscol.education.gouv.fr/sites/default/files/document/"
    "listefrequencedesmots132918292375xls-76260.xls"
)
WOLF_URL = (
    "https://almanach.inria.fr/software_and_resources/downloads/"
    "wolf-1.0b4.xml.bz2"
)
WORD_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿŒœ]+(?:[-'][A-Za-zÀ-ÖØ-öø-ÿŒœ]+)?$")
POS = {"adj.": "a", "subst.": "n", "verbe": "v"}


def normalize_answer(value: str) -> str:
    value = value.replace("œ", "oe").replace("Œ", "OE")
    value = "".join(
        character for character in unicodedata.normalize("NFD", value)
        if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"[^A-Z]", "", value.upper())


def display_clue(value: str) -> str | None:
    """Return a complete one/two-word clue, never a truncated phrase."""
    value = re.sub(r"\s+", " ", value.strip().replace("_", " "))
    tokens = value.split()
    if not 1 <= len(tokens) <= 2 or not all(WORD_RE.fullmatch(token) for token in tokens):
        return None
    return value[0].upper() + value[1:]


def load_school_words(path: Path) -> dict[str, dict]:
    frame = pd.read_excel(path)
    words: dict[str, dict] = {}
    for row in frame.to_dict("records"):
        word = str(row.get("Mot", "")).strip().lower()
        answer = normalize_answer(word)
        nature = str(row.get("Nature", "")).strip()
        if nature not in POS or not WORD_RE.fullmatch(word) or not 2 <= len(answer) <= 8:
            continue
        words[word] = {
            "answer": answer,
            "frequency": float(row.get("Fréquence", 0)),
            "nature": nature,
            "pos": POS[nature],
        }
    return words


def wolf_synsets(path: Path, school_words: dict[str, dict]) -> dict[str, list[dict]]:
    """Index usable school-word synonyms from WOLF without loading its DOM."""
    index: dict[str, list[dict]] = defaultdict(list)
    with bz2.open(path, "rb") as stream:
        for _event, element in ET.iterparse(stream, events=("end",)):
            if element.tag != "SYNSET":
                continue
            pos = (element.findtext("POS") or "").strip()
            synset_id = element.findtext("ID") or ""
            literals: list[tuple[str, str]] = []
            synonym = element.find("SYNONYM")
            if synonym is not None:
                for literal in synonym.findall("LITERAL"):
                    word = (literal.text or "").strip().lower()
                    if word in school_words and school_words[word]["pos"] == pos:
                        clue = display_clue(word)
                        if clue:
                            literals.append((word, literal.get("lnote", "")))
            if len(literals) >= 2:
                for word, note in literals:
                    for synonym_word, synonym_note in literals:
                        if synonym_word == word:
                            continue
                        index[word].append({
                            "clue": display_clue(synonym_word),
                            "clueWord": synonym_word,
                            "clueFrequency": school_words[synonym_word]["frequency"],
                            "synsetId": synset_id,
                            "manual": "ManVal" in note or "ManVal" in synonym_note,
                        })
            element.clear()
    return index


def difficulty_for(frequency: float) -> str:
    if frequency >= 500:
        return "easy"
    if frequency >= 150:
        return "normal"
    return "hard"


def build_entries(school_words: dict[str, dict], synsets: dict[str, list[dict]]) -> list[dict]:
    entries = []
    for word, metadata in school_words.items():
        candidates = synsets.get(word, [])
        if not candidates:
            continue
        # Prefer a human-validated WOLF relation, then the most frequent clue.
        best = min(
            candidates,
            key=lambda item: (
                not item["manual"],
                -item["clueFrequency"],
                len(item["clue"].split()),
                len(item["clue"]),
            ),
        )
        answer = metadata["answer"]
        if normalize_answer(best["clue"]) == answer:
            continue
        difficulty = difficulty_for(metadata["frequency"])
        entries.append({
            "answer": answer,
            "clue": best["clue"],
            "length": len(answer),
            "frequency": round(min(7.5, 2.5 + metadata["frequency"] / 300), 3),
            "schoolFrequency": metadata["frequency"],
            "clueSchoolFrequency": best["clueFrequency"],
            "difficulty": difficulty,
            "sourceDifficulty": {"easy": 1, "normal": 2, "hard": 3}[difficulty],
            "clueType": "direct-synonym",
            "sourceType": "dictionary",
            "sourceId": "eduscol-wolf",
            "sourceUrl": "https://almanach.inria.fr/software_and_resources/WOLF-fr.html",
            "sourceSynsetId": best["synsetId"],
            "editorialStatus": "dictionary-derived",
            "conceptGroup": best["synsetId"],
            "semanticConflicts": [],
            "license": "Eduscol: Etalab-2.0; WOLF: CeCILL-C",
            "schoolNature": metadata["nature"],
            "wolfManualValidation": best["manual"],
        })
    return sorted(entries, key=lambda entry: (entry["length"], entry["answer"]))


def download(url: str, path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MotMan-corpus-audit"})
    with urllib.request.urlopen(request, timeout=60) as response:
        path.write_bytes(response.read())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--school-source", type=Path,
                        default=ROOT / "src/data/sources/eduscol-frequency.xls")
    parser.add_argument("--wolf-source", type=Path,
                        default=ROOT / "src/data/sources/wolf-1.0b4.xml.bz2")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "src/data/crossword.school.json")
    args = parser.parse_args()
    download(EDUSCOL_XLS, args.school_source)
    download(WOLF_URL, args.wolf_source)
    school_words = load_school_words(args.school_source)
    entries = build_entries(school_words, wolf_synsets(args.wolf_source, school_words))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "version": 1,
        "sources": [
            {"id": "eduscol-frequency", "url": EDUSCOL_XLS, "license": "Etalab-2.0"},
            {"id": "wolf", "url": WOLF_URL, "license": "CeCILL-C"},
        ],
        "policy": "Complete direct synonyms only; no arbitrary truncation",
        "entries": entries,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "schoolHeadwords": len(school_words),
        "retainedEntries": len(entries),
        "manualWolf": sum(entry["wolfManualValidation"] for entry in entries),
        "byDifficulty": {
            level: sum(entry["difficulty"] == level for entry in entries)
            for level in ("easy", "normal", "hard")
        },
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
