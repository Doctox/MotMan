"""Bounded search for readable fills in the owner-approved silhouette family."""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import generate_grid_catalog as generator
from grid_topology import audit_grid_topology
from optimize_grid_shapes import optimize
from propose_standard_crossing_drafts import as_grid, reviewed_pool
from search_audience_shapes import audience_index


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/quality/corpus-aware-quality-pool.json"

# Universally unsuitable answers exposed by the rejected smoke fills.  They
# are also fed into the durable blacklist before any selected grid is staged.
EDITORIAL_HARD_REJECTS = set("""
ADENT ADP AGITPROP AID ANAL ANTE ANTISIDA AREA ARTIFLOT ASDIC ASA
ASILAIRE ASPRE AULA AVALAGE AVALEUR BASIN BEATS BICLOUS BIFTON BIGO
BONIS CAROUSSE CIBOULOT CINERAMA COCACOLA CONTREUT CORAMINE DAO DEC
DECAVE DOL DOURA DUS ECOEUREE ENBUT ESTCE ESTES FAU FRA GON GRANA
GUNS HAUTESSE HEMI IBO ICECREAM INFONDES ITALIANO IVES JAR KEIRETSU
LARE LIBERA LOMPE LORI MAIGRIOT MALARD MANA MENTERIE MEXICO MIDOUCE
MIR NENESSES NERVI OFF ORILLON ORPIMENT ORT OVEE PECCATA PEP PEPES
PESSAIRE PIGE PIQUEFEU PIS PISSETTE PORNO RAC RAG RASEPETS REBARRE
REF RELAPSE REMIX REP RESET RHODO ROUF SADO SCAT SCHNOUF SECCO SEXY
SMACK SONG SPEECH STRING SUI SUSU TEC TEM TERTIO TIAMA TONER TUES
UNETELLE VAU
""".split())


def acceptable_profile(lengths: Counter[int]) -> bool:
    total = sum(lengths.values())
    preferred = sum(lengths[length] for length in (5, 6, 7, 8))
    average = sum(length * count for length, count in lengths.items()) / total
    return (
        lengths[2] <= 2
        and lengths[3] <= 7
        and preferred * 2 >= total
        and average >= 4.75
    )


def source_map(indexes) -> dict[str, dict]:
    _reviewed, sources = reviewed_pool()
    lexique = json.loads(
        (ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8")
    )["entries"]
    lexical_by_answer = {entry["answer"]: entry for entry in lexique}
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
                "sourceFrequency": lexical.get("sourceFrequency", 0),
            }
    return sources


def quality_score(
    answers: list[str], lexical_frequency: dict[str, float], central: set[str],
    active_usage: Counter[str],
) -> tuple[int, int, int, int]:
    rare_cost = 0
    for answer in answers:
        frequency = lexical_frequency.get(answer, 0)
        if frequency < .05:
            rare_cost += 8
        elif frequency < .2:
            rare_cost += 5
        elif frequency < .8:
            rare_cost += 3
        elif frequency < 2:
            rare_cost += 1
    return (
        rare_cost,
        sum(answer not in central for answer in answers),
        sum(active_usage[answer] for answer in answers),
        sum(len(answer) <= 3 for answer in answers),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts", type=int, default=80)
    parser.add_argument("--keep", type=int, default=15)
    parser.add_argument("--seed", type=int, default=26071590)
    parser.add_argument("--shape-seconds", type=float, default=1.5)
    parser.add_argument("--fill-seconds", type=float, default=4)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    indexes = audience_index("normal", 0, "placement", canonical_forms_only=True)
    sources = source_map(indexes)
    central = {entry["answer"] for entry in generator.load_entries()}
    lexical_frequency = {
        entry["answer"]: float(entry.get("sourceFrequency", 0))
        for entry in json.loads(
            (ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8")
        )["entries"]
    }
    active = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    active_usage = Counter(
        word["answer"] for grid in active.get("grids", []) for word in grid.get("words", [])
    )
    previous_shapes: list[set[tuple[int, int]]] = []
    candidates: list[dict] = []
    rng = random.Random(args.seed)

    for attempt in range(args.attempts):
        penalties = {
            (row, col): rng.randint(0, 3)
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
            enforce_clue_spacing=False,
            enforce_interior_line_limits=False,
            enforce_clue_triples=True,
            enforce_solid_clue_blocks=True,
            columns=9,
            rows=10,
            maximum_answer_length=8,
            short_answer_penalty=100,
            answer_length_penalties={2: 260, 3: 80, 4: 20, 5: 6, 6: 2, 7: 0, 8: 1},
            position_penalties=penalties,
            previous_shapes=previous_shapes,
            maximum_shape_overlap=20,
        )
        if not shape:
            continue
        lengths = Counter(slot["length"] for slot in shape["slots"])
        if not acceptable_profile(lengths):
            continue
        slots = [generator.Slot(
            slot["direction"], tuple(slot["clue"]),
            tuple(map(tuple, slot["cells"])), slot["arrow"],
        ) for slot in shape["slots"]]
        telemetry: dict = {}
        answers = generator.fill_bitset(
            slots, indexes, rng, None,
            unavailable_answers=EDITORIAL_HARD_REJECTS,
            answer_usage={},
            grammar_answers=generator.GRAMMAR_ANSWERS,
            max_grammar_answers=2,
            max_seconds=args.fill_seconds,
            node_limit=2_000_000,
            require_image=True,
            minimum_images=1,
            telemetry=telemetry,
        )
        if answers is None:
            continue
        values = [answers[index] for index in sorted(answers)]
        score = quality_score(values, lexical_frequency, central, active_usage)
        grid = as_grid(len(candidates) + 1, shape, answers, sources, telemetry)
        grid["lengthProfile"] = dict(sorted(lengths.items()))
        grid["qualitySearchScore"] = list(score)
        grid["id"] = f"quality-pool-{attempt + 1:03d}"
        for number, word in enumerate(grid["words"], 1):
            word["wordId"] = f"{grid['id']}:word:{number:02d}"
        topology = audit_grid_topology(grid)
        if any(error["code"] != "empty_clue" for error in topology["errors"]):
            continue
        candidates.append(grid)
        previous_shapes.append({tuple(cell) for cell in shape["clueCells"]})
        candidates.sort(key=lambda candidate: tuple(candidate["qualitySearchScore"]))
        candidates = candidates[:args.keep]
        print(json.dumps({
            "attempt": attempt + 1,
            "accepted": len(candidates),
            "score": score,
            "answers": values,
        }, ensure_ascii=False), flush=True)

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 1,
        "kind": "non-publishable-quality-search-pool",
        "attempts": args.attempts,
        "grids": candidates,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"kept": len(candidates), "output": str(output)}), flush=True)


if __name__ == "__main__":
    main()
