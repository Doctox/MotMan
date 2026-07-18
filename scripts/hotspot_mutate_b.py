"""Hotspot-guided topology mutations for the MotsFlex-inspired B adapter.

The script deliberately separates three stages:

1. a small diagnostic probe counts slots/crossings that kill partial fills;
2. at most twelve local clue-cell mutations are ranked without a long search;
3. only four balanced finalists receive a bounded beam search.

It is a clean Python implementation.  The active catalog is read-only.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as gen
from audit_active_answer_repetition import build_lexical_families
from editorial_quality import editorial_errors, grid_semantic_errors, valid_image
from grid_topology import audit_grid_topology
from motsflex_adapter_b import PREFERRED, WEAK, derive_slots, topologies


@dataclass(frozen=True)
class SearchState:
    assigned: tuple[tuple[int, str], ...]
    active_rare: int = 0
    quality: float = 0.0


def maximal_runs(clues: set[tuple[int, int]], direction: str):
    dr, dc = ((0, 1) if direction == "across" else (1, 0))
    letters = {(row, col) for row in range(10) for col in range(9)} - clues
    runs = []
    for cell in sorted(letters):
        previous = (cell[0] - dr, cell[1] - dc)
        if previous in letters:
            continue
        current = cell
        run = []
        while current in letters:
            run.append(current)
            current = (current[0] + dr, current[1] + dc)
        runs.append(tuple(run))
    return runs


def topology_errors(clues: set[tuple[int, int]]) -> list[str]:
    """Strict geometry-only gate matching the visible arrowword contract."""
    errors = []
    if (0, 0) not in clues:
        errors.append("missing-neutral-corner")
    slots = derive_slots(clues)
    lengths = Counter(len(slot.cells) for slot in slots)
    if lengths[2] > 1:
        errors.append("more-than-one-length-2")
    if lengths[3] > 9:
        errors.append("more-than-nine-length-3")
    if not 18 <= len(slots) <= 28:
        errors.append("implausible-slot-count")

    coverage = defaultdict(list)
    declared = {"across": set(), "down": set()}
    used_clues = set()
    for index, slot in enumerate(slots):
        declared[slot.direction].add(tuple(slot.cells))
        used_clues.add(slot.clue)
        for cell in slot.cells:
            coverage[cell].append(index)
    for row in range(10):
        for col in range(9):
            cell = (row, col)
            if cell not in clues and not coverage[cell]:
                errors.append("uncovered-letter")
                break

    # Every visible run of two or more letters must be an actual entry.  Runs
    # of one cell are permitted only as crossings/portions of the other axis.
    for direction in ("across", "down"):
        for run in maximal_runs(clues, direction):
            if len(run) >= 2 and run not in declared[direction]:
                errors.append(f"orphan-{direction}-run")

    for clue in clues - {(0, 0)}:
        if clue not in used_clues:
            errors.append("isolated-clue")
            break
    return sorted(set(errors))


class CorpusContext:
    def __init__(self):
        self.entries = gen.load_entries()
        indexes = gen.build_index(self.entries, min_frequency=1, difficulty="normal")
        (self.by_length, _, self.frequency, self.concept_group,
         self.semantic_conflicts, _, indexed_images) = indexes

        self.entry_by = {}
        self.image_by = {}
        for entry in self.entries:
            answer = entry["answer"]
            score = (6 if entry.get("editorialStatus") == "human-reviewed" else 0)
            score += 3 if entry.get("clue") else 0
            source_id = str(entry.get("sourceId", "")).lower()
            score += 2 if any(marker in source_id for marker in PREFERRED) else 0
            if answer not in self.entry_by or score > self.entry_by[answer][0]:
                self.entry_by[answer] = (score, entry)
            if answer in indexed_images and valid_image(entry.get("image"), ROOT):
                self.image_by[answer] = entry

        catalog = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
        blacklist = json.loads((ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8"))
        quarantined = set(blacklist.get("quarantinedGridIds", []))
        self.active_usage = Counter(
            word["answer"]
            for grid in catalog["grids"] if grid["id"] not in quarantined
            for word in grid["words"]
        )
        forms = sorted({word for words in self.by_length.values() for word in words} | set(self.active_usage))
        family, _ = build_lexical_families(forms)
        family_usage = Counter()
        for answer, count in self.active_usage.items():
            family_usage[family.get(answer, answer)] += count
        frequent = {answer for answer in forms if family_usage[family.get(answer, answer)] >= 2}
        source_answers = {word["answer"] for word in topologies()[1]["words"]}
        self.excluded = WEAK | source_answers | frequent
        self.pools = {
            length: tuple(word for word in words if word not in self.excluded)
            for length, words in self.by_length.items()
        }
        self.source_score = {}
        for answer in forms:
            entry = self.entry_by.get(answer, (0, {}))[1]
            source_id = str(entry.get("sourceId", "")).lower()
            score = 6 if any(marker in source_id for marker in PREFERRED) else 0
            self.source_score[answer] = score + math.log1p(float(self.frequency.get(answer, 0)))


def initial_metrics(clues: set[tuple[int, int]], ctx: CorpusContext) -> dict:
    slots = derive_slots(clues)
    owners = defaultdict(list)
    for index, slot in enumerate(slots):
        for position, cell in enumerate(slot.cells):
            owners[cell].append((index, position))
    ratios = []
    letter_mass = 0.0
    cell_metrics = []
    for cell, linked in owners.items():
        if len(linked) != 2:
            continue
        (left, lp), (right, rp) = linked
        left_pool = ctx.pools.get(len(slots[left].cells), ())
        right_pool = ctx.pools.get(len(slots[right].cells), ())
        lc = Counter(word[lp] for word in left_pool)
        rc = Counter(word[rp] for word in right_pool)
        support = sum(min(lc[letter], rc[letter]) for letter in set(lc) & set(rc))
        denominator = max(1, min(len(left_pool), len(right_pool)))
        ratio = support / denominator
        ratios.append(ratio)
        letter_mass += math.log1p(support)
        cell_metrics.append({"cell": list(cell), "support": support, "ratio": round(ratio, 6)})
    domain_mass = sum(math.log1p(len(ctx.pools.get(len(slot.cells), ()))) for slot in slots)
    lengths = Counter(len(slot.cells) for slot in slots)
    viability = (
        80 * min(ratios, default=0)
        + 12 * (sum(ratios) / max(1, len(ratios)))
        + letter_mass / max(1, len(ratios))
        + domain_mass / max(1, len(slots))
        - lengths[2] * 7 - lengths[3] * 0.8
    )
    return {
        "score": round(viability, 6),
        "domainMass": round(domain_mass, 3),
        "letterMass": round(letter_mass, 3),
        "minimumCrossingRatio": round(min(ratios, default=0), 6),
        "meanCrossingRatio": round(sum(ratios) / max(1, len(ratios)), 6),
        "slotLengths": dict(sorted(lengths.items())),
        "slotCount": len(slots),
        "weakestCells": sorted(cell_metrics, key=lambda item: (item["ratio"], item["support"]))[:8],
    }


def run_beam(
    clues: set[tuple[int, int]], ctx: CorpusContext, *, seconds: float,
    beam_width: int, branch_width: int, max_expanded: int | None = None,
    used_batch: set[str] | None = None, require_six_images: bool = False,
    seed: int = 260717,
):
    slots = derive_slots(clues)
    owners = defaultdict(list)
    for index, slot in enumerate(slots):
        for position, cell in enumerate(slot.cells):
            owners[cell].append((index, position))
    used_batch = used_batch or set()
    rng = random.Random(seed)
    started = time.monotonic()
    expanded = 0
    max_depth = 0
    dead = Counter()
    slot_extinctions = Counter()
    cell_extinctions = Counter()
    chosen_slots = Counter()
    completed_without_images = 0

    @lru_cache(maxsize=200_000)
    def pattern_candidates(slot_index: int, pattern: tuple[str | None, ...]):
        return tuple(
            word for word in ctx.pools.get(len(slots[slot_index].cells), ())
            if all(letter is None or word[position] == letter for position, letter in enumerate(pattern))
        )

    def domains(state: SearchState):
        assigned = dict(state.assigned)
        letters = {}
        used = set(assigned.values()) | used_batch
        groups = {ctx.concept_group.get(word, word) for word in used}
        for index, word in assigned.items():
            for position, cell in enumerate(slots[index].cells):
                letters[cell] = word[position]
        result = {}
        zero = []
        for index, slot in enumerate(slots):
            if index in assigned:
                continue
            pattern = tuple(letters.get(cell) for cell in slot.cells)
            candidates = tuple(
                word for word in pattern_candidates(index, pattern)
                if word not in used
                and ctx.concept_group.get(word, word) not in groups
                and not any(conflict in groups for conflict in ctx.semantic_conflicts.get(word, set()))
            )
            if not candidates:
                zero.append(index)
            else:
                result[index] = candidates
        return (None, zero, letters) if zero else (result, [], letters)

    def record_zero(zero_slots, letters):
        for index in zero_slots:
            slot_extinctions[index] += 1
            for cell in slots[index].cells:
                if cell in letters and len(owners[cell]) == 2:
                    cell_extinctions[cell] += 1

    def heat(state, current):
        assigned = dict(state.assigned)
        total = 0.0
        for cell, linked in owners.items():
            if len(linked) != 2:
                continue
            (left, lp), (right, rp) = linked
            if left in assigned and right in assigned:
                continue
            lc = Counter([assigned[left][lp]]) if left in assigned else Counter(word[lp] for word in current[left])
            rc = Counter([assigned[right][rp]]) if right in assigned else Counter(word[rp] for word in current[right])
            support = sum(min(lc[letter], rc[letter]) for letter in set(lc) & set(rc))
            if support == 0:
                cell_extinctions[cell] += 1
                return -math.inf
            total += math.log1p(support)
        return total + len(assigned) * 18 + state.quality - state.active_rare * 8

    beam = [SearchState(())]
    solved = None
    while beam and time.monotonic() - started < seconds:
        if max_expanded is not None and expanded >= max_expanded:
            break
        next_states = []
        for state in beam:
            current, zero, letters = domains(state)
            if current is None:
                dead["zero-domain"] += 1
                record_zero(zero, letters)
                continue
            if not current:
                image_count = sum(word in ctx.image_by for _, word in state.assigned)
                if require_six_images and image_count < 6:
                    completed_without_images += 1
                    dead["completed-fewer-than-six-images"] += 1
                    continue
                solved = state
                break
            slot_index = min(current, key=lambda index: (len(current[index]), -len(slots[index].cells), index))
            chosen_slots[slot_index] += 1
            ranked = []
            for word in current[slot_index]:
                support = 0.0
                impossible = False
                for position, cell in enumerate(slots[slot_index].cells):
                    for other, other_position in owners[cell]:
                        if other == slot_index or other not in current:
                            continue
                        matches = sum(candidate[other_position] == word[position] for candidate in current[other])
                        if matches == 0:
                            cell_extinctions[cell] += 1
                            impossible = True
                            break
                        support += math.log1p(matches)
                    if impossible:
                        break
                if impossible:
                    continue
                # Images remain an editorial choice after a complete fill; the
                # small preference only breaks otherwise comparable branches.
                quality = ctx.source_score.get(word, 0)
                quality += 4 if word in ctx.image_by else 0
                quality -= 20 * int(ctx.active_usage[word] == 1)
                ranked.append((support + quality, word))
            if not ranked:
                dead["no-supported-candidate"] += 1
                slot_extinctions[slot_index] += 1
                continue
            ranked.sort(reverse=True)
            head = ranked[: branch_width * 2]
            rng.shuffle(head)
            head.sort(reverse=True)
            for _, word in head[:branch_width]:
                rare = state.active_rare + int(ctx.active_usage[word] == 1)
                if rare > 3:
                    dead["rare-repeat-cap"] += 1
                    continue
                quality = state.quality + ctx.source_score.get(word, 0) + (4 if word in ctx.image_by else 0)
                child = SearchState(tuple(sorted((*state.assigned, (slot_index, word)))), rare, quality)
                max_depth = max(max_depth, len(child.assigned))
                child_domains, zero, child_letters = domains(child)
                expanded += 1
                if child_domains is None:
                    dead["zero-domain"] += 1
                    record_zero(zero, child_letters)
                    continue
                score = heat(child, child_domains)
                if score != -math.inf:
                    next_states.append((score, child))
                if max_expanded is not None and expanded >= max_expanded:
                    break
            if solved or (max_expanded is not None and expanded >= max_expanded):
                break
        if solved:
            break
        deduplicated = {}
        for score, state in sorted(next_states, key=lambda item: item[0], reverse=True):
            deduplicated.setdefault(state.assigned, (score, state))
            if len(deduplicated) >= beam_width:
                break
        beam = [state for _, state in deduplicated.values()]

    report = {
        "solved": solved is not None,
        "expandedStates": expanded,
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "bestAssigned": max(max_depth, max((len(state.assigned) for state in beam), default=0)),
        "deadStates": dict(dead),
        "completedWithoutSixImages": completed_without_images,
        "slotExtinctions": [
            {"slot": index, "count": count, "direction": slots[index].direction,
             "clueCell": list(slots[index].clue), "length": len(slots[index].cells)}
            for index, count in slot_extinctions.most_common()
        ],
        "cellExtinctions": [
            {"cell": list(cell), "count": count} for cell, count in cell_extinctions.most_common()
        ],
        "chosenSlots": [
            {"slot": index, "count": count, "direction": slots[index].direction,
             "clueCell": list(slots[index].clue), "length": len(slots[index].cells)}
            for index, count in chosen_slots.most_common()
        ],
    }
    return solved, report


def mutations_for(base_id: str, clues: set[tuple[int, int]], hotspots, ctx: CorpusContext):
    hot = [tuple(item["cell"]) for item in hotspots[:8]]
    if not hot:
        hot = [tuple(item["cell"]) for item in initial_metrics(clues, ctx)["weakestCells"]]

    def near_hot(cell, radius=2):
        return min((abs(cell[0] - h[0]) + abs(cell[1] - h[1]) for h in hot), default=99) <= radius

    mutable_clues = [cell for cell in clues if cell != (0, 0) and cell[0] > 0 and near_hot(cell, 3)]
    nearby_letters = [
        (row, col) for row in range(1, 10) for col in range(9)
        if (row, col) not in clues and near_hot((row, col), 2)
    ]
    # Geometry repairs known from the diagnostics are always represented in
    # the small universe, not hard-coded as selected winners.
    # (6,1) is the bridge repair for both lineages: in V1 it replaces the two
    # neighbouring definitions, while in V2 it turns the border run into a
    # declared entry without creating a second two-letter slot.
    forced = {(6, 0), (6, 1), (6, 2), (8, 5)}
    universe = list(dict.fromkeys(
        [cell for cell in forced if cell != (0, 0)]
        + mutable_clues[:7] + nearby_letters[:8]
    ))[:15]
    candidates = []
    seen = set()
    for edit_count in (1, 2, 3):
        for changed in itertools.combinations(universe, edit_count):
            mutated = set(clues)
            for cell in changed:
                if cell in mutated:
                    mutated.remove(cell)
                else:
                    mutated.add(cell)
            signature = tuple(sorted(mutated))
            if signature in seen:
                continue
            seen.add(signature)
            errors = topology_errors(mutated)
            if errors:
                continue
            metrics = initial_metrics(mutated, ctx)
            candidates.append({
                "baseId": base_id,
                "clues": mutated,
                "changes": [list(cell) for cell in changed],
                "removed": [list(cell) for cell in changed if cell in clues],
                "added": [list(cell) for cell in changed if cell not in clues],
                "editCount": edit_count,
                "initialMetrics": metrics,
            })
    candidates.sort(key=lambda item: (item["initialMetrics"]["score"], -item["editCount"]), reverse=True)
    return candidates


def build_grid(grid_id: str, clues, solved: SearchState, ctx: CorpusContext):
    slots = derive_slots(clues)
    answers = dict(solved.assigned)
    image_answers = sorted(
        (answer for answer in answers.values() if answer in ctx.image_by),
        key=lambda answer: (-len(answer), answer),
    )[:6]
    image_set = set(image_answers)
    words = []
    for index, slot in enumerate(slots):
        answer = answers[index]
        entry = ctx.entry_by[answer][1]
        word = {
            "wordId": f"{grid_id}:word:{index + 1:02d}",
            "answer": answer,
            "clue": entry.get("clue", ""),
            "sourceClue": entry.get("sourceClue", entry.get("clue", "")),
            "sourceId": entry.get("sourceId"),
            "sourceUrl": entry.get("sourceUrl"),
            "sourceType": entry.get("sourceType"),
            "editorialStatus": "agent-review-required",
            "conceptGroup": entry.get("conceptGroup", answer),
            "semanticConflicts": entry.get("semanticConflicts", []),
            "direction": slot.direction,
            "arrow": slot.arrow,
            "clueCell": list(slot.clue),
            "cells": [list(cell) for cell in slot.cells],
        }
        if answer in image_set:
            image_entry = ctx.image_by[answer]
            word.update(
                clue="", sourceClue=image_entry.get("sourceClue", image_entry.get("clue", "")),
                sourceId=image_entry.get("sourceId"), sourceUrl=image_entry.get("sourceUrl"),
                sourceType="image", editorialStatus="image-reviewed", image=image_entry["image"],
            )
        words.append(word)
    return {
        "id": grid_id,
        "columns": 9,
        "rows": 10,
        "editorialProfile": "motsflex-hotspot-mutated-b",
        "clueCells": [list(cell) for cell in sorted(clues)],
        "words": words,
        "publicationStatus": "owner-review-required",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-states", type=int, default=220)
    parser.add_argument("--seconds", type=float, default=24)
    parser.add_argument("--beam", type=int, default=20)
    parser.add_argument("--branch", type=int, default=10)
    parser.add_argument("--output", type=Path, default=ROOT / "output/quality/hotspot-mutated-b.json")
    args = parser.parse_args()
    ctx = CorpusContext()
    bases = topologies()[0]

    diagnostics = []
    candidate_pool = []
    for base_id, clues in bases:
        _, probe = run_beam(
            clues, ctx, seconds=8, beam_width=8, branch_width=6,
            max_expanded=args.probe_states, require_six_images=False,
            seed=260717 + len(diagnostics),
        )
        base_errors = topology_errors(clues)
        diagnostics.append({
            "baseId": base_id,
            "topologyErrors": base_errors,
            "initialMetrics": initial_metrics(clues, ctx),
            "probe": probe,
        })
        candidates = mutations_for(base_id, clues, probe["cellExtinctions"], ctx)
        candidate_pool.extend(candidates[:6])

    candidate_pool.sort(key=lambda item: item["initialMetrics"]["score"], reverse=True)
    candidate_pool = candidate_pool[:12]
    for rank, candidate in enumerate(candidate_pool, 1):
        candidate["rank"] = rank

    # Four tests maximum, balanced across the two requested lineages so that a
    # one-sided ranking cannot consume every expensive run.
    finalists = []
    for base_id, _ in bases:
        finalists.extend([item for item in candidate_pool if item["baseId"] == base_id][:2])
    finalists.sort(key=lambda item: item["initialMetrics"]["score"], reverse=True)

    used_batch = set()
    solved_bases = set()
    grids = []
    test_reports = []
    for test_index, candidate in enumerate(finalists[:4], 1):
        solved, report = run_beam(
            candidate["clues"], ctx, seconds=args.seconds,
            beam_width=args.beam, branch_width=args.branch,
            used_batch=used_batch, require_six_images=True,
            seed=270000 + test_index,
        )
        report.update({
            "testIndex": test_index,
            "candidateRank": candidate["rank"],
            "baseId": candidate["baseId"],
            "changes": candidate["changes"],
        })
        if solved is not None and candidate["baseId"] not in solved_bases:
            grid_id = f"hotspot-mutated-b-{len(grids) + 1:02d}"
            grid = build_grid(grid_id, candidate["clues"], solved, ctx)
            editorial = []
            for word in grid["words"]:
                editorial.extend({"wordId": word["wordId"], **error} for error in editorial_errors(word, root=ROOT))
            editorial.extend(grid_semantic_errors(grid["words"]))
            topology = audit_grid_topology(grid)
            report["topologyValid"] = topology["valid"]
            report["editorialErrors"] = editorial
            report["imageCount"] = sum("image" in word for word in grid["words"])
            if topology["valid"] and not editorial and report["imageCount"] == 6:
                grids.append(grid)
                solved_bases.add(candidate["baseId"])
                used_batch.update(word["answer"] for word in grid["words"])
            else:
                report["solved"] = False
                report["rejectedAfterFill"] = True
        test_reports.append(report)

    serial_candidates = []
    for item in candidate_pool:
        serial_candidates.append({key: value for key, value in item.items() if key != "clues"})
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.write_text(json.dumps({
        "version": 1,
        "kind": "motman-hotspot-guided-motsflex-mutations-b",
        "licenseReference": "MotsFlex inspected locally under MIT; clean Python adaptation, no copied source.",
        "policy": {
            "maximumMutationsRanked": 12,
            "maximumFinalistsTested": 4,
            "maximumLength3Slots": 9,
            "maximumLength2Slots": 1,
            "maximumRareActiveRepeats": 3,
            "requiredConcreteImagesAfterFill": 6,
            "beamWidth": args.beam,
            "branchWidth": args.branch,
            "secondsPerFinalist": args.seconds,
        },
        "baseDiagnostics": diagnostics,
        "rankedMutations": serial_candidates,
        "testedFinalists": test_reports,
        "grids": grids,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "rankedMutations": len(serial_candidates),
        "testedFinalists": len(test_reports),
        "grids": len(grids),
        "reports": [
            {key: report.get(key) for key in (
                "testIndex", "candidateRank", "baseId", "solved", "expandedStates",
                "bestAssigned", "imageCount", "topologyValid", "rejectedAfterFill",
            )}
            for report in test_reports
        ],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
