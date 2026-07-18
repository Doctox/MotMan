"""Assemble the 30-grid MotMan standard staging batch after manual review.

Six owner-approved grids act as anchors.  The other twenty-four geometries
were only assisted by a crossing solver; the answer selection and stable clue
wording below are an explicit editorial decision.  Nothing in this file is
published to the active game catalog.
"""
from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

from editorial_quality import editorial_errors
from grid_topology import audit_grid_topology, render_topology_html


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src/data/grid-generation-handcrafted/standard.batch.staging.json"
AUDIT = ROOT / "output/quality/standard-batch-audit.json"
HTML = ROOT / "output/quality/standard-batch-review.html"

ANCHOR_FILES = (
    ROOT / "src/data/grid-generation-handcrafted/reference.pilot.json",
    ROOT / "output/quality/difficulty-calibration-candidates.json",
    ROOT / "output/quality/hard-calibration-round-02-candidate.json",
)

SELECTED_DRAFTS = (
    ("standard-crossing-drafts-smoke.json", "standard-draft-04"),
    ("standard-crossing-drafts-v5.json", "standard-draft-24"),
    ("standard-crossing-drafts-v3.json", "standard-draft-01"),
    ("standard-crossing-drafts-v3.json", "standard-draft-24"),
    ("standard-crossing-drafts-v5.json", "standard-draft-07"),
    ("standard-crossing-drafts-v5.json", "standard-draft-14"),
    ("standard-crossing-drafts-smoke.json", "standard-draft-03"),
    ("standard-crossing-drafts-v6.json", "standard-draft-03"),
    ("standard-crossing-drafts-v6.json", "standard-draft-20"),
    ("standard-crossing-drafts-v5.json", "standard-draft-17"),
    ("standard-crossing-drafts-v4.json", "standard-draft-15"),
    ("standard-crossing-drafts-v6.json", "standard-draft-22"),
    ("standard-crossing-drafts-v5.json", "standard-draft-08"),
    ("standard-crossing-drafts-v2.json", "standard-draft-13"),
    ("standard-crossing-drafts-v5.json", "standard-draft-20"),
    ("standard-crossing-drafts-v6.json", "standard-draft-08"),
    ("standard-crossing-drafts.json", "standard-draft-15"),
    ("standard-crossing-drafts-v4.json", "standard-draft-21"),
    ("standard-crossing-drafts-v6.json", "standard-draft-18"),
    ("standard-crossing-drafts-v6.json", "standard-draft-06"),
    ("standard-crossing-drafts-v6.json", "standard-draft-23"),
    ("standard-crossing-drafts-v3.json", "standard-draft-13"),
    ("standard-crossing-drafts-v3.json", "standard-draft-15"),
    ("standard-crossing-drafts-v4.json", "standard-draft-20"),
)

# Stable MotMan clue book.  Entries are deliberately short, direct and
# independent of the old newspaper clue selected by the crossing proposal.
MANUAL_CLUES = {
    "ABIME": "Gouffre profond",
    "AERATION": "Renouvellement d'air",
    "AIDER": "Donner du soutien",
    "AIL": "Bulbe parfumé",
    "AIR": "Mélodie",
    "AIRE": "Surface mesurée",
    "AMITIES": "Liens affectueux",
    "AMNISTIE": "Pardon collectif",
    "ANE": "Cousin du cheval",
    "ANTIDOTE": "Remède au poison",
    "APPEL": "Cri adressé",
    "ASSEZ": "Suffisamment",
    "AUBE": "Début du jour",
    "AVAL": "Côté descendant",
    "BAC": "Examen lycéen",
    "BARS": "Poissons marins",
    "BAS": "En dessous",
    "BAVE": "Salive",
    "BEC": "Bouche d'oiseau",
    "BENNE": "Caisse basculante",
    "BERGERES": "Gardiennes de troupeaux",
    "BILAN": "Résultat global",
    "BISTOURI": "Scalpel chirurgical",
    "BITUME": "Revêtement routier",
    "BOISSONS": "Liquides à boire",
    "BOL": "Petit récipient",
    "BOUC": "Chèvre mâle",
    "BRAS": "Membre supérieur",
    "BREF": "Très court",
    "BUTIN": "Biens volés",
    "CAFETIER": "Patron de café",
    "CALE": "Coin de blocage",
    "CASTE": "Groupe social fermé",
    "CEDRE": "Conifère odorant",
    "CENT": "Dix dizaines",
    "CERISIER": "Arbre à cerises",
    "CIBLE": "Objet à viser",
    "CIEL": "Voûte bleue",
    "CIRE": "Matière des bougies",
    "CLES": "Objets qui ouvrent",
    "CLOU": "Pointe métallique",
    "CLUB": "Association sportive",
    "COBRA": "Serpent à capuchon",
    "COCO": "Noix tropicale",
    "COGNE": "Frappe fort",
    "COIFFURE": "Arrangement capillaire",
    "COMA": "Inconscience profonde",
    "CORDE": "Fibre longue tressée",
    "COURRIER": "Lettres reçues",
    "COU": "Sous la tête",
    "COUSCOUS": "Semoule nord-africaine",
    "CRAVATES": "Ornements du cou",
    "CREPE": "Fine galette",
    "CRETE": "Sommet allongé",
    "CRIMES": "Délits graves",
    "CURE": "Prêtre de paroisse",
    "CUVE": "Grand récipient",
    "DEMEURER": "Rester sur place",
    "DERAPAGE": "Glissement incontrôlé",
    "DESERT": "Étendue aride",
    "DOSE": "Quantité prescrite",
    "DOT": "Bien matrimonial",
    "DOULEURS": "Sensations pénibles",
    "DURCIR": "Rendre plus solide",
    "DURER": "Se prolonger",
    "EAU": "Liquide vital",
    "EGOUTIER": "Ouvrier des égouts",
    "EGO": "Moi intérieur",
    "ELABORER": "Préparer avec soin",
    "ELAN": "Mouvement vif",
    "ELEPHANT": "Animal à trompe",
    "ELFE": "Être féerique",
    "ELU": "Choisi par vote",
    "ELUS": "Choisis par vote",
    "EMAIL": "Courrier électronique",
    "ENCAS": "Petit repas",
    "ENFER": "Lieu des damnés",
    "EPAGNEUL": "Chien de chasse",
    "EPI": "Tête de blé",
    "EPIS": "Têtes de blé",
    "EPONGE": "Absorbe l'eau",
    "ERRER": "Marcher sans but",
    "EST": "Direction du levant",
    "ETAT": "Pays organisé",
    "EVACUER": "Faire sortir",
    "EVE": "Première femme",
    "EXIGENCE": "Obligation stricte",
    "FACON": "Manière d'agir",
    "FADO": "Chant portugais",
    "FAX": "Document télécopié",
    "FEES": "Créatures magiques",
    "FERRURES": "Pièces de métal",
    "FETE": "Jour de célébration",
    "FETER": "Célébrer",
    "FEU": "Flammes",
    "FIL": "Fibre à coudre",
    "FILIN": "Corde très solide",
    "FLEUVE": "Rivière maritime",
    "FLOT": "Masse d'eau",
    "FLOTTE": "Ensemble de navires",
    "FOC": "Voile triangulaire",
    "FRACAS": "Bruit assourdissant",
    "GARE": "Station ferroviaire",
    "GARS": "Jeune homme",
    "GAZ": "Fluide aérien",
    "GEL": "Froid solidifiant",
    "GENE": "Unité héréditaire",
    "GEOMETRE": "Mesure les terrains",
    "GILET": "Vêtement sans manches",
    "GONG": "Disque sonore",
    "GRECS": "Habitants de Grèce",
    "GRES": "Roche granuleuse",
    "GREVE": "Arrêt collectif",
    "HAIE": "Rangée d'arbustes",
    "HIER": "Jour précédent",
    "HOTEL": "Hébergement payant",
    "ICI": "En ce lieu",
    "ILE": "Entourée d'eau",
    "ILES": "Entourées d'eau",
    "INTIMITE": "Vie privée",
    "JAMBE": "Membre inférieur",
    "JUDO": "Art martial japonais",
    "JUS": "Liquide de fruit",
    "KILO": "Mille grammes",
    "LAC": "Grande eau intérieure",
    "LACIS": "Enchevêtrement de fils",
    "LAME": "Plaque tranchante",
    "LASSER": "Fatiguer",
    "LETTRE": "Signe de l'alphabet",
    "LIRE": "Parcourir un texte",
    "LIT": "Meuble pour dormir",
    "LITTORAL": "Bord de mer",
    "LOGO": "Symbole de marque",
    "LONGE": "Corde d'animal",
    "LOUP": "Canidé sauvage",
    "LUSTRE": "Grand chandelier",
    "MAI": "Mois du muguet",
    "MAIL": "Promenade arborée",
    "MAIRE": "Dirige la commune",
    "MANUCURE": "Soin des ongles",
    "MARE": "Étang miniature",
    "MASTIC": "Pâte d'étanchéité",
    "MATIN": "Début du jour",
    "MEME": "Identique",
    "MENU": "Liste des plats",
    "MERCI": "Mot de gratitude",
    "MERES": "Mamans",
    "MESSAGES": "Textes envoyés",
    "MIDI": "Douze heures",
    "MIE": "Cœur du pain",
    "MINE": "Galerie souterraine",
    "MOIS": "Douzième d'année",
    "MONDE": "Ensemble des humains",
    "MORAL": "État d'esprit",
    "MOT": "Unité de langage",
    "MOUCHOIR": "Carré de tissu",
    "NAGE": "Action de nager",
    "NAGER": "Pratiquer la natation",
    "NEF": "Partie centrale d'église",
    "NEGLIGER": "Manquer de soin",
    "NEIGE": "Précipitation blanche",
    "NEZ": "Organe de l'odorat",
    "NID": "Abri d'oiseau",
    "NIECE": "Fille du frère",
    "NOCE": "Mariage",
    "NOM": "Mot d'identité",
    "NUAGE": "Masse dans le ciel",
    "NUIT": "Entre soir et matin",
    "OFFRE": "Proposition commerciale",
    "OIE": "Oiseau de basse-cour",
    "OIES": "Oiseaux de basse-cour",
    "OMOPLATE": "Os dorsal",
    "ONDE": "Vague",
    "OPERA": "Drame chanté",
    "ORAGE": "Pluie avec tonnerre",
    "ORIGINAL": "Pas une copie",
    "OSER": "Prendre le risque",
    "OTER": "Enlever",
    "OUATE": "Coton moelleux",
    "OUIE": "Sens de l'écoute",
    "OUISTITI": "Petit singe",
    "OZONE": "Gaz atmosphérique",
    "PAGE": "Feuille de livre",
    "PAN": "Bruit sec",
    "PERE": "Papa",
    "PHARE": "Tour lumineuse",
    "PI": "Rapport du cercle",
    "PIETINER": "Marcher sur place",
    "PLAINE": "Grande étendue plate",
    "POCHE": "Petit sac cousu",
    "POTENCE": "Support vertical",
    "POULET": "Jeune coq",
    "PRE": "Petite prairie",
    "PRES": "À proximité",
    "PRESAGE": "Signe annonciateur",
    "RAGE": "Colère intense",
    "RADES": "Ports abrités",
    "RADIO": "Média sonore",
    "RALE": "Souffle bruyant",
    "RAP": "Musique rythmée",
    "RASSURER": "Redonner confiance",
    "RAT": "Rongeur",
    "REGARD": "Direction des yeux",
    "REGLE": "Instrument de mesure",
    "RESTO": "Restaurant familier",
    "REVE": "Songe",
    "RIA": "Vallée marine",
    "RIDE": "Pli de peau",
    "RIRE": "Expression joyeuse",
    "RIS": "Abat de veau",
    "RIZ": "Céréale asiatique",
    "ROBE": "Vêtement féminin",
    "ROC": "Masse rocheuse",
    "ROI": "Monarque",
    "RONDELLE": "Disque mince",
    "ROUE": "Disque tournant",
    "RUBAN": "Bande de tissu",
    "RUSE": "Astuce",
    "SAC": "Contenant souple",
    "SAPE": "Galerie de mine",
    "SAPIN": "Conifère de Noël",
    "SCENE": "Espace de théâtre",
    "SCOOP": "Information exclusive",
    "SECONDE": "Soixantième de minute",
    "SECU": "Protection sociale",
    "SEIN": "Poitrine",
    "SEL": "Assaisonnement blanc",
    "SENAT": "Assemblée législative",
    "SILEX": "Pierre à étincelles",
    "SINGE": "Primate",
    "SIRENE": "Créature marine",
    "SIROTER": "Boire lentement",
    "SITE": "Emplacement",
    "SITES": "Emplacements",
    "SOFA": "Canapé",
    "SOIE": "Fibre du ver",
    "SOL": "Terrain",
    "SOU": "Ancienne monnaie",
    "SUD": "Point cardinal",
    "STAND": "Emplacement d'exposition",
    "STEAK": "Tranche de viande",
    "TARE": "Défaut caché",
    "TAS": "Amas",
    "TENIR": "Garder en main",
    "TERME": "Mot précis",
    "TESTS": "Épreuves",
    "TETE": "Partie du corps",
    "TETES": "Parties du corps",
    "THEME": "Sujet principal",
    "TIC": "Mouvement involontaire",
    "TIERS": "Troisième partie",
    "TIGE": "Partie de plante",
    "TIR": "Action de tirer",
    "TIRS": "Coups de feu",
    "TISSUS": "Étoffes",
    "TOILE": "Tissu serré",
    "TOLES": "Plaques métalliques",
    "TOMBE": "Sépulture",
    "TOME": "Volume d'ouvrage",
    "TON": "Hauteur de voix",
    "TOPO": "Bref exposé",
    "TOTEM": "Emblème tribal",
    "TRIPES": "Abats",
    "TRUIE": "Femelle du porc",
    "TUBE": "Cylindre creux",
    "UNIR": "Assembler",
    "USURE": "Dégradation lente",
    "UT": "Ancienne note do",
    "VAL": "Petite vallée",
    "VELO": "Bicyclette",
    "VENIR": "Se rapprocher",
    "VER": "Petit invertébré",
    "VERRE": "Matière transparente",
    "VERS": "Petits invertébrés",
    "VERVE": "Énergie verbale",
    "VICE": "Défaut moral",
    "VIE": "Existence",
    "VIS": "Petite pièce filetée",
    "VITE": "Rapidement",
    "VOEU": "Souhait solennel",
    "VOL": "Trajet aérien",
    "VOLATILE": "Animal à plumes",
    "ZERO": "Nombre nul",
}

# Every answer used by the 24 new grids has an explicit editorial wording.
# This deliberately prevents a source-corpus clue from leaking into the batch:
# source corpora provide vocabulary/provenance, never the final clue copy.
MANUAL_CLUES.update({
    "ABRI": "Refuge",
    "ACNE": "Boutons cutanés",
    "ACTE": "Geste",
    "ADO": "Jeune",
    "ADOS": "Jeunes",
    "AGE": "Années vécues",
    "AGIR": "Intervenir",
    "AH": "Cri de surprise",
    "AIDE": "Soutien",
    "AILE": "Pour voler",
    "AINE": "Pli de cuisse",
    "ALIBI": "Justification d'absence",
    "ALOI": "Pureté du métal",
    "AMAS": "Gros tas",
    "AME": "Esprit",
    "AMES": "Esprits",
    "AMI": "Proche apprécié",
    "AMIE": "Proche appréciée",
    "AMIS": "Proches appréciés",
    "AMOUR": "Tendre sentiment",
    "AN": "Douze mois",
    "ANEMONES": "Fleurs colorées",
    "ANOMALIE": "Irrégularité",
    "ANS": "Années",
    "ANSE": "Poignée courbe",
    "ARC": "Arme courbée",
    "ARE": "Surface de 100m²",
    "ARME": "Pour combattre",
    "ART": "Création esthétique",
    "ARTS": "Créations esthétiques",
    "AS": "Champion",
    "ASTRE": "Corps céleste",
    "ATHEE": "Sans dieu",
    "AUGE": "Abreuvoir",
    "AURA": "Halo",
    "AVEU": "Confession",
    "AVIS": "Opinion",
    "AVOIR": "Posséder",
    "BAN": "Exclusion officielle",
    "BAR": "Comptoir à boissons",
    "BEBE": "Très jeune enfant",
    "BEY": "Chef ottoman",
    "BILE": "Liquide digestif",
    "BISE": "Vent froid",
    "BLE": "Céréale",
    "BOA": "Serpent constricteur",
    "BOLS": "Récipients creux",
    "BOSSU": "Courbé du dos",
    "BRIN": "Fine tige",
    "BUEE": "Vapeur condensée",
    "CAMP": "Groupe installé",
    "CAR": "Autocar",
    "CAS": "Situation",
    "CASER": "Ranger",
    "CASES": "Compartiments",
    "CERF": "Grand cervidé",
    "CHOC": "Collision",
    "CIL": "Poil palpébral",
    "COEUR": "Organe vital",
    "COL": "Passage montagneux",
    "COR": "Instrument cuivré",
    "CRAN": "Courage",
    "CREER": "Inventer",
    "CRI": "Son puissant",
    "DADA": "Cheval enfantin",
    "DELAI": "Temps accordé",
    "DEMI": "Moitié",
    "DIEU": "Être suprême",
    "DO": "Note musicale",
    "DON": "Cadeau",
    "DOS": "Partie arrière",
    "DRAME": "Tragédie",
    "EBENE": "Bois noir",
    "ECHO": "Son répété",
    "ECOUTEUR": "Oreillette",
    "ECU": "Ancienne monnaie",
    "ECUS": "Anciennes monnaies",
    "EDEN": "Paradis",
    "ELEVE": "Apprenant",
    "ELOGE": "Compliment",
    "EMINENCE": "Hauteur remarquable",
    "EMOI": "Trouble",
    "ENNUI": "Désagrément",
    "EPEE": "Arme blanche",
    "ERE": "Époque",
    "ESCALE": "Étape de voyage",
    "ETAL": "Table marchande",
    "ETAU": "Outil serrant",
    "ETE": "Saison chaude",
    "ETRE": "Exister",
    "FA": "Note musicale",
    "FER": "Métal",
    "FIEF": "Domaine féodal",
    "FIN": "Terminaison",
    "FRIME": "Esbroufe",
    "GAG": "Blague visuelle",
    "GENS": "Personnes",
    "GIRON": "Repli protecteur",
    "GITE": "Abri",
    "GRIL": "Grille à cuire",
    "GUERE": "Peu",
    "IA": "Intelligence artificielle",
    "IDEE": "Pensée",
    "IDEES": "Pensées",
    "IF": "Conifère",
    "IL": "Pronom masculin",
    "IMPOT": "Taxe",
    "IRIS": "Fleur violette",
    "ISSUE": "Sortie",
    "KINE": "Masseur médical",
    "KIT": "Ensemble prêt",
    "LA": "Note musicale",
    "LAIT": "Boisson blanche",
    "LICE": "Arène",
    "LIEU": "Endroit",
    "LIGNE": "Trait",
    "LIS": "Fleur royale",
    "LOI": "Règle",
    "LOT": "Ensemble",
    "LU": "Parcouru",
    "MAL": "Douleur",
    "MEMO": "Aide-mémoire",
    "MER": "Étendue salée",
    "MI": "Note musicale",
    "MOISI": "Pourri",
    "MONO": "Moniteur",
    "MUR": "Paroi",
    "NEON": "Gaz lumineux",
    "NET": "Propre",
    "NON": "Refus",
    "OBEIR": "Se soumettre",
    "OEUF": "Pondus par poule",
    "ON": "Pronom indéfini",
    "OR": "Métal précieux",
    "ORAL": "Parlé",
    "OREE": "Lisière",
    "OS": "Élément squelettique",
    "OUI": "Accord",
    "OURS": "Grand mammifère",
    "PEPE": "Grand-père",
    "PEU": "Pas beaucoup",
    "PEUR": "Frayeur",
    "PILE": "Batterie électrique",
    "PRIMO": "Premièrement",
    "PUCE": "Parasite sauteur",
    "RAIES": "Lignes",
    "RAILS": "Voies ferrées",
    "RE": "Note musicale",
    "RIEN": "Aucune chose",
    "ROLE": "Fonction",
    "ROMAN": "Récit fictif",
    "RU": "Petit ruisseau",
    "RUE": "Voie urbaine",
    "SAMBA": "Danse brésilienne",
    "SEAU": "Récipient à poignée",
    "SENS": "Direction",
    "SEVE": "Liquide végétal",
    "SI": "Condition",
    "SIC": "Ainsi écrit",
    "SONS": "Bruits",
    "SOUCI": "Préoccupation",
    "STOP": "Arrêt",
    "STUC": "Faux marbre",
    "SUIE": "Dépôt noir",
    "TAC": "Bruit sec",
    "TACOT": "Vieille voiture",
    "TARD": "Après l'heure",
    "TARIF": "Prix fixé",
    "TENACITE": "Persévérance",
    "TEST": "Épreuve",
    "TILT": "Déclic soudain",
    "TIRELIRE": "Boîte à économies",
    "TIRER": "Attirer vers soi",
    "TRES": "Beaucoup",
    "TRI": "Classement",
    "TRIO": "Groupe ternaire",
    "TROT": "Allure chevaline",
    "TUEUR": "Assassin",
    "TULLE": "Tissu ajouré",
    "VENT": "Souffle d'air",
    "YEN": "Monnaie japonaise",
    "ZELE": "Ardeur",
    "ZOO": "Parc animalier",
})

MANUAL_CLUES.update({
    "AGES": "Années vécues",
    "BUS": "Autobus",
    "CESSE": "Prend fin",
    "CHAT": "Félin domestique",
    "CLE": "Ouvre les serrures",
    "CREDO": "Profession de foi",
    "DERIVE": "Écart progressif",
    "DRAMES": "Tragédies",
    "GARDERIE": "Accueil d'enfants",
    "LETTRE": "Caractère alphabétique",
    "LION": "Grand félin",
    "LUNE": "Satellite terrestre",
    "NEF": "Vaisseau d'église",
    "NEZ": "Organe olfactif",
    "NUAGE": "Amas céleste",
    "NUIT": "Période obscure",
    "OIE": "Palmipède domestique",
    "OIES": "Palmipèdes domestiques",
    "OUIE": "Sens auditif",
    "PLAT": "Mets servi",
    "RIGUEURS": "Sévérités",
    "RIVE": "Bord d'eau",
    "SOIN": "Attention",
    "SUITE": "Ce qui suit",
    "TALC": "Poudre minérale",
    "TRAM": "Transport urbain",
    "VETO": "Refus formel",
})


def load_anchor_grids() -> list[dict]:
    grids = []
    for path in ANCHOR_FILES:
        grids.extend(json.loads(path.read_text(encoding="utf-8")).get("grids", []))
    return grids


def load_selected_drafts() -> list[dict]:
    selected = []
    for filename, grid_id in SELECTED_DRAFTS:
        path = ROOT / "output/quality" / filename
        document = json.loads(path.read_text(encoding="utf-8"))
        matches = [grid for grid in document.get("grids", []) if grid.get("id") == grid_id]
        if len(matches) != 1:
            raise ValueError(f"brouillon introuvable ou ambigu: {filename} / {grid_id}")
        selected.append(deepcopy(matches[0]))
    return selected


def normalized_anchor(grid: dict) -> dict:
    grid = deepcopy(grid)
    grid.pop("difficulty", None)
    grid.pop("difficultyMix", None)
    grid["editorialProfile"] = "motman-standard"
    for word in grid.get("words", []):
        word.pop("difficulty", None)
        word["editorialProfile"] = "motman-standard"
    return grid


def edited_grid(number: int, draft: dict) -> dict:
    grid = deepcopy(draft)
    grid_id = f"reference-standard-{number:02d}"
    grid["id"] = grid_id
    grid["editorialProfile"] = "motman-standard"
    grid["publicationStatus"] = "editorially-reviewed-staging"
    grid["humanReview"] = {
        "status": "editorially-reviewed",
        "reviewedAt": "2026-07-14",
        "note": "Réponses et définitions relues manuellement; validation propriétaire encore requise.",
    }
    grid.pop("generationMetrics", None)
    grid.pop("difficulty", None)
    grid.pop("difficultyMix", None)
    for index, word in enumerate(grid["words"], 1):
        answer = word["answer"]
        clue = MANUAL_CLUES.get(answer, "")
        if not clue:
            raise ValueError(f"définition manuelle absente pour {answer}")
        word["wordId"] = f"{grid_id}:word:{index:02d}"
        word["editorialProfile"] = "motman-standard"
        word["definitionStatus"] = "reviewed"
        word["manualReview"] = "approved"
        word.pop("difficulty", None)
        if word.get("image"):
            word["clue"] = ""
            word["sourceClue"] = f"Indice illustré : {word['image']['alt'].casefold()}"
            word["editorialStatus"] = "image-reviewed"
        else:
            word["clue"] = clue
            word["sourceClue"] = clue
            word["sourceId"] = "motman-manual-standard-20260714"
            word["sourceUrl"] = "https://www.lexique.org/"
            word["sourceType"] = "editorial-original"
            word["editorialStatus"] = "human-reviewed"
        errors = editorial_errors(word, root=ROOT)
        if errors:
            raise ValueError(f"{grid_id}/{answer}: {errors}")
    return grid


def main() -> None:
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    blocked = (
        set(blacklist.get("rejectedAnswers", []))
        | set(blacklist.get("rejectedEasyAnswers", []))
        | set(blacklist.get("rejectedNormalAnswers", []))
    )
    rejected_pairs = {
        (item["answer"], item["clue"].casefold())
        for item in blacklist.get("rejectedPairs", [])
    }

    anchors = [normalized_anchor(grid) for grid in load_anchor_grids()]
    drafts = load_selected_drafts()
    edited = [
        edited_grid(index + len(anchors) + 1, draft)
        for index, draft in enumerate(drafts)
    ]
    grids = [*anchors, *edited]
    if len(grids) != 30:
        raise ValueError(f"lot incomplet: {len(grids)} grilles")

    for grid in edited:
        for word in grid["words"]:
            if word["answer"] in blocked:
                raise ValueError(f"réponse blacklistée: {word['answer']}")
            if word.get("clue") and (word["answer"], word["clue"].casefold()) in rejected_pairs:
                raise ValueError(f"couple blacklisté: {word['answer']} / {word['clue']}")

    reports = [audit_grid_topology(grid) for grid in grids]
    invalid = [report["gridId"] for report in reports if not report["valid"]]
    if invalid:
        raise ValueError(f"grilles invalides: {invalid}")

    answer_usage = Counter(
        word["answer"] for grid in grids for word in grid.get("words", [])
    )
    shape_fingerprints = [tuple(sorted(map(tuple, grid["clueCells"]))) for grid in grids]
    document = {
        "version": 1,
        "kind": "motman-standard-staging",
        "publicationPolicy": "Revue propriétaire requise; aucune publication automatique.",
        "editorialProfile": "motman-standard",
        "grids": grids,
        "batchMetrics": {
            "grids": len(grids),
            "ownerApprovedAnchors": len(anchors),
            "editoriallyReviewedNew": len(edited),
            "uniqueShapes": len(set(shape_fingerprints)),
            "answers": sum(answer_usage.values()),
            "uniqueAnswers": len(answer_usage),
            "repeatedAnswers": sum(count - 1 for count in answer_usage.values()),
            "images": sum(bool(word.get("image")) for grid in grids for word in grid["words"]),
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    AUDIT.write_text(json.dumps({
        "version": 1,
        "valid": True,
        "metrics": document["batchMetrics"],
        "grids": reports,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    HTML.write_text(
        render_topology_html(reports, title="MotMan — lot standard de 30 grilles"),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "built",
        "html": str(HTML),
        "metrics": document["batchMetrics"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
