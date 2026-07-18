"""Compare les cinq placements d'IDEOLOGIE dans la silhouette A01 immuable.

Le domaine est volontairement éditorial : couples centraux relus, y compris
les entrées non canoniques, et réponses en cooldown réadmises. Les rejets
explicites restent exclus. IDEOLOGIE est la seule graphie sans couple central,
car elle constitue l'ancre donnée par le propriétaire.
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bitset_grid_filler import fill_bitset  # noqa: E402
from diagnose_fixed_shape_corpus_gaps import DEFAULT_SHAPES, load_shape  # noqa: E402

CENTRAL = ROOT / "src/data/crossword.central.json.gz"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
CATALOG = ROOT / "src/data/grid.catalog.json"
DEFAULT_OUTPUT = ROOT / "output/quality/reference-ribbon-a01-ideologie-placements.json"
REVIEWED = {"source-backed", "human-reviewed", "image-reviewed", "owner-approved"}
LONG_SLOTS = (0, 1, 2, 5, 6)
LENGTHS = {3, 4, 5, 8, 9}


def pair_key(entry: dict) -> tuple:
    return (
        0 if entry.get("canonicalForGenerator") else 1,
        0 if entry.get("editorialStatus") == "human-reviewed" else 1,
        len(str(entry.get("clue") or "")),
        str(entry.get("clue") or "").casefold(),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds-per-placement", type=float, default=35.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    shape, slots = load_shape(DEFAULT_SHAPES, "reference-ribbon-a-01")
    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    rejected = {
        item for key in ("rejectedAnswers", "rejectedEasyAnswers", "rejectedNormalAnswers")
        for item in blacklist.get(key, []) if isinstance(item, str)
    }
    cooldown = {
        item.get("answer") for item in blacklist.get("rotationCooldownAnswers", [])
        if isinstance(item, dict) and item.get("answer")
    }
    with gzip.open(CENTRAL, "rt", encoding="utf-8") as stream:
        central = json.load(stream)["entries"]

    pairs: dict[str, dict] = {}
    status_counts = Counter()
    for entry in central:
        answer = str(entry.get("answer") or "").upper()
        clue = str(entry.get("clue") or "").strip()
        status = entry.get("editorialStatus")
        if (
            len(answer) not in LENGTHS or not answer.isascii() or not answer.isalpha()
            or answer in rejected or not clue or status not in REVIEWED
        ):
            continue
        previous = pairs.get(answer)
        if previous is None or pair_key(entry) < pair_key(previous):
            pairs[answer] = entry
        status_counts[status] += 1

    # Cooldown is a rotation policy, not an editorial rejection. Its reviewed
    # pair remains a valid structural and editorial candidate for this test.
    restored_cooldown = sorted(answer for answer in cooldown if answer in pairs)
    pairs["IDEOLOGIE"] = {
        "answer": "IDEOLOGIE",
        "clue": "Courant d'idées",
        "editorialStatus": "owner-anchor",
        "sourceId": "owner-anchor-20260717",
        "canonicalForGenerator": False,
        "frequency": 4.06,
    }

    by_length: dict[int, list[str]] = defaultdict(list)
    for answer in pairs:
        by_length[len(answer)].append(answer)
    for answers in by_length.values():
        answers.sort()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    active = Counter(
        word.get("answer")
        for grid in catalog.get("grids", [])
        for word in grid.get("words", [])
    )
    concepts = {answer: answer for answer in pairs}
    indexes = (
        dict(by_length),
        None,
        {answer: float(pairs[answer].get("frequency") or 0) for answer in pairs},
        concepts,
        {answer: set() for answer in pairs},
        {answer: str(pairs[answer].get("difficulty") or "normal") for answer in pairs},
        set(),
    )

    attempts = []
    closures = []
    for offset, slot_index in enumerate(LONG_SLOTS):
        telemetry: dict = {}
        solution = fill_bitset(
            slots,
            indexes,
            random.Random(991_000 + slot_index),
            None,
            fixed_answers={slot_index: "IDEOLOGIE"},
            unavailable_answers=rejected,
            answer_usage=active,
            max_grammar_answers=99,
            grammar_answers=set(),
            max_seconds=args.seconds_per_placement,
            node_limit=50_000_000,
            require_image=False,
            prefer_constraint_support=True,
            constraint_support_bucket_size=1,
            telemetry=telemetry,
        )
        attempt = {
            "slotIndex": slot_index,
            "slotId": slots[slot_index].slot_id,
            "complete": solution is not None,
            "telemetry": telemetry,
        }
        attempts.append(attempt)
        if solution:
            words = []
            for index, answer in sorted(solution.items()):
                pair = pairs[answer]
                words.append({
                    "slotIndex": index,
                    "slotId": slots[index].slot_id,
                    "answer": answer,
                    "clue": pair["clue"],
                    "editorialStatus": pair.get("editorialStatus"),
                    "canonical": bool(pair.get("canonicalForGenerator")),
                    "sourceId": pair.get("sourceId"),
                    "activeOccurrences": active[answer],
                })
            closures.append({
                "anchorSlotIndex": slot_index,
                "words": words,
                "nonCanonicalCount": sum(not word["canonical"] for word in words),
                "activeRepeatCount": sum(bool(word["activeOccurrences"]) for word in words),
            })

    document = {
        "version": 1,
        "kind": "reference-ribbon-a01-ideologie-placement-comparison",
        "generatedOn": str(date.today()),
        "shapeId": shape["id"],
        "shapeModified": False,
        "catalogModified": False,
        "publicationEligible": False,
        "policy": {
            "reviewedStatuses": sorted(REVIEWED),
            "nonCanonicalCentralIncluded": True,
            "rotationCooldownRestored": restored_cooldown,
            "explicitRejectedAnswersExcluded": len(rejected),
            "soleExternalAnchor": "IDEOLOGIE",
        },
        "pool": {
            "distinctAnswers": len(pairs),
            "byLength": {str(k): len(v) for k, v in sorted(by_length.items())},
            "statusRows": dict(status_counts),
        },
        "placements": attempts,
        "closures": closures,
        "verdict": (
            "complete-reviewed-closure-found"
            if closures else
            "no-reviewed-closure-in-tested-fixed-placements"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "pool": document["pool"],
        "placements": attempts,
        "closureCount": len(closures),
        "output": str(args.output),
    }, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
