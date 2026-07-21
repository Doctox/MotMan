#!/usr/bin/env python3
"""Assemble the duplicate-free editorial core for the current young batch."""
from __future__ import annotations

import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/quality/compact-7x8-young-current-raw-ten.json"
SELECTIONS = (
    ("compact-7x8-young-current-open-i.json", "NEMO"),
    ("compact-7x8-young-current-open-j.json", "MARVEL"),
    ("compact-7x8-young-current-open-k.json", "SPOTIFY"),
    ("compact-7x8-young-current-open-l.json", "INOXTAG"),
    ("compact-7x8-young-current-target-tiktok.json", "TIKTOK"),
    ("compact-7x8-young-current-target-pikachu.json", "PIKACHU"),
    ("compact-7x8-young-current-final-three-raw.json", "MATRIX"),
    ("compact-7x8-young-current-replacement-selfie.json", "SELFIE"),
    ("compact-7x8-young-current-final-map.json", "MAP"),
    ("compact-7x8-young-current-tenth-plain-3.json", None),
)


def main() -> None:
    selected = []
    seen_answers: set[str] = set()
    for filename, anchor in SELECTIONS:
        document = json.loads(
            (ROOT / "output/quality" / filename).read_text(encoding="utf-8")
        )
        matches = [
            grid for grid in document.get("grids", [])
            if grid.get("fixedPopAnswer") == anchor
        ]
        if len(matches) != 1:
            raise ValueError(f"{filename}: candidat {anchor} introuvable")
        grid = copy.deepcopy(matches[0])
        answers = {item["answer"] for item in grid["answers"]}
        repeated = sorted(answers & seen_answers)
        if repeated:
            raise ValueError(f"Répétitions dans le noyau: {repeated}")
        seen_answers.update(answers)
        grid["id"] = f"compact-7x8-young-current-core-{len(selected) + 1:02d}"
        selected.append(grid)

    payload = {
        "version": 1,
        "kind": "compact-7x8-young-current-core",
        "catalogModified": False,
        "grids": selected,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"grids": len(selected), "answers": len(seen_answers)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
