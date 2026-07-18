#!/usr/bin/env python3
"""Build close, topology-safe neighbors of one owner-approved strict-frame mask."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import craft_flexible_common_grid as craft  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--shape-id", required=True)
    parser.add_argument("--maximum-two-letter", type=int, default=2)
    parser.add_argument("--maximum-three-letter", type=int, default=6)
    parser.add_argument("--limit", type=int, default=160)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def build_neighbors(
    source_clues: set[tuple[int, int]],
    maximum_two_letter: int,
    maximum_three_letter: int,
) -> list[tuple[tuple, set, list, dict]]:
    """Remove or move one internal clue while preserving every hard invariant."""
    internal = source_clues - craft.FRAME
    free_zone = {
        (row, column)
        for row in range(3, craft.ROWS)
        for column in range(3, craft.COLUMNS)
    }
    candidates: dict[tuple, tuple[tuple, set, list, dict]] = {}
    proposals = [internal - {removed} for removed in internal]
    proposals.extend(
        (internal - {removed}) | {added}
        for removed in internal
        for added in free_zone - internal
    )
    for proposed_internal in proposals:
        clues = craft.FRAME | proposed_internal
        fingerprint = tuple(sorted(clues))
        if fingerprint in candidates:
            continue
        raw_slots = craft.direct_slots(clues)
        lengths = [slot["length"] for slot in raw_slots]
        if (
            not lengths
            or min(lengths) < 2
            or lengths.count(2) > maximum_two_letter
            or lengths.count(3) > maximum_three_letter
        ):
            continue
        audit = craft.validate_geometry("strict-frame-neighbor", clues, raw_slots)
        if not audit.get("valid"):
            continue
        long_answers = sum(length >= 5 for length in lengths)
        score = (
            lengths.count(2),
            lengths.count(3),
            -long_answers,
            len(proposed_internal),
            fingerprint,
        )
        candidates[fingerprint] = (score, clues, raw_slots, audit)
    return sorted(candidates.values(), key=lambda item: item[0])


def main() -> int:
    args = parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8"))
    source = next(
        grid for grid in document.get("grids", [])
        if grid.get("id") == args.shape_id
    )
    source_clues = {tuple(cell) for cell in source["clueCells"]}
    neighbors = build_neighbors(
        source_clues,
        args.maximum_two_letter,
        args.maximum_three_letter,
    )[: args.limit]
    grids = []
    for index, (_score, clues, raw_slots, audit) in enumerate(neighbors, 1):
        shape_id = f"{args.shape_id}-neighbor-{index:03d}"
        audit = {**audit, "sourceShapeId": shape_id, "parentShapeId": args.shape_id}
        grids.append({
            "id": shape_id,
            "columns": craft.COLUMNS,
            "rows": craft.ROWS,
            "clueCells": [list(cell) for cell in sorted(clues)],
            "rawSlots": raw_slots,
            "geometryAudit": audit,
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({
            "version": 1,
            "kind": "strict-frame-neighbor-shapes",
            "parentShapeId": args.shape_id,
            "policy": {
                "topRowAllDefinitions": True,
                "leftColumnAllDefinitions": True,
                "maximumTwoLetterAnswers": args.maximum_two_letter,
                "maximumThreeLetterAnswers": args.maximum_three_letter,
                "orphanLettersAllowed": False,
                "editDistance": "remove or move one internal clue",
            },
            "grids": grids,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "parent": args.shape_id,
        "neighbors": len(grids),
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if grids else 1


if __name__ == "__main__":
    raise SystemExit(main())
