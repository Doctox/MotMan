"""Build unpublished grids used to calibrate difficulty with the owner."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from build_handcrafted_reference_grids import clue_cells, direct_slots
from grid_topology import audit_grid_topology, render_topology_html


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/quality/difficulty-calibration-candidates.json"
AUDIT = ROOT / "output/quality/difficulty-calibration-audit.json"
HTML = ROOT / "output/quality/difficulty-calibration.html"

PATTERN = (
    "####..###",
    "#...##...",
    "#........",
    "#....#...",
    "#.#...#.#",
    ".#...#.#.",
    ".#.#.....",
    "#...#....",
    "#........",
    "#...#....",
)

ANSWERS = (
    "MI", "FEU", "PRE", "RANCOEUR", "OUIE", "UNE", "TRI", "NEF",
    "STELE", "LAC", "EMIR", "EGOUTIER", "VER", "ERRE", "FROC", "EAU",
    "UNITE", "PEU", "RUNE", "ERE", "CERFS", "OS", "NUAGE", "GEMIR",
    "VERRE", "TETE", "LIER", "LEV", "COR",
)

CLUES = {
    "MI": "Note médiane",
    "FEU": "Élément de base",
    "PRE": "Domaine de Pan",
    "RANCOEUR": "Ressentiment tenace",
    "OUIE": "Sens de Beethoven",
    "UNE": "Vedette de presse",
    "TRI": "Sélection ordonnée",
    "NEF": "Vaisseau d'église",
    "STELE": "Pierre commémorative",
    "LAC": "Léman, par exemple",
    "EMIR": "Prince musulman",
    "EGOUTIER": "Travailleur souterrain",
    "VER": "Lombric",
    "ERRE": "Élan du navire",
    "FROC": "Habit monastique",
    "EAU": "",
    "UNITE": "Grandeur de mesure",
    "PEU": "Presque rien",
    "RUNE": "Lettre scandinave",
    "ERE": "Temps géologique",
    "CERFS": "Bois sur tête",
    "OS": "Reste archéologique",
    "NUAGE": "Cumulus",
    "GEMIR": "Se plaindre sourdement",
    "VERRE": "Matière de Murano",
    "TETE": "Chef anatomique",
    "LIER": "Mettre en relation",
    "LEV": "Monnaie bulgare",
    "COR": "Instrument de Roland",
}

EASY = {"EAU", "PEU", "OS"}
HARD = {"PRE", "NEF", "ERRE", "FROC", "VERRE", "LEV", "COR"}


def build_candidate() -> dict:
    grid_id = "calibration-normal-upper-01"
    words = []
    slots = direct_slots(PATTERN)
    if len(slots) != len(ANSWERS):
        raise ValueError(f"{len(slots)} chemins pour {len(ANSWERS)} réponses")
    for index, (slot, answer) in enumerate(zip(slots, ANSWERS)):
        if len(slot["cells"]) != len(answer):
            raise ValueError(f"longueur incohérente pour {answer}")
        image = None
        if answer == "EAU":
            image = {
                "asset": "/assets/clues/twemoji/eau.svg",
                "alt": "Eau",
                "source": "Twemoji",
                "license": "CC BY 4.0",
            }
        difficulty = "easy" if answer in EASY else "hard" if answer in HARD else "normal"
        clue = CLUES[answer]
        words.append({
            "wordId": f"{grid_id}:word:{index + 1:02d}",
            "answer": answer,
            "clue": clue,
            "sourceClue": clue or "Indice illustré : eau",
            "definitionStatus": "reviewed",
            "editorialStatus": "calibration-review" if not image else "image-reviewed",
            "sourceType": "editorial-original" if not image else "image",
            "sourceId": "motman-difficulty-calibration-01",
            "sourceUrl": "https://www.lexique.org/",
            "difficulty": difficulty,
            "audienceEvidence": "owner-calibration-pending",
            "conceptGroup": answer,
            "semanticConflicts": [],
            **slot,
            **({"image": image} if image else {}),
        })
    return {
        "id": grid_id,
        "columns": 9,
        "rows": 10,
        "difficulty": "normal",
        "audience": "adultes, niveau normal supérieur",
        "clueCells": [list(cell) for cell in sorted(clue_cells(PATTERN))],
        "words": words,
        "difficultyMix": dict(Counter(word["difficulty"] for word in words)),
        "imageCount": 1,
        "publicationStatus": "owner-approved-staging",
        "humanReview": {
            "status": "approved",
            "reviewedAt": "2026-07-14",
            "note": "Classée normale supérieure par le propriétaire; deux indices corrigés après revue.",
        },
    }


def main() -> None:
    grid = build_candidate()
    report = audit_grid_topology(grid)
    if not report["valid"]:
        raise ValueError(report["errors"])
    for path in (OUTPUT, AUDIT, HTML):
        path.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"version": 1, "grids": [grid]}, ensure_ascii=False, indent=2), encoding="utf-8")
    AUDIT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    HTML.write_text(
        render_topology_html([report], title="Calibration MotMan — candidate culturelle 01"),
        encoding="utf-8",
    )
    print(json.dumps({
        "html": str(HTML),
        "valid": report["valid"],
        "difficultyMix": grid["difficultyMix"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
