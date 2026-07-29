#!/usr/bin/env python3
"""Rank strict 7x8 placements after propagating one reviewed anchor.

This scanner performs no deep search. It mirrors the pilot construction
domain, fixes exactly one answer, runs root arc-consistency/all-different
propagation, and records the remaining domain widths. Dead placements can
therefore be discarded before they consume solver time.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
from collections import Counter
from pathlib import Path

from wordfreq import zipf_frequency

from build_compact_7x8_review import family_key
from scan_modern_anchor_compatibility import compile_domains
from search_compact_grid_pilot import (
    PILOT_REVIEWED_CURRENT_SHORT,
    PILOT_SAFE_SHORT,
    Slot,
    build_slots_from_shape,
    excluded_answers,
    load_editorial_rescue_entries,
    normalized,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHAPES = ROOT / "output/quality/corrected-7x8-shapes/corrected-shape-library.json"
DEFAULT_RESCUE = ROOT / "src/data/grid-generation/editorial-rescue.young-common.20260721.json"
DEFAULT_OUTPUT = ROOT / "output/quality/semi-editorial-7x8-pilot/single-anchor-feasibility.json"
DEFAULT_ANCHORS = (
    "CONSOLE",
    "PODCAST",
    "NETFLIX",
    "GUITARE",
    "FROMAGE",
    "TIKTOK",
    "MOBILE",
    "SOURIS",
    "DANSER",
    "TWITCH",
)
PILOT_EXCLUDED = {
    "PROFES", "ARANDA", "ELIADE", "TOMCAT", "ACABIT", "ROBINE",
    "PUTAIN", "AMENAGE", "ELARGI", "STOPPE", "REPORTE", "DJIHAD", "MAHOMET",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shape-file", type=Path, default=DEFAULT_SHAPES)
    parser.add_argument("--rescue-file", type=Path, default=DEFAULT_RESCUE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--anchor", action="append", default=[])
    parser.add_argument("--exclude-shape", action="append", default=["corrected-7x8-03"])
    parser.add_argument("--minimum-zipf", type=float, default=3.2)
    parser.add_argument("--minimum-constructor-score", type=float, default=5.0)
    return parser.parse_args()


def next_pilot_exclusions() -> set[str]:
    document = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    return {
        normalized(str(item.get("answer", "")))
        for item in document.get("registerPenaltyAnswers", [])
        if isinstance(item, dict) and item.get("excludeFromNextPilot") is True
    }


def strict_construction_indexes(
    lengths: set[int], rescue_file: Path, minimum_zipf: float, minimum_score: float
):
    excluded = excluded_answers([]) | next_pilot_exclusions() | PILOT_EXCLUDED
    excluded_families = {family_key(answer) for answer in excluded}
    by_length: dict[int, list[str]] = {length: [] for length in lengths}
    scores: dict[str, float] = {}
    families: dict[str, str] = {}
    metadata: dict[str, dict] = {}
    with gzip.open(
        ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8"
    ) as stream:
        entries = json.load(stream).get("entries", [])
    for item in entries:
        answer = normalized(str(item.get("answer", "")))
        spelling = str(item.get("spelling") or answer.lower())
        constructor_score = float(item.get("constructorScore", 0.0))
        zipf = float(zipf_frequency(spelling, "fr"))
        if (
            len(answer) not in by_length
            or answer in excluded
            or family_key(str(item.get("lemma") or answer)) in excluded_families
            or answer in scores
            or item.get("attestedCommonForm") is not True
            or item.get("partOfSpeech") == "proper-noun"
            or (
                item.get("partOfSpeech") == "verb"
                and item.get("formType") != "lemma"
            )
            or constructor_score < minimum_score
            or zipf < minimum_zipf
            or (len(answer) <= 3 and answer not in PILOT_SAFE_SHORT)
        ):
            continue
        scores[answer] = constructor_score + 5.0 * zipf
        families[answer] = family_key(str(item.get("lemma") or answer))
        metadata[answer] = {
            "source": "large-attested-common",
            "partOfSpeech": item.get("partOfSpeech"),
            "formType": item.get("formType"),
            "wordfreqZipf": zipf,
        }
        by_length[len(answer)].append(answer)

    for answer in PILOT_SAFE_SHORT - excluded:
        if len(answer) not in by_length or family_key(answer) in excluded_families:
            continue
        if answer not in scores:
            by_length[len(answer)].append(answer)
        scores[answer] = max(scores.get(answer, 0.0), 50.0)
        families[answer] = family_key(answer)
        metadata[answer] = {
            "source": "pilot-safe-short",
            "partOfSpeech": "editorial-reviewed",
            "formType": "editorial-reviewed",
            "wordfreqZipf": float(zipf_frequency(answer.lower(), "fr")),
        }

    rescue_answers = set()
    recognized_current_answers = {
        answer for answer in PILOT_REVIEWED_CURRENT_SHORT if answer in scores
    }
    for item in load_editorial_rescue_entries(rescue_file):
        answer = item["answer"]
        lemma_family = family_key(str(item.get("lemma") or answer))
        if (
            len(answer) not in by_length
            or answer in excluded
        ):
            continue
        if answer not in scores:
            by_length[len(answer)].append(answer)
        scores[answer] = max(scores.get(answer, 0.0), 90.0)
        families[answer] = lemma_family
        metadata[answer] = {
            "source": "human-reviewed-rescue",
            "partOfSpeech": item.get("partOfSpeech"),
            "formType": item.get("formType"),
            "register": item.get("register"),
            "wordfreqZipf": float(zipf_frequency(
                str(item.get("spelling") or answer).lower(), "fr"
            )),
        }
        rescue_answers.add(answer)
        if str(item.get("register") or "").startswith("current-"):
            recognized_current_answers.add(answer)

    indexed = {
        length: tuple(sorted(set(words))) for length, words in by_length.items()
    }
    indexes = (
        indexed,
        None,
        scores,
        families,
        {answer: set() for answer in scores},
        {answer: "normal" for answer in scores},
        set(),
    )
    return indexes, metadata, rescue_answers, recognized_current_answers


def propagate_single_anchor(
    slots: list[Slot], indexed, word_index, masks, slot_index: int, answer: str
) -> dict:
    domains: list[int] = []
    for slot in slots:
        length = len(slot.cells)
        domain = (1 << len(indexed[length])) - 1
        if slot.index == slot_index:
            index = word_index[length].get(answer)
            if index is None:
                return {"survives": False, "reason": "fixed-answer-missing"}
            domain = 1 << index
        domains.append(domain)

    cell_links: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for slot in slots:
        for position, cell in enumerate(slot.cells):
            cell_links.setdefault(cell, []).append((slot.index, position))
    arcs = []
    for links in cell_links.values():
        if len(links) == 2:
            left, right = links
            arcs.extend((
                (left[0], left[1], right[0], right[1]),
                (right[0], right[1], left[0], left[1]),
            ))
    by_length: dict[int, list[int]] = {}
    for slot in slots:
        by_length.setdefault(len(slot.cells), []).append(slot.index)

    changed = True
    while changed:
        changed = False
        for group in by_length.values():
            singles = [domains[index] for index in group if domains[index].bit_count() == 1]
            if len(singles) != len(set(singles)):
                return {"survives": False, "reason": "duplicate-singleton"}
            used = 0
            for singleton in singles:
                used |= singleton
            for index in group:
                if domains[index].bit_count() == 1:
                    continue
                revised = domains[index] & ~used
                if not revised:
                    return {
                        "survives": False,
                        "reason": "all-different-domain-wipeout",
                        "slot": index,
                    }
                if revised != domains[index]:
                    domains[index] = revised
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
                return {
                    "survives": False,
                    "reason": "crossing-domain-wipeout",
                    "slot": left,
                    "position": left_position,
                    "neighbor": right,
                    "neighborPosition": right_position,
                }
            if revised != domains[left]:
                domains[left] = revised
                changed = True

    widths = {
        str(slot.index): domains[slot.index].bit_count()
        for slot in slots if slot.index != slot_index
    }
    values = list(widths.values())
    return {
        "survives": True,
        "reason": "survives-root-propagation",
        "domainWidths": widths,
        "minimumRemainingDomain": min(values),
        "narrowDomainCount": sum(value <= 10 for value in values),
        "domainFlexibility": round(sum(math.log2(value + 1) for value in values), 3),
        "bottleneckSlots": [
            int(index) for index, value in widths.items() if value == min(values)
        ],
    }


def anchor_patterns(slots: list[Slot], slot_index: int, answer: str) -> dict[str, str]:
    letters = dict(zip(slots[slot_index].cells, answer))
    return {
        str(slot.index): "".join(letters.get(cell, "?") for cell in slot.cells)
        for slot in slots
        if slot.index != slot_index
        and any(cell in letters for cell in slot.cells)
    }


def main() -> int:
    args = parse_args()
    anchors = tuple(dict.fromkeys(
        normalized(answer) for answer in (args.anchor or DEFAULT_ANCHORS)
    ))
    library = json.loads(args.shape_file.read_text(encoding="utf-8"))
    parsed = []
    lengths: set[int] = set()
    excluded_shapes = set(args.exclude_shape)
    for shape in library.get("shapes", []):
        if shape.get("shapeId") in excluded_shapes:
            continue
        columns, rows, shape_id, clues, raw_slots, slots = build_slots_from_shape(shape)
        if (columns, rows) != (7, 8):
            continue
        lengths.update(len(slot.cells) for slot in slots)
        parsed.append((shape_id, raw_slots, slots))

    indexes, metadata, rescue_answers, recognized_current_answers = strict_construction_indexes(
        lengths, args.rescue_file, args.minimum_zipf, args.minimum_constructor_score
    )
    indexed = indexes[0]
    word_index, masks = compile_domains(indexed)
    reports = []
    causes: Counter[str] = Counter()
    for shape_id, raw_slots, slots in parsed:
        for anchor in anchors:
            for slot in slots:
                if len(slot.cells) != len(anchor):
                    continue
                result = propagate_single_anchor(
                    slots, indexed, word_index, masks, slot.index, anchor
                )
                causes[result["reason"]] += 1
                reports.append({
                    "shapeId": shape_id,
                    "anchor": anchor,
                    "anchorMetadata": metadata.get(anchor),
                    "slotIndex": slot.index,
                    "direction": slot.direction,
                    "patterns": anchor_patterns(slots, slot.index, anchor),
                    **result,
                })

    survivors = [item for item in reports if item["survives"]]
    survivors.sort(key=lambda item: (
        -item["minimumRemainingDomain"],
        item["narrowDomainCount"],
        -item["domainFlexibility"],
        0 if item["anchor"] == "CONSOLE" else 1,
        item["shapeId"],
        item["slotIndex"],
    ))
    payload = {
        "version": 1,
        "kind": "motman-reviewed-single-anchor-root-feasibility",
        "shapeFile": str(args.shape_file),
        "rescueFile": str(args.rescue_file),
        "catalogModified": False,
        "publicationEligible": False,
        "excludedShapes": sorted(excluded_shapes),
        "anchors": list(anchors),
        "strictDomain": {
            "minimumZipf": args.minimum_zipf,
            "minimumConstructorScore": args.minimum_constructor_score,
            "properNames": "human-reviewed-rescue-only",
            "finiteVerbs": "forbidden",
            "candidateCounts": {
                str(length): len(words) for length, words in indexed.items()
            },
            "reviewedRescueAnswers": sorted(rescue_answers),
            "recognizedCurrentAnswers": sorted(recognized_current_answers),
        },
        "placementCount": len(reports),
        "survivingPlacementCount": len(survivors),
        "rejectionCauses": dict(causes.most_common()),
        "recommendedDeepSearches": survivors[:12],
        "placements": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "placementCount": len(reports),
        "survivingPlacementCount": len(survivors),
        "rejectionCauses": dict(causes.most_common()),
        "recommendedDeepSearches": [
            {
                "shapeId": item["shapeId"],
                "anchor": item["anchor"],
                "slotIndex": item["slotIndex"],
                "minimumRemainingDomain": item["minimumRemainingDomain"],
                "narrowDomainCount": item["narrowDomainCount"],
                "domainFlexibility": item["domainFlexibility"],
            }
            for item in survivors[:12]
        ],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
