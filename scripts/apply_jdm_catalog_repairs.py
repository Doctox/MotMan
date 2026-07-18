"""Apply two reviewed catalog repairs without publishing unreviewed drafts."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "src/data/grid.catalog.json"
JDM_URL = "https://www.jeuxdemots.org/jdm-about.php"

REPLACEMENTS = {
    1: ("EVE", "BAC", "Barque"),
    3: ("TIRS", "EXIL", "Départ forcé"),
    15: ("ETAT", "BEAU", "Plaisant"),
    16: ("VIE", "AXE", "Pivot"),
    17: ("ERRER", "CIRER", "Lustrer"),
    21: ("SAPIN", "LAPIN", ""),
}


def jdm_word(original: dict, answer: str, clue: str) -> dict:
    result = {
        **original,
        "answer": answer,
        "clue": clue,
        "sourceClue": clue,
        "sourceId": "jeuxdemots-r_syn",
        "sourceUrl": JDM_URL,
        "sourceType": "lexical-relation",
        "editorialStatus": "human-reviewed",
        "manualReview": "approved",
        "definitionStatus": "reviewed",
        "conceptGroup": answer,
        "semanticConflicts": [],
    }
    result.pop("image", None)
    if answer == "EXIL":
        result["sourceId"] = "motman-editorial-jdm-review"
        result["sourceType"] = "editorial-original"
    if answer == "LAPIN":
        result.update({
            "clue": "",
            "sourceClue": "Indice illustré : lapin",
            "sourceId": "twemoji-lapin",
            "sourceUrl": "https://github.com/jdecked/twemoji/blob/master/assets/svg/lapin.svg",
            "sourceType": "image",
            "editorialStatus": "image-reviewed",
            "image": {
                "asset": "/assets/clues/twemoji/lapin.svg",
                "alt": "Lapin",
                "source": "Twemoji",
                "license": "CC BY 4.0",
            },
        })
    return result


def main() -> None:
    document = json.loads(CATALOG.read_text(encoding="utf-8"))
    updated = deepcopy(document)
    grid21 = next(grid for grid in updated["grids"] if grid["id"] == "reference-standard-21")
    for index, (expected, answer, clue) in REPLACEMENTS.items():
        if grid21["words"][index]["answer"] != expected:
            raise ValueError(f"catalogue inattendu a l'index {index}")
        grid21["words"][index] = jdm_word(grid21["words"][index], answer, clue)
    grid21["humanReview"] = {
        "status": "editorially-reviewed",
        "reviewedAt": "2026-07-15",
        "note": "Zone TIR/TIRS remplacee par six reponses relues, dont une image lapin.",
    }

    grid27 = next(grid for grid in updated["grids"] if grid["id"] == "reference-standard-27")
    flower_clues = {"IRIS": "Fleur violette", "LIS": "Fleur royale"}
    for word in grid27["words"]:
        if word["answer"] in flower_clues:
            word["clue"] = flower_clues[word["answer"]]
            word["sourceClue"] = word["clue"]
            word["sourceId"] = "motman-editorial-review-20260715"
            word["sourceType"] = "editorial-original"
            word["editorialStatus"] = "human-reviewed"
            word["manualReview"] = "approved"
            word["definitionStatus"] = "reviewed"

    for grid in (grid21, grid27):
        report = audit_grid_topology(grid)
        if not report["valid"]:
            raise ValueError(f"reparation invalide {grid['id']}: {report['errors']}")
    CATALOG.write_text(
        json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "repaired": [grid21["id"], grid27["id"]],
        "grid21Replacements": [answer for _old, answer, _clue in REPLACEMENTS.values()],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
