"""Build the fifth owner-approved MotMan reference grid.

The geometry and fill come from the constrained shape search, but every clue
below is deliberately edited.  This candidate stays out of the active catalog
until the owner has rated its playability.  The former difficulty label is
kept only in the historical filename; MotMan now uses one editorial profile.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from build_handcrafted_reference_grids import clue_cells, direct_slots
from grid_topology import audit_grid_topology, render_topology_html


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/quality/hard-calibration-round-02-candidate.json"
AUDIT = ROOT / "output/quality/hard-calibration-round-02-audit.json"
HTML = ROOT / "output/quality/hard-calibration-round-02.html"

# # = clue cell, . = letter cell.  The top-left cell is neutral.
PATTERN = (
    "#####..##",
    "#....##..",
    "#...#....",
    "#........",
    "#.#......",
    ".#....#.#",
    ".#.#.#.#.",
    "#........",
    "#...#....",
    "#........",
)

ANSWERS = (
    "IF", "AVIS", "PI", "ROC", "CAID", "CLOPORTE", "NAITRE", "REIN",
    "ECHEVEAU", "GUI", "AIRE", "OSCILLER", "ARCS", "VOL", "ICONE",
    "PITRE", "IDEE", "COIN", "ART", "PAIRE", "AH", "RECUS", "OEIL",
    "TUER", "EGO", "HIC", "VAL", "ARE",
)

CLUES = {
    "IF": "Conifère des cimetières",
    "AVIS": "Opinion exprimée",
    "PI": "Rapport circonférence-diamètre",
    "ROC": "Masse de pierre",
    "CAID": "Chef de clan",
    "CLOPORTE": "Crustacé terrestre",
    "NAITRE": "Voir le jour",
    "REIN": "Organe à néphrons",
    "ECHEVEAU": "Fils avant pelote",
    "GUI": "Plante des druides",
    "AIRE": "Surface mesurée",
    "OSCILLER": "Varier périodiquement",
    "ARCS": "Portions de cercle",
    "VOL": "Larcin",
    "ICONE": "Image orthodoxe",
    "PITRE": "Bouffon de scène",
    "IDEE": "Concept mental",
    "COIN": "Angle de pièce",
    "ART": "Création esthétique",
    "PAIRE": "Ensemble de deux",
    "AH": "Marque de surprise",
    "RECUS": "Preuves de paiement",
    "OEIL": "",
    "TUER": "Causer la mort",
    "EGO": "Moi freudien",
    "HIC": "Difficulté imprévue",
    "VAL": "Creux entre monts",
    "ARE": "Cent mètres carrés",
}

def build_candidate() -> dict:
    grid_id = "calibration-hard-02"
    slots = direct_slots(PATTERN)
    if len(slots) != len(ANSWERS):
        raise ValueError(f"{len(slots)} chemins pour {len(ANSWERS)} réponses")

    words = []
    for index, (slot, answer) in enumerate(zip(slots, ANSWERS)):
        if len(slot["cells"]) != len(answer):
            raise ValueError(
                f"{answer}: longueur {len(answer)} != chemin {len(slot['cells'])}"
            )
        image = None
        if answer == "OEIL":
            image = {
                "asset": "/assets/clues/twemoji/oeil.svg",
                "alt": "Œil",
                "source": "Twemoji",
                "license": "CC BY 4.0",
            }
        clue = CLUES[answer]
        words.append({
            "wordId": f"{grid_id}:word:{index + 1:02d}",
            "answer": answer,
            "clue": clue,
            "sourceClue": clue or "Indice illustré : œil",
            "definitionStatus": "reviewed",
            "editorialStatus": "calibration-review" if not image else "image-reviewed",
            "sourceType": "editorial-original" if not image else "image",
            "sourceId": "motman-hard-calibration-02" if not image else "twemoji-oeil",
            "sourceUrl": "https://www.lexique.org/" if not image else (
                "https://github.com/jdecked/twemoji/blob/master/assets/svg/1f441.svg"
            ),
            "editorialProfile": "motman-standard",
            "audienceEvidence": "owner-approved-reference",
            "conceptGroup": answer,
            "semanticConflicts": [],
            **slot,
            **({"image": image} if image else {}),
        })

    return {
        "id": grid_id,
        "columns": 9,
        "rows": 10,
        "editorialProfile": "motman-standard",
        "audience": "grand public",
        "clueCells": [list(cell) for cell in sorted(clue_cells(PATTERN))],
        "words": words,
        "imageCount": 1,
        "publicationStatus": "owner-approved-staging",
        "humanReview": {
            "status": "approved",
            "reviewedAt": "2026-07-14",
            "note": "Grille validée par le propriétaire; les niveaux de difficulté produit sont abandonnés.",
        },
        "provenance": {
            "answers": "Lexique 3.83, formes canoniques et revue mot par mot",
            "clues": "Formulations originales MotMan en calibration humaine",
            "geometry": "Recherche contrainte avec silhouette distincte des pilotes approuvés",
        },
    }


def main() -> None:
    grid = build_candidate()
    report = audit_grid_topology(grid)
    if not report["valid"]:
        raise ValueError(report["errors"])
    for path in (OUTPUT, AUDIT, HTML):
        path.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps({"version": 1, "grids": [grid]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    AUDIT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    HTML.write_text(
        render_topology_html([report], title="MotMan — tentative difficile n°2"),
        encoding="utf-8",
    )
    print(json.dumps({
        "html": str(HTML),
        "valid": report["valid"],
        "answers": len(grid["words"]),
        "publicationStatus": grid["publicationStatus"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
