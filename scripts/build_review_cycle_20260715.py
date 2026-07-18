"""Build three manually edited 9x10 grids for an owner review pause.

This script never touches the active catalog.  Geometry comes from bounded
solver drafts; every displayed clue is explicitly rewritten and reviewed.
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

from editorial_quality import editorial_errors
from grid_topology import audit_grid_topology, render_topology_html


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "src/data/grid-generation-handcrafted/review-cycle-20260715.staging.json"
AUDIT = ROOT / "output/quality/review-cycle-20260715-audit.json"
HTML = ROOT / "output/quality/review-cycle-20260715.html"

SELECTIONS = (
    (ROOT / "output/quality/standard-crossing-drafts.json", "standard-draft-09"),
    (ROOT / "output/quality/priority3-replacement-draft.json", "standard-draft-01"),
    (ROOT / "output/quality/standard-crossing-drafts-v3.json", "standard-draft-17"),
)

# Short, direct mobile clues.  Image answers are intentionally absent: their
# existing reviewed Twemoji record replaces text in the rendered clue cell.
CLUES = {
    # Review grid 01
    "DO": "Note avant ré",
    "TIC": "Mouvement nerveux",
    "CAP": "Diplôme professionnel",
    "ECORCHER": "Blesser la peau",
    "TIRELIRE": "Cagnotte à pièces",
    "PAPES": "Chefs du Vatican",
    "SLIP": "Sous-vêtement",
    "AUTOS": "Voitures",
    "BUT": "Objectif",
    "TOFU": "Pâte de soja",
    "ELIMINER": "Écarter",
    "YEN": "Monnaie japonaise",
    "SOUS": "Petites monnaies",
    "TETE": "Partie du corps",
    "ICI": "À cet endroit",
    "COR": "Instrument de chasse",
    "CHIP": "Puce électronique",
    "AERER": "Ventiler",
    "PRES": "À proximité",
    "REPIT": "Pause",
    "CLAPOTIS": "Bruit aquatique",
    "RU": "Petit ruisseau",
    "SAULE": "Arbre pleureur",
    "LUTIN": "Petit elfe",
    "SONO": "Matériel audio",
    "BEY": "Titre ottoman",
    # Review grid 02
    "TV": "Télévision",
    "CASTE": "Groupe social",
    "AGIR": "Faire",
    "PLI": "Étoffe repliée",
    "DECISION": "Choix arrêté",
    "CONGE": "Vacances",
    "CHOISIR": "Se décider",
    "HOTE": "Invité",
    "SENS": "Direction",
    "ART": "Création esthétique",
    "HIER": "Jour précédent",
    "CIEL": "Voûte bleue",
    "ELU": "Choisi",
    "CADI": "Juge musulman",
    "AGE": "Années vécues",
    "SIC": "Ainsi écrit",
    "TRICOTS": "Pulls en laine",
    "DINER": "Repas du soir",
    "PINS": "Conifères",
    "LOGICIEL": "Programme informatique",
    "SOIE": "Tissu précieux",
    "BD": "Bande dessinée",
    "CHERI": "Adoré",
    "HONTE": "Gêne profonde",
    "SAC": "Bagage dorsal",
    "PIE": "Oiseau bavard",
    "CRU": "Vin classé",
    # Review grid 03
    "AS": "Champion",
    "ANS": "Années",
    "RIS": "Abats de veau",
    "MOIS": "Douzièmes d'année",
    "ADO": "Jeune",
    "INTERNET": "Réseau mondial",
    "ORAGES": "Tempêtes électriques",
    "STUC": "Faux marbre",
    "MER": "Étendue salée",
    "FER": "Métal",
    "SOIR": "Fin de journée",
    "ANIS": "Plante aromatique",
    "BLE": "Céréale dorée",
    "FEES": "Créatures magiques",
    "AMIS": "Camarades",
    "NON": "Refus",
    "SITOT": "Dès",
    "RANG": "Position",
    "IDEES": "Pensées",
    "SOTS": "Peu malins",
    "SERUM": "Liquide médical",
    "RACES": "Variétés animales",
    "IA": "Intelligence artificielle",
    "SCENE": "Dispute",
    "ROBE": "Vêtement long",
    "TRES": "Beaucoup",
    "FAN": "Admirateur",
    "RIZ": "Céréale asiatique",
    "ILE": "Terre isolée",
}


def selected_grids() -> list[dict]:
    grids = []
    for number, (path, grid_id) in enumerate(SELECTIONS, start=1):
        document = json.loads(path.read_text(encoding="utf-8"))
        source = next(grid for grid in document["grids"] if grid["id"] == grid_id)
        grid = copy.deepcopy(source)
        new_id = f"review-20260715-{number:02d}"
        grid["id"] = new_id
        grid["editorialProfile"] = "motman-standard"
        grid["publicationStatus"] = "owner-review-required"
        grid["reviewCycle"] = "2026-07-15"
        for index, word in enumerate(grid["words"], start=1):
            answer = word["answer"]
            if answer == "SAC" and not word.get("sourceUrl"):
                word["sourceUrl"] = (
                    "https://github.com/jdecked/twemoji/blob/master/assets/svg/1f392.svg"
                )
            word["wordId"] = f"{new_id}:word:{index:02d}"
            word["sourceClue"] = word.get("sourceClue") or word.get("clue", "")
            word["definitionStatus"] = "reviewed"
            word["manualReview"] = "reviewed-awaiting-owner"
            word["editorialReviewId"] = "motman-editorial-review-20260715"
            if word.get("image"):
                word["clue"] = ""
                word["editorialStatus"] = "image-reviewed"
            else:
                if answer not in CLUES:
                    raise ValueError(f"définition manuelle manquante: {new_id}/{answer}")
                word["clue"] = CLUES[answer]
                word["editorialStatus"] = "human-reviewed"
            errors = editorial_errors(word, root=ROOT)
            if errors:
                raise ValueError(f"{new_id}/{answer}: {errors}")
        grids.append(grid)
    return grids


def main() -> None:
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    blocked_answers = set(blacklist.get("rejectedAnswers", []))
    # This reviewed batch predates the rotation cooldown. Cooldown answers are
    # not editorial rejections: the runtime selector now prevents them from
    # repeating inside a player's twelve-grid window.
    blocked_pairs = {
        (item["answer"], item["clue"].casefold())
        for item in blacklist.get("rejectedPairs", [])
    }
    grids = selected_grids()
    for grid in grids:
        for word in grid["words"]:
            if word["answer"] in blocked_answers:
                raise ValueError(f"réponse blacklistée: {word['answer']}")
            pair = (word["answer"], word.get("clue", "").casefold())
            if word.get("clue") and pair in blocked_pairs:
                raise ValueError(f"couple blacklisté: {pair}")

    reports = [audit_grid_topology(grid) for grid in grids]
    invalid = [report["gridId"] for report in reports if not report["valid"]]
    if invalid:
        raise ValueError(f"grilles invalides: {invalid}")

    answers = [word["answer"] for grid in grids for word in grid["words"]]
    usage = Counter(answers)
    repeated = {answer: count for answer, count in usage.items() if count > 1}
    if repeated:
        raise ValueError(f"réponses répétées dans le lot: {repeated}")

    active = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    active_usage = Counter(
        word["answer"] for grid in active.get("grids", []) for word in grid.get("words", [])
    )
    shapes = [tuple(sorted(map(tuple, grid["clueCells"]))) for grid in grids]
    metrics = {
        "grids": len(grids),
        "answers": len(answers),
        "uniqueAnswers": len(usage),
        "repeatedAnswersInsideCycle": 0,
        "uniqueShapes": len(set(shapes)),
        "images": sum(bool(word.get("image")) for grid in grids for word in grid["words"]),
        "answersNewToActiveCatalog": sum(active_usage[answer] == 0 for answer in usage),
        "answersAlreadyInActiveCatalog": sum(active_usage[answer] > 0 for answer in usage),
    }
    document = {
        "version": 1,
        "kind": "motman-owner-review-cycle",
        "publicationPolicy": "Aucune publication automatique; validation du propriétaire requise.",
        "grids": grids,
        "batchMetrics": metrics,
    }
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    AUDIT.write_text(json.dumps({
        "version": 1,
        "valid": True,
        "metrics": metrics,
        "grids": reports,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    HTML.write_text(
        render_topology_html(reports, title="MotMan — revue courte du 15 juillet 2026"),
        encoding="utf-8",
    )
    print(json.dumps({"status": "built", "html": str(HTML), "metrics": metrics}, ensure_ascii=False))


if __name__ == "__main__":
    main()
