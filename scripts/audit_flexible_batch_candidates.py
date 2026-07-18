"""Audit raw flexible-grid candidates before any editorial staging or publication."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--reference",
        action="append",
        type=Path,
        default=[],
        help=(
            "Previously accepted replacement-grid JSON. Exact answers and "
            "lemma/concept families found there are blocking repeats."
        ),
    )
    return parser.parse_args()


def load_lemma_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for name in ("lexique.lemmas.json", "lexique.child-forms.json"):
        document = json.loads((ROOT / "src/data" / name).read_text(encoding="utf-8"))
        for entry in document.get("entries", []):
            answer = str(entry.get("answer", "")).upper()
            lemma = str(entry.get("lemma") or answer).upper()
            if answer:
                result[answer] = lemma
    return result


def load_blacklist() -> set[str]:
    document = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    return {
        str(answer).upper()
        for key in ("rejectedAnswers", "rejectedEasyAnswers", "rejectedNormalAnswers")
        for answer in document.get(key, [])
    }


def load_rejected_cooccurrences() -> list[dict]:
    document = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    return [
        {
            "answers": sorted({
                str(answer).upper() for answer in rule.get("answers", []) if answer
            }),
            "reason": str(rule.get("reason", "")),
        }
        for rule in document.get("rejectedCooccurrences", [])
        if len(set(rule.get("answers", []))) >= 2
    ]


def find_rejected_cooccurrences(
    answers: set[str], rules: list[dict]
) -> list[dict]:
    return [
        rule for rule in rules
        if set(rule["answers"]).issubset(answers)
    ]


def load_active_usage() -> Counter:
    document = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    return Counter(
        word["answer"]
        for grid in document.get("grids", [])
        for word in grid.get("words", [])
    )


def load_image_answers() -> dict[str, dict]:
    document = json.loads(
        (ROOT / "src/data/crossword.images-reviewed.json").read_text(encoding="utf-8")
    )
    return {
        entry["answer"]: entry["image"]
        for entry in document.get("entries", [])
        if entry.get("answer") and isinstance(entry.get("image"), dict)
    }


def extract_grid(document: dict) -> dict:
    if isinstance(document.get("grid"), dict):
        return document["grid"]
    grids = document.get("grids")
    if isinstance(grids, list) and grids:
        return grids[0]
    return document


def extract_answers(grid: dict) -> list[dict]:
    return list(grid.get("answers") or grid.get("words") or [])


def answer_family(item: dict, lemmas: dict[str, str]) -> str:
    answer = str(item.get("answer", "")).upper()
    concept = str(item.get("conceptGroup") or "").upper()
    return concept or lemmas.get(answer, answer)


def load_reference_usage(
    paths: list[Path], lemmas: dict[str, str]
) -> tuple[Counter, Counter]:
    answers: Counter = Counter()
    families: Counter = Counter()
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        grid = extract_grid(document)
        for item in extract_answers(grid):
            answer = str(item.get("answer", "")).upper()
            if not answer:
                continue
            answers[answer] += 1
            families[answer_family(item, lemmas)] += 1
    return answers, families


def topology_grid(path: Path, grid: dict, answers: list[dict]) -> dict:
    words = []
    for number, item in enumerate(answers, start=1):
        direction = item["direction"]
        words.append({
            "wordId": f"audit:{path.stem}:{number:02d}",
            "answer": item["answer"],
            "clue": item.get("clue") or f"Revue {number}",
            "direction": direction,
            "arrow": "right" if direction == "across" else "down",
            "clueCell": item["clueCell"],
            "cells": item["cells"],
        })
    return {
        "id": grid.get("id", path.stem),
        "columns": grid.get("columns", 9),
        "rows": grid.get("rows", 10),
        "clueCells": grid["clueCells"],
        "words": words,
    }


def audit_candidate(
    path: Path,
    *,
    lemmas: dict[str, str],
    blacklist: set[str],
    active_usage: Counter,
    images: dict[str, dict],
    reference_answers: Counter | None = None,
    reference_families: Counter | None = None,
    rejected_cooccurrences: list[dict] | None = None,
) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    grid = extract_grid(document)
    answers = extract_answers(grid)
    names = [str(item.get("answer", "")).upper() for item in answers]
    topology = audit_grid_topology(
        topology_grid(path, grid, answers), enforce_layout=False
    )

    reference_answers = reference_answers or Counter()
    reference_families = reference_families or Counter()
    family_by_answer = {
        str(item.get("answer", "")).upper(): answer_family(item, lemmas)
        for item in answers
    }
    by_lemma: dict[str, list[str]] = defaultdict(list)
    for answer in names:
        by_lemma[family_by_answer[answer]].append(answer)
    repeated_families = {
        lemma: members
        for lemma, members in sorted(by_lemma.items())
        if len(set(members)) > 1
    }
    active_repeats = {
        answer: active_usage[answer]
        for answer in names
        if active_usage[answer]
    }
    reference_answer_repeats = {
        answer: reference_answers[answer]
        for answer in names
        if reference_answers[answer]
    }
    reference_family_repeats = {
        family_by_answer[answer]: reference_families[family_by_answer[answer]]
        for answer in names
        if reference_families[family_by_answer[answer]]
    }
    image_matches = {
        answer: images[answer]
        for answer in names
        if answer in images
    }
    frequency_doubts = [
        {
            "answer": item["answer"],
            "zipf": item.get("zipf"),
        }
        for item in answers
        if item.get("zipf") is not None and float(item["zipf"]) < 3.0
    ]
    two_letter = [answer for answer in names if len(answer) == 2]
    hard_errors = []
    if not topology["valid"]:
        hard_errors.append("invalid_topology")
    if topology["orphanSegments"]:
        hard_errors.append("orphan_segments")
    if len(two_letter) > 2:
        hard_errors.append("too_many_two_letter_answers")
    if len(names) != len(set(names)):
        hard_errors.append("duplicate_answers")
    if repeated_families:
        hard_errors.append("duplicate_lemma_families")
    if reference_answer_repeats:
        hard_errors.append("answer_repeated_from_replacement_reference")
    if reference_family_repeats:
        hard_errors.append("family_repeated_from_replacement_reference")
    blacklisted = sorted(set(names) & blacklist)
    if blacklisted:
        hard_errors.append("blacklisted_answers")
    cooccurrence_conflicts = find_rejected_cooccurrences(
        set(names), rejected_cooccurrences or []
    )
    if cooccurrence_conflicts:
        hard_errors.append("rejected_answer_cooccurrence")

    return {
        "path": str(path),
        "gridId": grid.get("id", path.stem),
        "shapeFingerprint": ";".join(
            f"{row},{col}" for row, col in sorted(map(tuple, grid["clueCells"]))
        ),
        "hardValid": not hard_errors,
        "hardErrors": hard_errors,
        "topologyValid": topology["valid"],
        "topologyErrors": topology["errors"],
        "answers": names,
        "answerCount": len(names),
        "lengthProfile": dict(sorted(Counter(map(len, names)).items())),
        "twoLetterAnswers": two_letter,
        "blacklistedAnswers": blacklisted,
        "rejectedCooccurrences": cooccurrence_conflicts,
        "repeatedLemmaFamilies": repeated_families,
        "familyByAnswer": family_by_answer,
        "referenceAnswerRepeats": reference_answer_repeats,
        "referenceFamilyRepeats": reference_family_repeats,
        "activeRepeats": active_repeats,
        "activeRepeatCount": len(active_repeats),
        "imageMatches": image_matches,
        "imageMatchCount": len(image_matches),
        "frequencyDoubts": frequency_doubts,
    }


def apply_cross_candidate_repeat_gates(reports: list[dict]) -> dict:
    answer_members: dict[str, list[str]] = defaultdict(list)
    family_members: dict[str, list[dict]] = defaultdict(list)
    for report in reports:
        for answer in set(report["answers"]):
            answer_members[answer].append(report["gridId"])
            family = report["familyByAnswer"].get(answer, answer)
            family_members[family].append({
                "gridId": report["gridId"],
                "answer": answer,
            })

    answer_collisions = {
        answer: members
        for answer, members in sorted(answer_members.items())
        if len(set(members)) > 1
    }
    family_collisions = {
        family: members
        for family, members in sorted(family_members.items())
        if len({member["gridId"] for member in members}) > 1
    }
    for report in reports:
        grid_id = report["gridId"]
        report["batchAnswerRepeats"] = {
            answer: members
            for answer, members in answer_collisions.items()
            if grid_id in members
        }
        report["batchFamilyRepeats"] = {
            family: members
            for family, members in family_collisions.items()
            if any(member["gridId"] == grid_id for member in members)
        }
        if report["batchAnswerRepeats"]:
            report["hardErrors"].append("answer_repeated_across_candidate_batch")
        if report["batchFamilyRepeats"]:
            report["hardErrors"].append("family_repeated_across_candidate_batch")
        report["hardErrors"] = list(dict.fromkeys(report["hardErrors"]))
        report["hardValid"] = not report["hardErrors"]

    return {
        "answerCollisions": answer_collisions,
        "familyCollisions": family_collisions,
    }


def main() -> None:
    args = parse_args()
    lemmas = load_lemma_map()
    blacklist = load_blacklist()
    rejected_cooccurrences = load_rejected_cooccurrences()
    active_usage = load_active_usage()
    images = load_image_answers()
    reference_answers, reference_families = load_reference_usage(
        args.reference, lemmas
    )
    reports = [
        audit_candidate(
            path,
            lemmas=lemmas,
            blacklist=blacklist,
            active_usage=active_usage,
            images=images,
            reference_answers=reference_answers,
            reference_families=reference_families,
            rejected_cooccurrences=rejected_cooccurrences,
        )
        for path in args.inputs
    ]
    batch_repeats = apply_cross_candidate_repeat_gates(reports)
    duplicate_shapes = [
        fingerprint
        for fingerprint, count in Counter(
            report["shapeFingerprint"] for report in reports
        ).items()
        if count > 1
    ]
    payload = {
        "version": 1,
        "catalogModified": False,
        "candidateCount": len(reports),
        "hardValidCount": sum(report["hardValid"] for report in reports),
        "duplicateShapeFingerprints": duplicate_shapes,
        "replacementReferences": [str(path) for path in args.reference],
        "batchAnswerCollisions": batch_repeats["answerCollisions"],
        "batchFamilyCollisions": batch_repeats["familyCollisions"],
        "candidates": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "candidates": len(reports),
        "hardValid": payload["hardValidCount"],
        "duplicateShapes": len(duplicate_shapes),
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
