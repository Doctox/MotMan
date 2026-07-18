"""Search one clean 9x10 reference grid without recycling active answers.

Geometry and vocabulary are searched together.  Every candidate has the full
top/left definition frame, direct arrows, no orphan letter, and exactly one
deliberately selected two-letter answer.  The solver only sees sourced entries
from the reviewed central corpus; Lexique rescue forms are excluded.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as generator  # noqa: E402
from craft_flexible_common_grid import CURATED_TWO_LETTER  # noqa: E402
from cp_sat_grid_filler import fill_cp_sat  # noqa: E402
from grid_topology import audit_grid_topology  # noqa: E402
from optimize_grid_shapes import optimize  # noqa: E402
from propose_standard_crossing_drafts import as_grid  # noqa: E402


MUSIC_NOTES = {"DO", "RE", "MI", "FA", "SOL", "LA", "SI"}
OWNER_ROTATION_BLOCK = {
    "AMAS", "AN", "ANS", "BOL", "FER", "ILE", "ILES", "MER", "MERS", "SEL",
}
LEGACY_IMAGE_CORPUS = ROOT / "src/data/crossword.corpus.json"


def answer_family(answer: str) -> str:
    if len(answer) >= 4 and answer.endswith(("S", "X")):
        return answer[:-1]
    return answer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--seed", type=int, default=650_000)
    parser.add_argument("--shape-seconds", type=float, default=1.5)
    parser.add_argument("--fill-seconds", type=float, default=3)
    parser.add_argument("--solver", choices=("bitset", "cp-sat"), default="bitset")
    parser.add_argument(
        "--branching-strategy", choices=("slot", "cell"), default="slot",
        help="Bitset solver branching mode; cell groups candidates by crossing letter.",
    )
    parser.add_argument("--minimum-visible-clues", type=int, default=22)
    parser.add_argument("--maximum-visible-clues", type=int, default=26)
    parser.add_argument("--maximum-shape-overlap", type=int, default=22)
    parser.add_argument(
        "--maximum-adjacent-pairs", type=int, default=3,
        help="Préférence visuelle : plafond de paires de cases-définition adjacentes.",
    )
    parser.add_argument(
        "--maximum-crossing-letter-cells", type=int,
        help=(
            "Plafond optionnel de lettres appartenant aux deux directions. "
            "Un plafond plus bas facilite un craft riche en images sans créer d'orphelins."
        ),
    )
    parser.add_argument("--crossing-cell-penalty", type=int, default=0)
    parser.add_argument(
        "--maximum-existing-uses", type=int, default=1,
        help=(
            "Exclude answers already used this many times. Set to 2 to allow "
            "a word seen exactly once while keeping recurring words blocked."
        ),
    )
    parser.add_argument(
        "--maximum-noncanonical-source-answers", type=int, default=8,
        help=(
            "Open the complete reviewed central corpus to the solver, but keep "
            "at most this many source-backed press answers outside the safe "
            "lemma subset in an accepted grid. Every such answer still requires "
            "manual review. Set to 0 only for the reduced unattended subset."
        ),
    )
    parser.add_argument("--maximum-active-repeats", type=int, default=3)
    parser.add_argument(
        "--minimum-images", type=int, default=0,
        help="Require this many reviewed image clues in every accepted grid.",
    )
    parser.add_argument(
        "--include-legacy-reviewed-images", action="store_true",
        help=(
            "Merge the already reviewed Twemoji entries from crossword.corpus.json "
            "into the placement pool. This restores concrete image answers that "
            "the central canonical merge currently hides behind a text-only pair."
        ),
    )
    parser.add_argument(
        "--reserve-image-slots", action="store_true",
        help=(
            "Réserve avant remplissage les emplacements les moins croisés pour les "
            "indices-images ; recommandé à partir de 4 images."
        ),
    )
    parser.add_argument(
        "--soft-image-preference", action="store_true",
        help=(
            "Prefer fresh reviewed image answers during ordinary filling, then "
            "apply --minimum-images only as an acceptance gate. This prevents "
            "the image quota from forcing weak crossing answers."
        ),
    )
    parser.add_argument("--required-short-answer", default="")
    parser.add_argument("--maximum-short-answers", type=int, choices=(0, 1, 2, 3), default=2)
    parser.add_argument(
        "--maximum-answers-2-to-4", type=int,
        help=(
            "Préférence optionnelle : maximum total de réponses de 2, 3 ou 4 lettres. "
            "Laisser vide pour ne pas transformer cette préférence en invariant."
        ),
    )
    parser.add_argument(
        "--exclude-answer", action="append", default=[],
        help="Answer forbidden from this batch (repeatable).",
    )
    parser.add_argument(
        "--exclude-from", action="append", default=[], type=Path,
        help="Grid JSON added to the no-repeat baseline (repeatable).",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "output/quality/low-short-reference-prototype.json",
    )
    args = parser.parse_args()

    active = json.loads(
        (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
    )
    active_usage = Counter(
        word["answer"]
        for grid in active.get("grids", [])
        for word in grid.get("words", [])
    )
    baseline_grids = list(active.get("grids", []))
    replacement_reference_grids = []
    for raw_path in args.exclude_from:
        path = raw_path if raw_path.is_absolute() else ROOT / raw_path
        document = json.loads(path.read_text(encoding="utf-8"))
        referenced = document.get("grids", [])
        replacement_reference_grids.extend(referenced)
        baseline_grids.extend(referenced)
    baseline_usage = Counter(
        word["answer"]
        for grid in baseline_grids
        for word in grid.get("words", [])
    )
    replacement_reference_usage = Counter(
        word["answer"]
        for grid in replacement_reference_grids
        for word in grid.get("words", [])
    )
    explicit_exclusions = {
        answer.strip().upper() for answer in args.exclude_answer if answer.strip()
    }
    unavailable_families = {
        answer_family(answer) for answer, count in baseline_usage.items()
        if count >= args.maximum_existing_uses
    } | {
        answer_family(answer) for answer in replacement_reference_usage
    } | {answer_family(answer) for answer in explicit_exclusions}
    unavailable = {
        answer for answer, count in baseline_usage.items()
        if count >= args.maximum_existing_uses
    } | set(replacement_reference_usage) | MUSIC_NOTES | OWNER_ROTATION_BLOCK | explicit_exclusions
    entries = generator.load_entries()
    legacy_images_added = 0
    legacy_images_merged = 0
    if args.include_legacy_reviewed_images:
        legacy_document = json.loads(LEGACY_IMAGE_CORPUS.read_text(encoding="utf-8"))
        by_answer = {entry["answer"]: entry for entry in entries}
        for legacy in legacy_document.get("entries", []):
            if (
                not legacy.get("image")
                or legacy.get("editorialStatus") not in {"image-reviewed", "source-backed"}
                or not 2 <= len(legacy["answer"]) <= 9
            ):
                continue
            asset = ROOT / "public" / legacy["image"]["asset"].lstrip("/")
            if not asset.is_file():
                continue
            answer = legacy["answer"]
            if answer in by_answer:
                if not by_answer[answer].get("image"):
                    by_answer[answer] = {**by_answer[answer], "image": legacy["image"]}
                    legacy_images_merged += 1
            else:
                by_answer[answer] = legacy
                legacy_images_added += 1
        entries = list(by_answer.values())
    unavailable.update(
        entry["answer"] for entry in entries
        if answer_family(entry["answer"]) in unavailable_families
    )
    sources = {entry["answer"]: entry for entry in entries}
    indexes = generator.build_index(
        entries,
        excluded_answers=unavailable,
        min_frequency=0,
        difficulty="normal",
        allow_dictionary_derived=False,
    )
    lexical_entries = json.loads(
        (ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8")
    )["entries"]
    lexical_by_answer = {entry["answer"]: entry for entry in lexical_entries}

    def editorially_safe_for_unattended_fill(answer: str) -> bool:
        source = sources[answer]
        if len(answer) == 2:
            return source.get("shortAnswerApproved") is True
        if (
            source.get("editorialStatus") == "human-reviewed"
            or source.get("sourceType") in {
                "image", "dictionary", "editorial-original", "lexical-relation"
            }
            or str(source.get("sourceId", "")).startswith("jeuxdemots")
        ):
            return True
        lexical = lexical_by_answer.get(answer, {})
        if float(lexical.get("sourceFrequency", 0)) < 1.0:
            return False
        part_of_speech = lexical.get("partOfSpeech")
        lemma = lexical.get("lemma", answer)
        if part_of_speech == "NOM":
            # Regular noun plurals remain perfectly clueable; family reuse is
            # blocked separately inside and across grids.
            return True
        if part_of_speech in {"ADJ", "ADV"}:
            return answer == lemma
        if part_of_speech == "VER":
            return str(lexical.get("verbInfo", "")).startswith("inf")
        return False

    canonical_quality = {
        answer for answers in indexes[0].values() for answer in answers
        if editorially_safe_for_unattended_fill(answer)
    }
    all_indexed = {
        answer for answers in indexes[0].values() for answer in answers
    }
    quality_allowed = (
        all_indexed
        if args.maximum_noncanonical_source_answers > 0
        else canonical_quality
    )
    quality_allowed = {
        answer for answer in quality_allowed
        if len(answer) != 2 or answer in CURATED_TWO_LETTER
    }
    indexes = (
        {
            length: [answer for answer in answers if answer in quality_allowed]
            for length, answers in indexes[0].items()
        },
        None,
        {
            answer: (
                value if answer in canonical_quality else value - 100
            )
            for answer, value in indexes[2].items() if answer in quality_allowed
        },
        *[
            {answer: value for answer, value in mapping.items() if answer in quality_allowed}
            for mapping in indexes[3:6]
        ],
        indexes[6] & quality_allowed,
    )
    approved_short = set(indexes[0].get(2, []))
    expected_short = {
        entry["answer"] for entry in entries
        if entry.get("shortAnswerApproved") is True
        and entry["answer"] not in unavailable
    }
    unexpected_short = approved_short - CURATED_TWO_LETTER
    if unexpected_short:
        raise ValueError(f"Unapproved short-answer pool: {sorted(unexpected_short)}")

    previous_shapes = [
        {tuple(cell) for cell in grid.get("clueCells", [])}
        for grid in baseline_grids
    ]
    selected_answers: set[str] = set()
    selected_families: set[str] = set()
    rng = random.Random(args.seed)
    rejections: Counter[str] = Counter()
    examples: dict[str, list] = defaultdict(list)
    accepted = []

    for attempt in range(args.attempts):
        shape_seed = args.seed + attempt
        shape = optimize(
            timeout=args.shape_seconds,
            seed=shape_seed,
            visible_clue_cells=rng.randint(
                args.minimum_visible_clues, args.maximum_visible_clues
            ),
            minimum_double_clues=3,
            maximum_double_clues=8,
            maximum_adjacent_pairs=args.maximum_adjacent_pairs,
            only_direct_arrows=True,
            maximum_length_two_answers=args.maximum_short_answers,
            maximum_short_answers_2_to_4=args.maximum_answers_2_to_4,
            maximum_crossing_letter_cells=args.maximum_crossing_letter_cells,
            crossing_cell_penalty=args.crossing_cell_penalty,
            require_length_bands=True,
            enforce_length_balance=False,
            enforce_clue_spacing=False,
            enforce_interior_line_limits=True,
            # The required full top/left definition frame is itself a long
            # clue ribbon; triple/block bans only make sense for the interior.
            enforce_clue_triples=False,
            enforce_solid_clue_blocks=False,
            full_definition_frame=True,
            # Counts exclude the neutral top-left corner: eight definitions
            # across the top and nine down the left for the current 9x10 rule.
            minimum_border_clues=8,
            maximum_top_border_clues=8,
            maximum_left_border_clues=9,
            columns=9,
            rows=10,
            maximum_answer_length=9,
            short_answer_penalty=60,
            position_penalties={
                (row, col): rng.randint(0, 8)
                for row in range(1, 10)
                for col in range(1, 9)
            },
            previous_shapes=previous_shapes,
            maximum_shape_overlap=args.maximum_shape_overlap,
        )
        if shape is None:
            rejections["geometry"] += 1
            continue
        short_slots = [
            index for index, slot in enumerate(shape["slots"])
            if slot["length"] == 2
        ]
        valid_short_count = (
            len(short_slots) == 0 if args.maximum_short_answers == 0
            else 1 <= len(short_slots) <= args.maximum_short_answers
        )
        if not valid_short_count:
            rejections["short-answer-count"] += 1
            continue
        small_slots = [
            index for index, slot in enumerate(shape["slots"])
            if 2 <= slot["length"] <= 4
        ]
        if (
            args.maximum_answers_2_to_4 is not None
            and len(small_slots) > args.maximum_answers_2_to_4
        ):
            # Defensive check: the geometry optimizer already enforces this,
            # but keeping the gate here makes imported/cached shapes safe too.
            rejections["answers-2-to-4-count"] += 1
            continue

        slots = [
            generator.Slot(
                slot["direction"], tuple(slot["clue"]),
                tuple(map(tuple, slot["cells"])), slot["arrow"],
            )
            for slot in shape["slots"]
        ]
        required_image_slots: set[int] = set()
        if (
            args.reserve_image_slots
            and args.minimum_images > 0
            and not args.soft_image_preference
        ):
            cell_use = Counter(
                cell for slot in slots for cell in slot.cells
            )
            image_counts_by_length = Counter(
                len(answer) for answer in indexes[6]
            )
            preferred_direction = "across" if attempt % 2 == 0 else "down"
            eligible_image_slots = [
                index for index, slot in enumerate(slots)
                if slot.direction == preferred_direction
                and image_counts_by_length[len(slot.cells)] > 0
            ]
            rng.shuffle(eligible_image_slots)
            eligible_image_slots.sort(key=lambda index: (
                -image_counts_by_length[len(slots[index].cells)],
                sum(cell_use[cell] == 2 for cell in slots[index].cells),
                -len(slots[index].cells),
            ))
            required_image_slots = set(eligible_image_slots[:args.minimum_images])
            if len(required_image_slots) < args.minimum_images:
                rejections["insufficient-image-capable-slots"] += 1
                continue
        telemetry: dict = {}
        fill_options = {
            "unavailable_answers": unavailable | selected_answers,
            # When the policy permits a word seen exactly once, it remains a
            # last-resort crossing rescue. Fresh answers are always ordered
            # first instead of being selected at random among equals.
            "answer_usage": {
                answer: (
                    -1
                    if (
                        args.soft_image_preference
                        and answer in indexes[6]
                        and active_usage[answer] == 0
                    )
                    else active_usage[answer]
                )
                for answer in all_indexed
            },
            "grammar_answers": generator.GRAMMAR_ANSWERS,
            "max_grammar_answers": 2,
            "max_seconds": args.fill_seconds,
            "require_image": args.minimum_images > 0 and not args.soft_image_preference,
            "minimum_images": (
                0 if args.soft_image_preference else args.minimum_images
            ),
            "fixed_answers": (
                {short_slots[0]: args.required_short_answer.strip().upper()}
                if args.required_short_answer else {}
            ),
            "undesirable_answers": all_indexed - canonical_quality,
            "max_undesirable_answers": args.maximum_noncanonical_source_answers,
            "telemetry": telemetry,
            "required_image_slots": required_image_slots,
        }
        if args.solver == "bitset":
            fill_options.update({
                "node_limit": 500_000,
                "prefer_constraint_support": True,
                "constraint_support_bucket_size": 8,
                "branching_strategy": args.branching_strategy,
            })
            filler = generator.fill_bitset
        else:
            filler = fill_cp_sat
        answers = filler(
            slots, indexes, random.Random(args.seed * 10_000 + attempt), None,
            **fill_options,
        )
        if answers is None:
            reason = f"fill-{telemetry.get('reason', 'failed')}"
            rejections[reason] += 1
            if len(examples[reason]) < 3:
                examples[reason].append({
                    "attempt": attempt + 1,
                    "shapeSeed": shape_seed,
                    "shapeMetrics": shape["metrics"],
                    "shape": shape,
                    "telemetry": telemetry,
                })
            continue

        values = list(answers.values())
        active_repeats = sorted({
            answer: active_usage[answer]
            for answer in values if active_usage[answer]
        }.items())
        if len(active_repeats) > args.maximum_active_repeats:
            rejections["too-many-active-repeats"] += 1
            if len(examples["too-many-active-repeats"]) < 3:
                examples["too-many-active-repeats"].append(active_repeats)
            continue
        noncanonical = sorted(set(values) - canonical_quality)
        if len(noncanonical) > args.maximum_noncanonical_source_answers:
            rejections["too-many-noncanonical-source-answers"] += 1
            if len(examples["too-many-noncanonical-source-answers"]) < 3:
                examples["too-many-noncanonical-source-answers"].append({
                    "answers": noncanonical,
                    "count": len(noncanonical),
                })
            continue
        selected_image_answers = sorted(
            answer for answer in values if answer in indexes[6]
        )
        if len(selected_image_answers) < args.minimum_images:
            rejections["minimum-images"] += 1
            continue
        families = [answer_family(answer) for answer in values]
        if (
            len(families) != len(set(families))
            or set(families) & selected_families
        ):
            rejections["singular-plural-family"] += 1
            continue
        grid_number = len(accepted) + 1
        grid = as_grid(grid_number, shape, answers, sources, telemetry)
        grid["id"] = f"fresh-reference-review-{grid_number:02d}"
        for number, word in enumerate(grid["words"], 1):
            word["wordId"] = f"{grid['id']}:word:{number:02d}"
        # Publication blockers are structural: dimensions, declared paths,
        # crossings and orphan coverage. Dense clue layouts remain visible in
        # the human review but are no longer rejected as if they were corrupt.
        report = audit_grid_topology(grid, enforce_layout=False)
        if not report["valid"]:
            rejections["topology"] += 1
            examples["topology"].append(report["errors"][:5])
            continue
        accepted.append(grid)
        selected_answers.update(values)
        selected_families.update(families)
        previous_shapes.append({tuple(cell) for cell in grid["clueCells"]})
        if len(accepted) >= args.count:
            break

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 1,
        "kind": "owner-review-low-short-reference-prototype",
        "policy": {
            "activeAnswerRepeats": 0,
            "batchAnswerRepeats": 0,
            "musicNotes": 0,
            "maximumTwoLetterAnswersPerGrid": args.maximum_short_answers,
            "maximumAnswers2To4PerGrid": args.maximum_answers_2_to_4,
            "placementCorpus": "reviewed-central-only",
            "publication": "blocked-until-owner-review",
        },
        "seed": args.seed,
        "solver": args.solver,
        "attemptsRequested": args.attempts,
        "gridsRequested": args.count,
        "requiredShortAnswer": args.required_short_answer.strip().upper(),
        "centralCorpusAnswers": len(entries),
        "qualityEligibleAnswers": len(quality_allowed),
        "canonicalQualityAnswers": len(canonical_quality),
        "reviewedImageAnswersAvailable": len(indexes[6]),
        "legacyReviewedImagesIncluded": {
            "addedAnswers": legacy_images_added,
            "mergedIntoCanonicalAnswers": legacy_images_merged,
        },
        "minimumImagesPerGrid": args.minimum_images,
        "imageSelectionMode": (
            "soft-preference-then-acceptance-gate"
            if args.soft_image_preference else "solver-hard-constraint"
        ),
        "maximumNoncanonicalSourceAnswers": args.maximum_noncanonical_source_answers,
        "maximumExistingUses": args.maximum_existing_uses,
        "maximumActiveRepeats": args.maximum_active_repeats,
        "explicitlyExcludedAnswers": sorted(explicit_exclusions),
        "additionalBaselineFiles": [str(path) for path in args.exclude_from],
        "replacementReferenceAnswersAlwaysExcluded": sorted(replacement_reference_usage),
        "activeRepeats": (
            sorted({
                word["answer"]: active_usage[word["answer"]]
                for grid in accepted for word in grid["words"]
                if active_usage[word["answer"]]
            }.items()) if accepted else []
        ),
        "grids": accepted,
        "rejectionCounts": dict(sorted(rejections.items())),
        "rejectionExamples": dict(examples),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "accepted": len(accepted),
        "requested": args.count,
        "attempts": args.attempts,
        "output": str(output),
        "rejectionCounts": dict(sorted(rejections.items())),
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
