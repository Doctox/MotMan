#!/usr/bin/env python3
"""Bounded staging search seeded by six concrete, imageable French words."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import craft_flexible_common_grid as craft  # noqa: E402
from bitset_grid_filler import fill_bitset  # noqa: E402


REFERENCE_PATHS = [
    ROOT / "src/data/grid-generation-handcrafted/owner-low-short-02.review.json",
    ROOT / "src/data/grid-generation-handcrafted/batch-v2-base.review.json",
    ROOT / "src/data/grid-generation-handcrafted/batch-v2-shifted.review.json",
]

# Reviewed image-library answers that are concrete and immediately recognizable.
CONCRETE = {
    "ABRI", "AUTO", "BAIN", "BARBE", "BOIS", "BRAS", "CAFE", "CAMION",
    "CARTE", "CHAISE", "CHAPEAU", "CHATEAU", "CHEVAL", "COQ", "CRANE",
    "CUILLERE", "DENT", "DOUCHE", "EPEE", "FENETRE", "FIL", "FILM",
    "FORET", "FUMEE", "HERBE", "LAIT", "LUMIERE", "MAGASIN", "MIROIR",
    "MONTAGNE", "MOTO", "NID", "PANTALON", "PAPIER", "PAQUET", "PARFUM",
    "PHOTO", "PLAGE", "PLANETE", "PONT", "PORTE", "POT", "RAIL", "RENARD",
    "REPAS", "ROUE", "ROUTE", "SEAU", "SINGE", "SKI", "TABLEAU", "TGV",
    "TORTUE", "TOUR", "TRACTEUR", "TRAM", "VALISE", "VESTE", "VILLE",
    "VISAGE",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=280)
    parser.add_argument("--seed", type=int, default=922001)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def intersections(slots) -> dict[tuple[int, int], tuple[int, int]]:
    links = defaultdict(list)
    for index, slot in enumerate(slots):
        for position, cell in enumerate(slot.cells):
            links[cell].append((index, position))
    result = {}
    for values in links.values():
        if len(values) == 2:
            left, right = values
            result[left[0], right[0]] = left[1], right[1]
            result[right[0], left[0]] = right[1], left[1]
    return result


def compatible_fixed_assignment(slots, anchors_by_length, rng, count=6):
    eligible = [
        index for index, slot in enumerate(slots)
        if anchors_by_length.get(len(slot.cells))
    ]
    if len(eligible) < count:
        return None
    crossing = intersections(slots)
    # Prefer a mix of directions and slots with fewer mutual crossings; this
    # still seeds the grid but leaves the closure enough freedom.
    for _ in range(80):
        rng.shuffle(eligible)
        selected = []
        across = down = 0
        for index in eligible:
            direction = slots[index].direction
            if direction == "across" and across >= 4:
                continue
            if direction == "down" and down >= 4:
                continue
            selected.append(index)
            across += direction == "across"
            down += direction == "down"
            if len(selected) == count:
                break
        if len(selected) < count or not across or not down:
            continue
        assigned = {}
        used = set()

        def place(offset: int) -> bool:
            if offset == len(selected):
                return True
            index = selected[offset]
            words = list(anchors_by_length[len(slots[index].cells)])
            rng.shuffle(words)
            words.sort(key=lambda word: -len(set(word)))
            for word in words:
                if word in used:
                    continue
                good = True
                for other, other_word in assigned.items():
                    cross = crossing.get((index, other))
                    if cross and word[cross[0]] != other_word[cross[1]]:
                        good = False
                        break
                if not good:
                    continue
                assigned[index] = word
                used.add(word)
                if place(offset + 1):
                    return True
                used.remove(word)
                del assigned[index]
            return False

        if place(0):
            return assigned
    return None


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    excluded, blocked_families = craft.build_replacement_exclusions(
        set(), REFERENCE_PATHS
    )
    by_length, scores, spellings = craft.load_candidates(2.8, excluded, False)
    image_doc = json.loads(
        (ROOT / "src/data/crossword.images-reviewed.json").read_text(encoding="utf-8")
    )
    reviewed_images = {
        entry["answer"] for entry in image_doc.get("entries", [])
        if isinstance(entry.get("image"), dict)
    }
    anchors = sorted(CONCRETE & reviewed_images & set(scores))
    anchors_by_length = defaultdict(list)
    for answer in anchors:
        anchors_by_length[len(answer)].append(answer)
    indexes = (
        by_length,
        None,
        scores,
        {answer: answer for answer in scores},
        {answer: set() for answer in scores},
        {answer: "normal" for answer in scores},
        reviewed_images & set(scores),
    )
    usage = craft.active_usage()
    shapes = craft.catalog_shape_candidates(rng)
    # The two recently proven masks are checked first, followed by catalog masks.
    for source in (ROOT / "output/quality/root-fixed-l.json",
                   ROOT / "output/quality/root-fixed-l-shifted.shape.json"):
        document = json.loads(source.read_text(encoding="utf-8"))
        grid = document.get("grid") or document
        clues = {tuple(cell) for cell in grid["clueCells"]}
        raw_slots = craft.direct_slots(clues)
        audit = craft.validate_geometry(source.stem, clues, raw_slots)
        slots = [
            craft.Slot(
                index=index, slot_id=item["slotId"], direction=item["direction"],
                clue_cell=tuple(item["clueCell"]),
                cells=tuple(tuple(cell) for cell in item["cells"]),
            )
            for index, item in enumerate(raw_slots)
        ]
        shapes.insert(0, (source.stem, clues, raw_slots, slots, audit))

    started = time.monotonic()
    attempts = 0
    solution = selected = fixed = None
    last_telemetry = {}
    while time.monotonic() - started < args.seconds and solution is None:
        source_id, clues, raw_slots, slots, audit = shapes[attempts % len(shapes)]
        attempts += 1
        fixed_answers = compatible_fixed_assignment(slots, anchors_by_length, rng, 6)
        if not fixed_answers:
            continue
        telemetry = {}
        result = fill_bitset(
            slots, indexes, rng, None,
            answer_usage={
                answer: usage[answer] * 10_000 + int(1_000 - scores[answer] * 100)
                for answer in scores
            },
            fixed_answers=fixed_answers,
            max_grammar_answers=99,
            grammar_answers=set(),
            max_seconds=min(2.5, args.seconds - (time.monotonic() - started)),
            node_limit=8_000_000,
            require_image=False,
            minimum_images=0,
            prefer_constraint_support=True,
            constraint_support_bucket_size=2,
            telemetry=telemetry,
        )
        last_telemetry = telemetry
        if result is not None and len(result) == len(slots):
            solution = result
            selected = source_id, clues, raw_slots, slots, audit
            fixed = fixed_answers
            break

    payload = {
        "version": 1,
        "kind": "word-first-concrete-grid-search",
        "complete": solution is not None,
        "catalogModified": False,
        "publicationEligible": False,
        "constraints": {
            "columns": 9, "rows": 10, "maximumTwoLetterAnswers": 2,
            "minimumConcreteAnchors": 6, "allRunsMinimumLength": 2,
            "excludedReferenceFamilies": sorted(blocked_families),
        },
        "availableConcreteAnchors": anchors,
        "attempts": attempts,
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "lastTelemetry": last_telemetry,
        "grid": None,
    }
    if solution is not None:
        source_id, clues, raw_slots, slots, audit = selected
        answers = []
        for index, answer in sorted(solution.items()):
            answers.append({
                "slotIndex": index,
                "slotId": slots[index].slot_id,
                "direction": slots[index].direction,
                "clueCell": list(slots[index].clue_cell),
                "cells": [list(cell) for cell in slots[index].cells],
                "answer": answer,
                "spelling": spellings[answer],
                "zipf": scores[answer],
                "concreteAnchor": index in fixed,
                "imageAvailable": answer in reviewed_images,
            })
        payload["grid"] = {
            "id": f"word-first-concrete-{args.seed}",
            "sourceShapeGridId": source_id,
            "clueCells": [list(cell) for cell in sorted(clues)],
            "rawSlots": raw_slots,
            "geometryAudit": audit,
            "lengthDistribution": dict(sorted(Counter(map(lambda x: len(x["answer"]), answers)).items())),
            "concreteAnchors": [item["answer"] for item in answers if item["concreteAnchor"]],
            "answers": answers,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "complete": payload["complete"], "attempts": attempts,
        "elapsedSeconds": payload["elapsedSeconds"],
        "anchors": payload["grid"]["concreteAnchors"] if payload["grid"] else [],
        "answers": [item["answer"] for item in payload["grid"]["answers"]] if payload["grid"] else [],
    }, ensure_ascii=False, indent=2))
    return 0 if solution is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
