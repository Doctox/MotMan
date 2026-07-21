#!/usr/bin/env python3
"""Assemble and editorially curate the second young/current 7x8 owner batch."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from build_compact_7x8_review import family_key, reference_answer_index


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/quality/compact-7x8-young-current-round2-curated.json"

SELECTION = [
    ("output/quality/compact-7x8-young-current-refills-flex.json", 0),
    ("output/quality/compact-7x8-young-current-shortpool-a.json", 1),
    ("output/quality/compact-7x8-young-current-shortpool-a.json", 2),
    ("output/quality/compact-7x8-young-current-shortpool-a.json", 5),
    ("output/quality/compact-7x8-young-current-shortpool-b.json", 1),
    ("output/quality/compact-7x8-young-current-final-search.json", 2),
    ("output/quality/compact-7x8-young-current-final-search.json", 3),
    ("output/quality/compact-7x8-young-current-final-search-2.json", 0),
    ("output/quality/compact-7x8-young-current-raw-ten.json", 3),
    ("output/quality/compact-7x8-young-current-raw-ten.json", 6),
]

OBSERVED_INTERNAL_REPEATS = {"EGO", "EN", "LE", "OSE", "PC", "TE", "TOM"}
OBSERVED_REFERENCE_REPEATS = {
    "AGE", "AS", "AU", "CB", "CE", "CET", "CV", "DON", "DOS", "EGO",
    "ELU", "EN", "ES", "ETIONS", "EVE", "JEU", "LA", "LE", "ME", "NE",
    "NO", "OM", "OSE", "PC", "SI", "TE", "TOM", "TPE", "TRI", "TUER", "VA",
}

CURATIONS = [
    {
        "definitions": {
            "COMPACT": "Peu encombrant", "AVANCER": "Aller devant", "RATEE": "Manquée",
            "ALOURDI": "Rendu plus lourd", "FEU": "Flammes", "ES": "Forme d'être",
            "CARAFE": "Pichet de table", "OVALES": "Formes arrondies", "MATOU": "Chat mâle",
            "PERE": "Papa", "PNEU": "Roue en caoutchouc", "BUT": "Objectif",
            "ACERBE": "Très piquant", "CE": "Pronom démonstratif", "DUR": "Pas mou",
            "TRAITE": "S'occupe de",
        },
        "images": {
            "FEU": ("Feu", "Feu allumé", "🔥"),
            "CARAFE": ("Carafe", "Carafe d'eau", "🏺"),
            "MATOU": ("Matou", "Chat mâle", "🐈"),
            "PNEU": ("Pneu", "Pneu de voiture", "🛠️"),
        },
    },
    {
        "definitions": {
            "MANETTE": "Accessoire de console", "EMOTION": "Sentiment fort", "CB": "Carte bancaire",
            "HIHAN": "Cri d'âne", "EGO": "Moi profond", "SUPREME": "Au sommet",
            "MECHES": "Cheveux groupés", "AMBIGU": "À double sens", "NO": "Non, en anglais",
            "HOP": "D'un saut", "NEMO": "Poisson de Pixar", "ETNA": "Volcan sicilien",
            "NOM": "Identité écrite", "TIENNE": "Soit à toi", "TOM": "Prénom de Voldemort",
            "OM": "Club marseillais", "ENORME": "Très grand",
        },
        "images": {
            "MANETTE": ("Manette", "Manette de jeu", "🎮"),
            "EMOTION": ("Émotion", "Visage ému", "🥹"),
            "NEMO": ("Nemo", "Poisson-clown", "🐠"),
            "ETNA": ("Etna", "Volcan en éruption", "🌋"),
        },
    },
    {
        "definitions": {
            "DESERTS": "Régions arides", "EVITERA": "Contournera", "PATINER": "Glisser sur glace",
            "OLEODUC": "Tuyau à pétrole", "TU": "Pronom familier", "SELS": "Cristaux salés",
            "DEPOTS": "Sommes laissées", "EVALUE": "Donne une note", "SITE": "Lieu en ligne",
            "NEIL": "Prénom d'Armstrong", "ETIONS": "Nous existions", "RENDE": "Restitue",
            "LE": "Article masculin", "TREUIL": "Appareil de levage", "SARCLE": "Désherbe",
        },
        "images": {
            "DESERTS": ("Déserts", "Paysages arides", "🏜️"),
            "PATINER": ("Patiner", "Patin à glace", "⛸️"),
            "SELS": ("Sels", "Sel de table", "🧂"),
            "TREUIL": ("Treuil", "Câble de levage", "🏗️"),
        },
    },
    {
        "definitions": {
            "ATHENES": "Capitale grecque", "FRAGILE": "Facile à casser", "FILLEUL": "Enfant du parrain",
            "OBEIR": "Suivre les ordres", "LA": "Article féminin", "ELLE": "Pronom féminin",
            "AFFOLE": "Met en panique", "TRIBAL": "Lié au clan", "HALE": "Bronzé",
            "SAVE": "Sauvegarde en jeu", "EGLISE": "Lieu de culte", "NIERA": "Dira non",
            "AS": "Champion", "ELU": "Choisi par vote", "VA": "Se déplace", "SELLES": "Sièges de cheval",
        },
        "images": {
            "ATHENES": ("Athènes", "Temple grec", "🏛️"),
            "FRAGILE": ("Fragile", "Colis fragile", "📦"),
            "EGLISE": ("Église", "Bâtiment religieux", "⛪"),
            "SELLES": ("Selles", "Selle de cheval", "🏇"),
        },
    },
    {
        "definitions": {
            "DIGERER": "Transformer les aliments", "IMAGINE": "Crée mentalement", "LAGON": "Étendue turquoise",
            "AGE": "Années vécues", "TE": "Pronom personnel", "ESSORER": "Retirer l'eau",
            "DILATE": "Agrandit", "IMAGES": "Représentations visuelles", "GAGE": "Objet confié",
            "PESE": "Mesure le poids", "EGO": "Moi intérieur", "PO": "Fleuve italien",
            "COL": "Passage montagneux", "RINCER": "Laver rapidement", "EN": "Dans",
            "OSE": "Tente", "REGLER": "Met au point",
        },
        "images": {
            "LAGON": ("Lagon", "Lagon tropical", "🏝️"),
            "IMAGES": ("Images", "Images encadrées", "🖼️"),
            "COL": ("Col", "Col de montagne", "🏔️"),
            "RINCER": ("Rincer", "Eau de rinçage", "🚿"),
        },
    },
    {
        "definitions": {
            "POTENCE": "Support en équerre", "UNIVERS": "Cosmos", "ECREMES": "Sans crème",
            "BLA": "Discours inutile", "LEGO": "Briques danoises", "OSE": "Tente",
            "PUEBLO": "Village amérindien", "ONCLES": "Frères des parents", "TIRAGE": "Impression ou loterie",
            "EVE": "Première femme", "SOI": "Pronom réfléchi", "JEU": "Activité ludique",
            "NEMS": "Rouleaux asiatiques", "LE": "Article masculin", "CREOLE": "Langue des Antilles",
            "ESSIEU": "Axe des roues",
        },
        "images": {
            "UNIVERS": ("Univers", "Galaxie lointaine", "🌌"),
            "LEGO": ("Lego", "Briques colorées", "🧱"),
            "NEMS": ("Nems", "Rouleaux asiatiques", "🥟"),
            "ESSIEU": ("Essieu", "Roues reliées", "🚗"),
        },
    },
    {
        "definitions": {
            "ADAPTER": "Ajuster", "VISCOSE": "Fibre artificielle", "ONU": "Organisation mondiale",
            "CES": "Démonstratif pluriel", "AU": "À le", "TRAVERS": "De biais",
            "AVOCAT": "Défenseur au tribunal", "DINEUR": "Client du soir", "ASUS": "Marque d'ordinateurs",
            "CRIE": "Parle très fort", "PC": "Ordinateur", "RPG": "Jeu de rôle",
            "CV": "Parcours professionnel", "DON": "Cadeau", "TORDRE": "Tourner de force",
            "ESPOIR": "Attente positive", "REGNES": "Périodes royales",
        },
        "images": {
            "AVOCAT": ("Avocat", "Avocat coupé", "🥑"),
            "PC": ("PC", "Ordinateur portable", "💻"),
            "RPG": ("RPG", "Dé de jeu", "🎲"),
            "DON": ("Don", "Cadeau offert", "🎁"),
        },
    },
    {
        "definitions": {
            "ENQUETE": "Recherche policière", "SOUPLES": "Faciles à plier", "CREDO": "Principe personnel",
            "ATLANTA": "Ville de Géorgie", "POST": "Publication en ligne", "EN": "Dans",
            "ESCAPE": "Touche de sortie", "NORTON": "Antivirus connu", "QUELS": "Interrogatif pluriel",
            "EPEE": "Arme de chevalier", "UPDATE": "Mise à jour", "ELON": "Prénom de Musk",
            "PC": "Ordinateur", "TE": "Pronom personnel", "TPE": "Terminal de paiement", "ESPACE": "Cosmos",
        },
        "images": {
            "ENQUETE": ("Enquête", "Loupe d'enquête", "🔎"),
            "POST": ("Post", "Message publié", "📮"),
            "EPEE": ("Épée", "Épée de chevalier", "⚔️"),
            "ESPACE": ("Espace", "Espace étoilé", "🌌"),
        },
    },
    {
        "definitions": {
            "INOXTAG": "Youtubeur de Kaizen", "MEDIANE": "Valeur du milieu", "PUE": "Sent mauvais",
            "ANTOINE": "Prénom de Griezmann", "CET": "Article masculin", "TUER": "Donner la mort",
            "IMPACT": "Choc", "NEUNEU": "Un peu bêta", "ODETTE": "Cygne du ballet",
            "XI": "Onze, à Rome", "PAN": "Bruit sec", "RAP": "Musique rimée",
            "TAPIR": "Animal à trompe", "SI": "À condition", "ANANAS": "Fruit tropical",
            "GENEPI": "Plante des Alpes",
        },
        "images": {
            "PUE": ("Mauvaise odeur", "Mauvaise odeur", "🤢"),
            "IMPACT": ("Impact", "Choc violent", "💥"),
            "RAP": ("Rap", "Micro de rap", "🎤"),
            "ANANAS": ("Ananas", "Fruit ananas", "🍍"),
        },
    },
    {
        "definitions": {
            "EMANANT": "Provenant de", "RAVAGER": "Tout détruire", "ATONE": "Sans éclat",
            "FRIAND": "Qui adore", "LIN": "Plante textile", "EXEGESE": "Analyse de texte",
            "ERAFLE": "Petite blessure", "MATRIX": "Pilule rouge", "AVOINE": "Céréale",
            "NANA": "Femme, familièrement", "TOM": "Prénom de Voldemort", "AGENTE": "Employée en mission",
            "NE": "Venu au monde", "DOS": "Arrière du corps", "TRI": "Classement", "ME": "Pronom personnel",
        },
        "images": {
            "RAVAGER": ("Ravager", "Tornade destructrice", "🌪️"),
            "ERAFLE": ("Éraflure", "Petite blessure", "🩹"),
            "AVOINE": ("Avoine", "Épis d'avoine", "🌾"),
            "TRI": ("Tri", "Symbole de tri", "♻️"),
        },
    },
]


def selected_grids() -> list[dict]:
    grids = []
    for relative_path, index in SELECTION:
        document = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
        grids.append(document["grids"][index])
    return grids


def build_payload() -> dict:
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    rejected = set(blacklist.get("rejectedAnswers", []))
    grids = selected_grids()
    if len(grids) != len(CURATIONS):
        raise ValueError("La sélection et la curation doivent contenir dix grilles")

    answer_counts: Counter[str] = Counter()
    family_answers: dict[str, set[str]] = {}
    curated = []
    for index, (grid, review) in enumerate(zip(grids, CURATIONS, strict=True), 1):
        actual = {item["answer"] for item in grid["answers"]}
        definitions = review["definitions"]
        images = review["images"]
        if actual != set(definitions):
            raise ValueError(
                f"grille {index}: définitions manquantes={sorted(actual - set(definitions))}, "
                f"superflues={sorted(set(definitions) - actual)}"
            )
        blocked_answers = sorted(actual & rejected)
        if not 4 <= len(images) <= 6 or not set(images) <= actual:
            raise ValueError(f"grille {index}: sélection d'images invalide")
        answer_counts.update(actual)
        for answer in actual:
            family_answers.setdefault(family_key(answer), set()).add(answer)
        curated.append({
            **grid,
            "id": f"compact-7x8-young-current-round2-{index:02d}",
            "answers": [
                {**item, "definition": definitions[item["answer"]]}
                for item in grid["answers"]
            ],
            "imageAnswers": [
                {"answer": answer, "concept": concept, "alt": alt, "emoji": emoji}
                for answer, (concept, alt, emoji) in images.items()
            ],
            "minimumImages": 4,
            "editorialStatus": "owner-rejected",
            "publicationStatus": "owner-rejected",
            "automaticRejections": blocked_answers,
        })

    repeated = {answer for answer, count in answer_counts.items() if count > 1}
    if repeated != OBSERVED_INTERNAL_REPEATS:
        raise ValueError(
            f"Répétitions inattendues: {sorted(repeated)} au lieu de "
            f"{sorted(OBSERVED_INTERNAL_REPEATS)}"
        )
    if any(answer_counts[answer] != 2 for answer in repeated):
        raise ValueError("Une charnière interne apparaît plus de deux fois")
    family_variants = {
        family: answers for family, answers in family_answers.items() if len(answers) > 1
    }
    if family_variants:
        raise ValueError(f"Variantes morphologiques répétées: {family_variants}")

    reference_exact, reference_families = reference_answer_index(
        [ROOT / "src/data/grid.catalog.json"]
    )
    reference_repeats = {
        answer
        for answer in answer_counts
        if answer in reference_exact or family_key(answer) in reference_families
    }
    if reference_repeats != OBSERVED_REFERENCE_REPEATS:
        raise ValueError(
            f"Répétitions catalogue inattendues: {sorted(reference_repeats)} au lieu de "
            f"{sorted(OBSERVED_REFERENCE_REPEATS)}"
        )

    return {
        "version": 1,
        "kind": "compact-7x8-young-current-round2-curated",
        "catalogModified": False,
        "publicationEligible": False,
        "ownerDecision": "rejected",
        "ownerDecisionDate": "2026-07-20",
        "ownerRejectionReasons": [
            "répétitions excessives avec le catalogue actif",
            "EGO et OM surutilisés",
            "SARCLE inconnu pour le public visé",
            "NIERA ressenti comme remplissage forcé",
            "indice HIHAN non univoque",
            "visuel CARAFE non reconnaissable comme broc d'eau",
        ],
        "editorialProfile": "current-language-pop-balanced",
        "observedInternalRepeats": sorted(OBSERVED_INTERNAL_REPEATS),
        "observedReferenceRepeats": sorted(OBSERVED_REFERENCE_REPEATS),
        "grids": curated,
    }


def main() -> None:
    payload = build_payload()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    unique_answers = {
        item["answer"] for grid in payload["grids"] for item in grid["answers"]
    }
    print(json.dumps({
        "grids": len(payload["grids"]),
        "uniqueAnswers": len(unique_answers),
        "ownerDecision": payload["ownerDecision"],
        "observedInternalRepeats": sorted(OBSERVED_INTERNAL_REPEATS),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
