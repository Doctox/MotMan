"""Build the compact lemma gate used by the offline grid generator."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/data/sources/Lexique383.tsv"
SCHOOL_SOURCE = ROOT / "src/data/sources/eduscol-frequency.xls"
OUTPUT = ROOT / "src/data/lexique.lemmas.json"


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", str(value).upper())
    return re.sub(r"[^A-Z]", "", "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    ))


def main() -> None:
    frame = pd.read_csv(SOURCE, sep="\t", low_memory=False)
    school_frame = pd.read_excel(SCHOOL_SOURCE)
    school_frequency = {
        normalize(row.get("Mot", "")): float(row.get("Fréquence", 0))
        for row in school_frame.to_dict("records")
        if str(row.get("Nature", "")).strip() in {"adj.", "subst.", "verbe"}
    }
    # Nouns/adjectives/adverbs remain valid lexical forms when inflected.
    # Verbs are admitted only in their infinitive lemma: this blocks the
    # newspaper filler made of isolated passé-simple forms (TUA, ALLA, TINT).
    rows = frame[
        frame["cgram"].isin({"NOM", "ADJ", "ADV"})
        | ((frame["cgram"] == "VER") & (frame["islem"] == 1))
    ]
    entries_by_answer = {}
    for row in rows.to_dict("records"):
        answer = normalize(row["ortho"])
        if not 3 <= len(answer) <= 9:
            continue
        frequency = max(float(row.get("freqfilms2") or 0), float(row.get("freqlivres") or 0))
        current = entries_by_answer.get(answer)
        if current is None or frequency > current["sourceFrequency"]:
            entries_by_answer[answer] = {
                "answer": answer,
                "length": len(answer),
                "partOfSpeech": row["cgram"],
                "sourceFrequency": round(frequency, 3),
                "schoolFrequency": school_frequency.get(answer, 0),
                "difficulty": "easy" if answer in school_frequency else (
                    "normal" if frequency >= 5 else "hard"
                ),
            }
    entries = sorted(entries_by_answer.values(), key=lambda item: (item["length"], item["answer"]))
    lemmas = [entry["answer"] for entry in entries]
    OUTPUT.write_text(json.dumps({
        "version": 1,
        "source": "Lexique 3.83",
        "sourceUrl": "http://www.lexique.org/databases/Lexique383/Lexique383.tsv",
        "license": "CC BY-SA 4.0",
        "policy": "NOM/ADJ/ADV lexical forms; VER only when explicitly marked as lemma",
        "lemmas": lemmas,
        "entries": entries,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"lemmas": len(lemmas), "output": str(OUTPUT)}))


if __name__ == "__main__":
    main()
