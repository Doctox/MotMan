#!/usr/bin/env python3
"""Search small, deterministic pivot moves around a proven flexible mask."""
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

from bitset_grid_filler import fill_bitset  # noqa: E402
from build_reference_style_shapes_a import direct_slots, validate_geometry  # noqa: E402
from craft_flexible_common_grid import (  # noqa: E402
    COLUMNS,
    FRAME,
    ROWS,
    active_usage,
    build_replacement_exclusions,
    load_candidates,
)
from diagnose_fixed_shape_corpus_gaps import Slot  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-zipf", type=float, default=2.8)
    parser.add_argument("--seconds", type=float, default=180.0)
    parser.add_argument("--seconds-per-shape", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=718400)
    parser.add_argument("--exclude-answer", action="append", default=[])
    parser.add_argument("--exclude-from", action="append", type=Path, default=[])
    return parser.parse_args()


def extract_grid(document: dict) -> dict:
    if isinstance(document.get("grid"), dict):
        return document["grid"]
    if isinstance(document.get("grids"), list) and document["grids"]:
        return document["grids"][0]
    return document


def answers_from(path: Path) -> set[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    grid = extract_grid(document)
    return {
        item["answer"]
        for item in (grid.get("answers") or grid.get("words") or [])
        if item.get("answer")
    }


def lemma_map() -> dict[str, str]:
    result = {}
    for name in ("lexique.lemmas.json", "lexique.child-forms.json"):
        document = json.loads((ROOT / "src/data" / name).read_text(encoding="utf-8"))
        for entry in document.get("entries", []):
            answer = str(entry.get("answer", "")).upper()
            if answer:
                result[answer] = str(entry.get("lemma") or answer).upper()
    return result


def has_duplicate_family(values: list[str], lemmas: dict[str, str]) -> bool:
    by_lemma = defaultdict(set)
    for answer in values:
        by_lemma[lemmas.get(answer, answer)].add(answer)
    return any(len(members) > 1 for members in by_lemma.values())


def variants(base_clues: set[tuple[int, int]], rng: random.Random):
    interior = sorted(base_clues - FRAME)
    seen = {tuple(sorted(base_clues))}
    candidates = []
    for index, cell in enumerate(interior):
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            moved = (cell[0] + dr, cell[1] + dc)
            if not (2 <= moved[0] < ROWS and 2 <= moved[1] < COLUMNS):
                continue
            clues = set(base_clues)
            clues.remove(cell)
            clues.add(moved)
            fingerprint = tuple(sorted(clues))
            if len(clues) == len(base_clues) and fingerprint not in seen:
                seen.add(fingerprint)
                candidates.append(clues)
    # A pair of small moves gives more silhouette diversity without returning
    # to unconstrained random masks.
    single_moves = list(candidates)
    for _ in range(240):
        first = rng.choice(single_moves)
        current = sorted(first - FRAME)
        cell = rng.choice(current)
        dr, dc = rng.choice(((-1, 0), (1, 0), (0, -1), (0, 1)))
        moved = (cell[0] + dr, cell[1] + dc)
        if not (2 <= moved[0] < ROWS and 2 <= moved[1] < COLUMNS):
            continue
        clues = set(first)
        clues.remove(cell)
        clues.add(moved)
        fingerprint = tuple(sorted(clues))
        if len(clues) == len(base_clues) and fingerprint not in seen:
            seen.add(fingerprint)
            candidates.append(clues)
    rng.shuffle(candidates)
    return candidates


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    base_document = json.loads(args.base.read_text(encoding="utf-8"))
    base_grid = extract_grid(base_document)
    base_clues = {tuple(cell) for cell in base_grid["clueCells"]}
    excluded, excluded_families = build_replacement_exclusions(
        {answer.upper() for answer in args.exclude_answer}, args.exclude_from
    )
    by_length, scores, spellings = load_candidates(
        args.minimum_zipf, excluded, True
    )
    indexes = (
        by_length,
        None,
        scores,
        {answer: answer for answer in scores},
        {answer: set() for answer in scores},
        {answer: "normal" for answer in scores},
        set(),
    )
    usage = active_usage()
    lemmas = lemma_map()
    started = time.monotonic()
    tried = 0
    geometry_valid = 0
    rejected_families = 0
    selected = None
    solution = None
    telemetry = {}
    for clues in variants(base_clues, rng):
        if time.monotonic() - started >= args.seconds:
            break
        tried += 1
        raw_slots = direct_slots(clues)
        lengths = [slot["length"] for slot in raw_slots]
        audit = validate_geometry(f"pivot-{args.seed}-{tried}", clues, raw_slots)
        if (
            not audit["valid"]
            or any(length < 2 or length > 9 for length in lengths)
            or lengths.count(2) > 2
            or sum(length >= 5 for length in lengths) < 5
        ):
            continue
        geometry_valid += 1
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
        current_telemetry = {}
        result = fill_bitset(
            slots,
            indexes,
            random.Random(args.seed + tried),
            None,
            answer_usage={
                answer: usage[answer] * 10_000 + int(1_000 - scores[answer] * 100)
                for answer in scores
            },
            max_grammar_answers=99,
            grammar_answers=set(),
            max_seconds=min(
                args.seconds_per_shape,
                max(0.05, args.seconds - (time.monotonic() - started)),
            ),
            node_limit=20_000_000,
            require_image=False,
            prefer_constraint_support=True,
            constraint_support_bucket_size=2,
            telemetry=current_telemetry,
        )
        telemetry = current_telemetry
        if result is None:
            continue
        mapping = result if isinstance(result, dict) else dict(enumerate(result))
        values = list(mapping.values())
        if len(mapping) != len(slots):
            continue
        if has_duplicate_family(values, lemmas):
            rejected_families += 1
            continue
        selected = clues, raw_slots, slots, audit
        solution = mapping
        break

    payload = {
        "version": 1,
        "kind": "clean-pivot-variant-search",
        "complete": solution is not None,
        "catalogModified": False,
        "seed": args.seed,
        "minimumZipf": args.minimum_zipf,
        "attempts": tried,
        "geometryValidTried": geometry_valid,
        "duplicateFamilyClosuresRejected": rejected_families,
        "replacementExclusions": {
            "references": [str(path) for path in args.exclude_from],
            "answerCount": len(excluded),
            "familyCount": len(excluded_families),
        },
        "lastTelemetry": telemetry,
        "grid": None,
    }
    if solution is not None and selected is not None:
        clues, raw_slots, slots, audit = selected
        answers = [
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
            for index, answer in sorted(solution.items())
        ]
        payload["grid"] = {
            "id": f"clean-pivot-{args.seed}",
            "columns": COLUMNS,
            "rows": ROWS,
            "clueCells": [list(cell) for cell in sorted(clues)],
            "internalClueCells": [list(cell) for cell in sorted(clues - FRAME)],
            "lengthDistribution": dict(sorted(Counter(map(lambda item: len(item["answer"]), answers)).items())),
            "geometryAudit": audit,
            "rawSlots": raw_slots,
            "answers": answers,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "complete": payload["complete"],
        "attempts": tried,
        "geometryValid": geometry_valid,
        "answers": [item["answer"] for item in payload["grid"]["answers"]] if payload["grid"] else None,
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if solution is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
