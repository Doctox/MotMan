"""Extract a conservative two-letter shortlist from cached Le Parisien grids.

Only exact, source-attested clue/answer pairs listed below are promoted.  The
list deliberately excludes music notes, arbitrary fragments, chemical symbols
and vague category clues.  Publication still requires the normal grid review.
"""
from __future__ import annotations

import gzip
import json
import re
import unicodedata
from pathlib import Path

from wordfreq import zipf_frequency


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "src/data/crossword.leparisien.raw.json.gz"
OUTPUT = ROOT / "src/data/crossword.short-source-reviewed.json"
GRID_URL = (
    "https://static.rcijeux.fr/drupal_game/leparisien/"
    "mfleches1/grids/mfleches_{force}_{number}.mfj"
)

# Exact source clues.  Each pair was selected for being short, natural and
# unambiguous enough to survive on a phone-sized arrowword cell.
APPROVED = {
    "CD": "DISQUE COMPACT",
    "CP": "COURS PRÉPARATOIRE",
    "EP": "DISQUE COURT",
    "GI": "SOLDAT AMÉRICAIN",
    "HS": "HORS D'USAGE",
    "IP": "ADRESSE INFORMATIQUE",
    "JT": "INFO EN IMAGES",
    "KO": "ASSOMMÉ",
    "MO": "MÉGAOCTET",
    "OB": "FLEUVE SIBÉRIEN",
    "PC": "ORDINATEUR",
    "PS": "POST-SCRIPTUM",
    "QI": "QUOTIENT INTELLECTUEL",
    "RH": "FACTEUR RHÉSUS",
    "RN": "ROUTE NATIONALE",
    "TP": "TRAVAUX PRATIQUES",
    "VO": "NON DOUBLÉ",
    "WC": "LIEUX D'AISANCES",
    "ZI": "ZONE INDUSTRIELLE",
}


def normalize_answer(value: str) -> str:
    folded = "".join(
        char for char in unicodedata.normalize("NFD", value.upper())
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"[^A-Z]", "", folded)


def display_clue(value: str) -> str:
    value = " ".join(value.strip().split()).lower()
    return value[:1].upper() + value[1:]


def main() -> None:
    with gzip.open(CACHE, "rt", encoding="utf-8") as stream:
        raw = json.load(stream)
    selected = {}
    for pair in raw["pairs"]:
        answer = normalize_answer(pair["answer"])
        if answer not in APPROVED or pair["clue"].strip() != APPROVED[answer]:
            continue
        # Stable preference when the same pair appeared in several editions.
        key = (pair.get("publishedOn", ""), pair.get("puzzleId", ""))
        if answer not in selected or key < selected[answer][0]:
            selected[answer] = (key, pair)
    missing = sorted(set(APPROVED) - set(selected))
    if missing:
        raise ValueError(f"Source pairs missing from cache: {missing}")

    entries = []
    for answer in sorted(APPROVED):
        pair = selected[answer][1]
        number = pair["puzzleId"].split("_")[-1]
        entries.append({
            "answer": answer,
            "clue": display_clue(pair["clue"]),
            "sourceClue": pair["clue"],
            "length": 2,
            "frequency": round(zipf_frequency(answer.lower(), "fr"), 3),
            "difficulty": "normal" if answer in {"EP", "GI", "OB", "RH", "VO"} else "easy",
            "sourceDifficulty": pair["force"],
            "sourceType": "crossword",
            "sourceId": "leparisien-rcijeux-short-reviewed",
            "sourceUrl": GRID_URL.format(force=pair["force"], number=number),
            "sourcePuzzleId": pair["puzzleId"],
            "sourcePublishedOn": pair["publishedOn"],
            "editorialStatus": "source-backed",
            "conceptGroup": answer,
            "semanticConflicts": [],
            "shortAnswerApproved": True,
            "shortReviewReason": "exact source pair; clear non-musical answer",
        })
    OUTPUT.write_text(json.dumps({
        "version": 1,
        "kind": "reviewed-short-source-corpus",
        "policy": "Exact Le Parisien pairs only; music notes and arbitrary fragments excluded.",
        "source": {
            "id": "leparisien-rcijeux",
            "cache": str(CACHE.relative_to(ROOT)).replace("\\", "/"),
        },
        "entries": entries,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "entries": len(entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
