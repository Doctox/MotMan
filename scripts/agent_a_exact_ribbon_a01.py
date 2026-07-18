"""Agent A: exact fixed-mask search for reference-ribbon-a-01.

This is a staging-only diagnostic.  The 22 paths are read verbatim from the
approved shape.  Morphalou contributes spellings, never definitions: an
answer found only there is explicitly emitted with ``clue: null`` and cannot
be published before a separate editorial review.
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as generator  # noqa: E402
from bitset_grid_filler import fill_bitset  # noqa: E402


SHAPES = ROOT / "output/quality/reference-style-shapes-a.json"
CENTRAL = ROOT / "src/data/crossword.central.json.gz"
MORPHALOU = ROOT / "src/data/crossword.morphalou.staging.json.gz"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
CATALOG = ROOT / "src/data/grid.catalog.json"
OUTPUT = ROOT / "output/quality/agent-a-ribbon-a01-fill.json"

SHAPE_ID = "reference-ribbon-a-01"
EXPLICITLY_UNDESIRABLE = {
    "AN", "ANS", "AME", "AMES", "ARE", "ERE", "ILE", "ILES", "MER",
    "FER", "SEL", "MUR", "CLE", "ANE", "NON", "OUI", "OS", "NOTE",
    "UT", "RE", "DO", "MI", "LA", "SI", "FA", "BEL", "ATT", "SS",
    "SPEED",
}
REVIEWED_STATUSES = {
    "human-reviewed", "owner-approved", "image-reviewed", "source-backed",
}


def pair_rank(entry: dict) -> tuple:
    return (
        0 if entry.get("canonicalForGenerator") else 1,
        0 if entry.get("editorialStatus") in REVIEWED_STATUSES else 1,
        len((entry.get("clue") or "").strip()),
        (entry.get("clue") or "").casefold(),
    )


def load_shape() -> dict:
    document = json.loads(SHAPES.read_text(encoding="utf-8"))
    return next(shape for shape in document["shapes"] if shape["id"] == SHAPE_ID)


def load_blocked() -> set[str]:
    document = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    blocked = set(EXPLICITLY_UNDESIRABLE)
    for key in ("rejectedAnswers", "rejectedEasyAnswers", "rejectedNormalAnswers"):
        blocked.update(item for item in document.get(key, []) if isinstance(item, str))
    blocked.update(
        item["answer"] for item in document.get("rotationCooldownAnswers", [])
        if isinstance(item, dict) and item.get("answer")
    )
    return blocked


def load_domains(blocked: set[str], include_inflections: bool):
    with gzip.open(CENTRAL, "rt", encoding="utf-8") as handle:
        central_document = json.load(handle)
    central_pairs: dict[str, dict] = {}
    for entry in central_document["entries"]:
        answer = str(entry.get("answer", "")).upper()
        clue = str(entry.get("clue") or "").strip()
        if not (
            3 <= len(answer) <= 9 and answer.isascii() and answer.isalpha()
            and answer not in blocked and clue
            and (
                entry.get("canonicalForGenerator") is True
                or entry.get("editorialStatus") in REVIEWED_STATUSES
            )
        ):
            continue
        if answer not in central_pairs or pair_rank(entry) < pair_rank(central_pairs[answer]):
            central_pairs[answer] = entry

    with gzip.open(MORPHALOU, "rt", encoding="utf-8") as handle:
        morphalou_document = json.load(handle)
    morphalou_entries: dict[str, dict] = {}
    for entry in morphalou_document["entries"]:
        answer = str(entry.get("answer", "")).upper()
        if not (
            3 <= len(answer) <= 9 and answer.isascii() and answer.isalpha()
            and answer not in blocked
            and (include_inflections or entry.get("formType") == "lemma")
        ):
            continue
        previous = morphalou_entries.get(answer)
        if previous is None or (
            previous.get("formType") != "lemma" and entry.get("formType") == "lemma"
        ):
            morphalou_entries[answer] = entry

    answers = set(central_pairs) | set(morphalou_entries)
    by_length = defaultdict(list)
    frequency = {}
    concept_group = {}
    semantic_conflicts = {}
    difficulty = {}
    for answer in sorted(answers):
        entry = central_pairs.get(answer)
        by_length[len(answer)].append(answer)
        frequency[answer] = float((entry or {}).get("frequency", 0) or 0)
        concept_group[answer] = answer
        semantic_conflicts[answer] = set()
        declared = (entry or {}).get("difficulty", "normal")
        difficulty[answer] = declared if declared in {"easy", "normal", "hard"} else "normal"

    assets = {
        path.stem.upper()
        for path in (ROOT / "public/assets/clues/twemoji").glob("*.svg")
    }
    indexes = (
        by_length,
        {},
        frequency,
        concept_group,
        semantic_conflicts,
        difficulty,
        answers & assets,
    )
    return indexes, central_pairs, morphalou_entries, morphalou_document["source"]


def active_usage() -> Counter:
    document = json.loads(CATALOG.read_text(encoding="utf-8"))
    return Counter(
        word["answer"]
        for grid in document["grids"]
        for word in grid["words"]
    )


def mechanical_audit(shape: dict, answers: dict[int, str]) -> dict:
    letters = {}
    coverage = defaultdict(list)
    errors = []
    for index, slot in enumerate(shape["slots"]):
        answer = answers[index]
        if len(answer) != len(slot["cells"]):
            errors.append({"code": "length", "slotId": slot["slotId"]})
            continue
        for letter, raw_cell in zip(answer, slot["cells"]):
            cell = tuple(raw_cell)
            previous = letters.get(cell)
            if previous is not None and previous != letter:
                errors.append({
                    "code": "crossing", "cell": list(cell),
                    "letters": [previous, letter], "slotId": slot["slotId"],
                })
            letters[cell] = letter
            coverage[cell].append(slot["slotId"])
    expected = {
        (row, col) for row in range(shape["rows"])
        for col in range(shape["columns"])
        if [row, col] not in shape["clueCells"]
    }
    uncovered = sorted(expected - set(coverage))
    extra = sorted(set(coverage) - expected)
    return {
        "valid": not errors and not uncovered and not extra,
        "declaredSlots": len(shape["slots"]),
        "letterCells": len(expected),
        "coveredLetterCells": len(expected & set(coverage)),
        "crossingErrors": errors,
        "uncoveredLetterCells": [list(cell) for cell in uncovered],
        "extraLetterCells": [list(cell) for cell in extra],
        "cellCoverage": [
            {"cell": list(cell), "letter": letters.get(cell), "slotIds": coverage.get(cell, [])}
            for cell in sorted(expected)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=12.0)
    parser.add_argument("--seeds", type=int, default=2)
    parser.add_argument("--min-structural", type=int, default=0)
    parser.add_argument("--max-structural", type=int, default=12)
    parser.add_argument("--include-inflections", action="store_true")
    args = parser.parse_args()

    shape = load_shape()
    blocked = load_blocked()
    indexes, central_pairs, morphalou_entries, morphalou_source = load_domains(
        blocked, args.include_inflections
    )
    usage = active_usage()
    structural_only = set(morphalou_entries) - set(central_pairs)
    slots = [
        generator.Slot(
            slot["direction"], tuple(slot["clueCell"]),
            tuple(map(tuple, slot["cells"])), slot["arrow"],
        )
        for slot in shape["slots"]
    ]

    attempts = []
    solution = None
    # This staged cap makes the search exact for each editorial budget.  The
    # first closure therefore uses the fewest structural-only answers among
    # all fully exhausted lower caps.
    caps = list(range(args.min_structural, args.max_structural + 1))
    for cap in caps:
        cap_exhausted = True
        for seed_offset in range(args.seeds):
            seed = 810_100 + cap * 101 + seed_offset
            telemetry = {}
            found = fill_bitset(
                slots,
                indexes,
                random.Random(seed),
                None,
                unavailable_answers=blocked,
                answer_usage=usage,
                max_grammar_answers=len(slots),
                grammar_answers=set(),
                max_seconds=args.seconds,
                node_limit=5_000_000,
                require_image=False,
                undesirable_answers=structural_only,
                max_undesirable_answers=cap,
                prefer_constraint_support=True,
                constraint_support_bucket_size=1,
                telemetry=telemetry,
            )
            attempts.append({"structuralCap": cap, "seed": seed, **telemetry})
            if telemetry.get("reason") == "timeout":
                cap_exhausted = False
            if found:
                solution = found
                break
        if solution:
            break
        # Multiple timeouts do not prove this cap impossible.  Continue to a
        # wider cap for a useful closure, but preserve the honest telemetry.
        if not cap_exhausted:
            continue

    if solution is None:
        result = {
            "version": 1,
            "kind": "agent-a-fixed-ribbon-a01-fill",
            "status": "blocked-no-complete-closure",
            "shapeId": SHAPE_ID,
            "geometryModified": False,
            "search": {
                "strategy": "exact bitset AC-3, staged structural-only cap, deterministic multi-seed",
                "includeMorphalouInflections": args.include_inflections,
                "attempts": attempts,
                "proof": "infeasible" if attempts and all(
                    item.get("reason") == "infeasible" for item in attempts
                ) else "bounded-search-not-exhausted",
            },
            "catalogModified": False,
            "blacklistModified": False,
            "grids": [],
        }
        OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 2

    mechanical = mechanical_audit(shape, solution)
    words = []
    structural_count = 0
    image_count = 0
    assets = {
        path.stem.upper(): f"/assets/clues/twemoji/{path.name}"
        for path in (ROOT / "public/assets/clues/twemoji").glob("*.svg")
    }
    for index, slot in enumerate(shape["slots"]):
        answer = solution[index]
        pair = central_pairs.get(answer)
        morph = morphalou_entries.get(answer)
        structural = pair is None
        structural_count += int(structural)
        image_count += int(answer in assets)
        provenance = []
        if pair:
            provenance.append({
                "kind": "reviewed-pair",
                "sourceId": pair.get("sourceId"),
                "sourceUrl": pair.get("sourceUrl"),
                "editorialStatus": pair.get("editorialStatus"),
                "canonicalForGenerator": pair.get("canonicalForGenerator", False),
            })
        if morph:
            provenance.append({
                "kind": "structural-form",
                "source": morph.get("source"),
                "sourceUrl": morph.get("sourceUrl"),
                "license": morph.get("license"),
                "formType": morph.get("formType"),
                "lemma": morph.get("lemma"),
                "partOfSpeech": morph.get("partOfSpeech"),
            })
        words.append({
            "slotId": slot["slotId"],
            "answer": answer,
            "clue": pair.get("clue") if pair else None,
            "playablePairAvailable": pair is not None,
            "structuralOnly": structural,
            "image": (
                {"asset": assets[answer], "alt": answer.title()}
                if answer in assets else None
            ),
            "activeOccurrences": usage[answer],
            "direction": slot["direction"],
            "arrow": slot["arrow"],
            "clueCell": slot["clueCell"],
            "cells": slot["cells"],
            "provenance": provenance,
        })

    result = {
        "version": 1,
        "kind": "agent-a-fixed-ribbon-a01-fill",
        "status": (
            "closed-playable-pairs-available"
            if structural_count == 0 else "closed-structural-review-required"
        ),
        "shapeId": SHAPE_ID,
        "columns": shape["columns"],
        "rows": shape["rows"],
        "clueCells": shape["clueCells"],
        "geometryModified": False,
        "pathsModified": False,
        "words": words,
        "metrics": {
            "answers": len(words),
            "structuralOnlyAnswers": structural_count,
            "playablePairsAvailable": len(words) - structural_count,
            "imageAnswersPresent": image_count,
            "activeAnswerOccurrences": sum(word["activeOccurrences"] for word in words),
        },
        "mechanicalAudit": mechanical,
        "search": {
            "strategy": "exact bitset AC-3, staged structural-only cap, deterministic multi-seed",
            "includeMorphalouInflections": args.include_inflections,
            "attempts": attempts,
        },
        "morphalouPolicy": (
            "Morphalou valide seulement l'orthographe et la morphologie. "
            "Toute réponse structuralOnly reste interdite de publication sans indice court sourcé et relu."
        ),
        "morphalouSource": morphalou_source,
        "catalogModified": False,
        "blacklistModified": False,
        "published": False,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if mechanical["valid"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
