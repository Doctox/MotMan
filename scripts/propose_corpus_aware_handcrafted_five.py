"""Propose five corpus-aware 9x10 crossing drafts for manual editing.

Geometry is optimized around the actual reviewed placement lexicon: lengths
5-8 dominate the available vocabulary, while lengths 2 and 3 remain scarce.
The solver only establishes crossings;
publication still requires explicit clue rewriting and owner review.
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
from propose_standard_crossing_drafts import as_grid, reviewed_pool
from search_audience_shapes import audience_index


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output/quality/corpus-aware-handcrafted-five-drafts.json"
PREFERRED_LENGTHS = {5, 6, 7, 8}


def acceptable_lengths(lengths: Counter[int]) -> bool:
    total = sum(lengths.values())
    if not total or lengths[2] > 2 or lengths[3] > 7:
        return False
    preferred = sum(lengths[length] for length in PREFERRED_LENGTHS)
    average = sum(length * count for length, count in lengths.items()) / total
    return preferred * 2 >= total and average >= 4.75


def acceptable_visual_shape(shape: dict) -> bool:
    """Reject definition walls while allowing conventional border frames."""
    cells = {tuple(cell) for cell in shape["clueCells"]}
    for row in range(1, 10):
        if sum((row, col) in cells for col in range(9)) > 4:
            return False
        for col in range(7):
            if all((row, col + offset) in cells for offset in range(3)):
                return False
    for col in range(1, 9):
        if sum((row, col) in cells for row in range(10)) > 4:
            return False
        for row in range(8):
            if all((row + offset, col) in cells for offset in range(3)):
                return False
    for row in range(9):
        for col in range(8):
            if all((row + dr, col + dc) in cells for dr in (0, 1) for dc in (0, 1)):
                return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--attempts", type=int, default=100)
    parser.add_argument("--seed", type=int, default=26072200)
    parser.add_argument("--shape-seconds", type=float, default=2)
    parser.add_argument("--fill-seconds", type=float, default=6)
    parser.add_argument("--minimum-frequency", type=float, default=0.8)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    output = args.output if args.output.is_absolute() else ROOT / args.output
    # Use the broad canonical placement lexicon to make long crossings
    # possible.  It is solver-only: every selected answer still receives an
    # empty clue and must be manually validated before staging/publication.
    indexes = audience_index(
        "normal", args.minimum_frequency, "placement", canonical_forms_only=True
    )
    _reviewed_indexes, sources = reviewed_pool()
    lexique_entries = json.loads(
        (ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8")
    )["entries"]
    lexique_by_answer = {entry["answer"]: entry for entry in lexique_entries}
    for answers in indexes[0].values():
        for answer in answers:
            if answer in sources:
                continue
            lexical = lexique_by_answer.get(answer, {})
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
                "sourceFrequency": lexical.get("sourceFrequency", 0),
            }
    supply = {length: len(answers) for length, answers in sorted(indexes[0].items())}
    # These costs are intentionally derived from the observed supply bands,
    # rather than from an arbitrary target distribution.  Two-letter slots
    # stay possible because the 9x10 direct-arrow topology needs a couple of
    # them, but the optimizer strongly prefers the abundant 5-8 bands.
    length_penalties = {2: 260, 3: 80, 4: 20, 5: 6, 6: 2, 7: 0, 8: 1}
    active = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    active_usage = Counter(
        word["answer"]
        for grid in active.get("grids", [])
        for word in grid.get("words", [])
    )
    active_shapes = [
        {tuple(cell) for cell in grid.get("clueCells", [])}
        for grid in active.get("grids", [])
    ]
    position_usage = Counter(
        tuple(cell)
        for shape in active_shapes
        for cell in shape
        if tuple(cell) != (0, 0)
    )
    selected_answers: set[str] = set()
    selected_shapes: list[set[tuple[int, int]]] = []
    accepted = []
    rejection_counts = defaultdict(int)
    if output.exists():
        previous = json.loads(output.read_text(encoding="utf-8"))
        if previous.get("kind") == "non-publishable-corpus-aware-handcrafted-drafts":
            accepted = previous.get("grids", [])[:args.count]
            rejection_counts.update(previous.get("rejectionCounts", {}))
            for grid in accepted:
                answers = {word["answer"] for word in grid.get("words", [])}
                shape_cells = {tuple(cell) for cell in grid.get("clueCells", [])}
                selected_answers.update(answers)
                selected_shapes.append(shape_cells)
                position_usage.update(shape_cells - {(0, 0)})
    rng = random.Random(args.seed)

    for attempt in range(args.attempts):
        attempt_position_penalties = {
            (row, col): min(3, position_usage[(row, col)]) + rng.randint(0, 3)
            for row in range(1, 10) for col in range(1, 9)
        }
        shape = optimize(
            timeout=args.shape_seconds,
            seed=args.seed + attempt,
            visible_clue_cells=22,
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
            # The generic spacing rule makes a single two-letter entry
            # geometrically impossible in 9x10.  We relax that solver rule,
            # then keep the stricter human-facing checks below.
            enforce_clue_spacing=False,
            enforce_interior_line_limits=False,
            enforce_clue_triples=True,
            enforce_solid_clue_blocks=True,
            columns=9,
            rows=10,
            maximum_answer_length=8,
            short_answer_penalty=100,
            answer_length_penalties=length_penalties,
            position_penalties=attempt_position_penalties,
            previous_shapes=selected_shapes,
            maximum_shape_overlap=16,
        )
        if not shape:
            rejection_counts["geometry"] += 1
            continue
        shape_cells = {tuple(cell) for cell in shape["clueCells"]}
        if any(shape_cells == active_shape for active_shape in active_shapes):
            rejection_counts["active-shape-duplicate"] += 1
            continue
        if not acceptable_visual_shape(shape):
            rejection_counts["visual-shape"] += 1
            continue
        lengths = Counter(slot["length"] for slot in shape["slots"])
        if not acceptable_lengths(lengths):
            rejection_counts["length-profile"] += 1
            continue

        slots = [
            generator.Slot(
                slot["direction"], tuple(slot["clue"]),
                tuple(map(tuple, slot["cells"])), slot["arrow"]
            )
            for slot in shape["slots"]
        ]
        best = None
        best_telemetry = None
        best_score = None
        # One bounded fill per mask: if it fails, change the topology instead
        # of burning time on repeated blind searches of the same dead end.
        for variant in range(1):
            telemetry = {}
            answers = generator.fill_bitset(
                slots,
                indexes,
                random.Random(args.seed + attempt * 10 + variant),
                None,
                unavailable_answers=(
                    set(generator.ROTATION_COOLDOWN_ANSWERS) | selected_answers
                ),
                answer_usage=active_usage,
                grammar_answers=generator.GRAMMAR_ANSWERS,
                max_grammar_answers=2,
                max_seconds=args.fill_seconds,
                node_limit=1_000_000,
                require_image=False,
                minimum_images=0,
                prefer_constraint_support=args.minimum_frequency > 0,
                telemetry=telemetry,
            )
            if answers is None:
                rejection_counts[f"fill-{telemetry.get('reason', 'failed')}"] += 1
                continue
            values = list(answers.values())
            score = (
                sum(active_usage[answer] for answer in values),
                sum(active_usage[answer] > 0 for answer in values),
                max((active_usage[answer] for answer in values), default=0),
            )
            if best_score is None or score < best_score:
                best, best_telemetry, best_score = answers, telemetry, score
        if best is None:
            continue

        grid = as_grid(len(accepted) + 1, shape, best, sources, best_telemetry or {})
        new_id = f"corpus-aware-handcrafted-draft-{len(accepted) + 1:02d}"
        grid["id"] = new_id
        grid["lengthProfile"] = dict(sorted(lengths.items()))
        grid["publicationStatus"] = "manual-review-required"
        for index, word in enumerate(grid["words"], start=1):
            word["wordId"] = f"{new_id}:word:{index:02d}"
        report = audit_grid_topology(grid)
        if any(error["code"] != "empty_clue" for error in report["errors"]):
            rejection_counts["topology"] += 1
            continue

        answers = {word["answer"] for word in grid["words"]}
        if answers & selected_answers:
            rejection_counts["batch-repeat"] += 1
            continue
        selected_answers.update(answers)
        accepted.append(grid)
        selected_shapes.append(shape_cells)
        position_usage.update(shape_cells - {(0, 0)})
        print(json.dumps({
            "accepted": len(accepted),
            "attempt": attempt + 1,
            "lengths": dict(sorted(lengths.items())),
            "answersNewToActive": sum(active_usage[answer] == 0 for answer in answers),
            "words": len(answers),
        }), flush=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({
            "version": 1,
            "kind": "non-publishable-corpus-aware-handcrafted-drafts",
            "policy": "Croisements seulement; chaque couple exige une revue manuelle.",
            "corpusSupplyByLength": supply,
            "answerLengthPenalties": length_penalties,
            "grids": accepted,
            "rejectionCounts": dict(rejection_counts),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        if len(accepted) >= args.count:
            break

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 1,
        "kind": "non-publishable-corpus-aware-handcrafted-drafts",
        "policy": "Croisements seulement; chaque couple exige une revue manuelle.",
        "corpusSupplyByLength": supply,
        "answerLengthPenalties": length_penalties,
        "grids": accepted,
        "rejectionCounts": dict(rejection_counts),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "accepted": len(accepted),
        "requested": args.count,
        "corpusSupplyByLength": supply,
        "rejectionCounts": dict(rejection_counts),
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
