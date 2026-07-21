#!/usr/bin/env python3
"""Column-first exact filler for the corrected 7x8 shape with pivot (4, 6)."""
from __future__ import annotations

import argparse
import gzip
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

from wordfreq import iter_wordlist, zipf_frequency

from build_compact_7x8_review import family_key
from editorial_fill_quality import answer_usage
from search_compact_grid_pilot import (
    GRAMMAR_ANSWERS,
    OWNER_SHORT,
    PILOT_CONCEPT_FAMILY_OVERRIDES,
    PILOT_REVIEWED_LONG,
    PILOT_REVIEWED_NATURAL_FORMS,
    PILOT_SAFE_SHORT,
    ROOT,
    build_slots_from_shape,
    load_shape_definition,
    normalized,
    rotation_cooldown_usage,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shape-file", type=Path, required=True)
    parser.add_argument("--shape-id", default="corrected-7x8-02")
    parser.add_argument("--lexicon", choices=("large", "wordfreq"), default="large")
    parser.add_argument("--minimum-zipf", type=float, default=2.8)
    parser.add_argument("--minimum-constructor-score", type=float, default=10.0)
    parser.add_argument("--minimum-familiarity-zipf", type=float, default=3.0)
    parser.add_argument("--max-unfamiliar-answers", type=int, default=2)
    parser.add_argument("--maximum-grammar-answers", type=int, default=1)
    parser.add_argument("--short-domain", choices=("safe", "owner"), default="safe")
    parser.add_argument("--seconds", type=float, default=90.0)
    parser.add_argument("--solution-limit", type=int, default=128)
    parser.add_argument("--seed", type=int, default=814100)
    parser.add_argument("--reference-catalog", type=Path, action="append", default=[])
    parser.add_argument("--avoid-fill", type=Path, action="append", default=[])
    parser.add_argument("--minimum-solution-distance", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def bits(value: int):
    while value:
        least = value & -value
        yield least.bit_length() - 1
        value ^= least


def main() -> int:
    args = parse_args()
    shape = load_shape_definition(args.shape_file, args.shape_id)
    columns, rows, shape_id, clues, raw_slots, slots = build_slots_from_shape(shape)
    lengths = [len(slot.cells) for slot in slots]
    if (columns, rows, lengths) != (
        7,
        8,
        [7, 7, 7, 7, 7, 3, 6, 6, 6, 5, 3, 6, 6, 6],
    ):
        raise ValueError("Ce remplisseur spécialisé exige exactement corrected-7x8-02")

    blacklist_document = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    rejected = {normalized(answer) for answer in blacklist_document.get("rejectedAnswers", [])}
    rejected_families = {family_key(answer) for answer in rejected}
    active = answer_usage(args.reference_catalog)
    for answer, uses in rotation_cooldown_usage(blacklist_document).items():
        active[answer] = max(active[answer], uses)

    words_by_length: dict[int, set[str]] = {3: set(), 5: set(), 6: set(), 7: set()}
    spelling: dict[str, str] = {}
    metadata: dict[str, dict] = {}
    zipf: dict[str, float] = {}
    score: dict[str, float] = {}
    families: dict[str, str] = {}

    def admit(answer: str, label: str, item: dict | None, constructor: float) -> None:
        if len(answer) not in words_by_length or answer in rejected:
            return
        family = PILOT_CONCEPT_FAMILY_OVERRIDES.get(answer, family_key(answer))
        if family in rejected_families or answer in score:
            return
        frequency = float(zipf_frequency(label, "fr"))
        if len(answer) > 3 and frequency < args.minimum_zipf:
            return
        words_by_length[len(answer)].add(answer)
        spelling[answer] = label
        metadata[answer] = item or {
            "partOfSpeech": "editorial-reviewed",
            "formType": "editorial-reviewed",
        }
        zipf[answer] = frequency
        score[answer] = constructor + 5.0 * frequency - min(30.0, 12.0 * active.get(answer, 0))
        families[answer] = family

    with gzip.open(
        ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8"
    ) as stream:
        entries = json.load(stream).get("entries", [])
    lexical_metadata: dict[str, dict] = {}
    for item in entries:
        answer = normalized(str(item.get("answer", "")))
        if answer and answer not in lexical_metadata:
            lexical_metadata[answer] = item

    if args.lexicon == "large":
        for item in entries:
            answer = normalized(str(item.get("answer", "")))
            if len(answer) not in words_by_length or len(answer) == 3:
                continue
            constructor = float(item.get("constructorScore", 0.0))
            if (
                item.get("attestedCommonForm") is not True
                or constructor < args.minimum_constructor_score
                or (
                    item.get("partOfSpeech") == "verb"
                    and item.get("formType") != "lemma"
                )
            ):
                continue
            admit(answer, str(item.get("spelling") or answer.lower()), item, constructor)
    else:
        for label in iter_wordlist("fr"):
            frequency = float(zipf_frequency(label, "fr"))
            if frequency < args.minimum_zipf:
                break
            if not label.isalpha():
                continue
            answer = normalized(label)
            if len(answer) in words_by_length and len(answer) > 3:
                item = lexical_metadata.get(answer)
                if item is not None and (
                    item.get("attestedCommonForm") is not True
                    or (
                        item.get("partOfSpeech") == "verb"
                        and item.get("formType") != "lemma"
                    )
                ):
                    continue
                admit(answer, label, item, 5.0)

    for answer in PILOT_REVIEWED_LONG | PILOT_REVIEWED_NATURAL_FORMS:
        if len(answer) in words_by_length:
            admit(answer, answer.lower(), None, 65.0)
    reviewed_short = PILOT_SAFE_SHORT if args.short_domain == "safe" else OWNER_SHORT
    for answer in reviewed_short:
        if len(answer) == 3:
            admit(answer, answer.lower(), None, 65.0)

    word5 = words_by_length[5]
    word6 = words_by_length[6]
    word7 = sorted(words_by_length[7])
    short3 = sorted(words_by_length[3])
    prefix6: list[set[str]] = [set() for _ in range(6)]
    prefix5: list[set[str]] = [set() for _ in range(5)]
    for word in word6:
        for size in range(6):
            prefix6[size].add(word[:size])
    for word in word5:
        for size in range(5):
            prefix5[size].add(word[:size])

    masks = [[0 for _ in range(26)] for _ in range(7)]
    for index, word in enumerate(word7):
        bit = 1 << index
        for position, letter in enumerate(word):
            masks[position][ord(letter) - 65] |= bit
    all_columns = (1 << len(word7)) - 1

    next_letters6: list[dict[str, set[str]]] = [defaultdict(set) for _ in range(5)]
    next_letters5: list[dict[str, set[str]]] = [defaultdict(set) for _ in range(5)]
    for word in word6:
        for size in range(5):
            next_letters6[size][word[:size]].add(word[size])
    for word in word5:
        for size in range(5):
            next_letters5[size][word[:size]].add(word[size])

    rng = random.Random(args.seed)
    started = time.monotonic()
    deadline = started + args.seconds
    nodes = 0
    complete = 0
    diversity_rejected = 0
    best: tuple | None = None
    best_assignment: dict[int, str] | None = None

    avoided: list[dict[int, str]] = []
    for path in args.avoid_fill:
        document = json.loads(path.read_text(encoding="utf-8"))
        candidate = document.get("answers")
        if isinstance(candidate, list):
            assignment = {
                int(item["slotIndex"]): normalized(str(item["answer"]))
                for item in candidate
                if isinstance(item, dict) and "slotIndex" in item and item.get("answer")
            }
            if assignment:
                avoided.append(assignment)

    def valid_complete(answers: dict[int, str]) -> tuple | None:
        nonlocal complete, diversity_rejected
        values = list(answers.values())
        answer_families = [families[word] for word in values]
        if len(values) != len(set(values)) or len(answer_families) != len(set(answer_families)):
            return None
        if sum(word in GRAMMAR_ANSWERS for word in values) > args.maximum_grammar_answers:
            return None
        unfamiliar = sum(
            len(word) > 3 and zipf.get(word, 0.0) < args.minimum_familiarity_zipf
            for word in values
        )
        if unfamiliar > args.max_unfamiliar_answers:
            return None
        if avoided:
            nearest = min(
                sum(answers.get(slot) != answer for slot, answer in reference.items())
                for reference in avoided
            )
            if nearest < args.minimum_solution_distance:
                diversity_rejected += 1
                return None
        complete += 1
        scores = [score[word] for word in values]
        usages = [active.get(word, 0) for word in values]
        return (
            min(scores),
            -sum(value < 20 for value in scores),
            sum(scores),
            -sum(use > 0 for use in usages),
            -sum(usages),
        )

    def finish(columns_chosen: list[str], row_prefixes: list[str]) -> None:
        nonlocal best, best_assignment
        centre = row_prefixes[3]
        if centre not in word5:
            return
        top_options = []
        bottom_options = []
        for short in short3:
            top_rows = [row_prefixes[row] + short[row] for row in range(3)]
            if all(word in word6 for word in top_rows):
                top_options.append((short, top_rows))
            bottom_rows = [row_prefixes[row] + short[row - 4] for row in range(4, 7)]
            if all(word in word6 for word in bottom_rows):
                bottom_options.append((short, bottom_rows))
        for top_short, top_rows in top_options:
            for bottom_short, bottom_rows in bottom_options:
                answers = {
                    0: columns_chosen[0], 1: columns_chosen[1], 2: columns_chosen[2],
                    3: columns_chosen[3], 4: columns_chosen[4], 5: top_short,
                    6: top_rows[0], 7: top_rows[1], 8: top_rows[2], 9: centre,
                    10: bottom_short, 11: bottom_rows[0], 12: bottom_rows[1],
                    13: bottom_rows[2],
                }
                quality = valid_complete(answers)
                if quality is not None and (best is None or quality > best):
                    best = quality
                    best_assignment = answers

    def search(columns_chosen: list[str], row_prefixes: list[str]) -> None:
        nonlocal nodes
        if time.monotonic() >= deadline or complete >= args.solution_limit:
            return
        nodes += 1
        depth = len(columns_chosen)
        if depth == 5:
            finish(columns_chosen, row_prefixes)
            return
        domain = all_columns
        for row, prefix in enumerate(row_prefixes):
            allowed = (
                next_letters5[depth].get(prefix, set())
                if row == 3 else next_letters6[depth].get(prefix, set())
            )
            position_mask = 0
            for letter in allowed:
                position_mask |= masks[row][ord(letter) - 65]
            domain &= position_mask
            if not domain:
                return
        candidates = list(bits(domain))
        rng.shuffle(candidates)
        candidates.sort(key=lambda index: -int(score[word7[index]] // 5))
        used_families = {families[word] for word in columns_chosen}
        for index in candidates:
            word = word7[index]
            if word in columns_chosen or families[word] in used_families:
                continue
            search(columns_chosen + [word], [prefix + word[row] for row, prefix in enumerate(row_prefixes)])
            if time.monotonic() >= deadline or complete >= args.solution_limit:
                return

    search([], [""] * 7)
    elapsed = round(time.monotonic() - started, 3)
    payload = {
        "version": 1,
        "kind": "corrected-7x8-column-first-fill",
        "sourceShapeId": shape_id,
        "sourceShapeFile": str(args.shape_file),
        "columns": columns,
        "rows": rows,
        "clueCells": clues,
        "rawSlots": raw_slots,
        "complete": best_assignment is not None,
        "publicationEligible": False,
        "catalogModified": False,
        "candidateCounts": {str(length): len(words) for length, words in words_by_length.items()},
        "telemetry": {
            "solver": "column-first-prefix-csp",
            "nodes": nodes,
            "elapsedSeconds": elapsed,
            "completeSolutions": complete,
            "diversityRejectedSolutions": diversity_rejected,
            "avoidedFillCount": len(avoided),
            "minimumSolutionDistance": args.minimum_solution_distance,
            "solutionLimit": args.solution_limit,
            "reason": "solved" if best_assignment else (
                "timeout" if time.monotonic() >= deadline else "infeasible"
            ),
            "bestQuality": list(best) if best is not None else None,
        },
        "answers": [],
    }
    if best_assignment:
        payload["answers"] = [
            {
                "slotIndex": index,
                "slotId": raw_slots[index]["slotId"],
                "answer": answer,
                "spelling": spelling[answer],
                "lemma": families[answer],
                "wordfreqZipf": zipf[answer],
                "constructorScore": metadata[answer].get("constructorScore"),
                "partOfSpeech": metadata[answer].get("partOfSpeech"),
                "formType": metadata[answer].get("formType"),
            }
            for index, answer in sorted(best_assignment.items())
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "complete": payload["complete"],
        "answers": [item["answer"] for item in payload["answers"]],
        "telemetry": payload["telemetry"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if best_assignment else 1


if __name__ == "__main__":
    raise SystemExit(main())
