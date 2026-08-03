from __future__ import annotations

import copy
import json
import re
from collections import Counter
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

import prepare_certified_editorial_sublot_111bca5d3810 as base


ROOT = Path(__file__).resolve().parents[1]
SOURCE_EXPORT = Path(
    r"C:\Users\peete\AppData\Local\MotManLexiconStudio\exports"
    r"\motman-certified-grids-for-editorialization-2.json"
)
SOURCE_AUDIT = Path(
    r"C:\Users\peete\OneDrive\Documents\MotMan Grid Factory\reports"
    r"\lexical-reservoir\certified-batch-lexical-audit-9e969ceeb44a.json"
)
CATALOG_PATH = ROOT / "src/data/grid.catalog.json"
RUNTIME_PATH = ROOT / "src/data/runtime.grid.catalog.json"
BLACKLIST_PATH = ROOT / "src/data/editorial.blacklist.json"
OUTPUT_DIR = ROOT / "output/quality/certified-editorial-9e969ceeb44a"
STAGING_PATH = OUTPUT_DIR / "staging.json"
AUDIT_PATH = OUTPUT_DIR / "audit.json"
SELECTION_PATH = OUTPUT_DIR / "selection-report.json"
REVIEW_PATH = OUTPUT_DIR / "owner-review-with-solutions.html"
PLAYTEST_PATH = OUTPUT_DIR / "owner-playtest-no-solutions.html"
ARTIFACT_MANIFEST_PATH = OUTPUT_DIR / "artifact-manifest.json"

EXPECTED_SCHEMA = "motman-grid-certified-editorial-handoff"
EXPECTED_VERSION = 1
EXPECTED_FILE_SHA256 = (
    "9e969ceeb44a45b28029df49b809ae68c4d6a59240e202a2c65b7a41aca53241"
)
EXPECTED_PAYLOAD_SHA256 = (
    "f684b5b2040c94faecff661cc40956fd8eeef45826fbd6d99dcc5d4cc5411a1c"
)
EXPECTED_AUDIT_SHA256 = (
    "33b4666831f2213df18be51c7fe834c859a0a1ff0ed1edb05a23b9d00cef8a68"
)
EXPECTED_CATALOG_SHA256 = (
    "77611ba7ae121b7fdf4369692f1de85503f51074b2e3065c8bb1b926c3bec622"
)
EXPECTED_RUNTIME_SHA256 = (
    "ba9fa0c4e64c36cb7bf727c474c567c86a8c704e8adfd51090d6076822344655"
)
EXPECTED_CATALOG_VERSION = 22
EXPECTED_ACTIVE_GRID_COUNT = 44
EXPECTED_SOURCE_GRID_COUNT = 54
EXPECTED_CANDIDATE_STATE_COUNT = 286
REVIEW_DATE = "2026-07-31"
EDITORIAL_SOURCE_ID = "motman-editorial-certified-9e969ceeb44a"
EDITORIAL_SOURCE_URL = "internal://motman/editorial/certified-9e969ceeb44a"


RETAINED_CANDIDATES = (
    "4098493d-916e-4d73-ab70-35ac5e2d7ed5",
    "a7cced25-9afe-4822-9ad5-4f92913df0a9",
    "0d9a815d-ad17-4f62-8549-5ab3ffe14336",
    "d0fa5c27-8138-4d1b-8eb5-8cb726cb7305",
    "1cb63d2a-7a1f-4d34-87e8-18b26bcf7e5a",
    "441f7942-f428-4bb3-99ff-dbfd30d020bb",
    "0024adb9-8621-4232-9b01-21d36a6019b3",
    "d286b291-267d-4b30-9780-c4cf3a5ffb4d",
    "9bec2e93-d282-410e-bd17-4e25ea9e7d1b",
    "c7fea712-1159-4463-a6a2-3ce922a07767",
    "5b7b37fb-097a-47be-ad86-968643de5cb9",
    "9b2a6bfd-0813-40e3-8622-ebd424729dac",
)


EXCLUSION_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "category": "variante-active",
        "reason": (
            "Variante à 88,9 % de la grille active factory-7x8-081c89e3c3924258 ; "
            "100 % de ses réponses ont déjà été vues."
        ),
        "ids": ["ff14f81e-946d-48f4-a545-d80cc7dbd47e"],
    },
    {
        "category": "qualite-lexicale",
        "reason": (
            "Concentration de formes faibles, anciennes ou techniques qui rend la grille "
            "moins agréable que le sous-lot retenu."
        ),
        "ids": [
            "f8a0d5f1-5b6f-46aa-bc12-4d12bc445c38",
            "e9a3ddde-9e24-4fe1-9e42-9a9ff2f6a1c9",
            "51525e48-125d-4880-8ee3-7d9ef1628c1a",
            "7ff16f49-dc47-4f4f-9394-29826a8464a3",
            "7c36f630-f864-4d91-bc3f-b2c765e78c39",
            "c4d0bf3c-8344-4897-8a44-c9b73247706d",
            "61dc67a7-6548-4e01-b533-b02269f549c7",
            "aee0ad64-b6e4-44da-aa6d-d1c2df71ac6a",
        ],
    },
    {
        "category": "variante-refusee",
        "reason": (
            "Variante à 87,5 % d’une grille déjà refusée par le propriétaire ; "
            "elle n’apporte pas assez de diversité."
        ),
        "ids": ["8a68ddc7-3c81-4b11-96df-cc79188e5b23"],
    },
    {
        "category": "variante-proche",
        "reason": (
            "Variante moins convaincante d’une famille représentée par une grille retenue "
            "ou par une forme lexicalement plus accessible."
        ),
        "ids": [
            "5b370926-8db1-46d5-b434-026b25b47f2b",
            "8ba194b7-1137-4214-8276-c529cb3b3cc7",
            "d0194bdd-50fe-4928-91c2-b7d3d332a044",
            "c6aa35eb-fb94-4549-8e1f-288b2fd789ec",
            "fc74e17a-8b5b-4272-8b28-9fb7366b98fa",
            "98beab3a-7d8b-4e8b-a165-274fad8190f0",
            "08645710-353d-44ce-906d-24509e2510da",
            "c5b485b3-0ead-4195-b5ef-599cd28d0bba",
            "816528f2-337e-40ce-b32d-82980fb10e5c",
            "5aef517f-e4db-4de4-adb4-9e7ab36b6437",
            "2bfe7cd0-cb9f-4e83-add4-55c25882de3c",
            "f334ffb8-4a92-466c-8df5-5905cedc4186",
        ],
    },
    {
        "category": "repetition-et-diversite",
        "reason": (
            "La grille augmente trop les répétitions de petites réponses ou recoupe "
            "fortement une famille déjà surreprésentée dans l’export."
        ),
        "ids": [
            "fde73582-8b45-4104-912c-1d1dce868531",
            "b068dbd3-6e4d-4cc9-be33-cf2dd39d293d",
            "3ed40dbb-586e-4ca5-8b59-52256d2b8504",
            "412b1c87-994e-4280-bdbe-6ca5ef6e8f65",
            "f90bc13d-f031-480b-ad26-45f717366680",
            "eac401ba-9b30-40f9-897d-83788c9a8baa",
            "c7fd7c61-a935-4f45-8c51-f7b37da36772",
            "883b9672-3b6b-4347-a845-983d802d28ca",
            "a6e3c19d-0c77-4fb0-b3ed-015cca288e78",
            "0cdcf56a-a9c6-497e-9ca0-33d8acf0a273",
            "13cfb7cf-fd3f-4151-93c3-a2bc99bb8bd0",
            "7d808657-bd5b-42c7-807c-b4bd32ae1f95",
            "a6889217-04b0-441c-b5be-16dd0ce5def7",
            "67a35673-4a11-401b-a372-dfef61b0a13e",
            "d9e74e13-3ceb-4531-a650-4a3c8094ddc2",
            "76035b61-b737-46df-a8c1-344663f43e69",
            "a7c8e093-8e88-498d-acb0-34710c10c406",
            "61a1c083-1b83-4c92-9ba0-150ebde60950",
            "d703dde5-e020-44d1-8e14-9c31c08b95d8",
            "68c92747-1b42-4b27-87c9-e55b9cd97692",
        ],
    },
)


def exclusion_map() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for group in EXCLUSION_GROUPS:
        for candidate_id in group["ids"]:
            if candidate_id in result:
                raise ValueError(f"Exclusion en double : {candidate_id}")
            result[candidate_id] = {
                "category": str(group["category"]),
                "reason": str(group["reason"]),
            }
    return result


EXCLUSIONS = exclusion_map()


CLUES: dict[str, str] = {
    "ACTION": "Fait d’agir",
    "ADIDAS": "Rivale de Nike",
    "AGILITE": "Souplesse et rapidité",
    "AGIR": "Entrer en action",
    "AGUERRI": "Habitué aux épreuves",
    "ALEA": "Événement imprévisible",
    "AMANITE": "Champignon parfois toxique",
    "AME": "Partie spirituelle",
    "AMENER": "Conduire jusqu’ici",
    "AMI": "Proche de confiance",
    "AMINCI": "Devenu plus mince",
    "AMORAL": "Sans sens moral",
    "AN": "Douze mois",
    "ANEMIE": "Carence sanguine",
    "APANAGE": "Privilège exclusif",
    "ARIDITE": "Grande sécheresse",
    "ART": "Création esthétique",
    "AS": "Champion",
    "ATRES": "Foyers de cheminée",
    "AVARIE": "Dégât survenu",
    "AVIS": "Opinion exprimée",
    "BACCARA": "Jeu de casino",
    "BEIGNET": "Pâtisserie du flic américain",
    "BESSON": "Luc, réalisateur français",
    "BOITES": "Récipients fermés",
    "BRASERO": "Foyer extérieur chauffant",
    "BRAVOS": "Applaudissements",
    "CALMANT": "Apaisant",
    "CANAPE": "Long siège rembourré",
    "CAVERNE": "Grande grotte",
    "CORSET": "Sous-vêtement gainant",
    "CRI": "Voix très forte",
    "CROISER": "Rencontrer en chemin",
    "DRE": "Mentor d’Eminem",
    "DUE": "À payer",
    "ECAILLE": "Armure du poisson",
    "ECHELLE": "Suite progressive",
    "ECLATE": "En mille morceaux",
    "ECU": "Ancienne monnaie française",
    "EDITO": "Article d’opinion",
    "EGALES": "De même valeur",
    "ELEMENT": "Partie constitutive",
    "ELU": "Choisi par vote",
    "EMETTRE": "Diffuser un signal",
    "ENIEME": "Encore une fois",
    "ENIVRER": "Rendre ivre",
    "ENNEMIE": "Adversaire déclarée",
    "ENONCE": "Texte du problème",
    "ENORMES": "Vraiment gigantesques",
    "ENTREE": "Accès principal",
    "EPARGNE": "Argent économisé",
    "EPAULE": "Articulation du bras",
    "EPICER": "Ajouter des épices",
    "EPURER": "Retirer le superflu",
    "ERRATA": "Liste de corrections",
    "ERRE": "Vagabonde",
    "ERRONE": "Inexact",
    "EST": "Direction du levant",
    "ETALER": "Déployer",
    "ETALON": "Mâle reproducteur",
    "ETE": "Saison chaude",
    "ETENDU": "Mis à plat",
    "FER": "Métal magnétique",
    "FIEF": "Domaine seigneurial",
    "FILTRE": "Retient les impuretés",
    "FRAISES": "Fruits rouges",
    "FRAPPE": "Coup porté",
    "GAIN": "Somme remportée",
    "GRACILE": "Fin et délicat",
    "GRANDE": "Pas petite",
    "GRAS": "Riche en graisse",
    "GREFFER": "Transplanter un tissu",
    "HONTE": "Gêne humiliante",
    "IA": "Intelligence artificielle",
    "IGNARE": "Sans aucune culture",
    "IGUANE": "Grand lézard tropical",
    "IL": "Pronom masculin",
    "IMAGIER": "Livre d’images",
    "ION": "Atome chargé",
    "LAC": "Étendue aquatique",
    "LASCAR": "Homme rusé",
    "LIMITE": "Frontière à respecter",
    "LIMITES": "Frontières à respecter",
    "LION": "Grand félin africain",
    "LOIR": "Rongeur grand dormeur",
    "MACULER": "Couvrir de taches",
    "MAIGRE": "Très peu charnu",
    "MAL": "Douleur",
    "MATETA": "Jean-Philippe, footballeur",
    "MEPRIS": "Dédain affiché",
    "MERDIER": "Sacré bazar",
    "MESURER": "Calculer une dimension",
    "MIEL": "Produit des abeilles",
    "MOT": "Unité de langage",
    "MUE": "Changement de voix",
    "NERF": "Fibre du corps",
    "NET": "Sans bavure",
    "NIVEAU": "Degré atteint",
    "NOM": "Mot qui désigne",
    "OCARINA": "Flûte en terre",
    "OIE": "Cousine du canard",
    "ON": "Pronom indéfini",
    "ONDE": "Vibration propagée",
    "OR": "Métal précieux",
    "OREO": "Biscuit noir fourré",
    "OUIE": "Sens auditif",
    "PAN": "Bruit de tir",
    "PARENTS": "Père et mère",
    "PARFAIT": "Sans aucun défaut",
    "PERONE": "Voisin du tibia",
    "PEUPLE": "Population nationale",
    "PIC": "Sommet pointu",
    "PISTARD": "Motard sur piste",
    "RACHAT": "Acquérir une nouvelle fois",
    "RADINE": "Avare au féminin",
    "RAGEUR": "Plein de colère",
    "RAGOTER": "Raconter des potins",
    "RAISIN": "Fruit en grappe",
    "RALLYE": "Course automobile chronométrée",
    "RAP": "Musique aux rimes",
    "RAPIERE": "Fine épée ancienne",
    "RARE": "Peu fréquent",
    "RAS": "Rien à signaler",
    "RECENT": "Datant de peu",
    "RECTEUR": "Dirige une académie",
    "REGENT": "Dirigeant provisoire",
    "REINES": "Monarques couronnées",
    "RELENT": "Odeur persistante",
    "RELEVES": "Documents bancaires",
    "RESEAU": "Ensemble connecté",
    "RESOLU": "Décidé à agir",
    "RESTOS": "Lieux où manger",
    "ROI": "Monarque couronné",
    "ROMAIN": "Habitant de Rome",
    "ROMAINE": "Salade allongée",
    "RUE": "Voie en ville",
    "SACHET": "Petit emballage souple",
    "SCIAGE": "Découpe par scie",
    "SEAU": "Récipient à anse",
    "SEC": "Sans humidité",
    "SECOUER": "Agiter vivement",
    "SEMEUR": "Personne qui ensemence",
    "SERIES": "Épisodes à suivre",
    "SERREES": "Très rapprochées",
    "SET": "Manche au tennis",
    "SETTER": "Chien de chasse à poil long",
    "SINUER": "Avancer en courbes",
    "SMS": "Message sur téléphone",
    "SODAS": "Boissons gazeuses sucrées",
    "STARTUP": "Jeune entreprise innovante",
    "SUE": "Transpire",
    "TAMTAM": "Tambour africain",
    "TASSEES": "Serrées ensemble",
    "TASSER": "Compacter fortement",
    "TEE": "Support de balle de golf",
    "TENDRE": "Pas très dur",
    "TIC": "Geste involontaire",
    "TISANE": "Infusion de plantes",
    "TON": "Manière de parler",
    "TRIS": "Classements successifs",
    "UN": "Premier nombre",
    "UNE": "Article féminin",
    "UTILE": "Qui rend service",
    "VIRALES": "Massivement partagées",
    "VISEUR": "Aide à viser",
    "YEN": "Monnaie japonaise",
}


IMAGE_SPECS: dict[str, dict[str, Any]] = {
    "ART": {
        "asset": "/assets/clues/twemoji/art.svg",
        "alt": "Palette de peintre",
        "concept": "art",
    },
    "FRAISES": {
        "asset": "/assets/clues/twemoji/fraise.svg",
        "alt": "Des fruits rouges",
        "concept": "fraises",
    },
    "LION": {
        "asset": "/assets/clues/twemoji/lion.svg",
        "alt": "Un félin criniéré",
        "concept": "lion",
    },
    "OIE": {
        "asset": "/assets/clues/twemoji/oie.svg",
        "alt": "Une volaille blanche",
        "concept": "oie",
    },
    "MIEL": {
        "asset": "/assets/clues/twemoji/miel.svg",
        "alt": "Pot doré sucré",
        "concept": "miel",
        "alreadyAvailableInMotMan": False,
        "requiresNewAabAsset": False,
        "sourceUrl": (
            "https://github.com/jdecked/twemoji/blob/v15.1.0/"
            "assets/svg/1f36f.svg"
        ),
    },
    "RAISIN": {
        "asset": "/assets/clues/twemoji/raisin.svg",
        "alt": "Une grappe violette",
        "concept": "raisin",
    },
    "ROI": {
        "asset": "/assets/clues/twemoji/roi.svg",
        "alt": "Monarque couronné",
        "concept": "roi",
    },
    "SEAU": {
        "asset": "/assets/clues/twemoji/seau.svg",
        "alt": "Récipient avec anse",
        "concept": "seau",
    },
    "SMS": {
        "asset": "/assets/clues/twemoji/sms.svg",
        "alt": "Un message mobile",
        "concept": "SMS",
    },
}


ENTITY_REVIEWS: dict[str, dict[str, Any]] = {
    "ADIDAS": {
        "entityType": "marque",
        "distinctiveTokens": ["Nike"],
        "sourceUrl": "https://www.adidas-group.com/en/legal-notice",
        "acceptedAs": "adidas",
    },
    "BESSON": {
        "entityType": "personne",
        "distinctiveTokens": ["Luc"],
        "sourceUrl": "https://www.unifrance.org/film/11187/leon",
        "acceptedAs": "Luc Besson",
    },
    "DRE": {
        "entityType": "personne",
        "distinctiveTokens": ["Eminem"],
        "sourceUrl": "https://www.drdre.com/",
        "acceptedAs": "Dr. Dre",
    },
    "MATETA": {
        "entityType": "personne",
        "distinctiveTokens": ["Jean-Philippe"],
        "sourceUrl": (
            "https://www.cpfc.co.uk/teams/first-team/forward/"
            "jean-philippe-mateta/"
        ),
        "acceptedAs": "Jean-Philippe Mateta",
    },
    "OREO": {
        "entityType": "marque",
        "distinctiveTokens": ["Biscuit"],
        "sourceUrl": "https://www.oreo.com/",
        "acceptedAs": "Oreo",
    },
}


COMMON_ANGLICISMS = {"RAP", "SET", "SMS", "STARTUP", "TEE"}
CURRENT_COMMON = COMMON_ANGLICISMS | {"IA", "RESTOS"}


OWNER_APPROVED_LONG_CLUES = {
    "BEIGNET": "Référence au cliché du policier américain demandée par le propriétaire.",
    "RACHAT": "Reformulation explicite demandée par le propriétaire.",
    "SETTER": "La précision sur la chasse et le poil long distingue clairement la race.",
    "TEE": "La mention du golf élimine l’ambiguïté du support de balle.",
}


FLAGGED_FORM_REVIEWS: dict[str, dict[str, str]] = {
    "ATRES": {
        "status": "acceptée-sous-revue",
        "definition": CLUES["ATRES"],
        "reason": "Pluriel concret ; la définition évite le sens abstrait.",
    },
    "EDITO": {
        "status": "acceptée-sous-revue",
        "definition": CLUES["EDITO"],
        "reason": "Abréviation courante et immédiatement trouvable.",
    },
    "ERRE": {
        "status": "acceptée-sous-revue",
        "definition": CLUES["ERRE"],
        "reason": "Sens verbal courant retenu explicitement par le propriétaire.",
    },
    "MATETA": {
        "status": "décision-propriétaire",
        "definition": CLUES["MATETA"],
        "reason": "Référence football actuelle, sourcée, mais nom propre à confirmer.",
    },
    "MERDIER": {
        "status": "décision-propriétaire",
        "definition": CLUES["MERDIER"],
        "reason": "Registre familier assumé ; aucune vulgarité n’apparaît dans l’indice.",
    },
    "PERONE": {
        "status": "acceptée-sous-revue",
        "definition": CLUES["PERONE"],
        "reason": "Terme anatomique précis avec voisin distinctif.",
    },
    "RELEVES": {
        "status": "acceptée-sous-revue",
        "definition": CLUES["RELEVES"],
        "reason": "Le sens bancaire lève l’ambiguïté du pluriel.",
    },
}


HUMAN_DECISION_ITEMS = [
    {
        "answer": "MATETA",
        "recommendation": "Valider si la référence football convient au ton MotMan.",
        "reason": "Jean-Philippe Mateta est sourcé sur le site de son club.",
    },
    {
        "answer": "MERDIER",
        "recommendation": "Valider ou refuser la grille entière selon le registre souhaité.",
        "reason": "Le mot est courant mais familier ; l’indice reste propre.",
    },
]


SUPABASE_SNAPSHOT = {
    "projectRef": "kfacjvxzdtxybvxhfmzg",
    "checkedOn": "2026-07-31",
    "queryMode": "read-only-select",
    "activeGridCount": 44,
    "minimumVersion": 22,
    "maximumVersion": 22,
    "matchesLocalRuntimeIds": True,
}


def baseline_catalog_paths() -> tuple[Path, Path]:
    """Return the immutable v22 inputs, even after the approved v23 publication."""
    if (
        base.sha256_file(CATALOG_PATH) == EXPECTED_CATALOG_SHA256
        and base.sha256_file(RUNTIME_PATH) == EXPECTED_RUNTIME_SHA256
    ):
        return CATALOG_PATH, RUNTIME_PATH
    archived_catalog = OUTPUT_DIR / "prepublish-grid-catalog-v22.json"
    archived_runtime = OUTPUT_DIR / "prepublish-runtime-grid-catalog-v22.json"
    if (
        archived_catalog.is_file()
        and archived_runtime.is_file()
        and base.sha256_file(archived_catalog) == EXPECTED_CATALOG_SHA256
        and base.sha256_file(archived_runtime) == EXPECTED_RUNTIME_SHA256
    ):
        return archived_catalog, archived_runtime
    raise ValueError("Le baseline v22 revu est introuvable ou a changé")


def verify_catalog_baseline() -> dict[str, Any]:
    catalog_path, runtime_path = baseline_catalog_paths()
    catalog_sha = base.sha256_file(catalog_path)
    runtime_sha = base.sha256_file(runtime_path)
    catalog = base.read_json(catalog_path)
    runtime = base.read_json(runtime_path)
    if (
        catalog.get("version") != EXPECTED_CATALOG_VERSION
        or runtime.get("version") != EXPECTED_CATALOG_VERSION
        or len(catalog.get("grids", [])) != EXPECTED_ACTIVE_GRID_COUNT
        or len(runtime.get("grids", [])) != EXPECTED_ACTIVE_GRID_COUNT
    ):
        raise ValueError("Le baseline actif n’est plus le catalogue v22 à 44 grilles")
    local_ids = sorted(str(grid.get("id")) for grid in runtime["grids"])
    return {
        "version": EXPECTED_CATALOG_VERSION,
        "gridCount": EXPECTED_ACTIVE_GRID_COUNT,
        "catalogPath": str(catalog_path),
        "catalogSha256": catalog_sha,
        "runtimePath": str(runtime_path),
        "runtimeSha256": runtime_sha,
        "runtimeIdDigest": base.canonical_digest(local_ids),
        "supabase": SUPABASE_SNAPSHOT,
    }


def walk_editorial_fields(value: object, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}.{key}"
            if str(key).casefold() in {
                "clue",
                "definition",
                "image",
                "images",
                "sourceclue",
            }:
                found.append(child)
            found.extend(walk_editorial_fields(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(walk_editorial_fields(item, f"{prefix}[{index}]"))
    return found


def verify_source() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if base.sha256_file(SOURCE_EXPORT) != EXPECTED_FILE_SHA256:
        raise ValueError("SHA-256 physique du handoff inattendu")
    if base.sha256_file(SOURCE_AUDIT) != EXPECTED_AUDIT_SHA256:
        raise ValueError("SHA-256 de l’audit Réservoir inattendu")
    document = base.read_json(SOURCE_EXPORT)
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
    computed_payload = base.canonical_digest(unsigned)
    if (
        manifest.get("payloadSha256") != EXPECTED_PAYLOAD_SHA256
        or computed_payload != EXPECTED_PAYLOAD_SHA256
    ):
        raise ValueError("Digest payload invalide")
    grids = document.get("grids")
    states = manifest.get("candidateStates")
    if not isinstance(grids, list) or len(grids) != EXPECTED_SOURCE_GRID_COUNT:
        raise ValueError("Le handoff doit contenir exactement 54 grilles")
    if not isinstance(states, list) or len(states) != EXPECTED_CANDIDATE_STATE_COUNT:
        raise ValueError("Le manifest doit décrire exactement 286 candidats")
    editorial_paths = walk_editorial_fields(document)
    if editorial_paths:
        raise ValueError(f"Champs éditoriaux interdits : {editorial_paths[:5]}")

    state_by_id = {str(item.get("candidateId")): item for item in states}
    if len(state_by_id) != len(states):
        raise ValueError("candidateId du manifest en double")
    exported_ids = {str(grid.get("candidateId")) for grid in grids}
    eligible_ids = {
        candidate_id
        for candidate_id, state in state_by_id.items()
        if state.get("requestedForExport") and state.get("eligibleForExport")
    }
    if exported_ids != eligible_ids:
        raise ValueError("Les grilles exportées ne correspondent pas aux états éligibles")

    grid_ids: set[str] = set()
    exact_fingerprints: set[str] = set()
    word_ids: set[str] = set()
    lineage_errors: list[str] = []
    structure_errors: list[str] = []
    for grid in grids:
        candidate_id = str(grid["candidateId"])
        state = state_by_id[candidate_id]
        final = grid.get("finalAudit", {})
        if not (
            state.get("reviewStatus") == "approved"
            and state.get("certificationStatus") == "certified"
            and state.get("eligibleForExport") is True
            and final.get("status") == "certified"
            and final.get("exportable") is True
            and not final.get("blocking")
        ):
            lineage_errors.append(candidate_id)
        certification = str(final.get("certificationDigest") or "")
        if certification != str(state.get("certificationDigest") or ""):
            lineage_errors.append(f"{candidate_id}:certification")
        if certification != str(grid.get("digests", {}).get("certification") or ""):
            lineage_errors.append(f"{candidate_id}:digest")
        if grid.get("columns") != 7 or grid.get("rows") != 8:
            structure_errors.append(f"{candidate_id}:dimensions")
        proposed_id = str(grid.get("proposedGridId") or "")
        exact = str(grid.get("exactFingerprint") or "")
        if not proposed_id or proposed_id in grid_ids:
            structure_errors.append(f"{candidate_id}:grid-id")
        if not exact or exact in exact_fingerprints:
            structure_errors.append(f"{candidate_id}:exact-fingerprint")
        grid_ids.add(proposed_id)
        exact_fingerprints.add(exact)
        for answer in grid.get("answers", []):
            word_id = str(answer.get("proposedWordId") or "")
            normalized = str(answer.get("normalized") or "")
            cells = answer.get("cells") or []
            if not word_id or word_id in word_ids:
                structure_errors.append(f"{candidate_id}:word-id")
            word_ids.add(word_id)
            if len(cells) != int(answer.get("length") or 0):
                structure_errors.append(f"{word_id}:path-length")
            if len(normalized) != int(answer.get("length") or 0):
                structure_errors.append(f"{word_id}:answer-length")
    if lineage_errors or structure_errors:
        raise ValueError(
            f"Filiation/topologie source invalide : lineage={lineage_errors[:5]}, "
            f"structure={structure_errors[:5]}"
        )

    lexical_audit = base.read_json(SOURCE_AUDIT)
    contract = lexical_audit.get("contract_validation", {})
    intrinsic_checks = {
        "physicalJsonValid": contract.get("physical_json_valid") is True,
        "schemaValid": contract.get("schema_valid") is True,
        "payloadValid": contract.get("payload_sha256_valid") is True,
        "wordsOnly": contract.get("words_only") is True,
        "allCertifiedExportable": contract.get("all_grids_certified_exportable") is True,
        "noStructureErrors": not contract.get("structure_errors"),
        "noFingerprintMismatches": not contract.get("fingerprint_mismatches"),
        "noCertificationMismatches": not contract.get("certification_digest_mismatches"),
        "factoryDigestsCurrent": all(
            contract.get("factory_digest_matches", {}).values()
        ),
    }
    if not all(intrinsic_checks.values()):
        raise ValueError(f"Audit intrinsèque invalide : {intrinsic_checks}")
    owner_matches = contract.get("current_owner_source_digest_matches", {})
    expected_owner_matches = {
        "approvedBatch": False,
        "forbiddenGrids": True,
        "pendingPool": True,
        "playedHistory": True,
    }
    if owner_matches != expected_owner_matches:
        raise ValueError(f"Divergence propriétaire inattendue : {owner_matches}")
    if contract.get("motman_policy_hash_current") is not False:
        raise ValueError("La divergence de snapshot MotMan attendue a changé")
    provenance = {
        "intrinsicContractValid": True,
        "externalSnapshotStatus": "expected-divergence-recorded",
        "externalContractValid": bool(contract.get("contract_valid")),
        "ownerSourceDigestMatches": owner_matches,
        "motmanPolicyHashCurrent": contract.get("motman_policy_hash_current"),
        "explanation": (
            "Le handoff provient de la copie SQLite cohérente annoncée par le "
            "clavardage principal ; la base propriétaire réelle n’a volontairement "
            "pas reçu ce lot approuvé et son snapshot de politique précède le v22."
        ),
    }
    return document, lexical_audit, provenance


def source_answer_set(grid: dict[str, Any]) -> set[str]:
    return {
        str(item.get("normalized") or "").upper()
        for item in grid.get("answers", [])
        if str(item.get("normalized") or "").strip()
    }


def image_for(answer: str) -> dict[str, Any] | None:
    spec = IMAGE_SPECS.get(answer)
    if spec is None:
        return None
    return {
        "asset": base.local_asset_data_uri(spec["asset"]),
        "alt": spec["alt"],
        "concept": spec["concept"],
        "source": "Twemoji 15.1",
        "license": "CC BY 4.0",
        "sourceUrl": spec.get("sourceUrl", "https://github.com/jdecked/twemoji"),
        "sourceAsset": spec["asset"],
        "alreadyAvailableInMotMan": spec.get("alreadyAvailableInMotMan", True),
        "requiresNewAabAsset": spec.get("requiresNewAabAsset", False),
    }


def build_word(source: dict[str, Any]) -> dict[str, Any]:
    answer = str(source["normalized"]).upper()
    definition = CLUES[answer]
    image = image_for(answer)
    entity = ENTITY_REVIEWS.get(answer)
    source_url = entity["sourceUrl"] if entity else EDITORIAL_SOURCE_URL
    word: dict[str, Any] = {
        "wordId": source["proposedWordId"],
        "answer": answer,
        "clue": "" if image else definition,
        "sourceClue": image["alt"] if image else definition,
        "editorialDefinition": definition,
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
            "thoughtful" if float(source.get("familiarity") or 0) < 20 else "common"
        ),
        "partOfSpeech": (
            "proper-name"
            if entity and entity["entityType"] == "personne"
            else "brand"
            if entity and entity["entityType"] == "marque"
            else source.get("partOfSpeech")
            if source.get("partOfSpeech") not in {None, "", "unknown"}
            else "reviewed-lexical-item"
        ),
        "languageStatus": (
            "known-proper-name"
            if entity
            else "common-anglicism"
            if answer in COMMON_ANGLICISMS
            else "french"
        ),
        "culturalStatus": (
            "current-pop"
            if entity
            else "current-common"
            if answer in CURRENT_COMMON
            else "everyday"
        ),
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
            "flexionType": source.get("flexionType"),
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
    if answer in OWNER_APPROVED_LONG_CLUES:
        word["longClueReview"] = {
            "status": "owner-approved-clarity",
            "reason": OWNER_APPROVED_LONG_CLUES[answer],
            "approvedOn": REVIEW_DATE,
        }
    if entity:
        word["properNameReview"] = {
            "status": "human-reviewed-distinctive",
            "entityType": entity["entityType"],
            "clueUniquenessChecked": True,
            "distinctiveTokens": entity["distinctiveTokens"],
            "acceptedAs": entity["acceptedAs"],
            "sourceUrl": entity["sourceUrl"],
        }
    errors = base.pilot_editorial_errors(word, root=ROOT)
    if errors:
        raise ValueError(f"{answer}: contrat éditorial invalide : {errors}")
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
            "culturalEntities": sorted(
                word["answer"] for word in words if word.get("properNameReview")
            ),
        },
    }
    topology = base.audit_grid_topology(
        grid,
        require_word_ids=True,
        enforce_layout=False,
        topology_profile="pilot",
    )
    if not topology["valid"]:
        raise ValueError(f"{grid['id']}: topologie invalide : {topology['errors']}")
    return grid


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return 0.0 if not union else round(100 * len(left & right) / len(union), 1)


def selected_pairwise(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, left in enumerate(sources):
        for right in sources[index + 1 :]:
            left_answers = source_answer_set(left)
            right_answers = source_answer_set(right)
            result.append(
                {
                    "leftCandidateId": left["candidateId"],
                    "rightCandidateId": right["candidateId"],
                    "proximityPercent": jaccard(left_answers, right_answers),
                    "commonAnswers": sorted(left_answers & right_answers),
                    "sameShape": left["shapeFingerprint"] == right["shapeFingerprint"],
                }
            )
    return sorted(result, key=lambda item: (-item["proximityPercent"], item["leftCandidateId"]))


def active_catalog_crosscheck(sources: list[dict[str, Any]]) -> dict[str, Any]:
    catalog_path, _runtime_path = baseline_catalog_paths()
    catalog = base.read_json(catalog_path)
    active = []
    for grid in catalog.get("grids", []):
        active.append(
            {
                "id": str(grid.get("id")),
                "exactFingerprint": str(grid.get("sourceExactFingerprint") or ""),
                "answers": {
                    str(word.get("answer") or "").upper()
                    for word in grid.get("words", [])
                    if str(word.get("answer") or "").strip()
                },
            }
        )
    exact: list[dict[str, str]] = []
    closest: list[dict[str, Any]] = []
    for source in sources:
        answers = source_answer_set(source)
        comparisons = [
            {
                "gridId": item["id"],
                "proximityPercent": jaccard(answers, item["answers"]),
                "commonAnswers": sorted(answers & item["answers"]),
            }
            for item in active
        ]
        best = max(comparisons, key=lambda item: item["proximityPercent"])
        closest.append({"candidateId": source["candidateId"], **best})
        for item in active:
            if (
                item["exactFingerprint"]
                and item["exactFingerprint"] == source["exactFingerprint"]
            ):
                exact.append(
                    {"candidateId": source["candidateId"], "gridId": item["id"]}
                )
    return {
        "catalogVersion": catalog.get("version"),
        "activeGridCount": len(active),
        "exactDuplicates": exact,
        "closestByCandidate": closest,
        "maximumProximityPercent": max(
            (item["proximityPercent"] for item in closest), default=0
        ),
        "valid": not exact and all(
            item["proximityPercent"] < 80 for item in closest
        ),
    }


def selection_report(
    document: dict[str, Any],
    lexical_audit: dict[str, Any],
    provenance: dict[str, Any],
    retained_sources: list[dict[str, Any]],
    active_crosscheck: dict[str, Any],
) -> dict[str, Any]:
    by_candidate = {str(grid["candidateId"]): grid for grid in document["grids"]}
    source_counts = Counter(
        answer for grid in document["grids"] for answer in source_answer_set(grid)
    )
    selected_counts = Counter(
        answer for grid in retained_sources for answer in source_answer_set(grid)
    )
    pairwise = selected_pairwise(retained_sources)
    focus = ("IL", "OR", "ON", "AN", "ETE", "IA", "RUE", "SEL", "EST")
    return {
        "schema": "motman-certified-editorial-selection-report",
        "version": 2,
        "reviewDate": REVIEW_DATE,
        "sourceGridCount": len(document["grids"]),
        "retainedGridCount": len(retained_sources),
        "excludedGridCount": len(EXCLUSIONS),
        "retainedCandidateIds": list(RETAINED_CANDIDATES),
        "retainedProposedGridIds": [grid["proposedGridId"] for grid in retained_sources],
        "excluded": [
            {
                "candidateId": candidate_id,
                "proposedGridId": by_candidate[candidate_id]["proposedGridId"],
                **decision,
            }
            for candidate_id, decision in sorted(EXCLUSIONS.items())
        ],
        "selectionRationale": (
            "Sous-lot volontairement resserré : priorité à la variété lexicale, "
            "aux définitions naturelles et à l’absence de variantes proches."
        ),
        "repetition": {
            "sourceSlots": sum(source_counts.values()),
            "retainedSlots": sum(selected_counts.values()),
            "sourceDistinctAnswers": len(source_counts),
            "retainedDistinctAnswers": len(selected_counts),
            "focusReduction": {
                answer: {
                    "source54": source_counts[answer],
                    "retained12": selected_counts[answer],
                    "removed": source_counts[answer] - selected_counts[answer],
                    "reductionPercent": round(
                        100
                        * (source_counts[answer] - selected_counts[answer])
                        / max(1, source_counts[answer]),
                        1,
                    ),
                }
                for answer in focus
            },
            "retainedRepeatedAnswers": {
                answer: count
                for answer, count in sorted(selected_counts.items())
                if count > 1
            },
        },
        "selectedPairwise": {
            "maximumProximityPercent": pairwise[0]["proximityPercent"],
            "closestPairs": pairwise[:10],
            "allBelowEightyPercent": all(
                item["proximityPercent"] < 80 for item in pairwise
            ),
        },
        "catalogCrossCheck": active_crosscheck,
        "reservoirCrossCheck": {
            "auditPath": str(SOURCE_AUDIT),
            "auditSha256": EXPECTED_AUDIT_SHA256,
            "blacklistedWordIntersection": lexical_audit.get("lexical_summary", {}).get(
                "blacklisted_word_intersection"
            ),
            "exactActiveDuplicates": lexical_audit.get("catalog_summary", {}).get(
                "exact_active_duplicates"
            ),
            "exactRetiredDuplicates": lexical_audit.get("catalog_summary", {}).get(
                "exact_retired_duplicates"
            ),
            "exactOwnerRefusedDuplicates": lexical_audit.get("catalog_summary", {}).get(
                "exact_owner_refused_duplicates"
            ),
            "externalProvenance": provenance,
        },
        "flaggedFormReviews": FLAGGED_FORM_REVIEWS,
        "humanDecisionItems": HUMAN_DECISION_ITEMS,
        "policyDecision": {
            "rotationCooldown": "warning-and-penalty",
            "hardBlacklist": "blocking",
            "ownerInstructionApplied": True,
        },
    }


def review_header(selection: dict[str, Any], grids: list[dict[str, Any]]) -> str:
    focus_rows = "".join(
        "<tr>"
        f"<td>{escape(answer)}</td>"
        f"<td>{item['source54']}</td>"
        f"<td>{item['retained12']}</td>"
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
      Les solutions figurent uniquement sur cette page. Le playtest séparé
      n’en contient aucune.</p>
      <div class="summary-cards">
        <div><b>{len(grids)}</b><span>grilles proposées</span></div>
        <div><b>{len(EXCLUSIONS)}</b><span>grilles écartées</span></div>
        <div><b>{sum(len(grid['words']) for grid in grids)}</b><span>réponses</span></div>
        <div><b>{sum(grid['imageCount'] for grid in grids)}</b><span>indices-images</span></div>
      </div>
      <h2>Deux décisions demandées</h2>
      <table><thead><tr><th>Réponse</th><th>Recommandation</th><th>Pourquoi</th>
      </tr></thead><tbody>{decision_rows}</tbody></table>
      <h2>Formes surveillées</h2>
      <table><thead><tr><th>Forme</th><th>Statut</th><th>Définition</th><th>Motif</th>
      </tr></thead><tbody>{flagged_rows}</tbody></table>
      <h2>Réduction des répétitions</h2>
      <table><thead><tr><th>Réponse</th><th>Export 54</th><th>Sous-lot 12</th>
      <th>Réduction</th></tr></thead><tbody>{focus_rows}</tbody></table>
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
    page = base.render_topology_html(
        reports,
        title="MotMan — revue du lot certifié 9e969ceeb44a",
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
    script = f"""
    <script>
    (() => {{
      const key = 'motman-certified-editorial-9e969ceeb44a-decisions-v1';
      const load = () => {{ try {{ return JSON.parse(localStorage.getItem(key) || '{{}}'); }}
        catch {{ return {{}}; }} }};
      const decisions = load();
      const paint = box => {{
        const id = box.dataset.ownerGrid;
        const value = decisions[id] || '';
        box.classList.toggle('accept', value === 'accept');
        box.classList.toggle('reject', value === 'reject');
        box.querySelector('.decision-state').textContent =
          value === 'accept' ? 'Validée localement' :
          value === 'reject' ? 'Refusée localement' : 'À décider';
      }};
      document.querySelectorAll('[data-owner-grid]').forEach(box => {{
        paint(box);
        box.querySelectorAll('[data-decision]').forEach(button =>
          button.addEventListener('click', () => {{
            decisions[box.dataset.ownerGrid] = button.dataset.decision;
            localStorage.setItem(key, JSON.stringify(decisions));
            paint(box);
          }}));
      }});
      document.querySelector('#export-decisions').addEventListener('click', () => {{
        const payload = {{schema:'motman-owner-editorial-decisions',version:1,
          sourceFileSha256:'{EXPECTED_FILE_SHA256}', decisions}};
        const blob = new Blob([JSON.stringify(payload, null, 2)], {{type:'application/json'}});
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = 'motman-certified-editorial-owner-decisions-lot2.json';
        link.click();
        URL.revokeObjectURL(link.href);
      }});
    }})();
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
        "version": 2,
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
                "sha256": base.sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in paths
        ],
        "catalogMutation": False,
        "supabaseMutation": False,
        "publicationAuthorized": False,
    }


def main() -> None:
    document, lexical_audit, provenance = verify_source()
    baseline_before = verify_catalog_baseline()
    by_candidate = {str(grid["candidateId"]): grid for grid in document["grids"]}
    selected = set(RETAINED_CANDIDATES)
    excluded = set(EXCLUSIONS)
    if set(by_candidate) != selected | excluded or selected & excluded:
        raise ValueError("La sélection n’est pas exhaustive ou disjointe")
    retained_sources = [by_candidate[candidate_id] for candidate_id in RETAINED_CANDIDATES]
    expected_answers = set().union(*(source_answer_set(grid) for grid in retained_sources))
    if expected_answers != set(CLUES):
        raise ValueError(
            f"Couverture éditoriale incorrecte : "
            f"missing={sorted(expected_answers - set(CLUES))}, "
            f"extra={sorted(set(CLUES) - expected_answers)}"
        )

    blacklist = base.blacklist_audit(retained_sources)
    if not blacklist.get("valid"):
        raise ValueError(f"Blacklist bloquante : {blacklist}")
    active_crosscheck = active_catalog_crosscheck(retained_sources)
    if not active_crosscheck["valid"]:
        raise ValueError(f"Doublon ou variante active trop proche : {active_crosscheck}")
    selection = selection_report(
        document,
        lexical_audit,
        provenance,
        retained_sources,
        active_crosscheck,
    )
    grids = [build_grid(source) for source in retained_sources]
    topology_reports = [
        base.audit_grid_topology(
            grid,
            require_word_ids=True,
            enforce_layout=False,
            topology_profile="pilot",
        )
        for grid in grids
    ]
    if any(not report["valid"] for report in topology_reports):
        raise ValueError("Une topologie de staging est invalide")
    definition_crosscheck = base.active_definition_crosscheck(grids)

    staging = {
        "schema": "motman-grid-certified-editorial-staging",
        "version": 2,
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
            "provenance": provenance,
        },
        "selection": {
            "sourceGridCount": len(document["grids"]),
            "retainedGridCount": len(grids),
            "excludedGridCount": len(EXCLUSIONS),
            "selectionReport": str(SELECTION_PATH),
        },
        "grids": grids,
    }
    audit = {
        "schema": "motman-certified-editorial-staging-audit",
        "version": 2,
        "reviewDate": REVIEW_DATE,
        "valid": True,
        "contract": {
            "physicalSha256Valid": True,
            "payloadSha256Valid": True,
            "wordsOnly": True,
            "gridCount": len(document["grids"]),
            "candidateStateCount": len(document["manifest"]["candidateStates"]),
            "allSourceGridsCertifiedExportable": True,
            "intrinsicContractValid": True,
            "externalSnapshot": provenance,
        },
        "baseline": baseline_before,
        "blacklist": blacklist,
        "selection": {
            "retained": len(grids),
            "excluded": len(EXCLUSIONS),
            "distinctAnswers": len(CLUES),
            "answerSlots": sum(len(grid["words"]) for grid in grids),
            "images": sum(grid["imageCount"] for grid in grids),
            "maximumSelectedPairProximityPercent": selection["selectedPairwise"][
                "maximumProximityPercent"
            ],
            "flaggedFormReviews": FLAGGED_FORM_REVIEWS,
            "humanDecisionItems": HUMAN_DECISION_ITEMS,
        },
        "catalogCrossCheck": active_crosscheck,
        "editorial": {
            "allAnswersCovered": True,
            "allTextDefinitionsAtMostThreeWords": all(
                len(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]+", clue)) <= 3
                for clue in CLUES.values()
            ),
            "allTextDefinitionsComplyWithLengthPolicy": all(
                len(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]+", clue)) <= 3
                or answer in OWNER_APPROVED_LONG_CLUES
                for answer, clue in CLUES.items()
            ),
            "ownerApprovedLongDefinitions": {
                answer: {
                    "definition": CLUES[answer],
                    "reason": reason,
                }
                for answer, reason in OWNER_APPROVED_LONG_CLUES.items()
            },
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
    base.atomic_json(SELECTION_PATH, selection)
    base.atomic_json(STAGING_PATH, staging)
    base.atomic_json(AUDIT_PATH, audit)
    base.atomic_text(REVIEW_PATH, render_owner_review(topology_reports, selection, grids))
    base.atomic_text(
        PLAYTEST_PATH,
        base.render_playtest_html(copy.deepcopy(topology_reports)),
    )

    baseline_after = verify_catalog_baseline()
    if baseline_after != baseline_before:
        raise ValueError("Un catalogue a changé pendant la préparation")
    manifest = artifact_manifest(
        [SELECTION_PATH, STAGING_PATH, AUDIT_PATH, REVIEW_PATH, PLAYTEST_PATH]
    )
    base.atomic_json(ARTIFACT_MANIFEST_PATH, manifest)
    result = {
        "valid": True,
        "retained": len(grids),
        "excluded": len(EXCLUSIONS),
        "answerSlots": sum(len(grid["words"]) for grid in grids),
        "distinctAnswers": len(CLUES),
        "images": sum(grid["imageCount"] for grid in grids),
        "humanDecisions": HUMAN_DECISION_ITEMS,
        "catalogModified": False,
        "runtimeModified": False,
        "supabaseModified": False,
        "artifacts": manifest["artifacts"],
        "artifactManifest": {
            "path": str(ARTIFACT_MANIFEST_PATH),
            "sha256": base.sha256_file(ARTIFACT_MANIFEST_PATH),
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
