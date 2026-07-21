#!/usr/bin/env python3
"""Apply the owner's 2026-07-19 image choices to the approved 7x8 batch."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUALITY = ROOT / "output" / "quality"


def asset(answer: str, concept: str, alt: str, filename: str) -> dict[str, str]:
    return {
        "answer": answer,
        "concept": concept,
        "alt": alt,
        "asset": f"/assets/clues/custom/{filename}",
    }


IMAGE_SELECTIONS: dict[str, list[str | dict[str, str]]] = {
    "compact-7x8-agent-c-01": [
        asset("REPASSE", "fer à repasser", "Fer à repasser", "fer-a-repasser.svg"),
        "AGE", "PICOLER", "GRAPPE", "ESCALE",
    ],
    "compact-7x8-agent-c-02": ["RUE", "MERLOT", "DON", "IVOIRE"],
    "compact-7x8-agent-e-01": [
        "ARGENTE",
        asset("TONNE", "poids de musculation", "Poids lourd", "poids-musculation.svg"),
        "GAGNER", "ENNEMI", "TREFLE",
    ],
    "compact-7x8-agent-f-01": ["EPERLAN", "IRIS", "SOL", "REMISE", "CDI"],
    "compact-7x8-agent-f-02": [
        "DESSERT", "ECOUTER", "ECOLES", "TRESOR",
    ],
    "compact-7x8-agent-f-03": [
        asset("ROMAINE", "Colisée de Rome", "Colisée", "colisee.svg"),
        "PNEU", "ESSENCE", "TRAPPE",
    ],
    "compact-7x8-agent-root-03": [
        "EVASION",
        asset("UNION", "anneaux unis", "Union", "anneaux-union.svg"),
        "REVUES", "AVENUE", "MARI",
    ],
}


SOURCE_FILES = (
    QUALITY / "compact-7x8-agent-c.json",
    QUALITY / "compact-7x8-agent-e.json",
    QUALITY / "compact-7x8-agent-f.json",
    QUALITY / "compact-7x8-agent-g.json",
    QUALITY / "compact-7x8-agent-root.json",
)


def original_image_lookup(grid: dict) -> dict[str, dict | str]:
    lookup: dict[str, dict | str] = {}
    for item in grid.get("imageAnswers", []):
        answer = item if isinstance(item, str) else item.get("answer", "")
        lookup[str(answer).upper()] = item
    return lookup


def update_grid(grid: dict) -> bool:
    grid_id = grid.get("id")
    selection = IMAGE_SELECTIONS.get(grid_id)
    if selection is None:
        return False
    originals = original_image_lookup(grid)
    resolved: list[dict | str] = []
    for item in selection:
        if isinstance(item, dict):
            resolved.append(item)
        else:
            resolved.append(originals[item])
    grid["imageAnswers"] = resolved

    if grid_id == "compact-7x8-agent-c-02":
        for answer in grid.get("answers", []):
            if answer.get("answer") == "EPUISE":
                answer["definition"] = "À bout"
        for clue in grid.get("clues", []):
            if clue.get("answer") == "EPUISE":
                clue["clue"] = "À bout"
    return True


def main() -> None:
    updated_ids: list[str] = []
    for path in SOURCE_FILES:
        document = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for grid in document.get("grids", []):
            if update_grid(grid):
                changed = True
                updated_ids.append(grid["id"])
        if changed:
            path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    missing = sorted(set(IMAGE_SELECTIONS) - set(updated_ids))
    if missing:
        raise RuntimeError(f"grilles introuvables: {missing}")
    print(json.dumps({"updated": updated_ids}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
