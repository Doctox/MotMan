"""Build the third five-grid 9x10 owner-review batch.

Every clue is written explicitly here.  The script produces review artifacts
only and never mutates the active runtime catalog.
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
from collections import Counter
from pathlib import Path

from editorial_quality import editorial_errors, grid_semantic_errors
from grid_topology import audit_grid_topology, render_topology_html


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "src/data/grid-generation-handcrafted/central-priority-third-five.review.json"
AUDIT = ROOT / "output/quality/central-priority-third-five-audit.json"
HTML = ROOT / "output/quality/central-priority-third-five-review.html"

SELECTIONS = (
    ROOT / "output/quality/central-priority-third-clean-rabes.json",
    ROOT / "output/quality/central-priority-third-dedupe-pi.json",
    ROOT / "output/quality/central-priority-third-clean-gatte-nursing.json",
    ROOT / "output/quality/central-priority-third-g4-age-ame-clean.json",
    ROOT / "output/quality/central-priority-third-g5-zero-1931.json",
)

FORBIDDEN = {"AMAS", "BOL", "AN", "ANS"}

CLUES = {
    # Grid 1
    "RE": "Note musicale", "PAPES": "Chefs du Vatican",
    "EDAM": "Fromage néerlandais", "CRU": "Vin classé",
    "LOTERIES": "Jeux de hasard", "TRESSE": "Natte",
    "CUITES": "Non crues", "TOLET": "Appui d'aviron",
    "ESPERERA": "Attendra", "GAI": "Joyeux", "SERF": "Paysan féodal",
    "ORNE": "Département normand", "SAS": "Passage étanche",
    "PELE": "Sans végétation", "ADO": "Jeune",
    "PATTU": "Aux pattes fournies", "EMERITE": "Très expérimenté",
    "BUSE": "Conduit", "CISELEES": "Finement gravées",
    "RESSERRA": "Rapprocha", "RETORS": "Rusé", "LU": "Parcouru",
    "CESAR": "Empereur romain", "TAFS": "Boulots familiers", "EGO": "Moi",
    # Grid 2
    "MI": "Note musicale", "DODOS": "Sommeils enfantins",
    "ETUI": "Boîte protectrice", "CRI": "Son puissant",
    "REPEREUR": "Localisateur", "ARE": "Cent mètres carrés",
    "ARIA": "Air d'opéra", "PARADIS": "Lieu céleste",
    "MASSE": "Grande quantité", "PLURIEL": "Opposé du singulier",
    "AISSEAU": "Bardeau de bois", "ANSE": "Petite baie",
    "RUE": "Voie urbaine", "DERAPE": "Glisse", "OTERA": "Enlèvera",
    "DUPER": "Tromper", "DIRA": "Exprimera",
    "CERISIER": "Arbre à cerises", "RUISSEAU": "Cours d'eau",
    "RADARS": "Détecteurs routiers", "AMUSE": "Divertit",
    "ELUE": "Choisie", "AH": "Cri surpris", "PAN": "Bruit soudain",
    "LIS": "Fleurs à bulbe",
    # Grid 3
    "AS": "Champion", "ABBES": "Supérieurs religieux",
    "GOUT": "Sens gustatif", "AGE": "Nombre d'années",
    "INTERNET": "Réseau mondial", "BANNIE": "Chassée",
    "EVIDENT": "Manifeste", "CRETONNE": "Toile de coton",
    "ANNE": "Duchesse bretonne", "NET": "Bien défini",
    "PAS": "Mouvement du pied", "PESE": "A du poids",
    "AGIR": "Intervenir", "BON": "De qualité",
    "BUT": "Objectif", "ETERNITE": "Temps sans fin",
    "FETE": "Moment de célébration", "ANCIENNE": "D'autrefois",
    "GEHENNES": "Souffrances infernales", "RONDO": "Forme musicale",
    "IA": "Intelligence artificielle", "BERNA": "Trompa",
    "AVENS": "Gouffres calcaires", "TETE": "Partie du corps",
    "CAP": "Direction suivie",
    # Grid 4
    "MEMENTOS": "Rappels écrits", "OVALAIRE": "De forme ovale",
    "TELECRAN": "Ardoise magique", "CRANS": "Encoches",
    "APTE": "Capable", "VERSE": "Fait couler", "PIRE": "Plus mauvais",
    "TAC": "Bruit sec", "LOT": "Groupe assorti", "SAMU": "Urgence médicale",
    "INEDITES": "Jamais publiées", "MOTS": "Unités écrites",
    "EVE": "Première femme", "MAL": "Douleur",
    "ELECTRE": "Fille d'Agamemnon", "NACRES": "Matières irisées",
    "TIRA": "Fit feu", "ORANT": "Personnage en prière",
    "SENS": "Direction", "LA": "Note musicale", "PERTE": "Déficit",
    "ETAT": "Pays", "ECUS": "Anciennes monnaies", "PLI": "Marque du tissu",
    "AME": "Esprit", "SI": "Sous condition",
    # Grid 5
    "CAS": "Situation", "TON": "Manière de parler",
    "REAPPARU": "Revenu", "ARBOUSES": "Fruits d'arbousier",
    "MELER": "Entremêler", "PRETES": "Disponibles", "ETIER": "Canal côtier",
    "ABSENTS": "Non présents", "RASSURE": "Réconforte", "ATRE": "Foyer",
    "SEC": "Sans humidité", "CRAMPE": "Contraction douloureuse",
    "AERER": "Renouveler l'air", "SABLE": "Grains de plage",
    "TAS": "Grand nombre", "OREE": "Bord du bois", "NUS": "Sans vêtements",
    "POETESSE": "Femme poète",
    "PURETES": "Absences d'impuretés", "SINUS": "Cavités nasales",
    "ORSEC": "Plan de secours", "ETRE": "Exister", "FA": "Note musicale",
    "ART": "Savoir-faire", "BAR": "Café",
}

IMAGES = {
    "PIN": ("pin.svg", "Pin"),
    "OIE": ("oie.svg", "Oie"),
    "ROCHE": ("roche.svg", "Roche"),
    "AVION": ("avion.svg", "Avion"),
    "ART": ("art.svg", "Palette de peinture"),
}


def shape_fingerprint(grid: dict) -> str:
    payload = json.dumps(sorted(grid["clueCells"]), separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def image_record(filename: str, alt: str) -> dict:
    return {
        "asset": f"/assets/clues/twemoji/{filename}",
        "alt": alt,
        "source": "Twemoji",
        "sourceUrl": "https://github.com/jdecked/twemoji",
        "license": "CC BY 4.0",
    }


def load_grids() -> list[dict]:
    grids = []
    for number, path in enumerate(SELECTIONS, 1):
        source_grid = json.loads(path.read_text(encoding="utf-8"))["grids"][0]
        grid = copy.deepcopy(source_grid)
        grid_id = f"central-priority-third-review-{number:02d}"
        grid["id"] = grid_id
        grid["publicationStatus"] = "owner-rejected"
        grid["editorialProfile"] = "motman-standard-owner-reviewed"
        grid["reviewCycle"] = "2026-07-15-third-five"
        grid["shapeFingerprint"] = shape_fingerprint(grid)
        for word_number, word in enumerate(grid["words"], 1):
            answer = word["answer"]
            if answer in FORBIDDEN:
                raise ValueError(f"{grid_id}: réponse interdite {answer}")
            if answer not in CLUES and answer not in IMAGES:
                raise ValueError(f"{grid_id}: définition manuelle absente pour {answer}")
            word["wordId"] = f"{grid_id}:word:{word_number:02d}"
            word["clue"] = "" if answer in IMAGES else CLUES[answer]
            word["definitionStatus"] = "manually-edited"
            word["manualReview"] = "rejected-with-grid-by-owner"
            word["editorialStatus"] = "image-reviewed" if answer in IMAGES else "human-reviewed"
            word["editorialReviewId"] = "central-priority-third-five-20260715"
            # Owner-written clues keep their lexical attestation when their
            # editorial source intentionally has no public URL.
            if not word.get("sourceUrl"):
                word["sourceUrl"] = "https://www.lexique.org/"
            if answer in IMAGES:
                word["image"] = image_record(*IMAGES[answer])
            else:
                word.pop("image", None)
            errors = editorial_errors(word, root=ROOT)
            if errors:
                raise ValueError(f"{grid_id}/{answer}: {errors}")
        semantic = grid_semantic_errors(grid["words"])
        if semantic:
            raise ValueError(f"{grid_id}: {semantic}")
        grids.append(grid)
    return grids


def assert_blacklist(grids: list[dict]) -> int:
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    blocked = set(blacklist.get("rejectedAnswers", []))
    blocked_pairs = {
        (item["answer"], item["clue"].casefold())
        for item in blacklist.get("rejectedPairs", [])
    }
    for grid in grids:
        for word in grid["words"]:
            if word["answer"] in blocked:
                raise ValueError(f"réponse blacklistée: {word['answer']}")
            pair = (word["answer"], word.get("clue", "").casefold())
            if word.get("clue") and pair in blocked_pairs:
                raise ValueError(f"couple blacklisté: {pair}")
    return len(blocked)


def main() -> None:
    grids = load_grids()
    blacklist_total = assert_blacklist(grids)
    reports = [audit_grid_topology(grid) for grid in grids]
    invalid = {report["gridId"]: report["errors"] for report in reports if not report["valid"]}
    if invalid:
        raise ValueError(f"grilles invalides: {invalid}")

    answers = [word["answer"] for grid in grids for word in grid["words"]]
    usage = Counter(answers)
    repeated = {answer: count for answer, count in usage.items() if count > 1}
    if repeated != {"SI": 2}:
        raise ValueError(f"répétitions inattendues: {repeated}")
    answer_set = set(answers)
    inflections = sorted(
        (answer, f"{answer}S") for answer in answer_set
        if len(answer) >= 3 and f"{answer}S" in answer_set
    )
    if inflections:
        raise ValueError(f"singuliers/pluriels répétés: {inflections}")

    metrics = {
        "grids": len(grids),
        "answers": len(answers),
        "uniqueAnswers": len(usage),
        "repeatedAnswersInsideBatch": repeated,
        "singularPluralFamiliesInsideBatch": 0,
        "uniqueShapes": len({grid["shapeFingerprint"] for grid in grids}),
        "images": sum(bool(word.get("image")) for grid in grids for word in grid["words"]),
        "forbiddenAnswers": sorted(FORBIDDEN),
        "centralCorpusEligibleAnswers": 9218,
        "centralCorpusAnswersUsed": sum(grid.get("centralAnswerCount", 0) for grid in grids),
        "lexiqueRescueAnswersUsed": sum(grid.get("lexiqueRescueCount", 0) for grid in grids),
        "blacklistedAnswersTotal": blacklist_total,
    }
    document = {
        "version": 1,
        "kind": "central-priority-third-five-owner-rejected",
        "publicationPolicy": "Lot rejeté par le propriétaire; publication interdite.",
        "ownerDecision": {
            "status": "rejected",
            "date": "2026-07-15",
            "reason": "Trop de réponses déjà présentes dans le catalogue actif et trop de mots de deux lettres.",
        },
        "batchMetrics": metrics,
        "grids": grids,
    }
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    AUDIT.write_text(json.dumps({
        "version": 1, "valid": True, "metrics": metrics, "grids": reports,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    page = render_topology_html(reports, title="MotMan — troisième lot de cinq grilles")
    summary = (
        '<section style="max-width:1100px;margin:18px auto;padding:14px 18px;'
        'background:#fff8dc;border:1px solid #d7b75a;border-radius:10px">'
        '<b>Lot rejeté — ne pas publier</b><br>'
        f'{metrics["answers"]} réponses · {metrics["uniqueShapes"]} silhouettes · '
        f'{metrics["images"]} images. AMAS, BOL, AN et ANS sont absents. '
        'Une seule répétition résiduelle est signalée : SI (2 fois). '
        'Aucune famille singulier/pluriel.</section>'
    )
    source_note = (
        '<section style="max-width:1100px;margin:18px auto;padding:12px 18px;'
        'background:#eef6ff;border:1px solid #8db7df;border-radius:10px">'
        '<b>Vérifications lexicales ciblées</b><br>'
        'Les termes moins courants conservés (TOLET, AISSEAU, CRÉTONNE, GÉHENNES, '
        'RONDO, AVENS, OVALAIRE, ORANT, ÉTIER, ORÉE et ARBOUSES) ont été contrôlés. '
        'Les définitions affichées restent volontairement courtes.</section>'
    )
    page = page.replace("<body>", "<body>" + summary + source_note, 1)
    HTML.write_text(page, encoding="utf-8")
    print(json.dumps({
        "status": "built", "html": str(HTML), "staging": str(STAGING),
        "audit": str(AUDIT), "metrics": metrics,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
