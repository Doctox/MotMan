#!/usr/bin/env python3
"""Fill the two independent lexical components of the flexible L shape."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bitset_grid_filler import fill_bitset  # noqa: E402
from build_reference_style_shapes_a import direct_slots, validate_geometry  # noqa: E402
from craft_flexible_common_grid import active_usage, load_candidates  # noqa: E402
from diagnose_fixed_shape_corpus_gaps import Slot  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shape", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-zipf", type=float, default=3.0)
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--seed", type=int, default=718200)
    parser.add_argument("--exclude-answer", action="append", default=[])
    parser.add_argument("--include-child-forms", action="store_true")
    return parser.parse_args()


def local_slots(slots, original_indexes):
    return [
        Slot(
            index=local_index,
            slot_id=slots[original_index].slot_id,
            direction=slots[original_index].direction,
            clue_cell=slots[original_index].clue_cell,
            cells=slots[original_index].cells,
        )
        for local_index, original_index in enumerate(original_indexes)
    ]


def as_mapping(result):
    return result if isinstance(result, dict) else dict(enumerate(result or []))


def lexical_components(slots):
    """Return connected slot indexes, using crossings as graph edges."""
    slots_by_cell = {}
    for index, slot in enumerate(slots):
        for cell in slot.cells:
            slots_by_cell.setdefault(cell, []).append(index)
    neighbors = {index: set() for index in range(len(slots))}
    for indexes in slots_by_cell.values():
        for index in indexes:
            neighbors[index].update(other for other in indexes if other != index)

    pending = set(range(len(slots)))
    components = []
    while pending:
        start = min(pending)
        stack = [start]
        component = set()
        while stack:
            index = stack.pop()
            if index in component:
                continue
            component.add(index)
            stack.extend(neighbors[index] - component)
        pending -= component
        components.append(sorted(component))
    return sorted(components, key=lambda component: component[0])


def solve_component(
    slots,
    indexes,
    usage,
    scores,
    *,
    seed,
    seconds,
    unavailable=None,
):
    telemetry = {}
    result = fill_bitset(
        slots,
        indexes,
        random.Random(seed),
        None,
        unavailable_answers=set(unavailable or ()),
        answer_usage={
            answer: usage[answer] * 10_000 + int(1_000 - scores[answer] * 100)
            for answer in scores
        },
        max_grammar_answers=99,
        grammar_answers=set(),
        max_seconds=seconds,
        node_limit=100_000_000,
        require_image=False,
        prefer_constraint_support=True,
        constraint_support_bucket_size=2,
        telemetry=telemetry,
    )
    return as_mapping(result), telemetry


def main():
    args = parse_args()
    shape = json.loads(args.shape.read_text(encoding="utf-8"))
    clues = {tuple(cell) for cell in shape["clueCells"]}
    raw_slots = direct_slots(clues)
    audit = validate_geometry(shape["id"], clues, raw_slots)
    slots = [
        Slot(
            index=index,
            slot_id=item["slotId"],
            direction=item["direction"],
            clue_cell=tuple(item["clueCell"]),
            cells=tuple(tuple(cell) for cell in item["cells"]),
        )
        for index, item in enumerate(raw_slots)
    ]
    components = lexical_components(slots)
    if len(components) != 2:
        raise ValueError(
            "La forme doit se décomposer en exactement deux composantes lexicales "
            f"(trouvé : {len(components)})"
        )
    core_indexes, block_indexes = components

    words_by_length, scores, spellings = load_candidates(
        args.minimum_zipf,
        {answer.upper() for answer in args.exclude_answer},
        args.include_child_forms,
    )
    indexes = (
        words_by_length,
        None,
        scores,
        {answer: answer for answer in scores},
        {answer: set() for answer in scores},
        {answer: "normal" for answer in scores},
        set(),
    )
    usage = active_usage()
    core, core_telemetry = solve_component(
        local_slots(slots, core_indexes),
        indexes,
        usage,
        scores,
        seed=args.seed,
        seconds=args.seconds,
    )
    block = {}
    block_telemetry = {"reason": "core-unsolved"}
    if len(core) == len(core_indexes):
        block, block_telemetry = solve_component(
            local_slots(slots, block_indexes),
            indexes,
            usage,
            scores,
            seed=args.seed + 1,
            seconds=args.seconds,
            unavailable=set(core.values()),
        )
    complete = len(core) == len(core_indexes) and len(block) == len(block_indexes)
    combined = {}
    if complete:
        combined.update(
            {core_indexes[local]: answer for local, answer in core.items()}
        )
        combined.update(
            {block_indexes[local]: answer for local, answer in block.items()}
        )
    payload = {
        "version": 1,
        "kind": "component-filled-owner-flex-grid",
        "shapeId": shape["id"],
        "columns": 9,
        "rows": 10,
        "catalogModified": False,
        "publicationEligible": False,
        "complete": complete,
        "componentIndexes": {"frame": core_indexes, "lowerRight": block_indexes},
        "telemetry": {"frame": core_telemetry, "lowerRight": block_telemetry},
        "clueCells": shape["clueCells"],
        "geometryAudit": audit,
        "answers": [
            {
                "slotIndex": index,
                "slotId": slots[index].slot_id,
                "direction": slots[index].direction,
                "clueCell": list(slots[index].clue_cell),
                "cells": [list(cell) for cell in slots[index].cells],
                "answer": answer,
                "spelling": spellings[answer],
                "zipf": scores[answer],
                "activeUses": usage[answer],
            }
            for index, answer in sorted(combined.items())
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "complete": complete,
        "componentSizes": [len(core_indexes), len(block_indexes)],
        "telemetry": payload["telemetry"],
        "answers": [item["answer"] for item in payload["answers"]],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
