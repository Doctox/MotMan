"""Prepare the owner-review staging for certified handoff 111bca5d3810.

This command is intentionally unable to publish. It verifies the immutable
words-only handoff and lexical audit, selects the editorial sublot, adds
human-written clues and reviewed image clues, then writes review artifacts
outside both MotMan catalogs.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date
from html import escape
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_compact_7x8_review import render_playtest_html  # noqa: E402
from editorial_quality import pilot_editorial_errors  # noqa: E402
from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402


SOURCE_EXPORT = Path(
    r"C:\Users\peete\AppData\Local\MotManLexiconStudio\exports"
    r"\motman-certified-grids-for-editorialization-1.json"
)
SOURCE_AUDIT = Path(
    r"C:\Users\peete\OneDrive\Documents\MotMan Grid Factory\reports"
    r"\lexical-reservoir\certified-batch-lexical-audit-111bca5d3810.json"
)
EXPECTED_FILE_SHA256 = (
    "111bca5d3810ca201e5c36bfb1a4757a3c700df458bda010a1a8ec9a406eeace"
)
EXPECTED_PAYLOAD_SHA256 = (
    "7d46720680a914d11387b2b06024ab4e30d815e4f725ba8a506693fac9a8837e"
)
EXPECTED_AUDIT_SHA256 = (
    "37974d2fce8bf112ebc67a37b9c12c6bfe2ac33e1d019d905d643f50089254cb"
)
EXPECTED_SCHEMA = "motman-grid-certified-editorial-handoff"
EXPECTED_VERSION = 1
EXPECTED_CATALOG_VERSION = 20
EXPECTED_ACTIVE_GRID_COUNT = 29
EXPECTED_CATALOG_SHA256 = (
    "a8f835fe665d2bc4465153064ab16983e5d2d1804ae635b97808f65b019870f3"
)
EXPECTED_RUNTIME_SHA256 = (
    "4827f6882e92e13cb8a3577f329f3ceb30f5b137f0fb59c3914dd323dec023f4"
)

CATALOG_PATH = ROOT / "src/data/grid.catalog.json"
RUNTIME_PATH = ROOT / "src/data/runtime.grid.catalog.json"
BLACKLIST_PATH = ROOT / "src/data/editorial.blacklist.json"
OUTPUT_DIR = ROOT / "output/quality/certified-editorial-111bca5d3810"
STAGING_PATH = OUTPUT_DIR / "staging.json"
AUDIT_PATH = OUTPUT_DIR / "audit.json"
SELECTION_PATH = OUTPUT_DIR / "selection-report.json"
REVIEW_PATH = OUTPUT_DIR / "owner-review-with-solutions.html"
PLAYTEST_PATH = OUTPUT_DIR / "owner-playtest-no-solutions.html"
ARTIFACT_MANIFEST_PATH = OUTPUT_DIR / "artifact-manifest.json"

EDITORIAL_SOURCE_ID = "motman-editorial-certified-111bca5d3810"
EDITORIAL_SOURCE_URL = "internal://motman/editorial/certified-111bca5d3810"
REVIEW_DATE = "2026-07-29"


RETAINED_CANDIDATES = (
    "8c1758ee-5ce6-4312-b370-7ed29002bad2",
    "23f625ed-9215-4709-ab5c-17f9c82d6ea0",
    "9b33481d-ee53-44a0-951e-ed616b3c60de",
    "fa4c2538-1fdb-4149-8bab-d68d397d2686",
    "e0076126-02af-4919-acf9-4e5130cbf9f2",
    "7899d39f-3076-40c2-b913-898f398c2304",
    "49100aab-d329-419c-aea4-df030e5929d6",
    "0dbb98eb-2306-40ea-b511-e0ba3120d8bc",
    "004254ee-d74d-4b91-bdb3-4c108979b3f9",
    "11e4c294-c2fc-4eb2-b5d4-e58d9649a0eb",
    "d95997f7-8f13-4379-b01a-a42ac0163c35",
    "2427f525-9430-4aac-80e9-431bdba9e29b",
    "4f43eb77-4be7-4aab-b85c-8340bcf45673",
    "7b3bca78-1112-4f32-bd9a-69c010364b69",
    "8e4177e9-5b86-4c40-ab26-b579d1e4202e",
)


EXCLUSIONS: dict[str, dict[str, Any]] = {
    "0092d1d2-c124-4493-bca6-37703e8764d0": {
        "category": "active-exact-duplicate",
        "reason": "Grille déjà active à l’identique dans le catalogue v20.",
    },
    "081c89e3-c392-4258-a0e0-cffec95b2f43": {
        "category": "active-exact-duplicate",
        "reason": "Grille déjà active à l’identique dans le catalogue v20.",
    },
    "5354b8e2-bf35-45ce-9cbd-d96f1bbf7012": {
        "category": "active-exact-duplicate",
        "reason": "Grille déjà active à l’identique dans le catalogue v20.",
    },
    "e9a3ddde-9e24-4fe1-9e42-9a9ff2f6a1c9": {
        "category": "owner-avoid-next-lot",
        "reason": "Contient ANS, sous décision propriétaire avoid-next-lot.",
    },
    "ff14f81e-946d-48f4-a545-d80cc7dbd47e": {
        "category": "strong-pair-against-active",
        "reason": (
            "Variante à 88,9 % de la candidate 081c89e3, déjà active ; "
            "la variante nouvelle est écartée."
        ),
    },
    "0046c9fc-ab63-486e-9cd2-555c76234331": {
        "category": "strong-pair-loser",
        "reason": (
            "Paire à 88,2 % : 8e4177e9 est retenue pour son meilleur score "
            "(-29,12 contre -32,24), sa répétition légèrement moindre et RELIRE."
        ),
    },
    "09fa406f-3b78-4c8b-8c27-110dc41cafff": {
        "category": "strong-pair-loser",
        "reason": (
            "Paire à 88,2 % : 0dbb98eb est retenue pour son meilleur score "
            "(-240,78 contre -319,86) et sa moindre exposition au catalogue actif."
        ),
    },
    "e660b8f7-902f-4ed7-94ff-40dcab75a643": {
        "category": "strong-pair-loser",
        "reason": (
            "Paire à 88,2 % : fa4c2538 est retenue ; NET est plus familier "
            "et naturel que NEM dans cette variante."
        ),
    },
    "f104a449-96cf-47be-b99d-08aaa85a0117": {
        "category": "near-clone-loser",
        "reason": (
            "Quasi-clone à 78,9 % de 8c1758ee ; 8c1758ee a une meilleure "
            "familiarité minimale et une répétition historique plus faible."
        ),
    },
    "4f9ecf0e-521f-482d-9811-39b7ff8267f3": {
        "category": "near-clone-loser",
        "reason": (
            "Quasi-clone à 78,9 % de d95997f7 ; d95997f7 a un bien meilleur "
            "score et remplace OIE/OR par VIE/VR."
        ),
    },
    "597497bb-14c6-4612-9563-2b831f07d304": {
        "category": "near-clone-loser",
        "reason": (
            "Quasi-clone à 77,8 % de 112a5005 ; 112a5005 avait le meilleur "
            "score avant le contrôle éditorial final."
        ),
    },
    "050dbaf7-d1ac-4a0a-a2ae-83bac50dd420": {
        "category": "semantic-duplicate",
        "reason": (
            "AVOCAT et AVOCATS désignent le même concept dans la même grille ; "
            "ce doublon morphologique est bloquant."
        ),
    },
    "1ea6b510-141f-48d0-97af-8ede77ab946b": {
        "category": "diversity-near-variant",
        "reason": (
            "Partage douze réponses avec 004254ee sur la même silhouette ; "
            "sa variante réintroduit IL, SEL et ICI. 004254ee est gardée."
        ),
    },
    "f05ea753-9339-4104-b3c1-4df468e787b9": {
        "category": "crosswordese",
        "reason": (
            "OYE est une graphie archaïque d’OIE ; la grille ne respecte pas "
            "la ligne éditoriale actuelle malgré une définition possible."
        ),
    },
    "f8a0d5f1-5b6f-46aa-bc12-4d12bc445c38": {
        "category": "crosswordese-and-weak-form",
        "reason": (
            "CASTEL est trop daté et TIRANT est une forme verbale faible ; "
            "ÉTAGÉE est définissable mais ne suffit pas à sauver la grille."
        ),
    },
    "112a5005-761a-4cba-8de8-5fb21239a34a": {
        "category": "specialist-word",
        "reason": (
            "RAISINÉ, confiture traditionnelle de raisin, est trop spécialisé "
            "pour le public prioritaire ; son retrait réduit aussi IL/EST/SEL."
        ),
    },
    "12271efe-6e97-4c8f-8d86-b283d93f70d0": {
        "category": "global-repetition",
        "reason": (
            "Grille correcte isolément, mais elle cumule ÉTÉ, EAU, RUE, OR et "
            "la petite conjugaison SUE ; elle dégrade trop la diversité du lot."
        ),
    },
    "f29ed29e-eb25-430e-9e04-85741d3e0ad9": {
        "category": "global-repetition-and-weak-forms",
        "reason": (
            "Cumule ÉTÉ, TEE, VR, UN et REPEINT déjà présents, avec REMIS/PURS ; "
            "son apport lexical ne compense pas la répétition."
        ),
    },
}


# One manually written fallback definition for every distinct retained answer.
# Displayed image clues intentionally have an empty ``clue`` but keep this
# textual fallback in ``editorialDefinition``.
CLUES: dict[str, str] = {
    "ABDOMEN": "Ventre",
    "ABJECT": "Très méprisable",
    "ACCRUE": "Devenue plus forte",
    "ACRE": "Mesure foncière britannique",
    "AGENDA": "Planning personnel",
    "AGES": "Périodes de vie",
    "ALERTE": "Signal de danger",
    "ALIAGAS": "Nikos",
    "ALIENER": "Perdre la raison",
    "ALLIES": "Partenaires de combat",
    "AMANITE": "Champignon parfois toxique",
    "AMARRE": "Corde de quai",
    "AME": "Partie spirituelle",
    "AMI": "Proche de confiance",
    "AMINCI": "Devenu plus mince",
    "AMONT": "Vers la source",
    "AMORCER": "Commencer un mouvement",
    "AMUSANT": "Qui fait rire",
    "AN": "Douze mois",
    "ANANAS": "Fruit à couronne",
    "ANERIE": "Grosse bêtise",
    "ANIMEE": "Pleine de vie",
    "API": "Interface logicielle",
    "ARENES": "Lieu de combats",
    "AS": "Champion",
    "AVENANT": "Ajout au contrat",
    "AVIS": "Opinion exprimée",
    "AVOCAT": "Défenseur au tribunal",
    "AVOINES": "Céréales des chevaux",
    "AYA": "Prénom de Nakamura",
    "BD": "Bande dessinée",
    "BEIGNET": "Donut d’Homer",
    "BINETTE": "Petite pioche",
    "BOITER": "Marcher de travers",
    "CABLAGE": "Ensemble de fils",
    "CADDIE": "Chariot de courses",
    "CAMERAS": "Appareils de tournage",
    "CAPOTS": "Couvercles de moteurs",
    "CENTRE": "Point du milieu",
    "CHINEUR": "Fan de brocantes",
    "CIMENT": "Liant du béton",
    "CITE": "Ville fortifiée",
    "CLAPET": "Valve anti-retour",
    "COU": "Soutien de tête",
    "COURGE": "Gros légume orange",
    "CRI": "Son très fort",
    "CRUE": "Montée des eaux",
    "DANSER": "Bouger en rythme",
    "DEFACER": "Abîmer un visage",
    "DEPENS": "Dépense",
    "DESIRER": "Avoir très envie",
    "DETONER": "Exploser",
    "DJ": "Mixeur de soirée",
    "DOPANT": "Produit stimulant",
    "DOS": "Arrière du corps",
    "DRE": "Mentor d’Eminem",
    "EAU": "Liquide indispensable",
    "ECLATE": "En mille morceaux",
    "ECUYER": "Cavalier",
    "EDITEUR": "Publie des livres",
    "EGO": "Idée de soi",
    "EMERITE": "Très expérimenté",
    "EMEUTE": "Violence de foule",
    "ENIEME": "Encore une fois",
    "ENIGME": "Question mystérieuse",
    "ENTREE": "Accès principal",
    "EPI": "Tête de céréale",
    "EROSION": "Usure naturelle",
    "ESSORER": "Retirer l’eau",
    "EST": "Direction du levant",
    "ETAGERE": "Tablette de rangement",
    "ETALON": "Mâle reproducteur",
    "ETAU": "Outil de serrage",
    "ETE": "Saison chaude",
    "ETERNEL": "Sans fin",
    "ETRIER": "Appui du cavalier",
    "FATRAS": "Tas désordonné",
    "FIER": "Content de soi",
    "FRAISE": "Fruit rouge",
    "FRATRIE": "Frères et sœurs",
    "FRET": "Transport de marchandises",
    "FUMISTE": "Pas très sérieux",
    "GAG": "Blague visuelle",
    "GARDON": "Poisson des étangs",
    "GENEUR": "Personne embarrassante",
    "GLACON": "Petit cube glacé",
    "GRAS": "Riche en graisse",
    "GRAVATS": "Débris de chantier",
    "GREFFE": "Transplantation d’organe",
    "GRIMACE": "Expression du visage",
    "GUI": "Plante de Noël",
    "HIC": "Petit problème",
    "HUMIDE": "Légèrement mouillé",
    "IA": "Intelligence artificielle",
    "ICI": "À cet endroit",
    "IL": "Pronom masculin",
    "INCULTE": "Sans connaissances",
    "INERTE": "Sans mouvement",
    "INERTES": "Sans mouvement",
    "ION": "Atome chargé",
    "IRL": "Dans la réalité",
    "IRONIE": "Moquerie implicite",
    "ITEM": "Élément de liste",
    "JUS": "Boisson de fruits",
    "LANDAU": "Voiture de bébé",
    "LATINES": "Femmes hispaniques",
    "LIN": "Plante textile",
    "LIVE": "Diffusion en direct",
    "LOPEZ": "Nom de JLo",
    "LOTI": "Bien pourvu",
    "LURONNE": "Femme très enjouée",
    "MALOTRU": "Personne très grossière",
    "MDR": "Rire en texto",
    "MEDINA": "Vieille ville arabe",
    "MINES": "Visages familiers",
    "MUR": "Paroi verticale",
    "NEM": "Rouleau vietnamien",
    "NET": "Sans bavure",
    "NEZ": "Organe olfactif",
    "NID": "Abri des oiseaux",
    "NIVEAU": "Degré atteint",
    "NON": "Réponse négative",
    "OCARINA": "Flûte en terre",
    "OCTROI": "Attribution officielle",
    "ON": "Pronom indéfini",
    "OR": "Métal précieux",
    "OS": "Pièce du squelette",
    "OSER": "Avoir l’audace",
    "OUI": "Réponse positive",
    "OUT": "Mis hors jeu",
    "PARTNER": "Partenaire en anglais",
    "PASTAGA": "Pastis",
    "PATTES": "Membres des animaux",
    "PERSIL": "Herbe aromatique",
    "PIN": "Conifère à aiguilles",
    "PLACARD": "Rangement mural",
    "PRIMES": "Bonus financiers",
    "PUR": "Sans mélange",
    "RABAIS": "Réduction de prix",
    "RACLURE": "Résidu gratté",
    "RACOLER": "Attirer avec insistance",
    "RAIFORT": "Racine très piquante",
    "RANCHS": "Fermes de cowboys",
    "RAS": "Coupé très court",
    "RASAGE": "Suppression de barbe",
    "RASOIR": "Lame à barbe",
    "RAVINE": "Creux d’érosion",
    "RECRUES": "Nouveaux membres",
    "REDUIT": "Rapetisse",
    "REFERE": "Procédure judiciaire urgente",
    "REGAIN": "Force revenue",
    "RELAIS": "Transmission d’équipe",
    "RELIRE": "Lire de nouveau",
    "RENDUE": "Restituée",
    "RENEGAT": "Fidèle devenu traître",
    "REPEINT": "Recouvert de peinture",
    "RESIGNE": "Sans plus lutter",
    "RESTES": "Ce qui demeure",
    "RETAPE": "Remis à neuf",
    "RETOUR": "Fait de revenir",
    "RIGIDES": "Sans souplesse",
    "RINCER": "Laver abondamment",
    "ROI": "Monarque couronné",
    "ROSEAU": "Plante des marais",
    "RUE": "Voie en ville",
    "SARI": "Tenue indienne drapée",
    "SEC": "Sans humidité",
    "SEL": "Cristaux d’assaisonnement",
    "SERVANT": "Employé domestique",
    "SET": "Manche au tennis",
    "SIA": "Chanteuse de Chandelier",
    "SINUER": "Avancer en courbes",
    "SNAP": "Photo éphémère",
    "SOUVENT": "Fréquemment",
    "STRESS": "Tension nerveuse",
    "STRICT": "Sans indulgence",
    "SUE": "Transpire",
    "SURGELE": "Gelé industriellement",
    "TAF": "Travail familièrement",
    "TANT": "À ce point",
    "TARAMA": "Tartinade grecque rose",
    "TASSEES": "Serrées ensemble",
    "TASSES": "Récipients à café",
    "TATA": "Tante familière",
    "TAUTOU": "Audrey dans Amélie",
    "TEE": "Support de balle",
    "TENTER": "Essayer malgré tout",
    "TINTER": "Produire un son",
    "TRAQUER": "Poursuivre sans relâche",
    "TREUIL": "Appareil de levage",
    "TRI": "Action de classer",
    "TRIP": "Voyage hallucinatoire",
    "TROU": "Creuser",
    "TRUANDE": "Femme malhonnête",
    "UN": "Premier nombre",
    "UNE": "Article féminin",
    "VETIR": "Habiller quelqu’un",
    "VIE": "Existence",
    "VIS": "Fixation filetée",
    "VR": "Réalité virtuelle",
}


IMAGE_SPECS: dict[str, dict[str, str]] = {
    "ANANAS": {
        "asset": "/assets/clues/twemoji/ananas.svg",
        "alt": "Un ananas mûr",
        "concept": "fruit tropical couronné",
    },
    "ARENES": {
        "asset": "/assets/clues/custom/colisee.svg",
        "alt": "Un amphithéâtre antique",
        "concept": "arènes antiques",
        "source": "MotMan original",
        "license": "MotMan original",
    },
    "BD": {
        "asset": "/assets/clues/twemoji/bd.svg",
        "alt": "Une bande dessinée ouverte",
        "concept": "bande dessinée",
    },
    "CAMERAS": {
        "asset": "/assets/clues/twemoji/camera.svg",
        "alt": "Une caméra de tournage",
        "concept": "caméras",
    },
    "EAU": {
        "asset": "/assets/clues/twemoji/eau.svg",
        "alt": "Une goutte d’eau",
        "concept": "eau",
    },
    "ENTREE": {
        "asset": "/assets/clues/twemoji/porte.svg",
        "alt": "Une porte d’entrée",
        "concept": "entrée",
    },
    "ETE": {
        "asset": "/assets/clues/twemoji/soleil.svg",
        "alt": "Un soleil estival",
        "concept": "été",
    },
    "FRAISE": {
        "asset": "/assets/clues/twemoji/fraise.svg",
        "alt": "Une fraise rouge",
        "concept": "fraise",
    },
    "MUR": {
        "asset": "/assets/clues/twemoji/mur.svg",
        "alt": "Un mur en briques",
        "concept": "mur",
    },
    "NEZ": {
        "asset": "/assets/clues/twemoji/nez.svg",
        "alt": "Un nez",
        "concept": "nez",
    },
    "NID": {
        "asset": "/assets/clues/twemoji/nid.svg",
        "alt": "Un nid d’oiseau",
        "concept": "nid",
    },
    "OS": {
        "asset": "/assets/clues/twemoji/os.svg",
        "alt": "Un os",
        "concept": "os",
    },
    "PIN": {
        "asset": "/assets/clues/twemoji/pin.svg",
        "alt": "Un pin",
        "concept": "pin",
    },
    "ROI": {
        "asset": "/assets/clues/twemoji/roi.svg",
        "alt": "Un roi couronné",
        "concept": "roi",
    },
    "TASSES": {
        "asset": "/assets/clues/twemoji/tasse.svg",
        "alt": "Deux tasses",
        "concept": "tasses",
    },
}


PROPER_NAME_REVIEWS: dict[str, dict[str, Any]] = {
    "ALIAGAS": {
        "entityType": "personne",
        "distinctiveTokens": ["Nikos"],
        "sourceUrl": "https://www.tf1info.fr/actualite/nikos-aliagas-10693/",
        "acceptedAs": "Nikos Aliagas",
    },
    "AYA": {
        "entityType": "personne",
        "distinctiveTokens": ["Nakamura"],
        "sourceUrl": "https://www.ayanakamura-officiel.com/",
        "acceptedAs": "Aya Nakamura",
    },
    "DRE": {
        "entityType": "personne",
        "distinctiveTokens": ["Eminem"],
        "sourceUrl": "https://www.drdre.com/videos/",
        "acceptedAs": "Dr. Dre",
    },
    "LOPEZ": {
        "entityType": "personne",
        "distinctiveTokens": ["JLo"],
        "sourceUrl": "https://www.biography.com/musicians/jennifer-lopez",
        "acceptedAs": "Jennifer Lopez",
    },
    "SIA": {
        "entityType": "personne",
        "distinctiveTokens": ["Chandelier"],
        "sourceUrl": "https://universalmusic.fr/artistes/20000379074",
        "acceptedAs": "Sia",
    },
    "TAUTOU": {
        "entityType": "personne",
        "distinctiveTokens": ["Amélie"],
        "sourceUrl": (
            "https://www.unifrance.org/film/20864/"
            "le-fabuleux-destin-d-amelie-poulain"
        ),
        "acceptedAs": "Audrey Tautou",
    },
}


COMMON_ANGLICISMS = {
    "API",
    "DJ",
    "IRL",
    "LIVE",
    "OUT",
    "PARTNER",
    "SET",
    "SNAP",
    "TEE",
    "TRIP",
    "VR",
}
CURRENT_COMMON = COMMON_ANGLICISMS | {"IA", "MDR", "TAF"}


FLAGGED_FORM_REVIEWS: dict[str, dict[str, Any]] = {
    "ALIAGAS": {
        "status": "accepted-retained",
        "definition": "Nikos",
        "reason": "Nom médiatique actuel, fait distinctif court et non ambigu.",
        "candidateId": "4f43eb77-4be7-4aab-b85c-8340bcf45673",
    },
    "DEFACER": {
        "status": "accepted-retained",
        "definition": "Abîmer un visage",
        "reason": "Verbe français transparent, définition directe et actuelle.",
        "candidateId": "e0076126-02af-4919-acf9-4e5130cbf9f2",
    },
    "FOSTER": {
        "status": "acceptable-form-grid-excluded",
        "definition": "Nom de Jodie",
        "reason": "Nom propre devinable, mais la grille est déjà active à l’identique.",
        "candidateId": "0092d1d2-c124-4493-bca6-37703e8764d0",
    },
    "LOPEZ": {
        "status": "accepted-retained",
        "definition": "Nom de JLo",
        "reason": "Référence pop largement connue, indice distinctif et stable.",
        "candidateId": "0dbb98eb-2306-40ea-b511-e0ba3120d8bc",
    },
    "LOUNGE": {
        "status": "acceptable-form-grid-excluded",
        "definition": "Salon d’aéroport",
        "reason": (
            "Anglicisme courant et définissable, mais la grille porte le doublon "
            "AVOCAT/AVOCATS."
        ),
        "candidateId": "050dbaf7-d1ac-4a0a-a2ae-83bac50dd420",
    },
    "TAUTOU": {
        "status": "accepted-retained",
        "definition": "Audrey dans Amélie",
        "reason": "Référence cinéma française distinctive et intergénérationnelle.",
        "candidateId": "2427f525-9430-4aac-80e9-431bdba9e29b",
    },
    "DRE": {
        "status": "accepted-retained",
        "definition": "Mentor d’Eminem",
        "reason": "Nom de scène actuel, lien musical distinctif.",
        "candidateId": "8c1758ee-5ce6-4312-b370-7ed29002bad2",
    },
    "ETAGEE": {
        "status": "acceptable-form-grid-excluded",
        "definition": "Disposée par niveaux",
        "reason": (
            "Adjectif autonome et naturel, mais la grille est écartée pour "
            "CASTEL et TIRANT."
        ),
        "candidateId": "f8a0d5f1-5b6f-46aa-bc12-4d12bc445c38",
    },
    "REFERE": {
        "status": "accepted-retained",
        "definition": "Procédure judiciaire urgente",
        "reason": "Terme juridique courant dans l’actualité, sens unique ici.",
        "candidateId": "e0076126-02af-4919-acf9-4e5130cbf9f2",
    },
}


HUMAN_DECISION_ITEMS: list[dict[str, Any]] = [
    {
        "answer": "ALIAGAS",
        "candidateIds": ["4f43eb77-4be7-4aab-b85c-8340bcf45673"],
        "recommendation": "retain",
        "reason": (
            "Nom propre absent du lexique principal mais très identifiable par "
            "« Nikos » ; validation culturelle propriétaire souhaitée."
        ),
    },
    {
        "answer": "SUE",
        "candidateIds": [
            "8c1758ee-5ce6-4312-b370-7ed29002bad2",
            "0dbb98eb-2306-40ea-b511-e0ba3120d8bc",
        ],
        "recommendation": "retain-with-warning",
        "reason": (
            "Petite conjugaison claire (« Transpire »), encore présente deux "
            "fois ; à supprimer si le propriétaire veut zéro forme verbale faible."
        ),
    },
    {
        "answer": "LURONNE",
        "candidateIds": ["8e4177e9-5b86-4c40-ab26-b579d1e4202e"],
        "recommendation": "retain-with-warning",
        "reason": (
            "Forme française valide mais moins familière aux 16–45 ans ; "
            "la définition « Femme très enjouée » reste naturelle."
        ),
    },
    {
        "answer": "PARTNER",
        "candidateIds": [
            "49100aab-d329-419c-aea4-df030e5929d6",
            "d95997f7-8f13-4379-b01a-a42ac0163c35",
        ],
        "recommendation": "retain-with-warning",
        "reason": (
            "Anglicisme courant mais répété deux fois ; la définition explicite "
            "le statut anglais."
        ),
    },
]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(encoded)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Objet JSON attendu : {path}")
    return value


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def local_asset_data_uri(asset: str) -> str:
    if not asset.startswith("/assets/clues/"):
        raise ValueError(f"Indice-image hors bibliothèque MotMan : {asset}")
    path = (ROOT / "public" / asset.lstrip("/")).resolve()
    clue_root = (ROOT / "public/assets/clues").resolve()
    if not path.is_relative_to(clue_root) or not path.is_file():
        raise ValueError(f"Indice-image introuvable : {asset}")
    mime = {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower())
    if mime is None:
        raise ValueError(f"Format image non pris en charge : {asset}")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def verify_source() -> tuple[dict[str, Any], dict[str, Any]]:
    file_digest = sha256_file(SOURCE_EXPORT)
    if file_digest != EXPECTED_FILE_SHA256:
        raise ValueError(
            f"SHA-256 physique inattendu : {file_digest}; "
            f"attendu {EXPECTED_FILE_SHA256}"
        )
    audit_digest = sha256_file(SOURCE_AUDIT)
    if audit_digest != EXPECTED_AUDIT_SHA256:
        raise ValueError(
            f"SHA-256 audit inattendu : {audit_digest}; "
            f"attendu {EXPECTED_AUDIT_SHA256}"
        )
    document = read_json(SOURCE_EXPORT)
    if (
        document.get("schema") != EXPECTED_SCHEMA
        or document.get("version") != EXPECTED_VERSION
    ):
        raise ValueError("Contrat de handoff non pris en charge")
    manifest = document.get("manifest")
    if not isinstance(manifest, dict):
        raise ValueError("Manifest absent")
    unsigned = copy.deepcopy(document)
    unsigned["manifest"].pop("payloadSha256", None)
    payload_digest = canonical_digest(unsigned)
    if manifest.get("payloadSha256") != EXPECTED_PAYLOAD_SHA256:
        raise ValueError("Digest payload du manifest inattendu")
    if payload_digest != EXPECTED_PAYLOAD_SHA256:
        raise ValueError(
            f"Digest payload invalide : {payload_digest}; "
            f"attendu {EXPECTED_PAYLOAD_SHA256}"
        )
    grids = document.get("grids")
    if not isinstance(grids, list) or len(grids) != 33:
        raise ValueError("Le handoff doit contenir exactement 33 grilles")

    editorial_paths: list[str] = []

    def walk(value: object, prefix: str = "$") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child = f"{prefix}.{key}"
                if str(key).casefold() in {
                    "clue",
                    "definition",
                    "image",
                    "images",
                }:
                    editorial_paths.append(child)
                walk(item, child)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{prefix}[{index}]")

    walk(document)
    if editorial_paths:
        raise ValueError(
            "Le handoff words-only contient des champs éditoriaux : "
            f"{editorial_paths[:5]}"
        )
    lexical_audit = read_json(SOURCE_AUDIT)
    contract = lexical_audit.get("contract_validation", {})
    if not (
        contract.get("contract_valid")
        and contract.get("words_only")
        and contract.get("payload_sha256_valid")
        and contract.get("all_grids_certified_exportable")
    ):
        raise ValueError("L’audit Réservoir ne confirme plus le contrat certifié")
    if not all(contract.get("current_owner_source_digest_matches", {}).values()):
        raise ValueError("Un digest de source propriétaire n’est plus courant")
    return document, lexical_audit


def verify_catalog_baseline() -> dict[str, Any]:
    catalog_sha = sha256_file(CATALOG_PATH)
    runtime_sha = sha256_file(RUNTIME_PATH)
    if catalog_sha != EXPECTED_CATALOG_SHA256:
        raise ValueError(
            f"grid.catalog.json a changé : {catalog_sha}; "
            f"attendu {EXPECTED_CATALOG_SHA256}"
        )
    if runtime_sha != EXPECTED_RUNTIME_SHA256:
        raise ValueError(
            f"runtime.grid.catalog.json a changé : {runtime_sha}; "
            f"attendu {EXPECTED_RUNTIME_SHA256}"
        )
    catalog = read_json(CATALOG_PATH)
    runtime = read_json(RUNTIME_PATH)
    if (
        catalog.get("version") != EXPECTED_CATALOG_VERSION
        or runtime.get("version") != EXPECTED_CATALOG_VERSION
        or len(catalog.get("grids", [])) != EXPECTED_ACTIVE_GRID_COUNT
        or len(runtime.get("grids", [])) != EXPECTED_ACTIVE_GRID_COUNT
    ):
        raise ValueError("Le baseline actif n’est plus le catalogue v20 à 29 grilles")
    return {
        "version": EXPECTED_CATALOG_VERSION,
        "gridCount": EXPECTED_ACTIVE_GRID_COUNT,
        "catalogPath": str(CATALOG_PATH),
        "catalogSha256": catalog_sha,
        "runtimePath": str(RUNTIME_PATH),
        "runtimeSha256": runtime_sha,
    }


def source_answer_set(source_grid: dict[str, Any]) -> set[str]:
    return {
        str(item.get("normalized", "")).upper()
        for item in source_grid.get("answers", [])
        if str(item.get("normalized", "")).strip()
    }


def answer_jaccard(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_answers = source_answer_set(left)
    right_answers = source_answer_set(right)
    common = sorted(left_answers & right_answers)
    union = left_answers | right_answers
    return {
        "sharedAnswers": common,
        "sharedAnswerCount": len(common),
        "jaccardPercent": round(100 * len(common) / max(1, len(union)), 1),
        "sameShape": left.get("shapeFingerprint") == right.get("shapeFingerprint"),
    }


def blacklist_audit(grids: list[dict[str, Any]]) -> dict[str, Any]:
    blacklist = read_json(BLACKLIST_PATH)
    hard = (
        set(blacklist.get("rejectedAnswers", []))
        | set(blacklist.get("rejectedEasyAnswers", []))
        | set(blacklist.get("rejectedNormalAnswers", []))
    )
    hits: dict[str, list[str]] = {}
    cooccurrence_hits: dict[str, list[list[str]]] = {}
    for grid in grids:
        answers = source_answer_set(grid)
        intersection = sorted(answers & hard)
        if intersection:
            hits[str(grid["candidateId"])] = intersection
        pairs = []
        for item in blacklist.get("rejectedCooccurrences", []):
            pair = set(item.get("answers", []))
            if pair and pair <= answers:
                pairs.append(sorted(pair))
        if pairs:
            cooccurrence_hits[str(grid["candidateId"])] = pairs
    if hits or cooccurrence_hits:
        raise ValueError(
            f"Blacklist réelle touchée : answers={hits}, cooccurrences={cooccurrence_hits}"
        )
    return {
        "path": str(BLACKLIST_PATH),
        "sha256": sha256_file(BLACKLIST_PATH),
        "version": blacklist.get("version"),
        "hardRejectedAnswerCount": len(hard),
        "answerHits": hits,
        "cooccurrenceHits": cooccurrence_hits,
        "valid": True,
        "rotationCooldownHandling": (
            "warning-and-penalty-owner-override; never treated as a hard gate"
        ),
    }


def duplicate_candidate_ids(value: object) -> set[str]:
    if isinstance(value, dict):
        return {str(candidate_id) for candidate_id in value}
    if not isinstance(value, list):
        return set()
    return {
        str(item.get("candidate_id") or item.get("candidateId"))
        for item in value
        if isinstance(item, dict)
        and (item.get("candidate_id") or item.get("candidateId"))
    }


def folded_clue(value: object) -> str:
    if not isinstance(value, str):
        return ""
    import unicodedata

    decomposed = unicodedata.normalize("NFD", value.casefold())
    plain = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    return " ".join(re.findall(r"[a-z0-9]+", plain))


def active_definition_crosscheck(grids: list[dict[str, Any]]) -> dict[str, Any]:
    catalog = read_json(CATALOG_PATH)
    active_by_answer: dict[str, set[str]] = {}
    active_by_key: dict[tuple[str, int], set[str]] = {}
    for grid in catalog.get("grids", []):
        for word in grid.get("words", []):
            answer = str(word.get("answer", "")).upper()
            clue = str(word.get("clue") or word.get("sourceClue") or "").strip()
            if not answer or not clue:
                continue
            active_by_answer.setdefault(answer, set()).add(clue)
            key = (folded_clue(clue), len(answer))
            active_by_key.setdefault(key, set()).add(answer)

    reused_same_answer: dict[str, dict[str, list[str]]] = {}
    ambiguous_same_length: list[dict[str, Any]] = []
    seen_conflicts: set[tuple[str, str, str]] = set()
    for grid in grids:
        for word in grid["words"]:
            answer = word["answer"]
            clue = word["editorialDefinition"]
            active_clues = active_by_answer.get(answer)
            if active_clues:
                reused_same_answer[answer] = {
                    "activeDefinitions": sorted(active_clues),
                    "stagedDefinition": clue,
                }
            key = (folded_clue(clue), len(answer))
            for active_answer in active_by_key.get(key, set()) - {answer}:
                signature = (answer, active_answer, key[0])
                if signature in seen_conflicts:
                    continue
                seen_conflicts.add(signature)
                ambiguous_same_length.append(
                    {
                        "stagedAnswer": answer,
                        "activeAnswer": active_answer,
                        "definition": clue,
                        "answerLength": len(answer),
                    }
                )
    if ambiguous_same_length:
        raise ValueError(
            "Définition ambiguë avec le catalogue actif : "
            f"{ambiguous_same_length}"
        )
    return {
        "activeCatalogVersion": catalog.get("version"),
        "activeGridCount": len(catalog.get("grids", [])),
        "sameAnswerAlreadyDefined": dict(sorted(reused_same_answer.items())),
        "sameLengthDifferentAnswerConflicts": ambiguous_same_length,
        "valid": True,
    }


def image_for(answer: str) -> dict[str, Any] | None:
    spec = IMAGE_SPECS.get(answer)
    if spec is None:
        return None
    source_asset = spec["asset"]
    custom = spec.get("source") == "MotMan original"
    return {
        "asset": local_asset_data_uri(source_asset),
        "alt": spec["alt"],
        "concept": spec["concept"],
        "source": spec.get("source", "Twemoji 15.1"),
        "license": spec.get("license", "CC BY 4.0"),
        "sourceUrl": (
            EDITORIAL_SOURCE_URL
            if custom
            else "https://github.com/jdecked/twemoji"
        ),
        "sourceAsset": source_asset,
        "alreadyAvailableInMotMan": True,
        "requiresNewAabAsset": False,
    }


def build_word(source: dict[str, Any]) -> dict[str, Any]:
    answer = str(source["normalized"]).upper()
    fallback = CLUES[answer]
    image = image_for(answer)
    proper = PROPER_NAME_REVIEWS.get(answer)
    source_url = proper["sourceUrl"] if proper else EDITORIAL_SOURCE_URL
    language_status = (
        "known-proper-name"
        if proper
        else "common-anglicism"
        if answer in COMMON_ANGLICISMS
        else "french"
    )
    cultural_status = (
        "current-pop"
        if proper
        else "current-common"
        if answer in CURRENT_COMMON
        else "everyday"
    )
    word: dict[str, Any] = {
        "wordId": source["proposedWordId"],
        "answer": answer,
        "clue": "" if image else fallback,
        "sourceClue": image["alt"] if image else fallback,
        "editorialDefinition": fallback,
        "definitionStatus": "image-review" if image else "manually-reviewed",
        "editorialStatus": "owner-review-required",
        "sourceType": "image-concept" if image else "editorial-original",
        "sourceId": EDITORIAL_SOURCE_ID,
        "sourceUrl": source_url,
        "license": image["license"] if image else "MotMan original",
        "conceptGroup": answer,
        "semanticConflicts": [],
        "direction": source["direction"],
        "arrow": source["arrow"],
        "clueCell": source["clueCell"],
        "cells": source["cells"],
        "clueStyle": "image" if image else "direct",
        "familiarityScore": float(source.get("familiarity") or 0),
        "familiarityBand": (
            "thoughtful"
            if float(source.get("familiarity") or 0) < 20
            else "common"
        ),
        "partOfSpeech": (
            "proper-name"
            if proper
            else source.get("partOfSpeech")
            if source.get("partOfSpeech") not in {None, "", "unknown"}
            else "reviewed-lexical-item"
        ),
        "languageStatus": language_status,
        "culturalStatus": cultural_status,
        "editorialReview": {
            "status": "human-reviewed",
            "semanticFit": True,
            "grammaticalFit": True,
            "unambiguous": True,
            "answerNotRevealed": True,
            "languageAcceptable": True,
            "allAudience": True,
            "mobileReadable": True,
            "imageRecognizable": bool(image),
            "reviewDate": REVIEW_DATE,
            "audience": "16-45-priority",
        },
        "factoryMetadata": {
            "formType": source.get("formType"),
            "properName": source.get("properName"),
            "qualityTier": source.get("qualityTier"),
            "solverPenalty": source.get("solverPenalty"),
            "familiarity": source.get("familiarity"),
            "register": source.get("register"),
            "domain": source.get("domain"),
            "pendingPoolId": source.get("pendingPoolId"),
        },
    }
    if image:
        word["image"] = image
        word["imageStatus"] = "reviewed-recognizable-licensed"
    if proper:
        word["properNameReview"] = {
            "status": "human-reviewed-distinctive",
            "entityType": proper["entityType"],
            "clueUniquenessChecked": True,
            "distinctiveTokens": proper["distinctiveTokens"],
            "acceptedAs": proper["acceptedAs"],
            "sourceUrl": proper["sourceUrl"],
        }
    strict_errors = pilot_editorial_errors(word, root=ROOT)
    if strict_errors:
        raise ValueError(f"{answer}: contrat éditorial pilote invalide : {strict_errors}")
    return word


def build_grid(source_grid: dict[str, Any]) -> dict[str, Any]:
    words = [build_word(source) for source in source_grid["answers"]]
    grid = {
        "id": source_grid["proposedGridId"],
        "columns": source_grid["columns"],
        "rows": source_grid["rows"],
        "sourceCandidateId": source_grid["candidateId"],
        "sourceCampaignId": source_grid["campaignId"],
        "sourceShapeId": source_grid["shapeId"],
        "sourceShapeFingerprint": source_grid["shapeFingerprint"],
        "sourceExactFingerprint": source_grid["exactFingerprint"],
        "audience": "16-45-priority",
        "clueCells": source_grid["clueCells"],
        "words": words,
        "imageCount": sum(bool(word.get("image")) for word in words),
        "publicationStatus": "owner-review-required",
        "ownerReview": {
            "status": "pending-explicit-owner-validation",
            "reviewedAt": None,
            "decision": None,
        },
        "certification": {
            "status": "source-certified",
            "certifiedAt": source_grid["certifiedAt"],
            "finalAudit": source_grid["finalAudit"],
            "sourceDigests": source_grid["digests"],
        },
        "editorialReview": {
            "status": "prepared-for-owner-review",
            "reviewDate": REVIEW_DATE,
            "definitionCount": len(words),
            "imageCount": sum(bool(word.get("image")) for word in words),
            "properNames": sorted(
                word["answer"] for word in words if word.get("properNameReview")
            ),
        },
    }
    topology = audit_grid_topology(
        grid,
        require_word_ids=True,
        enforce_layout=False,
        topology_profile="pilot",
    )
    if not topology["valid"]:
        raise ValueError(
            f"{grid['id']}: topologie invalide : {topology['errors']}"
        )
    return grid


def repeated_counts(grids: list[dict[str, Any]], *, source: bool) -> Counter[str]:
    if source:
        return Counter(
            answer
            for grid in grids
            for answer in source_answer_set(grid)
        )
    return Counter(
        word["answer"]
        for grid in grids
        for word in grid["words"]
    )


def selection_report(
    document: dict[str, Any],
    lexical_audit: dict[str, Any],
    retained_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    by_candidate = {
        str(grid["candidateId"]): grid for grid in document["grids"]
    }
    original_counts = repeated_counts(document["grids"], source=True)
    selected_counts = repeated_counts(retained_sources, source=True)
    focus = ("IL", "ETE", "EST", "SEL", "ON", "ICI")
    focus_reduction = {
        answer: {
            "source33": original_counts[answer],
            "retained15": selected_counts[answer],
            "removed": original_counts[answer] - selected_counts[answer],
            "reductionPercent": round(
                100 * (original_counts[answer] - selected_counts[answer])
                / max(1, original_counts[answer]),
                1,
            ),
        }
        for answer in focus
    }
    pair_decisions = [
        {
            "pair": [
                "ff14f81e-946d-48f4-a545-d80cc7dbd47e",
                "081c89e3-c392-4258-a0e0-cffec95b2f43",
            ],
            "similarityPercent": 88.9,
            "kept": None,
            "reason": "La seconde est déjà active ; la nouvelle variante est écartée.",
        },
        {
            "pair": [
                "0046c9fc-ab63-486e-9cd2-555c76234331",
                "8e4177e9-5b86-4c40-ab26-b579d1e4202e",
            ],
            "similarityPercent": 88.2,
            "kept": "8e4177e9-5b86-4c40-ab26-b579d1e4202e",
            "reason": "Meilleur score, répétition moindre et RELIRE plutôt que REDIRE.",
        },
        {
            "pair": [
                "0dbb98eb-2306-40ea-b511-e0ba3120d8bc",
                "09fa406f-3b78-4c8b-8c27-110dc41cafff",
            ],
            "similarityPercent": 88.2,
            "kept": "0dbb98eb-2306-40ea-b511-e0ba3120d8bc",
            "reason": "Meilleur score et moindre exposition au catalogue actif.",
        },
        {
            "pair": [
                "fa4c2538-1fdb-4149-8bab-d68d397d2686",
                "e660b8f7-902f-4ed7-94ff-40dcab75a643",
            ],
            "similarityPercent": 88.2,
            "kept": "fa4c2538-1fdb-4149-8bab-d68d397d2686",
            "reason": "NET est plus familier que NEM, avec de meilleurs indicateurs.",
        },
    ]
    extra_comparison = answer_jaccard(
        by_candidate["004254ee-d74d-4b91-bdb3-4c108979b3f9"],
        by_candidate["1ea6b510-141f-48d0-97af-8ede77ab946b"],
    )
    extra_comparison.update(
        {
            "kept": "004254ee-d74d-4b91-bdb3-4c108979b3f9",
            "excluded": "1ea6b510-141f-48d0-97af-8ede77ab946b",
            "reason": "La variante écartée ajoute IL, SEL et ICI.",
        }
    )
    catalog_summary = lexical_audit.get("catalog_summary", {})
    return {
        "schema": "motman-certified-editorial-selection-report",
        "version": 1,
        "reviewDate": REVIEW_DATE,
        "sourceGridCount": len(document["grids"]),
        "retainedGridCount": len(retained_sources),
        "excludedGridCount": len(EXCLUSIONS),
        "retainedCandidateIds": list(RETAINED_CANDIDATES),
        "retainedProposedGridIds": [
            grid["proposedGridId"] for grid in retained_sources
        ],
        "excluded": [
            {
                "candidateId": candidate_id,
                "proposedGridId": by_candidate[candidate_id]["proposedGridId"],
                **decision,
            }
            for candidate_id, decision in EXCLUSIONS.items()
        ],
        "pairDecisions": pair_decisions,
        "additionalVariantDecision": extra_comparison,
        "repetition": {
            "sourceSlots": sum(original_counts.values()),
            "retainedSlots": sum(selected_counts.values()),
            "sourceDistinctAnswers": len(original_counts),
            "retainedDistinctAnswers": len(selected_counts),
            "focusReduction": focus_reduction,
            "retainedRepeatedAnswers": {
                answer: count
                for answer, count in sorted(selected_counts.items())
                if count > 1
            },
        },
        "flaggedFormReviews": FLAGGED_FORM_REVIEWS,
        "humanDecisionItems": HUMAN_DECISION_ITEMS,
        "catalogCrossCheck": {
            "activeSourceGridCount": catalog_summary.get(
                "active_source_grid_count"
            ),
            "activeSourceSha256": catalog_summary.get("active_source_sha256"),
            "fullCatalogSha256": catalog_summary.get("full_catalog_sha256"),
            "retiredGridCount": catalog_summary.get(
                "owner_db_retired_grid_count"
            ),
            "ownerDatabaseSnapshotStale": catalog_summary.get(
                "owner_db_catalog_snapshot_stale"
            ),
            "exactActiveDuplicates": catalog_summary.get(
                "exact_active_duplicates"
            ),
            "exactRetiredDuplicates": catalog_summary.get(
                "exact_retired_duplicates"
            ),
            "exactOwnerRefusedDuplicates": catalog_summary.get(
                "exact_owner_refused_duplicates"
            ),
        },
        "policyDecision": {
            "rotationCooldown": "warning-and-penalty",
            "hardBlacklist": "blocking",
            "avoidNextLot": "blocking-for-this-lot",
            "ownerInstructionApplied": True,
        },
    }


def review_header(selection: dict[str, Any], grids: list[dict[str, Any]]) -> str:
    focus_rows = "".join(
        "<tr>"
        f"<td>{escape(answer)}</td>"
        f"<td>{item['source33']}</td>"
        f"<td>{item['retained15']}</td>"
        f"<td>−{item['reductionPercent']:.1f}%</td>"
        "</tr>"
        for answer, item in selection["repetition"]["focusReduction"].items()
    )
    flagged_rows = "".join(
        "<tr>"
        f"<td>{escape(answer)}</td>"
        f"<td>{escape(item['status'])}</td>"
        f"<td>{escape(item['definition'])}</td>"
        f"<td>{escape(item['reason'])}</td>"
        "</tr>"
        for answer, item in FLAGGED_FORM_REVIEWS.items()
    )
    decision_rows = "".join(
        "<tr>"
        f"<td>{escape(item['answer'])}</td>"
        f"<td>{escape(item['recommendation'])}</td>"
        f"<td>{escape(item['reason'])}</td>"
        "</tr>"
        for item in HUMAN_DECISION_ITEMS
    )
    excluded_rows = "".join(
        "<tr>"
        f"<td><code>{escape(item['candidateId'])}</code></td>"
        f"<td>{escape(item['category'])}</td>"
        f"<td>{escape(item['reason'])}</td>"
        "</tr>"
        for item in selection["excluded"]
    )
    return f"""
    <section class="editorial-summary">
      <p class="owner-warning"><strong>REVUE PROPRIÉTAIRE — NON PUBLIÉ.</strong>
      Les solutions figurent uniquement dans cette page. La page de playtest
      séparée n’en contient aucune.</p>
      <div class="summary-cards">
        <div><b>{len(grids)}</b><span>grilles retenues</span></div>
        <div><b>{len(EXCLUSIONS)}</b><span>grilles écartées</span></div>
        <div><b>{sum(len(grid['words']) for grid in grids)}</b><span>réponses</span></div>
        <div><b>{len(CLUES)}</b><span>sens mutualisés</span></div>
      </div>
      <h2>Réduction des répétitions</h2>
      <table><thead><tr><th>Réponse</th><th>Export 33</th><th>Sous-lot 15</th>
      <th>Réduction</th></tr></thead><tbody>{focus_rows}</tbody></table>
      <h2>Formes demandées</h2>
      <table><thead><tr><th>Forme</th><th>Décision</th><th>Définition</th>
      <th>Motif</th></tr></thead><tbody>{flagged_rows}</tbody></table>
      <h2>Points d’attention propriétaire</h2>
      <table><thead><tr><th>Réponse</th><th>Recommandation</th><th>Pourquoi</th>
      </tr></thead><tbody>{decision_rows}</tbody></table>
      <details><summary>Afficher les {len(EXCLUSIONS)} exclusions motivées</summary>
      <table><thead><tr><th>Candidate</th><th>Catégorie</th><th>Motif</th>
      </tr></thead><tbody>{excluded_rows}</tbody></table></details>
      <div class="review-actions">
        <button id="export-decisions">Exporter les décisions locales</button>
      </div>
    </section>
    """


def render_owner_review(
    reports: list[dict[str, Any]],
    selection: dict[str, Any],
    grids: list[dict[str, Any]],
) -> str:
    page = render_topology_html(
        reports,
        title="MotMan — revue du sous-lot certifié 111bca5d3810",
    )
    header = review_header(selection, grids)
    for grid in grids:
        grid_id = escape(grid["id"])
        marker = (
            f"<div class='owner-decision' data-owner-grid='{grid_id}'>"
            "<button data-decision='accept'>Valider</button>"
            "<button data-decision='reject'>Refuser</button>"
            "<span class='decision-state'>À décider</span></div>"
        )
        needle = f"<section class='grid-review' data-grid-id='{grid_id}'>"
        page = page.replace(needle, needle + marker, 1)
    css = """
    <style>
    .editorial-summary{max-width:1100px;margin:20px auto;padding:22px;background:#fff;
      border:2px solid #183153;border-radius:18px;box-shadow:0 8px 28px #18315322}
    .owner-warning{padding:14px;background:#fff2cc;border:1px solid #c9971a;border-radius:12px}
    .summary-cards{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:10px}
    .summary-cards div{padding:14px;background:#eef4fb;border-radius:12px;text-align:center}
    .summary-cards b{font-size:28px;display:block}.summary-cards span{font-size:13px}
    .editorial-summary table{width:100%;border-collapse:collapse;margin:10px 0 18px}
    .editorial-summary th,.editorial-summary td{padding:8px;border:1px solid #ccd5df;text-align:left}
    .editorial-summary th{background:#e9f0f8}.editorial-summary code{font-size:11px}
    .owner-decision{display:flex;gap:8px;align-items:center;padding:10px;background:#eef4fb}
    .owner-decision button,.review-actions button{padding:8px 13px;border:0;border-radius:9px;
      background:#183153;color:#fff;font-weight:700;cursor:pointer}
    .owner-decision.reject{background:#ffe7e7}.owner-decision.accept{background:#e1f6e8}
    @media(max-width:700px){.summary-cards{grid-template-columns:repeat(2,1fr)}
      .editorial-summary{padding:12px}.editorial-summary table{font-size:12px}}
    </style>
    """
    script = """
    <script>
    (() => {
      const key = 'motman-certified-editorial-111bca5d3810-decisions-v1';
      const load = () => { try { return JSON.parse(localStorage.getItem(key) || '{}'); }
        catch { return {}; } };
      const decisions = load();
      const paint = box => {
        const id = box.dataset.ownerGrid;
        const value = decisions[id] || '';
        box.classList.toggle('accept', value === 'accept');
        box.classList.toggle('reject', value === 'reject');
        box.querySelector('.decision-state').textContent =
          value === 'accept' ? 'Validée localement' :
          value === 'reject' ? 'Refusée localement' : 'À décider';
      };
      document.querySelectorAll('[data-owner-grid]').forEach(box => {
        paint(box);
        box.querySelectorAll('[data-decision]').forEach(button =>
          button.addEventListener('click', () => {
            decisions[box.dataset.ownerGrid] = button.dataset.decision;
            localStorage.setItem(key, JSON.stringify(decisions));
            paint(box);
          }));
      });
      document.querySelector('#export-decisions').addEventListener('click', () => {
        const payload = {schema:'motman-owner-editorial-decisions',version:1,
          sourceFileSha256:'111bca5d3810ca201e5c36bfb1a4757a3c700df458bda010a1a8ec9a406eeace',
          decisions};
        const blob = new Blob([JSON.stringify(payload, null, 2)], {type:'application/json'});
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'motman-certified-editorial-owner-decisions.json';
        link.click();
        URL.revokeObjectURL(link.href);
      });
    })();
    </script>
    """
    return (
        page.replace("</head>", css + "</head>")
        .replace("</h1>", "</h1>" + header, 1)
        .replace("</body>", script + "</body>")
    )


def artifact_manifest(paths: list[Path]) -> dict[str, Any]:
    return {
        "schema": "motman-editorial-staging-artifact-manifest",
        "version": 1,
        "generatedOn": date.today().isoformat(),
        "source": {
            "path": str(SOURCE_EXPORT),
            "sha256": EXPECTED_FILE_SHA256,
            "payloadSha256": EXPECTED_PAYLOAD_SHA256,
        },
        "lexicalAudit": {
            "path": str(SOURCE_AUDIT),
            "sha256": EXPECTED_AUDIT_SHA256,
        },
        "artifacts": [
            {
                "path": str(path),
                "relativePath": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in paths
        ],
        "catalogMutation": False,
        "supabaseMutation": False,
        "publicationAuthorized": False,
    }


def main() -> None:
    document, lexical_audit = verify_source()
    baseline_before = verify_catalog_baseline()
    by_candidate = {
        str(grid["candidateId"]): grid for grid in document["grids"]
    }
    if set(by_candidate) != set(RETAINED_CANDIDATES) | set(EXCLUSIONS):
        missing = sorted(set(by_candidate) - set(RETAINED_CANDIDATES) - set(EXCLUSIONS))
        extra = sorted((set(RETAINED_CANDIDATES) | set(EXCLUSIONS)) - set(by_candidate))
        raise ValueError(f"Sélection non exhaustive : missing={missing}, extra={extra}")
    retained_sources = [by_candidate[candidate] for candidate in RETAINED_CANDIDATES]
    expected_answers = set().union(
        *(source_answer_set(grid) for grid in retained_sources)
    )
    if expected_answers != set(CLUES):
        missing = sorted(expected_answers - set(CLUES))
        extra = sorted(set(CLUES) - expected_answers)
        raise ValueError(f"Couverture éditoriale incorrecte : missing={missing}, extra={extra}")
    blacklist = blacklist_audit(retained_sources)
    selection = selection_report(document, lexical_audit, retained_sources)
    grids = [build_grid(source) for source in retained_sources]
    topology_reports = [
        audit_grid_topology(
            grid,
            require_word_ids=True,
            enforce_layout=False,
            topology_profile="pilot",
        )
        for grid in grids
    ]
    topology_errors = [
        {
            "gridId": report["gridId"],
            "errors": report["errors"],
        }
        for report in topology_reports
        if not report["valid"]
    ]
    if topology_errors:
        raise ValueError(f"Topologie staging invalide : {topology_errors}")

    catalog_summary = lexical_audit.get("catalog_summary", {})
    exact_active = duplicate_candidate_ids(
        catalog_summary.get("exact_active_duplicates")
    )
    exact_retired = duplicate_candidate_ids(
        catalog_summary.get("exact_retired_duplicates")
    )
    exact_owner_refused = duplicate_candidate_ids(
        catalog_summary.get("exact_owner_refused_duplicates")
    )
    duplicate_crosscheck = {
        "active": sorted(set(RETAINED_CANDIDATES) & exact_active),
        "retired": sorted(set(RETAINED_CANDIDATES) & exact_retired),
        "ownerRefused": sorted(
            set(RETAINED_CANDIDATES) & exact_owner_refused
        ),
    }
    if any(duplicate_crosscheck.values()):
        raise ValueError(
            "Doublons de catalogue retenus par erreur : "
            f"{duplicate_crosscheck}"
        )
    definition_crosscheck = active_definition_crosscheck(grids)

    staging = {
        "schema": "motman-grid-certified-editorial-staging",
        "version": 1,
        "reviewDate": REVIEW_DATE,
        "publicationStatus": "owner-review-required",
        "publicationAuthorized": False,
        "catalogMutation": False,
        "supabaseMutation": False,
        "source": {
            "path": str(SOURCE_EXPORT),
            "schema": document["schema"],
            "version": document["version"],
            "fileSha256": EXPECTED_FILE_SHA256,
            "payloadSha256": EXPECTED_PAYLOAD_SHA256,
            "lexicalAuditPath": str(SOURCE_AUDIT),
            "lexicalAuditSha256": EXPECTED_AUDIT_SHA256,
        },
        "selection": {
            "sourceGridCount": 33,
            "retainedGridCount": len(grids),
            "excludedGridCount": len(EXCLUSIONS),
            "selectionReport": str(SELECTION_PATH),
        },
        "grids": grids,
    }
    audit = {
        "schema": "motman-certified-editorial-staging-audit",
        "version": 1,
        "reviewDate": REVIEW_DATE,
        "valid": True,
        "contract": {
            "physicalSha256Valid": True,
            "payloadSha256Valid": True,
            "lexicalAuditSha256Valid": True,
            "wordsOnly": True,
            "gridCount": len(document["grids"]),
            "allSourceGridsCertifiedExportable": True,
        },
        "baseline": baseline_before,
        "blacklist": blacklist,
        "selection": {
            "retained": len(grids),
            "excluded": len(EXCLUSIONS),
            "distinctAnswers": len(CLUES),
            "answerSlots": sum(len(grid["words"]) for grid in grids),
            "images": sum(grid["imageCount"] for grid in grids),
            "exactDuplicatesSelected": duplicate_crosscheck,
            "flaggedFormReviews": FLAGGED_FORM_REVIEWS,
            "humanDecisionItems": HUMAN_DECISION_ITEMS,
        },
        "editorial": {
            "allAnswersCovered": True,
            "allTextDefinitionsAtMostThreeWords": True,
            "identicalSensesMutualized": True,
            "imagePolicy": "only-useful-existing-assets",
            "imageAssetsRequireNewAab": False,
            "ownerValidationPending": True,
            "activeDefinitionCrosscheck": definition_crosscheck,
        },
        "topology": {
            "profile": "pilot",
            "validGridCount": sum(report["valid"] for report in topology_reports),
            "invalidGridCount": sum(not report["valid"] for report in topology_reports),
            "reports": topology_reports,
        },
        "publication": {
            "gridCatalogModified": False,
            "runtimeCatalogModified": False,
            "supabaseModified": False,
            "authorized": False,
        },
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    atomic_json(SELECTION_PATH, selection)
    atomic_json(STAGING_PATH, staging)
    atomic_json(AUDIT_PATH, audit)
    atomic_text(REVIEW_PATH, render_owner_review(topology_reports, selection, grids))
    atomic_text(PLAYTEST_PATH, render_playtest_html(copy.deepcopy(topology_reports)))

    baseline_after = verify_catalog_baseline()
    if baseline_after != baseline_before:
        raise ValueError("Un catalogue a changé pendant la préparation")
    artifacts = artifact_manifest(
        [SELECTION_PATH, STAGING_PATH, AUDIT_PATH, REVIEW_PATH, PLAYTEST_PATH]
    )
    atomic_json(ARTIFACT_MANIFEST_PATH, artifacts)
    result = {
        "valid": True,
        "retained": len(grids),
        "excluded": len(EXCLUSIONS),
        "answerSlots": sum(len(grid["words"]) for grid in grids),
        "distinctAnswers": len(CLUES),
        "images": sum(grid["imageCount"] for grid in grids),
        "catalogModified": False,
        "runtimeModified": False,
        "supabaseModified": False,
        "artifacts": artifacts["artifacts"],
        "artifactManifest": {
            "path": str(ARTIFACT_MANIFEST_PATH),
            "sha256": sha256_file(ARTIFACT_MANIFEST_PATH),
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
