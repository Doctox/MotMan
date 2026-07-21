#!/usr/bin/env python3
"""Turn selected 7x8 lexical fills into explicitly curated review sources."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "quality" / "compact-7x8-agent-root.json"


SELECTIONS = [
    {
        "id": "compact-7x8-agent-root-01",
        "source": ROOT / "output" / "quality" / "compact-7x8-root-s4-raw.json",
        "definitions": {
            "PARADES": "Défilés festifs",
            "EMERITE": "Très expérimenté",
            "DICTE": "Énonce à écrire",
            "ADO": "Jeune lycéen",
            "LOI": "Règle officielle",
            "ENTREES": "Débuts de repas",
            "PEDALE": "Commande du vélo",
            "AMIDON": "Fécule de maïs",
            "RECOIT": "Accueille",
            "ART": "Création esthétique",
            "PAS": "Unité de marche",
            "PIE": "Oiseau chapardeur",
            "DIEPPE": "Port normand",
            "ET": "Relie deux mots",
            "AIE": "Cri douloureux",
            "SENSES": "Raisonnables",
        },
        "images": {
            "LOI": ("Loi", "La loi", "⚖️"),
            "ENTREES": ("Entrées", "Entrées", "🚪"),
            "PEDALE": ("Pédale", "Pédale", "🚲"),
            "ART": ("Art", "Art", "🎨"),
            "PAS": ("Pas", "Pas", "👣"),
            "AIE": ("Douleur", "Aïe", "🤕"),
        },
    },
    {
        "id": "compact-7x8-agent-root-02",
        "source": ROOT / "output" / "quality" / "compact-7x8-root-h4-r4-3.json",
        "definitions": {
            "ABAISSE": "Rend moins haut",
            "BOSNIEN": "Originaire de Bosnie",
            "OU": "Propose un choix",
            "NEFASTE": "Très nuisible",
            "DUO": "Paire d'artistes",
            "EXIGEES": "Réclamées",
            "ABONDE": "Existe en quantité",
            "BOUEUX": "Plein de boue",
            "AS": "Champion",
            "FOI": "Croyance profonde",
            "CERF": "Grand cervidé",
            "INCA": "Peuple des Andes",
            "TIR": "Coup de feu",
            "SIESTE": "Repos après-midi",
            "SERTIE": "Garnie de pierres",
            "ENFERS": "Lieux de supplice",
        },
        "images": {
            "DUO": ("Duo", "Duo", "👥"),
            "BOUEUX": ("Boue", "Boueux", "🥾"),
            "AS": ("Champion", "Champion", "🏆"),
            "CERF": ("Cerf", "Cerf", "🦌"),
            "TIR": ("Cible", "Tir", "🎯"),
            "SIESTE": ("Sieste", "Sieste", "😴"),
        },
    },
    {
        "id": "compact-7x8-agent-root-03",
        "source": ROOT / "output" / "quality" / "compact-7x8-root-v4-repair-r1.json",
        "definitions": {
            "RAMASSE": "Récupère au sol",
            "EVASION": "Fuite de prison",
            "VERSENT": "Font couler",
            "UNION": "Alliance",
            "EU": "Obtenu",
            "SECTEUR": "Zone délimitée",
            "REVUES": "Magazines",
            "AVENUE": "Grande rue",
            "MARI": "Époux",
            "INDE": "Pays asiatique",
            "ASSOIT": "Met sur chaise",
            "SIENNE": "Possessif féminin",
            "SON": "Bruit",
            "DU": "Article contracté",
            "ENTIER": "Sans manque",
        },
        "images": {
            "EVASION": ("Évasion", "Évasion", "🏃"),
            "UNION": ("Union", "Union", "🤝"),
            "REVUES": ("Revues", "Revues", "📰"),
            "AVENUE": ("Avenue", "Avenue", "🛣️"),
            "MARI": ("Mari", "Mari", "💍"),
            "INDE": ("Inde", "Inde", "🇮🇳"),
        },
    },
]


def curate(selection: dict) -> dict:
    raw = json.loads(selection["source"].read_text(encoding="utf-8"))
    if not raw.get("complete"):
        raise ValueError(f"Remplissage incomplet : {selection['source']}")

    definitions = selection["definitions"]
    answers = []
    actual = {item["answer"] for item in raw["answers"]}
    if actual != set(definitions):
        missing = sorted(actual - set(definitions))
        extra = sorted(set(definitions) - actual)
        raise ValueError(f"Revue incomplète : manquants={missing}, superflus={extra}")

    for item in raw["answers"]:
        answer = item["answer"]
        answers.append({**item, "definition": definitions[answer]})

    image_answers = [
        {"answer": answer, "concept": concept, "alt": alt, "emoji": emoji}
        for answer, (concept, alt, emoji) in selection["images"].items()
    ]
    if len(image_answers) < 6:
        raise ValueError("Six indices-images minimum")

    return {
        "id": selection["id"],
        "columns": 7,
        "rows": 8,
        "sourceShapeId": raw.get("sourceShapeId", "compact-7x8-free-interior"),
        "sourceCandidate": str(selection["source"].relative_to(ROOT)).replace("\\", "/"),
        "clueCells": raw["clueCells"],
        "rawSlots": raw["rawSlots"],
        "answers": answers,
        "imageAnswers": image_answers,
        "editorialStatus": "manually-reviewed",
        "publicationStatus": "owner-review-required",
    }


def main() -> None:
    payload = {
        "version": 1,
        "kind": "compact-7x8-curated-candidates",
        "catalogModified": False,
        "grids": [curate(selection) for selection in SELECTIONS],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(payload['grids'])} grille(s) écrite(s) dans {OUTPUT}")


if __name__ == "__main__":
    main()
