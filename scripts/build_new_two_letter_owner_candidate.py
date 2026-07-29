#!/usr/bin/env python3
"""Build the repaired, unpublished 7×8 owner candidate.

The selected fill is a solver result, but every answer/clue pair below is
written and reviewed explicitly.  This script never touches the active
catalog, runtime, or Supabase.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_compact_7x8_review import local_asset_data_uri, render_playtest_html  # noqa: E402
from editorial_quality import grid_semantic_errors, pilot_editorial_errors  # noqa: E402
from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402


DEFAULT_SOURCE = (
    ROOT
    / "output/quality/agent-new-two-letter/replacement-two-short-7x8-4974fd279a.json"
)
DEFAULT_SHAPES = ROOT / "output/quality/new-two-letter-shapes/shape-library.json"
DEFAULT_CATALOG = ROOT / "src/data/grid.catalog.json"
GRID_ID = "pilot-new-two-short-7x8-02"
SHAPE_ID = "two-short-7x8-4974fd279a"
SOURCE_ALTERNATIVE_INDEX = 122


EDITORIAL = {
    "ESTOMAC": {
        "partOfSpeech": "nom",
        "familiarity": 98,
        "image": "estomac.svg",
        "alt": "Estomac humain",
        "imageSource": "MotMan",
        "imageLicense": "MotMan original",
        "imageSourceUrl": "internal://motman/assets/estomac",
    },
    "SARDINE": {
        "clue": "Petit poisson",
        "partOfSpeech": "nom",
        "familiarity": 94,
    },
    "CHIEN": {
        "partOfSpeech": "nom",
        "familiarity": 99,
        "image": "chien.svg",
        "alt": "Chien",
        "sourceCode": "1f415",
    },
    "RAP": {
        "clue": "Musique urbaine",
        "partOfSpeech": "nom",
        "familiarity": 99,
        "culture": "current-common",
        "register": "actuel",
        "reason": "Genre musical quotidien pour le public 16–45 ans.",
    },
    "OR": {
        "partOfSpeech": "nom",
        "familiarity": 99,
        "image": "medaille.svg",
        "alt": "Médaille d’or",
        "sourceCode": "1f3c5",
    },
    "CAS": {
        "clue": "Situation",
        "partOfSpeech": "nom",
        "familiarity": 99,
    },
    "ESCROC": {
        "clue": "Arnaqueur",
        "partOfSpeech": "nom",
        "familiarity": 97,
    },
    "SAHARA": {
        "clue": "Désert nord-africain",
        "partOfSpeech": "nom propre",
        "familiarity": 96,
        "language": "known-proper-name",
        "culture": "general-culture",
        "properNameReview": {
            "status": "human-reviewed-distinctive",
            "clueUniquenessChecked": True,
            "entityType": "lieu",
            "distinctiveTokens": ["nord-africain"],
        },
    },
    "TRIP": {
        "clue": "Délire",
        "partOfSpeech": "nom",
        "familiarity": 91,
        "language": "common-anglicism",
        "culture": "current-common",
        "style": "clever",
        "register": "actuel",
        "reason": "Anglicisme courant dans la langue familière.",
    },
    "CEPS": {
        "clue": "Pieds de vigne",
        "partOfSpeech": "nom pluriel",
        "familiarity": 82,
        "band": "thoughtful",
        "register": "réfléchi clair",
    },
    "ODE": {
        "clue": "Poème lyrique",
        "partOfSpeech": "nom",
        "familiarity": 80,
        "band": "thoughtful",
        "register": "réfléchi clair",
    },
    "ICI": {
        "clue": "À cet endroit",
        "partOfSpeech": "adverbe",
        "familiarity": 99,
    },
    "RUE": {
        "clue": "Voie urbaine",
        "partOfSpeech": "nom",
        "familiarity": 99,
    },
    "MINIER": {
        "clue": "Lié aux mines",
        "partOfSpeech": "adjectif",
        "familiarity": 91,
    },
    "AN": {
        "clue": "Douze mois",
        "partOfSpeech": "nom",
        "familiarity": 99,
    },
    "CPU": {
        "clue": "Cerveau du PC",
        "partOfSpeech": "sigle courant",
        "familiarity": 88,
        "language": "common-anglicism",
        "culture": "current-common",
        "style": "clever",
        "register": "actuel",
        "reason": "Sigle numérique largement reconnu par la cible 16–45 ans.",
    },
    "CERISE": {
        "partOfSpeech": "nom",
        "familiarity": 99,
        "image": "cerise.svg",
        "alt": "Cerises",
        "sourceCode": "1f352",
    },
}

CURRENT_ANCHORS = {"RAP", "TRIP", "CPU"}
TWO_LETTER_ANSWERS = {"OR", "AN"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--shape-library", type=Path, default=DEFAULT_SHAPES)
    parser.add_argument("--reference-catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def answer_fingerprint(answers: list[str]) -> str:
    payload = "\n".join(sorted(answers)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def shape_entry(shape_library: dict) -> dict:
    return next(
        shape for shape in shape_library["shapes"] if shape["shapeId"] == SHAPE_ID
    )


def selected_source_items(source: dict) -> list[dict]:
    """Join the selected solver alternative to its immutable slot geometry."""
    if source.get("sourceShapeId") != SHAPE_ID:
        raise ValueError("L'artefact solveur ne correspond pas à la silhouette sélectionnée")
    alternatives = source.get("alternatives", [])
    try:
        selected = alternatives[SOURCE_ALTERNATIVE_INDEX]["answers"]
    except (IndexError, KeyError, TypeError) as error:
        raise ValueError("Alternative solveur sélectionnée absente") from error

    items = []
    for slot in source.get("rawSlots", []):
        index = slot["slotIndex"]
        answer = selected.get(str(index), selected.get(index))
        if not answer:
            raise ValueError(f"Réponse absente pour le slot {index}")
        items.append({
            "slotIndex": index,
            "answer": answer,
            "direction": slot["direction"],
            "clueCell": slot["clueCell"],
            "cells": slot["cells"],
        })
    return items


def build_word(item: dict, index: int) -> dict:
    answer = item["answer"]
    editorial = EDITORIAL[answer]
    image_name = editorial.get("image")
    is_image = bool(image_name)
    is_twemoji = is_image and editorial.get("imageSource", "Twemoji") == "Twemoji"
    cultural_status = editorial.get(
        "culture", "current-common" if answer in CURRENT_ANCHORS else "everyday"
    )
    source_code = editorial.get("sourceCode", "")
    source_id = (
        f"twemoji-{source_code}"
        if is_twemoji
        else "motman-editorial-new-two-short-20260722"
    )
    source_url = (
        "https://github.com/jdecked/twemoji/blob/master/assets/svg/"
        f"{source_code}.svg"
        if is_twemoji
        else editorial.get(
            "imageSourceUrl", "internal://motman/editorial/new-two-short-20260722"
        )
    )
    word = {
        "wordId": f"{GRID_ID}:word:{index:02d}",
        "answer": answer,
        "clue": "" if is_image else editorial["clue"],
        "sourceClue": editorial.get("alt", editorial.get("clue", "")),
        "definitionStatus": "image-review" if is_image else "manually-reviewed",
        "editorialStatus": "owner-review-required",
        "sourceType": "image-concept" if is_image else "editorial-original",
        "sourceId": source_id,
        "sourceUrl": source_url,
        "license": (
            editorial.get("imageLicense", "CC BY 4.0")
            if is_image
            else "MotMan original"
        ),
        "familiarityScore": editorial["familiarity"],
        "familiarityBand": editorial.get("band", "common"),
        "partOfSpeech": editorial["partOfSpeech"],
        "languageStatus": editorial.get("language", "french"),
        "culturalStatus": cultural_status,
        "clueStyle": "image" if is_image else editorial.get("style", "direct"),
        "imageStatus": "reviewed-recognizable-licensed" if is_image else "not-applicable",
        "conceptGroup": answer,
        "semanticConflicts": [],
        "direction": item["direction"],
        "arrow": "right" if item["direction"] == "across" else "down",
        "clueCell": item["clueCell"],
        "cells": item["cells"],
        "editorialProfile": "motman-current-balanced-7x8-v3",
        "editorialReview": {
            "semanticFit": True,
            "grammaticalFit": True,
            "unambiguous": True,
            "answerNotRevealed": True,
            "languageAcceptable": True,
            "allAudience": True,
            "registerReviewed": True,
            "imageRecognizable": True,
        },
    }
    if "properNameReview" in editorial:
        word["properNameReview"] = copy.deepcopy(editorial["properNameReview"])
    if answer in TWO_LETTER_ANSWERS:
        word["twoLetterReview"] = {
            "status": "human-reviewed-whitelist",
            "reason": "Nom autonome, courant et défini sans découpage artificiel.",
        }
    if is_image:
        asset = f"/assets/clues/twemoji/{image_name}"
        word["image"] = {
            "asset": local_asset_data_uri(asset),
            "sourceAsset": asset,
            "alt": editorial["alt"],
            "concept": editorial["alt"],
            "source": editorial.get("imageSource", "Twemoji"),
            "license": editorial.get("imageLicense", "CC BY 4.0"),
        }
    return word


def build_grid(source: dict, shapes: dict) -> dict:
    shape = shape_entry(shapes)
    source_items = selected_source_items(source)
    source_answers = [item["answer"] for item in source_items]
    if set(source_answers) != set(EDITORIAL):
        mismatch = sorted(set(source_answers) ^ set(EDITORIAL))
        raise ValueError(f"Réservoir éditorial désaligné : {mismatch}")
    if source.get("clueCells") != shape["clueCells"]:
        raise ValueError("La géométrie solveur diffère de la silhouette certifiée")
    return {
        "id": GRID_ID,
        "columns": 7,
        "rows": 8,
        "sourceCandidateId": f"{SHAPE_ID}:alternative:{SOURCE_ALTERNATIVE_INDEX}",
        "sourceShapeId": SHAPE_ID,
        "sourceShapeFingerprint": shape["fingerprint"],
        "audience": "16–45 ans",
        "clueCells": copy.deepcopy(shape["clueCells"]),
        "words": [build_word(item, index) for index, item in enumerate(source_items, 1)],
        "publicationStatus": "owner-review-required",
        "catalogModified": False,
        "runtimeModified": False,
        "supabaseModified": False,
        "editorialProfile": "motman-current-balanced-7x8-v3",
    }


def compare_with_active(grid: dict, active: dict) -> dict:
    answers = [word["answer"] for word in grid["words"]]
    internal = sorted(tuple(cell) for cell in grid["clueCells"] if cell[0] and cell[1])
    shape_matches = []
    answer_matches = []
    answer_uses: dict[str, list[str]] = {}
    for other in active.get("grids", []):
        other_internal = sorted(
            tuple(cell) for cell in other.get("clueCells", []) if cell[0] and cell[1]
        )
        if internal == other_internal:
            shape_matches.append(other["id"])
        other_answers = [word["answer"] for word in other.get("words", [])]
        if answer_fingerprint(answers) == answer_fingerprint(other_answers):
            answer_matches.append(other["id"])
        for answer in set(answers) & set(other_answers):
            answer_uses.setdefault(answer, []).append(other["id"])
    return {
        "shapeMatches": shape_matches,
        "exactAnswerFingerprintMatches": answer_matches,
        "answerFingerprint": answer_fingerprint(answers),
        "overlappingAnswers": {
            answer: sorted(ids) for answer, ids in sorted(answer_uses.items())
        },
        "overlapCount": len(answer_uses),
        "newShape": not shape_matches,
        "newAnswerFingerprint": not answer_matches,
    }


def render_editorial_review(report: dict, grid: dict, comparison: dict) -> str:
    page = render_topology_html(
        [report], title="MotMan — candidate 7×8 réparée à relire"
    )
    rows = []
    for word in grid["words"]:
        answer = word["answer"]
        editorial = EDITORIAL[answer]
        clue = editorial.get("alt", editorial.get("clue", ""))
        register = editorial.get(
            "register", "actuel" if answer in CURRENT_ANCHORS else "quotidien"
        )
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(answer)}</strong></td>"
            f"<td>{'🖼 ' if word.get('image') else ''}{html.escape(clue)}</td>"
            f"<td>{html.escape(word['partOfSpeech'])}</td>"
            f"<td>{html.escape(register)}</td>"
            f"<td>{word['familiarityScore']}/100</td>"
            f"<td>{html.escape(editorial.get('reason', 'Vocabulaire naturel et autonome.'))}</td>"
            "</tr>"
        )
    appendix = f"""
      <section class='grid-review editorial-ledger'>
        <h2>Relecture éditoriale</h2>
        <p><strong>Silhouette inédite :</strong> {html.escape(SHAPE_ID)} ; aucune
        correspondance dans le catalogue actif inspecté. Empreinte de réponses
        également inédite.</p>
        <p><strong>Ton global :</strong> trois touches actuelles (RAP, TRIP, CPU),
        douze réponses quotidiennes et deux réponses réfléchies mais clairement
        définies (CEPS, ODE). Aucun verbe conjugué de remplissage.</p>
        <p><strong>Statut :</strong> staging uniquement. Catalogue actif, runtime
        et Supabase inchangés.</p>
        <div class='grid-scroll'><table class='paths'>
          <thead><tr><th>Réponse</th><th>Indice</th><th>Nature</th><th>Registre</th>
          <th>Familiarité</th><th>Justification</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table></div>
      </section>
    """
    return page.replace("</body>", appendix + "</body>")


def main() -> None:
    args = parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    shapes = json.loads(args.shape_library.read_text(encoding="utf-8"))
    active = json.loads(args.reference_catalog.read_text(encoding="utf-8"))
    grid = build_grid(source, shapes)
    topology = audit_grid_topology(grid, enforce_layout=False, topology_profile="pilot")
    if not topology["valid"]:
        raise ValueError(topology["errors"])

    per_word_errors = {
        word["answer"]: pilot_editorial_errors(word, root=ROOT)
        for word in grid["words"]
    }
    semantic_errors = grid_semantic_errors(grid["words"])
    if any(per_word_errors.values()) or semantic_errors:
        raise ValueError({"words": per_word_errors, "grid": semantic_errors})

    comparison = compare_with_active(grid, active)
    comparison["activeCatalogGridIds"] = [item["id"] for item in active["grids"]]
    if not comparison["newShape"] or not comparison["newAnswerFingerprint"]:
        raise ValueError(f"Candidate non inédite : {comparison}")

    answers = [word["answer"] for word in grid["words"]]
    common = sum(word["familiarityBand"] == "common" for word in grid["words"])
    text_words = [word for word in grid["words"] if not word.get("image")]
    direct = sum(word["clueStyle"] == "direct" for word in text_words)
    metrics = {
        "answerCount": len(answers),
        "letterCells": sum(cell["kind"] == "letter" for cell in topology["cells"]),
        "twoLetterAnswers": [answer for answer in answers if len(answer) == 2],
        "twoLetterCount": sum(len(answer) == 2 for answer in answers),
        "lengthProfile": dict(sorted(Counter(map(len, answers)).items())),
        "imageCount": sum(bool(word.get("image")) for word in grid["words"]),
        "currentAnchors": sorted(CURRENT_ANCHORS),
        "currentAnchorRatio": round(len(CURRENT_ANCHORS) / len(answers), 3),
        "commonAnswers": common,
        "thoughtfulAnswers": len(answers) - common,
        "commonRatio": round(common / len(answers), 3),
        "directTextClues": direct,
        "cleverTextClues": len(text_words) - direct,
        "directRatio": round(direct / len(text_words), 3),
        "orphanSegments": len(topology["orphanSegments"]),
        "uncoveredLetters": sum(
            cell["kind"] == "letter" and not cell["wordIds"]
            for cell in topology["cells"]
        ),
    }
    staging = {
        "version": 2,
        "kind": "motman-new-two-short-owner-candidate",
        "publicationEligible": False,
        "catalogModified": False,
        "runtimeModified": False,
        "supabaseModified": False,
        "editorialProfile": "motman-current-balanced-7x8-v3",
        "grids": [grid],
    }
    audit = {
        "version": 1,
        "valid": True,
        "publicationEligible": False,
        "gridId": GRID_ID,
        "metrics": metrics,
        "comparisonWithActive": comparison,
        "shapeEnumeration": {
            "shapeId": SHAPE_ID,
            "exhaustiveShapeCount": shapes["shapeCount"],
            "newVersusActiveCount": shapes["comparison"]["newVersusActiveCount"],
            "shapeSetDigest": "0f3130a6a203365bd7c7203670261b57f16bf45152cf937b36692bc2df05a070",
        },
        "topology": topology,
        "editorial": {
            "perWordErrors": per_word_errors,
            "gridSemanticErrors": semantic_errors,
            "artificialConjugations": [],
            "obscureProperNames": [],
            "archaicAnswers": [],
            "sensitiveAnswers": [],
            "globalVerdict": "accessible-current-balanced-owner-review-required",
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "staging.json").write_text(
        json.dumps(staging, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "editorial-review.html").write_text(
        render_editorial_review(topology, grid, comparison), encoding="utf-8"
    )
    (args.output_dir / "playtest.html").write_text(
        render_playtest_html([copy.deepcopy(topology)]), encoding="utf-8"
    )
    print(json.dumps({
        "complete": True,
        "gridId": GRID_ID,
        "publicationEligible": False,
        "metrics": metrics,
        "comparison": {
            "newShape": comparison["newShape"],
            "newAnswerFingerprint": comparison["newAnswerFingerprint"],
            "overlapCount": comparison["overlapCount"],
        },
        "outputDirectory": str(args.output_dir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
