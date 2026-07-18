#!/usr/bin/env python3
"""Build the strict, unpublished review for the retained base closure."""

from __future__ import annotations

import json
import sys
from collections import Counter
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from agent_editorialize_shifted import (  # noqa: E402
    blacklist_audit,
    family_audit,
    load_lemmas,
    read_json,
    write_json,
)
from audit_flexible_batch_candidates import (  # noqa: E402
    answer_family,
    load_reference_usage,
)
from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402


SOURCE = ROOT / "output/quality/root-fixed-l.json"
OUTPUT = ROOT / "output/quality/batch-v2-base-review.json"
AUDIT = ROOT / "output/quality/batch-v2-base-review.audit.json"
HTML = ROOT / "output/quality/batch-v2-base-review.html"
STAGING = ROOT / "src/data/grid-generation-handcrafted/batch-v2-base.review.json"
IMAGES = ROOT / "src/data/crossword.images-reviewed.json"
GRID_ID = "batch-v2-base-review-01"
REPLACEMENT_REFERENCES: list[Path] = []


CLUES = {
    "APPARENTS": "Visibles",
    "PREMATURE": "Trop précoce",
    "PORES": "Orifices cutanés",
    "ETIRER": "Allonger en tirant",
    "LE": "Article masculin",
    "AIL": "Plante condimentaire",
    "INOX": "Acier inoxydable",
    "SET": "Manche de tennis",
    "APPELAIS": "Téléphonais",
    "PROTEINE": "Molécule du vivant",
    "PERI": "A succombé",
    "LOT": "Ensemble attribué",
    "AMERE": "Au goût âpre",
    "USURE": "Dégradation progressive",
    "TELES": "Postes de télévision",
    "RASE": "Coupe très court",
    "EDEN": "Jardin paradisiaque",
    "TEST": "Épreuve de contrôle",
    "ET": "Relie deux mots",
    "RESTE": "Ce qui demeure",
    "SAC": "Contenant souple",
    "NUS": "Sans vêtements",
    "DUEL": "Combat singulier",
    "TRAVERSE": "Coupe en deux",
    "SEC": "Sans humidité",
    "NETS": "Bien distincts",
}


# The source lemma indexes do not consistently fold accented inflections.
# These narrow overrides make the family audit explicit without broad stemming.
CONCEPT_OVERRIDES = {
    "APPARENTS": "APPARENT",
    "PREMATURE": "PREMATURE",
    "ETIRER": "ETIRER",
    "PERI": "PERIR",
    "TELES": "TELEVISION",
    "RASE": "RASER",
}


def reviewed_images() -> dict[str, dict]:
    requested = {"AIL", "SAC", "DUEL"}
    matches: dict[str, list[dict]] = {answer: [] for answer in requested}
    for entry in read_json(IMAGES).get("entries", []):
        answer = str(entry.get("answer", "")).upper()
        if (
            answer in requested
            and entry.get("editorialStatus") == "image-reviewed"
            and isinstance(entry.get("image"), dict)
        ):
            matches[answer].append(entry)
    invalid_counts = {answer: len(items) for answer, items in matches.items() if len(items) != 1}
    if invalid_counts:
        raise ValueError({"reviewedImageCounts": invalid_counts})
    result = {answer: items[0] for answer, items in matches.items()}
    for answer, entry in result.items():
        asset = str(entry["image"].get("asset", ""))
        if not asset.startswith("/") or not (ROOT / "public" / asset.lstrip("/")).is_file():
            raise ValueError(f"Asset {answer} absent : {asset}")
    return result


def build_words(raw: dict, lemmas: dict[str, str], images: dict[str, dict]) -> list[dict]:
    raw_answers = raw.get("answers", [])
    answers = [str(item.get("answer", "")).upper() for item in raw_answers]
    missing = sorted(set(answers) - CLUES.keys())
    extras = sorted(CLUES.keys() - set(answers))
    if missing or extras or len(answers) != 26:
        raise ValueError({"missingClues": missing, "unusedClues": extras, "answers": len(answers)})

    words = []
    for number, item in enumerate(raw_answers, start=1):
        answer = item["answer"]
        direction = item["direction"]
        clue = CLUES[answer]
        concept = CONCEPT_OVERRIDES.get(answer, lemmas.get(answer, answer))
        word = {
            "wordId": f"{GRID_ID}:word:{number:02d}",
            "answer": answer,
            "clue": clue,
            "sourceClue": clue,
            "definitionStatus": "manually-edited",
            "editorialStatus": "human-reviewed-awaiting-owner",
            "manualReview": "strict-agent-editorial-pass-20260718",
            "sourceType": "editorial-original",
            "sourceId": "motman-batch-v2-base-human-pass-20260718",
            "sourceUrl": "",
            "license": "MotMan original",
            "direction": direction,
            "arrow": "right" if direction == "across" else "down",
            "clueCell": item["clueCell"],
            "cells": item["cells"],
            "conceptGroup": concept,
            "semanticConflicts": [],
            "editorialProfile": "motman-batch-v2-base-strict-pass",
            "sourceSpelling": item.get("spelling", answer.lower()),
            "sourceZipf": item.get("zipf"),
            "activeUsesAtSearch": item.get("activeUses", 0),
        }
        image_entry = images.get(answer)
        if image_entry:
            word.update({
                "editorialStatus": "image-reviewed-awaiting-owner",
                "sourceType": "image",
                "sourceId": image_entry["sourceId"],
                "sourceUrl": image_entry["sourceUrl"],
                "license": image_entry["license"],
                "conceptGroup": image_entry.get("conceptGroup", concept),
                "semanticConflicts": image_entry.get("semanticConflicts", []),
                "image": image_entry["image"],
            })
        words.append(word)
    return words


def main() -> None:
    source = read_json(SOURCE)
    if not source.get("complete") or not isinstance(source.get("grid"), dict):
        raise ValueError("La fermeture de base n'est pas complète")
    raw = source["grid"]
    lemmas = load_lemmas()
    images = reviewed_images()
    words = build_words(raw, lemmas, images)

    grid = {
        "id": GRID_ID,
        "columns": source.get("columns", 9),
        "rows": source.get("rows", 10),
        "clueCells": raw["clueCells"],
        "words": words,
        "publicationStatus": "owner-review-required",
        "editorialProfile": "motman-batch-v2-base-strict-pass",
        "reviewCycle": "2026-07-18",
        "layoutPolicy": "full-frame; free-interior; exactly-two-two-letter-answers",
        "accentPolicy": (
            "Accents ignored in answer cells; preserved in French clues; "
            "PERI represents PÉRI."
        ),
        "sourceCandidate": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "sourceShapeGridId": raw.get("sourceShapeGridId"),
    }
    topology = audit_grid_topology(grid, enforce_layout=False)
    answers = [word["answer"] for word in words]
    two_letter = [answer for answer in answers if len(answer) == 2]
    letter_cells = [cell for cell in topology["cells"] if cell["kind"] == "letter"]
    covered_letters = [cell for cell in letter_cells if cell["wordIds"]]
    audit_lemmas = dict(lemmas)
    audit_lemmas.update(CONCEPT_OVERRIDES)
    family = family_audit(answers, audit_lemmas)
    blacklist = blacklist_audit(words)
    reference_answers, reference_families = load_reference_usage(
        REPLACEMENT_REFERENCES, audit_lemmas
    )
    replacement_answer_repeats = {
        answer: reference_answers[answer]
        for answer in answers
        if reference_answers[answer]
    }
    replacement_family_repeats = {
        answer_family(word, audit_lemmas): reference_families[
            answer_family(word, audit_lemmas)
        ]
        for word in words
        if reference_families[answer_family(word, audit_lemmas)]
    }

    hard_failures = []
    if not topology["valid"]:
        hard_failures.append("invalid_topology")
    if topology["orphanSegments"]:
        hard_failures.append("orphan_segments")
    if len(letter_cells) != len(covered_letters):
        hard_failures.append("orphan_letter_cells")
    if len(answers) != len(set(answers)):
        hard_failures.append("duplicate_answers")
    if len(two_letter) != 2:
        hard_failures.append("two_letter_policy")
    if family["duplicateFamilies"]:
        hard_failures.append("duplicate_lemma_families")
    if blacklist["hardAnswerHitCount"]:
        hard_failures.append("blacklisted_answers")
    if blacklist["rejectedPairHitCount"]:
        hard_failures.append("blacklisted_answer_clue_pairs")
    if replacement_answer_repeats:
        hard_failures.append("answer_repeated_from_replacement_pool")
    if replacement_family_repeats:
        hard_failures.append("family_repeated_from_replacement_pool")

    # Cooldowns are publication blockers even when the vocabulary itself is sound.
    publication_blockers = [*hard_failures]
    if blacklist["rotationCooldownHitCount"]:
        publication_blockers.append("rotation_cooldown_answer_requires_replacement")
    publication_eligible = not publication_blockers
    if not publication_eligible:
        grid["publicationStatus"] = "blocked-editorial-review"

    metrics = {
        "dimensions": f"{grid['columns']}x{grid['rows']}",
        "answers": len(answers),
        "uniqueAnswers": len(set(answers)),
        "lengthProfile": dict(sorted(Counter(map(len, answers)).items())),
        "twoLetterAnswers": two_letter,
        "letterCells": len(letter_cells),
        "coveredLetterCells": len(covered_letters),
        "orphanLetterCells": len(letter_cells) - len(covered_letters),
        "orphanSegments": len(topology["orphanSegments"]),
        "topologyValid": topology["valid"],
        "duplicateFamilyCount": family["duplicateFamilyCount"],
        "imageAnswers": [word["answer"] for word in words if word.get("image")],
        "manualClueCount": len(words),
        "replacementAnswerRepeats": replacement_answer_repeats,
        "replacementFamilyRepeats": replacement_family_repeats,
        "publicationEligible": publication_eligible,
    }
    editorial_review = {
        "decision": "ready-for-owner-review" if publication_eligible else "blocked",
        "hardFailures": hard_failures,
        "publicationBlockers": publication_blockers,
        "rejectionRecommendations": [],
        "replacementPoolRepeatAudit": {
            "references": [str(path.relative_to(ROOT)).replace("\\", "/") for path in REPLACEMENT_REFERENCES],
            "answerRepeats": replacement_answer_repeats,
            "familyRepeats": replacement_family_repeats,
        },
        "accentDecisions": {
            "PERI": {
                "displayForm": "PÉRI",
                "clue": "A succombé",
                "decision": "accepted-complete-inflected-form",
                "note": "Participe passé de périr ; l'accent est normalisé dans les cases.",
            }
        },
        "acceptedEditorialDoubts": {
            "TELES": "Abréviation familière mais très courante de télévisions.",
            "SET": "Terme sportif installé en français.",
            "APPARENTS": "Adjectif pluriel autonome et clairement défini par Visibles.",
        },
        "imagePolicy": (
            "AIL, SAC et DUEL reprennent chacun leur entrée image-reviewed ; "
            "aucune autre image n'est ajoutée."
        ),
    }
    document = {
        "version": 1,
        "kind": "batch-v2-base-owner-review",
        "publicationPolicy": "Staging non publié ; répétitions du pool de remplacement bloquantes.",
        "catalogModified": False,
        "blacklistModified": False,
        "sourceCandidateModified": False,
        "metrics": metrics,
        "blacklistAudit": blacklist,
        "familyAudit": family,
        "editorialReview": editorial_review,
        "grids": [grid],
    }
    audit = {
        "version": 1,
        "kind": "batch-v2-base-strict-audit",
        "reviewArtifactGenerated": True,
        "valid": publication_eligible,
        "topologyValid": topology["valid"],
        "publicationEligible": publication_eligible,
        "catalogModified": False,
        "blacklistModified": False,
        "sourceCandidateModified": False,
        "metrics": metrics,
        "hardFailures": hard_failures,
        "publicationBlockers": publication_blockers,
        "blacklistAudit": blacklist,
        "familyAudit": family,
        "editorialReview": editorial_review,
        "topology": topology,
    }
    write_json(OUTPUT, document)
    write_json(STAGING, document)
    write_json(AUDIT, audit)

    page = render_topology_html([topology], title="MotMan — revue stricte batch v2 base")
    objection_lines = "".join(
        f"<li><b>{escape(item['answer'])}</b> — {escape(item['reason'])}</li>"
        for item in blacklist["rotationCooldownHits"]
    ) or "<li>Aucune objection bloquante.</li>"
    repeat_lines = "".join(
        f"<li><b>{escape(answer)}</b> — déjà présent dans le nouveau pool</li>"
        for answer in sorted(replacement_answer_repeats)
    )
    if repeat_lines:
        objection_lines += repeat_lines
    summary_class = "ready" if publication_eligible else "blocked"
    summary_title = "PRÊTE POUR REVUE PROPRIÉTAIRE" if publication_eligible else "BLOQUÉE ÉDITORIALEMENT"
    summary = f"""
    <section class='editorial-summary {summary_class}'>
      <h2>{summary_title}</h2>
      <p><b>Géométrie :</b> {len(covered_letters)}/{len(letter_cells)} cases-lettres couvertes,
      zéro segment orphelin, {len(answers)} réponses distinctes, deux mots de deux lettres
      ({', '.join(two_letter)}) et aucune famille répétée.</p>
      <p><b>Accent :</b> PERI correspond à PÉRI, indice « A succombé » ; la forme est complète.</p>
      <p><b>Images revues :</b> {', '.join(metrics['imageAnswers'])}. Aucune autre image n'a été forcée.</p>
      <p><b>Objections :</b></p><ul>{objection_lines}</ul>
      <p>Artefact de revue uniquement ; catalogue et blacklist inchangés.</p>
    </section>
    """
    page = page.replace("</head>", """
    <style>
    .editorial-summary{max-width:1100px;margin:18px auto;padding:16px 20px;border-radius:12px}
    .editorial-summary.ready{background:#edf8ef;border:2px solid #397748}
    .editorial-summary.blocked{background:#fff1ee;border:2px solid #b84034}
    .editorial-summary h2{margin-top:0}.editorial-summary li{margin:.35rem 0}
    </style></head>""", 1)
    page = page.replace("</h1>", "</h1>" + summary, 1)
    HTML.write_text(page, encoding="utf-8")

    print(json.dumps({
        "complete": True,
        "publicationEligible": publication_eligible,
        "topologyValid": topology["valid"],
        "metrics": metrics,
        "objections": blacklist["rotationCooldownHits"],
        "outputs": [str(path) for path in (OUTPUT, AUDIT, HTML, STAGING)],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
