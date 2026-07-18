"""Propose crossing drafts for manual MotMan editing.

This is deliberately not a catalog generator.  It only saves geometrically
valid crossing drafts.  Every answer/clue pair remains rejected by default
until it is copied into the handcrafted batch after a human editorial pass.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

import generate_grid_catalog as generator
from grid_topology import audit_grid_topology
from optimize_grid_shapes import optimize
from placement_lexicon import build_placement_index


ROOT = Path(__file__).resolve().parents[1]
ANCHORS = (
    ROOT / "src/data/grid-generation-handcrafted/reference.pilot.json",
    ROOT / "output/quality/difficulty-calibration-candidates.json",
    ROOT / "output/quality/hard-calibration-round-02-candidate.json",
)
def anchor_grids() -> list[dict]:
    grids = []
    for path in ANCHORS:
        if path.exists():
            grids.extend(json.loads(path.read_text(encoding="utf-8")).get("grids", []))
    return grids


def reviewed_pool() -> tuple[tuple, dict[str, dict]]:
    editorial_entries = generator.load_entries()
    editorial_by_answer = {entry["answer"]: entry for entry in editorial_entries}
    indexes = list(build_placement_index(generator, "normal"))
    lexique_entries = json.loads(
        (ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8")
    )["entries"]
    lexique_by_answer = {entry["answer"]: entry for entry in lexique_entries}

    allowed = set()
    for answers in indexes[0].values():
        for answer in answers:
            lexical = lexique_by_answer.get(answer, {})
            if answer in generator.REJECTED_EASY_ANSWERS | generator.REJECTED_NORMAL_ANSWERS:
                continue
            if len(answer) != 2 and (
                lexical.get("partOfSpeech") not in {"NOM", "VER", "ADV"}
                or float(lexical.get("sourceFrequency", 0)) < 1.2
            ):
                continue
            allowed.add(answer)

    by_length = {
        length: [answer for answer in answers if answer in allowed]
        for length, answers in indexes[0].items()
    }
    frequency = {}
    sources = {}
    for answer in allowed:
        lexical = lexique_by_answer.get(answer, {})
        editorial = editorial_by_answer.get(answer, {})
        source_frequency = float(lexical.get("sourceFrequency", 0))
        image_bonus = 2 if editorial.get("image") else 0
        frequency[answer] = math.log1p(source_frequency) + 1 + image_bonus
        sources[answer] = {
            "answer": answer,
            "clue": editorial.get("clue", ""),
            "sourceClue": editorial.get("sourceClue", editorial.get("clue", "")),
            "sourceId": editorial.get("sourceId", "lexique-3.83"),
            "sourceUrl": editorial.get(
                "sourceUrl", "http://www.lexique.org/databases/Lexique383/Lexique383.tsv"
            ),
            "sourceType": editorial.get("sourceType", "lexical-attestation"),
            "editorialStatus": editorial.get("editorialStatus", "manual-clue-required"),
            "conceptGroup": editorial.get("conceptGroup", answer),
            "semanticConflicts": editorial.get("semanticConflicts", []),
            **({"image": editorial["image"]} if editorial.get("image") else {}),
        }
    return (
        by_length,
        indexes[1],
        frequency,
        {answer: value for answer, value in indexes[3].items() if answer in allowed},
        {answer: value for answer, value in indexes[4].items() if answer in allowed},
        {answer: value for answer, value in indexes[5].items() if answer in allowed},
        indexes[6] & allowed,
    ), sources


def as_grid(number: int, shape: dict, answers: dict[int, str], sources: dict[str, dict], telemetry: dict) -> dict:
    grid_id = f"standard-draft-{number:02d}"
    words = []
    for index, slot in enumerate(shape["slots"]):
        answer = answers[index]
        source = sources[answer]
        # Keep missing editorial work visibly empty in staging.  A fake
        # placeholder must never look like a playable definition.
        suggested_clue = source.get("clue") or ""
        words.append({
            "wordId": f"{grid_id}:word:{index + 1:02d}",
            "answer": answer,
            "clue": suggested_clue,
            "sourceClue": source.get("sourceClue", source.get("clue", "")),
            "sourceId": source.get("sourceId"),
            "sourceUrl": source.get("sourceUrl"),
            "sourceType": source.get("sourceType"),
            "editorialStatus": source.get("editorialStatus"),
            "manualReview": "pending-reject-by-default",
            "conceptGroup": source.get("conceptGroup", answer),
            "semanticConflicts": source.get("semanticConflicts", []),
            "direction": slot["direction"],
            "arrow": slot["arrow"],
            "clueCell": slot["clue"],
            "cells": slot["cells"],
            **({"image": source["image"]} if source.get("image") else {}),
        })
    return {
        "id": grid_id,
        "columns": 9,
        "rows": 10,
        "editorialProfile": "motman-standard",
        "clueCells": shape["clueCells"],
        "words": words,
        "generationMetrics": telemetry,
        "publicationStatus": "manual-review-required",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--attempts", type=int, default=240)
    parser.add_argument("--seed", type=int, default=26071490)
    parser.add_argument("--maximum-shape-overlap", type=int, default=22)
    parser.add_argument(
        "--compare-active-catalog",
        action="store_true",
        help="Use every active grid as the diversity/repetition baseline.",
    )
    parser.add_argument(
        "--anchor-catalog",
        action="append",
        type=Path,
        default=[],
        help="Additional catalogue whose answers and silhouettes must influence the draft.",
    )
    parser.add_argument(
        "--forbid-catalog",
        action="append",
        type=Path,
        default=[],
        help="Additional catalogue whose answers cannot be reused in the draft.",
    )
    parser.add_argument(
        "--forbid-answer",
        action="append",
        default=[],
        help="One normalized answer that cannot appear in the draft.",
    )
    parser.add_argument(
        "--maximum-existing-answer-uses",
        type=int,
        default=None,
        help="Reject answers already used this many times in the baseline/batch.",
    )
    parser.add_argument("--minimum-images", type=int, default=1)
    parser.add_argument(
        "--fill-seconds",
        type=float,
        default=3,
        help="Maximum solver time for one shape; keep smoke runs deliberately short.",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "output/quality/standard-crossing-drafts.json")
    args = parser.parse_args()

    anchors = anchor_grids()
    if args.compare_active_catalog:
        active = json.loads(
            (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
        ).get("grids", [])
        anchors = active
    for anchor_path in [*args.anchor_catalog, *args.forbid_catalog]:
        resolved = anchor_path if anchor_path.is_absolute() else ROOT / anchor_path
        anchors.extend(json.loads(resolved.read_text(encoding="utf-8")).get("grids", []))
    forbidden_catalog_answers = set(args.forbid_answer)
    for forbidden_path in args.forbid_catalog:
        resolved = forbidden_path if forbidden_path.is_absolute() else ROOT / forbidden_path
        forbidden_document = json.loads(resolved.read_text(encoding="utf-8"))
        forbidden_catalog_answers.update(
            word["answer"]
            for grid in forbidden_document.get("grids", [])
            for word in grid.get("words", [])
        )
    output = args.output if args.output.is_absolute() else ROOT / args.output
    accepted = []
    previous_rejections = {}
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing.get("kind") == "non-publishable-crossing-drafts":
            accepted = existing.get("grids", [])
            previous_rejections = existing.get("rejectionCounts", {})
    # Repetition is discouraged before it is forbidden.  The closed list of
    # reviewed two-letter answers is necessarily reused more often.
    answer_usage = Counter(
        word["answer"]
        for grid in [*anchors, *accepted]
        for word in grid.get("words", [])
    )
    previous_shapes = [
        {tuple(cell) for cell in grid.get("clueCells", [])}
        for grid in [*anchors, *accepted]
    ]
    indexes, sources = reviewed_pool()
    rng = random.Random(args.seed)
    rejection_counts = defaultdict(int, previous_rejections)

    for attempt in range(args.attempts):
        shape = optimize(
            timeout=1,
            seed=args.seed + attempt,
            visible_clue_cells=rng.randint(23, 27),
            minimum_double_clues=1,
            maximum_double_clues=6,
            maximum_adjacent_pairs=3,
            maximum_top_border_clues=7,
            maximum_left_border_clues=7,
            maximum_border_clue_run=5,
            maximum_length_two_answers=2,
            only_direct_arrows=True,
            required_lengths=(),
            require_length_bands=True,
            enforce_length_balance=False,
            enforce_clue_spacing=True,
            columns=9,
            rows=10,
            maximum_answer_length=8,
            previous_shapes=previous_shapes,
            maximum_shape_overlap=args.maximum_shape_overlap,
        )
        if not shape:
            rejection_counts["geometry"] += 1
            continue
        fingerprint = {tuple(cell) for cell in shape["clueCells"]}
        if any(previous == fingerprint for previous in previous_shapes):
            rejection_counts["duplicate-shape"] += 1
            continue
        slots = [generator.Slot(
            slot["direction"], tuple(slot["clue"]), tuple(map(tuple, slot["cells"])), slot["arrow"]
        ) for slot in shape["slots"]]
        telemetry = {}
        unavailable = set(generator.ROTATION_COOLDOWN_ANSWERS) | forbidden_catalog_answers | {
            answer for answer, count in answer_usage.items()
            if count >= (
                args.maximum_existing_answer_uses
                if args.maximum_existing_answer_uses is not None
                else (8 if len(answer) == 2 else 6)
            )
        }
        answers = generator.fill_bitset(
            slots,
            indexes,
            rng,
            None,
            unavailable_answers=unavailable,
            grammar_answers=generator.GRAMMAR_ANSWERS,
            max_grammar_answers=2,
            max_seconds=args.fill_seconds,
            node_limit=500_000,
            require_image=True,
            minimum_images=args.minimum_images,
            telemetry=telemetry,
        )
        if answers is None:
            rejection_counts[f"fill-{telemetry.get('reason', 'failed')}"] += 1
            continue
        grid = as_grid(len(accepted) + 1, shape, answers, sources, telemetry)
        report = audit_grid_topology(grid)
        blocking_codes = {
            error["code"] for error in report["errors"]
            if error["code"] != "empty_clue"
        }
        if blocking_codes:
            rejection_counts["topology"] += 1
            continue
        accepted.append(grid)
        answer_usage.update(answers.values())
        previous_shapes.append({tuple(cell) for cell in shape["clueCells"]})
        print(json.dumps({
            "accepted": len(accepted),
            "attempt": attempt + 1,
            "words": len(grid["words"]),
        }), flush=True)
        if len(accepted) >= args.count:
            break

    # A zero-result smoke is still a useful result: always persist its
    # aggregate rejection reasons instead of leaving the operator blind.
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 1,
        "kind": "non-publishable-crossing-drafts",
        "policy": "Rejected by default until every pair is manually reviewed.",
        "seed": args.seed,
        "anchorCount": len(anchors),
        "attemptsRequested": args.attempts,
        "grids": accepted,
        "rejectionCounts": dict(rejection_counts),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "accepted": len(accepted),
        "requested": args.count,
        "rejectionCounts": dict(rejection_counts),
    }), flush=True)


if __name__ == "__main__":
    main()
