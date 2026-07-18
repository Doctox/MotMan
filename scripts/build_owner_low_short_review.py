"""Build the second owner-review grid, capped at two two-letter answers."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402
from agent_editorialize_shifted import family_audit, load_lemmas  # noqa: E402


RAW = ROOT / "output/quality/common-flex-editorial-c-refill.json"
STAGING = ROOT / "src/data/grid-generation-handcrafted/owner-low-short-02.review.json"
AUDIT = ROOT / "output/quality/owner-low-short-02.audit.json"
HTML = ROOT / "output/quality/owner-low-short-02.html"
GRID_ID = "owner-low-short-02"

CLUES = {
    "RESSENTIE": "Éprouvée",
    "EMEUTIERS": "Fauteurs de trouble",
    "GEMIR": "Se plaindre",
    "ARETES": "Os de poisson",
    "RA": "Dieu égyptien",
    "DUR": "Pas tendre",
    "EDIT": "Décret royal",
    "SET": "Manche de tennis",
    "REGARDES": "Observes",
    "EMERAUDE": "Pierre verte",
    "SEME": "Disperse des graines",
    "RIT": "Trouve drôle",
    "SUITE": "Enchaînement",
    "FLUOR": "Dans les dentifrices",
    "BOSSU": "Dos courbé",
    "ETRE": "Exister",
    "AOUT": "Mois d'été",
    "TRIO": "Groupe de trois",
    "NI": "Pas davantage",
    "SALTO": "Saut retourné",
    "SOT": "Peu malin",
    "TES": "Possessif pluriel",
    "OURS": "Animal des forêts",
    "IROQUOIS": "Peuple amérindien",
    "EST": "Point cardinal",
    "TROU": "Ouverture",
}


def build_grid(raw: dict) -> dict:
    if not raw.get("complete") or not raw.get("grid"):
        raise ValueError("Remplissage source incomplet")
    source = raw["grid"]
    answers = source["answers"]
    words = []
    for number, item in enumerate(answers, start=1):
        answer = item["answer"]
        clue = CLUES.get(answer, "").strip()
        if not clue:
            raise ValueError(f"Définition absente : {answer}")
        direction = item["direction"]
        words.append({
            "wordId": f"{GRID_ID}:word:{number:02d}",
            "answer": answer,
            "clue": clue,
            "sourceClue": clue,
            "definitionStatus": "manually-edited",
            "editorialStatus": "human-reviewed-awaiting-owner",
            "manualReview": "reviewed-awaiting-owner",
            "sourceType": "editorial-original",
            "sourceId": "motman-low-short-human-pass-20260718",
            "sourceUrl": "",
            "license": "MotMan original",
            "direction": direction,
            "arrow": "right" if direction == "across" else "down",
            "clueCell": item["clueCell"],
            "cells": item["cells"],
            "editorialProfile": "motman-low-short-human-pass",
        })
    return {
        "id": GRID_ID,
        "columns": 9,
        "rows": 10,
        "clueCells": source["clueCells"],
        "words": words,
        "publicationStatus": "owner-review-required",
        "editorialProfile": "motman-low-short-human-pass",
        "reviewCycle": "2026-07-18",
        "layoutPolicy": "full-frame; free-interior; maximum-two-two-letter-answers",
        "accentPolicy": "Accents ignored in answer cells; preserved in French clues.",
    }


def main() -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    grid = build_grid(raw)
    report = audit_grid_topology(grid, enforce_layout=False)
    if not report["valid"]:
        raise ValueError(report["errors"])

    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    rejected = {answer.upper() for answer in blacklist.get("rejectedAnswers", [])}
    blacklisted = [word["answer"] for word in grid["words"] if word["answer"] in rejected]
    if blacklisted:
        raise ValueError(f"Réponses blacklistées : {blacklisted}")

    answers = [word["answer"] for word in grid["words"]]
    families = family_audit(answers, load_lemmas())
    two_letter = [answer for answer in answers if len(answer) == 2]
    if len(two_letter) > 2:
        raise ValueError(f"Trop de réponses de deux lettres : {two_letter}")
    letter_cells = [cell for cell in report["cells"] if cell["kind"] == "letter"]
    metrics = {
        "dimensions": "9x10",
        "totalCells": len(report["cells"]),
        "letterCells": len(letter_cells),
        "coveredLetterCells": sum(bool(cell["wordIds"]) for cell in letter_cells),
        "orphanLetters": sum(not cell["wordIds"] for cell in letter_cells),
        "orphanSegments": len(report["orphanSegments"]),
        "answers": len(answers),
        "uniqueAnswers": len(set(answers)),
        "twoLetterAnswers": two_letter,
        "lengthProfile": dict(sorted(Counter(map(len, answers)).items())),
        "topologyValid": report["valid"],
        "duplicateFamilies": families["duplicateFamilies"],
        "duplicateFamilyCount": families["duplicateFamilyCount"],
        "accentPolicyExamples": {"CHÊNE": "CHENE", "ÉMERAUDE": "EMERAUDE", "AOÛT": "AOUT"},
    }
    document = {
        "version": 1,
        "kind": "owner-low-short-grid-review",
        "publicationPolicy": "Quarantaine ; famille lexicale répétée dans la grille.",
        "metrics": metrics,
        "grids": [grid],
    }
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    AUDIT.write_text(json.dumps({
        "version": 1,
        "valid": not families["duplicateFamilies"],
        "catalogModified": False,
        "hardFailures": (
            ["duplicate_lemma_families"] if families["duplicateFamilies"] else []
        ),
        "metrics": metrics,
        "grids": [report],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    page = render_topology_html(
        [report], title="MotMan — grille avec seulement deux mots de 2 lettres"
    )
    summary = (
        '<section style="max-width:1100px;margin:18px auto;padding:14px 18px;'
        'background:#fff1ee;border:2px solid #b84034;border-radius:10px">'
        '<b>QUARANTAINE — famille lexicale répétée</b><br>'
        f'{len(answers)} réponses · seulement {len(two_letter)} mots de deux lettres '
        f'({", ".join(two_letter)}) · {len(letter_cells)} cases-lettres couvertes '
        '· zéro lettre orpheline.<br>'
        f'Répétition bloquante : {families["duplicateFamilies"]}.<br>'
        'Les accents sont ignorés dans les cases : CHÊNE = CHENE, ÉMERAUDE = EMERAUDE.'
        '</section>'
    )
    page = page.replace("</h1>", "</h1>" + summary, 1)
    HTML.write_text(page, encoding="utf-8")
    print(json.dumps({
        "complete": True,
        "catalogModified": False,
        "metrics": metrics,
        "html": str(HTML),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
