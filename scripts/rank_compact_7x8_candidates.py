#!/usr/bin/env python3
"""Rank existing raw 7x8 fills for human editorial recovery.

This script never publishes a grid.  It only removes candidates that repeat an
answer family already in a reviewed reference and surfaces the least risky raw
fills for a human pass.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from build_compact_7x8_review import family_key, normalize
from editorial_fill_quality import blacklist_sets, editorial_entry_score


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("output/quality"))
    parser.add_argument("--pattern", default="compact-7x8*.json")
    parser.add_argument("--reference", type=Path, action="append", default=[])
    parser.add_argument("--after", default="")
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--maximum-weak-entries", type=int, default=2)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def answer_records(grid: dict) -> list[dict]:
    records: list[dict] = []
    values = grid.get("answers")
    if not isinstance(values, list):
        values = grid.get("words", [])
    for value in values:
        if isinstance(value, str):
            records.append({"answer": value})
        elif isinstance(value, dict) and value.get("answer"):
            records.append(value)
    return records


def grids_in(document: dict) -> Iterable[tuple[int, dict]]:
    if not isinstance(document, dict):
        return
    grids = document.get("grids")
    if isinstance(grids, list):
        for index, grid in enumerate(grids, start=1):
            if isinstance(grid, dict):
                yield index, grid
        return
    if answer_records(document):
        yield 1, document


def reference_families(paths: list[Path]) -> set[str]:
    families: set[str] = set()
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        for _, grid in grids_in(document):
            for record in answer_records(grid):
                families.add(family_key(record.get("answer", "")))
    return families


def has_no_isolated_clues(grid: dict) -> bool:
    raw_slots = grid.get("rawSlots")
    clue_cells = grid.get("clueCells")
    if not isinstance(raw_slots, list) or not isinstance(clue_cells, list):
        return False
    used_clues = {
        tuple(slot.get("clueCell", []))
        for slot in raw_slots
        if len(slot.get("clueCell", [])) == 2
    }
    return all(
        tuple(cell) == (0, 0) or tuple(cell) in used_clues
        for cell in clue_cells
    )


def editorial_score_summary(records: list[dict]) -> dict:
    pop_answers = {
        normalize(str(record.get("answer", "")))
        for record in records
        if "pop-culture" in str(record.get("sourceId") or "")
    }
    scores = {
        normalize(str(record.get("answer", ""))): float(
            record.get("editorialFillScore")
            if record.get("editorialFillScore") is not None
            else editorial_entry_score(
                str(record.get("answer", "")),
                record,
                pop_answers=pop_answers,
            )
        )
        for record in records
        if normalize(str(record.get("answer", "")))
    }
    weak = sorted(answer for answer, score in scores.items() if score < 30.0)
    mechanical = sorted(answer for answer, score in scores.items() if score == 0.0)
    return {
        "scores": scores,
        "weakAnswers": weak,
        "mechanicalAnswers": mechanical,
        "weakestEntryScore": min(scores.values(), default=0.0),
        "meanEntryScore": round(sum(scores.values()) / max(1, len(scores)), 3),
        "strongEntryCount": sum(score >= 60.0 for score in scores.values()),
    }


def main() -> None:
    args = parse_args()
    blocked_families = reference_families(args.reference)
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    blocked_answers, cooldown_answers = blacklist_sets(blacklist)
    ranked: list[dict] = []
    for path in sorted(args.root.glob(args.pattern)):
        if args.after and path.name < args.after:
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for index, grid in grids_in(document):
            records = answer_records(grid)
            if not records:
                continue
            answers = [normalize(record["answer"]) for record in records]
            if set(answers) & (blocked_answers | cooldown_answers):
                continue
            if not has_no_isolated_clues(grid):
                continue
            families = [family_key(record["answer"]) for record in records]
            repeated = sorted(set(families) & blocked_families)
            internal_repeat = len(families) != len(set(families))
            if repeated or internal_repeat:
                continue
            two_letter = sum(len(answer) <= 2 for answer in answers)
            short = sum(len(answer) <= 3 for answer in answers)
            zipfs = [
                float(record.get("wordfreqZipf", 0) or 0)
                for record in records
                if record.get("wordfreqZipf") is not None
            ]
            low_zipf = sum(0 < value < 2.5 for value in zipfs)
            unsourced = sum(
                not record.get("centralClue") and not record.get("sourceClue")
                for record in records
            )
            lexical_review = sum(
                "owner-review-required" in str(record.get("editorialStatus", ""))
                for record in records
            )
            editorial = editorial_score_summary(records)
            if (
                editorial["mechanicalAnswers"]
                or len(editorial["weakAnswers"]) > args.maximum_weak_entries
            ):
                continue
            score = (
                two_letter * 12
                + short * 3
                + low_zipf * 8
                + unsourced * 2
                + lexical_review
                + len(editorial["weakAnswers"]) * 25
                - editorial["strongEntryCount"] * 2
            )
            ranked.append(
                {
                    "source": path.as_posix(),
                    "index": index,
                    "score": score,
                    "twoLetter": two_letter,
                    "short": short,
                    "lowZipf": low_zipf,
                    "unsourced": unsourced,
                    **editorial,
                    "answers": answers,
                }
            )
    ranked.sort(key=lambda item: (item["score"], item["twoLetter"], item["short"], item["source"]))
    result = ranked[: args.limit]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
