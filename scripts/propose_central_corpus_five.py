"""Search bounded 9x10 drafts with the 9,491-pair central corpus first.

The active catalog is used as a repetition baseline.  Answers of length three
or more already active are penalised.  Lexique may rescue a bounded number of slots
when the central-only crossings are infeasible.  Output remains non-publishable
until every selected pair has been manually reviewed.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import generate_grid_catalog as generator
from grid_topology import audit_grid_topology
from optimize_grid_shapes import optimize
from propose_corpus_aware_handcrafted_five import (
    acceptable_visual_shape,
)
from propose_standard_crossing_drafts import as_grid
from search_audience_shapes import audience_index


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output/quality/central-corpus-five-drafts.json"


def acceptable_central_lengths(lengths: Counter[int]) -> bool:
    """Keep variety without reviving the old rigid per-length quotas."""
    total = sum(lengths.values())
    preferred = sum(lengths[length] for length in (5, 6, 7, 8))
    average = sum(length * count for length, count in lengths.items()) / total
    return lengths[2] <= 2 and lengths[3] <= 9 and preferred / total >= .40 and average >= 4.3


def editorial_cost(
    answers: list[str],
    sources: dict[str, dict],
    lexical_answers: set[str],
    active_usage: Counter[str],
    central_answers: set[str],
    standard_central: set[str],
) -> int:
    cost = 0
    for answer in answers:
        entry = sources[answer]
        if len(answer) >= 3:
            cost += 25 * active_usage[answer]
        if answer not in central_answers:
            cost += 100
        elif answer not in standard_central:
            cost += 12
        if answer not in lexical_answers:
            cost += 6
        frequency = float(entry.get("frequency", entry.get("sourceFrequency", 0)))
        if frequency < .5:
            cost += 6
        elif frequency < 1:
            cost += 3
        elif frequency < 2:
            cost += 1
        if len(answer) == 3:
            cost += 1
        if entry.get("sourceType") == "lexical-relation":
            cost -= 1
    return cost


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--attempts", type=int, default=80)
    parser.add_argument("--seed", type=int, default=949115)
    parser.add_argument("--shape-seconds", type=float, default=1.5)
    parser.add_argument("--fill-seconds", type=float, default=4)
    parser.add_argument("--fill-variants", type=int, default=4)
    parser.add_argument("--minimum-frequency", type=float, default=1)
    parser.add_argument("--maximum-active-long-repeats", type=int, default=5)
    parser.add_argument("--maximum-lexique-rescues", type=int, default=10)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    entries = generator.load_entries()
    central_answers = {entry["answer"] for entry in entries}
    sources = {entry["answer"]: entry for entry in entries}
    lexical_answers = {
        entry["answer"] for entry in json.loads(
            (ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8")
        )["entries"]
    }
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
        "normal", args.minimum_frequency, "placement", canonical_forms_only=True
    )
    lexical_by_answer = {
        entry["answer"]: entry for entry in json.loads(
            (ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8")
        )["entries"]
    }
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
    eligible = {answer for answers in indexes[0].values() for answer in answers}

    active = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    active_grids = active.get("grids", [])
    active_usage: Counter[str] = Counter(
        word["answer"] for grid in active_grids for word in grid.get("words", [])
    )
    active_shapes = [
        {tuple(cell) for cell in grid.get("clueCells", [])}
        for grid in active_grids
    ]
    selected_shapes: list[set[tuple[int, int]]] = []
    selected_answers: set[str] = set()
    search_usage = active_usage.copy()
    for answers in indexes[0].values():
        for answer in answers:
            if answer not in central_answers:
                search_usage[answer] += 4
            elif answer not in standard_central:
                search_usage[answer] += 2
    accepted = []
    rejection_counts: Counter[str] = Counter()
    for attempt in range(args.attempts):
        attempt_rng = random.Random(args.seed + attempt * 101)
        visible_clues = 20 + attempt % 5
        position_penalties = {
            (row, col): attempt_rng.randint(0, 1)
            for row in range(1, 10) for col in range(1, 9)
        } if attempt >= 3 else None
        shape = optimize(
            timeout=args.shape_seconds,
            seed=args.seed + attempt,
            visible_clue_cells=visible_clues,
            minimum_double_clues=3,
            maximum_double_clues=10,
            maximum_adjacent_pairs=3,
            maximum_top_border_clues=8,
            maximum_left_border_clues=9,
            maximum_border_clue_run=8,
            maximum_length_two_answers=2,
            only_direct_arrows=True,
            required_lengths=(5, 6),
            require_length_bands=False,
            enforce_length_balance=False,
            enforce_clue_spacing=False,
            enforce_interior_line_limits=False,
            enforce_clue_triples=True,
            enforce_solid_clue_blocks=True,
            columns=9,
            rows=10,
            maximum_answer_length=8,
            short_answer_penalty=100,
            answer_length_penalties={2: 280, 3: 55, 4: 12, 5: 3, 6: 0, 7: 0, 8: 1},
            position_penalties=position_penalties,
            previous_shapes=selected_shapes,
            maximum_shape_overlap=18,
        )
        if not shape:
            rejection_counts["geometry"] += 1
            continue
        shape_cells = {tuple(cell) for cell in shape["clueCells"]}
        if any(shape_cells == previous for previous in active_shapes):
            rejection_counts["active-shape-duplicate"] += 1
            continue
        if not acceptable_visual_shape(shape):
            rejection_counts["visual-shape"] += 1
            continue
        lengths = Counter(slot["length"] for slot in shape["slots"])
        if not acceptable_central_lengths(lengths):
            rejection_counts["length-profile"] += 1
            continue

        slots = [
            generator.Slot(
                slot["direction"], tuple(slot["clue"]),
                tuple(map(tuple, slot["cells"])), slot["arrow"],
            )
            for slot in shape["slots"]
        ]
        best: tuple[int, dict[int, str], dict, set[str]] | None = None
        variant_failures: Counter[str] = Counter()
        for variant in range(args.fill_variants):
            telemetry: dict = {}
            answers = generator.fill_bitset(
                slots,
                indexes,
                # Fill order is deliberately varied while geometry stays
                # fixed; the best editorial result wins, not the first one.
                random.Random(6 + attempt * 31 + variant * 10_007),
                None,
                unavailable_answers=selected_answers,
                answer_usage=dict(search_usage),
                grammar_answers=generator.GRAMMAR_ANSWERS,
                max_grammar_answers=2,
                max_seconds=args.fill_seconds,
                node_limit=1_500_000,
                require_image=True,
                minimum_images=1,
                prefer_constraint_support=True,
                telemetry=telemetry,
            )
            if answers is None:
                variant_failures[telemetry.get("reason", "failed")] += 1
                continue
            values = list(answers.values())
            if any(answer not in eligible for answer in values):
                raise AssertionError("un remplissage a quitté le corpus central")
            repeated_long = {
                answer for answer in values if len(answer) >= 3 and active_usage[answer]
            }
            if len(repeated_long) > args.maximum_active_long_repeats:
                variant_failures["too-many-active-repeats"] += 1
                continue
            rescue_answers = {answer for answer in values if answer not in central_answers}
            nonstandard_central = {
                answer for answer in values
                if answer in central_answers and answer not in standard_central
            }
            if len(rescue_answers) > args.maximum_lexique_rescues:
                variant_failures["too-many-lexique-rescues"] += 1
                continue
            if len(nonstandard_central) > 4:
                variant_failures["too-many-nonstandard-central"] += 1
                continue
            score = editorial_cost(
                values, sources, lexical_answers, active_usage,
                central_answers, standard_central,
            )
            candidate = (score, answers, telemetry, repeated_long)
            if best is None or score < best[0]:
                best = candidate
        if best is None:
            for reason, count in variant_failures.items():
                rejection_counts[f"fill-{reason}"] += count
            continue
        quality_score, answers, telemetry, repeated_long = best
        values = list(answers.values())
        rescue_answers = {answer for answer in values if answer not in central_answers}
        nonstandard_central = {
            answer for answer in values
            if answer in central_answers and answer not in standard_central
        }
        grid = as_grid(len(accepted) + 1, shape, answers, sources, telemetry)
        grid_id = f"central-corpus-review-draft-{len(accepted) + 1:02d}"
        grid["id"] = grid_id
        grid["lengthProfile"] = dict(sorted(lengths.items()))
        grid["publicationStatus"] = "manual-review-required"
        grid["corpusPolicy"] = "central-9491-priority-with-bounded-lexique-rescue"
        grid["centralAnswerCount"] = len(values) - len(rescue_answers)
        grid["lexiqueRescueCount"] = len(rescue_answers)
        for number, word in enumerate(grid["words"], 1):
            word["wordId"] = f"{grid_id}:word:{number:02d}"
        report = audit_grid_topology(grid)
        blocking = [error for error in report["errors"] if error["code"] != "empty_clue"]
        if blocking:
            rejection_counts["topology"] += 1
            continue
        selected = set(values)
        if selected & selected_answers:
            rejection_counts["batch-repeat"] += 1
            continue
        selected_answers.update(selected)
        selected_shapes.append(shape_cells)
        search_usage.update(selected)
        accepted.append(grid)
        print(json.dumps({
            "accepted": len(accepted),
            "attempt": attempt + 1,
            "answers": values,
            "sources": dict(Counter(sources[answer]["sourceId"] for answer in values)),
            "activeRepeatsLength3Plus": sorted(repeated_long),
            "editorialSearchCost": quality_score,
            "centralAnswers": len(values) - len(rescue_answers),
            "lexiqueRescues": sorted(rescue_answers),
            "nonstandardCentral": sorted(nonstandard_central),
        }, ensure_ascii=False), flush=True)
        if len(accepted) >= args.count:
            break

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 1,
        "kind": "non-publishable-central-priority-drafts",
        "centralCorpusAnswers": len(entries),
        "eligibleAfterQualityGates": len(eligible),
        "minimumFrequency": args.minimum_frequency,
        "lexiqueFallbackAnswers": len(eligible - central_answers),
        "activeAnswersUsedAsRepetitionPenalty": len(active_usage),
        "policy": (
            "Corpus central prioritaire; secours Lexique borné par la commande; "
            "revue manuelle obligatoire."
        ),
        "maximumLexiqueRescuesPerGrid": args.maximum_lexique_rescues,
        "grids": accepted,
        "rejectionCounts": dict(rejection_counts),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "accepted": len(accepted),
        "requested": args.count,
        "output": str(output),
        "rejectionCounts": dict(rejection_counts),
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
