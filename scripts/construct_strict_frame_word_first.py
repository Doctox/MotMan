#!/usr/bin/env python3
"""Construct strict-frame grids from common boundary words before choosing the mask."""
from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import craft_flexible_common_grid as craft  # noqa: E402
from bitset_grid_filler import fill_bitset  # noqa: E402
from generate_large_lexical_batch import is_editorially_confirmed  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--wordlist",
        type=Path,
        default=ROOT / "src/data/fill.wordlist.large.json.gz",
    )
    parser.add_argument("--minimum-boundary-score", type=float, default=20.0)
    parser.add_argument("--maximum-two-letter", type=int, default=2)
    parser.add_argument("--maximum-three-letter", type=int, default=6)
    parser.add_argument("--maximum-unconfirmed", type=int, default=2)
    parser.add_argument("--attempt-limit", type=int, default=200000)
    parser.add_argument("--seconds", type=float, default=180.0)
    parser.add_argument("--seconds-per-fill", type=float, default=3.0)
    parser.add_argument("--target", type=int, default=3)
    parser.add_argument("--seed", type=int, default=724800)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def endpoints_are_compatible(
    vertical: dict[int, str], horizontal: dict[int, str]
) -> bool:
    for column, word in vertical.items():
        if len(word) < craft.ROWS - 1:
            endpoint_row = len(word) + 1
            if column <= len(horizontal[endpoint_row]):
                return False
    for row, word in horizontal.items():
        if len(word) < craft.COLUMNS - 1:
            endpoint_column = len(word) + 1
            if row <= len(vertical[endpoint_column]):
                return False
    return True


def main() -> int:
    args = parse_args()
    craft.MAX_TWO_LETTER = args.maximum_two_letter
    loaded = craft.load_large_constructor_candidates(
        args.wordlist, set(), 15.0
    )
    if loaded is None:
        raise RuntimeError("The definition-free constructor wordlist is missing")
    words_by_length, scores, spellings, lemmas, _usage, meta = loaded
    with gzip.open(args.wordlist, "rt", encoding="utf-8") as handle:
        wordlist = json.load(handle)
    metadata = {
        entry["answer"]: entry for entry in wordlist.get("entries", [])
        if entry.get("answer") in scores
    }
    confirmed = {
        answer for answer, entry in metadata.items()
        if is_editorially_confirmed(answer, entry)
    }
    active_usage = craft.active_usage()
    boundary_answers = {
        answer for answer in confirmed
        if scores[answer] >= args.minimum_boundary_score
        and answer not in active_usage
    }
    boundary_by_length_prefix: dict[int, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for answer in boundary_answers:
        boundary_by_length_prefix[len(answer)][answer[:2]].append(answer)
    for prefixes in boundary_by_length_prefix.values():
        for answers in prefixes.values():
            answers.sort(key=lambda answer: (-scores[answer], answer))
    boundary9 = sorted(
        (answer for answer in boundary_answers if len(answer) == 9),
        key=lambda answer: (-scores[answer], answer),
    )
    conflicts = craft.load_rejected_cooccurrence_map()
    indexes = (
        words_by_length,
        None,
        scores,
        lemmas,
        {answer: set(conflicts.get(answer, set())) for answer in scores},
        {answer: "normal" for answer in scores},
        set(),
    )
    rng = random.Random(args.seed)
    started = time.monotonic()
    attempts = 0
    fill_attempts = 0
    failure_reasons = Counter()
    candidates = []
    seen_geometry = set()

    def choose(prefix: str, length: int, used: set[str]) -> str | None:
        options = [
            answer
            for answer in boundary_by_length_prefix[length].get(prefix, [])[:80]
            if answer not in used
        ]
        if not options:
            return None
        options.sort(key=lambda answer: (-scores[answer], answer))
        return rng.choice(options[: min(40, len(options))])

    while (
        len(candidates) < args.target
        and attempts < args.attempt_limit
        and time.monotonic() - started < args.seconds
    ):
        attempts += 1
        down1 = rng.choice(boundary9)
        down2 = rng.choice(boundary9)
        if down1 == down2:
            continue
        across1_options = boundary_by_length_prefix[8].get(
            down1[0] + down2[0], []
        )
        across2_options = boundary_by_length_prefix[8].get(
            down1[1] + down2[1], []
        )
        if not across1_options or not across2_options:
            continue
        across1 = rng.choice(across1_options[: min(60, len(across1_options))])
        across2 = rng.choice(across2_options[: min(60, len(across2_options))])
        used = {down1, down2, across1, across2}
        if len(used) != 4:
            continue
        vertical_options = {}
        for column in range(3, craft.COLUMNS):
            prefix = across1[column - 1] + across2[column - 1]
            vertical_options[column] = {
                length: boundary_by_length_prefix[length].get(prefix, [])
                for length in range(3, craft.ROWS)
                if boundary_by_length_prefix[length].get(prefix)
            }
        horizontal_options = {}
        for row in range(3, craft.ROWS):
            prefix = down1[row - 1] + down2[row - 1]
            horizontal_options[row] = {
                length: boundary_by_length_prefix[length].get(prefix, [])
                for length in range(3, craft.COLUMNS)
                if boundary_by_length_prefix[length].get(prefix)
            }
        if any(not options for options in vertical_options.values()) or any(
            not options for options in horizontal_options.values()
        ):
            continue
        vertical_lengths = None
        horizontal_lengths = None
        for _layout_attempt in range(80):
            candidate_vertical = {1: 9, 2: 9}
            for column, options in vertical_options.items():
                lengths = sorted(options)
                candidate_vertical[column] = rng.choice(lengths)
            candidate_horizontal = {1: 8, 2: 8}
            layout_viable = True
            for row, options in horizontal_options.items():
                max_length = 8
                endpoint_columns = [
                    column
                    for column, length in candidate_vertical.items()
                    if length < 9 and length + 1 == row
                ]
                if endpoint_columns:
                    max_length = min(endpoint_columns) - 1
                allowed_lengths = [
                    length for length in options
                    if length <= max_length
                    and (
                        length == 8
                        or candidate_vertical[length + 1] < row
                    )
                ]
                if not allowed_lengths:
                    layout_viable = False
                    break
                candidate_horizontal[row] = rng.choice(allowed_lengths)
            if layout_viable:
                vertical_lengths = candidate_vertical
                horizontal_lengths = candidate_horizontal
                break
        if vertical_lengths is None or horizontal_lengths is None:
            continue
        vertical = {1: down1, 2: down2}
        horizontal = {1: across1, 2: across2}
        viable = True
        for column in range(3, craft.COLUMNS):
            prefix = across1[column - 1] + across2[column - 1]
            answer = choose(prefix, vertical_lengths[column], used)
            if answer is None:
                viable = False
                break
            vertical[column] = answer
            used.add(answer)
        if not viable:
            continue
        for row in range(3, craft.ROWS):
            prefix = down1[row - 1] + down2[row - 1]
            answer = choose(prefix, horizontal_lengths[row], used)
            if answer is None:
                viable = False
                break
            horizontal[row] = answer
            used.add(answer)
        if not viable or not endpoints_are_compatible(vertical, horizontal):
            continue
        clues = set(craft.FRAME)
        for column, answer in vertical.items():
            if len(answer) < craft.ROWS - 1:
                clues.add((len(answer) + 1, column))
        for row, answer in horizontal.items():
            if len(answer) < craft.COLUMNS - 1:
                clues.add((row, len(answer) + 1))
        fingerprint = tuple(sorted(clues))
        if fingerprint in seen_geometry:
            continue
        raw_slots = craft.direct_slots(clues)
        lengths = [slot["length"] for slot in raw_slots]
        if (
            not lengths
            or min(lengths) < 2
            or lengths.count(2) > args.maximum_two_letter
            or lengths.count(3) > args.maximum_three_letter
        ):
            continue
        geometry_id = f"strict-frame-word-first-{len(seen_geometry) + 1:05d}"
        audit = craft.validate_geometry(geometry_id, clues, raw_slots)
        if not audit.get("valid"):
            failure_reasons["invalid-geometry"] += 1
            continue
        slots = [
            craft.Slot(
                index=index,
                slot_id=item["slotId"],
                direction=item["direction"],
                clue_cell=tuple(item["clueCell"]),
                cells=tuple(tuple(cell) for cell in item["cells"]),
            )
            for index, item in enumerate(raw_slots)
        ]
        index_by_launch = {
            (slot.direction, slot.clue_cell): slot.index for slot in slots
        }
        fixed_answers = {}
        for column, answer in vertical.items():
            slot_index = index_by_launch.get(("down", (0, column)))
            if slot_index is None or len(slots[slot_index].cells) != len(answer):
                viable = False
                break
            fixed_answers[slot_index] = answer
        if not viable:
            continue
        for row, answer in horizontal.items():
            slot_index = index_by_launch.get(("across", (row, 0)))
            if slot_index is None or len(slots[slot_index].cells) != len(answer):
                viable = False
                break
            fixed_answers[slot_index] = answer
        if not viable or len(fixed_answers) != 17:
            continue
        seen_geometry.add(fingerprint)
        fill_attempts += 1
        telemetry = {}
        solved = fill_bitset(
            slots,
            indexes,
            random.Random(args.seed + attempts),
            None,
            unavailable_answers=set(active_usage),
            answer_usage={answer: count * 10000 for answer, count in active_usage.items()},
            fixed_answers=fixed_answers,
            undesirable_answers=set(scores) - confirmed,
            max_undesirable_answers=args.maximum_unconfirmed,
            max_grammar_answers=99,
            grammar_answers=set(),
            require_image=False,
            prefer_constraint_support=True,
            constraint_support_bucket_size=4,
            branching_strategy="cell",
            quality_scores=scores,
            solution_limit=64,
            max_seconds=min(
                args.seconds_per_fill,
                max(0.05, args.seconds - (time.monotonic() - started)),
            ),
            node_limit=8_000_000,
            telemetry=telemetry,
        )
        if solved is None:
            failure_reasons[str(telemetry.get("reason", "unsolved"))] += 1
            continue
        answers = [solved[index] for index in sorted(solved)]
        candidates.append({
            "id": f"strict-frame-word-first-candidate-{len(candidates) + 1:02d}",
            "sourceShapeId": geometry_id,
            "clueCells": [list(cell) for cell in sorted(clues)],
            "rawSlots": raw_slots,
            "geometryAudit": {**audit, "sourceShapeId": geometry_id},
            "fixedBoundaryAnswers": {
                str(index): answer for index, answer in sorted(fixed_answers.items())
            },
            "answers": [
                {
                    "slotIndex": index,
                    "answer": solved[index],
                    "spelling": spellings[solved[index]],
                    "lemma": lemmas[solved[index]],
                    "constructorScore": scores[solved[index]],
                    "editoriallyConfirmed": solved[index] in confirmed,
                    "formType": metadata[solved[index]].get("formType"),
                    "attestedCommonForm": metadata[solved[index]].get(
                        "attestedCommonForm", False
                    ),
                }
                for index in sorted(solved)
            ],
            "solverTelemetry": telemetry,
            "publicationEligible": False,
        })
    payload = {
        "version": 1,
        "kind": "strict-frame-word-first-candidates",
        "catalogModified": False,
        "publicationEligible": False,
        "policy": {
            "topRowAllDefinitions": True,
            "leftColumnAllDefinitions": True,
            "wordFirstBoundaryConstruction": True,
            "maximumTwoLetterAnswers": args.maximum_two_letter,
            "maximumThreeLetterAnswers": args.maximum_three_letter,
            "maximumUnconfirmedAnswers": args.maximum_unconfirmed,
        },
        "metrics": {
            "attempts": attempts,
            "validGeometriesTried": fill_attempts,
            "candidates": len(candidates),
            "elapsedSeconds": round(time.monotonic() - started, 2),
            "failureReasons": dict(sorted(failure_reasons.items())),
        },
        "candidates": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))
    return 0 if candidates else 1


if __name__ == "__main__":
    raise SystemExit(main())
