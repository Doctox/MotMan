#!/usr/bin/env python3
"""Build an owner-review batch from manually reviewed strict-frame fills."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--html", type=Path, required=True)
    return parser.parse_args()


def load_candidate(path: Path, seed: int | None) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("rawCandidates"):
        if seed is None:
            raise ValueError(f"sourceSeed requis pour {path}")
        return next(
            item for item in document["rawCandidates"]
            if int(item.get("seed", -1)) == seed
        )
    if document.get("answers") and document.get("rawSlots"):
        return document
    raise ValueError(f"Aucun candidat exploitable dans {path}")


def image_index() -> dict[str, dict]:
    path = ROOT / "src/data/crossword.images-reviewed.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        item["answer"]: item
        for item in document.get("entries", [])
        if item.get("answer") and isinstance(item.get("image"), dict)
    }


def blacklist_index() -> tuple[set[str], set[tuple[str, str]]]:
    path = ROOT / "src/data/editorial.blacklist.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    answers = set(document.get("rejectedAnswers", []))
    pairs = {
        (item.get("answer", ""), item.get("clue", ""))
        for item in document.get("rejectedPairs", [])
    }
    return answers, pairs


def active_usage() -> Counter:
    path = ROOT / "src/data/grid.catalog.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    return Counter(
        word["answer"]
        for grid in document.get("grids", [])
        for word in grid.get("words", [])
    )


def build_grid(item: dict, images: dict[str, dict]) -> dict:
    grid_id = item["id"]
    source = ROOT / item["source"]
    candidate = load_candidate(source, item.get("sourceSeed"))
    columns = int(candidate.get("columns", item.get("columns", 9)))
    rows = int(candidate.get("rows", item.get("rows", 10)))
    clues = item.get("clues", {})
    image_answers = set(item.get("imageAnswers", []))
    if len(image_answers) < 6:
        raise ValueError(f"{grid_id}: six images minimum requises")
    missing_images = image_answers - set(images)
    if missing_images:
        raise ValueError(f"{grid_id}: images manquantes {sorted(missing_images)}")

    words = []
    for number, answer_item in enumerate(candidate["answers"], 1):
        slot = candidate["rawSlots"][answer_item["slotIndex"]]
        answer = answer_item["answer"]
        image_entry = images.get(answer) if answer in image_answers else None
        clue = "" if image_entry else str(clues.get(answer, "")).strip()
        if not clue and image_entry is None:
            raise ValueError(f"{grid_id}: définition absente pour {answer}")
        word = {
            "wordId": f"{grid_id}:word:{number:02d}",
            "answer": answer,
            "clue": clue,
            "sourceClue": image_entry["sourceClue"] if image_entry else clue,
            "definitionStatus": "image-reviewed" if image_entry else "manually-edited",
            "editorialStatus": "human-reviewed-awaiting-owner",
            "manualReview": "reviewed-awaiting-owner",
            "sourceType": "image" if image_entry else "editorial-original",
            "sourceId": image_entry["sourceId"] if image_entry else item.get(
                "sourceId", "motman-professional-batch-20260718"
            ),
            "sourceUrl": image_entry.get("sourceUrl", "") if image_entry else (
                "internal://motman/editorial/strict-frame-professional-batch"
            ),
            "license": image_entry.get("license", "") if image_entry else "MotMan original",
            "direction": slot["direction"],
            "arrow": "right" if slot["direction"] == "across" else "down",
            "clueCell": slot["clueCell"],
            "cells": slot["cells"],
            "conceptGroup": answer_item.get("lemma", answer),
            "semanticConflicts": [],
            "editorialProfile": "assisted-human-professional-pass",
        }
        if image_entry:
            word["image"] = image_entry["image"]
        words.append(word)

    return {
        "id": grid_id,
        "columns": columns,
        "rows": rows,
        "clueCells": candidate["clueCells"],
        "words": words,
        "publicationStatus": "owner-review-required",
        "editorialProfile": "assisted-human-professional-pass",
        "reviewCycle": item.get("reviewCycle", "2026-07-18"),
        "layoutPolicy": item.get(
            "layoutPolicy", "strict full frame; no orphan letters"
        ),
        "accentPolicy": "Accents ignored in answer cells; preserved in French clues.",
        "sourceShapeId": candidate.get("sourceShapeId", item.get("sourceShapeId", "")),
        "constructorSeed": item.get("sourceSeed"),
    }


def validate_grid(grid: dict, rejected: set[str], rejected_pairs: set[tuple[str, str]]) -> tuple[dict, dict]:
    report = audit_grid_topology(grid, enforce_layout=False)
    if not report["valid"]:
        raise ValueError(f"{grid['id']}: {report['errors']}")
    expected_frame = {
        *((0, column) for column in range(grid["columns"])),
        *((row, 0) for row in range(1, grid["rows"])),
    }
    if not expected_frame.issubset({tuple(cell) for cell in grid["clueCells"]}):
        raise ValueError(f"{grid['id']}: cadre supérieur/gauche incomplet")
    answers = [word["answer"] for word in grid["words"]]
    if len(answers) != len(set(answers)):
        raise ValueError(f"{grid['id']}: réponse répétée dans la grille")
    blocked = sorted(set(answers) & rejected)
    if blocked:
        raise ValueError(f"{grid['id']}: réponses blacklistées {blocked}")
    blocked_pairs = [
        (word["answer"], word["clue"])
        for word in grid["words"]
        if (word["answer"], word["clue"]) in rejected_pairs
    ]
    if blocked_pairs:
        raise ValueError(f"{grid['id']}: couples blacklistés {blocked_pairs}")
    letter_cells = [cell for cell in report["cells"] if cell["kind"] == "letter"]
    metrics = {
        "answers": len(answers),
        "uniqueAnswers": len(set(answers)),
        "letterCells": len(letter_cells),
        "coveredLetterCells": sum(bool(cell["wordIds"]) for cell in letter_cells),
        "orphanLetters": sum(not cell["wordIds"] for cell in letter_cells),
        "orphanSegments": len(report["orphanSegments"]),
        "twoLetterAnswers": [answer for answer in answers if len(answer) == 2],
        "threeLetterAnswers": [answer for answer in answers if len(answer) == 3],
        "lengthProfile": dict(sorted(Counter(map(len, answers)).items())),
        "imageAnswers": sorted(word["answer"] for word in grid["words"] if word.get("image")),
        "topologyValid": True,
    }
    metrics["imageCount"] = len(metrics["imageAnswers"])
    return report, metrics


def main() -> None:
    args = parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    images = image_index()
    rejected, rejected_pairs = blacklist_index()
    usage = active_usage()
    grids = [build_grid(item, images) for item in spec.get("grids", [])]
    reports = []
    metrics = []
    batch_answers: set[str] = set()
    for grid in grids:
        report, item_metrics = validate_grid(grid, rejected, rejected_pairs)
        overlap = batch_answers & {word["answer"] for word in grid["words"]}
        if overlap:
            raise ValueError(f"Répétitions entre nouvelles grilles : {sorted(overlap)}")
        batch_answers.update(word["answer"] for word in grid["words"])
        item_metrics["activeRepeats"] = {
            word["answer"]: usage[word["answer"]]
            for word in grid["words"] if usage[word["answer"]]
        }
        reports.append(report)
        metrics.append({"gridId": grid["id"], **item_metrics})

    document = {
        "version": 1,
        "kind": "strict-frame-professional-owner-review-batch",
        "catalogModified": False,
        "publicationEligible": False,
        "grids": grids,
        "metrics": metrics,
    }
    args.staging.parent.mkdir(parents=True, exist_ok=True)
    args.staging.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(
        json.dumps({"version": 1, "valid": True, "metrics": metrics, "grids": reports}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    page = render_topology_html(reports, title=spec.get("title", "MotMan — lot professionnel à relire"))
    summary = (
        '<section style="max-width:1100px;margin:18px auto;padding:14px 18px;'
        'background:#edf7f2;border:2px solid #247052;border-radius:10px">'
        f'<b>À VALIDER — {len(grids)} nouvelles grilles</b><br>'
        'Toutes les cases-lettres sont couvertes, aucune grille n’est publiée, '
        'et chaque grille contient au moins six images relues.'
        '</section>'
    )
    args.html.parent.mkdir(parents=True, exist_ok=True)
    args.html.write_text(page.replace("</h1>", "</h1>" + summary, 1), encoding="utf-8")
    print(json.dumps({"complete": True, "grids": len(grids), "metrics": metrics, "html": str(args.html)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
