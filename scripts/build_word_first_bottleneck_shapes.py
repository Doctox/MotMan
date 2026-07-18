#!/usr/bin/env python3
"""Build sparse bottleneck masks for word-first 9x10 experiments.

Each mask keeps the clue frame, has no orphan segment and uses a short clue
ribbon to split the lexical problem into two weakly connected zones.  This is
deliberately different from scattering pivots before knowing whether ordinary
French words can close the grid.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_reference_style_shapes_a import direct_slots, validate_geometry  # noqa: E402
from craft_flexible_common_grid import FRAME  # noqa: E402


OUTPUT = ROOT / "output/quality/word-first-bottleneck-shapes.json"


SPECS = {
    "word-first-v4-c4": FRAME | {(row, 4) for row in range(4, 10)},
    "word-first-v4-c5": FRAME | {(row, 5) for row in range(4, 10)},
    "word-first-h4-c4": FRAME | {(4, column) for column in range(4, 9)},
    "word-first-h5-c3": FRAME | {(5, column) for column in range(3, 9)},
}


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    shapes = []
    for shape_id, clues in SPECS.items():
        slots = direct_slots(clues)
        audit = validate_geometry(shape_id, clues, slots)
        if not audit["valid"]:
            raise ValueError({"shapeId": shape_id, "audit": audit})
        lengths = Counter(slot["length"] for slot in slots)
        if lengths[2] > 2:
            raise ValueError({"shapeId": shape_id, "twoLetterSlots": lengths[2]})
        shapes.append({
            "id": shape_id,
            "columns": 9,
            "rows": 10,
            "clueCells": [list(cell) for cell in sorted(clues)],
            "slots": slots,
            "lengthProfile": dict(sorted(lengths.items())),
            "geometryAudit": audit,
        })
        individual = OUTPUT.with_name(f"{shape_id}.json")
        individual.write_text(
            json.dumps(shapes[-1], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    OUTPUT.write_text(
        json.dumps({
            "version": 1,
            "kind": "word-first-bottleneck-shapes",
            "catalogModified": False,
            "shapes": shapes,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "shapes": len(shapes),
        "output": str(OUTPUT),
        "profiles": {shape["id"]: shape["lengthProfile"] for shape in shapes},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
