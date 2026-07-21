#!/usr/bin/env python3
"""Assemble manually reviewed compact 7×8 candidates for the owner checkpoint."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology  # noqa: E402


GRIDS = [
    {
        "id": "compact-7x8-agent-e-01",
        "source": "output/quality/compact-7x8-agent-e-valid-59-repair1.json",
        "clues": {
            "SEGMENT": "Morceau",
            "TRAINER": "Tirer derrière",
            "ARGENTE": "Comme l'argent",
            "TONNE": "Mille kilos",
            "UNE": "Article féminin",
            "TERMINE": "Achevé",
            "STATUT": "Position sociale",
            "ERRONE": "Inexact",
            "GAGNER": "Remporter",
            "MIEN": "À moi",
            "MAL": "Douleur",
            "ENNEMI": "Adversaire",
            "NET": "Sans bavure",
            "AN": "Douze mois",
            "TREFLE": "Plante porte-bonheur",
        },
        "images": {
            "SEGMENT": ("📏", "segment de ligne", "Segment"),
            "ARGENTE": ("🥈", "médaille argentée", "Argenté"),
            "TONNE": ("⚖️", "poids d'une tonne", "Tonne"),
            "GAGNER": ("🏆", "trophée gagné", "Gagner"),
            "ENNEMI": ("⚔️", "adversaires", "Ennemi"),
            "TREFLE": ("🍀", "trèfle vert", "Trèfle"),
        },
    },
]


def assemble(spec: dict) -> dict:
    source_path = ROOT / spec["source"]
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    answer_by_slot = {int(item["slotIndex"]): item for item in raw["answers"]}
    words = []
    for index, slot in enumerate(raw["rawSlots"]):
        answer_item = answer_by_slot[index]
        answer = answer_item["answer"]
        words.append(
            {
                "wordId": f"{spec['id']}:word:{index + 1:02d}",
                "answer": answer,
                "displayAnswer": answer_item.get("spelling", answer.lower()),
                "clue": spec["clues"][answer],
                "direction": slot["direction"],
                "arrow": slot["arrow"],
                "clueCell": slot["clueCell"],
                "cells": slot["cells"],
                "source": "agent-manual-common-fr",
                "editorialStatus": "agent-reviewed",
            }
        )
    grid = {
        "id": spec["id"],
        "columns": int(raw["columns"]),
        "rows": int(raw["rows"]),
        "sourceShapeId": raw["sourceShapeId"],
        "sourceCandidate": spec["source"],
        "clueCells": raw["clueCells"],
        "rawSlots": raw["rawSlots"],
        "words": words,
        "answers": [
            {
                **answer,
                "definition": spec["clues"][answer["answer"]],
                "imageCandidate": answer["answer"] in spec["images"],
            }
            for answer in raw["answers"]
        ],
        "imageAnswers": [
            {"answer": answer, "emoji": image[0], "concept": image[1], "alt": image[2]}
            for answer, image in spec["images"].items()
        ],
    }
    report = audit_grid_topology(grid, enforce_layout=False)
    isolated = [item for item in report["errors"] if item["code"] == "isolated_clue"]
    grid["geometryAudit"] = {
        "valid": report["valid"],
        "errorCount": len(report["errors"]),
        "orphanLetters": sum(item["code"] == "orphan_letter" for item in report["errors"]),
        "orphanSegments": sum(item["code"] == "orphan_segment" for item in report["errors"]),
        "isolatedClues": len(isolated),
    }
    if not report["valid"]:
        raise SystemExit(json.dumps(report["errors"], ensure_ascii=False, indent=2))
    return grid


def main() -> int:
    grids = [assemble(spec) for spec in GRIDS]
    output = {
        "version": 1,
        "kind": "compact-7x8-agent-e-review",
        "catalogModified": False,
        "publicationEligible": False,
        "reviewStatus": "agent-reviewed-awaiting-owner",
        "constraints": {
            "dimensions": "7x8",
            "fullTopAndLeftDefinitionFrame": True,
            "minimumImages": 6,
            "maximumTwoLetterAnswers": 2,
            "noOrphanLetters": True,
            "referenceForRepetition": "output/quality/compact-7x8-agent-c.json",
        },
        "grids": grids,
    }
    destination = ROOT / "output/quality/compact-7x8-agent-e.json"
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(destination), "grids": len(grids)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
