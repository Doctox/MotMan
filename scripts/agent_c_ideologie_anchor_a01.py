"""Test one exact IDEOLOGIE placement in immutable reference-ribbon-a-01.

This is a staging diagnostic.  It intentionally excludes the Morphalou
inflection reservoir: every candidate comes from the current central corpus or
the frequency-filtered Lexique expansion.  The fixed shape is never edited.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagnose_fixed_shape_corpus_gaps import (  # noqa: E402
    DEFAULT_SHAPES,
    load_expansion_words,
    load_shape,
    load_words,
)
from fill_fixed_ribbon_a01 import (  # noqa: E402
    FixedRibbonArcSolver,
    load_owner_accepts,
    validate_fixed_layout,
)
from bitset_grid_filler import fill_bitset  # noqa: E402


ANCHOR = "IDEOLOGIE"
LONG_SLOTS = (0, 1, 2, 5, 6)
CENTRAL_RAW = ROOT / "src/data/crossword.central.json.gz"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"


def restore_rotation_cooldowns(words_by_length, metadata):
    """Cooldown means rotate, never lexical rejection.

    The generic expansion loader excludes cooldown answers because generators
    should avoid repetition.  For a single manually edited grid they remain
    valid structural candidates and must be reintroduced explicitly.
    """
    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    cooldowns = {
        item["answer"] for item in blacklist.get("rotationCooldownAnswers", [])
    }
    rejected = set(blacklist.get("rejectedAnswers", []))
    with gzip.open(CENTRAL_RAW, "rt", encoding="utf-8") as handle:
        central_document = json.load(handle)
    restored_entries = {}
    for entry in central_document["entries"]:
        answer = entry.get("answer", "")
        if (
            answer not in cooldowns
            or answer in rejected
            or len(answer) not in {3, 4, 5, 8, 9}
        ):
            continue
        previous = restored_entries.get(answer)
        if previous is None or (
            bool(entry.get("clue")) and not bool(previous.get("clue"))
        ):
            restored_entries[answer] = entry
    mutable = {length: list(answers) for length, answers in words_by_length.items()}
    for answer, entry in restored_entries.items():
        if answer not in mutable.setdefault(len(answer), []):
            mutable[len(answer)].append(answer)
        metadata[answer] = {
            "answer": answer,
            "length": len(answer),
            "partOfSpeech": "CENTRAL-ROTATION-COOLDOWN",
            "sourceFrequency": float(entry.get("frequency", 0) or 0),
            "schoolFrequency": 0,
            "difficulty": entry.get("difficulty", "normal"),
        }
    return (
        {length: tuple(sorted(answers)) for length, answers in mutable.items()},
        restored_entries,
    )


def structurally_devinable(answer, entry, canonical, restored_cooldowns):
    if answer in canonical or answer in restored_cooldowns or answer == ANCHOR:
        return True
    if entry.get("formType") != "inflected":
        return True
    if entry.get("partOfSpeech") != "verb":
        return True
    inflection = entry.get("inflection") or {}
    return (
        inflection.get("mode") == "indicative"
        and inflection.get("person") == "thirdPerson"
        and inflection.get("tense") != "simplePast"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", type=int, required=True, choices=LONG_SLOTS)
    parser.add_argument("--seconds", type=float, default=28.0)
    parser.add_argument("--seed", type=int, default=717300)
    parser.add_argument("--include-morphalou", action="store_true")
    parser.add_argument("--solver", choices=("arc", "bitset"), default="arc")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    shape, slots = load_shape(DEFAULT_SHAPES, "reference-ribbon-a-01")
    validate_fixed_layout(slots)
    _central_words, canonical = load_words()
    words_by_length, metadata, corpus_stats = load_expansion_words(
        canonical,
        permissive=False,
        include_morphalou=args.include_morphalou,
    )
    words_by_length, restored_cooldowns = restore_rotation_cooldowns(
        words_by_length, metadata
    )
    corpus_stats["restoredRotationCooldownAnswers"] = sorted(restored_cooldowns)
    corpus_stats["rotationCooldownPolicy"] = (
        "structurally valid; restored for this single-grid editorial repair"
    )
    if args.include_morphalou:
        filtered = {}
        rejected_inflections = 0
        for length, answers in words_by_length.items():
            kept = []
            for answer in answers:
                if structurally_devinable(
                    answer, metadata[answer], canonical, restored_cooldowns
                ):
                    kept.append(answer)
                else:
                    rejected_inflections += 1
            filtered[length] = tuple(kept)
        words_by_length = filtered
        corpus_stats["rejectedArtificialInflections"] = rejected_inflections
    owner_accepts = load_owner_accepts()
    if args.solver == "arc":
        solver = FixedRibbonArcSolver(
            slots=slots,
            words_by_length=words_by_length,
            metadata=metadata,
            canonical=canonical,
            owner_accepts=owner_accepts,
            seed=args.seed + args.slot,
            seconds=args.seconds,
            strategy="information",
            preferred_answers={args.slot: ANCHOR},
        )
        solved, telemetry = solver.solve(fixed_answers={args.slot: ANCHOR})
    else:
        frequency = {
            answer: float(metadata[answer].get("sourceFrequency", 0) or 0)
            for answers in words_by_length.values() for answer in answers
        }
        concepts = {
            answer: answer for answers in words_by_length.values() for answer in answers
        }
        indexes = (
            words_by_length,
            None,
            frequency,
            concepts,
            {answer: set() for answer in concepts},
            {answer: "normal" for answer in concepts},
            set(),
        )
        answer_usage = {
            answer: int(
                answer not in canonical
                and answer not in owner_accepts
                and answer not in restored_cooldowns
            )
            for answer in concepts
        }
        telemetry = {}
        bitset_solution = fill_bitset(
            slots,
            indexes,
            __import__("random").Random(args.seed + args.slot),
            None,
            unavailable_answers=set(),
            answer_usage=answer_usage,
            max_grammar_answers=99,
            grammar_answers=set(),
            max_seconds=args.seconds,
            node_limit=30_000_000,
            require_image=False,
            fixed_answers={args.slot: ANCHOR},
            prefer_constraint_support=True,
            constraint_support_bucket_size=2,
            telemetry=telemetry,
        )
        solved = (
            {index: answer for index, answer in enumerate(bitset_solution)}
            if bitset_solution is not None else None
        )
        telemetry.setdefault(
            "reason", "solved" if solved is not None else "bounded-no-closure"
        )
        telemetry.setdefault("elapsedSeconds", args.seconds)
        telemetry.setdefault("bestFilledSlots", 22 if solved is not None else 0)

    row_patterns = []
    anchor_slot = slots[args.slot]
    anchor_letters = dict(zip(anchor_slot.cells, ANCHOR))
    for index in range(8, 22):
        slot = slots[index]
        pattern = "".join(anchor_letters.get(cell, ".") for cell in slot.cells)
        if pattern != "." * slot.length:
            matching = [
                answer for answer in words_by_length[slot.length]
                if all(expected == "." or answer[position] == expected
                       for position, expected in enumerate(pattern))
            ]
            row_patterns.append({
                "slotIndex": index,
                "length": slot.length,
                "pattern": pattern,
                "candidateCount": len(matching),
                "canonicalCandidates": [
                    answer for answer in matching if answer in canonical
                ][:80],
            })

    solution = None
    if solved is not None:
        records = []
        for index, answer in sorted(solved.items()):
            source = canonical.get(answer)
            records.append({
                "slotIndex": index,
                "answer": answer,
                "length": slots[index].length,
                "direction": slots[index].direction,
                "canonical": answer in canonical,
                "ownerAccepted": answer in owner_accepts,
                "clue": source.get("clue", "") if source else "",
                "sourceFrequency": metadata[answer].get("sourceFrequency", 0),
            })
        solution = {
            "answers": records,
            "canonicalCount": sum(item["canonical"] for item in records),
            "ownerAcceptedCount": sum(item["ownerAccepted"] for item in records),
            "unreviewedAnswers": [
                item["answer"] for item in records
                if not item["canonical"] and not item["ownerAccepted"]
            ],
        }

    payload = {
        "version": 1,
        "kind": "agent-c-ideologie-fixed-placement",
        "shapeId": shape["id"],
        "shapeModified": False,
        "anchor": ANCHOR,
        "anchorSlotIndex": args.slot,
        "anchorSlotId": slots[args.slot].slot_id,
        "complete": solution is not None,
        "corpusPolicy": (
            "central-plus-frequency-filtered-lexique-plus-morphalou"
            if args.include_morphalou else
            "central-plus-frequency-filtered-lexique-no-morphalou"
        ),
        "corpusStats": corpus_stats,
        "rowPatterns": row_patterns,
        "solverTelemetry": telemetry,
        "solution": solution,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "slot": args.slot,
        "complete": payload["complete"],
        "reason": telemetry["reason"],
        "elapsedSeconds": telemetry["elapsedSeconds"],
        "bestFilledSlots": telemetry["bestFilledSlots"],
        "canonicalCount": solution["canonicalCount"] if solution else None,
        "unreviewed": solution["unreviewedAnswers"] if solution else None,
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
