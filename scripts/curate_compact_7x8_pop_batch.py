#!/usr/bin/env python3
"""Attach short human-written clues and clear image concepts to the new 7x8 batch.

This is staging-only: it never edits the active catalog.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output" / "quality" / "compact-7x8-new-selected-reserve.json"
OUTPUT = ROOT / "output" / "quality" / "compact-7x8-pop-owner-curated.json"


CURATIONS = [
    {
        "definitions": {
            "AFFABLE": "Aimable et courtois",
            "PARLAIS": "Prenais la parole",
            "PROGRES": "Amélioration",
            "ACTU": "Infos du jour",
            "RITE": "Cérémonie réglée",
            "TRESSEE": "Entrelacée",
            "APPART": "Logement familier",
            "FARCIR": "Garnir l'intérieur",
            "FROTTE": "Astique",
            "ALGUES": "Organismes marins",
            "BAR": "Poisson marin",
            "SU": "Appris",
            "SI": "Marque une condition",
            "LIESSE": "Joie collective",
            "ESSUIE": "Sèche en frottant",
        },
        "images": {
            "ACTU": ("Actualité", "Actualité", "📰"),
            "APPART": ("Appartement", "Appartement", "🏠"),
            "ALGUES": ("Algues", "Algues", "🌿"),
            "BAR": ("Bar", "Poisson bar", "🐟"),
        },
    },
    {
        "definitions": {
            "DEPLAIT": "Ne séduit pas",
            "EVEILLE": "Réveille",
            "BARBE": "Poils du menton",
            "ACCEPTA": "A dit oui",
            "TUER": "Donner la mort",
            "SEREINE": "Très calme",
            "DEBATS": "Échanges d'idées",
            "EVACUE": "Fait sortir",
            "PERCER": "Faire un trou",
            "LIBERE": "Rend la liberté",
            "ALEP": "Ville de Syrie",
            "ON": "Pronom indéfini",
            "IL": "Pronom masculin",
            "TON": "Adjectif possessif",
            "TEXANE": "Habitante du Texas",
        },
        "images": {
            "BARBE": ("Barbe", "Barbe", "🧔"),
            "EVACUE": ("Évacuer", "Sortie d'évacuation", "🚪"),
            "PERCER": ("Percer", "Outil pour percer", "🛠️"),
            "TEXANE": ("Texane", "Texane", "🤠"),
        },
    },
    {
        "definitions": {
            "SCIERIE": "Atelier du bois",
            "COLLANT": "Qui adhère",
            "APLATIE": "Rendue bien plate",
            "MAIN": "Bout du bras",
            "PIC": "Sommet pointu",
            "INONDER": "Couvrir d'eau",
            "SCAMPI": "Grosses crevettes",
            "COPAIN": "Ami proche",
            "ILLICO": "Tout de suite",
            "ELAN": "Grand cervidé",
            "BIO": "D'agriculture biologique",
            "RAT": "Rongeur",
            "BD": "Bande dessinée",
            "INITIE": "Mis au courant",
            "ETE": "Saison chaude",
            "OR": "Métal précieux",
        },
        "images": {
            "MAIN": ("Main", "Main", "✋"),
            "PIC": ("Pic", "Sommet pointu", "⛰️"),
            "ELAN": ("Élan", "Élan", "🫎"),
            "RAT": ("Rat", "Rat", "🐀"),
            "ETE": ("Été", "Soleil d'été", "☀️"),
        },
    },
    {
        "definitions": {
            "APPREND": "Acquiert un savoir",
            "RELATER": "Raconter des faits",
            "CRAME": "Brûlé",
            "ACCENTS": "Marques de prononciation",
            "DUE": "À payer",
            "ES": "Forme d'être",
            "ARCADE": "Galerie à arches",
            "PERCUS": "Percussions familières",
            "PLACE": "Espace public",
            "BUTE": "Heurte un obstacle",
            "RAME": "Avance lentement",
            "DOS": "Arrière du corps",
            "ETENDU": "Mis à plat",
            "NE": "Venu au monde",
            "TOT": "Avant l'heure",
            "DRESSE": "Met debout",
        },
        "images": {
            "CRAME": ("Bruit de feu", "Brûlé", "🔥"),
            "ARCADE": ("Arcade", "Jeu d'arcade", "🕹️"),
            "PLACE": ("Place", "Place publique", "🏙️"),
            "RAME": ("Rame", "Rame", "🚣"),
        },
    },
    {
        "definitions": {
            "OFFICES": "Fonctions remplies",
            "RAINURE": "Entaille allongée",
            "GUETTER": "Surveiller discrètement",
            "ECLAT": "Brillance vive",
            "AH": "Cri de surprise",
            "TERTRES": "Petites buttes",
            "ORGEAT": "Sirop d'amandes",
            "FAUCHE": "Coupe les herbes",
            "FIEL": "Grande amertume",
            "CECI": "Cette chose",
            "INTACT": "Sans dommage",
            "CUTTER": "Couteau à lame",
            "ERE": "Longue période",
            "CE": "Démonstratif masculin",
            "SERAIS": "Conditionnel d'être",
        },
        "images": {
            "ECLAT": ("Éclat", "Éclat brillant", "✨"),
            "AH": ("Surprise", "Ah !", "😮"),
        },
        "assets": {
            "FAUCHE": ("Fauche", "Faux agricole", "/assets/clues/custom/faux.svg"),
            "CUTTER": ("Cutter", "Cutter", "/assets/clues/custom/cutter.svg"),
        },
    },
    {
        "definitions": {
            "VOLONTE": "Détermination",
            "EROSION": "Usure naturelle",
            "LAC": "Étendue d'eau",
            "CLAC": "Bruit sec",
            "RELAYER": "Prendre la suite",
            "OSER": "Avoir l'audace",
            "VELCRO": "Fermeture auto-agrippante",
            "ORALES": "Non écrites",
            "LOCALE": "Du voisinage",
            "OS": "Pièce du squelette",
            "CAR": "Autobus",
            "LUI": "Pronom masculin",
            "NIL": "Fleuve d'Afrique",
            "TV": "Télévision",
            "SE": "Pronom réfléchi",
            "TOUTES": "Sans exception",
            "ENIVRE": "Rend ivre",
        },
        "images": {
            "LAC": ("Lac", "Lac", "🏞️"),
            "CLAC": ("Clac", "Bruit sec", "💥"),
            "OS": ("Os", "Os", "🦴"),
            "CAR": ("Car", "Autobus", "🚌"),
            "TV": ("Télévision", "Télévision", "📺"),
        },
    },
    {
        "definitions": {
            "SAMPLER": "Prélever un son",
            "EGALISE": "Rend égal",
            "DEPARTS": "Actions de partir",
            "UN": "Premier nombre",
            "IDEE": "Pensée soudaine",
            "TA": "Possessif de toi",
            "SEDUIT": "Charme",
            "AGENDA": "Carnet de rendez-vous",
            "MAP": "Carte en anglais",
            "GAIE": "Pleine de joie",
            "SEAU": "Récipient à anse",
            "PLAGES": "Bords de mer",
            "LIRA": "Fera la lecture",
            "MA": "Possessif de moi",
            "ESTIMA": "Évalua",
            "RESEAU": "Ensemble connecté",
        },
        "images": {
            "AGENDA": ("Agenda", "Agenda", "📅"),
            "MAP": ("Carte", "Carte", "🗺️"),
            "SEAU": ("Seau", "Seau", "🪣"),
            "PLAGES": ("Plages", "Plage", "🏖️"),
            "LIRA": ("Lecture", "Livre ouvert", "📖"),
        },
    },
    {
        "definitions": {
            "PARADIS": "Lieu idéal",
            "ADORENT": "Aiment beaucoup",
            "REBECCA": "Film d'Hitchcock",
            "TPE": "Terminal de paiement",
            "IT": "Informatique en anglais",
            "REJETEE": "Non acceptée",
            "PARTIR": "Prendre le départ",
            "ADEPTE": "Fidèle partisan",
            "ROBE": "Vêtement féminin",
            "VETU": "Habillé",
            "ARE": "Cent mètres carrés",
            "VE": "Véhicule électrique",
            "RIT": "Montre sa joie",
            "DECRET": "Décision officielle",
            "INCITE": "Encourage",
            "STATUE": "Sculpture humaine",
        },
        "images": {
            "PARADIS": ("Paradis", "Île paradisiaque", "🏝️"),
            "TPE": ("TPE", "Paiement par carte", "💳"),
            "ROBE": ("Robe", "Robe", "👗"),
            "VE": ("Véhicule électrique", "Voiture électrique", "🚙⚡"),
            "STATUE": ("Statue", "Statue", "🗿"),
        },
    },
    {
        "definitions": {
            "ETABLIR": "Mettre en place",
            "COCAINE": "Stupéfiant en poudre",
            "HURLAIT": "Criait très fort",
            "EREINTE": "Très fatigué",
            "CB": "Carte bancaire",
            "SEME": "Répand des graines",
            "ECHECS": "Jeu du roi",
            "TOURBE": "Sol des marais",
            "ACRE": "Unité de surface",
            "SEIN": "Partie de poitrine",
            "BALISE": "Repère de route",
            "LIANE": "Plante grimpante",
            "AU": "À le",
            "INITIA": "Commença",
            "RETENU": "Gardé en mémoire",
        },
        "images": {
            "CB": ("Carte bancaire", "Carte bancaire", "💳"),
            "ECHECS": ("Échecs", "Pièces d'échecs", "♟️"),
            "SEME": ("Semer", "Jeune pousse", "🌱"),
            "BALISE": ("Balise", "Balise de signalisation", "🚧"),
            "LIANE": ("Liane", "Liane", "🌿"),
        },
    },
    {
        "definitions": {
            "DEBACLE": "Échec total",
            "EPAULER": "Aider",
            "CONTOUR": "Bord extérieur",
            "LU": "Déjà parcouru",
            "ISSU": "Né de",
            "CA": "Cela familièrement",
            "DECLIC": "Élément déclencheur",
            "EPOUSA": "Se maria avec",
            "BAN": "Exclusion",
            "EURE": "Rivière normande",
            "RUER": "Donner des ruades",
            "AUTEUR": "Écrivain",
            "CLOU": "Pointe métallique",
            "RU": "Petit ruisseau",
            "LEURRE": "Appât trompeur",
            "ERREUR": "Faute",
        },
        "images": {
            "EPOUSA": ("Épouser", "Mariage", "💍"),
            "AUTEUR": ("Auteur", "Auteur", "✍️"),
            "LEURRE": ("Leurre", "Leurre de pêche", "🎣"),
            "ERREUR": ("Erreur", "Erreur", "❌"),
        },
    },
]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    grids = source.get("grids", [])
    if len(grids) != len(CURATIONS):
        raise ValueError(f"{len(grids)} grilles brutes pour {len(CURATIONS)} revues")

    curated = []
    for index, (grid, review) in enumerate(zip(grids, CURATIONS, strict=True), start=1):
        definitions = review["definitions"]
        actual = {item["answer"] for item in grid["answers"]}
        if actual != set(definitions):
            raise ValueError(
                f"grille {index}: manquants={sorted(actual - set(definitions))}, "
                f"superflus={sorted(set(definitions) - actual)}"
            )
        images = review["images"]
        assets = review.get("assets", {})
        image_keys = set(images) | set(assets)
        if (
            not 4 <= len(image_keys) <= 6
            or not image_keys <= actual
            or set(images) & set(assets)
        ):
            raise ValueError(f"grille {index}: sélection d'images invalide")
        answers = [
            {**item, "definition": definitions[item["answer"]]}
            for item in grid["answers"]
        ]
        curated.append(
            {
                **grid,
                "id": f"compact-7x8-pop-owner-{index:02d}",
                "answers": answers,
                "imageAnswers": [
                    {"answer": answer, "concept": concept, "alt": alt, "emoji": emoji}
                    for answer, (concept, alt, emoji) in images.items()
                ]
                + [
                    {"answer": answer, "concept": concept, "alt": alt, "asset": asset}
                    for answer, (concept, alt, asset) in assets.items()
                ],
                "editorialStatus": "manually-reviewed",
                "publicationStatus": "owner-review-required",
            }
        )

    payload = {
        "version": 1,
        "kind": "compact-7x8-pop-curated-candidates",
        "catalogModified": False,
        "grids": curated,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"grids": len(curated), "output": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
