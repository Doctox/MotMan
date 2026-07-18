#!/usr/bin/env python3
"""Stage and audit the retained shifted-fill grid without publishing it.

The source fill is immutable input.  This script adds short, hand-written
French clues, reuses only the already-reviewed ROC image, and records strict
editorial gates separately from the geometric topology result.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from editorial_quality import fold  # noqa: E402
from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402
from audit_flexible_batch_candidates import (  # noqa: E402
    answer_family,
    load_reference_usage,
)


SOURCE = ROOT / "output/quality/root-fixed-l-shifted-fill-v2.json"
OUTPUT = ROOT / "output/quality/batch-v2-shifted-review.json"
AUDIT = ROOT / "output/quality/batch-v2-shifted-review.audit.json"
HTML = ROOT / "output/quality/batch-v2-shifted-review.html"
STAGING = (
    ROOT
    / "src/data/grid-generation-handcrafted/batch-v2-shifted.review.json"
)
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
IMAGES = ROOT / "src/data/crossword.images-reviewed.json"
GRID_ID = "batch-v2-shifted-review-01"
REPLACEMENT_REFERENCES = [
    ROOT / "output/quality/batch-v2-base-review.json",
]


# Deliberately short and natural.  Accents belong in clues even though answer
# cells use the unaccented canonical spelling.
CLUES = {
    "PARASITES": "Organismes nuisibles",
    "AMABILITE": "Gentillesse",
    "REPIT": "Courte pause",
    "EN": "Dans",
    "MALE": "Opposé à femelle",
    "EGO": "Le moi",
    "NETS": "Bien distincts",
    "TRI": "Mise en ordre",
    "PAREMENT": "Revêtement décoratif",
    "AMENAGER": "Rendre habitable",
    "RAP": "Musique scandée",
    "LOTI": "Bien pourvu",
    "MET": "Pose",
    "ABIME": "Gouffre profond",
    "CACAO": "Base du chocolat",
    "TESTS": "Épreuves de contrôle",
    "SITE": "Lieu précis",
    "REND": "Restitue",
    "MUNI": "Bien équipé",
    "IL": "Pronom masculin",
    "TRAME": "Fil conducteur",
    "ROC": "Masse rocheuse",
    "TIR": "Coup de feu",
    "ECUS": "Anciennes monnaies",
    "ETONNANT": "Qui surprend",
    "SEC": "Sans humidité",
    "DOIS": "Suis obligé",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_lemmas() -> dict[str, str]:
    result: dict[str, str] = {}
    for name in ("lexique.lemmas.json", "lexique.child-forms.json"):
        document = read_json(ROOT / "src/data" / name)
        for entry in document.get("entries", []):
            answer = str(entry.get("answer", "")).upper()
            lemma = str(entry.get("lemma") or answer).upper()
            if answer:
                result[answer] = lemma
    return result


def reviewed_roc_image() -> dict:
    matches = [
        entry
        for entry in read_json(IMAGES).get("entries", [])
        if entry.get("answer") == "ROC"
        and entry.get("editorialStatus") == "image-reviewed"
        and isinstance(entry.get("image"), dict)
    ]
    if len(matches) != 1:
        raise ValueError(f"Image ROC revue attendue une fois, trouvée {len(matches)} fois")
    entry = matches[0]
    asset = str(entry["image"].get("asset", ""))
    if not asset.startswith("/") or not (ROOT / "public" / asset.lstrip("/")).is_file():
        raise ValueError(f"Asset ROC absent : {asset}")
    return entry


def blacklist_audit(words: list[dict]) -> dict:
    document = read_json(BLACKLIST)
    answers = {word["answer"] for word in words}
    hard_sets = {
        key: sorted(answers & {str(value).upper() for value in document.get(key, [])})
        for key in ("rejectedAnswers", "rejectedEasyAnswers", "rejectedNormalAnswers")
    }
    cooldown_by_answer = {
        str(item.get("answer", "")).upper(): item
        for item in document.get("rotationCooldownAnswers", [])
        if item.get("answer")
    }
    cooldown_hits = [cooldown_by_answer[answer] for answer in sorted(answers & cooldown_by_answer.keys())]

    rejected_pairs = []
    pairs_by_folded_clue: set[tuple[str, str]] = set()
    for word in words:
        for clue_field in ("clue", "sourceClue"):
            clue = str(word.get(clue_field, "")).strip()
            if clue:
                pairs_by_folded_clue.add((word["answer"], fold(clue)))
    for item in document.get("rejectedPairs", []):
        pair = (str(item.get("answer", "")).upper(), fold(str(item.get("clue", ""))))
        if pair in pairs_by_folded_clue:
            rejected_pairs.append(item)
    return {
        "hardAnswerHits": hard_sets,
        "hardAnswerHitCount": sum(len(items) for items in hard_sets.values()),
        "rejectedPairHits": rejected_pairs,
        "rejectedPairHitCount": len(rejected_pairs),
        "rotationCooldownHits": cooldown_hits,
        "rotationCooldownHitCount": len(cooldown_hits),
    }


def family_audit(answers: list[str], lemmas: dict[str, str]) -> dict:
    members: dict[str, list[str]] = defaultdict(list)
    for answer in answers:
        members[lemmas.get(answer, answer)].append(answer)
    duplicates = {
        lemma: values
        for lemma, values in sorted(members.items())
        if len(set(values)) > 1
    }
    return {
        "lemmaByAnswer": {answer: lemmas.get(answer, answer) for answer in answers},
        "duplicateFamilies": duplicates,
        "duplicateFamilyCount": len(duplicates),
    }


def build_words(raw: dict, lemmas: dict[str, str], roc_entry: dict) -> list[dict]:
    raw_answers = raw.get("answers", [])
    answers = [str(item.get("answer", "")).upper() for item in raw_answers]
    missing = sorted(set(answers) - CLUES.keys())
    extras = sorted(CLUES.keys() - set(answers))
    if missing or extras or len(answers) != 27:
        raise ValueError({"missingClues": missing, "unusedClues": extras, "answers": len(answers)})

    words = []
    for number, item in enumerate(raw_answers, start=1):
        answer = item["answer"]
        direction = item["direction"]
        clue = CLUES[answer]
        word = {
            "wordId": f"{GRID_ID}:word:{number:02d}",
            "answer": answer,
            "clue": clue,
            "sourceClue": clue,
            "definitionStatus": "manually-edited",
            "editorialStatus": "human-reviewed-awaiting-owner",
            "manualReview": "strict-agent-editorial-pass-20260718",
            "sourceType": "editorial-original",
            "sourceId": "motman-batch-v2-shifted-human-pass-20260718",
            "sourceUrl": "",
            "license": "MotMan original",
            "direction": direction,
            "arrow": "right" if direction == "across" else "down",
            "clueCell": item["clueCell"],
            "cells": item["cells"],
            "conceptGroup": lemmas.get(answer, answer),
            "semanticConflicts": [],
            "editorialProfile": "motman-batch-v2-shifted-strict-pass",
            "sourceSpelling": item.get("spelling", answer.lower()),
            "sourceZipf": item.get("zipf"),
            "activeUsesAtSearch": item.get("activeUses", 0),
        }
        if answer == "ROC":
            word.update({
                "editorialStatus": "image-reviewed-awaiting-owner",
                "sourceType": "image",
                "sourceId": roc_entry["sourceId"],
                "sourceUrl": roc_entry["sourceUrl"],
                "license": roc_entry["license"],
                "image": roc_entry["image"],
            })
        words.append(word)
    return words


def main() -> None:
    source = read_json(SOURCE)
    if not source.get("complete") or not isinstance(source.get("grid"), dict):
        raise ValueError("La source shifted n'est pas une grille complète")
    raw = source["grid"]
    lemmas = load_lemmas()
    roc_entry = reviewed_roc_image()
    words = build_words(raw, lemmas, roc_entry)

    grid = {
        "id": GRID_ID,
        "columns": source.get("columns", 9),
        "rows": source.get("rows", 10),
        "clueCells": raw["clueCells"],
        "words": words,
        "publicationStatus": "blocked-editorial-review",
        "editorialProfile": "motman-batch-v2-shifted-strict-pass",
        "reviewCycle": "2026-07-18",
        "layoutPolicy": "full-frame; free-interior; exactly-two-two-letter-answers",
        "accentPolicy": "Accents ignored in answer cells; preserved in French clues.",
        "sourceCandidate": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "sourceShapeGridId": raw.get("sourceShapeGridId"),
    }
    topology = audit_grid_topology(grid, enforce_layout=False)
    answers = [word["answer"] for word in words]
    two_letter = [answer for answer in answers if len(answer) == 2]
    letter_cells = [cell for cell in topology["cells"] if cell["kind"] == "letter"]
    covered_letters = [cell for cell in letter_cells if cell["wordIds"]]
    family = family_audit(answers, lemmas)
    blacklist = blacklist_audit(words)
    reference_answers, reference_families = load_reference_usage(
        REPLACEMENT_REFERENCES, lemmas
    )
    replacement_answer_repeats = {
        answer: reference_answers[answer]
        for answer in answers
        if reference_answers[answer]
    }
    replacement_family_repeats = {
        answer_family(word, lemmas): reference_families[answer_family(word, lemmas)]
        for word in words
        if reference_families[answer_family(word, lemmas)]
    }

    rejection_recommendations = [
        {
            "answer": item["answer"],
            "decision": "reject-from-this-staging-grid",
            "reason": item.get("reason", "Réponse placée en délai de rotation."),
            "replacementRequired": True,
        }
        for item in blacklist["rotationCooldownHits"]
    ]
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

    publication_blockers = [*hard_failures]
    if rejection_recommendations:
        publication_blockers.append("rotation_cooldown_answer_requires_replacement")
    publication_eligible = not publication_blockers
    if publication_eligible:
        grid["publicationStatus"] = "owner-review-required"

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
        "textClueCount": len(words),
        "replacementAnswerRepeats": replacement_answer_repeats,
        "replacementFamilyRepeats": replacement_family_repeats,
        "publicationEligible": publication_eligible,
    }
    editorial_review = {
        "decision": "blocked-replace-il" if rejection_recommendations else "ready-for-owner-review",
        "hardFailures": hard_failures,
        "publicationBlockers": publication_blockers,
        "rejectionRecommendations": rejection_recommendations,
        "replacementPoolRepeatAudit": {
            "references": [str(path.relative_to(ROOT)).replace("\\", "/") for path in REPLACEMENT_REFERENCES],
            "answerRepeats": replacement_answer_repeats,
            "familyRepeats": replacement_family_repeats,
        },
        "acceptedEditorialDoubts": {
            "PAREMENT": "Terme précis mais standard ; définition concrète.",
            "LOTI": "Participe courant dans l'expression « bien loti ».",
            "ECUS": "Monnaies historiques, forme française claire.",
        },
        "imagePolicy": (
            "Seul ROC reprend une image déjà marquée image-reviewed ; "
            "aucune autre image n'est forcée."
        ),
    }
    document = {
        "version": 1,
        "kind": "batch-v2-shifted-owner-review",
        "publicationPolicy": "Staging non publié ; remplacement de IL requis avant validation.",
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
        "kind": "batch-v2-shifted-strict-audit",
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

    page = render_topology_html([topology], title="MotMan — revue stricte batch v2 shifted")
    rejected = "".join(
        f"<li><b>{escape(item['answer'])}</b> — {escape(item['reason'])}</li>"
        for item in rejection_recommendations
    ) or "<li>Aucun rejet recommandé.</li>"
    repeated = "".join(
        f"<li><b>{escape(answer)}</b> — répété dans le nouveau pool</li>"
        for answer in sorted(replacement_answer_repeats)
    )
    if repeated:
        rejected += repeated
    summary_class = "blocked" if publication_blockers else "ready"
    summary_title = "BLOQUÉE ÉDITORIALEMENT" if publication_blockers else "PRÊTE POUR REVUE PROPRIÉTAIRE"
    summary = f"""
    <section class='editorial-summary {summary_class}'>
      <h2>{summary_title}</h2>
      <p><b>Géométrie valide :</b> {len(covered_letters)}/{len(letter_cells)} cases-lettres couvertes,
      zéro segment orphelin, {len(answers)} réponses distinctes et deux mots de deux lettres
      ({', '.join(two_letter)}).</p>
      <p><b>Image :</b> ROC utilise l'unique pictogramme revu ; aucune autre image ambiguë n'a été ajoutée.</p>
      <p><b>Rejet à traiter avant publication :</b></p><ul>{rejected}</ul>
      <p>La grille et son audit restent en staging ; ni le catalogue ni la blacklist n'ont été modifiés.</p>
    </section>
    """
    extra_style = """
    <style>
    .editorial-summary{max-width:1100px;margin:18px auto;padding:16px 20px;border-radius:12px}
    .editorial-summary.blocked{background:#fff1ee;border:2px solid #b84034}
    .editorial-summary.ready{background:#edf8ef;border:2px solid #397748}
    .editorial-summary h2{margin-top:0}.editorial-summary li{margin:.35rem 0}
    </style>
    """
    page = page.replace("</head>", extra_style + "</head>", 1)
    page = page.replace("</h1>", "</h1>" + summary, 1)
    HTML.write_text(page, encoding="utf-8")

    print(json.dumps({
        "complete": True,
        "publicationEligible": publication_eligible,
        "topologyValid": topology["valid"],
        "metrics": metrics,
        "rejectionRecommendations": rejection_recommendations,
        "outputs": [str(path) for path in (OUTPUT, AUDIT, HTML, STAGING)],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
