"""Search geometry and vocabulary together instead of optimizing masks blindly."""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import generate_grid_catalog as generator
from cp_sat_grid_filler import fill_cp_sat
from optimize_grid_shapes import optimize
from placement_lexicon import build_placement_index


ROOT = Path(__file__).resolve().parents[1]


def target_mix(level: str, count: int) -> dict[str, int]:
    ratios = {
        "easy": (0.70, 0.30, 0.00),
        "normal": (0.20, 0.65, 0.15),
        "hard": (0.10, 0.30, 0.60),
    }[level]
    easy = round(count * ratios[0])
    normal = round(count * ratios[1])
    return {"easy": easy, "normal": normal, "hard": count - easy - normal}


def audience_index(
    level: str,
    minimum_frequency: float,
    source: str,
    *,
    canonical_forms_only: bool = False,
):
    if source in {"publishable", "reviewable"}:
        return generator.build_index(
            generator.load_entries(include_review_staging=source == "reviewable"),
            min_frequency=minimum_frequency, difficulty=level,
            allow_dictionary_derived=source == "reviewable",
            strict_declared_difficulty=level == "easy",
        )
    indexes = list(build_placement_index(generator, level))
    by_length, position_index, frequency, concept_group, semantic_conflicts, word_difficulty, image_answers = indexes
    minimum_score = math.log1p(minimum_frequency) + 1
    allowed = {
        answer for answer, score in frequency.items()
        if score >= minimum_score
    }
    by_length = {
        length: [answer for answer in answers if answer in allowed]
        for length, answers in by_length.items()
    }
    indexes = [
        by_length,
        position_index,
        {answer: value for answer, value in frequency.items() if answer in allowed},
        {answer: value for answer, value in concept_group.items() if answer in allowed},
        {answer: value for answer, value in semantic_conflicts.items() if answer in allowed},
        {answer: value for answer, value in word_difficulty.items() if answer in allowed},
        image_answers & allowed,
    ]
    if canonical_forms_only:
        lexique = json.loads(
            (ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8")
        )["entries"]
        part_of_speech = {
            entry["answer"]: entry.get("partOfSpeech") for entry in lexique
        }
        reviewed_central = {
            entry["answer"] for entry in generator.load_entries()
            if entry.get("generatorEligible") is True
            and entry.get("canonicalForGenerator") is True
        }
        canonical = {
            answer for answers in by_length.values() for answer in answers
            if part_of_speech.get(answer) in {"NOM", "ADJ", "ADV"}
        }
        # Central editorial approval is stronger evidence than a missing or
        # imperfect Lexique POS tag.  Keep every already-filtered central
        # answer in the placement index.
        canonical.update(
            answer for answers in by_length.values() for answer in answers
            if answer in reviewed_central
        )
        # A VER tag alone is not enough: Lexique also contains conjugated
        # forms such as SAIS.  Only infinitives are acceptable as unattended
        # placement candidates; any other form needs an explicit editorial
        # pair instead of being smuggled in by geometry.
        lexical_by_answer = {entry["answer"]: entry for entry in lexique}
        canonical.update(
            answer for answers in by_length.values() for answer in answers
            if part_of_speech.get(answer) == "VER"
            and str(lexical_by_answer.get(answer, {}).get("verbInfo", "")).startswith("inf")
        )
        # Two-letter entries already come from the manually reviewed closed
        # list; Lexique does not consistently carry their POS metadata.
        canonical.update(by_length.get(2, []))
        indexes = [
            {
                length: [answer for answer in answers if answer in canonical]
                for length, answers in indexes[0].items()
            },
            indexes[1],
            *[
                {answer: value for answer, value in mapping.items() if answer in canonical}
                for mapping in indexes[2:6]
            ],
            indexes[6] & canonical,
        ]
    # The easy placement index is already built from school-attested lemmas
    # and their familiar inflected forms.  Filtering it a second time against
    # the lemma-only index used to discard useful forms such as plurals and
    # ordinary conjugations, making otherwise sound masks falsely infeasible.
    if level == "easy":
        return tuple(indexes)
    return tuple(indexes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", choices=("easy", "normal", "hard"), default="easy")
    parser.add_argument("--attempts", type=int, default=100)
    parser.add_argument("--target", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--columns", type=int, default=9)
    parser.add_argument("--rows", type=int, default=10)
    parser.add_argument("--minimum-frequency", type=float, default=5)
    parser.add_argument("--shape-timeout", type=float, default=.75)
    parser.add_argument("--fill-timeout", type=float, default=1.5)
    parser.add_argument("--minimum-visible-clues", type=int)
    parser.add_argument("--maximum-visible-clues", type=int)
    parser.add_argument("--maximum-length-two", type=int)
    parser.add_argument("--maximum-answer-length", type=int, default=8)
    parser.add_argument("--minimum-doubles", type=int, default=0)
    parser.add_argument("--maximum-doubles", type=int, default=6)
    parser.add_argument("--maximum-adjacent-pairs", type=int, default=3)
    parser.add_argument("--maximum-top-border-clues", type=int)
    parser.add_argument("--maximum-left-border-clues", type=int)
    parser.add_argument("--maximum-border-adjacent-pairs", type=int)
    parser.add_argument("--maximum-border-clue-run", type=int)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--index-source", choices=("placement", "publishable", "reviewable"), default="reviewable")
    parser.add_argument("--solver", choices=("bitset", "cp-sat"), default="cp-sat")
    parser.add_argument("--without-audience-mix", action="store_true")
    parser.add_argument("--canonical-forms-only", action="store_true")
    parser.add_argument("--exclude-reference-pilot", action="store_true")
    parser.add_argument("--maximum-shape-overlap", type=int)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    indexes = audience_index(
        args.level,
        args.minimum_frequency,
        args.index_source,
        canonical_forms_only=args.canonical_forms_only,
    )
    unavailable_answers = set()
    reference_pilot = ROOT / "src/data/grid-generation-handcrafted/reference.pilot.json"
    calibration_pilot = ROOT / "output/quality/difficulty-calibration-candidates.json"
    if args.exclude_reference_pilot:
        for source in (reference_pilot, calibration_pilot):
            if not source.exists():
                continue
            source_document = json.loads(source.read_text(encoding="utf-8"))
            unavailable_answers.update(
                word["answer"]
                for grid in source_document.get("grids", [])
                for word in grid.get("words", [])
            )
    previous_shapes = []
    if args.maximum_shape_overlap is not None:
        shape_sources = [
            reference_pilot,
            calibration_pilot,
        ]
        for source in shape_sources:
            if not source.exists():
                continue
            source_document = json.loads(source.read_text(encoding="utf-8"))
            previous_shapes.extend(
                {tuple(cell) for cell in grid.get("clueCells", [])}
                for grid in source_document.get("grids", [])
            )
    accepted = []
    rejection_counts = defaultdict(int)
    minimum_frame = args.columns + args.rows - 2
    for attempt in range(args.attempts):
        minimum_visible = args.minimum_visible_clues or minimum_frame + 3
        maximum_visible = args.maximum_visible_clues or min(minimum_frame + 12, 30)
        visible_clues = rng.randint(minimum_visible, maximum_visible)
        position_penalties = {
            (row, col): rng.randint(0, 3)
            for row in range(1, args.rows) for col in range(1, args.columns)
        }
        shape = optimize(
            timeout=args.shape_timeout,
            seed=args.seed * 10_000 + attempt,
            visible_clue_cells=visible_clues,
            minimum_double_clues=args.minimum_doubles,
            maximum_double_clues=args.maximum_doubles,
            maximum_adjacent_pairs=args.maximum_adjacent_pairs,
            maximum_top_border_clues=args.maximum_top_border_clues,
            maximum_left_border_clues=args.maximum_left_border_clues,
            maximum_border_adjacent_pairs=args.maximum_border_adjacent_pairs,
            maximum_border_clue_run=args.maximum_border_clue_run,
            maximum_length_two_answers=args.maximum_length_two,
            only_direct_arrows=True,
            required_lengths=(),
            require_length_bands=True,
            enforce_length_balance=False,
            enforce_clue_spacing=True,
            full_definition_frame=False,
            columns=args.columns,
            rows=args.rows,
            maximum_answer_length=args.maximum_answer_length,
            position_penalties=position_penalties,
            previous_shapes=previous_shapes,
            maximum_shape_overlap=args.maximum_shape_overlap,
        )
        if not shape:
            rejection_counts["geometry-infeasible"] += 1
            continue
        fingerprint = tuple(map(tuple, shape["clueCells"]))
        if any(tuple(map(tuple, item["clueCells"])) == fingerprint for item in accepted):
            rejection_counts["duplicate-shape"] += 1
            continue
        slots = [generator.Slot(
            slot["direction"], tuple(slot["clue"]), tuple(map(tuple, slot["cells"])),
            slot["arrow"],
        ) for slot in shape["slots"]]
        telemetry = {}
        fill = fill_cp_sat if args.solver == "cp-sat" else generator.fill_bitset
        fill_options = {
            "max_seconds": args.fill_timeout,
            "require_image": False,
            "grammar_answers": generator.GRAMMAR_ANSWERS,
            "max_grammar_answers": 2,
            "telemetry": telemetry,
            "unavailable_answers": unavailable_answers,
        }
        if args.solver == "bitset":
            fill_options["node_limit"] = 150_000
        mix = None if args.without_audience_mix else target_mix(args.level, len(slots))
        answers = fill(slots, indexes, rng, mix, **fill_options)
        if answers is None:
            rejection_counts[f"fill-{telemetry.get('reason', 'failed')}"] += 1
            continue
        shape["sampleAnswers"] = [answers[index] for index in sorted(answers)]
        shape["fillTelemetry"] = telemetry
        shape["targetDifficultyMix"] = mix
        accepted.append(shape)
        print(json.dumps({
            "status": "accepted", "attempt": attempt + 1,
            "accepted": len(accepted), "metrics": shape["metrics"],
        }), flush=True)
        if len(accepted) >= args.target:
            break

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 1,
        "level": args.level,
        "columns": args.columns,
        "rows": args.rows,
        "minimumFrequency": args.minimum_frequency,
        "indexSource": args.index_source,
        "solver": args.solver,
        "attempted": args.attempts,
        "accepted": accepted,
        "rejectionCounts": dict(sorted(rejection_counts.items())),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "finished", "accepted": len(accepted),
        "rejectionCounts": dict(sorted(rejection_counts.items())),
        "output": str(output),
    }), flush=True)


if __name__ == "__main__":
    main()
