"""Assemble five locally repaired 9x10 grids for owner review.

Answers and short definitions are frozen explicitly here.  The script never
publishes to the active catalog; it produces staging, audit and HTML review
artifacts only.
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
STAGING = ROOT / "src/data/grid-generation-handcrafted/central-priority-five.review.json"
AUDIT = ROOT / "output/quality/central-priority-five-audit.json"
HTML = ROOT / "output/quality/central-priority-five-review.html"

SELECTIONS = (
    ROOT / "output/quality/central-priority-final-grid-1.json",
    ROOT / "output/quality/central-priority-final-grid-2.json",
    ROOT / "output/quality/central-priority-final-repair-human-d2.json",
    ROOT / "output/quality/central-priority-final-grid-4.json",
    ROOT / "output/quality/central-priority-final-grid-5.json",
)

CLUES = {
    # Grid 1
    "AN": "Douze mois", "ALORS": "Donc", "BOBO": "Petite blessure",
    "LAC": "Étendue d'eau", "BIENAIME": "Très cher", "ICIBAS": "Sur terre",
    "ERIGER": "Construire", "ERRES": "Vagabondes", "SOBRIETE": "Modération",
    "EGO": "Moi", "TETU": "Obstiné", "CELA": "Cette chose", "SOL": "Terrain",
    "ABBE": "Prêtre", "LOI": "Règle", "OBEIR": "Se soumettre",
    "RONCIER": "Buisson épineux", "ACES": "Services gagnants",
    "LIBEREES": "Rendues libres", "AMARETTO": "Liqueur italienne",
    "AIGRIT": "Rend amer", "RE": "Note musicale", "ELOGE": "Compliment",
    "SEUL": "Sans compagnie", "SEC": "Sans humidité",
    # Grid 2
    "SI": "Sous condition", "CAP": "Direction", "FAN": "Admirateur",
    "IVOIRINE": "Teinte ivoire", "TONNELET": "Petit tonneau", "RITES": "Cérémonies",
    "ORESTE": "Héros grec", "PAIRE": "Duo", "AMENDER": "Corriger",
    "MORTELS": "Non éternels", "TETE": "Visage", "RUE": "Voie urbaine",
    "AVOIR": "Posséder", "PONTE": "Femelle pondeuse", "FIL": "Brin",
    "ANES": "Baudets", "NET": "Très clair", "INESPERE": "Inattendu",
    "RESTANT": "Encore présent", "EIDER": "Canard nordique", "VERSE": "Répand",
    "RELU": "Lu encore", "MI": "Note musicale", "AME": "Esprit", "MOT": "Unité écrite",
    # Grid 3
    "AS": "Champion", "ASTER": "Fleur étoilée", "BAIL": "Contrat locatif",
    "DOS": "Partie arrière", "ACCELERE": "Augmente l'allure", "VENIR": "Arriver",
    "CHASTE": "Pudique", "RAGEANT": "Exaspérant", "CELERITE": "Rapidité",
    "ADOS": "Jeunes", "SON": "Bruit", "MELE": "Entremêle", "ABAT": "Renverse",
    "SAC": "Grand bagage", "TIC": "Manie", "ELEVAGES": "Fermes animales",
    "OSER": "Se risquer", "DENTAIRE": "Des dents", "ORIENTAL": "Venu d'Asie",
    "LESER": "Désavantager", "IA": "Intelligence artificielle", "CREDO": "Principes",
    "HALON": "Gaz extincteur", "CAS": "Situation",
    # Grid 4
    "UT": "Ancien do", "NUS": "Sans vêtements", "MAL": "Douleur",
    "UNITAIRE": "Non divisé", "MINARETS": "Tours musulmanes", "ETANGS": "Petits lacs",
    "REINE": "Souveraine", "ENDOS": "Signature dorsale", "ORIENTE": "Guide",
    "LIEE": "Attachée", "TIR": "Lancer", "NUMERO": "Identifiant",
    "UNITE": "Élément seul", "SINAI": "Péninsule égyptienne",
    "MIES": "Intérieurs du pain", "ART": "Savoir-faire", "LEST": "Poids stabilisateur",
    "TANNERIE": "Atelier du cuir", "ARGENTE": "Couvert d'argent",
    "COATI": "Petit carnivore", "DENT": "Quenotte", "SUER": "Transpirer",
    "LU": "Parcouru", "MOI": "Ego", "ARE": "Cent mètres carrés",
    # Grid 5
    "LA": "Note musicale", "APNEE": "Souffle suspendu", "MUET": "Sans voix",
    "TAS": "Grand nombre", "ARTISANE": "Travailleuse manuelle", "REMIS": "Reporté",
    "TREMAS": "Deux points", "AERONEF": "Engin volant", "VUE": "Image",
    "NOTE": "Facture", "ILLICITE": "Illégal", "ERES": "Temps géologiques",
    "AMAS": "Accumulation", "PUR": "Sans mélange", "ETIRER": "Allonger",
    "OSES": "Tentes", "TAMANOIR": "Grand fourmilier", "ANISETTE": "Liqueur anisée",
    "SEMONCE": "Réprimande", "PI": "Constante circulaire", "TAULE": "Prison familière",
    "REELU": "Élu encore", "FEES": "Magiciennes", "VIF": "Plein d'énergie",
}

IMAGES = {
    "BOL": ("bol.svg", "Bol"),
    "CITRON": ("citron.svg", "Citron"),
    "RAT": ("rat.svg", "Rat"),
    "MARTEAU": ("marteau.svg", "Marteau"),
    "FEU": ("feu.svg", "Feu"),
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
        grid_id = f"central-priority-review-{number:02d}"
        grid["id"] = grid_id
        grid["publicationStatus"] = "owner-review-required"
        grid["editorialProfile"] = "motman-standard-owner-reviewed"
        grid["reviewCycle"] = "2026-07-15"
        grid["shapeFingerprint"] = shape_fingerprint(grid)
        for word_number, word in enumerate(grid["words"], 1):
            answer = word["answer"]
            word["wordId"] = f"{grid_id}:word:{word_number:02d}"
            word["clue"] = "" if answer in IMAGES else CLUES[answer]
            word["definitionStatus"] = "manually-edited"
            word["manualReview"] = "reviewed-awaiting-owner"
            word["editorialStatus"] = "image-reviewed" if answer in IMAGES else "human-reviewed"
            word["editorialReviewId"] = "central-priority-five-20260715"
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


def assert_blacklist(grids: list[dict]) -> None:
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    blocked = set(blacklist.get("rejectedAnswers", []))
    blocked.update(item["answer"] for item in blacklist.get("rotationCooldownAnswers", []))
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


def main() -> None:
    grids = load_grids()
    assert_blacklist(grids)
    reports = [audit_grid_topology(grid) for grid in grids]
    invalid = {report["gridId"]: report["errors"] for report in reports if not report["valid"]}
    if invalid:
        raise ValueError(f"grilles invalides: {invalid}")

    answers = [word["answer"] for grid in grids for word in grid["words"]]
    usage = Counter(answers)
    repeated = {answer: count for answer, count in usage.items() if count > 1}
    expected_repeats = {"NET": 2, "TETE": 2}
    if repeated != expected_repeats:
        raise ValueError(f"répétitions inattendues: {repeated}")
    answer_set = set(answers)
    inflections = sorted(
        (answer, f"{answer}S") for answer in answer_set
        if len(answer) >= 3 and f"{answer}S" in answer_set
    )
    if inflections:
        raise ValueError(f"singuliers/pluriels répétés: {inflections}")

    central_total = sum(grid.get("centralAnswerCount", 0) for grid in grids)
    rescue_total = sum(grid.get("lexiqueRescueCount", 0) for grid in grids)
    metrics = {
        "grids": 5,
        "answers": len(answers),
        "uniqueAnswers": len(usage),
        "repeatedAnswersInsideBatch": repeated,
        "singularPluralFamiliesInsideBatch": 0,
        "uniqueShapes": len({grid["shapeFingerprint"] for grid in grids}),
        "images": sum(bool(word.get("image")) for grid in grids for word in grid["words"]),
        "centralCorpusAnswersUsed": central_total,
        "lexiqueRescueAnswersUsed": rescue_total,
        "centralCorpusSize": 9491,
        "blacklistedAnswersTotal": len(json.loads(
            (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
        ).get("rejectedAnswers", [])),
    }
    document = {
        "version": 1,
        "kind": "central-priority-five-owner-review",
        "publicationPolicy": "Aucune publication automatique; validation du propriétaire requise.",
        "batchMetrics": metrics,
        "grids": grids,
    }
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    AUDIT.write_text(json.dumps({
        "version": 1, "valid": True, "metrics": metrics, "grids": reports,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    page = render_topology_html(reports, title="MotMan — cinq nouvelles grilles à relire")
    summary = (
        '<section style="max-width:1100px;margin:18px auto;padding:14px 18px;'
        'background:#fff8dc;border:1px solid #d7b75a;border-radius:10px">'
        '<b>Lot de revue — non publié</b><br>'
        f'{metrics["centralCorpusAnswersUsed"]} réponses centrales + '
        f'{metrics["lexiqueRescueAnswersUsed"]} secours relus · 5 images · 5 silhouettes. '
        'Deux répétitions résiduelles sont signalées : NET et TÊTE (2 fois chacune). '
        'Aucune famille singulier/pluriel.</section>'
    )
    page = page.replace("<body>", "<body>" + summary, 1)
    HTML.write_text(page, encoding="utf-8")
    print(json.dumps({
        "status": "built", "html": str(HTML), "staging": str(STAGING),
        "audit": str(AUDIT), "metrics": metrics,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
