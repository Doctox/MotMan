#!/usr/bin/env python3
"""Assemble the owner-feedback checkpoint after withdrawing rejected grids."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETAINED = ROOT / "output/quality/compact-7x8-young-balanced-retained-for-repair.json"
REPLACEMENT = ROOT / "output/quality/compact-7x8-young-freshpool-4.json"
OUTPUT = ROOT / "output/quality/compact-7x8-young-feedback-curated.json"

DEFINITIONS = {
    "RENOMME": "Appelle autrement",
    "ANIMAIT": "Donnait vie",
    "DVD": "Disque vidéo",
    "IA": "Intelligence artificielle",
    "OH": "Cri surpris",
    "SIDEREE": "Très étonnée",
    "RADIOS": "Postes audio",
    "ENVAHI": "Occupé partout",
    "NID": "Maison d'oiseau",
    "TEND": "Présente la main",
    "PUNI": "Sanctionné",
    "OM": "Club marseillais",
    "TPE": "Paiement par carte",
    "JEU": "Activité ludique",
    "MAJEUR": "Qui a 18 ans",
    "MIENNE": "À moi",
    "ETUDIE": "Analyse avec soin",
}

IMAGES = {
    "DVD": ("DVD", "Disque DVD", "💿"),
    "RADIOS": ("Radio", "Poste de radio", "📻"),
    "NID": ("Nid", "Nid d'oiseau", "🪹"),
    "TPE": ("TPE", "Paiement par carte", "💳"),
    "JEU": ("Jeu", "Manette de jeu", "🎮"),
}


def main() -> None:
    retained = json.loads(RETAINED.read_text(encoding="utf-8"))["grids"]
    candidates = json.loads(REPLACEMENT.read_text(encoding="utf-8"))["grids"]
    if len(retained) != 6 or len(candidates) != 1:
        raise ValueError("Le checkpoint attend six grilles conservées et une remplaçante")

    replacement = candidates[0]
    actual = {item["answer"] for item in replacement["answers"]}
    if actual != set(DEFINITIONS):
        raise ValueError(
            f"Réponses inattendues: manquantes={sorted(actual - set(DEFINITIONS))}, "
            f"superflues={sorted(set(DEFINITIONS) - actual)}"
        )
    replacement = {
        **replacement,
        "id": "compact-7x8-young-feedback-replacement-01",
        "answers": [
            {**item, "definition": DEFINITIONS[item["answer"]]}
            for item in replacement["answers"]
        ],
        "imageAnswers": [
            {"answer": answer, "concept": concept, "alt": alt, "emoji": emoji}
            for answer, (concept, alt, emoji) in IMAGES.items()
        ],
        "editorialStatus": "manually-reviewed",
        "publicationStatus": "owner-review-required",
    }

    payload = {
        "version": 1,
        "kind": "compact-7x8-young-feedback-curated",
        "catalogModified": False,
        "withdrawnGridIds": [
            "compact-7x8-young-balanced-01",
            "compact-7x8-young-balanced-03",
            "compact-7x8-young-balanced-05",
            "compact-7x8-young-balanced-10",
        ],
        "grids": [*retained, replacement],
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"grids": len(payload["grids"]), "output": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
