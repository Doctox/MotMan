#!/usr/bin/env python3
"""One-off word-first staging search for the five owner-approved shapes.

This tool deliberately ignores the clue corpus.  It only proposes spellings
from the French frequency list, plus a short owner-approved list of common
abbreviations.  Its output is never publication-ready: an editor/agent must
accept every answer and write every clue afterwards.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import unicodedata
from pathlib import Path

from wordfreq import iter_wordlist, zipf_frequency


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bitset_grid_filler import fill_bitset  # noqa: E402
from diagnose_fixed_shape_corpus_gaps import load_shape  # noqa: E402


OWNER_APPROVED_SHORT = {
    "BAC", "CB", "CDI", "CLAC", "CPE", "HLM", "LIT", "LOT", "MAP",
    "MIG", "NIL", "PAC", "PNG", "POP", "RAP", "SAC", "TIG", "TOM",
    "TOT", "TPE",
}


def normalized(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.upper())
    return "".join(char for char in folded if "A" <= char <= "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shape-file", type=Path, required=True)
    parser.add_argument("--shape-id", required=True)
    parser.add_argument("--minimum-zipf", type=float, default=3.5)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--seed", type=int, default=719200)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    shape, slots = load_shape(args.shape_file, args.shape_id)
    lengths = sorted({slot.length for slot in slots})
    words_by_length = {length: [] for length in lengths}
    scores: dict[str, float] = {}
    spellings: dict[str, str] = {}
    for spelling in iter_wordlist("fr"):
        score = zipf_frequency(spelling, "fr")
        if score < args.minimum_zipf:
            break
        if not spelling.isalpha():
            continue
        answer = normalized(spelling)
        if len(answer) not in words_by_length or answer in scores:
            continue
        scores[answer] = score
        spellings[answer] = spelling
        words_by_length[len(answer)].append(answer)
    for answer in OWNER_APPROVED_SHORT:
        if len(answer) in words_by_length and answer not in scores:
            scores[answer] = 5.0
            spellings[answer] = answer.lower()
            words_by_length[len(answer)].append(answer)
    for length in lengths:
        words_by_length[length] = tuple(sorted(words_by_length[length]))

    indexes = (
        words_by_length,
        None,
        scores,
        {answer: answer for answer in scores},
        {answer: set() for answer in scores},
        {answer: "normal" for answer in scores},
        set(),
    )
    telemetry: dict = {}
    solution = fill_bitset(
        slots,
        indexes,
        random.Random(args.seed),
        None,
        answer_usage={
            answer: int(1000 - score * 100) for answer, score in scores.items()
        },
        max_grammar_answers=99,
        grammar_answers=set(),
        max_seconds=args.seconds,
        node_limit=80_000_000,
        require_image=False,
        prefer_constraint_support=True,
        constraint_support_bucket_size=2,
        telemetry=telemetry,
    )
    document = {
        "version": 1,
        "kind": "owner-approved-shape-word-first-staging",
        "shapeId": args.shape_id,
        "shapeModified": False,
        "catalogModified": False,
        "complete": solution is not None,
        "publicationEligible": False,
        "minimumZipf": args.minimum_zipf,
        "candidateCounts": {
            str(length): len(words) for length, words in words_by_length.items()
        },
        "telemetry": telemetry,
        "answers": (
            [
                {
                    "slotIndex": index,
                    "slotId": slots[index].slot_id,
                    "answer": answer,
                    "spelling": spellings[answer],
                    "zipf": scores[answer],
                    "ownerApprovedShort": answer in OWNER_APPROVED_SHORT,
                }
                for index, answer in enumerate(solution)
            ]
            if solution is not None
            else None
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "shapeId": args.shape_id,
        "complete": document["complete"],
        "telemetry": telemetry,
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if solution is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
