#!/usr/bin/env python3
"""Canonical 7×8 pilot orchestrator: shapes -> fills -> ranked staging.

This command never publishes.  It resumes from per-attempt JSON files, so a
failed or completed deterministic search is not repeated accidentally.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from enumerate_compact_7x8_shapes import enumerate_shapes
from wordfreq import zipf_frequency


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output/quality/pilot-7x8-production"
CACHE_VERSION = 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--attempts-per-shape", type=int, default=2)
    parser.add_argument("--seconds-per-attempt", type=float, default=20.0)
    parser.add_argument("--solution-limit", type=int, default=64)
    parser.add_argument("--seed", type=int, default=783000)
    parser.add_argument(
        "--lexicon",
        choices=("large", "wordfreq", "hybrid", "central"),
        default="large",
    )
    parser.add_argument("--minimum-zipf", type=float, default=2.0)
    parser.add_argument("--minimum-constructor-score", type=float, default=5.0)
    parser.add_argument("--minimum-familiarity-zipf", type=float, default=2.8)
    parser.add_argument("--max-unfamiliar-answers", type=int, default=3)
    parser.add_argument("--maximum-grammar-answers", type=int, default=1)
    parser.add_argument(
        "--minimum-images",
        type=int,
        default=4,
        help="nombre minimal de réponses disposant d'un indice-image relu",
    )
    parser.add_argument(
        "--branching-strategy", choices=("cell", "slot"), default="cell"
    )
    parser.add_argument(
        "--cell-letter-order", choices=("quality", "support"), default="quality"
    )
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="désactive le mélange par seed afin de prouver une impasse exacte",
    )
    parser.add_argument("--shape", action="append", default=[])
    parser.add_argument("--avoid-fill", type=Path, action="append", default=[])
    parser.add_argument("--minimum-solution-distance", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_lexical_metadata() -> dict[str, dict]:
    with gzip.open(ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8") as stream:
        entries = json.load(stream).get("entries", [])
    return {str(item["answer"]): item for item in entries}


def load_image_answers() -> set[str]:
    document = json.loads(
        (ROOT / "src/data/crossword.images-reviewed.json").read_text(encoding="utf-8")
    )
    return {str(item.get("answer", "")).upper() for item in document.get("entries", [])}


def rank_fill(
    answers: list[str], metadata: dict[str, dict], image_answers: set[str]
) -> tuple[float, dict]:
    rows = [metadata.get(answer, {}) for answer in answers]
    zipfs = [float(zipf_frequency(str(row.get("spelling") or answer).lower(), "fr"))
             for answer, row in zip(answers, rows)]
    constructor = [float(row.get("constructorScore") or 0.0) for row in rows]
    short_count = sum(len(answer) == 3 for answer in answers)
    inflected_count = sum(row.get("formType") == "inflected" for row in rows)
    inflected_verbs = sum(
        row.get("partOfSpeech") == "verb" and row.get("formType") != "lemma"
        for row in rows
    )
    active_repeats = sum(int(row.get("activeUses") or 0) > 0 for row in rows)
    image_count = sum(answer in image_answers for answer in answers)
    weak = sum(score < 2.5 for score in zipfs) + sum(score < 15 for score in constructor)
    score = (
        sum(constructor)
        + 8.0 * sum(zipfs)
        + 8.0 * min(image_count, 6)
        - 14.0 * short_count
        - 10.0 * inflected_count
        - 80.0 * inflected_verbs
        - 12.0 * active_repeats
        - 30.0 * weak
    )
    return round(score, 3), {
        "weakestZipf": round(min(zipfs, default=0.0), 3),
        "meanZipf": round(sum(zipfs) / max(1, len(zipfs)), 3),
        "weakestConstructorScore": round(min(constructor, default=0.0), 3),
        "threeLetterAnswers": short_count,
        "inflectedAnswers": inflected_count,
        "inflectedVerbs": inflected_verbs,
        "activeRepeatAnswers": active_repeats,
        "existingImageAnswers": image_count,
        "automaticEditorialPass": inflected_verbs == 0 and weak == 0,
    }


def candidate_key(shape_id: str, answers: list[str]) -> str:
    return shape_id + ":" + ",".join(answers)


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def attempt_signature(shape: dict, configuration: dict) -> str:
    input_files = [
        "scripts/search_compact_grid_pilot.py",
        "scripts/bitset_grid_filler.py",
        "src/data/editorial.blacklist.json",
        "src/data/grid.catalog.json",
        "src/data/crossword.images-reviewed.json",
    ]
    if configuration.get("lexicon") in {"large", "hybrid"}:
        input_files.append("src/data/fill.wordlist.large.json.gz")
    if configuration.get("lexicon") == "central":
        input_files.append("src/data/crossword.central.json.gz")
    inputs = {
        "version": CACHE_VERSION,
        "shape": {
            "shapeId": shape["shapeId"],
            "fingerprint": shape["fingerprint"],
            "pivots": shape["pivots"],
        },
        "configuration": configuration,
        "files": {
            relative: file_digest(ROOT / relative)
            for relative in input_files
        },
    }
    encoded = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def attempt_status(payload: dict) -> str:
    if payload.get("complete"):
        return "solved"
    reason = str((payload.get("solverTelemetry") or {}).get("reason") or "")
    if reason == "infeasible":
        return "dead"
    return "cutoff"


def reusable_attempt(record: dict, path: Path) -> bool:
    """Reuse an exact signed attempt without conflating cutoff and dead-end."""
    return record.get("status") in {"solved", "dead", "cutoff"} and path.is_file()


def main() -> int:
    args = parse_args()
    if not args.output_dir.is_absolute():
        args.output_dir = (ROOT / args.output_dir).resolve()
    args.avoid_fill = [
        path if path.is_absolute() else (ROOT / path).resolve()
        for path in args.avoid_fill
    ]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = args.output_dir / "attempt-cache.json"
    if cache_path.is_file():
        cache_document = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        cache_document = {"version": CACHE_VERSION, "attempts": {}}
    cache = cache_document.setdefault("attempts", {})
    shapes = enumerate_shapes()
    if args.shape:
        wanted = set(args.shape)
        shapes = [shape for shape in shapes if shape["shapeId"] in wanted]
        missing = wanted - {shape["shapeId"] for shape in shapes}
        if missing:
            raise ValueError(f"Silhouettes inconnues : {sorted(missing)}")

    attempts = []
    candidates: dict[str, dict] = {}
    metadata = load_lexical_metadata()
    image_answers = load_image_answers()
    for shape in shapes:
        shape_number = int(shape["shapeId"].rsplit("-", 1)[-1])
        for attempt_index in range(args.attempts_per_shape):
            seed = args.seed + (shape_number - 1) * 100 + attempt_index
            output = args.output_dir / f"{shape['shapeId']}-seed-{seed}.json"
            signature_configuration = {
                "seed": seed,
                "seconds": args.seconds_per_attempt,
                "solutionLimit": args.solution_limit,
                "lexicon": args.lexicon,
                "minimumZipf": args.minimum_zipf,
                "minimumConstructorScore": args.minimum_constructor_score,
                "minimumFamiliarityZipf": args.minimum_familiarity_zipf,
                "maxUnfamiliarAnswers": args.max_unfamiliar_answers,
                "maximumGrammarAnswers": args.maximum_grammar_answers,
                "minimumImages": args.minimum_images,
                "branchingStrategy": args.branching_strategy,
                "cellLetterOrder": args.cell_letter_order,
                "exploreRandomly": not args.deterministic,
                "pilotSafeShortOnly": True,
                "minimumSolutionDistance": args.minimum_solution_distance,
                "avoidFills": [
                    {"path": str(path.relative_to(ROOT)), "digest": file_digest(path)}
                    for path in args.avoid_fill
                ],
            }
            signature = attempt_signature(shape, signature_configuration)
            cached = cache.get(signature, {})
            cached_file = ROOT / str(cached.get("file") or "")
            if not cached and output.is_file():
                existing_payload = json.loads(output.read_text(encoding="utf-8"))
                cached = {
                    "status": attempt_status(existing_payload),
                    "file": str(output.relative_to(ROOT)),
                    "reason": (existing_payload.get("solverTelemetry") or {}).get("reason"),
                }
                cache[signature] = cached
                cached_file = output
            reused = (
                not args.force
                and reusable_attempt(cached, cached_file)
            )
            if reused:
                output = cached_file
            if not reused:
                command = [
                    sys.executable,
                    str(ROOT / "scripts/search_compact_grid_pilot.py"),
                    "--lexicon", args.lexicon,
                    "--minimum-zipf", str(args.minimum_zipf),
                    "--minimum-constructor-score", str(args.minimum_constructor_score),
                    "--minimum-familiarity-zipf", str(args.minimum_familiarity_zipf),
                    "--max-unfamiliar-answers", str(args.max_unfamiliar_answers),
                    "--minimum-images", str(args.minimum_images),
                    "--maximum-grammar-answers", str(args.maximum_grammar_answers),
                    "--pilot-safe-short-only",
                    "--seconds", str(args.seconds_per_attempt),
                    "--solution-limit", str(args.solution_limit),
                    "--seed", str(seed),
                    "--branching-strategy", args.branching_strategy,
                    "--cell-letter-order", args.cell_letter_order,
                    "--reference-catalog", str(ROOT / "src/data/grid.catalog.json"),
                    "--output", str(output),
                ]
                if not args.deterministic:
                    command.append("--explore-randomly")
                for path in args.avoid_fill:
                    command.extend(("--avoid-fill", str(path)))
                if args.avoid_fill:
                    command.extend((
                        "--minimum-solution-distance",
                        str(args.minimum_solution_distance),
                    ))
                for row, column in shape["pivots"]:
                    command.extend(("--pivot", f"{row},{column}"))
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                return_code = completed.returncode
            else:
                return_code = 0
            payload = json.loads(output.read_text(encoding="utf-8"))
            status = attempt_status(payload)
            cache[signature] = {
                "status": status,
                "file": str(output.relative_to(ROOT)),
                "reason": (payload.get("solverTelemetry") or {}).get("reason"),
            }
            cache_path.write_text(
                json.dumps(cache_document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            attempts.append({
                "shapeId": shape["shapeId"],
                "seed": seed,
                "reused": reused,
                "returnCode": return_code,
                "complete": payload.get("complete", False),
                "status": status,
                "inputSignature": signature,
                "alternativeCount": payload.get("alternativeCount", 0),
                "telemetry": payload.get("solverTelemetry", {}),
                "file": str(output.relative_to(ROOT)),
            })
            for record in payload.get("alternatives", []):
                by_slot = {int(index): answer for index, answer in record["answers"].items()}
                answers = [by_slot[index] for index in sorted(by_slot)]
                key = candidate_key(shape["shapeId"], answers)
                if key in candidates:
                    continue
                score, metrics = rank_fill(answers, metadata, image_answers)
                candidates[key] = {
                    "candidateId": f"pilot-fill-{len(candidates) + 1:04d}",
                    "shapeId": shape["shapeId"],
                    "pivots": shape["pivots"],
                    "seed": seed,
                    "answers": answers,
                    "solverQuality": record.get("quality"),
                    "editorialPreScore": score,
                    "metrics": metrics,
                    "publicationEligible": False,
                }

    ranked = sorted(
        candidates.values(),
        key=lambda item: (-item["editorialPreScore"], item["candidateId"]),
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    summary = {
        "version": 1,
        "kind": "motman-canonical-7x8-pilot-run",
        "catalogModified": False,
        "publicationEligible": False,
        "configuration": {
            "shapeCount": len(shapes),
            "attemptsPerShape": args.attempts_per_shape,
            "secondsPerAttempt": args.seconds_per_attempt,
            "solutionLimit": args.solution_limit,
            "baseSeed": args.seed,
            "lexicon": args.lexicon,
            "minimumAnswerLength": 3,
            "minimumFamiliarityZipf": args.minimum_familiarity_zipf,
            "maxUnfamiliarAnswers": args.max_unfamiliar_answers,
            "maximumGrammarAnswers": args.maximum_grammar_answers,
            "minimumImages": args.minimum_images,
            "branchingStrategy": args.branching_strategy,
            "cellLetterOrder": args.cell_letter_order,
            "exploreRandomly": not args.deterministic,
            "activeCatalogPolicy": "freshness-penalty",
        },
        "counts": {
            "attempts": len(attempts),
            "successfulAttempts": sum(item["complete"] for item in attempts),
            "deadAttempts": sum(item["status"] == "dead" for item in attempts),
            "cutoffAttempts": sum(item["status"] == "cutoff" for item in attempts),
            "reusedAttempts": sum(item["reused"] for item in attempts),
            "uniqueCompleteFills": len(ranked),
            "automaticEditorialPass": sum(
                item["metrics"]["automaticEditorialPass"] for item in ranked
            ),
        },
        "attempts": attempts,
        "candidates": ranked,
    }
    manifest = args.output_dir / "candidate-pool.json"
    manifest.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "manifest": str(manifest),
        **summary["counts"],
    }, ensure_ascii=False, indent=2))
    return 0 if ranked else 2


if __name__ == "__main__":
    raise SystemExit(main())
