"""Build five reproducible 9x10 silhouettes whose answers all have 3+ letters."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from optimize_grid_shapes import optimize  # noqa: E402


OUTPUT = ROOT / "output/quality/no-two-shape-library.json"
TARGET_CLUE_COUNTS = (20, 21, 22, 23, 24)
BASE_SEED = 410_000


def as_template(shape: dict, number: int) -> dict:
    return {
        "id": f"no-two-shape-{number:02d}",
        "columns": shape["columns"],
        "rows": shape["rows"],
        "clueCells": shape["clueCells"],
        "lengthProfile": shape["metrics"]["lengths"],
        "shapeMetrics": shape["metrics"],
        "words": [
            {
                "wordId": f"no-two-shape-{number:02d}:slot:{slot_number:02d}",
                "answer": "X" * slot["length"],
                "clue": "Gabarit",
                "direction": slot["direction"],
                "arrow": slot["arrow"],
                "clueCell": slot["clue"],
                "cells": slot["cells"],
            }
            for slot_number, slot in enumerate(shape["slots"], 1)
        ],
    }


def main() -> None:
    active = json.loads(
        (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
    )
    previous_shapes = [
        {tuple(cell) for cell in grid["clueCells"]}
        for grid in active.get("grids", [])
    ]
    selected = []
    for number, visible_clues in enumerate(TARGET_CLUE_COUNTS, 1):
        shape = None
        used_seed = None
        for attempt in range(20):
            seed = BASE_SEED + number * 100 + attempt
            rng = random.Random(seed)
            shape = optimize(
                timeout=4,
                seed=seed,
                visible_clue_cells=visible_clues,
                minimum_double_clues=2,
                maximum_double_clues=6,
                maximum_adjacent_clues=2,
                only_direct_arrows=True,
                maximum_length_two_answers=0,
                require_length_bands=True,
                enforce_length_balance=False,
                enforce_clue_spacing=False,
                enforce_interior_line_limits=True,
                enforce_clue_triples=True,
                enforce_solid_clue_blocks=True,
                full_definition_frame=True,
                minimum_border_clues=2,
                columns=9,
                rows=10,
                short_answer_penalty=100,
                position_penalties={
                    (row, col): rng.randint(0, 8)
                    for row in range(1, 10) for col in range(1, 9)
                },
                previous_shapes=previous_shapes,
                maximum_shape_overlap=19,
            )
            if shape is not None:
                used_seed = seed
                break
        if shape is None:
            raise SystemExit(f"Silhouette {number}: aucune solution bornée")
        if min(slot["length"] for slot in shape["slots"]) < 3:
            raise ValueError(f"Silhouette {number}: réponse de moins de 3 lettres")
        shape["acceptedSeed"] = used_seed
        selected.append(as_template(shape, number))
        previous_shapes.append({tuple(cell) for cell in shape["clueCells"]})

    document = {
        "version": 1,
        "kind": "no-two-answer-shape-library",
        "minimumAnswerLength": 3,
        "activeShapeExclusion": True,
        "grids": selected,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "output": str(OUTPUT),
        "grids": len(selected),
        "slots": sum(len(grid["words"]) for grid in selected),
        "lengthProfiles": [grid["lengthProfile"] for grid in selected],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
