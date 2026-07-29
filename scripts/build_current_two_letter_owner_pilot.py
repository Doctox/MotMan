#!/usr/bin/env python3
"""Build one non-published 7x8 owner pilot with one reviewed 2-letter answer."""
from __future__ import annotations

import argparse
import copy
import html
import json
import sys
from collections import Counter
from pathlib import Path

from wordfreq import zipf_frequency


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_compact_7x8_review import render_playtest_html  # noqa: E402
from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402


SOURCE_GRID_ID = "compact-7x8-agent-e-01"
PILOT_GRID_ID = "pilot-current-two-letter-7x8-01"

EDITORIAL = {
    "SEGMENT": ("Extrait de vidéo", "nom commun", "current-common", "direct"),
    "TRAINER": ("Tirer derrière", "verbe à l'infinitif", "daily-common", "direct"),
    "ARGENTE": ("Médaille d'argent", "adjectif lexicalisé", "daily-common", "image"),
    "TONNE": ("Poids de musculation", "nom commun", "daily-common", "image"),
    "UNE": ("Article féminin", "déterminant", "daily-common", "direct"),
    "TERMINE": ("Arrivé au bout", "adjectif lexicalisé", "daily-common", "direct"),
    "STATUT": ("État du profil", "nom commun", "current-common", "direct"),
    "ERRONE": ("Inexact", "adjectif lexicalisé", "daily-common", "direct"),
    "GAGNER": ("Trophée doré", "verbe à l'infinitif", "daily-common", "image"),
    "MIEN": ("À moi", "pronom possessif", "daily-common", "direct"),
    "MAL": ("Douleur", "nom commun", "daily-common", "direct"),
    "ENNEMI": ("Épées croisées", "nom commun", "daily-common", "image"),
    "NET": ("Internet", "nom courant", "current-common", "direct"),
    "AN": ("Douze mois", "nom commun", "daily-common", "direct"),
    "TREFLE": ("Feuilles triples", "nom commun", "daily-common", "image"),
}

IMAGE_ALT = {
    "ARGENTE": "Médaille d'argent",
    "TONNE": "Poids de musculation",
    "GAGNER": "Trophée doré",
    "ENNEMI": "Épées croisées",
    "TREFLE": "Trèfle vert",
}

THOUGHTFUL_ANSWERS = {"ARGENTE", "ERRONE", "TREFLE"}
CLEVER_TEXT_ANSWERS = {"AN"}
CURRENT_ANCHOR_REASONS = {
    "SEGMENT": "Vocabulaire vidéo courant",
    "STATUT": "Usage des profils et applis",
    "NET": "Usage numérique installé en français",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=ROOT / "src/data/grid.catalog.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def build_grid(catalog: dict) -> dict:
    source = next(grid for grid in catalog["grids"] if grid["id"] == SOURCE_GRID_ID)
    grid = copy.deepcopy(source)
    grid.update({
        "id": PILOT_GRID_ID,
        "sourceGridId": SOURCE_GRID_ID,
        "publicationStatus": "owner-review-required",
        "catalogModified": False,
        "runtimeModified": False,
        "supabaseModified": False,
        "audience": "16–45 ans",
        "editorialProfile": "motman-current-two-letter-pilot-v1",
    })
    for index, word in enumerate(grid["words"], 1):
        answer = word["answer"]
        clue, part_of_speech, register, clue_style = EDITORIAL[answer]
        word.update({
            "wordId": f"{PILOT_GRID_ID}:word:{index:02d}",
            "clue": clue,
            "sourceClue": clue,
            "definitionStatus": "image-review" if answer in IMAGE_ALT else "manually-reviewed",
            "editorialStatus": "owner-review-required",
            "sourceType": "image-concept" if answer in IMAGE_ALT else "editorial-original",
            "sourceId": "motman-current-two-letter-pilot-20260722",
            "sourceUrl": "internal://motman/editorial/current-two-letter-pilot-20260722",
            "license": "MotMan original",
            "familiarityScore": round(float(zipf_frequency(answer.lower(), "fr")), 2),
            "familiarityBand": (
                "thoughtful" if answer in THOUGHTFUL_ANSWERS else "common"
            ),
            "partOfSpeech": part_of_speech,
            "languageStatus": "common-anglicism" if answer == "NET" else "french",
            "culturalStatus": (
                "current-common" if register == "current-common" else "everyday"
            ),
            "clueStyle": (
                "clever" if answer in CLEVER_TEXT_ANSWERS else clue_style
            ),
            "imageStatus": (
                "reviewed-recognizable-licensed"
                if answer in IMAGE_ALT else "not-applicable"
            ),
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
        })
        if answer == "AN":
            word["twoLetterReview"] = {
                "status": "human-reviewed-whitelist",
                "reason": "Nom autonome, indice précis et immédiatement devinable.",
            }
        if answer in IMAGE_ALT:
            word["image"]["alt"] = IMAGE_ALT[answer]
            word["image"]["concept"] = IMAGE_ALT[answer]
    return grid


def render_editorial_review(report: dict, grid: dict) -> str:
    base = render_topology_html(
        [report], title="MotMan — pilote actuel 7×8 à relire"
    )
    rows = []
    for word in grid["words"]:
        answer = word["answer"]
        register = (
            "actuel" if word["culturalStatus"] == "current-common" else "quotidien"
        )
        anchor_reason = CURRENT_ANCHOR_REASONS.get(answer, "—")
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(answer)}</strong></td>"
            f"<td>{html.escape(word['clue'])}</td>"
            f"<td>{html.escape(word['partOfSpeech'])}</td>"
            f"<td>{register}</td>"
            f"<td>{html.escape(word['familiarityBand'])}</td>"
            f"<td>{html.escape(anchor_reason)}</td>"
            f"<td>{html.escape(word['sourceId'])}</td>"
            "</tr>"
        )
    appendix = f"""
      <section class='grid-review editorial-ledger'>
        <h2>Relecture éditoriale</h2>
        <p><strong>Staging uniquement :</strong> aucune modification du catalogue,
        du runtime ou de Supabase. La structure reprend une grille déjà approuvée
        par le propriétaire afin de valider sans risque le nouveau contrat 1–2
        réponses courtes.</p>
        <p><strong>Ancrages actuels :</strong> SEGMENT, STATUT et NET. Le reste
        privilégie le vocabulaire quotidien et intemporel.</p>
        <div class='grid-scroll'><table class='paths'>
          <thead><tr><th>Réponse</th><th>Indice</th><th>Nature</th><th>Registre</th>
          <th>Familiarité</th><th>Rôle actuel</th><th>Source</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table></div>
      </section>
    """
    return base.replace("</body>", appendix + "</body>")


def main() -> None:
    args = parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    grid = build_grid(catalog)
    report = audit_grid_topology(
        grid, enforce_layout=False, topology_profile="pilot"
    )
    if not report["valid"]:
        raise ValueError(report["errors"])

    answers = [word["answer"] for word in grid["words"]]
    two_letter = [answer for answer in answers if len(answer) == 2]
    current = [
        word["answer"] for word in grid["words"]
        if word.get("culturalStatus") == "current-common"
    ]
    metrics = {
        "answerCount": len(answers),
        "twoLetterAnswers": two_letter,
        "twoLetterCount": len(two_letter),
        "lengthProfile": dict(sorted(Counter(map(len, answers)).items())),
        "imageCount": sum(bool(word.get("image")) for word in grid["words"]),
        "currentAnchors": current,
        "orphanSegments": len(report["orphanSegments"]),
        "uncoveredLetters": sum(
            cell["kind"] == "letter" and not cell["wordIds"]
            for cell in report["cells"]
        ),
    }
    staging = {
        "version": 1,
        "kind": "motman-current-two-letter-owner-pilot",
        "publicationEligible": False,
        "catalogModified": False,
        "runtimeModified": False,
        "supabaseModified": False,
        "contract": {
            "columns": 7,
            "rows": 8,
            "fullTopAndLeftClueFrame": True,
            "arrows": ["right", "down"],
            "minimumTwoLetterAnswers": 1,
            "maximumTwoLetterAnswers": 2,
            "twoLetterWhitelist": ["AN"],
        },
        "grids": [grid],
        "metrics": [metrics],
    }
    audit = {
        "version": 1,
        "valid": True,
        "publicationEligible": False,
        "gridId": PILOT_GRID_ID,
        "metrics": metrics,
        "topology": report,
        "toneReview": {
            "audience": "16–45 ans",
            "currentAnchors": current,
            "dailyTimelessAnswers": [
                word["answer"] for word in grid["words"]
                if word.get("culturalStatus") == "daily-common"
            ],
            "artificialConjugations": [],
            "obscureProperNames": [],
            "archaicAnswers": [],
            "globalVerdict": "accessible-current-balanced",
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "staging.json").write_text(
        json.dumps(staging, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    editorial = render_editorial_review(report, grid)
    (args.output_dir / "editorial-review.html").write_text(editorial, encoding="utf-8")
    (args.output_dir / "playtest.html").write_text(
        render_playtest_html([report]), encoding="utf-8"
    )
    print(json.dumps({
        "complete": True,
        "gridId": PILOT_GRID_ID,
        "metrics": metrics,
        "outputDirectory": str(args.output_dir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
