"""Build the five owner-approved corpus-aware silhouettes for human review.

The shapes and answer lists are frozen deliberately.  Definitions are edited
one by one below; this script never invokes an automatic clue generator and
never modifies the active catalog.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import generate_grid_catalog as generator
from editorial_quality import editorial_errors, grid_semantic_errors
from grid_topology import audit_grid_topology, render_topology_html
from render_corpus_aware_shape_pilot import load_unique_shapes


ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "src/data/grid-generation-handcrafted/corpus-aware-five.review.json"
AUDIT = ROOT / "output/quality/corpus-aware-five-audit.json"
HTML = ROOT / "output/quality/corpus-aware-five-review.html"
QUALITY_POOL = ROOT / "output/quality/corpus-aware-quality-pool.json"

# These fingerprints are the five silhouettes the owner approved visually on
# 2026-07-15.  A source file change must never replace one silently.
EXPECTED_SHAPE_FINGERPRINTS = (
    "0873030fda86222e",
    "dfcfc055ca59e9d4",
    "7b1f724af7b4083c",
    "fd6198e93a2ca37c",
    "3d1057aa45e23753",
)

ANSWERS = (
    """AH TASSE ABEILLES PERSUADE ATRE PIE NIE JETS RARE ABUSEUR DISPARU
    ROCHEUSE TAPANT ABETI SERRE SISE ELU USEES LAPEREAU EDITEURS JASPE
    RUSH AS ADO BIC RUE""".split(),
    """AN ODE PUB PECORINO ECUREUIL ROMAN ARETES OTAGE AMITIES GARENNE
    DETESTEE OPERAS DECOR ECUME PIU UNIS BOL ORATOIRE RENETTES SAINT
    PESEE GENE LU AGE MAT""".split(),
    """MI ESTER DAIM TRI ACROMION TARSE AVINES LEVITES ILLETTRE FEU OEIL
    SEMEUSES EDAM SAC TIR EMOTIVE MINE TIRETTES ROSSERIE MANITOU PI ALLEE
    VELUM SELS IFS""".split(),
    """FA BOA RAT AIREDALE VERDELET OISEAU KITS RAPE SIBILANT PLACENTA
    ALTESSES BAVE OIE ARROI RALE ALEA TETUE EDITRICE DESSALES SI KRILL
    PANS ENTE SPA BAT TAS""".split(),
    """IA IFTAR MORS COU BUISSONS DIONEE PIEUVRE GRUE CINECLUB AME ISSU
    POTELEES IMBU FOU TRIDI ASSIEGE MUSEE CONVULSE ONEREUSE SOURCIL UT
    PRIMO CAP NET BUS""".split(),
)

# Every textual clue is manually edited.  Image answers are intentionally
# absent: a valid Twemoji record replaces their text in the clue cell.
CLUES = {
    # Grid 1
    "AH": "Cri de surprise",
    "PERSUADE": "Convainc",
    "ATRE": "Foyer de cheminée",
    "PIE": "Oiseau bavard",
    "NIE": "Refuse d'admettre",
    "JETS": "Lancers",
    "RARE": "Peu commun",
    "ABUSEUR": "Trompeur",
    "DISPARU": "Introuvable",
    "ROCHEUSE": "Pleine de rochers",
    "TAPANT": "Très voyant",
    "ABETI": "Rendu stupide",
    "SERRE": "Abri vitré",
    "SISE": "Située",
    "ELU": "Choisi par vote",
    "USEES": "Très fatiguées",
    "LAPEREAU": "Jeune lapin",
    "EDITEURS": "Publient des livres",
    "JASPE": "Pierre colorée",
    "RUSH": "Prise de tournage",
    "AS": "Champion",
    "ADO": "Jeune personne",
    "BIC": "Stylo jetable",
    "RUE": "Voie urbaine",
    # Grid 2
    "AN": "Douze mois",
    "ODE": "Poème lyrique",
    "PUB": "Réclame familière",
    "PECORINO": "Fromage de brebis",
    "ECUREUIL": "Rongeur roux",
    "ROMAN": "Long récit",
    "ARETES": "Os de poisson",
    "OTAGE": "Prisonnier retenu",
    "AMITIES": "Liens affectueux",
    "GARENNE": "Refuge de lapins",
    "DETESTEE": "Profondément haïe",
    "OPERAS": "Drames chantés",
    "DECOR": "Cadre de scène",
    "ECUME": "Mousse marine",
    "PIU": "Plus, en musique",
    "UNIS": "Rassemblés",
    "ORATOIRE": "Lieu de prière",
    "RENETTES": "Pommes anciennes",
    "SAINT": "Homme canonisé",
    "PESEE": "Mesure du poids",
    "GENE": "Embarrasse",
    "LU": "Déjà parcouru",
    "AGE": "Années vécues",
    "MAT": "Roi piégé",
    # Grid 3
    "MI": "Troisième note",
    "ESTER": "Saisir la justice",
    "DAIM": "Cervidé tacheté",
    "TRI": "Classement",
    "ACROMION": "Saillie scapulaire",
    "TARSE": "Arrière du pied",
    "AVINES": "Ivres de vin",
    "LEVITES": "Prêtres hébreux",
    "ILLETTRE": "Sans savoir lire",
    "SEMEUSES": "Répandent des graines",
    "EDAM": "Fromage hollandais",
    "SAC": "Contenant souple",
    "TIR": "Action de tirer",
    "EMOTIVE": "Très sensible",
    "MINE": "Gisement exploité",
    "TIRETTES": "Petites poignées",
    "ROSSERIE": "Méchanceté",
    "MANITOU": "Esprit amérindien",
    "PI": "Lettre grecque",
    "ALLEE": "Chemin bordé",
    "VELUM": "Voile anatomique",
    "SELS": "Cristaux minéraux",
    "IFS": "Conifères toxiques",
    # Grid 4
    "FA": "Quatrième note",
    "BOA": "Grand serpent",
    "RAT": "Petit rongeur",
    "AIREDALE": "Chien anglais",
    "VERDELET": "Un peu vert",
    "KITS": "Ensembles prêts",
    "RAPE": "Ustensile denté",
    "SIBILANT": "Comme un sifflement",
    "PLACENTA": "Organe de grossesse",
    "ALTESSES": "Personnes royales",
    "BAVE": "Salive coulante",
    "OIE": "Palmipède domestique",
    "ARROI": "Éclat solennel",
    "RALE": "Cri rauque",
    "ALEA": "Hasard",
    "TETUE": "Très obstinée",
    "EDITRICE": "Professionnelle du livre",
    "DESSALES": "Retire le sel",
    "SI": "À condition",
    "KRILL": "Petits crustacés",
    "PANS": "Parties de mur",
    "ENTE": "Greffe végétale",
    "SPA": "Centre de soins",
    "BAT": "Frappe",
    "TAS": "Amas",
    # Grid 5
    "IA": "Intelligence artificielle",
    "IFTAR": "Repas du ramadan",
    "MORS": "Pièce de bride",
    "COU": "Sous la tête",
    "BUISSONS": "Petits arbustes",
    "DIONEE": "Plante carnivore",
    "GRUE": "Engin de chantier",
    "CINECLUB": "Séances de cinéma",
    "AME": "Esprit intérieur",
    "ISSU": "Provenant de",
    "POTELEES": "Un peu rondes",
    "IMBU": "Plein de soi",
    "FOU": "Pas raisonnable",
    "TRIDI": "Troisième jour républicain",
    "ASSIEGE": "Encercle une ville",
    "MUSEE": "Lieu d'exposition",
    "CONVULSE": "Secoue violemment",
    "ONEREUSE": "Qui coûte cher",
    "SOURCIL": "Arcade de poils",
    "UT": "Ancien do",
    "PRIMO": "En premier lieu",
    "CAP": "Pointe de terre",
    "NET": "Sans flou",
}

IMAGE_CLUES = {
    "TASSE": ("tasse.svg", "Tasse"),
    "ABEILLES": ("abeille.svg", "Abeilles"),
    "BOL": ("bol.svg", "Bol"),
    "FEU": ("feu.svg", "Feu"),
    "OEIL": ("oeil.svg", "Œil"),
    "OISEAU": ("oiseau.svg", "Oiseau"),
    "PIEUVRE": ("pieuvre.svg", "Pieuvre"),
    "BUS": ("bus.svg", "Bus"),
}


def shape_fingerprint(grid: dict) -> str:
    payload = json.dumps(sorted(grid["clueCells"]), separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def templates() -> list[dict]:
    # Once the owner-approved staging exists, its shapes are the canonical
    # source. Generated candidate pools are mutable diagnostics and must not
    # make this historical review batch fail or silently change shape later.
    if STAGING.exists():
        frozen = json.loads(STAGING.read_text(encoding="utf-8")).get("grids", [])
        frozen_fingerprints = tuple(shape_fingerprint(grid) for grid in frozen)
        if frozen_fingerprints == EXPECTED_SHAPE_FINGERPRINTS:
            return frozen

    pilot = load_unique_shapes()
    quality = json.loads(QUALITY_POOL.read_text(encoding="utf-8"))
    quality_grid = next(
        grid for grid in quality["grids"] if grid["id"] == "quality-pool-010"
    )
    selected = [pilot[0], pilot[1], quality_grid, pilot[3], pilot[4]]
    fingerprints = tuple(shape_fingerprint(grid) for grid in selected)
    if fingerprints != EXPECTED_SHAPE_FINGERPRINTS:
        raise ValueError(
            "les silhouettes sources ont changé; refus de remplacer celles validées "
            f"({fingerprints!r})"
        )
    return selected


def source_index() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for entry in generator.load_entries():
        answer = entry["answer"]
        previous = result.get(answer)
        if previous is None or (
            previous.get("sourceType") != "crossword"
            and entry.get("sourceType") == "crossword"
        ):
            result[answer] = entry
    lexical = json.loads(
        (ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8")
    )["entries"]
    for entry in lexical:
        result.setdefault(entry["answer"], {
            **entry,
            "clue": "",
            "sourceClue": "",
            "sourceId": "lexique-3.83",
            "sourceUrl": "http://www.lexique.org/databases/Lexique383/Lexique383.tsv",
            "sourceType": "lexical-attestation",
            "editorialStatus": "manual-clue-required",
            "conceptGroup": entry["answer"],
            "semanticConflicts": [],
        })
    return result


def image_record(filename: str, alt: str) -> dict:
    return {
        "asset": f"/assets/clues/twemoji/{filename}",
        "alt": alt,
        "source": "Twemoji",
        "license": "CC BY 4.0",
    }


def build_grids() -> list[dict]:
    sources = source_index()
    grids = []
    for grid_number, (template, answers) in enumerate(zip(templates(), ANSWERS), 1):
        if len(template["words"]) != len(answers):
            raise ValueError(f"nombre de réponses incohérent pour la grille {grid_number}")
        grid_id = f"corpus-aware-review-{grid_number:02d}"
        words = []
        for word_number, (slot, answer) in enumerate(
            zip(template["words"], answers), 1
        ):
            if len(slot["cells"]) != len(answer):
                raise ValueError(
                    f"longueur incohérente: grille {grid_number}, {answer}, "
                    f"{len(slot['cells'])} cases"
                )
            source = copy.deepcopy(sources.get(answer, {}))
            if not source:
                raise ValueError(f"réponse sans attestation lexicale: {answer}")
            image_spec = IMAGE_CLUES.get(answer)
            clue = "" if image_spec else CLUES.get(answer)
            if clue is None:
                raise ValueError(f"définition manuelle manquante: {answer}")
            word = {
                "wordId": f"{grid_id}:word:{word_number:02d}",
                "answer": answer,
                "clue": clue,
                "sourceClue": source.get("sourceClue") or source.get("clue", ""),
                "direction": slot["direction"],
                "arrow": slot["arrow"],
                "clueCell": slot["clueCell"],
                "cells": slot["cells"],
                "sourceId": source.get("sourceId", "lexique-3.83"),
                "sourceUrl": source.get("sourceUrl", ""),
                "sourceType": source.get("sourceType", "lexical-attestation"),
                "sourcePuzzleId": source.get("sourcePuzzleId"),
                "sourcePublishedOn": source.get("sourcePublishedOn"),
                "sourceFrequency": source.get(
                    "sourceFrequency", source.get("frequency", 0)
                ),
                "partOfSpeech": source.get("partOfSpeech"),
                "difficulty": source.get("difficulty", "unrated"),
                "conceptGroup": source.get("conceptGroup") or answer,
                "semanticConflicts": source.get("semanticConflicts", []),
                "editorialStatus": "image-reviewed" if image_spec else "human-reviewed",
                "definitionStatus": "manually-edited",
                "manualReview": "reviewed-awaiting-owner",
                "editorialReviewId": "motman-corpus-aware-five-20260715",
            }
            if image_spec:
                word["image"] = image_record(*image_spec)
            word = {key: value for key, value in word.items() if value is not None}
            errors = editorial_errors(word, root=ROOT)
            if errors:
                raise ValueError(f"{grid_id}/{answer}: {errors}")
            words.append(word)
        semantic_errors = grid_semantic_errors(words)
        if semantic_errors:
            raise ValueError(f"doublons sémantiques dans {grid_id}: {semantic_errors}")
        grids.append({
            "id": grid_id,
            "columns": 9,
            "rows": 10,
            "editorialProfile": "motman-standard-owner-calibrated",
            "publicationStatus": "owner-review-required",
            "reviewCycle": "2026-07-15",
            "shapeFingerprint": EXPECTED_SHAPE_FINGERPRINTS[grid_number - 1],
            "clueCells": copy.deepcopy(template["clueCells"]),
            "words": words,
        })
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
    grids = build_grids()
    assert_blacklist(grids)

    reports = [audit_grid_topology(grid) for grid in grids]
    invalid = {
        report["gridId"]: report["errors"]
        for report in reports if not report["valid"]
    }
    if invalid:
        raise ValueError(f"grilles invalides: {invalid}")

    answers = [word["answer"] for grid in grids for word in grid["words"]]
    usage = Counter(answers)
    repeated = {answer: count for answer, count in usage.items() if count > 1}
    if repeated:
        raise ValueError(f"réponses répétées dans le lot: {repeated}")
    answer_set = set(answers)
    inflections = sorted(
        (answer, f"{answer}S")
        for answer in answer_set
        if len(answer) >= 3 and f"{answer}S" in answer_set
    )
    if inflections:
        raise ValueError(f"singuliers/pluriels répétés dans le lot: {inflections}")

    active = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    active_usage = Counter(
        word["answer"]
        for grid in active.get("grids", [])
        for word in grid.get("words", [])
    )
    length_profile = Counter(map(len, answers))
    metrics = {
        "grids": len(grids),
        "answers": len(answers),
        "uniqueAnswers": len(usage),
        "repeatedAnswersInsideBatch": 0,
        "singularPluralFamiliesInsideBatch": 0,
        "uniqueShapes": len({grid["shapeFingerprint"] for grid in grids}),
        "images": sum(
            bool(word.get("image")) for grid in grids for word in grid["words"]
        ),
        "answersNewToActiveCatalog": sum(active_usage[answer] == 0 for answer in usage),
        "answersAlreadyInActiveCatalog": sum(active_usage[answer] > 0 for answer in usage),
        "answerLengthProfile": dict(sorted(length_profile.items())),
    }
    document = {
        "version": 1,
        "kind": "motman-corpus-aware-five-owner-review",
        "publicationPolicy": (
            "Aucune publication automatique; validation du propriétaire requise."
        ),
        "batchMetrics": metrics,
        "grids": grids,
    }
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    AUDIT.write_text(json.dumps({
        "version": 1,
        "valid": True,
        "metrics": metrics,
        "grids": reports,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    HTML.write_text(
        render_topology_html(
            reports,
            title="MotMan — cinq grilles remplies à relire",
        ),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "built",
        "html": str(HTML),
        "staging": str(STAGING),
        "metrics": metrics,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
