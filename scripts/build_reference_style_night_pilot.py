"""Build an owner-review pilot using the visual grammar of the supplied grid.

The active MotMan catalog mostly uses broken borders and many internal clue
cells.  This pilot deliberately inverts that grammar: the top and left border
carry the clues, while only a handful of internal clue cells interrupt long
answer bands.  Nothing produced here is published automatically.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as gen
from grid_topology import audit_grid_topology, render_topology_html
from motsflex_beam_filler import fill_motsflex_beam

ROWS = 10
COLUMNS = 9
BORDER = {(0, col) for col in range(COLUMNS)} | {(row, 0) for row in range(1, ROWS)}
WEAK = {
    "AN", "ANS", "AME", "AMES", "CLE", "CLES", "ERE", "ERES", "ILE", "ILES",
    "AIR", "AMI", "AMIS", "ARC", "ARCS", "ART", "ARTS", "BEC", "CRI", "CRIS",
    "EAU", "EGO", "EPEE", "EPEES", "FEU", "FER", "MER", "MUR", "NET", "OR",
    "RITE", "RITES", "SEL", "TETE", "TETES", "TIR",
}


def simple_lexical_family(answer: str) -> str:
    """Fast conservative family key for obvious singular/plural variants."""
    if len(answer) > 3 and answer.endswith(("S", "X")):
        return answer[:-1]
    return answer


def derive_slots(clues: set[tuple[int, int]]) -> list[gen.Slot]:
    slots: list[gen.Slot] = []
    for direction, dr, dc, arrow in (("across", 0, 1, "right"), ("down", 1, 0, "down")):
        for row, col in sorted(clues):
            cells = []
            current_row, current_col = row + dr, col + dc
            while (
                0 <= current_row < ROWS
                and 0 <= current_col < COLUMNS
                and (current_row, current_col) not in clues
            ):
                cells.append((current_row, current_col))
                current_row += dr
                current_col += dc
            if len(cells) >= 2:
                slots.append(gen.Slot(direction, (row, col), tuple(cells), arrow))
    return slots


def shape_is_complete(clues: set[tuple[int, int]], slots: list[gen.Slot]) -> bool:
    owners = defaultdict(list)
    outgoing = Counter()
    for slot_index, slot in enumerate(slots):
        outgoing[slot.clue] += 1
        for cell in slot.cells:
            owners[cell].append(slot_index)
    letters = {
        (row, col)
        for row in range(ROWS)
        for col in range(COLUMNS)
        if (row, col) not in clues
    }
    return (
        all(len(owners[cell]) == 2 for cell in letters)
        and all(outgoing[clue] >= 1 for clue in clues - {(0, 0)})
        and all(2 <= len(slot.cells) <= 9 for slot in slots)
    )


def clue_mask_similarity(left: set[tuple[int, int]], right: set[tuple[int, int]]) -> float:
    return len(left & right) / len(left | right)


def active_shapes() -> list[set[tuple[int, int]]]:
    catalog = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    return [set(map(tuple, grid["clueCells"])) for grid in catalog["grids"]]


def generate_shapes(seed: int, count: int = 32) -> list[dict]:
    rng = random.Random(seed)
    existing = active_shapes()
    candidates: dict[tuple[tuple[int, int], ...], dict] = {}
    internal_pool = [(row, col) for row in range(2, 8) for col in range(2, 7)]
    for _attempt in range(45_000):
        internal_count = rng.choice((4, 5, 5, 6, 6, 7))
        internal = set(rng.sample(internal_pool, internal_count))
        clues = BORDER | internal
        slots = derive_slots(clues)
        if not shape_is_complete(clues, slots):
            continue
        lengths = [len(slot.cells) for slot in slots]
        if min(lengths) < 3:
            continue
        long_count = sum(length >= 5 for length in lengths)
        short_count = sum(length <= 3 for length in lengths)
        if long_count < 10 or short_count > 10:
            continue
        double_internal = sum(
            sum(slot.clue == clue for slot in slots) == 2 for clue in internal
        )
        if double_internal < max(2, internal_count - 2):
            continue
        maximum_similarity = max(clue_mask_similarity(clues, shape) for shape in existing)
        if maximum_similarity > 0.58:
            continue
        corpus_length_support = sum(
            5 if length in (5, 6, 7) else 2 if length in (4, 8) else -3 if length <= 3 else 0
            for length in lengths
        )
        score = (
            long_count * 8
            - short_count * 5
            + double_internal * 3
            + corpus_length_support * 2
            + sum(lengths) / len(lengths)
            - maximum_similarity * 30
        )
        fingerprint = tuple(sorted(clues))
        candidates[fingerprint] = {
            "clues": clues,
            "slots": slots,
            "score": score,
            "metrics": {
                "internalClueCells": internal_count,
                "wordCount": len(slots),
                "longAnswers5Plus": long_count,
                "shortAnswers2Or3": short_count,
                "averageLength": round(sum(lengths) / len(lengths), 3),
                "maximumActiveClueMaskJaccard": round(maximum_similarity, 3),
                "lengthHistogram": dict(sorted(Counter(lengths).items())),
            },
        }
    ranked = sorted(candidates.values(), key=lambda item: item["score"], reverse=True)
    return ranked[:count]


def choose_image_slot_sets(
    slots: list[gen.Slot], image_answers: set[str], rng: random.Random, count: int = 10
) -> list[set[int]]:
    image_counts = Counter(map(len, image_answers))
    eligible = [
        index for index, slot in enumerate(slots)
        if image_counts[len(slot.cells)] >= 8
    ]
    results = []
    seen = set()
    for _attempt in range(500):
        rng.shuffle(eligible)
        selected = []
        used_clues = set()
        directions = Counter()
        for index in sorted(
            eligible,
            key=lambda item: (
                directions[slots[item].direction],
                -image_counts[len(slots[item].cells)],
                rng.random(),
            ),
        ):
            slot = slots[index]
            if slot.clue in used_clues:
                continue
            selected.append(index)
            used_clues.add(slot.clue)
            directions[slot.direction] += 1
            if len(selected) == 6:
                break
        if len(selected) != 6 or min(directions.values(), default=0) < 2:
            continue
        key = tuple(sorted(selected))
        if key not in seen:
            seen.add(key)
            results.append(set(selected))
        if len(results) >= count:
            break
    return results


def best_entry_by_answer(entries: list[dict]) -> dict[str, dict]:
    result = {}
    for entry in entries:
        answer = entry["answer"]
        score = (
            5 * (entry.get("editorialStatus") == "human-reviewed")
            + 4 * bool(entry.get("image"))
            + 2 * bool(entry.get("sourceUrl"))
            + float(entry.get("frequency", 0)) / 1000
        )
        if answer not in result or score > result[answer][0]:
            result[answer] = (score, entry)
    return {answer: value[1] for answer, value in result.items()}


def make_grid(grid_id: str, clues: set[tuple[int, int]], slots, answers, image_slots, entries_by_answer):
    words = []
    for index, slot in enumerate(slots):
        answer = answers[index]
        entry = entries_by_answer[answer]
        image = entry.get("image") if index in image_slots else None
        word = {
            "wordId": f"{grid_id}:word:{index + 1:02d}",
            "answer": answer,
            "clue": "" if image else entry["clue"],
            "sourceClue": entry.get("sourceClue", entry["clue"]),
            "definitionStatus": "reviewed" if entry.get("editorialStatus") == "human-reviewed" else "source-backed",
            "editorialStatus": "owner-review-required",
            "sourceType": "image" if image else entry.get("sourceType"),
            "sourceId": entry.get("sourceId"),
            "sourceUrl": entry.get("sourceUrl"),
            "conceptGroup": entry.get("conceptGroup", answer),
            "semanticConflicts": entry.get("semanticConflicts", []),
            "direction": slot.direction,
            "arrow": slot.arrow,
            "clueCell": list(slot.clue),
            "cells": [list(cell) for cell in slot.cells],
            "editorialProfile": "reference-style-night-pilot",
        }
        if image:
            word["image"] = image
        words.append(word)
    return {
        "id": grid_id,
        "columns": COLUMNS,
        "rows": ROWS,
        "audience": "standard",
        "clueCells": [list(cell) for cell in sorted(clues)],
        "words": words,
        "imageCount": len(image_slots),
        "publicationStatus": "owner-review-required",
        "editorialProfile": "reference-style-night-pilot",
        "provenance": {
            "method": "agent-assisted-reference-style-beam-fill",
            "reference": "owner-supplied mobile arrow-crossword screenshot",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=26071701)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=28.0)
    parser.add_argument("--shape-limit", type=int, default=24)
    parser.add_argument("--image-attempts", type=int, default=10)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output/quality/reference-style-night-pilot.json",
    )
    args = parser.parse_args()

    entries = gen.load_entries()
    indexes = gen.build_index(entries, min_frequency=0, difficulty="hard")
    image_answers = indexes[6]
    entries_by_answer = best_entry_by_answer(entries)
    catalog = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    active_answers = {
        word["answer"] for grid in catalog["grids"] for word in grid["words"]
    }
    all_answers = {answer for words in indexes[0].values() for answer in words}
    concept_group = indexes[3]
    active_concepts = {concept_group.get(answer, answer) for answer in active_answers}
    active_families = {simple_lexical_family(answer) for answer in active_answers}
    unavailable = WEAK | {
        answer for answer in all_answers
        if (
            simple_lexical_family(answer) in active_families
            or concept_group.get(answer, answer) in active_concepts
        )
    }

    rng = random.Random(args.seed)
    shapes = generate_shapes(args.seed, args.shape_limit)
    grids = []
    diagnostics = []
    used_answers = set()
    for shape_index, shape in enumerate(shapes, start=1):
        if len(grids) >= args.count:
            break
        image_slot_sets = choose_image_slot_sets(
            shape["slots"], image_answers, rng, count=args.image_attempts
        )
        for image_attempt, image_slots in enumerate(image_slot_sets, start=1):
            telemetry = {}
            answers = fill_motsflex_beam(
                shape["slots"],
                indexes,
                rng,
                unavailable_answers=unavailable | used_answers,
                answer_usage={},
                grammar_answers=gen.GRAMMAR_ANSWERS,
                maximum_grammar_answers=1,
                maximum_active_answers=0,
                required_image_slots=image_slots,
                image_answers=image_answers,
                beam_width=128,
                branch_width=24,
                max_seconds=args.seconds,
                state_limit=220_000,
                telemetry=telemetry,
            )
            diagnostics.append({
                "shapeRank": shape_index,
                "imageAttempt": image_attempt,
                "shapeMetrics": shape["metrics"],
                "imageSlots": sorted(image_slots),
                "solved": answers is not None,
                "telemetry": telemetry,
            })
            if answers is None:
                continue
            grid_id = f"reference-style-night-{len(grids) + 1:02d}"
            grid = make_grid(
                grid_id,
                shape["clues"],
                shape["slots"],
                answers,
                image_slots,
                entries_by_answer,
            )
            audit = audit_grid_topology(grid)
            if not audit["valid"]:
                diagnostics[-1]["solved"] = False
                diagnostics[-1]["auditErrors"] = audit["errors"]
                continue
            grid["shapeMetrics"] = shape["metrics"]
            grid["topologyAudit"] = {
                "valid": True,
                "orphanSegments": len(audit.get("orphanSegments", [])),
            }
            grids.append(grid)
            used_answers.update(answers.values())
            break

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "kind": "reference-style-owner-review-pilot",
        "generatorSeed": args.seed,
        "policy": {
            "publishedAutomatically": False,
            "topAndLeftClueBorder": True,
            "minimumImages": 6,
            "activeLexicalFamiliesExcluded": True,
            "referenceStyle": "long answer bands with sparse internal clue cells",
        },
        "generatedShapes": len(shapes),
        "diagnostics": diagnostics,
        "grids": grids,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    reports = [audit_grid_topology(grid) for grid in grids]
    html_path = output.with_suffix(".html")
    html_path.write_text(
        render_topology_html(reports, "Pilote nocturne — nouvelles silhouettes de référence"),
        encoding="utf-8",
    )
    print(json.dumps({
        "generated": len(grids),
        "attempts": len(diagnostics),
        "output": str(output),
        "html": str(html_path),
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
