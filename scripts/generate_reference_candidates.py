"""Generate resumable answer skeletons; never writes the active catalog."""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import generate_grid_catalog as generator
from placement_lexicon import build_placement_index


ROOT = Path(__file__).resolve().parents[1]
LEVELS = ("easy", "normal", "hard")


def editorial_sources() -> dict[str, dict]:
    return {entry["answer"]: entry for entry in generator.load_entries()}


def audience_evidence() -> dict[str, str]:
    document = json.loads((ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8"))
    evidence = {
        entry["answer"]: (
            "eduscol-school-list" if entry.get("schoolFrequency", 0) > 0
            else "high-frequency-general" if entry.get("sourceFrequency", 0) >= 5
            else "specialist-or-rare"
        )
        for entry in document["entries"]
    }
    child_document = json.loads(
        (ROOT / "src/data/lexique.child-forms.json").read_text(encoding="utf-8")
    )
    evidence.update({
        entry["answer"]: entry["audienceEvidence"]
        for entry in child_document["entries"]
    })
    return evidence


def oriented_shape(shape: tuple, transpose: bool) -> set[tuple[int, int]]:
    cells = set(shape)
    return {(col, row) for row, col in cells} if transpose else cells


def make_candidate(level: str, seed: int, attempts: int, seconds: float,
                   unavailable: set[str], used_shapes: set[tuple]) -> dict | None:
    rng = random.Random(seed)
    index = build_placement_index(generator, level)
    sources = editorial_sources()
    evidence = audience_evidence()
    unavailable_by_level = set(unavailable)
    if level == "easy":
        unavailable_by_level.update(
            answer for answer, tier in index[5].items() if tier == "hard"
        )
    for attempt in range(attempts):
        shape_index = rng.randrange(len(generator.SHAPES))
        transpose = bool(rng.randrange(2))
        clues = oriented_shape(generator.SHAPES[shape_index], transpose)
        fingerprint = tuple(sorted(clues))
        if fingerprint in used_shapes:
            continue
        slots = generator.slots_for(clues)
        if generator.shape_errors(clues, slots):
            continue
        target = None if level == "easy" else generator.choose_difficulty_mix(len(slots), level, rng)
        telemetry = {}
        answers = generator.fill_bitset(
            slots, index, rng, target,
            unavailable_answers=unavailable_by_level,
            grammar_answers=generator.GRAMMAR_ANSWERS,
            max_grammar_answers=2,
            max_seconds=seconds,
            node_limit=200_000,
            require_image=True,
            minimum_images=1,
            telemetry=telemetry,
        )
        if answers is None:
            continue
        grid_id = f"reference-{level}-{seed}-{attempt}"
        words = []
        for slot_index, answer in sorted(answers.items()):
            source = sources.get(answer)
            image = source.get("image") if source else None
            reviewed = bool(source and source.get("editorialStatus") in {
                "human-reviewed", "image-reviewed"
            })
            words.append({
                "wordId": f"{grid_id}:word:{slot_index}",
                "answer": answer,
                "clue": source.get("clue") if source else None,
                "definitionStatus": "reviewed" if reviewed else "review-required",
                "sourceId": source.get("sourceId") if source else "lexique-3.83",
                "sourceUrl": source.get("sourceUrl") if source else (
                    "http://www.lexique.org/databases/Lexique383/Lexique383.tsv"
                ),
                "difficulty": index[5][answer],
                "audienceEvidence": evidence.get(answer, "editorial-review"),
                "direction": slots[slot_index].direction,
                "arrow": slots[slot_index].arrow,
                "clueCell": list(slots[slot_index].clue),
                "cells": [list(cell) for cell in slots[slot_index].cells],
                **({"image": image} if image else {}),
            })
        return {
            "id": grid_id,
            "size": generator.SIZE,
            "difficulty": level,
            "clueCells": [list(cell) for cell in sorted(clues)],
            "shapeFamily": shape_index + 1,
            "transposed": transpose,
            "words": words,
            "generationMetrics": telemetry,
            "publicationStatus": "editorial-review-required",
        }
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count-per-level", type=int, default=1)
    parser.add_argument("--attempts", type=int, default=45)
    parser.add_argument("--fill-timeout", type=float, default=5)
    parser.add_argument("--seed", type=int, default=2026071900)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "output/quality/reference-candidates.json")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        document = json.loads(output.read_text(encoding="utf-8"))
        grids = document.get("grids", [])
    else:
        grids = []
    for level_index, level in enumerate(LEVELS):
        accepted = [grid for grid in grids if grid["difficulty"] == level]
        answer_uses = Counter(
            word["answer"] for grid in accepted for word in grid["words"]
        )
        used_shapes = {tuple(map(tuple, grid["clueCells"])) for grid in accepted}
        while len(accepted) < args.count_per_level:
            unavailable = {
                answer for answer, count in answer_uses.items()
                if count >= (2 if len(answer) == 2 else 1)
            }
            candidate = make_candidate(
                level,
                args.seed + level_index * 100_000 + len(accepted) * 1000,
                args.attempts,
                args.fill_timeout,
                unavailable,
                used_shapes,
            )
            if candidate is None:
                print(json.dumps({"status": "stopped", "level": level,
                                  "accepted": len(accepted), "reason": "bounded-search-exhausted"}))
                break
            grids.append(candidate)
            accepted.append(candidate)
            answer_uses.update(word["answer"] for word in candidate["words"])
            used_shapes.add(tuple(map(tuple, candidate["clueCells"])))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({
                "version": 1,
                "kind": "non-publishable-reference-candidates",
                "seed": args.seed,
                "difficultyRanges": generator.DIFFICULTY_RANGES,
                "maximumAnswerUsesPerLevel": 1,
                "maximumShortAnswerUsesPerLevel": 2,
                "grids": grids,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"status": "candidate", "level": level,
                              "accepted": len(accepted), "id": candidate["id"]}), flush=True)
    print(json.dumps({
        "status": "finished",
        "output": str(output),
        "byLevel": dict(Counter(grid["difficulty"] for grid in grids)),
        "reviewRequired": sum(
            word["definitionStatus"] == "review-required"
            for grid in grids for word in grid["words"]
        ),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
