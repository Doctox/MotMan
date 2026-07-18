"""Recherche éditoriale bornée de la grille A01 ancrée par IDEOLOGIE.

Ce script de travail utilise la liste de fréquence française embarquée par
``wordfreq`` comme dictionnaire structurel. Elle sert uniquement à proposer
des graphies communes; aucune définition n'en est déduite. Une fermeture
doit encore recevoir 22 indices relus avant publication.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from wordfreq import iter_wordlist, zipf_frequency

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bitset_grid_filler import fill_bitset  # noqa: E402
from diagnose_fixed_shape_corpus_gaps import (  # noqa: E402
    DEFAULT_SHAPES,
    load_expansion_words,
    load_shape,
    load_words,
)


def normalized(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.upper())
    return "".join(char for char in folded if "A" <= char <= "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimum-zipf", type=float, default=2.5)
    parser.add_argument("--seconds", type=float, default=90.0)
    parser.add_argument("--seed", type=int, default=990201)
    parser.add_argument("--structural-cap", type=int, default=0)
    parser.add_argument("--row0-answer")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    _shape, slots = load_shape(DEFAULT_SHAPES, "reference-ribbon-a-01")
    allowed_lengths = {3, 4, 5, 8, 9}
    _central, canonical = load_words()
    expanded, _metadata, _stats = load_expansion_words(
        canonical, permissive=False, include_morphalou=True
    )
    licensed = {
        answer
        for length in allowed_lengths
        for answer in expanded.get(length, ())
    }
    scores: dict[str, float] = {}
    spellings: dict[str, str] = {}
    for spelling in iter_wordlist("fr"):
        answer = normalized(spelling)
        if (
            len(answer) not in allowed_lengths
            or not answer.isascii()
            or answer not in licensed
        ):
            continue
        score = zipf_frequency(spelling, "fr")
        if score < args.minimum_zipf:
            # iter_wordlist is in decreasing frequency order.
            break
        if score > scores.get(answer, -1):
            scores[answer] = score
            spellings[answer] = spelling
    common_answers = set(scores)
    if args.structural_cap:
        for answer in licensed:
            scores.setdefault(answer, 0.0)
            spellings.setdefault(answer, answer.lower())
    scores["IDEOLOGIE"] = max(scores.get("IDEOLOGIE", 0), 4.06)
    spellings["IDEOLOGIE"] = "idéologie"

    by_length: dict[int, list[str]] = defaultdict(list)
    for answer in scores:
        by_length[len(answer)].append(answer)
    for words in by_length.values():
        words.sort()

    all_answers = set(scores)
    indexes = (
        dict(by_length),
        None,
        {answer: scores[answer] for answer in all_answers},
        {answer: answer for answer in all_answers},
        {answer: set() for answer in all_answers},
        {answer: "normal" for answer in all_answers},
        set(),
    )
    telemetry: dict = {}
    fixed_answers = {0: "IDEOLOGIE"}
    if args.row0_answer:
        fixed_answers[8] = args.row0_answer.upper()
    solution = fill_bitset(
        slots,
        indexes,
        random.Random(args.seed),
        None,
        fixed_answers=fixed_answers,
        answer_usage={answer: int(100 - scores[answer] * 10) for answer in all_answers},
        max_grammar_answers=99,
        grammar_answers=set(),
        max_seconds=args.seconds,
        node_limit=50_000_000,
        require_image=False,
        undesirable_answers=set(scores) - common_answers - {"IDEOLOGIE"},
        max_undesirable_answers=args.structural_cap,
        prefer_constraint_support=True,
        constraint_support_bucket_size=2,
        telemetry=telemetry,
    )
    summary = {
        "complete": solution is not None,
        "minimumZipf": args.minimum_zipf,
        "counts": {str(k): len(v) for k, v in sorted(by_length.items())},
        "telemetry": telemetry,
    }
    if solution:
        summary["answers"] = [
            {
                "slotIndex": index,
                "answer": answer,
                "spelling": spellings[answer],
                "zipf": scores[answer],
            }
            for index, answer in sorted(solution.items())
        ]
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0 if solution else 2


if __name__ == "__main__":
    raise SystemExit(main())
