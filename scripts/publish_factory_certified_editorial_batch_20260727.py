"""Editorialize and publish the certified Grid Factory handoff dated 2026-07-27.

The source handoff is words-only.  This module verifies both its physical hash
and its canonical payload digest before adding manually written MotMan clues.
One of the five certified grids is deliberately withheld because it shares
sixteen of seventeen answers with another grid in the same handoff.

Run without ``--publish`` to regenerate the staging review.  ``--publish`` is
idempotent and atomically appends the four accepted grids to the local MotMan
catalog before the usual runtime/Supabase publication steps.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402


SOURCE_EXPORT = Path(
    r"C:\Users\peete\AppData\Local\MotManLexiconStudio\exports"
    r"\motman-certified-grids-for-editorialization.json"
)
EXPECTED_FILE_SHA256 = (
    "ea100ce00456e0c703be1fda4d9cbd9c64d1bd7a6b82ce2e6b61ebedef5a5d1a"
)
EXPECTED_PAYLOAD_SHA256 = (
    "2e5c506e67c90e499a3e4a63529bf3da85d39a19e40da3124d959611d1facadb"
)
EXPECTED_SCHEMA = "motman-grid-certified-editorial-handoff"
EXPECTED_VERSION = 1
TARGET_CATALOG_VERSION = 20

CATALOG_PATH = ROOT / "src/data/grid.catalog.json"
SNAPSHOT_PATH = (
    ROOT
    / "src/data/grid-generation-handcrafted"
    / "factory-certified-editorial-20260727.json"
)
OUTPUT_DIR = ROOT / "output/quality/factory-certified-editorial-20260727"
STAGING_PATH = OUTPUT_DIR / "staging.json"
AUDIT_PATH = OUTPUT_DIR / "audit.json"
REVIEW_PATH = OUTPUT_DIR / "review.html"

ACCEPTED_CANDIDATES = (
    "0092d1d2-c124-4493-bca6-37703e8764d0",
    "081c89e3-c392-4258-a0e0-cffec95b2f43",
    "80dfab8e-f16a-461b-aee7-030e8ab0702a",
    "5354b8e2-bf35-45ce-9cbd-d96f1bbf7012",
)
WITHHELD_CANDIDATE = "ff14f81e-946d-48f4-a545-d80cc7dbd47e"
WITHHELD_AGAINST = "081c89e3-c392-4258-a0e0-cffec95b2f43"

SOURCE_ID = "motman-factory-certified-20260727"
SOURCE_URL = "internal://motman/editorial/factory-certified-20260727"


def text(clue: str, *, style: str = "direct") -> dict[str, Any]:
    return {"clue": clue, "clueStyle": style}


def picture(asset: str, alt: str, concept: str, *, custom: bool = False) -> dict[str, Any]:
    return {
        "clue": "",
        "clueStyle": "image",
        "image": {
            "asset": asset,
            "alt": alt,
            "concept": concept,
            "source": "MotMan original" if custom else "Twemoji 15.1",
            "license": "MotMan original" if custom else "CC-BY 4.0",
            "sourceAsset": asset,
        },
    }


# Every clue below is original, explicit and manually reviewed for this batch.
# Image clues intentionally keep ``clue`` empty: the licensed image is the clue.
EDITORIAL: dict[str, dict[str, dict[str, Any]]] = {
    "0092d1d2-c124-4493-bca6-37703e8764d0": {
        "REFORME": text("Changement profond"),
        "EROSION": text("Usure progressive"),
        "SMS": picture("/assets/clues/twemoji/sms.svg", "Message sur téléphone", "SMS"),
        "TITRE": text("Intitulé d’œuvre"),
        "ETE": picture("/assets/clues/twemoji/soleil.svg", "Soleil estival", "Été"),
        "SERRURE": text("Mécanisme de porte"),
        "RESTES": text("Ce qui demeure"),
        "ERMITE": text("Solitaire retiré"),
        "FOSTER": text("Jodie, actrice oscarisée", style="clever"),
        "OS": picture("/assets/clues/twemoji/os.svg", "Os du squelette", "Os"),
        "DIT": text("Parole rapportée"),
        "AVE": text("Prière latine"),
        "RIDEAU": text("Cache la scène"),
        "MOI": text("Pronom personnel"),
        "VR": text("Réalité virtuelle"),
        "ENTREE": picture("/assets/clues/twemoji/porte.svg", "Porte d’entrée", "Entrée"),
    },
    "081c89e3-c392-4258-a0e0-cffec95b2f43": {
        "GRILLON": picture("/assets/clues/twemoji/insecte.svg", "Petit insecte chanteur", "Grillon"),
        "HEROINE": text("Personnage principal"),
        "ECOLE": picture("/assets/clues/twemoji/ecole.svg", "Bâtiment scolaire", "École"),
        "TON": text("Manière de parler"),
        "TRIO": text("Groupe de trois"),
        "ODE": text("Poème lyrique"),
        "GHETTO": text("Quartier ségrégué"),
        "RECORD": picture("/assets/clues/twemoji/medaille.svg", "Performance record", "Record"),
        "IRONIE": text("Moquerie implicite"),
        "LOL": text("Rire sur Internet"),
        "NOM": text("Mot qui désigne"),
        "VER": picture("/assets/clues/twemoji/ver.svg", "Petit animal rampant", "Ver"),
        "LIEN": text("Ce qui unit"),
        "IA": text("Intelligence artificielle"),
        "ON": text("Pronom indéfini"),
        "OIE": picture("/assets/clues/twemoji/oie.svg", "Oiseau de basse-cour", "Oie"),
        "NEYMAR": text("Brésilien ex-PSG", style="clever"),
    },
    "80dfab8e-f16a-461b-aee7-030e8ab0702a": {
        "MASCARA": text("Maquillage des cils"),
        "ABOULER": text("Donner familièrement"),
        "BOUILLE": picture("/assets/clues/twemoji/visage.svg", "Visage familier", "Bouille"),
        "ON": text("Pronom indéfini"),
        "UN": text("Article indéfini"),
        "LEGERES": text("Peu pesantes"),
        "MABOUL": text("Complètement fou"),
        "ABONNE": text("Client régulier"),
        "SOU": picture("/assets/clues/twemoji/argent.svg", "Ancienne petite monnaie", "Sou"),
        "SIEN": text("Possessif masculin"),
        "SEVE": picture("/assets/clues/twemoji/arbre.svg", "Liquide de l’arbre", "Sève"),
        "CUISSE": text("Partie de jambe"),
        "ALLIER": text("Associer étroitement"),
        "RELEVE": text("Nouvelle génération"),
        "ARENES": picture(
            "/assets/clues/custom/colisee.svg",
            "Arènes antiques",
            "Arènes",
            custom=True,
        ),
    },
    "5354b8e2-bf35-45ce-9cbd-d96f1bbf7012": {
        "PATINER": text("Glisser sur glace"),
        "AVOCATE": text("Juriste féminine"),
        "RELIURE": text("Habillage du livre"),
        "DRE": text("Producteur de Compton", style="clever"),
        "OS": picture("/assets/clues/twemoji/os.svg", "Os du squelette", "Os"),
        "NET": text("Sans aucune saleté"),
        "PARDON": text("Demande d’excuse"),
        "AVERSE": picture("/assets/clues/twemoji/pluie.svg", "Forte pluie soudaine", "Averse"),
        "TOLE": text("Feuille de métal"),
        "OEIL": picture("/assets/clues/twemoji/oeil.svg", "Organe de la vue", "Œil"),
        "ICI": text("À cet endroit"),
        "SOL": text("Sous nos pieds"),
        "ETE": picture("/assets/clues/twemoji/soleil.svg", "Soleil estival", "Été"),
        "NAUSEE": text("Envie de vomir"),
        "ETROIT": text("Manquant de largeur"),
        "REELLE": text("Qui existe vraiment"),
    },
}


PROPER_NAME_REVIEWS = {
    "FOSTER": {
        "status": "human-reviewed-distinctive",
        "entityType": "personne",
        "clueUniquenessChecked": True,
        "distinctiveTokens": ["Jodie", "oscarisée"],
        "decision": "accepted-known-proper-name",
    },
    "NEYMAR": {
        "status": "human-reviewed-distinctive",
        "entityType": "personne",
        "clueUniquenessChecked": True,
        "distinctiveTokens": ["PSG", "Brésilien"],
        "decision": "accepted-known-proper-name",
    },
    "DRE": {
        "status": "human-reviewed-distinctive",
        "entityType": "personne",
        "clueUniquenessChecked": True,
        "distinctiveTokens": ["Compton", "Producteur"],
        "decision": "accepted-stage-name",
    },
}

LEXICAL_EXCEPTIONS = {
    "FOSTER": {
        "status": "human-reviewed-exception",
        "reason": "Nom propre mondialement connu, absent du lexique principal.",
        "acceptedAs": "Jodie Foster",
    },
    "SIEN": {
        "status": "human-reviewed-exception",
        "reason": "Pronom possessif masculin autonome malgré son classement technique en quarantaine.",
        "acceptedAs": "pronom possessif",
    },
    "LEGERES": {
        "status": "human-reviewed-inflection",
        "reason": "Adjectif féminin pluriel autonome et défini sans contexte verbal.",
        "acceptedAs": "adjectif qualificatif",
    },
    "REELLE": {
        "status": "human-reviewed-inflection",
        "reason": "Adjectif féminin singulier autonome et défini sans contexte verbal.",
        "acceptedAs": "adjectif qualificatif",
    },
}


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def local_asset_data_uri(asset: str) -> str:
    if not asset.startswith("/assets/clues/"):
        raise ValueError(f"Indice-image hors bibliothèque MotMan: {asset}")
    path = (ROOT / "public" / asset.lstrip("/")).resolve()
    clue_root = (ROOT / "public/assets/clues").resolve()
    if not path.is_relative_to(clue_root) or not path.is_file():
        raise ValueError(f"Indice-image introuvable: {asset}")
    mime = {".svg": "image/svg+xml", ".png": "image/png"}.get(path.suffix.lower())
    if mime is None:
        raise ValueError(f"Format d’indice-image non pris en charge: {asset}")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def verify_handoff(path: Path = SOURCE_EXPORT) -> dict[str, Any]:
    raw = path.read_bytes()
    file_digest = hashlib.sha256(raw).hexdigest()
    if file_digest != EXPECTED_FILE_SHA256:
        raise ValueError(
            f"SHA-256 physique inattendu: {file_digest}; attendu {EXPECTED_FILE_SHA256}"
        )
    document = json.loads(raw.decode("utf-8"))
    if document.get("schema") != EXPECTED_SCHEMA or document.get("version") != EXPECTED_VERSION:
        raise ValueError("Schéma de handoff Grid Factory non pris en charge")
    manifest = document.get("manifest")
    if not isinstance(manifest, dict):
        raise ValueError("Manifeste absent")
    stored_payload_digest = manifest.get("payloadSha256")
    unsigned = copy.deepcopy(document)
    unsigned["manifest"].pop("payloadSha256", None)
    computed_payload_digest = canonical_digest(unsigned)
    if stored_payload_digest != EXPECTED_PAYLOAD_SHA256:
        raise ValueError("Le manifeste ne porte pas le digest payload attendu")
    if computed_payload_digest != EXPECTED_PAYLOAD_SHA256:
        raise ValueError(
            f"Digest payload invalide: {computed_payload_digest}; attendu {EXPECTED_PAYLOAD_SHA256}"
        )
    grids = document.get("grids")
    if not isinstance(grids, list) or len(grids) != 5:
        raise ValueError("Le handoff doit contenir exactement cinq grilles certifiées")
    editorial_paths: list[str] = []

    def walk(value: object, prefix: str = "$") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child = f"{prefix}.{key}"
                if str(key).casefold() in {"clue", "definition", "image", "images"}:
                    editorial_paths.append(child)
                walk(item, child)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{prefix}[{index}]")

    walk(document)
    if editorial_paths:
        raise ValueError(f"Le handoff words-only contient des données éditoriales: {editorial_paths[:3]}")
    return document


def answer_set(grid: dict[str, Any]) -> set[str]:
    return {str(item["normalized"]).upper() for item in grid["answers"]}


def withheld_report(document: dict[str, Any]) -> dict[str, Any]:
    by_candidate = {grid["candidateId"]: grid for grid in document["grids"]}
    withheld = by_candidate[WITHHELD_CANDIDATE]
    kept = by_candidate[WITHHELD_AGAINST]
    a = answer_set(withheld)
    b = answer_set(kept)
    intersection = sorted(a & b)
    union = a | b
    similarity = len(intersection) / max(1, len(union))
    if len(intersection) != 16 or similarity < 0.88:
        raise ValueError("Le motif de blocage de la cinquième grille a changé")
    return {
        "candidateId": WITHHELD_CANDIDATE,
        "proposedGridId": withheld["proposedGridId"],
        "status": "withheld",
        "reason": "near-duplicate-within-certified-batch",
        "comparedWithCandidateId": WITHHELD_AGAINST,
        "sharedAnswers": intersection,
        "sharedAnswerCount": len(intersection),
        "jaccardSimilarity": round(similarity, 6),
        "decision": (
            "Non publiée : seize réponses sur dix-sept sont identiques à la grille "
            f"{kept['proposedGridId']}."
        ),
    }


def build_grid(source_grid: dict[str, Any]) -> dict[str, Any]:
    candidate_id = source_grid["candidateId"]
    grid_id = source_grid["proposedGridId"]
    editorial_by_answer = EDITORIAL.get(candidate_id)
    if editorial_by_answer is None:
        raise ValueError(f"Aucune édition manuelle pour {candidate_id}")
    source_answers = {
        str(item["normalized"]).upper(): item for item in source_grid["answers"]
    }
    if set(source_answers) != set(editorial_by_answer):
        missing = sorted(set(source_answers) - set(editorial_by_answer))
        extra = sorted(set(editorial_by_answer) - set(source_answers))
        raise ValueError(f"Couverture éditoriale incomplète pour {candidate_id}: missing={missing}, extra={extra}")

    words: list[dict[str, Any]] = []
    for source in source_grid["answers"]:
        answer = str(source["normalized"]).upper()
        edited = copy.deepcopy(editorial_by_answer[answer])
        image = edited.get("image")
        is_image = image is not None
        if is_image:
            image["asset"] = local_asset_data_uri(image["sourceAsset"])
        word: dict[str, Any] = {
            "wordId": source["proposedWordId"],
            "answer": answer,
            "clue": edited["clue"],
            "sourceClue": edited["clue"] or image["alt"],
            "definitionStatus": "image-review" if is_image else "manually-reviewed",
            "editorialStatus": "human-reviewed",
            "sourceType": "image-concept" if is_image else "editorial-original",
            "sourceId": SOURCE_ID,
            "sourceUrl": SOURCE_URL,
            "license": image["license"] if is_image else "MotMan original",
            "conceptGroup": answer,
            "semanticConflicts": [],
            "direction": source["direction"],
            "arrow": source["arrow"],
            "clueCell": source["clueCell"],
            "cells": source["cells"],
            "clueStyle": edited["clueStyle"],
            "familiarityScore": float(source.get("familiarity") or 0),
            "familiarityBand": (
                "thoughtful"
                if source.get("qualityTier") == "reserve"
                else "common"
            ),
            "partOfSpeech": source.get("partOfSpeech") or "unknown",
            "formType": source.get("formType") or "unknown",
            "languageStatus": (
                "known-proper-name" if answer in PROPER_NAME_REVIEWS else "standard-french"
            ),
            "culturalStatus": (
                "current-common"
                if answer in {"SMS", "VR", "IA", "LOL", "NEYMAR"}
                else "timeless"
            ),
            "editorialReview": {
                "status": "human-reviewed",
                "meaningChecked": True,
                "clueAnswerFit": True,
                "allAudience": True,
                "mobileReadable": True,
                "imageRecognizable": bool(is_image),
                "reviewDate": "2026-07-27",
            },
            "factoryMetadata": {
                "qualityTier": source.get("qualityTier"),
                "solverPenalty": source.get("solverPenalty"),
                "familiarity": source.get("familiarity"),
                "register": source.get("register"),
                "domain": source.get("domain"),
                "pendingPoolId": source.get("pendingPoolId"),
            },
        }
        if is_image:
            word["image"] = image
            word["imageStatus"] = "reviewed-recognizable-licensed"
        if answer in PROPER_NAME_REVIEWS:
            word["properNameReview"] = copy.deepcopy(PROPER_NAME_REVIEWS[answer])
        if answer in LEXICAL_EXCEPTIONS:
            word["lexicalExceptionReview"] = copy.deepcopy(LEXICAL_EXCEPTIONS[answer])
        words.append(word)

    image_count = sum("image" in word for word in words)
    if not 4 <= image_count <= 6:
        raise ValueError(f"{grid_id}: {image_count} indices-images au lieu de 4 à 6")

    grid = {
        "id": grid_id,
        "columns": 7,
        "rows": 8,
        "sourceReviewId": source_grid["candidateId"],
        "sourceShapeId": source_grid["shapeId"],
        "audience": "16-45",
        "clueCells": source_grid["clueCells"],
        "words": words,
        "imageCount": image_count,
        "publicationStatus": "owner-certified-editorial-reviewed",
        "humanReview": {
            "status": "human-reviewed",
            "reviewDate": "2026-07-27",
            "sourceFileSha256": EXPECTED_FILE_SHA256,
            "sourcePayloadSha256": EXPECTED_PAYLOAD_SHA256,
            "lexicalExceptions": sorted(
                answer for answer in source_answers if answer in LEXICAL_EXCEPTIONS
            ),
            "properNames": sorted(
                answer for answer in source_answers if answer in PROPER_NAME_REVIEWS
            ),
        },
        "provenance": {
            "source": str(SOURCE_EXPORT),
            "candidateId": source_grid["candidateId"],
            "campaignId": source_grid["campaignId"],
            "certifiedAt": source_grid["certifiedAt"],
            "factoryDigests": source_grid["digests"],
        },
        "reviewSummary": {
            "answers": len(words),
            "images": image_count,
            "manualTextClues": len(words) - image_count,
            "properNamesReviewed": sum(
                word["answer"] in PROPER_NAME_REVIEWS for word in words
            ),
            "lexicalExceptionsReviewed": sum(
                word["answer"] in LEXICAL_EXCEPTIONS for word in words
            ),
        },
        "editorialProfile": "motman-factory-certified-20260727",
    }
    topology = audit_grid_topology(
        grid,
        require_word_ids=True,
        enforce_layout=False,
        topology_profile="pilot",
    )
    if not topology["valid"]:
        raise ValueError(f"{grid_id}: topologie invalide {topology['errorCounts']}")
    return grid


def build_batch(document: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_candidate = {grid["candidateId"]: grid for grid in document["grids"]}
    if set(by_candidate) != set(ACCEPTED_CANDIDATES) | {WITHHELD_CANDIDATE}:
        raise ValueError("Le contenu certifié du handoff a changé")
    grids = [build_grid(by_candidate[candidate_id]) for candidate_id in ACCEPTED_CANDIDATES]
    if len({grid["id"] for grid in grids}) != len(grids):
        raise ValueError("Identifiants de grille dupliqués")
    return grids, withheld_report(document)


def batch_report(
    document: dict[str, Any],
    grids: list[dict[str, Any]],
    withheld: dict[str, Any],
) -> dict[str, Any]:
    topology = [
        audit_grid_topology(
            grid,
            require_word_ids=True,
            enforce_layout=False,
            topology_profile="pilot",
        )
        for grid in grids
    ]
    uses = Counter(word["answer"] for grid in grids for word in grid["words"])
    errors = [
        f"{item['gridId']}: {error['code']} {error['message']}"
        for item in topology
        for error in item["errors"]
    ]
    report = {
        "schema": "motman-factory-certified-editorial-audit",
        "version": 1,
        "generatedAt": date.today().isoformat(),
        "source": {
            "path": str(SOURCE_EXPORT),
            "fileSha256": EXPECTED_FILE_SHA256,
            "payloadSha256": EXPECTED_PAYLOAD_SHA256,
            "schema": document["schema"],
            "version": document["version"],
            "certifiedGridCount": len(document["grids"]),
        },
        "decision": {
            "publishableGridCount": len(grids),
            "withheldGridCount": 1,
            "withheld": [withheld],
        },
        "lexicalReviews": {
            "FOSTER": LEXICAL_EXCEPTIONS["FOSTER"],
            "SIEN": LEXICAL_EXCEPTIONS["SIEN"],
            "LEGERES": LEXICAL_EXCEPTIONS["LEGERES"],
            "REELLE": LEXICAL_EXCEPTIONS["REELLE"],
            "properNames": PROPER_NAME_REVIEWS,
        },
        "metrics": {
            "answers": sum(len(grid["words"]) for grid in grids),
            "distinctAnswers": len(uses),
            "repeatedAnswers": {
                answer: count for answer, count in sorted(uses.items()) if count > 1
            },
            "images": sum(grid["imageCount"] for grid in grids),
            "topologyValid": sum(item["valid"] for item in topology),
        },
        "valid": not errors,
        "errors": errors,
        "grids": topology,
    }
    return report


def atomic_json(path: Path, value: object, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=None if compact else 2,
            separators=(",", ":") if compact else None,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_review(
    document: dict[str, Any],
    grids: list[dict[str, Any]],
    withheld: dict[str, Any],
    report: dict[str, Any],
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    staging = {
        "schema": "motman-factory-certified-editorial-staging",
        "version": 1,
        "catalogVersionTarget": TARGET_CATALOG_VERSION,
        "sourceFileSha256": EXPECTED_FILE_SHA256,
        "sourcePayloadSha256": EXPECTED_PAYLOAD_SHA256,
        "grids": grids,
        "withheld": [withheld],
    }
    atomic_json(STAGING_PATH, staging)
    atomic_json(AUDIT_PATH, report)
    topology_html = render_topology_html(
        report["grids"],
        title="MotMan — quatre grilles Factory éditorialisées",
    )
    decision = (
        "<section style=\"max-width:1100px;margin:24px auto;padding:18px;"
        "background:#fff7e6;border:1px solid #d7b86c;border-radius:16px\">"
        "<h2>Décision de publication</h2>"
        f"<p><strong>{len(grids)} grilles retenues</strong> après contrôle, "
        "définitions manuelles et indices-images licenciés.</p>"
        f"<p><strong>1 grille bloquée</strong> : {withheld['proposedGridId']} partage "
        f"{withheld['sharedAnswerCount']} réponses avec "
        f"{WITHHELD_AGAINST} (similarité {withheld['jaccardSimilarity']:.1%}).</p>"
        "<p>FOSTER, SIEN, LEGERES et REELLE portent une décision lexicale humaine "
        "explicite dans l’audit JSON.</p></section>"
    )
    REVIEW_PATH.write_text(
        topology_html.replace("<body>", f"<body>{decision}", 1),
        encoding="utf-8",
    )


def publish(grids: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    if not report["valid"]:
        raise ValueError("Publication refusée : audit éditorial invalide")
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    existing_by_id = {grid["id"]: grid for grid in catalog["grids"]}
    accepted_ids = {grid["id"] for grid in grids}
    present = accepted_ids & set(existing_by_id)
    if present and present != accepted_ids:
        raise ValueError(f"Publication partielle détectée: {sorted(present)}")
    if present == accepted_ids:
        for grid in grids:
            if existing_by_id[grid["id"]] != grid:
                raise ValueError(f"Une grille publiée diffère du lot revu: {grid['id']}")
        if catalog.get("version") != TARGET_CATALOG_VERSION:
            raise ValueError("Les grilles existent mais la version catalogue est incohérente")
        return {"changed": False, "catalogVersion": catalog["version"], "gridCount": len(catalog["grids"])}
    if catalog.get("version") != TARGET_CATALOG_VERSION - 1:
        raise ValueError(
            f"Version source inattendue: {catalog.get('version')}; "
            f"attendu {TARGET_CATALOG_VERSION - 1}"
        )

    updated = copy.deepcopy(catalog)
    updated["version"] = TARGET_CATALOG_VERSION
    updated["source"] = str(SNAPSHOT_PATH.relative_to(ROOT)).replace("\\", "/")
    updated["grids"].extend(grids)
    updated["batchMetrics"] = {
        "gridCount": len(updated["grids"]),
        "columns": 7,
        "rows": 8,
        "letterCells": sum(
            len({tuple(cell) for word in grid["words"] for cell in word["cells"]})
            for grid in updated["grids"]
        ),
        "answers": sum(len(grid["words"]) for grid in updated["grids"]),
        "imageCount": sum(
            bool(word.get("image"))
            for grid in updated["grids"]
            for word in grid["words"]
        ),
        "factoryCertifiedBatchAdded": len(grids),
        "factoryCertifiedGridWithheld": 1,
    }
    updated["publicationNote"] = (
        "29 grilles compactes 7x8 actives; quatre grilles Grid Factory certifiées "
        "puis éditorialisées manuellement le 2026-07-27. Une cinquième grille "
        "certifiée reste bloquée car elle partage 16 réponses sur 17 avec une "
        "grille du même lot."
    )
    snapshot = {
        "schema": "motman-factory-certified-editorial-source",
        "version": 1,
        "catalogVersion": TARGET_CATALOG_VERSION,
        "sourceFileSha256": EXPECTED_FILE_SHA256,
        "sourcePayloadSha256": EXPECTED_PAYLOAD_SHA256,
        "withheld": report["decision"]["withheld"],
        "lexicalReviews": report["lexicalReviews"],
        "grids": grids,
    }
    atomic_json(SNAPSHOT_PATH, snapshot)
    atomic_json(CATALOG_PATH, updated)
    return {"changed": True, "catalogVersion": updated["version"], "gridCount": len(updated["grids"])}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    document = verify_handoff()
    grids, withheld = build_batch(document)
    report = batch_report(document, grids, withheld)
    write_review(document, grids, withheld, report)
    result: dict[str, Any] = {
        "valid": report["valid"],
        "staged": len(grids),
        "withheld": 1,
        "staging": str(STAGING_PATH),
        "audit": str(AUDIT_PATH),
        "review": str(REVIEW_PATH),
        "published": False,
    }
    if args.publish:
        result["publication"] = publish(grids, report)
        result["published"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
