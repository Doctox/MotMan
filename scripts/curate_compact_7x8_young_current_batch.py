#!/usr/bin/env python3
"""Editorial curation for the ten current-language 7x8 owner-review grids."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output/quality/compact-7x8-young-current-raw-ten.json"
OUTPUT = ROOT / "output/quality/compact-7x8-young-current-curated.json"


CURATIONS = [
    {
        "definitions": {
            "CENSEUR": "Contrôle les médias", "OREILLE": "Organe de l'ouïe",
            "PROMETS": "Donne ta parole", "ION": "Atome chargé", "EN": "Dans",
            "RETIRES": "Enlèves", "COPIER": "Faire un double", "ERRONE": "Faux",
            "NEON": "Tube lumineux", "NEMO": "Poisson de Pixar", "SIM": "Carte du mobile",
            "NI": "Et pas", "VIT": "Habite", "ELEVER": "Faire grandir",
            "ULTIME": "Tout dernier", "RESTOS": "Lieux pour manger",
        },
        "images": {
            "OREILLE": ("Oreille", "Oreille humaine", "👂"),
            "ION": ("Ion", "Atome chargé", "⚛️"),
            "COPIER": ("Copier", "Deux documents identiques", "📋"),
            "RESTOS": ("Restaurants", "Repas au restaurant", "🍽️"),
        },
    },
    {
        "definitions": {
            "AMATEUR": "Non professionnel", "RAMASSE": "Prend au sol", "CRI": "Son très fort",
            "AVERENT": "Se révèlent", "DE": "Provenant de", "ELYSEES": "Avenue parisienne",
            "ARCADE": "Jeu à pièces", "MARVEL": "Maison des Avengers", "AMIE": "Proche appréciée",
            "ACTE": "Partie de pièce", "TA": "À toi", "RAS": "Rien à signaler",
            "PAS": "Avec « ne »", "ESPECE": "Sorte", "USANTE": "Qui fatigue",
            "RESTES": "Morceaux laissés",
        },
        "images": {
            "RAMASSE": ("Ramasser", "Balai qui ramasse", "🧹"),
            "CRI": ("Cri", "Visage qui crie", "😱"),
            "ARCADE": ("Arcade", "Jeu d'arcade", "🕹️"),
            "AMIE": ("Amie", "Deux amies", "🫂"),
        },
    },
    {
        "definitions": {
            "CIERGES": "Grandes bougies", "AMBIANT": "Tout autour", "SPOTIFY": "Appli de musique",
            "SOU": "Ancienne monnaie", "ELLA": "Prénom de Fitzgerald", "SIESTES": "Repos après-midi",
            "CASSES": "Brises", "IMPOLI": "Mal élevé", "EBOULE": "Fait tomber",
            "RIT": "S'amuse", "AS": "Champion", "NIL": "Fleuve d'Afrique",
            "GAIN": "Somme remportée", "LE": "Article masculin", "ENFILE": "Met un vêtement",
            "STYLES": "Façons de faire",
        },
        "images": {
            "CIERGES": ("Cierges", "Grandes bougies", "🕯️"),
            "SIESTES": ("Siestes", "Personne endormie", "😴"),
            "SOU": ("Sou", "Petite pièce", "🪙"),
            "GAIN": ("Gain", "Argent gagné", "💰"),
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
            "CREPITE": "Fait de petits bruits", "RELIAIT": "Mettait ensemble", "AVIS": "Opinion",
            "MORETTI": "Bière italienne", "PIE": "Oiseau bicolore", "ET": "Relie deux mots",
            "CRAMPE": "Contraction douloureuse", "REVOIT": "Regarde encore", "ELIRE": "Choisir par vote",
            "CAKE": "Gâteau anglais", "PISE": "Tour penchée", "VOL": "Trajet aérien",
            "IA": "Intelligence artificielle", "TVA": "Taxe à 20 %", "KO": "Hors combat",
            "TIKTOK": "Réseau de vidéos", "ETOILE": "Astre lumineux",
        },
        "images": {
            "CREPITE": ("Crépite", "Feu qui crépite", "🔥"),
            "CAKE": ("Cake", "Part de gâteau", "🍰"),
            "VOL": ("Vol", "Avion en vol", "✈️"),
            "ETOILE": ("Étoile", "Étoile brillante", "⭐"),
        },
    },
    {
        "definitions": {
            "PIKACHU": "Pokémon jaune", "AMADEUS": "Mozart, second prénom", "PARE": "Bloque le coup",
            "AGENCER": "Disposer ensemble", "YEN": "Monnaie japonaise", "ES": "Forme d'être",
            "PAPAYE": "Fruit tropical", "IMAGES": "Représentations visuelles", "KAREN": "Prénom devenu mème",
            "OURS": "Grand mammifère", "ADEN": "Port du Yémen", "RUE": "Voie en ville",
            "CE": "Pronom démonstratif", "CRU": "Non cuit", "MU": "Lettre grecque",
            "HUMEUR": "État d'esprit", "USURES": "Dégradations lentes",
        },
        "images": {
            "YEN": ("Yen", "Billet japonais", "💴"),
            "IMAGES": ("Images", "Images encadrées", "🖼️"),
            "OURS": ("Ours", "Ours brun", "🐻"),
            "HUMEUR": ("Humeur", "Visage expressif", "🙂"),
        },
    },
    {
        "definitions": {
            "EMANANT": "Provenant de", "RAVAGER": "Tout détruire", "ATONE": "Sans éclat",
            "FRIAND": "Qui adore", "LIN": "Plante textile", "EXEGESE": "Analyse de texte",
            "ERAFLE": "Petite blessure", "MATRIX": "Pilule rouge", "AVOINE": "Céréale",
            "NANA": "Femme, familièrement", "TOM": "Prénom de Voldemort", "AGENTE": "Employée en mission",
            "NE": "Venu au monde", "DOS": "Arrière du corps", "TRI": "Classement",
            "ME": "Pronom personnel",
        },
        "images": {
            "RAVAGER": ("Ravager", "Tornade destructrice", "🌪️"),
            "ERAFLE": ("Éraflure", "Petite blessure", "🩹"),
            "AVOINE": ("Avoine", "Épis d'avoine", "🌾"),
            "TRI": ("Tri", "Symbole de tri", "♻️"),
        },
    },
    {
        "definitions": {
            "ECORCES": "Peaux des arbres", "COUPOLE": "Toit arrondi", "ORIGNAL": "Élan du Canada",
            "UNE": "Article féminin", "TE": "Pronom personnel", "ETUDIEE": "Analysée",
            "ECOUTE": "Prête l'oreille", "CORNET": "Cône de glace", "OUIE": "Sens auditif",
            "BONI": "Petit bonus", "RPG": "Jeu de rôle", "BD": "Bande dessinée",
            "VIF": "Plein d'énergie", "CONVOI": "Groupe de véhicules", "ELAINE": "Héroïne de Seinfeld",
            "SELFIE": "Photo de soi",
        },
        "images": {
            "ECORCES": ("Écorce", "Écorces d'arbres", "🌳"),
            "ORIGNAL": ("Orignal", "Grand orignal", "🫎"),
            "CORNET": ("Cornet", "Cornet de glace", "🍦"),
            "SELFIE": ("Selfie", "Autoportrait mobile", "🤳"),
        },
    },
    {
        "definitions": {
            "ALABAMA": "État du Sud", "BAHAMAS": "Archipel des Caraïbes", "OM": "Club marseillais",
            "LIBAN": "Pays du Cèdre", "INONDEE": "Couverte d'eau", "SENTEUR": "Odeur agréable",
            "ABOLIS": "Supprimés", "LAMINE": "Écrase", "AH": "Cri surpris", "BON": "De qualité",
            "SEPT": "Après six", "BASANT": "Prenant appui", "AMENDE": "Sanction financière",
            "MAP": "Carte de jeu", "EU": "Obtenu", "ASTIER": "Alexandre de Kaamelott",
        },
        "images": {
            "LIBAN": ("Liban", "Drapeau du Liban", "🇱🇧"),
            "INONDEE": ("Inondée", "Zone inondée", "🌊"),
            "SENTEUR": ("Senteur", "Nez qui sent", "👃"),
            "MAP": ("Carte", "Carte de jeu", "🗺️"),
        },
    },
    {
        "definitions": {
            "BREVETS": "Diplômes ou inventions", "RETENUE": "Gardée", "AMANT": "Partenaire amoureux",
            "SOUTIEN": "Aide", "SU": "Appris", "ESTEREL": "Massif provençal",
            "BRASSE": "Nage ventrale", "REMOUS": "Eau agitée", "ETAU": "Outil qui serre",
            "REVU": "Regardé encore", "VENTRE": "Milieu du corps", "ENTIER": "Complet",
            "TU": "Pronom familier", "EVE": "Première femme", "SE": "Pronom réfléchi",
            "NUL": "Très mauvais",
        },
        "images": {
            "BREVETS": ("Brevets", "Diplôme obtenu", "🎓"),
            "SOUTIEN": ("Soutien", "Mains solidaires", "🤝"),
            "BRASSE": ("Brasse", "Nageur en brasse", "🏊"),
            "REMOUS": ("Remous", "Eau agitée", "🌊"),
        },
    },
]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    grids = source.get("grids", [])
    if len(grids) != len(CURATIONS):
        raise ValueError(f"{len(grids)} grilles brutes pour {len(CURATIONS)} curations")

    seen_answers: set[str] = set()
    curated = []
    for index, (grid, review) in enumerate(zip(grids, CURATIONS, strict=True), 1):
        actual = {item["answer"] for item in grid["answers"]}
        definitions = review["definitions"]
        if actual != set(definitions):
            raise ValueError(
                f"grille {index}: manquants={sorted(actual - set(definitions))}, "
                f"superflus={sorted(set(definitions) - actual)}"
            )
        repeated = sorted(actual & seen_answers)
        if repeated:
            raise ValueError(f"grille {index}: réponses répétées {repeated}")
        seen_answers.update(actual)
        images = review["images"]
        if not 4 <= len(images) <= 6 or not set(images) <= actual:
            raise ValueError(f"grille {index}: sélection d'images invalide")
        curated.append({
            **grid,
            "id": f"compact-7x8-young-current-{index:02d}",
            "answers": [
                {**item, "definition": definitions[item["answer"]]}
                for item in grid["answers"]
            ],
            "imageAnswers": [
                {"answer": answer, "concept": concept, "alt": alt, "emoji": emoji}
                for answer, (concept, alt, emoji) in images.items()
            ],
            "minimumImages": 4,
            "editorialStatus": "manually-reviewed",
            "publicationStatus": "owner-review-required",
        })

    payload = {
        "version": 1,
        "kind": "compact-7x8-young-current-curated",
        "catalogModified": False,
        "editorialProfile": "current-language-pop-balanced",
        "grids": curated,
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"grids": len(curated), "answers": len(seen_answers)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
