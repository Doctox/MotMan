"""Test IDEOLOGIE as the sole lexical anchor in A01 slots 5 and 6."""
from __future__ import annotations

import json
import random
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bitset_grid_filler import fill_bitset  # noqa: E402
from diagnose_fixed_shape_corpus_gaps import (  # noqa: E402
    DEFAULT_SHAPES, load_expansion_words, load_shape, load_words,
)
from grid_topology import audit_grid_topology  # noqa: E402
from agent_b_editorial_neighborhood_a01 import (  # noqa: E402
    BANNED as OLD_NO_GOODS, structural_is_devinable,
)

OUTPUT = ROOT / "output/quality/agent-b-ideologie-a01.json"
SHAPE_ID = "reference-ribbon-a-01"
ANSWER = "IDEOLOGIE"
POSITIONS = (5, 6)
NEW_NO_GOODS = {
    "ECORAIENT", "SOUSORDRE", "RELOUATES", "TRAILLEES", "ARS",
    "SERER", "DINA", "GEDRITES", "ENRENEES", "STERASSE",
}
NO_GOODS = set(OLD_NO_GOODS) | NEW_NO_GOODS


def main() -> None:
    started = time.monotonic()
    shape, slots = load_shape(DEFAULT_SHAPES, SHAPE_ID)
    _central_words, canonical = load_words()
    expanded, metadata, expansion_stats = load_expansion_words(
        canonical, include_morphalou=True
    )
    by_length = defaultdict(list)
    rejected = defaultdict(int)
    for length in {3, 4, 5, 8, 9}:
        for answer in expanded[length]:
            if answer in NO_GOODS:
                rejected["owner-and-editorial-no-good"] += 1
                continue
            if not structural_is_devinable(answer, metadata[answer], canonical):
                rejected["non-devinable-inflection"] += 1
                continue
            by_length[length].append(answer)
        by_length[length].sort()
    if ANSWER not in by_length[9]:
        raise ValueError("IDEOLOGIE absente du pool structurel filtré")

    all_answers = {answer for answers in by_length.values() for answer in answers}
    frequency = {
        answer: float(metadata[answer].get("sourceFrequency", 0) or 0)
        for answer in all_answers
    }
    concepts = {answer: answer for answer in all_answers}
    indexes = (
        dict(by_length), None, frequency, concepts,
        {answer: set() for answer in all_answers},
        {answer: "normal" for answer in all_answers},
        {answer for answer in all_answers if canonical.get(answer, {}).get("image")},
    )
    answer_usage = {
        answer: 0 if answer in canonical or answer == ANSWER else 1
        for answer in all_answers
    }

    attempts = []
    solutions = []
    for slot_index in POSITIONS:
        telemetry = {}
        attempt_started = time.monotonic()
        solution = fill_bitset(
            slots, indexes, random.Random(812100 + slot_index), None,
            unavailable_answers=NO_GOODS,
            answer_usage=answer_usage,
            max_grammar_answers=99,
            grammar_answers=set(),
            max_seconds=55.0,
            node_limit=30_000_000,
            require_image=False,
            fixed_answers={slot_index: ANSWER},
            prefer_constraint_support=True,
            constraint_support_bucket_size=2,
            telemetry=telemetry,
        )
        record = {
            "slotIndex": slot_index,
            "slotId": shape["slots"][slot_index]["slotId"],
            "direction": shape["slots"][slot_index]["direction"],
            "clueCell": shape["slots"][slot_index]["clueCell"],
            "cells": shape["slots"][slot_index]["cells"],
            "elapsedSeconds": round(time.monotonic() - attempt_started, 3),
            "solverTelemetry": telemetry,
            "complete": solution is not None,
        }
        if solution is not None:
            words = []
            for index, slot in enumerate(shape["slots"]):
                answer = solution[index]
                source = canonical.get(answer, {})
                words.append({
                    "wordId": f"agent-b-ideologie-slot-{slot_index}:word:{index + 1:02d}",
                    "slotIndex": index,
                    "slotId": slot["slotId"],
                    "answer": answer,
                    "clue": source.get("clue", ""),
                    "direction": slot["direction"],
                    "arrow": slot["arrow"],
                    "clueCell": slot["clueCell"],
                    "cells": slot["cells"],
                    "editorialTier": (
                        "owner-certain-structural" if answer == ANSWER
                        else "canonical" if answer in canonical
                        else "structural-review-required"
                    ),
                })
            grid = {
                "id": f"agent-b-ideologie-a01-slot-{slot_index}",
                "columns": shape["columns"], "rows": shape["rows"],
                "sourceShapeId": SHAPE_ID, "clueCells": shape["clueCells"],
                "words": words, "publicationStatus": "owner-review-required",
            }
            audit = audit_grid_topology(
                grid, require_word_ids=True, enforce_layout=False
            )
            record.update({
                "grid": grid,
                "strictAudit": audit,
                "canonicalAnswerCount": sum(w["editorialTier"] == "canonical" for w in words),
                "structuralReviewRequired": [
                    w["answer"] for w in words
                    if w["editorialTier"] == "structural-review-required"
                ],
            })
            solutions.append(record)
        attempts.append(record)

    payload = {
        "version": 1,
        "kind": "agent-b-a01-ideologie-position-test",
        "generatedOn": str(date.today()),
        "shapeId": SHAPE_ID,
        "shapeModified": False,
        "catalogModified": False,
        "interfaceModified": False,
        "soleLexicalAnchor": ANSWER,
        "additionalFixedAnswers": 0,
        "status": "complete-position-found" if solutions else "bounded-no-closure",
        "corpusMetrics": {
            **expansion_stats,
            "usableByLength": {str(k): len(v) for k, v in sorted(by_length.items())},
            "rejectedByEditorialRule": dict(rejected),
            "noGoods": sorted(NO_GOODS),
        },
        "attempts": attempts,
        "totalElapsedSeconds": round(time.monotonic() - started, 3),
        "publicationEligible": False,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "attempts": [
            {"slotIndex": item["slotIndex"], "complete": item["complete"],
             "telemetry": item["solverTelemetry"]}
            for item in attempts
        ],
        "output": str(OUTPUT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
