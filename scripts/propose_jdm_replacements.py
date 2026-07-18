"""Refill the four quarantined silhouettes from the central JDM reservoir.

The solver only chooses placements.  Every proposed relation remains staging
until its short clue is read by a human; nothing here publishes to the game.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

import generate_grid_catalog as generator
from build_open_synonym_corpus import normalize_answer
from cp_sat_grid_filler import fill_cp_sat
from grid_topology import audit_grid_topology, render_topology_html
from optimize_grid_shapes import optimize


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
TARGET_IDS = (
    "reference-standard-20",
    "reference-standard-21",
    "reference-standard-27",
    "reference-standard-29",
)
DEFAULT_OUTPUT = ROOT / "src/data/grid-generation-handcrafted/jdm.replacements.staging.json"
DEFAULT_HTML = ROOT / "output/quality/jdm-replacements-review.html"
MINIMUM_RELATION_WEIGHT = 25
MINIMUM_FREQUENCY = 0.1


def load_pool() -> tuple[tuple, dict[str, list[dict]], dict[str, dict], Counter]:
    with gzip.open(DATA / "crossword.jeuxdemots.review.json.gz", "rt", encoding="utf-8") as handle:
        jdm = json.load(handle)
    lexique = json.loads((DATA / "lexique.lemmas.json").read_text(encoding="utf-8"))
    metadata = {entry["answer"]: entry for entry in lexique["entries"]}
    blacklist = json.loads((DATA / "editorial.blacklist.json").read_text(encoding="utf-8"))
    cooldown = {entry["answer"] for entry in blacklist.get("rotationCooldownAnswers", [])}
    blocked = set(blacklist.get("rejectedAnswers", []))
    blocked.update(blacklist.get("rejectedEasyAnswers", []))
    blocked.update(blacklist.get("rejectedNormalAnswers", []))
    blocked.update(generator.FORBIDDEN_ANSWERS)

    catalog = json.loads((DATA / "grid.catalog.json").read_text(encoding="utf-8"))
    quarantined = set(blacklist["quarantinedGridIds"])
    active = [grid for grid in catalog["grids"] if grid["id"] not in quarantined]
    active_usage = Counter(
        word["answer"] for grid in active for word in grid.get("words", [])
    )

    relation_lookup = {
        (entry["answer"], normalize_answer(entry["clue"])): entry
        for entry in jdm["entries"]
    }
    clue_candidates: dict[str, list[dict]] = defaultdict(list)
    for entry in jdm["entries"]:
        answer = entry["answer"]
        clue_answer = normalize_answer(entry["clue"])
        reverse = relation_lookup.get((clue_answer, answer))
        lexical = metadata.get(answer, {})
        if (
            int(entry["sourceRelationWeight"]) < MINIMUM_RELATION_WEIGHT
            or float(lexical.get("sourceFrequency", 0)) < MINIMUM_FREQUENCY
            or lexical.get("partOfSpeech") not in {"NOM", "VER", "ADJ", "ADV"}
            or answer in blocked | cooldown
            or active_usage[answer] > 1
        ):
            continue
        clue_candidates[answer].append({
            **entry,
            "reverseRelationWeight": int(reverse["sourceRelationWeight"]) if reverse else 0,
        })

    for answer, choices in clue_candidates.items():
        choices.sort(
            key=lambda entry: (
                min(entry["sourceRelationWeight"], entry["reverseRelationWeight"]),
                bool(entry["reverseRelationWeight"]),
                entry["sourceRelationWeight"] + entry["reverseRelationWeight"],
                entry["minimumSourceFrequency"],
                -len(entry["clue"]),
            ),
            reverse=True,
        )

    # The JDM relation export intentionally starts at three letters.  Keep a
    # closed list of underused, already reviewed two-letter entries so the
    # approved silhouettes can still be refilled without reviving exhausted
    # short answers.
    short_sources = {}
    for entry in generator.load_entries():
        answer = entry["answer"]
        if (
            len(answer) == 2
            and entry.get("sourceType") == "dictionary"
            and entry.get("editorialStatus") == "human-reviewed"
            and answer not in blocked | cooldown
        ):
            short_sources[answer] = entry

    answers = set(clue_candidates) | set(short_sources)
    by_length = defaultdict(list)
    frequency = {}
    concept_group = {}
    semantic_conflicts = {}
    word_difficulty = {}
    for answer in sorted(answers):
        lexical = metadata.get(answer, {})
        by_length[len(answer)].append(answer)
        source_frequency = float(lexical.get("sourceFrequency", 1))
        frequency[answer] = math.log1p(source_frequency) + 1
        concept_group[answer] = answer
        semantic_conflicts[answer] = {
            normalize_answer(entry["clue"])
            for entry in clue_candidates.get(answer, [])
            if normalize_answer(entry["clue"]) in answers
        }
        word_difficulty[answer] = (
            "easy" if source_frequency >= 15 else "normal" if source_frequency >= 3 else "hard"
        )
    indexes = (
        by_length,
        None,
        frequency,
        concept_group,
        semantic_conflicts,
        word_difficulty,
        set(),
    )
    return indexes, clue_candidates, short_sources, active_usage


def assign_clues(
    answers: list[str],
    candidates: dict[str, list[dict]],
    short_sources: dict[str, dict],
) -> dict[str, dict] | None:
    answer_set = set(answers)
    used_clues = set()
    selected = {}
    for answer in sorted(answers, key=lambda value: (len(candidates.get(value, [])), value)):
        if answer in short_sources:
            entry = short_sources[answer]
            clue_key = normalize_answer(entry["clue"])
            if clue_key in used_clues:
                return None
            selected[answer] = entry
            used_clues.add(clue_key)
            continue
        choice = next((
            entry for entry in candidates[answer]
            if normalize_answer(entry["clue"]) not in answer_set
            and normalize_answer(entry["clue"]) not in used_clues
        ), None)
        if not choice:
            return None
        selected[answer] = choice
        used_clues.add(normalize_answer(choice["clue"]))
    return selected


def build_grid(number: int, target: dict, assignment: dict[int, str], sources: dict[str, dict], telemetry: dict) -> dict:
    grid_id = f"reference-jdm-replacement-{number:02d}"
    words = []
    for index, original in enumerate(target["words"]):
        answer = assignment[index]
        source = sources[answer]
        image = source.get("image") if len(answer) == 2 else None
        words.append({
            "wordId": f"{grid_id}:word:{index + 1:02d}",
            "answer": answer,
            "clue": source["clue"],
            "sourceClue": source.get("sourceClue", source["clue"]),
            "sourceId": source.get("sourceId", "jeuxdemots-r_syn"),
            "sourceUrl": source.get("sourceUrl", "https://www.jeuxdemots.org/jdm-about.php"),
            "sourceType": source.get("sourceType", "lexical-relation"),
            "editorialStatus": "jdm-relation-human-review-required",
            "manualReview": "pending-reject-by-default",
            "conceptGroup": answer,
            "semanticConflicts": sorted({normalize_answer(source["clue"])}),
            "direction": original["direction"],
            "arrow": original["arrow"],
            "clueCell": original["clueCell"],
            "cells": original["cells"],
            **({"image": image} if image else {}),
        })
    return {
        "id": grid_id,
        "columns": 9,
        "rows": 10,
        "editorialProfile": "motman-standard",
        "clueCells": target["clueCells"],
        "words": words,
        "generationMetrics": telemetry,
        "publicationStatus": "manual-review-required",
        "replacesQuarantinedGridId": target["id"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=15072026)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    args = parser.parse_args()
    indexes, candidates, short_sources, active_usage = load_pool()
    catalog = json.loads((DATA / "grid.catalog.json").read_text(encoding="utf-8"))
    previous_shapes = [
        {tuple(cell) for cell in grid.get("clueCells", [])}
        for grid in catalog["grids"]
        if grid["id"] not in TARGET_IDS
    ]
    position_penalties = Counter(
        tuple(cell)
        for shape in previous_shapes
        for cell in shape
        if tuple(cell) != (0, 0)
    )
    rng = random.Random(args.seed)
    accepted = []
    batch_answers = set()
    rejection_counts = Counter()
    for number, replaced_id in enumerate(TARGET_IDS, 1):
        built = None
        for attempt in range(25):
            shape = optimize(
                timeout=1,
                seed=args.seed + number * 100 + attempt,
                visible_clue_cells=rng.randint(24, 25),
                minimum_double_clues=2,
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
                previous_shapes=[],
                maximum_shape_overlap=None,
                position_penalties=position_penalties,
            )
            if not shape:
                rejection_counts["shape"] += 1
                continue
            fingerprint = {tuple(cell) for cell in shape["clueCells"]}
            if fingerprint in previous_shapes:
                rejection_counts["shape:duplicate"] += 1
                continue
            if any(len((fingerprint & previous) - {(0, 0)}) > 22 for previous in previous_shapes):
                rejection_counts["shape:overlap"] += 1
                continue
            length_counts = Counter(len(slot["cells"]) for slot in shape["slots"])
            if length_counts[3] > 8:
                rejection_counts["shape:too-many-length-3"] += 1
                continue
            slots = [generator.Slot(
                slot["direction"], tuple(slot["clue"]),
                tuple(map(tuple, slot["cells"])), slot["arrow"]
            ) for slot in shape["slots"]]
            telemetry = {}
            assignment = fill_cp_sat(
                slots,
                indexes,
                rng,
                None,
                unavailable_answers=batch_answers,
                answer_usage=dict(active_usage),
                grammar_answers=generator.GRAMMAR_ANSWERS,
                max_grammar_answers=1,
                max_seconds=4,
                require_image=False,
                minimum_images=0,
                telemetry=telemetry,
            )
            if assignment is None:
                rejection_counts[f"fill:{telemetry.get('reason', 'failed')}"] += 1
                continue
            answers = [assignment[index] for index in range(len(slots))]
            sources = assign_clues(answers, candidates, short_sources)
            if not sources:
                rejection_counts["clue-assignment"] += 1
                batch_answers.update(answers)
                continue
            target = {
                "id": replaced_id,
                "clueCells": shape["clueCells"],
                "words": [{
                    "direction": slot["direction"],
                    "arrow": slot["arrow"],
                    "clueCell": slot["clue"],
                    "cells": slot["cells"],
                } for slot in shape["slots"]],
            }
            grid = build_grid(number, target, assignment, sources, telemetry)
            report = audit_grid_topology(grid)
            if not report["valid"]:
                rejection_counts.update(
                    f"audit:{error['code']}" for error in report["errors"]
                )
                batch_answers.update(answers)
                continue
            built = grid
            batch_answers.update(answers)
            previous_shapes.append({tuple(cell) for cell in shape["clueCells"]})
            position_penalties.update(fingerprint - {(0, 0)})
            break
        if not built:
            break
        accepted.append(built)
        print(json.dumps({"accepted": len(accepted), "gridId": built["id"]}), flush=True)

    reports = [audit_grid_topology(grid) for grid in accepted]
    document = {
        "version": 1,
        "kind": "jdm-replacement-staging",
        "policy": "Rejet par defaut; revue humaine de chaque relation avant publication.",
        "seed": args.seed,
        "grids": accepted,
        "metrics": {
            "grids": len(accepted),
            "answers": sum(len(grid["words"]) for grid in accepted),
            "uniqueAnswers": len(batch_answers),
            "rejectionCounts": dict(rejection_counts),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.html.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    args.html.write_text(
        render_topology_html(reports, title="MotMan - remplacements JeuxDeMots a relire"),
        encoding="utf-8",
    )
    print(json.dumps(document["metrics"], ensure_ascii=False, indent=2))
    if len(accepted) != len(TARGET_IDS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
