"""Repair a small editorially rejected region without discarding a good grid."""
from __future__ import annotations

import argparse
import copy
import json
import random
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as generator  # noqa: E402
from grid_topology import audit_grid_topology  # noqa: E402
from propose_standard_crossing_drafts import as_grid  # noqa: E402


MUSIC_NOTES = {"DO", "RE", "MI", "FA", "SOL", "LA", "SI"}
OWNER_ROTATION_BLOCK = {
    "AMAS", "AN", "ANS", "BOL", "FER", "ILE", "ILES", "MER", "MERS", "SEL",
}


def answer_family(answer: str) -> str:
    if len(answer) >= 4 and answer.endswith(("S", "X")):
        return answer[:-1]
    return answer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--grid-id", help="Select a grid by id from a multi-grid document")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-answer", action="append", default=[])
    parser.add_argument("--release-radius", type=int, choices=(0, 1, 2, 3, 4), default=1)
    parser.add_argument("--maximum-existing-uses", type=int, default=1)
    parser.add_argument("--maximum-noncanonical-source-answers", type=int, default=10)
    parser.add_argument("--exclude-from", action="append", default=[], type=Path)
    parser.add_argument("--exclude-answer", action="append", default=[])
    parser.add_argument("--fill-seconds", type=float, default=10)
    parser.add_argument("--seed", type=int, default=670_000)
    args = parser.parse_args()

    input_path = args.input if args.input.is_absolute() else ROOT / args.input
    document = json.loads(input_path.read_text(encoding="utf-8"))
    if args.grid_id:
        original = next(
            (grid for grid in document["grids"] if grid.get("id") == args.grid_id),
            None,
        )
        if original is None:
            raise ValueError(f"Unknown grid id: {args.grid_id}")
    else:
        original = document["grids"][0]
    original_words = original["words"]
    slots = [
        generator.Slot(
            word["direction"], tuple(word["clueCell"]),
            tuple(map(tuple, word["cells"])), word["arrow"],
        )
        for word in original_words
    ]
    released = {
        index for index, word in enumerate(original_words)
        if word["answer"] in {value.strip().upper() for value in args.release_answer}
    }
    if not released:
        raise ValueError("No requested release answer occurs in the candidate")

    cell_slots = {}
    for index, slot in enumerate(slots):
        for cell in slot.cells:
            cell_slots.setdefault(cell, set()).add(index)
    for _ in range(args.release_radius):
        released.update(
            neighbor
            for index in list(released)
            for cell in slots[index].cells
            for neighbor in cell_slots[cell]
        )

    active = json.loads(
        (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
    )
    baseline_grids = list(active.get("grids", []))
    for raw_path in args.exclude_from:
        path = raw_path if raw_path.is_absolute() else ROOT / raw_path
        document = json.loads(path.read_text(encoding="utf-8"))
        baseline_grids.extend(document.get("grids", []))
    active_usage = Counter(
        word["answer"]
        for grid in baseline_grids
        for word in grid.get("words", [])
    )
    baseline_families = {
        answer_family(answer) for answer, count in active_usage.items()
        if count >= args.maximum_existing_uses
    }
    unavailable = {
        answer for answer, count in active_usage.items()
        if count >= args.maximum_existing_uses
    } | MUSIC_NOTES | OWNER_ROTATION_BLOCK | {
        answer.strip().upper() for answer in args.exclude_answer if answer.strip()
    }
    entries = generator.load_entries()
    sources = {entry["answer"]: entry for entry in entries}
    unavailable.update(
        entry["answer"] for entry in entries
        if answer_family(entry["answer"]) in baseline_families
    )
    indexes = generator.build_index(
        entries,
        excluded_answers=unavailable,
        min_frequency=0,
        difficulty="normal",
        allow_dictionary_derived=False,
    )
    fixed = {
        index: word["answer"]
        for index, word in enumerate(original_words)
        if index not in released
    }
    # Fixed answers belong to the approved part of the source grid. They may
    # be short forms that the general generator no longer proposes, but the
    # local solver still needs them in its domains to preserve the grid.
    unavailable.difference_update(fixed.values())
    by_length, position_index, frequency, concept_group, semantic_conflicts, word_difficulty, image_answers = indexes
    for index, answer in fixed.items():
        length = len(answer)
        if answer not in by_length[length]:
            by_length[length].append(answer)
            for position, letter in enumerate(answer):
                position_index[length][position][letter].add(answer)
            frequency[answer] = 1
            concept_group[answer] = answer_family(answer)
            semantic_conflicts[answer] = set()
            word_difficulty[answer] = "normal"
        sources.setdefault(answer, {
            **original_words[index],
            "sourceClue": original_words[index].get("clue", ""),
            "frequency": 1,
        })
    fixed_families = {answer_family(answer) for answer in fixed.values()}
    unavailable.update(
        entry["answer"] for entry in entries
        if answer_family(entry["answer"]) in fixed_families
        and entry["answer"] not in fixed.values()
    )
    lexical_by_answer = {
        entry["answer"]: entry for entry in json.loads(
            (ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8")
        )["entries"]
    }

    def safe_for_unattended_fill(answer: str) -> bool:
        source = sources[answer]
        if len(answer) == 2:
            return source.get("shortAnswerApproved") is True
        if (
            source.get("editorialStatus") == "human-reviewed"
            or source.get("sourceType") in {
                "image", "dictionary", "editorial-original", "lexical-relation"
            }
            or str(source.get("sourceId", "")).startswith("jeuxdemots")
        ):
            return True
        lexical = lexical_by_answer.get(answer, {})
        if float(lexical.get("sourceFrequency", 0)) < 1.0:
            return False
        part_of_speech = lexical.get("partOfSpeech")
        lemma = lexical.get("lemma", answer)
        if part_of_speech == "NOM":
            return True
        if part_of_speech in {"ADJ", "ADV"}:
            return answer == lemma
        if part_of_speech == "VER":
            return str(lexical.get("verbInfo", "")).startswith("inf")
        return False

    indexed_answers = {
        answer for answers in indexes[0].values() for answer in answers
    }
    undesirable_answers = {
        answer for answer in indexed_answers if not safe_for_unattended_fill(answer)
    }
    telemetry = {}
    answers = generator.fill_bitset(
        slots,
        indexes,
        random.Random(args.seed),
        None,
        unavailable_answers=unavailable,
        grammar_answers=generator.GRAMMAR_ANSWERS,
        max_grammar_answers=2,
        max_seconds=args.fill_seconds,
        node_limit=2_000_000,
        require_image=False,
        minimum_images=0,
        fixed_answers=fixed,
        undesirable_answers=undesirable_answers,
        max_undesirable_answers=args.maximum_noncanonical_source_answers,
        prefer_constraint_support=True,
        constraint_support_bucket_size=8,
        telemetry=telemetry,
    )
    if answers is None:
        raise SystemExit(json.dumps({
            "accepted": 0,
            "releasedSlots": sorted(released),
            "telemetry": telemetry,
        }, ensure_ascii=False))

    shape = {
        "clueCells": original["clueCells"],
        "slots": [
            {
                "direction": word["direction"],
                "arrow": word["arrow"],
                "clue": word["clueCell"],
                "cells": word["cells"],
                "length": len(word["cells"]),
            }
            for word in original_words
        ],
    }
    repaired = as_grid(1, shape, answers, sources, telemetry)
    repaired["id"] = f"{original['id']}-repaired"
    for index in fixed:
        repaired["words"][index] = copy.deepcopy(original_words[index])
    for number, word in enumerate(repaired["words"], 1):
        word["wordId"] = f"{repaired['id']}:word:{number:02d}"
    report = audit_grid_topology(repaired)
    if not report["valid"]:
        raise ValueError(report["errors"])
    families = [answer_family(word["answer"]) for word in repaired["words"]]
    if len(families) != len(set(families)):
        raise ValueError("singular/plural family duplicated after local repair")
    changes = [
        {
            "slot": index + 1,
            "oldAnswer": original_words[index]["answer"],
            "newAnswer": repaired["words"][index]["answer"],
            "newClue": repaired["words"][index]["clue"],
        }
        for index in sorted(released)
        if original_words[index]["answer"] != repaired["words"][index]["answer"]
    ]
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 1,
        "kind": "owner-review-local-repair",
        "sourceCandidate": str(input_path),
        "releasedSlots": [index + 1 for index in sorted(released)],
        "changes": changes,
        "grids": [repaired],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "accepted": 1,
        "releasedSlots": len(released),
        "changes": changes,
        "output": str(output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
