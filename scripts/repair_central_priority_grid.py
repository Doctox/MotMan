"""Repair only the rejected neighbourhood of a corpus-priority draft.

The script keeps every acceptable answer fixed, releases rejected answers and
their crossing neighbours, then asks the deterministic filler for a local
replacement.  Nothing is published; the output remains owner-review staging.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import random
from pathlib import Path

import generate_grid_catalog as generator
from grid_topology import audit_grid_topology
from propose_standard_crossing_drafts import as_grid
from search_audience_shapes import audience_index


ROOT = Path(__file__).resolve().parents[1]


def answer_family(answer: str) -> str:
    if len(answer) >= 4 and answer.endswith(("S", "X")):
        return answer[:-1]
    return answer


def load_pool(
    seed: int,
    minimum_frequency: float = 0,
    minimum_lexique_frequency: float = 0,
):
    entries = generator.load_entries()
    central = {entry["answer"]: entry for entry in entries}
    lexicon = {
        entry["answer"]: entry for entry in json.loads(
            (ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8")
        )["entries"]
    }
    indexes = audience_index(
        "normal", minimum_frequency, "placement", canonical_forms_only=True
    )
    strong_three = {
        answer for answer, entry in lexicon.items()
        if len(answer) == 3 and float(entry.get("sourceFrequency", 0)) >= 3
    }
    strong_three.update(
        entry["answer"] for entry in entries
        if len(entry["answer"]) == 3 and (
            entry.get("sourceType") in {"image", "dictionary", "editorial-original"}
            or entry.get("image")
            or str(entry.get("sourceId", "")).startswith("jeuxdemots")
        )
    )
    def strict_canonical(answer: str) -> bool:
        source = central.get(answer, {})
        lexical = lexicon.get(answer, {})
        if len(answer) <= 3:
            return answer in strong_three
        if source.get("sourceType") in {"image", "editorial-original"}:
            return True
        if float(lexical.get("sourceFrequency", 0)) < minimum_lexique_frequency:
            return False
        part_of_speech = lexical.get("partOfSpeech")
        lemma = lexical.get("lemma", answer)
        if part_of_speech in {"NOM", "ADJ", "ADV"}:
            return answer == lemma
        if part_of_speech == "VER":
            return str(lexical.get("verbInfo", "")).startswith("inf")
        return False

    by_length = {
        length: [answer for answer in answers if strict_canonical(answer)]
        for length, answers in indexes[0].items()
    }
    allowed = {answer for answers in by_length.values() for answer in answers}
    sources = dict(central)
    for answer in allowed - set(central):
        lexical = lexicon.get(answer, {})
        sources[answer] = {
            "answer": answer,
            "clue": "",
            "sourceClue": "",
            "sourceId": "lexique-3.83",
            "sourceUrl": "http://www.lexique.org/databases/Lexique383/Lexique383.tsv",
            "sourceType": "lexical-attestation",
            "editorialStatus": "manual-clue-required",
            "conceptGroup": answer,
            "semanticConflicts": [],
            "frequency": lexical.get("sourceFrequency", 0),
        }
    jitter = random.Random(seed ^ 0x9491)
    frequency = {}
    for answer in allowed:
        source = sources[answer]
        observed = max(
            float(source.get("frequency", source.get("sourceFrequency", 0))),
            float(lexicon.get(answer, {}).get("sourceFrequency", 0)),
        )
        frequency[answer] = (
            math.log1p(observed) + 1
            + (0.15 if answer in central else 0)
            + (1.5 if source.get("image") else 0)
            + jitter.uniform(-0.25, 0.25)
        )
    filtered = (
        by_length,
        indexes[1],
        frequency,
        *[
            {answer: value for answer, value in mapping.items() if answer in allowed}
            for mapping in indexes[3:6]
        ],
        indexes[6] & allowed,
    )
    return filtered, sources, allowed, set(central)


def neighbours(words: list[dict]) -> dict[int, set[int]]:
    paths = [set(map(tuple, word["cells"])) for word in words]
    return {
        index: {other for other in range(len(words)) if other != index and path & paths[other]}
        for index, path in enumerate(paths)
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--grid", type=int, default=1)
    parser.add_argument("--grid-id", help="Select a grid by id from a multi-grid document")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=9491)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--minimum-frequency", type=float, default=0)
    parser.add_argument("--minimum-lexique-frequency", type=float, default=0)
    parser.add_argument("--maximum-depth", type=int, default=3)
    parser.add_argument("--reject", action="append", default=[])
    parser.add_argument(
        "--replace", action="append", default=[], metavar="OLD=NEW",
        help="Force a same-length answer replacement while repairing its crossings.",
    )
    args = parser.parse_args()

    source_path = args.input if args.input.is_absolute() else ROOT / args.input
    document = json.loads(source_path.read_text(encoding="utf-8"))
    if args.grid_id:
        original = next(
            (grid for grid in document["grids"] if grid.get("id") == args.grid_id),
            None,
        )
        if original is None:
            raise ValueError(f"Unknown grid id: {args.grid_id}")
    else:
        original = document["grids"][args.grid - 1]
    indexes, sources, allowed, central = load_pool(
        args.seed, args.minimum_frequency, args.minimum_lexique_frequency
    )
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    replacements = {}
    for value in args.replace:
        if "=" not in value:
            raise SystemExit(f"Invalid replacement {value!r}; expected OLD=NEW")
        old, new = (part.strip().upper() for part in value.split("=", 1))
        if len(old) != len(new):
            raise SystemExit(f"Replacement must keep length: {old} -> {new}")
        replacements[old] = new
    rejected = set(blacklist.get("rejectedAnswers", [])) | {
        answer.upper() for answer in args.reject
    } | set(replacements)
    words = original["words"]
    by_length, position_index, frequency, concept_group, semantic_conflicts, word_difficulty, image_answers = indexes
    for answer in list(concept_group):
        concept_group[answer] = answer_family(answer)
    for word in words:
        answer = word["answer"]
        length = len(answer)
        if answer not in by_length[length]:
            by_length[length].append(answer)
            if position_index is not None:
                for position, letter in enumerate(answer):
                    position_index[length][position][letter].add(answer)
            frequency[answer] = 1
            concept_group[answer] = answer_family(answer)
            semantic_conflicts[answer] = set()
            word_difficulty[answer] = "normal"
            if word.get("image"):
                image_answers.add(answer)
        sources.setdefault(answer, {
            **word,
            "sourceClue": word.get("clue", ""),
            "frequency": 1,
        })
        allowed.add(answer)
    adjacency = neighbours(words)
    initially_free = {
        index for index, word in enumerate(words)
        if word["answer"] in rejected or word["answer"] not in allowed
    }
    if not initially_free:
        raise SystemExit("No rejected or unavailable answer to repair")

    shape = {
        "clueCells": original["clueCells"],
        "slots": [{
            "direction": word["direction"],
            "arrow": word["arrow"],
            "clue": word["clueCell"],
            "cells": word["cells"],
            "length": len(word["cells"]),
        } for word in words],
    }
    slots = [
        generator.Slot(
            slot["direction"], tuple(slot["clue"]),
            tuple(map(tuple, slot["cells"])), slot["arrow"],
        )
        for slot in shape["slots"]
    ]
    free = set(initially_free)
    forced = {}
    for index, word in enumerate(words):
        if word["answer"] not in replacements:
            continue
        replacement = replacements[word["answer"]]
        if replacement not in allowed:
            raise SystemExit(f"Forced replacement is unavailable: {replacement}")
        forced[index] = replacement
    result = None
    telemetry = {}
    used_depth = 0
    for depth in range(1, args.maximum_depth + 1):
        free |= {neighbour for index in tuple(free) for neighbour in adjacency[index]}
        fixed = {
            index: word["answer"] for index, word in enumerate(words) if index not in free
        }
        fixed.update(forced)
        telemetry = {}
        result = generator.fill_bitset(
            slots,
            indexes,
            random.Random(args.seed + depth * 1009),
            None,
            unavailable_answers=rejected,
            fixed_answers=fixed,
            max_grammar_answers=3,
            grammar_answers=generator.GRAMMAR_ANSWERS,
            max_seconds=args.seconds,
            node_limit=3_000_000,
            require_image=False,
            minimum_images=0,
            prefer_constraint_support=True,
            constraint_support_bucket_size=8,
            telemetry=telemetry,
        )
        if result is not None:
            used_depth = depth
            break
    if result is None:
        raise SystemExit(json.dumps({
            "repaired": False,
            "initiallyRejected": sorted(words[index]["answer"] for index in initially_free),
            "releasedSlots": len(free),
            "telemetry": telemetry,
        }, ensure_ascii=False))

    repaired = as_grid(1, shape, result, sources, telemetry)
    repaired["id"] = f"{original['id']}-repaired"
    repaired["publicationStatus"] = "manual-review-required"
    repaired["corpusPolicy"] = "local-human-frequency-repair-central-9491"
    repaired["repairDepth"] = used_depth
    repaired["repairedAnswers"] = sorted(words[index]["answer"] for index in initially_free)
    repaired["centralAnswerCount"] = sum(answer in central for answer in result.values())
    repaired["lexiqueRescueCount"] = sum(answer not in central for answer in result.values())
    for index, word in enumerate(words):
        if index not in free:
            repaired["words"][index] = copy.deepcopy(word)
    for number, word in enumerate(repaired["words"], 1):
        word["wordId"] = f"{repaired['id']}:word:{number:02d}"
    report = audit_grid_topology(repaired)
    # Source clues in repair drafts are placeholders and will be replaced by
    # the manual review builder.  Only geometry/topology is blocking here;
    # editorial clue gates run again on the final hand-edited records.
    blocking = [
        error for error in report["errors"]
        if error["code"] != "empty_clue"
        and not error["code"].startswith("clue_")
    ]
    if blocking:
        raise SystemExit(json.dumps({"repaired": False, "topology": blocking}, ensure_ascii=False))

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 1,
        "kind": "non-publishable-local-repair",
        "source": str(source_path),
        "grids": [repaired],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "repaired": True,
        "depth": used_depth,
        "releasedSlots": len(free),
        "central": repaired["centralAnswerCount"],
        "rescue": repaired["lexiqueRescueCount"],
        "answers": [word["answer"] for word in repaired["words"]],
        "output": str(output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
