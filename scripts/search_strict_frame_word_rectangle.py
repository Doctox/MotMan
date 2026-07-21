#!/usr/bin/env python3
"""Strict editorial 7x8 word-rectangle search with prefix-trie telemetry."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from wordfreq import zipf_frequency

from build_compact_7x8_review import family_key
from editorial_fill_quality import answer_usage
from search_compact_grid_pilot import (
    GRAMMAR_ANSWERS,
    PILOT_CONCEPT_FAMILY_OVERRIDES,
    PILOT_REVIEWED_LONG,
    PILOT_REVIEWED_NATURAL_FORMS,
    excluded_answers,
    load_reference_solutions,
    normalized,
    rotation_cooldown_usage,
)
from search_compact_word_rectangle import grid_payload
from word_rectangle_filler import RectangleEntry, fill_word_rectangle


ROOT = Path(__file__).resolve().parents[1]
WORDLIST = ROOT / "src/data/fill.wordlist.large.json.gz"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
IMAGES = ROOT / "src/data/crossword.images-reviewed.json"
ALGORITHM_VERSION = 2
PILOT_REVIEWED_RECTANGLE = (
    PILOT_REVIEWED_LONG | PILOT_REVIEWED_NATURAL_FORMS
)
REVIEWED_IMAGE_NUCLEUS = {
    "ANANAS", "BALLON", "BANANE", "BATEAU", "CADEAU", "CAMERA", "CAMION",
    "CANARD", "CERISE", "CHAISE", "CHEVAL", "CITRON", "CRAYON", "FRAISE",
    "MAISON", "MIROIR", "OISEAU", "SOLEIL", "TOMATE", "VALISE",
    "ABEILLE", "BALEINE", "CAROTTE", "CERVEAU", "CHAPEAU", "CHATEAU",
    "CISEAUX", "DAUPHIN", "FANTOME", "FENETRE", "FROMAGE", "GUITARE",
    "HOPITAL", "MARTEAU", "OREILLE", "PIEUVRE", "PLANETE", "POISSON",
    "TAMBOUR", "VOITURE", "COLISEE",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=45.0)
    parser.add_argument("--node-limit", type=int, default=100_000_000)
    parser.add_argument("--solution-limit", type=int, default=8)
    parser.add_argument("--minimum-zipf", type=float, default=2.0)
    parser.add_argument("--minimum-constructor-score", type=float, default=5.0)
    parser.add_argument("--minimum-familiarity-zipf", type=float, default=2.8)
    parser.add_argument("--max-unfamiliar-answers", type=int, default=3)
    parser.add_argument("--maximum-grammar-answers", type=int, default=1)
    parser.add_argument("--minimum-images", type=int, default=0)
    parser.add_argument("--seed", type=int, default=801000)
    parser.add_argument(
        "--orientation", choices=("auto", "row-first", "column-first"), default="auto"
    )
    parser.add_argument("--explore-randomly", action="store_true")
    parser.add_argument("--pilot-safe-short-only", action="store_true")
    parser.add_argument("--reference-catalog", type=Path, action="append", default=[])
    parser.add_argument("--avoid-fill", type=Path, action="append", default=[])
    parser.add_argument("--minimum-solution-distance", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _signature_inputs(
    args: argparse.Namespace, *, include_search_budget: bool
) -> dict:
    files = [
        WORDLIST,
        BLACKLIST,
        IMAGES,
        ROOT / "scripts/word_rectangle_filler.py",
        ROOT / "scripts/search_strict_frame_word_rectangle.py",
        *args.reference_catalog,
        *args.avoid_fill,
    ]
    configuration = {
        "minimumZipf": args.minimum_zipf,
        "minimumConstructorScore": args.minimum_constructor_score,
        "minimumFamiliarityZipf": args.minimum_familiarity_zipf,
        "maxUnfamiliarAnswers": args.max_unfamiliar_answers,
        "maximumGrammarAnswers": args.maximum_grammar_answers,
        "minimumImages": args.minimum_images,
        "seed": args.seed,
        "orientation": args.orientation,
        "exploreRandomly": args.explore_randomly,
        "pilotSafeShortOnly": args.pilot_safe_short_only,
        "solutionLimit": args.solution_limit,
        "minimumSolutionDistance": args.minimum_solution_distance,
    }
    if include_search_budget:
        configuration.update({
            "maxSeconds": args.seconds,
            "nodeLimit": args.node_limit,
        })
    return {
        "algorithmVersion": ALGORITHM_VERSION,
        "signatureKind": (
            "terminal-search-v1" if include_search_budget
            else "proved-root-checkpoint-v1"
        ),
        "configuration": configuration,
        "files": {
            str(path.resolve().relative_to(ROOT.resolve())): file_digest(path)
            for path in files
        },
    }


def _signature_digest(inputs: dict) -> str:
    encoded = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def cache_signature(args: argparse.Namespace) -> tuple[str, dict]:
    inputs = _signature_inputs(args, include_search_budget=True)
    return _signature_digest(inputs), inputs


def checkpoint_signature(
    args: argparse.Namespace, *, domain_order_digest: str | None = None
) -> tuple[str, dict]:
    """Sign every search/domain input except the time and node budgets."""

    inputs = _signature_inputs(args, include_search_budget=False)
    inputs["domainOrderDigest"] = domain_order_digest
    return _signature_digest(inputs), inputs


def ordered_domain_digest(
    horizontal: list[RectangleEntry], vertical: list[RectangleEntry]
) -> str:
    """Fingerprint the exact ordered values that influence traversal/pruning."""

    domain = {
        "horizontal": [
            {
                "answer": entry.answer,
                "family": entry.family,
                "quality": entry.quality,
                "zipf": entry.zipf,
                "unfamiliar": entry.unfamiliar,
                "grammar": entry.grammar,
                "activeUses": entry.active_uses,
                "hasImage": entry.has_image,
            }
            for entry in horizontal
        ],
        "vertical": [
            {
                "answer": entry.answer,
                "family": entry.family,
                "quality": entry.quality,
                "zipf": entry.zipf,
                "unfamiliar": entry.unfamiliar,
                "grammar": entry.grammar,
                "activeUses": entry.active_uses,
                "hasImage": entry.has_image,
            }
            for entry in vertical
        ],
    }
    return _signature_digest(domain)


def load_domain(args: argparse.Namespace) -> tuple[list[RectangleEntry], list[RectangleEntry], dict]:
    blacklist_document = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    excluded = excluded_answers([])
    excluded_families = {family_key(answer) for answer in excluded}
    usage = answer_usage(args.reference_catalog)
    for answer, count in rotation_cooldown_usage(blacklist_document).items():
        usage[answer] = max(usage[answer], count)
    image_document = json.loads(IMAGES.read_text(encoding="utf-8"))
    image_answers = {
        normalized(str(item.get("answer", "")))
        for item in image_document.get("entries", [])
    } | REVIEWED_IMAGE_NUCLEUS

    with gzip.open(WORDLIST, "rt", encoding="utf-8") as stream:
        raw_entries = json.load(stream).get("entries", [])
    raw_by_answer = {}
    for item in raw_entries:
        answer = normalized(str(item.get("answer", "")))
        if answer and answer not in raw_by_answer:
            raw_by_answer[answer] = item

    admitted: dict[str, RectangleEntry] = {}

    def add_entry(answer: str, item: dict | None, reviewed: bool = False) -> None:
        if len(answer) not in {6, 7} or answer in admitted or answer in excluded:
            return
        item = item or {}
        lemma = normalized(str(item.get("lemma") or answer))
        family = PILOT_CONCEPT_FAMILY_OVERRIDES.get(answer, family_key(lemma))
        if family in excluded_families:
            return
        spelling = str(item.get("spelling") or answer.lower())
        zipf = float(zipf_frequency(spelling, "fr"))
        constructor = float(item.get("constructorScore") or 0.0)
        if not reviewed and (
            not item.get("attestedCommonForm", False)
            or zipf < args.minimum_zipf
            or constructor < args.minimum_constructor_score
            or (
                item.get("partOfSpeech") == "verb"
                and item.get("formType") != "lemma"
            )
        ):
            return
        if reviewed:
            constructor = max(constructor, 65.0)
            zipf = max(zipf, 3.0)
        active_uses = int(usage.get(answer, 0))
        has_image = answer in image_answers
        quality = (
            constructor
            + 5.0 * zipf
            - min(30.0, 12.0 * active_uses)
            + (8.0 if has_image else 0.0)
        )
        admitted[answer] = RectangleEntry(
            answer=answer,
            family=family,
            quality=quality,
            zipf=zipf,
            unfamiliar=(
                zipf < args.minimum_familiarity_zipf
                and answer not in PILOT_REVIEWED_RECTANGLE
            ),
            grammar=answer in GRAMMAR_ANSWERS,
            active_uses=active_uses,
            has_image=has_image,
            metadata={
                "spelling": spelling,
                "lemma": lemma,
                "constructorScore": constructor,
                "wordfreqZipf": zipf,
                "partOfSpeech": item.get("partOfSpeech"),
                "formType": "editorial-reviewed" if reviewed else item.get("formType"),
                "sourceFrequency": item.get("sourceFrequency"),
                "schoolFrequency": item.get("schoolFrequency"),
            },
        )

    for answer, item in raw_by_answer.items():
        add_entry(answer, item)
    if args.pilot_safe_short_only:
        for answer in PILOT_REVIEWED_RECTANGLE:
            add_entry(answer, raw_by_answer.get(answer), reviewed=True)

    horizontal = sorted(
        (entry for entry in admitted.values() if len(entry.answer) == 6),
        key=lambda entry: entry.answer,
    )
    vertical = sorted(
        (entry for entry in admitted.values() if len(entry.answer) == 7),
        key=lambda entry: entry.answer,
    )
    stats = {
        "excludedAnswerCount": len(excluded),
        "excludedFamilyCount": len(excluded_families),
        "activeReferenceAnswerCount": len(usage),
        "candidateCounts": {"6": len(horizontal), "7": len(vertical)},
        "unfamiliarCandidateCounts": {
            "6": sum(entry.unfamiliar for entry in horizontal),
            "7": sum(entry.unfamiliar for entry in vertical),
        },
        "imagePotentialCandidateCounts": {
            "6": sum(entry.has_image for entry in horizontal),
            "7": sum(entry.has_image for entry in vertical),
        },
    }
    return horizontal, vertical, stats


def load_cached_payload(
    output: Path, expected_cache_key: str, *, force: bool = False
) -> dict | None:
    """Reuse a deterministic terminal run only when every signed input matches."""

    if force or not output.exists():
        return None
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        payload.get("kind") != "compact-7x8-strict-word-rectangle-search"
        or payload.get("cacheKey") != expected_cache_key
        or not isinstance(payload.get("solverTelemetry"), dict)
    ):
        return None
    return payload


def load_root_checkpoint(
    output: Path, expected_checkpoint_key: str, *, force: bool = False
) -> dict | None:
    """Load only roots and solutions explicitly proved by a compatible run."""

    if force or not output.exists():
        return None
    try:
        payload = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    checkpoint = payload.get("rootCheckpoint")
    if (
        payload.get("kind") != "compact-7x8-strict-word-rectangle-search"
        or not isinstance(checkpoint, dict)
        or checkpoint.get("version") != 1
        or checkpoint.get("checkpointKey") != expected_checkpoint_key
        or not isinstance(checkpoint.get("completedRootBranches"), list)
        or not all(
            isinstance(item, str)
            for item in checkpoint.get("completedRootBranches", [])
        )
        or not isinstance(checkpoint.get("provenSolutions"), list)
    ):
        return None
    return checkpoint


def write_payload_atomic(output: Path, payload: dict) -> None:
    """Replace an output only after the complete checkpoint JSON is durable."""

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(output)


def main() -> int:
    args = parse_args()
    signature, signature_inputs = cache_signature(args)
    cached = load_cached_payload(args.output, signature, force=args.force)
    if cached is not None:
        print(json.dumps({
            "complete": bool(cached.get("complete")),
            "alternativeCount": int(cached.get("alternativeCount") or 0),
            "answers": [item["answer"] for item in cached.get("answers", [])],
            "telemetry": cached["solverTelemetry"],
            "cacheKey": signature,
            "cacheHit": True,
            "output": str(args.output),
        }, ensure_ascii=False, indent=2))
        return 0 if cached.get("complete") else 2

    horizontal, vertical, domain_stats = load_domain(args)
    root_checkpoint_key, root_checkpoint_inputs = checkpoint_signature(
        args,
        domain_order_digest=ordered_domain_digest(horizontal, vertical),
    )
    previous_checkpoint = load_root_checkpoint(
        args.output, root_checkpoint_key, force=args.force
    )
    reference_solutions = load_reference_solutions(args.avoid_fill)
    result = fill_word_rectangle(
        horizontal,
        vertical,
        row_count=7,
        column_count=6,
        seed=args.seed,
        max_seconds=args.seconds,
        node_limit=args.node_limit,
        solution_limit=args.solution_limit,
        max_unfamiliar_answers=args.max_unfamiliar_answers,
        max_grammar_answers=args.maximum_grammar_answers,
        minimum_images=args.minimum_images,
        reference_solutions=reference_solutions,
        minimum_solution_distance=args.minimum_solution_distance,
        orientation=args.orientation,
        explore_randomly=args.explore_randomly,
        completed_root_branches=(
            previous_checkpoint.get("completedRootBranches", [])
            if previous_checkpoint else []
        ),
        initial_solutions=(
            previous_checkpoint.get("provenSolutions", [])
            if previous_checkpoint else []
        ),
    )
    result["telemetry"]["cacheHit"] = False
    result["telemetry"]["rootCheckpointHit"] = previous_checkpoint is not None
    payload = {
        "version": 2,
        "kind": "compact-7x8-strict-word-rectangle-search",
        "columns": 7,
        "rows": 8,
        "sourceShapeId": "pilot-7x8-strict-01",
        "catalogModified": False,
        "publicationEligible": False,
        "complete": result["complete"],
        "minimumZipf": args.minimum_zipf,
        "minimumConstructorScore": args.minimum_constructor_score,
        "minimumFamiliarityZipf": args.minimum_familiarity_zipf,
        "maxUnfamiliarAnswers": args.max_unfamiliar_answers,
        "maximumGrammarAnswers": args.maximum_grammar_answers,
        "minimumImages": args.minimum_images,
        "domain": domain_stats,
        "cacheKey": signature,
        "cacheInputs": signature_inputs,
        "rootCheckpoint": {
            "version": 1,
            "checkpointKey": root_checkpoint_key,
            "checkpointInputs": root_checkpoint_inputs,
            "completedRootBranches": result["checkpoint"]["completedRootBranches"],
            "provenSolutions": result["checkpoint"]["provenSolutions"],
        },
        "solverTelemetry": result["telemetry"],
        "alternativeCount": len(result["solutions"]),
        "alternatives": [
            {
                "answers": solution["slotAnswers"],
                "rows": solution["rows"],
                "columns": solution["columns"],
                "quality": solution["quality"],
                "metrics": solution["metrics"],
            }
            for solution in result["solutions"]
        ],
        "answers": [],
    }
    if result["solutions"]:
        best = result["solutions"][0]
        metadata = {
            entry.answer: dict(entry.metadata or {})
            for entry in [*horizontal, *vertical]
        }
        payload.update(grid_payload(best["rows"], best["columns"], metadata))
        payload["sourceShapeId"] = "pilot-7x8-strict-01"
        payload["complete"] = True
        payload["catalogModified"] = False
        payload["publicationEligible"] = False
        payload["cacheKey"] = signature
        payload["cacheInputs"] = signature_inputs
        payload["rootCheckpoint"] = {
            "version": 1,
            "checkpointKey": root_checkpoint_key,
            "checkpointInputs": root_checkpoint_inputs,
            "completedRootBranches": result["checkpoint"]["completedRootBranches"],
            "provenSolutions": result["checkpoint"]["provenSolutions"],
        }
        payload["domain"] = domain_stats
        payload["solverTelemetry"] = result["telemetry"]
        payload["alternativeCount"] = len(result["solutions"])
        payload["alternatives"] = [
            {
                "answers": solution["slotAnswers"],
                "rows": solution["rows"],
                "columns": solution["columns"],
                "quality": solution["quality"],
                "metrics": solution["metrics"],
            }
            for solution in result["solutions"]
        ]

    write_payload_atomic(args.output, payload)
    print(json.dumps({
        "complete": payload["complete"],
        "alternativeCount": payload["alternativeCount"],
        "answers": [item["answer"] for item in payload.get("answers", [])],
        "telemetry": payload["solverTelemetry"],
        "cacheKey": signature,
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if payload["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
