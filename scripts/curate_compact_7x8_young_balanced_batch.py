#!/usr/bin/env python3
"""Editorialise the balanced 7x8 owner-review batch without publishing it."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output/quality/compact-7x8-young-balanced-raw.json"
OUTPUT = ROOT / "output/quality/compact-7x8-young-balanced-curated.json"
RETAINED_OUTPUT = ROOT / "output/quality/compact-7x8-young-balanced-retained-for-repair.json"
RETAINED_GRID_NUMBERS = {2, 4, 6, 7, 8, 9}


CURATIONS = [
    {
        "definitions": {
            "POSTANT": "Mettant en ligne", "AMORTIR": "Réduire un choc",
            "SENAT": "Chambre des élus", "TRICEPS": "Muscle du bras",
            "ETC": "Et le reste", "LA": "Article féminin", "PASTEL": "Crayon coloré",
            "OMERTA": "Loi du silence", "SONIC": "Hérisson bleu", "PEPE": "Grand-père familier",
            "TRAC": "Peur de scène", "LOT": "Ensemble vendu", "ATTELE": "Relié au harnais",
            "NI": "Conjonction négative", "POP": "Musique grand public", "TRISTE": "Sans joie",
        },
        "images": {
            "TRICEPS": ("Triceps", "Muscle du bras", "💪"),
            "PASTEL": ("Pastel", "Crayon pastel", "🖍️"),
            "PEPE": ("Pépé", "Grand-père", "👴"),
            "TRISTE": ("Triste", "Visage triste", "😢"),
        },
    },
    {
        "minimumImages": 3,
        "definitions": {
            "CAVALER": "Courir très vite", "OPACITE": "Manque de transparence",
            "NASAL": "Venant du nez", "DISCORD": "Appli de discussion",
            "OSAI": "Eus le courage", "RELANCE": "Nouvelle tentative",
            "CONDOR": "Grand vautour", "APAISE": "Rend plus calme",
            "VASSAL": "Serviteur du seigneur", "ACACIA": "Arbre à fleurs",
            "LILO": "Amie de Stitch", "OU": "Indique un choix", "ET": "Relie deux mots",
            "ROC": "Masse de pierre", "RENDUE": "Restituée",
        },
        "images": {
            "CAVALER": ("Courir", "Personne qui court", "🏃"),
            "ACACIA": ("Acacia", "Arbre en fleurs", "🌳"),
            "ROC": ("Roc", "Gros rocher", "🪨"),
        },
    },
    {
        "definitions": {
            "FROTTIS": "Dessin par frottement", "RELIANT": "Mettant en relation",
            "AMARRER": "Attacher un bateau", "NEF": "Partie d'église", "CD": "Disque compact",
            "SENSEES": "Raisonnables", "FRANCS": "Sincères", "REMEDE": "Soin curatif",
            "OLAF": "Ami d'Elsa", "ARTS": "Créations humaines", "TIR": "Lancer vers une cible",
            "AS": "Très bon joueur", "TPE": "Terminal de paiement", "TARTRE": "Dépôt sur les dents",
            "INEPTE": "Sans compétence", "STRESS": "Forte tension nerveuse",
        },
        "images": {
            "CD": ("CD", "Disque compact", "💿"),
            "TIR": ("Tir", "Cible de tir", "🎯"),
            "TPE": ("TPE", "Paiement par carte", "💳"),
            "TARTRE": ("Tartre", "Dent entartrée", "🦷"),
            "STRESS": ("Stress", "Visage stressé", "😰"),
        },
    },
    {
        "definitions": {
            "SPASMES": "Contractions soudaines", "PIVOINE": "Grande fleur ronde",
            "ORAUX": "Examens parlés", "RAT": "Petit rongeur", "ETAT": "Situation présente",
            "SERVILE": "Trop soumis", "SPORES": "Graines de champignons", "PIRATE": "Bandit des mers",
            "AVATAR": "Image de profil", "SOU": "Ancienne monnaie", "TV": "Télévision",
            "EGO": "Idée de soi", "MIXE": "Mélange des sons", "EU": "Obtenu",
            "EN": "Pronom adverbial", "GEL": "Froid qui glace", "SECOUE": "Agite fortement",
        },
        "images": {
            "PIVOINE": ("Pivoine", "Fleur de pivoine", "🌸"),
            "RAT": ("Rat", "Rat", "🐀"),
            "SPORES": ("Spores", "Champignons", "🍄"),
            "PIRATE": ("Pirate", "Pirate", "🏴‍☠️"),
            "TV": ("Télévision", "Télévision", "📺"),
            "GEL": ("Gel", "Glace", "🧊"),
        },
    },
    {
        "definitions": {
            "ACCABLE": "Charge lourdement", "PARLAIS": "Prenais la parole",
            "EMAILS": "Messages électroniques", "RINCE": "Nettoie sous eau", "COTE": "Versant montagneux",
            "UNE": "Article féminin", "APERCU": "Vu rapidement", "CAMION": "Gros véhicule",
            "CRANTE": "Muni de dents", "ALICE": "Héroïne de Carroll", "DOS": "Arrière du corps",
            "BALE": "Ville suisse", "PU": "Réussi à", "LIS": "Fais la lecture",
            "PO": "Fleuve italien", "ES": "Forme d'être", "BUS": "Transport urbain",
        },
        "images": {
            "EMAILS": ("E-mails", "Courrier électronique", "✉️"),
            "RINCE": ("Rincer", "Nettoie sous eau", "🚿"),
            "CAMION": ("Camion", "Camion", "🚚"),
            "BUS": ("Bus", "Autobus", "🚌"),
        },
    },
    {
        "definitions": {
            "RITUELS": "Cérémonies réglées", "ENONCEE": "Formulée clairement",
            "VIT": "Est en vie", "ETAGERE": "Planche de rangement", "NIL": "Fleuve d'Afrique",
            "DE": "Préposition d'origine", "REVEND": "Cède contre argent", "INITIE": "Mis au courant",
            "TOTAL": "Somme complète", "USER": "Détériorer lentement", "UN": "Premier nombre",
            "HUM": "Marque l'hésitation", "CRU": "Non cuit", "ECHECS": "Jeu du roi",
            "LEURRE": "Appât trompeur", "SEMEUR": "Qui répand des graines",
        },
        "images": {
            "ETAGERE": ("Étagère", "Étagère", "🗄️"),
            "ECHECS": ("Échecs", "Pièce d'échecs", "♟️"),
            "LEURRE": ("Leurre", "Leurre de pêche", "🎣"),
            "SEMEUR": ("Semeur", "Graines semées", "🌱"),
        },
    },
    {
        "definitions": {
            "GRAVATS": "Débris de chantier", "REPAIRE": "Cachette d'un animal",
            "IMPUNI": "Non puni", "FORTE": "Puissante", "FUIR": "Partir au loin",
            "ESTEREL": "Massif du Var", "GRIFFE": "Ongle d'un animal", "REMOUS": "Tourbillon d'eau",
            "APPRIT": "Acquit un savoir", "VAUTRE": "Étale sans soin", "AINE": "Le plus âgé",
            "NO": "Théâtre japonais", "TRI": "Classement", "NE": "Venu au monde",
            "SE": "Pronom réfléchi", "VOL": "Déplacement aérien",
        },
        "images": {
            "REPAIRE": ("Repaire", "Cachette", "🏚️"),
            "GRIFFE": ("Griffe", "Patte avec griffes", "🐾"),
            "REMOUS": ("Remous", "Tourbillon d'eau", "🌊"),
            "TRI": ("Tri", "Tri des déchets", "♻️"),
        },
    },
    {
        "definitions": {
            "LOMBRIC": "Ver de terre", "ACEROLA": "Petite cerise tropicale", "STRASS": "Faux diamants",
            "SALSA": "Danse latine", "EVE": "Première femme", "RESPECT": "Considération",
            "LASSER": "Fatiguer par ennui", "OCTAVE": "Intervalle musical", "MERLES": "Oiseaux noirs",
            "BRAS": "Membre supérieur", "CPE": "Conseiller scolaire", "ROSACE": "Ornement circulaire",
            "ILS": "Pronom masculin", "PC": "Ordinateur personnel", "CA": "Cela familièrement",
            "MET": "Gala new-yorkais",
        },
        "images": {
            "LOMBRIC": ("Lombric", "Ver de terre", "🪱"),
            "SALSA": ("Salsa", "Danse salsa", "💃"),
            "MERLES": ("Merles", "Oiseau noir", "🐦‍⬛"),
            "BRAS": ("Bras", "Bras musclé", "💪"),
            "PC": ("PC", "Ordinateur", "💻"),
        },
    },
    {
        "definitions": {
            "CALOTTE": "Petit bonnet rond", "INITIAL": "Du début", "SEMENCE": "Graine à planter",
            "ETANT": "Participe d'être", "AH": "Cri de surprise", "USB": "Prise informatique",
            "CISEAU": "Outil à couper", "ANETHS": "Herbes aromatiques", "LIMA": "Capitale du Pérou",
            "TETE": "Partie du corps", "OTENT": "Enlèvent", "RAS": "Coupé très court",
            "TINTER": "Produire un son", "TAC": "Bruit sec", "TA": "Possessif féminin",
            "ELEVES": "Personnes scolarisées",
        },
        "images": {
            "SEMENCE": ("Semence", "Graine", "🌱"),
            "USB": ("USB", "Clé USB", "🔌"),
            "CISEAU": ("Ciseau", "Ciseaux", "✂️"),
            "TETE": ("Tête", "Tête", "🙂"),
        },
    },
    {
        "definitions": {
            "PLOMBER": "Rendre très lourd", "ROMAINE": "Habitante de Rome", "OC": "Langue du Midi",
            "MAMELON": "Petite colline", "ELU": "Choisi par vote", "TE": "Pronom de toi",
            "PROMET": "Donne sa parole", "LOCALE": "Du voisinage", "OM": "Club de Marseille",
            "MU": "Lettre grecque", "TETU": "Refuse de céder", "PERE": "Papa",
            "MATE": "Regarde fixement", "LUI": "Pronom masculin", "BIELLE": "Pièce du moteur",
            "ENTOUR": "Place autour", "REUNIE": "Rassemblée",
        },
        "images": {
            "ELU": ("Élu", "Bulletin de vote", "🗳️"),
            "PERE": ("Père", "Papa et enfant", "👨‍👧"),
            "BIELLE": ("Bielle", "Pièce mécanique", "⚙️"),
            "REUNIE": ("Réunie", "Personnes réunies", "🫂"),
        },
        "assets": {
            "ROMAINE": ("Romaine", "Colisée de Rome", "/assets/clues/custom/colisee.svg"),
        },
    },
]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    grids = source.get("grids", [])
    if len(grids) != len(CURATIONS):
        raise ValueError(f"{len(grids)} grilles brutes pour {len(CURATIONS)} revues")

    curated = []
    for index, (grid, review) in enumerate(zip(grids, CURATIONS, strict=True), 1):
        actual = {item["answer"] for item in grid["answers"]}
        definitions = review["definitions"]
        if actual != set(definitions):
            raise ValueError(
                f"grille {index}: manquants={sorted(actual - set(definitions))}, "
                f"superflus={sorted(set(definitions) - actual)}"
            )
        images = review.get("images", {})
        assets = review.get("assets", {})
        image_keys = set(images) | set(assets)
        # Le propriétaire a demandé explicitement une définition pour CONDOR.
        # Cette grille conserve donc exceptionnellement trois images validées.
        minimum_images = int(review.get("minimumImages", 4))
        if not minimum_images <= len(image_keys) <= 6 or not image_keys <= actual or set(images) & set(assets):
            raise ValueError(f"grille {index}: sélection d'images invalide")
        curated.append({
            **grid,
            "id": f"compact-7x8-young-balanced-{index:02d}",
            "minimumImages": minimum_images,
            "answers": [
                {**item, "definition": definitions[item["answer"]]}
                for item in grid["answers"]
            ],
            "imageAnswers": [
                {"answer": answer, "concept": concept, "alt": alt, "emoji": emoji}
                for answer, (concept, alt, emoji) in images.items()
            ] + [
                {"answer": answer, "concept": concept, "alt": alt, "asset": asset}
                for answer, (concept, alt, asset) in assets.items()
            ],
            "editorialStatus": "manually-reviewed",
            "publicationStatus": "owner-review-required",
        })

    payload = {
        "version": 1,
        "kind": "compact-7x8-young-balanced-curated-candidates",
        "catalogModified": False,
        "grids": curated,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    retained_payload = {
        **payload,
        "kind": "compact-7x8-young-balanced-retained-for-repair",
        "grids": [
            grid for number, grid in enumerate(curated, 1)
            if number in RETAINED_GRID_NUMBERS
        ],
    }
    RETAINED_OUTPUT.write_text(
        json.dumps(retained_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"grids": len(curated), "output": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
