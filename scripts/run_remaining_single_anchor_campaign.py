#!/usr/bin/env python3
"""Evaluate every root-surviving single-anchor placement with one shared cache."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from bitset_grid_filler import fill_bitset
from editorial_fill_quality import answer_usage
from scan_reviewed_single_anchor_7x8 import strict_construction_indexes
from search_compact_grid_pilot import GRAMMAR_ANSWERS, build_slots_from_shape


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCAN = ROOT / "output/quality/semi-editorial-7x8-pilot/single-anchor-feasibility.json"
DEFAULT_SHAPES = ROOT / "output/quality/corrected-7x8-shapes/corrected-shape-library.json"
DEFAULT_RESCUE = ROOT / "src/data/grid-generation/editorial-rescue.young-common.20260721.json"
DEFAULT_DEEP_DIR = ROOT / "output/quality/semi-editorial-7x8-pilot"
DEFAULT_OUTPUT = ROOT / "output/quality/semi-editorial-7x8-pilot/remaining-single-anchor-campaign.json"
DEFAULT_CATALOG = ROOT / "src/data/grid.catalog.json"
CACHE_VERSION = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", type=Path, default=DEFAULT_SCAN)
    parser.add_argument("--shape-file", type=Path, default=DEFAULT_SHAPES)
    parser.add_argument("--rescue-file", type=Path, default=DEFAULT_RESCUE)
    parser.add_argument("--deep-dir", type=Path, default=DEFAULT_DEEP_DIR)
    parser.add_argument("--reference-catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seconds-per-placement", type=float, default=8.0)
    parser.add_argument("--solution-limit", type=int, default=8)
    parser.add_argument("--minimum-current-answers", type=int, default=2)
    parser.add_argument("--minimum-zipf", type=float, default=3.2)
    parser.add_argument("--minimum-constructor-score", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=26072190)
    parser.add_argument(
        "--include-prior-deep",
        action="store_true",
        help="Réévalue aussi les placements historiques avec la politique actuelle.",
    )
    return parser.parse_args()


def placement_key(shape_id: str, anchor: str, slot_index: int) -> str:
    return f"{shape_id}|{anchor}|{slot_index}"


def prior_deep_keys(directory: Path) -> set[str]:
    keys = set()
    for path in directory.glob("deep-*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        fixed = document.get("requestedFixedAnswers", {})
        if len(fixed) != 1:
            continue
        slot_index, anchor = next(iter(fixed.items()))
        keys.add(placement_key(
            str(document.get("sourceShapeId")), str(anchor), int(slot_index)
        ))
    return keys


def ordered_remaining_placements(scan: dict, already_tested: set[str]) -> list[dict]:
    placements = [
        item for item in scan.get("placements", [])
        if item.get("survives")
        and placement_key(item["shapeId"], item["anchor"], item["slotIndex"])
        not in already_tested
    ]
    placements.sort(key=lambda item: (
        -int(item.get("minimumRemainingDomain", 0)),
        int(item.get("narrowDomainCount", 0)),
        -float(item.get("domainFlexibility", 0.0)),
        item["shapeId"],
        int(item["slotIndex"]),
        item["anchor"],
    ))
    return placements


def input_digest(paths: list[Path], parameters: dict) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    digest.update(json.dumps(parameters, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def write_checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    scan = json.loads(args.scan.read_text(encoding="utf-8"))
    library = json.loads(args.shape_file.read_text(encoding="utf-8"))
    shapes = {}
    lengths: set[int] = set()
    for shape in library.get("shapes", []):
        if shape.get("shapeId") == "corrected-7x8-03":
            continue
        parsed = build_slots_from_shape(shape)
        shapes[parsed[2]] = parsed
        lengths.update(len(slot.cells) for slot in parsed[5])

    indexes, metadata, rescue_answers, recognized_current_answers = (
        strict_construction_indexes(
            lengths, args.rescue_file, args.minimum_zipf,
            args.minimum_constructor_score,
        )
    )
    already_tested = set() if args.include_prior_deep else prior_deep_keys(args.deep_dir)
    placements = ordered_remaining_placements(scan, already_tested)
    parameters = {
        "cacheVersion": CACHE_VERSION,
        "secondsPerPlacement": args.seconds_per_placement,
        "solutionLimit": args.solution_limit,
        "minimumCurrentAnswers": args.minimum_current_answers,
        "minimumZipf": args.minimum_zipf,
        "minimumConstructorScore": args.minimum_constructor_score,
        "properNames": "human-reviewed-only",
        "finiteVerbs": "forbidden",
        "captureFailurePatterns": True,
        "includePriorDeep": args.include_prior_deep,
    }
    signature = input_digest(
        [args.scan, args.shape_file, args.rescue_file], parameters
    )
    previous_results = []
    if args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        if previous.get("inputDigest") == signature:
            previous_results = list(previous.get("results", []))
    completed = {item["placementKey"] for item in previous_results}
    placements = [
        item for item in placements
        if placement_key(item["shapeId"], item["anchor"], item["slotIndex"])
        not in completed
    ]
    active_usage = answer_usage([args.reference_catalog])
    payload = {
        "version": 1,
        "kind": "motman-remaining-single-anchor-campaign",
        "inputDigest": signature,
        "catalogModified": False,
        "runtimeModified": False,
        "supabaseModified": False,
        "publicationEligible": False,
        "parameters": parameters,
        "priorDeepPlacementCount": len(already_tested),
        "scheduledPlacementCount": len(ordered_remaining_placements(scan, already_tested)),
        "recognizedCurrentAnswerCount": len(recognized_current_answers),
        "recognizedCurrentAnswers": sorted(recognized_current_answers),
        "reviewedRescueAnswerCount": len(rescue_answers),
        "results": previous_results,
        "candidate": None,
        "status": "running",
    }

    for offset, placement in enumerate(placements):
        shape_id = str(placement["shapeId"])
        anchor = str(placement["anchor"])
        slot_index = int(placement["slotIndex"])
        key = placement_key(shape_id, anchor, slot_index)
        slots = shapes[shape_id][5]
        telemetry: dict = {}
        alternatives: list[dict] = []
        solution = fill_bitset(
            slots,
            indexes,
            random.Random(args.seed + len(payload["results"]) + offset),
            None,
            answer_usage=active_usage,
            max_grammar_answers=1,
            grammar_answers=GRAMMAR_ANSWERS,
            max_seconds=args.seconds_per_placement,
            node_limit=20_000_000,
            require_image=False,
            fixed_answers={slot_index: anchor},
            required_answer_pool=recognized_current_answers,
            minimum_required_answers=args.minimum_current_answers,
            prefer_constraint_support=True,
            constraint_support_bucket_size=3,
            branching_strategy="cell",
            cell_letter_order="quality",
            quality_scores=indexes[2],
            answer_families=indexes[3],
            solution_limit=args.solution_limit,
            solution_sink=alternatives,
            explore_randomly=False,
            capture_failure_patterns=True,
            telemetry=telemetry,
        )
        result = {
            "placementKey": key,
            "shapeId": shape_id,
            "anchor": anchor,
            "slotIndex": slot_index,
            "rootMinimumRemainingDomain": placement.get("minimumRemainingDomain"),
            "rootDomainFlexibility": placement.get("domainFlexibility"),
            "status": "solved" if solution is not None else telemetry.get("reason"),
            "telemetry": telemetry,
            "alternativeCount": len(alternatives),
            "answers": (
                {str(index): answer for index, answer in sorted(solution.items())}
                if solution is not None else {}
            ),
            "currentAnswers": (
                sorted(set(solution.values()) & recognized_current_answers)
                if solution is not None else []
            ),
            "rescueAnswers": (
                sorted(set(solution.values()) & rescue_answers)
                if solution is not None else []
            ),
            "answerMetadata": (
                {answer: metadata.get(answer, {}) for answer in solution.values()}
                if solution is not None else {}
            ),
        }
        payload["results"].append(result)
        print(json.dumps({
            "progress": f"{len(payload['results'])}/{payload['scheduledPlacementCount']}",
            "placementKey": key,
            "status": result["status"],
            "nodes": telemetry.get("nodes"),
            "elapsedSeconds": telemetry.get("elapsedSeconds"),
            "currentAnswers": result["currentAnswers"],
        }, ensure_ascii=False), flush=True)
        if solution is not None:
            payload["candidate"] = result
            payload["status"] = "candidate-found-pending-editorial-audit"
            write_checkpoint(args.output, payload)
            return 0
        write_checkpoint(args.output, payload)

    payload["status"] = (
        "complete-no-candidate"
        if all(item["status"] == "infeasible" for item in payload["results"])
        else "complete-with-cutoffs"
    )
    write_checkpoint(args.output, payload)
    print(json.dumps({
        "status": payload["status"],
        "evaluated": len(payload["results"]),
        "scheduled": payload["scheduledPlacementCount"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2), flush=True)
    return 2 if payload["status"] != "candidate-found-pending-editorial-audit" else 0


if __name__ == "__main__":
    raise SystemExit(main())
