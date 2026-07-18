"""Build child-familiar inflected forms from school lemmas and Lexique 3.83."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from build_lexique_lemma_index import normalize


ROOT = Path(__file__).resolve().parents[1]
LEXIQUE = ROOT / "src/data/sources/Lexique383.tsv"
SCHOOL = ROOT / "src/data/sources/eduscol-frequency.xls"
OUTPUT = ROOT / "src/data/lexique.child-forms.json"
ALLOWED_VERB_MARKERS = ("inf;", "ind:pre:", "imp:pre:", "ind:imp:", "ind:fut:")
MINIMUM_GENERAL_FREQUENCY = 10.0


def main() -> None:
    school = pd.read_excel(SCHOOL)
    school_lemmas = {
        normalize(row.get("Mot", ""))
        for row in school.to_dict("records")
        if str(row.get("Nature", "")).strip() in {"adj.", "subst.", "verbe"}
    }
    frame = pd.read_csv(LEXIQUE, sep="\t", low_memory=False)
    accepted = {}
    for row in frame.to_dict("records"):
        lemma = normalize(row.get("lemme", ""))
        answer = normalize(row.get("ortho", ""))
        if not 3 <= len(answer) <= 9:
            continue
        part = str(row.get("cgram", ""))
        info = str(row.get("infover", ""))
        if part not in {"NOM", "ADJ", "ADV", "VER"}:
            continue
        if part == "VER" and not any(marker in info for marker in ALLOWED_VERB_MARKERS):
            continue
        frequency = max(float(row.get("freqfilms2") or 0), float(row.get("freqlivres") or 0))
        is_school_lemma = lemma in school_lemmas
        if not is_school_lemma and frequency < MINIMUM_GENERAL_FREQUENCY:
            continue
        if frequency < 1:
            continue
        item = {
            "answer": answer,
            "lemma": lemma,
            "length": len(answer),
            "partOfSpeech": part,
            "gender": None if pd.isna(row.get("genre")) else row.get("genre"),
            "number": None if pd.isna(row.get("nombre")) else row.get("nombre"),
            "verbInfo": None if part != "VER" else info,
            "sourceFrequency": round(frequency, 3),
            "difficulty": "easy",
            "audienceEvidence": (
                "eduscol-lemma-common-form" if is_school_lemma
                else "lexique-high-frequency-common-form"
            ),
        }
        current = accepted.get(answer)
        if current is None or frequency > current["sourceFrequency"]:
            accepted[answer] = item
    entries = sorted(accepted.values(), key=lambda item: (item["length"], item["answer"]))
    OUTPUT.write_text(json.dumps({
        "version": 1,
        "source": "Lexique 3.83 + liste de fréquence lexicale Éduscol",
        "sourceUrl": "http://www.lexique.org/databases/Lexique383/Lexique383.tsv",
        "license": "CC BY-SA 4.0",
        "policy": "Lemmes scolaires; noms/adjectifs usuels et temps verbaux courants; passé simple exclu.",
        "minimumGeneralFrequency": MINIMUM_GENERAL_FREQUENCY,
        "entries": entries,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"entries": len(entries), "output": str(OUTPUT)}))


if __name__ == "__main__":
    main()
