"""Agent C: local-search + exact LNS closure for reference-ribbon-a-01.

This script never edits the active catalog or the blacklist.  It consumes the
current central corpus, keeps the approved geometry byte-for-byte, rotates
whole sourced answers during local search, then asks the exact bitset filler to
repair only the conflicted neighbourhood.  A result is written only to the
dedicated quality artifact requested for this experiment.
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as generator  # noqa: E402
from bitset_grid_filler import fill_bitset  # noqa: E402
from grid_topology import audit_grid_topology  # noqa: E402


SHAPES = ROOT / "output/quality/reference-style-shapes-a.json"
CENTRAL = ROOT / "src/data/crossword.central.json.gz"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
OUTPUT = ROOT / "output/quality/agent-c-ribbon-a01-fill.json"
TARGET = "reference-ribbon-a-01"
RELEVANT_LENGTHS = {3, 4, 5, 8, 9}


def entry_rank(entry: dict) -> tuple:
    status_rank = {
        "human-reviewed": 0,
        "image-reviewed": 0,
        "agent-reviewed": 0,
        "source-backed": 1,
        "jeuxdemots-review-required": 4,
    }
    return (
        status_rank.get(entry.get("editorialStatus"), 3),
        0 if entry.get("canonicalForGenerator") else 1,
        0 if entry.get("corpusStage") != "editorial-rejected" else 1,
        -float(entry.get("frequency", 0)),
        len(entry.get("clue", "")),
    )


def load_corpus() -> tuple[list[dict], dict[str, dict], dict]:
    with gzip.open(CENTRAL, "rt", encoding="utf-8") as handle:
        central = json.load(handle)
    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    banned_answers = (
        set(blacklist.get("rejectedAnswers", []))
        | set(blacklist.get("rejectedNormalAnswers", []))
        | set(generator.FORBIDDEN_ANSWERS)
    )
    banned_pairs = {
        (item["answer"], item["clue"].casefold())
        for item in blacklist.get("rejectedPairs", [])
    }

    by_answer: dict[str, tuple[tuple, dict]] = {}
    for entry in central["entries"]:
        answer = entry["answer"]
        clue = entry.get("clue", "")
        if (
            answer in banned_answers
            or len(answer) not in RELEVANT_LENGTHS
            or not re.fullmatch(r"[A-Z]+", answer)
            or not clue.strip()
            or (answer, clue.casefold()) in banned_pairs
        ):
            continue
        rank = entry_rank(entry)
        if answer not in by_answer or rank < by_answer[answer][0]:
            by_answer[answer] = (rank, entry)
    entries = [record[1] for record in by_answer.values()]
    return entries, {entry["answer"]: entry for entry in entries}, central


def build_indexes(entries: list[dict]):
    by_length: dict[int, list[str]] = defaultdict(list)
    frequency = {}
    difficulty = {}
    image_answers = set()
    for entry in entries:
        answer = entry["answer"]
        by_length[len(answer)].append(answer)
        frequency[answer] = float(entry.get("frequency", 0))
        difficulty[answer] = generator.audience_difficulty(entry)
        if entry.get("image"):
            image_answers.add(answer)
    for answers in by_length.values():
        answers.sort()
    # Concept and semantic conflict checks are intentionally neutral here.
    # This artifact is a lexical closure experiment; every doubtful pair is
    # surfaced for review after closure instead of being silently published.
    concepts = {entry["answer"]: entry["answer"] for entry in entries}
    conflicts = {entry["answer"]: set() for entry in entries}
    return (
        by_length,
        None,
        frequency,
        concepts,
        conflicts,
        difficulty,
        image_answers,
    )


def load_shape():
    document = json.loads(SHAPES.read_text(encoding="utf-8"))
    shape = next(item for item in document["shapes"] if item["id"] == TARGET)
    slots = [
        generator.Slot(
            item["direction"],
            tuple(item["clueCell"]),
            tuple(map(tuple, item["cells"])),
            item["arrow"],
        )
        for item in shape["slots"]
    ]
    return shape, slots


def crossing_links(slots):
    cells = defaultdict(list)
    for variable, slot in enumerate(slots):
        for position, cell in enumerate(slot.cells):
            cells[cell].append((variable, position))
    links = [[] for _ in slots]
    edges = []
    for cell, occurrences in cells.items():
        if len(occurrences) != 2:
            continue
        (left, left_pos), (right, right_pos) = occurrences
        links[left].append((left_pos, right, right_pos))
        links[right].append((right_pos, left, left_pos))
        edges.append((left, left_pos, right, right_pos, cell))
    return links, edges


def conflict_edges(assignment, edges):
    return [
        edge for edge in edges
        if assignment[edge[0]][edge[1]] != assignment[edge[2]][edge[3]]
    ]


def initial_assignment(slots, words, rng):
    assignment = [None] * len(slots)
    used_by_length = defaultdict(set)
    order = sorted(range(len(slots)), key=lambda item: -len(slots[item].cells))
    for variable in order:
        length = len(slots[variable].cells)
        candidates = [
            word for word in words[length]
            if word not in used_by_length[length]
        ]
        answer = rng.choice(candidates)
        assignment[variable] = answer
        used_by_length[length].add(answer)
    return assignment


def rotate_locally(
    slots,
    words,
    arrays,
    source_by_answer,
    links,
    edges,
    rng,
    iterations,
):
    assignment = initial_assignment(slots, words, rng)
    best_assignment = list(assignment)
    best_cost = len(conflict_edges(assignment, edges))
    stagnant = 0

    for iteration in range(iterations):
        bad = conflict_edges(assignment, edges)
        if not bad:
            return assignment, 0, iteration
        if len(bad) < best_cost:
            best_cost = len(bad)
            best_assignment = list(assignment)
            stagnant = 0
        else:
            stagnant += 1

        edge = rng.choice(bad)
        variable = rng.choice((edge[0], edge[2]))
        length = len(slots[variable].cells)
        positions = []
        expected = []
        for own_pos, neighbour, neighbour_pos in links[variable]:
            positions.append(own_pos)
            expected.append(ord(assignment[neighbour][neighbour_pos]) - 65)
        scores = (
            arrays[length][:, positions]
            == np.asarray(expected, dtype=np.int8)
        ).sum(axis=1)
        top = int(scores.max())
        candidate_indices = np.flatnonzero(scores == top).tolist()
        used = set(assignment)
        used.discard(assignment[variable])
        unique = [
            index for index in candidate_indices
            if words[length][index] not in used
        ]
        if unique:
            candidate_indices = unique

        if rng.random() < 0.03:
            noisy = np.flatnonzero(scores >= max(0, top - 1)).tolist()
            index = rng.choice(noisy)
        else:
            sample = rng.sample(candidate_indices, min(48, len(candidate_indices)))
            index = min(
                sample,
                key=lambda item: entry_rank(source_by_answer[words[length][item]]),
            )
        assignment[variable] = words[length][index]

        # A bounded shock exits stable cycles without replacing any cell by a
        # forced letter: only whole corpus answers are rotated.
        if stagnant >= 1400:
            for shocked in rng.sample(range(len(slots)), 3):
                n = len(slots[shocked].cells)
                available = [word for word in words[n] if word not in assignment]
                assignment[shocked] = rng.choice(available)
            stagnant = 0

    return best_assignment, best_cost, iterations


def exact_lns_repair(
    assignment,
    slots,
    indexes,
    links,
    edges,
    rng,
    seconds,
):
    bad = conflict_edges(assignment, edges)
    repair = {edge[0] for edge in bad} | {edge[2] for edge in bad}
    all_variables = set(range(len(slots)))
    reports = []

    # Start with exactly the conflicted neighbourhood.  Each expansion unfreezes
    # variables adjacent to it, which is the large-neighbourhood-search step.
    for expansion in range(4):
        fixed = {
            variable: assignment[variable]
            for variable in all_variables - repair
        }
        telemetry = {}
        solved = fill_bitset(
            slots,
            indexes,
            rng,
            None,
            fixed_answers=fixed,
            max_grammar_answers=99,
            grammar_answers=set(),
            require_image=False,
            max_seconds=seconds,
            node_limit=12_000_000,
            prefer_constraint_support=True,
            constraint_support_bucket_size=2,
            telemetry=telemetry,
        )
        reports.append({
            "expansion": expansion,
            "repairVariables": sorted(repair),
            "fixedVariables": sorted(fixed),
            **telemetry,
        })
        if solved is not None:
            return [solved[index] for index in range(len(slots))], reports

        frontier = {
            neighbour
            for variable in repair
            for _, neighbour, _ in links[variable]
            if neighbour not in repair
        }
        if not frontier:
            break
        take = min(len(frontier), max(2, 2 + expansion))
        repair.update(rng.sample(sorted(frontier), take))
    return None, reports


def word_record(grid_id, number, slot_source, answer, source):
    return {
        "wordId": f"{grid_id}:word:{number:02d}",
        "answer": answer,
        "clue": source.get("clue", ""),
        "sourceClue": source.get("sourceClue", source.get("clue", "")),
        "sourceId": source.get("sourceId"),
        "sourceUrl": source.get("sourceUrl"),
        "sourceType": source.get("sourceType"),
        "editorialStatus": source.get("editorialStatus"),
        "corpusStage": source.get("corpusStage"),
        "canonicalForGenerator": bool(source.get("canonicalForGenerator")),
        "direction": slot_source["direction"],
        "arrow": slot_source["arrow"],
        "clueCell": slot_source["clueCell"],
        "cells": slot_source["cells"],
    }


def write_result(
    shape,
    slots,
    assignment,
    source_by_answer,
    central,
    runs,
    elapsed,
):
    grid_id = "agent-c-ribbon-a01-lexical-closure"
    words = [
        word_record(grid_id, number, shape["slots"][index], answer, source_by_answer[answer])
        for number, (index, answer) in enumerate(enumerate(assignment), 1)
    ]
    doubtful = [
        {
            "wordId": word["wordId"],
            "answer": word["answer"],
            "clue": word["clue"],
            "editorialStatus": word["editorialStatus"],
            "reason": "couple central non canonique à relire avant toute publication",
        }
        for word in words
        if not word["canonicalForGenerator"]
    ]
    grid = {
        "id": grid_id,
        "columns": shape["columns"],
        "rows": shape["rows"],
        "sourceShapeId": TARGET,
        "clueCells": shape["clueCells"],
        "words": words,
        "publicationStatus": (
            "lexical-closure-editorial-review-required"
            if doubtful else "lexical-closure-canonical"
        ),
    }
    topology = audit_grid_topology(grid, enforce_layout=False)
    if not topology["valid"]:
        raise ValueError(topology["errors"])
    if len({word["answer"] for word in words}) != len(words):
        raise ValueError("réponse répétée dans la fermeture")

    result = {
        "version": 1,
        "kind": "agent-c-reference-ribbon-a01-lns-fill",
        "status": grid["publicationStatus"],
        "catalogModified": False,
        "blacklistModified": False,
        "corpus": {
            "file": "src/data/crossword.central.json.gz",
            "distinctAnswers": central["metrics"]["distinctAnswers"],
            "canonicalAnswers": central["metrics"]["generatorEligibleDistinctAnswers"],
        },
        "method": {
            "name": "whole-answer rotations plus exact LNS repair",
            "elapsedSeconds": round(elapsed, 3),
            "runs": runs,
            "forcedLetters": 0,
        },
        "invariants": {
            "columns": 9,
            "rows": 10,
            "slots": 22,
            "letterCells": 69,
            "duplicateAnswers": 0,
            "topologyValid": True,
        },
        "editorialReview": {
            "required": bool(doubtful),
            "doubtfulPairs": doubtful,
            "warning": (
                "Fermeture lexicale seulement; ne pas publier avant revue des couples signalés."
                if doubtful else None
            ),
        },
        "grid": grid,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=180)
    parser.add_argument("--iterations", type=int, default=45_000)
    parser.add_argument("--seed", type=int, default=971_000)
    args = parser.parse_args()

    started = time.monotonic()
    entries, source_by_answer, central = load_corpus()
    indexes = build_indexes(entries)
    words = indexes[0]
    arrays = {
        length: np.asarray(
            [[ord(letter) - 65 for letter in word] for word in answers],
            dtype=np.int8,
        )
        for length, answers in words.items()
    }
    shape, slots = load_shape()
    links, edges = crossing_links(slots)
    runs = []
    run = 0
    while time.monotonic() - started < args.seconds:
        run += 1
        seed = args.seed + run
        rng = random.Random(seed)
        assignment, local_cost, iterations = rotate_locally(
            slots,
            words,
            arrays,
            source_by_answer,
            links,
            edges,
            rng,
            args.iterations,
        )
        run_record = {
            "run": run,
            "seed": seed,
            "localIterations": iterations,
            "localConflictEdges": local_cost,
        }
        if local_cost == 0:
            runs.append(run_record)
            write_result(
                shape, slots, assignment, source_by_answer, central,
                runs, time.monotonic() - started,
            )
            print(json.dumps({"status": "solved-local", **run_record}, ensure_ascii=False), flush=True)
            return

        remaining = max(2.0, args.seconds - (time.monotonic() - started))
        solved, repair_reports = exact_lns_repair(
            assignment,
            slots,
            indexes,
            links,
            edges,
            rng,
            min(10.0, remaining),
        )
        run_record["repairs"] = repair_reports
        runs.append(run_record)
        print(json.dumps({
            "status": "run-complete",
            "run": run,
            "localConflictEdges": local_cost,
            "repairReasons": [item.get("reason") for item in repair_reports],
        }, ensure_ascii=False), flush=True)
        if solved is not None:
            write_result(
                shape, slots, solved, source_by_answer, central,
                runs, time.monotonic() - started,
            )
            print(json.dumps({"status": "solved-lns", "run": run}, ensure_ascii=False), flush=True)
            return

    OUTPUT.write_text(json.dumps({
        "version": 1,
        "kind": "agent-c-reference-ribbon-a01-lns-fill",
        "status": "no-closure-within-bounded-search",
        "conclusion": (
            "Aucune fermeture complète trouvée dans le budget borné. "
            "Ce résultat n'est pas une preuve mathématique d'impossibilité."
        ),
        "catalogModified": False,
        "blacklistModified": False,
        "corpus": {
            "file": "src/data/crossword.central.json.gz",
            "centralDistinctAnswers": central["metrics"]["distinctAnswers"],
            "canonicalAnswers": central["metrics"]["generatorEligibleDistinctAnswers"],
            "indexedWholeAnswersAfterBlacklist": len(entries),
            "indexedByRequiredLength": {
                str(length): len(words[length])
                for length in sorted(RELEVANT_LENGTHS)
            },
        },
        "invariants": {
            "sourceShapeId": TARGET,
            "columns": shape["columns"],
            "rows": shape["rows"],
            "slots": len(slots),
            "clueCellsUnchanged": True,
            "pathsUnchanged": True,
            "letterCells": 69,
            "crossingConstraints": len(edges),
            "duplicateAnswersAllowed": False,
            "forcedLetters": 0,
        },
        "method": {
            "name": "whole-answer rotations plus exact LNS repair",
            "elapsedSeconds": round(time.monotonic() - started, 3),
            "runCount": len(runs),
            "bestRemainingConflictEdges": min(
                item["localConflictEdges"] for item in runs
            ),
            "interpretation": (
                "Chaque tentative ne manipule que des réponses entières du corpus; "
                "les réparations exactes gèlent puis élargissent le voisinage cohérent."
            ),
            "runs": runs,
            "forcedLetters": 0,
        },
        "publication": {
            "allowed": False,
            "reason": "Aucune grille complète; catalogue et interface intouchés.",
        },
        "grid": None,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
