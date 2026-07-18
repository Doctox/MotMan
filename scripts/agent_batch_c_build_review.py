#!/usr/bin/env python3
"""Build the agent-batch-c owner-review artifact without publishing it."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402


SOURCE = ROOT / "output/quality/agent-batch-c-search-07.json"
OUTPUT = ROOT / "output/quality/agent-batch-c-review-01.json"
AUDIT = ROOT / "output/quality/agent-batch-c-review-01.audit.json"
HTML = ROOT / "output/quality/agent-batch-c-review-01.html"
GRID_ID = "agent-batch-c-review-01"

CLUES = {
    "EPINETTES": "Conifères à aiguilles",
    "SALUTAIRE": "Bienfaisant",
    "PROMU": "Élevé en grade",
    "ACTIVE": "Met en marche",
    "CE": "Démonstratif singulier",
    "ELFE": "Créature fantastique",
    "ELUS": "Vainqueurs des urnes",
    "SET": "Manche de tennis",
    "ESPACEES": "Non rapprochées",
    "PARCELLE": "Petit terrain délimité",
    "ILOT": "Très petite île",
    "FUT": "Grand tonneau",
    "DECRET": "Décision officielle",
    "NUMIDES": "Peuple de Numidie",
    "OUEST": "Soleil couchant",
    "ETUVE": "Appareil chauffant",
    "RUNE": "Lettre viking",
    "ODES": "Poèmes lyriques",
    "TA": "Possessif féminin",
    "ECROU": "Pièce vissée",
    "ROC": "Bloc de pierre",
    "TIR": "Lancer de projectile",
    "RUDE": "Dur au toucher",
    "EROGENES": "Excitant le désir",
    "SEC": "Sans humidité",
    "TEST": "Épreuve de contrôle",
}

DOUBTS = {
    "EPINETTES": "Mot courant au Québec, plus botanique en France.",
    "NUMIDES": "Réponse historique, moins quotidienne que le reste de la grille.",
    "FUT": "L'accent de FÛT est volontairement absent dans les cases.",
}


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if not source.get("complete") or not source.get("grid"):
        raise ValueError("Source incomplète")
    raw = source["grid"]
    words = []
    for number, item in enumerate(raw["answers"], start=1):
        answer = item["answer"]
        clue = CLUES.get(answer, "").strip()
        if not clue:
            raise ValueError(f"Définition absente : {answer}")
        direction = item["direction"]
        word = {
            "wordId": f"{GRID_ID}:word:{number:02d}",
            "answer": answer,
            "clue": clue,
            "sourceClue": clue,
            "definitionStatus": "manually-edited",
            "editorialStatus": "human-reviewed-awaiting-owner",
            "manualReview": "reviewed-awaiting-owner",
            "sourceType": "editorial-original",
            "sourceId": "motman-agent-batch-c-20260718",
            "sourceUrl": "",
            "license": "MotMan original",
            "direction": direction,
            "arrow": "right" if direction == "across" else "down",
            "clueCell": item["clueCell"],
            "cells": item["cells"],
            "editorialProfile": "motman-agent-batch-c-human-pass",
            "activeUsesAtSearch": item["activeUses"],
        }
        if item.get("image"):
            word.update({
                "editorialStatus": "image-reviewed-awaiting-owner",
                "sourceType": "image",
                "sourceId": f"twemoji-{answer.lower()}",
                "sourceUrl": (
                    "https://github.com/jdecked/twemoji/blob/master/assets/svg/"
                    f"{answer.lower()}.svg"
                ),
                "license": "CC BY 4.0",
                "image": {
                    "asset": item["image"],
                    "alt": clue,
                    "source": "Twemoji",
                    "license": "CC BY 4.0",
                },
            })
        words.append(word)

    grid = {
        "id": GRID_ID,
        "columns": 9,
        "rows": 10,
        "clueCells": raw["clueCells"],
        "words": words,
        "publicationStatus": "owner-review-required",
        "editorialProfile": "motman-agent-batch-c-human-pass",
        "reviewCycle": "2026-07-18",
        "layoutPolicy": "full-frame; free-interior; maximum-two-two-letter-answers",
        "accentPolicy": "Accents ignored in answer cells; preserved in French clues.",
        "sourceShapeGridId": raw.get("sourceShapeGridId"),
        "ownerLowShort02SilhouetteDistinct": raw.get("ownerSilhouetteDistinct"),
    }
    report = audit_grid_topology(grid, enforce_layout=False)
    if not report["valid"]:
        raise ValueError(report["errors"])

    answers = [word["answer"] for word in words]
    two_letter = [answer for answer in answers if len(answer) == 2]
    letter_cells = [cell for cell in report["cells"] if cell["kind"] == "letter"]
    image_answers = [word["answer"] for word in words if word.get("image")]
    active_repeats = {
        word["answer"]: word["activeUsesAtSearch"]
        for word in words if word["activeUsesAtSearch"]
    }
    metrics = {
        "dimensions": "9x10",
        "totalCells": len(report["cells"]),
        "letterCells": len(letter_cells),
        "coveredLetterCells": sum(bool(cell["wordIds"]) for cell in letter_cells),
        "orphanLetters": sum(not cell["wordIds"] for cell in letter_cells),
        "orphanSegments": len(report["orphanSegments"]),
        "answers": len(answers),
        "uniqueAnswers": len(set(answers)),
        "twoLetterAnswers": two_letter,
        "lengthProfile": dict(sorted(Counter(map(len, answers)).items())),
        "topologyValid": report["valid"],
        "distinctFromOwnerLowShort02": raw.get("ownerSilhouetteDistinct"),
        "imageAnswers": image_answers,
        "activeRepeatsAtSearch": active_repeats,
        "accentPolicyExamples": {"ÉPINETTES": "EPINETTES", "ÎLOT": "ILOT", "FÛT": "FUT"},
    }
    document = {
        "version": 1,
        "kind": "agent-batch-c-owner-review",
        "publicationPolicy": "Non publiée ; validation humaine requise.",
        "metrics": metrics,
        "editorialDoubts": DOUBTS,
        "imageCandidates": {
            "ROC": "/assets/clues/twemoji/roc.svg",
        },
        "imageQuotaAttempt": (
            "Deux passes avec quota de trois images ont échoué ; aucune réponse "
            "faible n'a été forcée pour atteindre le quota."
        ),
        "grids": [grid],
    }
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    AUDIT.write_text(json.dumps({
        "version": 1,
        "valid": True,
        "catalogModified": False,
        "metrics": metrics,
        "editorialDoubts": DOUBTS,
        "grids": [report],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    page = render_topology_html([report], title="MotMan — candidat agent batch C")
    doubt_lines = "".join(
        f"<li><b>{answer}</b> : {note}</li>" for answer, note in DOUBTS.items()
    )
    summary = (
        '<section style="max-width:1100px;margin:18px auto;padding:14px 18px;'
        'background:#fff8e8;border:1px solid #c49a45;border-radius:10px">'
        '<b>Candidat C — non publié</b><br>'
        f'{len(answers)} réponses · {len(two_letter)} mots de deux lettres '
        f'({", ".join(two_letter)}) · {len(letter_cells)} cases-lettres couvertes '
        f'· {len(image_answers)} pictogramme exact ({", ".join(image_answers)}).<br>'
        'Silhouette différente de owner-low-short-02 ; accents ignorés dans les cases.'
        f'<ul>{doubt_lines}</ul>'
        '</section>'
    )
    page = page.replace("</h1>", "</h1>" + summary, 1)
    HTML.write_text(page, encoding="utf-8")
    print(json.dumps({
        "complete": True,
        "catalogModified": False,
        "metrics": metrics,
        "doubts": DOUBTS,
        "json": str(OUTPUT),
        "html": str(HTML),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
