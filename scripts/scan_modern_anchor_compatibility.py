#!/usr/bin/env python3
"""Cheap AC-3 compatibility scan for reviewed modern answers on 7x8 shapes.

This is deliberately not a grid generator.  It loads the construction domain
once, fixes two reviewed anchors at a time, and asks the bitset solver to run
root propagation only.  A surviving pair is worth a bounded full search; an
immediate wipeout is not.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from wordfreq import zipf_frequency

from build_compact_7x8_review import family_key
from search_compact_grid_pilot import (
    PILOT_CONCEPT_FAMILY_OVERRIDES,
    PILOT_REVIEWED_LONG,
    PILOT_SAFE_SHORT,
    build_slots_from_shape,
    excluded_answers,
    normalized,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHAPES = ROOT / "output/quality/corrected-7x8-shapes/corrected-shape-library.json"
DEFAULT_OUTPUT = ROOT / "output/quality/modern-anchor-compatibility.json"
MODERN_ANSWERS = (
    "WEB", "GIF", "BUG", "BOX", "RAP",
    "WIFI", "LIVE", "MEME", "CLIP", "BLOG",
    "STREAM", "CASQUE", "SERIES", "TWITCH", "DISNEY", "TIKTOK",
    "GAMING", "MOBILE", "GOOGLE", "MARVEL",
    "NETFLIX", "PODCAST", "POKEMON", "CONSOLE", "CLAVIER", "YOUTUBE",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shape-file", type=Path, default=DEFAULT_SHAPES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-zipf", type=float, default=2.0)
    parser.add_argument("--minimum-constructor-score", type=float, default=5.0)
    return parser.parse_args()


def construction_indexes(lengths: set[int], minimum_zipf: float, minimum_score: float):
    excluded = excluded_answers([])
    excluded_families = {family_key(answer) for answer in excluded}
    by_length = {length: [] for length in lengths}
    scores: dict[str, float] = {}
    families: dict[str, str] = {}
    with gzip.open(ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8") as stream:
        entries = json.load(stream).get("entries", [])
    for item in entries:
        answer = normalized(str(item.get("answer", "")))
        spelling = str(item.get("spelling") or answer.lower())
        score = float(item.get("constructorScore", 0.0))
        if (
            len(answer) not in by_length
            or answer in excluded
            or family_key(answer) in excluded_families
            or answer in scores
            or item.get("attestedCommonForm") is not True
            or (
                item.get("partOfSpeech") == "verb"
                and item.get("formType") != "lemma"
            )
            or score < minimum_score
            or float(zipf_frequency(spelling, "fr")) < minimum_zipf
            or (len(answer) <= 3 and answer not in PILOT_SAFE_SHORT)
        ):
            continue
        scores[answer] = score + 5.0 * float(zipf_frequency(spelling, "fr"))
        families[answer] = family_key(str(item.get("lemma") or answer))
        by_length[len(answer)].append(answer)

    reviewed = PILOT_SAFE_SHORT | PILOT_REVIEWED_LONG
    for answer in reviewed:
        if (
            len(answer) not in by_length
            or answer in excluded
            or family_key(answer) in excluded_families
            or answer in scores
        ):
            continue
        scores[answer] = 65.0
        families[answer] = family_key(answer)
        by_length[len(answer)].append(answer)
    manual_anchor_only = set()
    # Match search_compact_grid_pilot exactly: an out-of-domain modern term is
    # admitted only in the slot where it is explicitly fixed, never as an
    # automatic support word elsewhere in the grid.
    for answer in MODERN_ANSWERS:
        if (
            len(answer) not in by_length
            or answer in excluded
            or family_key(answer) in excluded_families
            or answer in scores
        ):
            continue
        scores[answer] = 65.0
        families[answer] = family_key(answer)
        by_length[len(answer)].append(answer)
        manual_anchor_only.add(answer)
    for answer, family in PILOT_CONCEPT_FAMILY_OVERRIDES.items():
        if answer in families:
            families[answer] = family
    indexed = {length: tuple(sorted(words)) for length, words in by_length.items()}
    return (
        indexed,
        None,
        scores,
        families,
        {answer: set() for answer in scores},
        {answer: "normal" for answer in scores},
        set(),
    ), scores, families, manual_anchor_only


def crossing_conflict(slots, left_slot: int, left: str, right_slot: int, right: str) -> bool:
    left_positions = {cell: position for position, cell in enumerate(slots[left_slot].cells)}
    for position, cell in enumerate(slots[right_slot].cells):
        other = left_positions.get(cell)
        if other is not None and left[other] != right[position]:
            return True
    return False


def compile_domains(indexed: dict[int, tuple[str, ...]]):
    word_index = {
        length: {word: index for index, word in enumerate(words)}
        for length, words in indexed.items()
    }
    masks = {
        length: [dict((letter, 0) for letter in range(26)) for _ in range(length)]
        for length in indexed
    }
    for length, words in indexed.items():
        for index, word in enumerate(words):
            bit = 1 << index
            for position, letter in enumerate(word):
                masks[length][position][ord(letter) - 65] |= bit
    return word_index, masks


def root_propagation(
    slots, indexed, word_index, masks, fixed_answers, manual_anchor_only
):
    domains = []
    for slot in slots:
        length = len(slot.cells)
        domain = (1 << len(indexed[length])) - 1
        fixed = fixed_answers.get(slot.index)
        if fixed is not None:
            index = word_index[length].get(fixed)
            if index is None:
                return False, "fixed-answer-missing"
            domain = 1 << index
        else:
            for answer in manual_anchor_only:
                index = word_index[length].get(answer)
                if index is not None:
                    domain &= ~(1 << index)
        domains.append(domain)

    cell_links = {}
    for slot in slots:
        for position, cell in enumerate(slot.cells):
            cell_links.setdefault(cell, []).append((slot.index, position))
    arcs = []
    for links in cell_links.values():
        if len(links) != 2:
            continue
        left, right = links
        arcs.extend(((left[0], left[1], right[0], right[1]),
                     (right[0], right[1], left[0], left[1])))
    by_length = {}
    for slot in slots:
        by_length.setdefault(len(slot.cells), []).append(slot.index)

    changed = True
    while changed:
        changed = False
        for length, group in by_length.items():
            singles = [domains[slot] for slot in group if domains[slot].bit_count() == 1]
            if len(singles) != len(set(singles)):
                return False, "duplicate-singleton"
            used = 0
            for singleton in singles:
                used |= singleton
            for slot in group:
                if domains[slot].bit_count() == 1:
                    continue
                revised = domains[slot] & ~used
                if not revised:
                    return False, "all-different-domain-wipeout"
                if revised != domains[slot]:
                    domains[slot] = revised
                    changed = True

        for left, left_position, right, right_position in arcs:
            right_length = len(slots[right].cells)
            supported_letters = [
                letter for letter in range(26)
                if domains[right] & masks[right_length][right_position][letter]
            ]
            left_length = len(slots[left].cells)
            allowed = 0
            for letter in supported_letters:
                allowed |= masks[left_length][left_position][letter]
            revised = domains[left] & allowed
            if not revised:
                return False, "crossing-domain-wipeout"
            if revised != domains[left]:
                domains[left] = revised
                changed = True
    return True, "survives-root-propagation"


def main() -> int:
    args = parse_args()
    library = json.loads(args.shape_file.read_text(encoding="utf-8"))
    shapes = library.get("shapes", [])
    parsed = []
    lengths: set[int] = set()
    for shape in shapes:
        columns, rows, shape_id, clues, raw_slots, slots = build_slots_from_shape(shape)
        lengths.update(len(slot.cells) for slot in slots)
        parsed.append((shape_id, columns, rows, clues, raw_slots, slots))
    indexes, scores, families, manual_anchor_only = construction_indexes(
        lengths, args.minimum_zipf, args.minimum_constructor_score
    )
    indexed = indexes[0]
    word_index, masks = compile_domains(indexed)

    shape_reports = []
    rejection_causes: Counter[str] = Counter()
    for shape_id, columns, rows, clues, raw_slots, slots in parsed:
        placements = [
            (answer, slot.index)
            for answer in MODERN_ANSWERS
            for slot in slots
            if len(answer) == len(slot.cells)
        ]
        tested = preconflict = 0
        survivors = []
        for left_index, (left, left_slot) in enumerate(placements):
            for right, right_slot in placements[left_index + 1:]:
                if left == right or left_slot == right_slot:
                    continue
                tested += 1
                if crossing_conflict(slots, left_slot, left, right_slot, right):
                    preconflict += 1
                    rejection_causes["direct-anchor-letter-conflict"] += 1
                    continue
                survives, reason = root_propagation(
                    slots, indexed, word_index, masks,
                    {left_slot: left, right_slot: right},
                    manual_anchor_only,
                )
                if survives:
                    survivors.append({
                        "answers": [left, right],
                        "slots": [left_slot, right_slot],
                        "lengthSum": len(left) + len(right),
                    })
                else:
                    rejection_causes[reason] += 1
        survivors.sort(key=lambda item: (-item["lengthSum"], item["answers"], item["slots"]))
        slot_lengths = [len(slot.cells) for slot in slots]
        shape_reports.append({
            "shapeId": shape_id,
            "slotCount": len(slots),
            "threeLetterSlotCount": slot_lengths.count(3),
            "slotLengths": slot_lengths,
            "placementCount": len(placements),
            "pairCountTested": tested,
            "directAnchorConflicts": preconflict,
            "compatiblePairCount": len(survivors),
            "bestCompatiblePairs": survivors[:25],
        })

    ranked = sorted(
        (item for item in shape_reports if item["compatiblePairCount"]),
        key=lambda item: (
            item["threeLetterSlotCount"],
            -item["bestCompatiblePairs"][0]["lengthSum"],
            -item["compatiblePairCount"],
            item["shapeId"],
        ),
    )
    payload = {
        "version": 1,
        "kind": "modern-anchor-root-propagation-scan",
        "shapeFile": str(args.shape_file),
        "modernAnswers": list(MODERN_ANSWERS),
        "minimumModernAnswers": 2,
        "propagationOnly": True,
        "candidateCounts": {str(length): len(words) for length, words in indexes[0].items()},
        "compatibleShapeCount": len(ranked),
        "recommendedAttempt": (
            {
                "shapeId": ranked[0]["shapeId"],
                **ranked[0]["bestCompatiblePairs"][0],
                "threeLetterSlotCount": ranked[0]["threeLetterSlotCount"],
            }
            if ranked else None
        ),
        "rejectionCauses": dict(rejection_causes.most_common()),
        "shapes": shape_reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
