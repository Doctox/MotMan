"""Bounded exact editorial neighbourhood search around Agent C's A01 closure."""
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

OUTPUT = ROOT / "output/quality/agent-b-ribbon-a01-fill.json"
SHAPE_ID = "reference-ribbon-a-01"
REQUIRED_LENGTHS = {3, 4, 5, 8, 9}
BANNED = {
    "ARNIS", "MANTELAS", "RASSORTS", "AMARINERA", "ARRISAIS", "SASSASSE",
    "RAMAGERAS", "RELACERAS", "TRACERAIS", "GITA", "REUNIRAS",
}
# Final owner-requested run: topology only, no lexical anchor is fixed.
FIXED = {}


def structural_is_devinable(answer: str, entry: dict, canonical: dict) -> bool:
    if answer in canonical:
        return True
    if answer in BANNED:
        return False
    if entry.get("formType") != "inflected" or entry.get("partOfSpeech") != "verb":
        return True
    inflection = entry.get("inflection") or {}
    # These forms produced the least human-readable answers in the known
    # closure. Third-person indicative forms remain candidates for review.
    if inflection.get("mode") != "indicative":
        return False
    if inflection.get("person") in {"firstPerson", "secondPerson"}:
        return False
    return inflection.get("tense") != "simplePast"


def main() -> None:
    process_started = time.monotonic()
    shape, slots = load_shape(DEFAULT_SHAPES, SHAPE_ID)
    _central_words, canonical = load_words()
    expanded, metadata, expansion_stats = load_expansion_words(
        canonical, include_morphalou=True
    )

    by_length = defaultdict(list)
    rejected = defaultdict(int)
    for length in REQUIRED_LENGTHS:
        for answer in expanded[length]:
            if answer in BANNED:
                rejected["explicit-or-detected-no-good"] += 1
                continue
            if not structural_is_devinable(answer, metadata[answer], canonical):
                rejected["non-devinable-inflection"] += 1
                continue
            by_length[length].append(answer)
        by_length[length].sort()

    frequency = {
        answer: float(metadata[answer].get("sourceFrequency", 0) or 0)
        for answers in by_length.values() for answer in answers
    }
    concepts = {answer: answer for answers in by_length.values() for answer in answers}
    conflicts = {answer: set() for answer in concepts}
    difficulty = {answer: "normal" for answer in concepts}
    images = {
        answer for answer in concepts
        if canonical.get(answer, {}).get("image")
    }
    indexes = (dict(by_length), None, frequency, concepts, conflicts, difficulty, images)
    # This first tuple component dominates the value ordering in fill_bitset.
    # Canonical/source-backed answers are therefore always tried before
    # structural-only forms at equal topology support.
    answer_usage = {answer: int(answer not in canonical) for answer in concepts}

    load_seconds = time.monotonic() - process_started
    search_budget = max(2.0, min(42.0, 58.0 - load_seconds))
    telemetry = {}
    solution = fill_bitset(
        slots,
        indexes,
        random.Random(717222),
        None,
        unavailable_answers=BANNED,
        answer_usage=answer_usage,
        max_grammar_answers=99,
        grammar_answers=set(),
        max_seconds=search_budget,
        node_limit=20_000_000,
        require_image=False,
        fixed_answers=FIXED,
        prefer_constraint_support=True,
        constraint_support_bucket_size=2,
        telemetry=telemetry,
    )
    elapsed = time.monotonic() - process_started
    payload = {
        "version": 3,
        "kind": "agent-b-a01-exact-editorial-neighbourhood",
        "generatedOn": str(date.today()),
        "shapeId": SHAPE_ID,
        "status": "complete-editorial-review-required" if solution else "bounded-no-alternative",
        "catalogModified": False,
        "interfaceModified": False,
        "shapeModified": False,
        "method": {
            "engine": "exact-bitset-CSP-with-no-goods",
            "elapsedSeconds": round(elapsed, 3),
            "loadSeconds": round(load_seconds, 3),
            "searchBudgetSeconds": round(search_budget, 3),
            "fixedCanonicalAnchors": FIXED,
            "bannedAnswers": sorted(BANNED),
            "canonicalFirstValueOrdering": True,
            "forcedLetters": 0,
            "solverTelemetry": telemetry,
        },
        "corpusMetrics": {
            **expansion_stats,
            "usableByLength": {str(k): len(v) for k, v in sorted(by_length.items())},
            "canonicalAnswers": len(canonical),
            "rejectedByNeighbourhoodRule": dict(rejected),
        },
        "solution": None,
        "publicationEligible": False,
    }
    if solution:
        words = []
        for index, slot in enumerate(shape["slots"]):
            answer = solution[index]
            source = canonical.get(answer, {})
            words.append({
                "wordId": f"agent-b-a01-editorial:word:{index + 1:02d}",
                "slotIndex": index,
                "slotId": slot["slotId"],
                "answer": answer,
                "clue": source.get("clue", ""),
                "direction": slot["direction"],
                "arrow": slot["arrow"],
                "clueCell": slot["clueCell"],
                "cells": slot["cells"],
                "editorialTier": "canonical" if answer in canonical else "structural-review-required",
                "sourceId": source.get("sourceId") or metadata[answer].get("sourceId"),
            })
        grid = {
            "id": "agent-b-a01-editorial-neighbourhood",
            "columns": shape["columns"], "rows": shape["rows"],
            "sourceShapeId": SHAPE_ID, "clueCells": shape["clueCells"],
            "words": words, "publicationStatus": "owner-review-required",
        }
        audit = audit_grid_topology(grid, require_word_ids=True, enforce_layout=False)
        missing = [word["answer"] for word in words if word["editorialTier"] != "canonical"]
        payload.update({
            "solution": grid,
            "strictAudit": audit,
            "answerCount": len(words),
            "distinctAnswerCount": len({word["answer"] for word in words}),
            "canonicalAnswerCount": len(words) - len(missing),
            "structuralReviewRequired": missing,
            "publicationEligible": audit["valid"] and not missing,
        })
        if not audit["valid"] or len({word["answer"] for word in words}) != 22:
            payload["status"] = "rejected-strict-audit"
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"], "elapsedSeconds": round(elapsed, 3),
        "telemetry": telemetry, "output": str(OUTPUT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
