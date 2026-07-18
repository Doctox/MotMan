"""Strictly audit an agent proposal for immutable reference-ribbon-a-01."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagnose_fixed_shape_corpus_gaps import (  # noqa: E402
    DEFAULT_SHAPES,
    crossing_arcs,
    load_expansion_words,
    load_shape,
    load_words,
)
from fill_fixed_ribbon_a01 import load_owner_accepts, selected_clue  # noqa: E402


def extract_records(document: dict) -> list[dict]:
    candidates = [
        document.get("answers"),
        document.get("allAnswers"),
        (document.get("solution") or {}).get("answers")
        if isinstance(document.get("solution"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return candidate
        if isinstance(candidate, dict):
            return [
                {"slotIndex": int(index), "answer": answer}
                for index, answer in candidate.items()
            ]
    raise ValueError("aucune liste de reponses reconnue dans la proposition")


def audit(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    records = extract_records(document)
    _shape, slots = load_shape(DEFAULT_SHAPES, "reference-ribbon-a-01")
    _words, canonical = load_words()
    words_by_length, metadata, corpus_stats = load_expansion_words(
        canonical, include_morphalou=True
    )
    owner_accepts = load_owner_accepts()
    allowed = {
        word for words in words_by_length.values() for word in words
    }
    errors = []
    by_slot: dict[int, str] = {}
    for record in records:
        try:
            index = int(record["slotIndex"])
        except (KeyError, TypeError, ValueError):
            errors.append({"code": "invalid_slot_index", "record": record})
            continue
        answer = str(record.get("answer", "")).upper().strip()
        if not 0 <= index < len(slots):
            errors.append({"code": "slot_out_of_range", "slotIndex": index})
            continue
        if index in by_slot:
            errors.append({"code": "duplicate_slot", "slotIndex": index})
            continue
        by_slot[index] = answer
        if len(answer) != slots[index].length:
            errors.append({
                "code": "length_mismatch",
                "slotIndex": index,
                "answer": answer,
                "expected": slots[index].length,
            })
        if answer not in allowed:
            errors.append({
                "code": "answer_outside_filtered_corpus",
                "slotIndex": index,
                "answer": answer,
            })
    missing = sorted(set(range(len(slots))) - set(by_slot))
    if missing:
        errors.append({"code": "missing_slots", "slotIndexes": missing})
    duplicates = [
        answer for answer, count in Counter(by_slot.values()).items()
        if answer and count > 1
    ]
    if duplicates:
        errors.append({"code": "duplicate_answers", "answers": sorted(duplicates)})

    cell_letters: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for index, answer in by_slot.items():
        if len(answer) != slots[index].length:
            continue
        for position, (cell, letter) in enumerate(zip(slots[index].cells, answer)):
            cell_letters[cell].append({
                "slotIndex": index,
                "position": position,
                "letter": letter,
            })
    crossing_errors = []
    for cell, uses in sorted(cell_letters.items()):
        letters = {item["letter"] for item in uses}
        if len(uses) != 2 or len(letters) != 1:
            crossing_errors.append({
                "cell": list(cell),
                "uses": uses,
            })
    if crossing_errors:
        errors.append({
            "code": "crossing_mismatches",
            "count": len(crossing_errors),
            "items": crossing_errors,
        })

    reviewed = []
    unreviewed = []
    for index, answer in sorted(by_slot.items()):
        clue = selected_clue(answer, canonical, owner_accepts)
        item = {
            "slotIndex": index,
            "slotId": slots[index].slot_id,
            "answer": answer,
            "clue": clue,
            "lexicalSource": metadata.get(answer, {}).get("source")
                or metadata.get(answer, {}).get("partOfSpeech"),
        }
        (reviewed if clue else unreviewed).append(item)
    return {
        "version": 1,
        "kind": "fixed-ribbon-agent-fill-audit",
        "input": str(path),
        "shapeId": "reference-ribbon-a-01",
        "shapeModified": False,
        "validLexicalClosure": not errors,
        "publicationEligible": not errors and not unreviewed,
        "slotCount": len(by_slot),
        "crossingCellsAudited": len(cell_letters),
        "errors": errors,
        "reviewedPairCount": len(reviewed),
        "unreviewedPairCount": len(unreviewed),
        "reviewed": reviewed,
        "unreviewed": unreviewed,
        "corpusFilter": corpus_stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.input)
    output = args.output or args.input.with_suffix(".audit.json")
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(output),
        "validLexicalClosure": report["validLexicalClosure"],
        "publicationEligible": report["publicationEligible"],
        "errors": report["errors"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
