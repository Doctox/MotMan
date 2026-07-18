"""Build one complete 9x10 owner-review grid under the relaxed layout rule.

The only shape constraints enforced here are the ones explicitly retained by
the owner: the complete top row and complete left column are clue cells (the
top-left corner stays neutral), and every other non-clue cell belongs to a
declared answer.  This script never publishes the grid to the active catalog.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402


FILL = ROOT / "output/quality/common-flex-l-shape.components-v3.json"
STAGING = (
    ROOT
    / "src/data/grid-generation-handcrafted/owner-flexible-complete-01.review.json"
)
AUDIT = ROOT / "output/quality/owner-flexible-complete-01.audit.json"
HTML = ROOT / "output/quality/owner-flexible-complete-01.html"

GRID_ID = "owner-flexible-complete-01"

# Deliberately short, direct clues.  These are an editorial pass over the
# lexical closure, not fragments copied from an imported dictionary.
CLUES = {
    "ARRONDIES": "Rendues rondes",
    "SOURIANTE": "Visiblement heureuse",
    "SUE": "Transpire",
    "OM": "Club marseillais",
    "MA": "Possessif féminin",
    "MI": "Note musicale",
    "EN": "À l'intérieur",
    "RE": "Après do",
    "ASSOMMER": "Mettre K.-O.",
    "ROUMAINE": "De Bucarest",
    "RUE": "Voie urbaine",
    "ECOSSE": "Pays du whisky",
    "COUPON": "Bon de réduction",
    "ADROIT": "Très habile",
    "RESTER": "Ne pas partir",
    "TRESSE": "Cheveux entrelacés",
    "OR": "Métal précieux",
    "ECART": "Distance séparant",
    "NI": "Pas davantage",
    "CODER": "Programmer",
    "DA": "Oui, en russe",
    "OURSE": "Ours femelle",
    "IN": "À la mode",
    "SPOTS": "Courtes publicités",
    "ET": "Relie deux mots",
    "SOIES": "Fibres de cocon",
    "SE": "Pronom réfléchi",
    "ENTRE": "Au milieu",
}


def _load_blacklist() -> tuple[set[str], set[tuple[str, str]]]:
    data = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    answers = {str(value).upper() for value in data.get("rejectedAnswers", [])}
    pairs = {
        (str(item.get("answer", "")).upper(), str(item.get("clue", "")).casefold())
        for item in data.get("rejectedPairs", [])
    }
    return answers, pairs


def _build_grid(fill: dict) -> dict:
    if not fill.get("complete"):
        raise ValueError("Le remplissage source n'est pas complet.")
    if fill.get("columns") != 9 or fill.get("rows") != 10:
        raise ValueError("La grille doit mesurer exactement 9 colonnes x 10 lignes.")

    clue_cells = [list(cell) for cell in fill["clueCells"]]
    clue_set = {tuple(cell) for cell in clue_cells}
    required_frame = {(0, col) for col in range(9)} | {
        (row, 0) for row in range(10)
    }
    if not required_frame.issubset(clue_set):
        missing = sorted(required_frame - clue_set)
        raise ValueError(f"Cadre de définitions incomplet : {missing}")

    words = []
    seen_answers: set[str] = set()
    for number, solved in enumerate(fill["answers"], start=1):
        answer = str(solved["answer"]).upper()
        clue = CLUES.get(answer, "").strip()
        if not clue:
            raise ValueError(f"Définition manuelle absente : {answer}")
        if answer in seen_answers:
            raise ValueError(f"Réponse répétée dans la grille : {answer}")
        seen_answers.add(answer)
        direction = solved["direction"]
        words.append(
            {
                "wordId": f"{GRID_ID}:word:{number:02d}",
                "answer": answer,
                "clue": clue,
                "sourceClue": clue,
                "definitionStatus": "manually-edited",
                "editorialStatus": "human-reviewed-awaiting-owner",
                "manualReview": "reviewed-awaiting-owner",
                "sourceType": "editorial-original",
                "sourceId": "motman-owner-flexible-pass-20260718",
                "sourceUrl": "",
                "license": "MotMan original",
                "direction": direction,
                "arrow": "right" if direction == "across" else "down",
                "clueCell": list(solved["clueCell"]),
                "cells": [list(cell) for cell in solved["cells"]],
                "editorialProfile": "motman-relaxed-layout-human-pass",
            }
        )

    rejected_answers, rejected_pairs = _load_blacklist()
    for word in words:
        if word["answer"] in rejected_answers:
            raise ValueError(f"Réponse blacklistée : {word['answer']}")
        if (word["answer"], word["clue"].casefold()) in rejected_pairs:
            raise ValueError(
                f"Couple blacklisté : {word['answer']} / {word['clue']}"
            )

    return {
        "id": GRID_ID,
        "columns": 9,
        "rows": 10,
        "clueCells": clue_cells,
        "words": words,
        "publicationStatus": "owner-review-required",
        "editorialProfile": "motman-relaxed-layout-human-pass",
        "reviewCycle": "2026-07-18",
        "shapeId": fill.get("shapeId"),
        "layoutPolicy": "full-top-row-and-left-column-clues; free-interior; exact-topology",
    }


def main() -> None:
    fill = json.loads(FILL.read_text(encoding="utf-8"))
    grid = _build_grid(fill)

    # The owner's relaxed rule intentionally permits the internal L-shaped clue
    # wall.  All topology invariants remain blocking.
    report = audit_grid_topology(grid, enforce_layout=False)
    if not report["valid"]:
        raise ValueError(f"Audit topologique refusé : {report['errors']}")

    letter_cells = [cell for cell in report["cells"] if cell["kind"] == "letter"]
    uncovered = [cell for cell in letter_cells if not cell.get("wordIds")]
    if uncovered or report.get("orphanSegments"):
        raise ValueError(
            f"Couverture incomplète : {len(uncovered)} cases, "
            f"{len(report.get('orphanSegments', []))} segments orphelins"
        )

    answers = [word["answer"] for word in grid["words"]]
    metrics = {
        "grids": 1,
        "dimensions": "9x10",
        "totalCells": 90,
        "clueCellsIncludingNeutralCorner": len(grid["clueCells"]),
        "letterCells": len(letter_cells),
        "coveredLetterCells": len(letter_cells) - len(uncovered),
        "orphanLetters": len(uncovered),
        "orphanSegments": len(report.get("orphanSegments", [])),
        "answers": len(answers),
        "uniqueAnswers": len(set(answers)),
        "lengthProfile": dict(sorted(Counter(map(len, answers)).items())),
        "topRowEntirelyClues": all((0, col) in {tuple(c) for c in grid["clueCells"]} for col in range(9)),
        "leftColumnEntirelyClues": all((row, 0) in {tuple(c) for c in grid["clueCells"]} for row in range(10)),
        "topologyValid": True,
    }
    staging_document = {
        "version": 1,
        "kind": "owner-flexible-complete-grid-review",
        "publicationPolicy": "Non publiée ; validation explicite du propriétaire requise.",
        "rule": "Première ligne et première colonne en définitions ; intérieur libre ; aucune lettre orpheline.",
        "metrics": metrics,
        "grids": [grid],
    }
    audit_document = {
        "version": 1,
        "valid": True,
        "catalogModified": False,
        "metrics": metrics,
        "grids": [report],
    }

    STAGING.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(
        json.dumps(staging_document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    AUDIT.write_text(
        json.dumps(audit_document, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    page = render_topology_html(
        [report], title="MotMan — première grille complète, règle assouplie"
    )
    summary = (
        '<section style="max-width:1100px;margin:18px auto;padding:14px 18px;'
        'background:#eef8f1;border:1px solid #77ad87;border-radius:10px">'
        '<b>Grille complète non publiée — à toi de la juger</b><br>'
        f'{metrics["answers"]} réponses · {metrics["letterCells"]} cases-lettres couvertes '
        '· 0 lettre orpheline · 0 segment orphelin.<br>'
        'Toute la première ligne et toute la première colonne sont des cases-définition. '
        "Le mur intérieur en L est volontairement autorisé par la nouvelle règle."
        '</section>'
    )
    page = page.replace("</h1>", "</h1>" + summary, 1)
    HTML.write_text(page, encoding="utf-8")

    print(json.dumps({
        "gridId": GRID_ID,
        "complete": True,
        "catalogModified": False,
        "metrics": metrics,
        "staging": str(STAGING),
        "audit": str(AUDIT),
        "html": str(HTML),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
