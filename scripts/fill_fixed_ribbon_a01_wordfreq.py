#!/usr/bin/env python3
"""Search the immutable A01 shape with a human-frequency candidate pool.

This is a lexical closure pass only.  ``wordfreq`` is used to rank and filter
forms already present in the licensed local Lexique/Morphalou/central pools;
it is never used as a clue source.  A result remains unpublishable until all
22 answer/clue pairs pass the normal editorial audit.
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
from pathlib import Path

from wordfreq import zipf_frequency


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
    FixedRibbonMinConflictsSolver,
    load_owner_accepts,
    validate_fixed_layout,
)


DEFAULT_OUTPUT = ROOT / "output/quality/reference-ribbon-a01-wordfreq.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimum-zipf", type=float, default=2.0)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--seed", type=int, default=717301)
    parser.add_argument("--solver", choices=("arc", "local"), default="arc")
    parser.add_argument("--anchor-slot", type=int)
    parser.add_argument("--anchor-answer")
    parser.add_argument("--include-cooldown", action="store_true")
    parser.add_argument("--include-common-inflections", action="store_true")
    parser.add_argument("--include-central-noncanonical", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _shape, slots = load_shape(DEFAULT_SHAPES, "reference-ribbon-a-01")
    validate_fixed_layout(slots)
    _central_by_length, canonical = load_words()
    expanded, metadata, source_stats = load_expansion_words(
        canonical,
        permissive=False,
        include_morphalou=True,
    )
    cooldown_answers: set[str] = set()
    central_noncanonical: set[str] = set()
    if args.include_cooldown or args.include_central_noncanonical:
        blacklist = json.loads(
            (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
        )
        rejected = set(blacklist.get("rejectedAnswers", []))
        cooldown_answers = {
            item["answer"]
            for item in blacklist.get("rotationCooldownAnswers", [])
            if item.get("answer") not in rejected
        }
        with gzip.open(
            ROOT / "src/data/crossword.central.json.gz", "rt", encoding="utf-8"
        ) as handle:
            central_document = json.load(handle)
        for entry in central_document.get("entries", []):
            answer = entry.get("answer", "")
            if len(answer) not in (3, 4, 5, 8, 9) or answer in rejected:
                continue
            if answer in cooldown_answers:
                metadata.setdefault(answer, entry)
            if args.include_central_noncanonical and not entry.get("canonicalForGenerator"):
                central_noncanonical.add(answer)
                metadata.setdefault(answer, entry)

    scores: dict[str, float] = {}
    words_by_length: dict[int, tuple[str, ...]] = {}
    for length in (3, 4, 5, 8, 9):
        kept = []
        for answer in expanded.get(length, ()):
            score = zipf_frequency(answer.lower(), "fr")
            scores[answer] = score
            inflection_allowed = False
            if (
                args.include_common_inflections
                and metadata[answer].get("formType") == "inflected"
            ):
                entry = metadata[answer]
                details = entry.get("inflection") or {}
                lemma_score = zipf_frequency(
                    str(entry.get("lemma", entry.get("lemmaAnswer", ""))).lower(),
                    "fr",
                )
                if entry.get("partOfSpeech") in {"common-noun", "adjective"}:
                    inflection_allowed = lemma_score >= 1.5
                elif entry.get("partOfSpeech") == "verb":
                    inflection_allowed = (
                        lemma_score >= 2.5
                        and details.get("mode") == "indicative"
                        and details.get("tense") in {"present", "future", "imperfect"}
                        and details.get("person") == "thirdPerson"
                    )
            if answer in canonical or score >= args.minimum_zipf or inflection_allowed:
                kept.append(answer)
        if args.include_cooldown:
            kept.extend(
                answer for answer in cooldown_answers
                if len(answer) == length and answer in metadata and answer not in kept
            )
        if args.include_central_noncanonical:
            kept.extend(
                answer for answer in central_noncanonical
                if len(answer) == length and answer in metadata and answer not in kept
            )
        words_by_length[length] = tuple(sorted(kept))

    owner_accepts = load_owner_accepts()
    common_args = {
        "slots": slots,
        "words_by_length": words_by_length,
        "metadata": metadata,
        "canonical": canonical,
        "owner_accepts": owner_accepts,
        "seed": args.seed,
        "seconds": args.seconds,
    }
    if args.solver == "local":
        solver = FixedRibbonMinConflictsSolver(**common_args, breakout=True)
    else:
        solver = FixedRibbonArcSolver(**common_args, strategy="information")
    rng = random.Random(args.seed)
    for answer in getattr(solver, "priority", {}):
        # Whole reviewed pairs lead, then ordinary high-frequency forms.
        reviewed_rank = (
            0 if answer in canonical or answer in cooldown_answers
            else (1 if answer in owner_accepts else 2)
        )
        solver.priority[answer] = (
            reviewed_rank * 100.0
            - scores.get(answer, 0.0) * 5.0
            + rng.random()
        )

    if args.solver == "local":
        for length, candidates in words_by_length.items():
            for index, answer in enumerate(candidates):
                # Keep lexical popularity as a tie-break only; crossing count
                # remains the hard optimization target.
                solver.quality[length][index] = (
                    (0.3 if answer in canonical or answer in cooldown_answers else 0.0)
                    + scores.get(answer, 0.0) / 10.0
                )
    initial_answers = None
    if args.anchor_slot is not None or args.anchor_answer:
        if args.anchor_slot is None or not args.anchor_answer:
            raise ValueError("--anchor-slot et --anchor-answer vont ensemble")
        answer = args.anchor_answer.upper()
        slot = slots[args.anchor_slot]
        if len(answer) != slot.length or answer not in words_by_length[slot.length]:
            raise ValueError(f"ancre absente ou longueur invalide: {answer}")
        initial_answers = {args.anchor_slot: answer}
    if args.solver == "local":
        solution, telemetry = solver.solve(initial_answers=initial_answers)
    else:
        solution, telemetry = solver.solve(fixed_answers=initial_answers)
    document = {
        "version": 1,
        "kind": "immutable-a01-human-frequency-closure",
        "shapeId": "reference-ribbon-a-01",
        "shapeModified": False,
        "complete": solution is not None,
        "publicationEligible": False,
        "minimumZipf": args.minimum_zipf,
        "solver": args.solver,
        "anchor": (
            {"slotIndex": args.anchor_slot, "answer": args.anchor_answer.upper()}
            if args.anchor_slot is not None else None
        ),
        "candidateCounts": {
            str(length): len(words) for length, words in words_by_length.items()
        },
        "cooldownAnswersRestored": sorted(cooldown_answers),
        "centralNoncanonicalRestored": len(central_noncanonical),
        "sourcePool": source_stats,
        "solverTelemetry": telemetry,
        "solution": [
            {
                "slotIndex": index,
                "slotId": slots[index].slot_id,
                "answer": solution[index],
                "zipf": scores.get(solution[index], 0.0),
                "hasReviewedPair": solution[index] in canonical or solution[index] in owner_accepts,
            }
            for index in sorted(solution or {})
        ] if solution else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "complete": document["complete"],
        "minimumZipf": args.minimum_zipf,
        "candidateCounts": document["candidateCounts"],
        "telemetry": telemetry,
        "output": str(args.output),
    }, ensure_ascii=False, indent=2), flush=True)
    return 0 if solution else 2


if __name__ == "__main__":
    raise SystemExit(main())
