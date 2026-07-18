"""Generate the first reviewed-size MotMan catalog across three levels."""
from __future__ import annotations

import argparse
import json
import os
import random
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path

import generate_grid_catalog as generator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "src" / "data" / "grid.catalog.json"
LEVELS = ("easy", "normal", "hard")


@contextmanager
def generation_lock():
    """Prevent two catalog generators from writing the same checkpoints/output."""
    lock_path = ROOT / "src" / "data" / ".grid-generation.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    handle.seek(0)
    if handle.read(1) == b"":
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        handle.close()
        raise SystemExit(
            "Une génération de catalogue est déjà en cours. "
            "Attendre sa fin au lieu d'en lancer une deuxième."
        ) from error
    try:
        yield
    finally:
        handle.seek(0)
        if os.name == "nt":
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def generate_one(level: str, seed: int, attempts: int, nodes: int,
                 unavailable_answers: set[str] | None = None,
                 unavailable_shapes: set[tuple] | None = None,
                 discouraged_answers: set[str] | None = None,
                 answer_usage: dict[str, int] | None = None,
                 fill_timeout: float = 5.0) -> dict | None:
    entries = generator.load_entries()
    clue_for = {entry["answer"]: entry["clue"] for entry in entries}
    image_for = {entry["answer"]: entry.get("image") for entry in entries if entry.get("image")}
    indexes = generator.build_index(
        entries,
        min_frequency={"easy": 3.5, "normal": 2.7, "hard": 1.2}[level],
        difficulty=level,
    )
    rng = random.Random(seed)
    unavailable_answers = unavailable_answers or set()
    unavailable_shapes = unavailable_shapes or set()

    for attempt in range(attempts):
        clues = generator.make_shape(rng)
        shape = tuple(sorted(clues))
        if shape in unavailable_shapes:
            continue
        slots = generator.slots_for(clues)
        if generator.shape_errors(clues, slots):
            continue
        fill_stats = {}
        target_mix = generator.choose_difficulty_mix(len(slots), level, rng)
        answers = generator.fill_bitset(
            slots, indexes, rng, target_mix,
            unavailable_answers=unavailable_answers,
            answer_usage=answer_usage,
            grammar_answers=generator.GRAMMAR_ANSWERS,
            max_seconds=fill_timeout,
            node_limit=nodes,
            minimum_images={"easy": 2, "normal": 2, "hard": 1}[level],
            telemetry=fill_stats,
        )
        if answers is None:
            continue
        if sum(answer in generator.GRAMMAR_ANSWERS for answer in answers.values()) > 1:
            continue

        difficulty_mix = Counter(indexes[5][answer] for answer in answers.values())
        word_count = len(answers)
        ranges = generator.DIFFICULTY_RANGES[level]
        if not all(ranges[tier][0] <= difficulty_mix[tier] / word_count <= ranges[tier][1]
                   for tier in ranges):
            continue

        image_limit = {"easy": 6, "normal": 4, "hard": 2}[level]
        available_images = sorted(answer for answer in answers.values() if answer in image_for)
        if not available_images:
            continue
        image_words = set(available_images[:image_limit])
        grid_id = f"{level}-{seed}-{attempt}"
        words = [{
            "wordId": f"{grid_id}:word:{index}",
            "answer": answer,
            "clue": clue_for[answer],
            "direction": slots[index].direction,
            "arrow": slots[index].arrow,
            "clueCell": list(slots[index].clue),
            "cells": [list(cell) for cell in slots[index].cells],
            **({"image": image_for[answer]} if answer in image_words else {}),
        } for index, answer in answers.items()]
        candidate = {
            "id": grid_id,
            "size": generator.SIZE,
            "difficulty": level,
            "difficultyMix": {tier: difficulty_mix[tier] for tier in LEVELS},
            "clueCells": [list(cell) for cell in sorted(clues)],
            "words": words,
            "generationMetrics": fill_stats,
        }
        if generator.audit_grid_topology(candidate)["valid"]:
            return candidate
    return None


def generate_unique_level(level: str, base_seed: int, count: int, retries_per_grid: int,
                          attempts: int, nodes: int, max_answer_uses: int,
                          checkpoint_path: str, fill_timeout: float = 5.0) -> list[dict]:
    checkpoint = Path(checkpoint_path)
    if checkpoint.exists():
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        grids = saved.get("grids", []) if saved.get("difficulty") == level else []
    else:
        grids = []
    answer_uses: Counter[str] = Counter()
    shape_uses: Counter[tuple] = Counter()
    for existing_grid in grids:
        answer_uses.update(word["answer"] for word in existing_grid["words"])
        shape_uses[tuple(tuple(cell) for cell in existing_grid["clueCells"])] += 1
    for grid_index in range(len(grids), count):
        grid = None
        for retry in range(retries_per_grid):
            seed = base_seed + grid_index * 1000 + retry
            previous_answers = {
                word["answer"] for word in grids[-1]["words"]
            } if grids else set()
            unavailable_answers = {
                answer for answer, uses in answer_uses.items()
                if uses >= (3 if len(answer) <= 3 else max_answer_uses)
            } | previous_answers
            unavailable_shapes = {
                shape for shape, uses in shape_uses.items() if uses >= 2
            }
            discouraged_answers = set(answer_uses)
            grid = generate_one(level, seed, attempts, nodes,
                                unavailable_answers, unavailable_shapes, discouraged_answers,
                                dict(answer_uses), fill_timeout)
            if grid:
                break
        if grid is None:
            break
        answers = [word["answer"] for word in grid["words"]]
        shape = tuple(tuple(cell) for cell in grid["clueCells"])
        answer_uses.update(answers)
        shape_uses[shape] += 1
        grids.append(grid)
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps({
            "difficulty": level,
            "maximumAnswerUses": max_answer_uses,
            "grids": grids,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "status": "gridAccepted", "level": level,
            "accepted": len(grids), "target": count,
            "uniqueAnswers": len(answer_uses),
        }), flush=True)
    return grids


def main() -> None:
    with generation_lock():
        run_generation()


def run_generation() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count-per-level", type=int, default=10)
    parser.add_argument("--retries-per-grid", type=int, default=8)
    parser.add_argument("--attempts", type=int, default=80)
    parser.add_argument("--nodes", type=int, default=8000)
    parser.add_argument("--fill-timeout", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=2026071300)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--max-answer-uses", type=int, default=2)
    parser.add_argument("--checkpoint-dir", type=Path,
                        default=ROOT / "src" / "data" / "grid-generation")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    grids_by_level = {level: [] for level in LEVELS}
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                generate_unique_level,
                level,
                args.seed + level_index * 100000,
                args.count_per_level,
                args.retries_per_grid,
                args.attempts,
                args.nodes,
                args.max_answer_uses,
                str((args.checkpoint_dir if args.checkpoint_dir.is_absolute()
                     else ROOT / args.checkpoint_dir) / f"{level}.json"),
                args.fill_timeout,
            ): level
            for level_index, level in enumerate(LEVELS)
        }
        for future in as_completed(futures):
            level = futures[future]
            grids_by_level[level] = future.result()
            print(json.dumps({
                "status": "levelFinished",
                "level": level,
                "accepted": len(grids_by_level[level]),
            }), flush=True)

    selected = [grid for level in LEVELS for grid in grids_by_level[level]]
    answer_uses = Counter(word["answer"] for grid in selected for word in grid["words"])

    counts = Counter(grid["difficulty"] for grid in selected)
    if any(counts[level] < args.count_per_level for level in LEVELS):
        raise SystemExit(f"Catalogue incomplet : {dict(counts)}. Augmenter --retries-per-grid.")

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 2,
        "generatorSeed": args.seed,
        "difficultyRanges": generator.DIFFICULTY_RANGES,
        "maximumAnswerUsesPerLevel": args.max_answer_uses,
        "maximumShortAnswerUsesPerLevel": 3,
        "grids": selected,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "finished",
        "output": str(output),
        "grids": len(selected),
        "byDifficulty": dict(counts),
        "uniqueAnswers": len(answer_uses),
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
