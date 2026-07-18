"""Fill the three owner-approved long-answer shapes from the full central corpus.

This is deliberately a proof-producing raw stage. All canonical central
answers are loaded into one index. Geometry and explicit no-repeat exclusions
may make an answer unavailable, but no hidden quality subset is substituted.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as generator  # noqa: E402
from bitset_grid_filler import fill_bitset  # noqa: E402
from grid_topology import audit_grid_topology  # noqa: E402


SHAPES = ROOT / "src/data/grid-generation-handcrafted/long-answer-shapes.review.json"
CATALOG = ROOT / "src/data/grid.catalog.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
OUTPUT = ROOT / "output/quality/full-corpus-long-grid-raw.json"
TARGET_SHAPES = (
    "long-answer-shape-01",
    "long-answer-shape-04",
    "long-answer-shape-05",
)
BASE_SEED = 816_000
MINIMUM_CANONICAL_ANSWERS = 10_000


def answer_family(answer: str) -> str:
    if len(answer) >= 4 and answer.endswith(("S", "X")):
        return answer[:-1]
    return answer


def corpus_digest(entries: list[dict]) -> str:
    rows = sorted(
        f"{entry['answer']}\t{entry['clue']}\t{entry.get('sourceId', '')}"
        for entry in entries
    )
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def full_index(entries: list[dict]):
    by_length: dict[int, list[str]] = defaultdict(list)
    frequency = {}
    concept_group = {}
    semantic_conflicts = {}
    word_difficulty = {}
    image_answers = set()
    for entry in entries:
        answer = entry["answer"]
        by_length[entry["length"]].append(answer)
        frequency[answer] = float(entry.get("frequency", 0))
        concept_group[answer] = entry.get("conceptGroup", answer)
        semantic_conflicts[answer] = set(entry.get("semanticConflicts", []))
        word_difficulty[answer] = generator.audience_difficulty(entry)
        if entry.get("image"):
            image_answers.add(answer)
    for answers in by_length.values():
        answers.sort()
    return by_length, None, frequency, concept_group, semantic_conflicts, word_difficulty, image_answers


def word_record(grid_id: str, number: int, slot: dict, answer: str, source: dict) -> dict:
    record = {
        "wordId": f"{grid_id}:word:{number:02d}",
        "answer": answer,
        "clue": source["clue"],
        "sourceClue": source.get("sourceClue", source["clue"]),
        "sourceId": source.get("sourceId"),
        "sourceUrl": source.get("sourceUrl"),
        "sourceType": source.get("sourceType"),
        "editorialStatus": source.get("editorialStatus"),
        "manualReview": "pending-owner-review",
        "definitionStatus": "central-canonical-raw",
        "conceptGroup": source.get("conceptGroup", answer),
        "semanticConflicts": source.get("semanticConflicts", []),
        "direction": slot["direction"],
        "arrow": slot["arrow"],
        "clueCell": slot["clue"],
        "cells": slot["cells"],
    }
    if source.get("image"):
        record["image"] = source["image"]
        record["clue"] = ""
    return record


def main() -> None:
    entries = generator.load_entries()
    if (
        len(entries) < MINIMUM_CANONICAL_ANSWERS
        or len({entry["answer"] for entry in entries}) != len(entries)
    ):
        raise ValueError(
            "Le corpus central est incomplet ou contient des réponses dupliquées "
            f"({len(entries)} chargées, minimum {MINIMUM_CANONICAL_ANSWERS})"
        )
    sources = {entry["answer"]: entry for entry in entries}
    indexes = full_index(entries)
    by_length = indexes[0]

    shapes_document = json.loads(SHAPES.read_text(encoding="utf-8"))
    approved_ids = set(shapes_document["ownerApprovedShapeIds"])
    if set(TARGET_SHAPES) - approved_ids:
        raise ValueError("Une silhouette cible n'est pas approuvée")
    shapes = {
        shape["id"]: shape for shape in shapes_document["shapes"]
        if shape["id"] in TARGET_SHAPES
    }
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    quarantined = set(blacklist.get("quarantinedGridIds", []))
    playable_grids = [
        grid for grid in catalog["grids"] if grid["id"] not in quarantined
    ]
    active_answers = {
        word["answer"] for grid in playable_grids for word in grid["words"]
    }
    active_families = {answer_family(answer) for answer in active_answers}
    active_family_exclusions = {
        entry["answer"] for entry in entries
        if answer_family(entry["answer"]) in active_families
    }

    corpus_by_length = Counter(entry["length"] for entry in entries)
    source_counts = Counter(entry.get("sourceId", "<sans-source>") for entry in entries)
    selected_answers: set[str] = set()
    selected_families: set[str] = set()
    accepted = []
    attempts_report = []

    for grid_number, shape_id in enumerate(TARGET_SHAPES, 1):
        shape = shapes[shape_id]
        slots = [
            generator.Slot(
                slot["direction"], tuple(slot["clue"]),
                tuple(map(tuple, slot["cells"])), slot["arrow"],
            )
            for slot in shape["slots"]
        ]
        grid_exclusions = set(active_family_exclusions) | selected_answers
        grid_exclusions.update(
            entry["answer"] for entry in entries
            if answer_family(entry["answer"]) in selected_families
        )
        solved = None
        solved_telemetry = None
        local_rejections = Counter()
        for attempt in range(8):
            telemetry = {}
            answers = fill_bitset(
                slots,
                indexes,
                random.Random(BASE_SEED + grid_number * 100 + attempt),
                None,
                unavailable_answers=grid_exclusions,
                answer_usage={},
                grammar_answers=generator.GRAMMAR_ANSWERS,
                max_grammar_answers=2,
                max_seconds=6,
                node_limit=700_000,
                require_image=True,
                minimum_images=1,
                prefer_constraint_support=True,
                constraint_support_bucket_size=8,
                telemetry=telemetry,
            )
            attempts_report.append({
                "shapeId": shape_id,
                "attempt": attempt + 1,
                "seed": BASE_SEED + grid_number * 100 + attempt,
                **telemetry,
            })
            if answers is None:
                local_rejections[f"fill-{telemetry.get('reason', 'failed')}"] += 1
                continue
            values = list(answers.values())
            families = [answer_family(answer) for answer in values]
            duplicates = [
                family for family, count in Counter(families).items() if count > 1
            ]
            if duplicates:
                local_rejections["singular-plural-family"] += 1
                for family in duplicates:
                    variants = sorted(answer for answer in values if answer_family(answer) == family)
                    grid_exclusions.add(variants[-1])
                continue
            solved = answers
            solved_telemetry = telemetry
            break
        if solved is None:
            raise SystemExit(f"{shape_id}: aucun remplissage borné {dict(local_rejections)}")

        grid_id = f"full-corpus-long-review-{grid_number:02d}"
        words = [
            word_record(grid_id, number, shape["slots"][slot_index], solved[slot_index], sources[solved[slot_index]])
            for number, slot_index in enumerate(sorted(solved), 1)
        ]
        grid = {
            "id": grid_id,
            "columns": 9,
            "rows": 10,
            "editorialProfile": "motman-full-corpus-long-review",
            "layoutProfile": "owner-approved-long-answer-wall",
            "sourceShapeId": shape_id,
            "clueCells": shape["clueCells"],
            "words": words,
            "publicationStatus": "owner-review-required",
            "manualReview": "pending-owner-review",
            "generationMetrics": {
                "seed": attempts_report[-1]["seed"],
                "solver": solved_telemetry,
                "fullCentralCorpusLoaded": len(entries),
                "fullCorpusDigest": corpus_digest(entries),
                "activeFamilyExclusions": len(active_family_exclusions),
                "batchAnswerExclusionsBeforeGrid": len(selected_answers),
                "initialCandidateDomains": [
                    {
                        "slot": index,
                        "length": len(slot.cells),
                        "fullCorpusAtLength": len(by_length[len(slot.cells)]),
                        "availableBeforeCrossings": sum(
                            answer not in grid_exclusions
                            for answer in by_length[len(slot.cells)]
                        ),
                    }
                    for index, slot in enumerate(slots)
                ],
                "rejectionsBeforeAcceptance": dict(local_rejections),
            },
        }
        topology = audit_grid_topology(grid, enforce_layout=False)
        if not topology["valid"]:
            raise ValueError(f"{grid_id}: {topology['errors']}")
        if any(word["answer"] not in sources for word in words):
            raise ValueError(f"{grid_id}: réponse absente du corpus central")
        accepted.append(grid)
        values = {word["answer"] for word in words}
        selected_answers.update(values)
        selected_families.update(answer_family(answer) for answer in values)

    used_sources = Counter(word["sourceId"] for grid in accepted for word in grid["words"])
    proof = {
        "corpusFile": "src/data/crossword.central.json.gz",
        "canonicalAnswersLoaded": len(entries),
        "canonicalDistinctAnswersLoaded": len({entry["answer"] for entry in entries}),
        "corpusDigestSha256": corpus_digest(entries),
        "corpusAnswersByLength": dict(sorted(corpus_by_length.items())),
        "corpusSources": dict(source_counts.most_common()),
        "answersIndexedWithoutHiddenSubset": sum(len(answers) for answers in by_length.values()),
        "lengthNineLoadedButUnusedBecauseNoNineLetterSlot": len(by_length[9]),
        "playableCatalogGridsUsedAsRepeatBaseline": len(playable_grids),
        "activeDistinctAnswers": len(active_answers),
        "activeFamilyExclusionsInsideCorpus": len(active_family_exclusions),
        "selectedAnswers": sum(len(grid["words"]) for grid in accepted),
        "selectedDistinctAnswers": len(selected_answers),
        "selectedSources": dict(used_sources),
        "allSelectedAnswersAreCentralMembers": all(
            word["answer"] in sources for grid in accepted for word in grid["words"]
        ),
        "activeAnswerRepeats": sorted(
            selected_answers & active_answers
        ),
    }
    document = {
        "version": 1,
        "kind": "full-central-corpus-long-grid-raw-review",
        "publicationPolicy": "Raw fill; editorial review and owner approval required.",
        "proof": proof,
        "attempts": attempts_report,
        "grids": accepted,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "built",
        "output": str(OUTPUT),
        "proof": proof,
        "grids": [
            {
                "id": grid["id"],
                "shape": grid["sourceShapeId"],
                "answers": [word["answer"] for word in grid["words"]],
            }
            for grid in accepted
        ],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
