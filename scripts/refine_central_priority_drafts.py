"""Refill discovered 9x10 silhouettes after each durable editorial blacklist pass."""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from pathlib import Path

import generate_grid_catalog as generator
from cp_sat_grid_filler import fill_cp_sat
from grid_topology import audit_grid_topology
from propose_central_corpus_five import editorial_cost
from propose_standard_crossing_drafts import as_grid
from search_audience_shapes import audience_index


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output/quality/central-priority-refined-five.json"
SHAPE_SOURCES = (
    ROOT / "output/quality/central-priority-drafts-c.json",
    ROOT / "output/quality/central-priority-drafts-d.json",
    ROOT / "output/quality/central-corpus-five-drafts-b.json",
    ROOT / "output/quality/central-corpus-five-drafts.json",
)


def shape_templates(sources: tuple[Path, ...] = SHAPE_SOURCES) -> list[dict]:
    result = []
    seen = set()
    for path in sources:
        if not path.exists():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("slots") and document.get("clueCells"):
            fingerprint = tuple(sorted(map(tuple, document["clueCells"])))
            if fingerprint not in seen:
                seen.add(fingerprint)
                result.append({
                    "clueCells": document["clueCells"],
                    "slots": document["slots"],
                })
            continue
        for grid in document.get("grids", []):
            fingerprint = tuple(sorted(map(tuple, grid["clueCells"])))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            result.append({
                "clueCells": grid["clueCells"],
                "slots": [{
                    "direction": word["direction"],
                    "arrow": word["arrow"],
                    "clue": word["clueCell"],
                    "cells": word["cells"],
                } for word in grid["words"]],
            })
    return result


def answer_family(answer: str) -> str:
    """Collapse the obvious singular/plural variants rejected by the owner."""
    if len(answer) >= 4 and answer.endswith(("S", "X")):
        return answer[:-1]
    return answer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--variants", type=int, default=10)
    parser.add_argument("--seed", type=int, default=577_000)
    parser.add_argument("--fill-seconds", type=float, default=3)
    parser.add_argument("--solver", choices=("bitset", "cp-sat"), default="bitset")
    parser.add_argument(
        "--minimum-images", type=int, choices=(0, 1), default=1,
        help="Require an illustrated answer during filling, or defer image selection.",
    )
    parser.add_argument(
        "--required-short-answer", default="",
        help=(
            "Fix the sole two-letter slot to this explicitly reviewed answer. "
            "Useful for making short answers deliberate instead of accidental."
        ),
    )
    parser.add_argument("--reverse-shapes", action="store_true")
    parser.add_argument(
        "--shape-number", type=int, default=0,
        help="One-based discovered silhouette number; zero searches them all.",
    )
    parser.add_argument("--maximum-active-repeats", type=int, default=8)
    parser.add_argument("--maximum-lexique-rescues", type=int, default=10)
    parser.add_argument("--maximum-nonstandard-central", type=int, default=4)
    parser.add_argument(
        "--minimum-answer-frequency", type=float, default=3,
        help=(
            "Minimum central/Lexique frequency for ordinary words. Explicitly "
            "reviewed JDM relations, images and dictionary entries stay eligible."
        ),
    )
    parser.add_argument(
        "--exclude-answer", action="append", default=[],
        help="Answer forbidden from this batch (repeatable, case-insensitive input).",
    )
    parser.add_argument(
        "--exclude-from", action="append", default=[], type=Path,
        help="JSON grid document whose answers are forbidden from this batch.",
    )
    parser.add_argument(
        "--exclude-active-shapes", action="store_true",
        help="Skip silhouettes already present in the active runtime catalog.",
    )
    parser.add_argument(
        "--shape-source", action="append", default=[], type=Path,
        help="JSON grid document providing silhouettes (repeatable).",
    )
    parser.add_argument(
        "--minimum-answer-length", type=int, choices=(2, 3), default=2,
        help="Reject silhouettes containing shorter answer slots.",
    )
    parser.add_argument(
        "--central-only", action="store_true",
        help=(
            "Restrict placement to answers from the reviewed central corpus. "
            "This avoids spending solver time on unclued Lexique rescue forms."
        ),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    entries = generator.load_entries()
    central_answers = {entry["answer"] for entry in entries}
    sources = {entry["answer"]: entry for entry in entries}
    lexical_entries = json.loads(
        (ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8")
    )["entries"]
    lexical_by_answer = {entry["answer"]: entry for entry in lexical_entries}
    lexical_answers = set(lexical_by_answer)
    child_answers = {
        entry["answer"] for entry in json.loads(
            (ROOT / "src/data/lexique.child-forms.json").read_text(encoding="utf-8")
        )["entries"]
    }
    standard_central = {
        entry["answer"] for entry in entries
        if entry["answer"] in lexical_answers
        or entry["answer"] in child_answers
        or entry.get("sourceType") in {"image", "dictionary", "editorial-original"}
        or entry.get("image")
        or str(entry.get("sourceId", "")).startswith("jeuxdemots")
        or any(
            str(source).startswith("jeuxdemots")
            for source in entry.get("evidenceSources", [])
        )
    }
    indexes = audience_index(
        "normal", 0, "placement", canonical_forms_only=True
    )
    strong_central = {
        entry["answer"] for entry in entries
        if entry.get("sourceType") in {"image", "dictionary", "editorial-original"}
        or entry.get("image")
        or str(entry.get("sourceId", "")).startswith("jeuxdemots")
        or any(
            str(source).startswith("jeuxdemots")
            for source in entry.get("evidenceSources", [])
        )
    }
    central_frequency = {
        entry["answer"]: float(entry.get("frequency", 0)) for entry in entries
    }
    human_allowed = {
        answer for answers in indexes[0].values() for answer in answers
        if (
            answer in strong_central
            or central_frequency.get(answer, 0) >= args.minimum_answer_frequency
            or float(lexical_by_answer.get(answer, {}).get("sourceFrequency", 0))
            >= args.minimum_answer_frequency
        )
    }
    common_three_letter = {
        answer for answer, entry in lexical_by_answer.items()
        if len(answer) == 3 and float(entry.get("sourceFrequency", 0)) >= 3
    }
    common_three_letter.update(
        entry["answer"] for entry in entries
        if len(entry["answer"]) == 3 and (
            entry.get("sourceType") in {"image", "dictionary", "editorial-original"}
            or entry.get("image")
            or str(entry.get("sourceId", "")).startswith("jeuxdemots")
        )
    )
    short_filtered_by_length = {
        length: [
            answer for answer in answers
            if answer in human_allowed and (length != 3 or answer in common_three_letter)
        ]
        for length, answers in indexes[0].items()
    }
    short_allowed = {
        answer for answers in short_filtered_by_length.values() for answer in answers
    }
    if args.central_only:
        short_allowed &= central_answers
        short_filtered_by_length = {
            length: [answer for answer in answers if answer in short_allowed]
            for length, answers in short_filtered_by_length.items()
        }
    indexes = (
        short_filtered_by_length,
        indexes[1],
        *[
            {answer: value for answer, value in mapping.items() if answer in short_allowed}
            for mapping in indexes[2:6]
        ],
        indexes[6] & short_allowed,
    )
    # The shared placement index gives every central answer a very large
    # ordering bonus.  That is useful for coverage experiments, but it makes a
    # rare crossword answer outrank a familiar Lexique rescue.  For owner-facing
    # drafts, rank by observed French frequency and keep only a modest central
    # bonus.  Central coverage is still selected by ``editorial_cost`` below.
    human_frequency = {}
    frequency_jitter = random.Random(args.seed ^ 0x9491)
    for answer in short_allowed:
        source = sources.get(answer, {})
        observed = max(
            float(source.get("frequency", source.get("sourceFrequency", 0))),
            float(lexical_by_answer.get(answer, {}).get("sourceFrequency", 0)),
        )
        human_frequency[answer] = (
            math.log1p(observed) + 1
            + (0.15 if answer in central_answers else 0)
            + (1.5 if source.get("image") else 0)
            + frequency_jitter.uniform(-0.25, 0.25)
        )
    indexes = (
        indexes[0], indexes[1], human_frequency,
        indexes[3], indexes[4], indexes[5], indexes[6],
    )
    for answers in indexes[0].values():
        for answer in answers:
            if answer in sources:
                continue
            lexical = lexical_by_answer.get(answer, {})
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

    active = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    active_usage = Counter(
        word["answer"] for grid in active.get("grids", []) for word in grid["words"]
    )
    active_shapes = {
        tuple(sorted(map(tuple, grid.get("clueCells", []))))
        for grid in active.get("grids", [])
    }
    # Active repetition is measured in the final editorial score and capped
    # below, but it must not outrank basic word quality during CSP traversal.
    # Otherwise the solver prefers an unseen oddity to a familiar answer used
    # once months earlier.  Only source-tier penalties and within-batch reuse
    # belong in this hard ordering signal.
    # Source provenance must not be a hard traversal tier: a common Lexique
    # rescue is preferable to obscure crosswordese.  Provenance remains part
    # of the final editorial score, after a complete valid fill exists.
    search_usage: Counter[str] = Counter()

    excluded_answers = {answer.strip().upper() for answer in args.exclude_answer if answer.strip()}
    for raw_path in args.exclude_from:
        path = raw_path if raw_path.is_absolute() else ROOT / raw_path
        document = json.loads(path.read_text(encoding="utf-8"))
        excluded_answers.update(
            word["answer"]
            for grid in document.get("grids", [])
            for word in grid.get("words", [])
        )
    selected_answers: set[str] = set(excluded_answers)
    selected_families: set[str] = {answer_family(answer) for answer in excluded_answers}
    accepted = []
    rejects: Counter[str] = Counter()
    reject_examples: dict[str, list] = {}
    raw_shape_sources = tuple(args.shape_source) or SHAPE_SOURCES
    shape_sources = tuple(
        path if path.is_absolute() else ROOT / path for path in raw_shape_sources
    )
    templates = [
        shape for shape in shape_templates(shape_sources)
        if all(len(slot["cells"]) >= args.minimum_answer_length for slot in shape["slots"])
    ]
    if not templates:
        raise SystemExit("Aucune silhouette compatible avec la longueur minimale demandée")
    if args.reverse_shapes:
        templates.reverse()
    if args.shape_number:
        if not 1 <= args.shape_number <= len(templates):
            raise SystemExit(f"shape-number must be between 1 and {len(templates)}")
        templates = [templates[args.shape_number - 1]]
    for shape_index, shape in enumerate(templates):
        shape_fingerprint = tuple(sorted(map(tuple, shape["clueCells"])))
        if args.exclude_active_shapes and shape_fingerprint in active_shapes:
            rejects["active-shape"] += 1
            continue
        slots = [
            generator.Slot(
                slot["direction"], tuple(slot["clue"]),
                tuple(map(tuple, slot["cells"])), slot["arrow"],
            )
            for slot in shape["slots"]
        ]
        fixed_answers = {}
        if args.required_short_answer:
            short_slots = [
                index for index, slot in enumerate(slots) if len(slot.cells) == 2
            ]
            if len(short_slots) != 1:
                rejects["required-short-slot-count"] += 1
                continue
            fixed_answers[short_slots[0]] = args.required_short_answer.strip().upper()
        best = None
        for variant in range(args.variants):
            telemetry = {}
            variant_rng = random.Random(
                args.seed + shape_index * 1009 + variant * 7919
            )
            if args.solver == "cp-sat":
                answers = fill_cp_sat(
                    slots,
                    indexes,
                    variant_rng,
                    None,
                    unavailable_answers=selected_answers,
                    answer_usage=dict(search_usage),
                    grammar_answers=generator.GRAMMAR_ANSWERS,
                    max_grammar_answers=2,
                    max_seconds=args.fill_seconds,
                    require_image=args.minimum_images > 0,
                    minimum_images=args.minimum_images,
                    fixed_answers=fixed_answers,
                    telemetry=telemetry,
                )
            else:
                answers = generator.fill_bitset(
                    slots,
                    indexes,
                    variant_rng,
                    None,
                    unavailable_answers=selected_answers,
                    answer_usage=dict(search_usage),
                    grammar_answers=generator.GRAMMAR_ANSWERS,
                    max_grammar_answers=2,
                    max_seconds=args.fill_seconds,
                    node_limit=2_000_000,
                    require_image=args.minimum_images > 0,
                    minimum_images=args.minimum_images,
                    fixed_answers=fixed_answers,
                    prefer_constraint_support=True,
                    constraint_support_bucket_size=8,
                    telemetry=telemetry,
                )
            if answers is None:
                rejects[telemetry.get("reason", "fill-failed")] += 1
                continue
            values = list(answers.values())
            families = [answer_family(answer) for answer in values]
            if len(families) != len(set(families)) or set(families) & selected_families:
                rejects["singular-plural-family"] += 1
                continue
            rescue = {answer for answer in values if answer not in central_answers}
            nonstandard = {
                answer for answer in values
                if answer in central_answers and answer not in standard_central
            }
            active_repeats = {
                answer for answer in values if len(answer) >= 3 and active_usage[answer]
            }
            if len(rescue) > args.maximum_lexique_rescues:
                rejects["too-many-lexique-rescues"] += 1
                continue
            if len(nonstandard) > args.maximum_nonstandard_central:
                rejects["too-many-nonstandard-central"] += 1
                continue
            if len(active_repeats) > args.maximum_active_repeats:
                rejects["too-many-active-repeats"] += 1
                continue
            score = editorial_cost(
                values, sources, lexical_answers, active_usage,
                central_answers, standard_central,
            )
            candidate = (score, answers, telemetry, rescue, nonstandard, active_repeats)
            if best is None or score < best[0]:
                best = candidate
        if best is None:
            continue
        score, answers, telemetry, rescue, nonstandard, active_repeats = best
        grid = as_grid(len(accepted) + 1, shape, answers, sources, telemetry)
        grid_id = f"central-priority-owner-review-{len(accepted) + 1:02d}"
        grid["id"] = grid_id
        grid["publicationStatus"] = "manual-review-required"
        grid["corpusPolicy"] = "central-9491-priority-with-bounded-lexique-rescue"
        grid["centralAnswerCount"] = len(answers) - len(rescue)
        grid["lexiqueRescueCount"] = len(rescue)
        grid["editorialSearchCost"] = score
        grid["lexiqueRescues"] = sorted(rescue)
        grid["nonstandardCentral"] = sorted(nonstandard)
        grid["activeRepeatsLength3Plus"] = sorted(active_repeats)
        for number, word in enumerate(grid["words"], 1):
            word["wordId"] = f"{grid_id}:word:{number:02d}"
        report = audit_grid_topology(grid)
        blocking = [error for error in report["errors"] if error["code"] != "empty_clue"]
        if blocking:
            rejects["topology"] += 1
            reject_examples.setdefault("topology", []).append({
                "shape": shape_index + 1,
                "errors": blocking,
            })
            continue
        values = set(answers.values())
        selected_answers.update(values)
        selected_families.update(answer_family(answer) for answer in values)
        search_usage.update(values)
        accepted.append(grid)
        print(json.dumps({
            "accepted": len(accepted),
            "shape": shape_index + 1,
            "score": score,
            "central": len(answers) - len(rescue),
            "rescue": sorted(rescue),
            "answers": list(answers.values()),
        }, ensure_ascii=False), flush=True)
        if len(accepted) >= args.count:
            break

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 1,
        "kind": "non-publishable-refined-central-priority-drafts",
        "centralCorpusAnswers": len(entries),
        "humanEligiblePlacementAnswers": len(short_allowed),
        "centralOnly": args.central_only,
        "minimumAnswerFrequency": args.minimum_answer_frequency,
        "solver": args.solver,
        "minimumImages": args.minimum_images,
        "requiredShortAnswer": args.required_short_answer.strip().upper(),
        "excludedAnswers": sorted(excluded_answers),
        "excludedActiveShapes": args.exclude_active_shapes,
        "grids": accepted,
        "rejectionCounts": dict(rejects),
        "rejectionExamples": reject_examples,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "accepted": len(accepted),
        "requested": args.count,
        "availableShapes": len(templates),
        "output": str(output),
        "rejectionCounts": dict(rejects),
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
