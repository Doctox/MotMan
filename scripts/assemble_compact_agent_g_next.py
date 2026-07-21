#!/usr/bin/env python3
"""Append the next manually reviewed compact 7x8 grid to agent G's batch."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology  # noqa: E402


SOURCE = ROOT / "output/quality/compact-7x8-agent-g-at-raw.json"
DESTINATION = ROOT / "output/quality/compact-7x8-agent-g.json"
GRID_ID = "compact-7x8-agent-g-02"

CLUES = {
    "BAISSER": "Descendre",
    "ANNUITE": "Versement annuel",
    "REDITES": "Répétitions",
    "IMITENT": "Font pareil",
    "LIEE": "Attachée",
    "SENSEES": "Raisonnables",
    "BARILS": "Grands tonneaux",
    "ANEMIE": "Manque de fer",
    "INDIEN": "De l'Inde",
    "SUITES": "Conséquences",
    "SITE": "Espace web",
    "DE": "Préposition",
    "ETENDE": "Qu'il déploie",
    "RESTES": "Tu demeures",
}

IMAGES = {
    "BAISSER": ("⬇️", "flèche dirigée vers le bas", "Baisser"),
    "IMITENT": ("👯", "deux personnes dans la même pose", "Imitent"),
    "LIEE": ("🔗", "deux maillons reliés", "Liée"),
    "BARILS": ("🛢️", "baril", "Barils"),
    "ANEMIE": ("🩸", "goutte de sang", "Anémie"),
    "SITE": ("🌐", "site sur le Web", "Site"),
}


def build_grid() -> dict:
    raw = json.loads(SOURCE.read_text(encoding="utf-8"))
    if not raw.get("complete"):
        raise SystemExit("Le remplissage source n'est pas complet.")
    answer_by_slot = {int(item["slotIndex"]): item for item in raw["answers"]}
    words = []
    for index, slot in enumerate(raw["rawSlots"]):
        answer_item = answer_by_slot[index]
        answer = answer_item["answer"]
        word_id = f"{GRID_ID}:word:{index + 1:02d}"
        words.append(
            {
                "wordId": word_id,
                "slotId": slot["slotId"],
                "answer": answer,
                "spelling": answer_item.get("spelling", answer.lower()),
                "lemma": answer_item.get("lemma", answer),
                "direction": slot["direction"],
                "arrow": slot["arrow"],
                "clueCell": slot["clueCell"],
                "cells": slot["cells"],
                "length": len(slot["cells"]),
                "clue": CLUES[answer],
            }
        )

    answers = [
        {**word, "imageCandidate": word["answer"] in IMAGES}
        for word in words
    ]
    clues = [
        {
            "wordId": word["wordId"],
            "slotId": word["slotId"],
            "answer": word["answer"],
            "clue": word["clue"],
            "type": "image-candidate" if word["answer"] in IMAGES else "text",
        }
        for word in words
    ]
    grid = {
        "id": GRID_ID,
        "sourceCandidate": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "sourceShapeId": raw["sourceShapeId"],
        "columns": int(raw["columns"]),
        "rows": int(raw["rows"]),
        "clueCells": raw["clueCells"],
        "rawSlots": raw["rawSlots"],
        "words": words,
        "answers": answers,
        "clues": clues,
        "imageAnswers": [
            {"answer": answer, "concept": data[1], "alt": data[2], "emoji": data[0]}
            for answer, data in IMAGES.items()
        ],
    }
    report = audit_grid_topology(
        grid, require_word_ids=True, enforce_layout=False
    )
    grid["topologyAudit"] = report
    if not report["valid"]:
        raise SystemExit(json.dumps(report["errors"], ensure_ascii=False, indent=2))
    return grid


def main() -> int:
    document = json.loads(DESTINATION.read_text(encoding="utf-8"))
    grid = build_grid()
    grids = [item for item in document.get("grids", []) if item.get("id") != GRID_ID]
    grids.append(grid)
    document["grids"] = grids
    DESTINATION.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(DESTINATION),
                "gridId": GRID_ID,
                "answers": [item["answer"] for item in grid["words"]],
                "images": len(grid["imageAnswers"]),
                "topologyValid": grid["topologyAudit"]["valid"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
