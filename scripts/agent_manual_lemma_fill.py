#!/usr/bin/env python3
"""One-off deterministic word-first fill for the owner's flexible 9x10 pilot."""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bitset_grid_filler import fill_bitset
from build_reference_style_shapes_a import direct_slots, validate_geometry
from craft_flexible_common_grid import (
    active_usage,
    build_replacement_exclusions,
    load_candidates,
    load_lemma_families,
)
from diagnose_fixed_shape_corpus_gaps import Slot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--seconds", type=float, default=180)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shape", type=Path)
    parser.add_argument("--minimum-images", type=int, default=0)
    parser.add_argument("--include-child-forms", action="store_true")
    parser.add_argument("--allow-active-families", action="store_true")
    args = parser.parse_args()

    shape_path = args.shape or (ROOT / "output/quality/root-fixed-l.json")
    base = json.loads(shape_path.read_text(encoding="utf-8"))
    grid = base.get("grid", base)
    clues = {tuple(cell) for cell in grid["clueCells"]}
    raw_slots = direct_slots(clues)
    geometry = validate_geometry("agent-manual-lemma", clues, raw_slots)
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

    references = [
        ROOT / "output/quality/batch-v2-base-review.json",
        ROOT / "src/data/grid-generation-handcrafted/owner-low-short-02.review.json",
    ]
    excluded, blocked_families = build_replacement_exclusions(
        set(), references, include_morphalou_forms=True
    )
    usage = active_usage()
    families = load_lemma_families(True)
    active_families = {families.get(answer, answer) for answer in usage}
    if not args.allow_active_families:
        excluded.update(
            answer for answer, family in families.items() if family in active_families
        )
    excluded.update(usage)
    words_by_length, scores, spellings = load_candidates(
        2.0,
        excluded,
        include_child_forms=args.include_child_forms,
        include_morphalou_forms=True,
        morphalou_lemmas_only=True,
    )
    images = json.loads(
        (ROOT / "src/data/crossword.images-reviewed.json").read_text(encoding="utf-8")
    )
    image_answers = {
        entry["answer"] for entry in images.get("entries", [])
        if entry.get("answer") in scores and isinstance(entry.get("image"), dict)
    }
    indexes = (
        words_by_length,
        None,
        scores,
        {answer: families.get(answer, answer) for answer in scores},
        {answer: set() for answer in scores},
        {answer: "normal" for answer in scores},
        image_answers,
    )
    telemetry = {}
    result = fill_bitset(
        slots,
        indexes,
        random.Random(args.seed),
        None,
        answer_usage={answer: int(1000 - scores[answer] * 100) for answer in scores},
        max_grammar_answers=99,
        grammar_answers=set(),
        max_seconds=args.seconds,
        node_limit=100_000_000,
        require_image=args.minimum_images > 0,
        minimum_images=args.minimum_images,
        prefer_constraint_support=True,
        constraint_support_bucket_size=2,
        branching_strategy="cell",
        telemetry=telemetry,
    )
    mapping = result if isinstance(result, dict) else dict(enumerate(result or []))
    answers = []
    for index, answer in sorted(mapping.items()):
        slot = slots[index]
        answers.append({
            "slotIndex": index,
            "slotId": slot.slot_id,
            "direction": slot.direction,
            "clueCell": list(slot.clue_cell),
            "cells": [list(cell) for cell in slot.cells],
            "answer": answer,
            "spelling": spellings.get(answer, answer.lower()),
            "zipf": scores.get(answer),
            "family": families.get(answer, answer),
            "imageAvailable": answer in image_answers,
        })
    family_members = defaultdict(list)
    for item in answers:
        family_members[item["family"]].append(item["answer"])
    duplicate_families = {
        family: members for family, members in family_members.items() if len(members) > 1
    }
    payload = {
        "version": 1,
        "kind": "agent-manual-lemma-only-fill",
        "complete": len(mapping) == len(slots),
        "catalogModified": False,
        "blacklistModified": False,
        "seed": args.seed,
        "candidateCounts": {str(k): len(v) for k, v in words_by_length.items()},
        "excludedFamilies": len(blocked_families | active_families),
        "telemetry": telemetry,
        "grid": {
            "id": f"agent-manual-lemma-{args.seed}",
            "columns": 9,
            "rows": 10,
            "clueCells": [list(cell) for cell in sorted(clues)],
            "geometryAudit": geometry,
            "lengthDistribution": dict(sorted(Counter(len(x["answer"]) for x in answers).items())),
            "imageAnswerCount": sum(item["imageAvailable"] for item in answers),
            "duplicateFamilies": duplicate_families,
            "answers": answers,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "complete": payload["complete"],
        "answers": [item["answer"] for item in answers],
        "images": [item["answer"] for item in answers if item["imageAvailable"]],
        "duplicateFamilies": duplicate_families,
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if payload["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
