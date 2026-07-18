"""Beam-search/heatmap adapter inspired by the MIT MotsFlex strategy.

This is a clean Python implementation for MotMan's fixed arrow-grid slots.  It
does not copy the TypeScript implementation: it reuses the ideas of MRV slot
selection, crossing-letter support, dead-cell pruning and a bounded beam.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as gen
from audit_active_answer_repetition import build_lexical_families

WEAK = set("""
APIS CAC IDES ILL OSIRIS SAURA TURCS TUT ALTERAI AUNEE TRITICALE ASSENANT
CRI CRIS EPEE EPEES RITE RITES CLE CLES AME AMES AN ANS ANE ANES ART ARTS
ERE ERES ILE ILES TETE TETES AIR AMI AMIS ARC ARCS FEU NET OR SEL TIR AGE
AGES BEC EAU EGO
""".split())
PREFERRED = ("leparisien", "ouestfrance", "jeuxdemots")


@dataclass(frozen=True)
class State:
    assigned: tuple[tuple[int, str], ...]
    active_rare: int
    editorial: float


def derive_slots(clues: set[tuple[int, int]]):
    slots = []
    for direction, dr, dc, arrow in (("across", 0, 1, "right"), ("down", 1, 0, "down")):
        for row in range(10):
            for col in range(9):
                if (row, col) not in clues:
                    continue
                cells = []
                r, c = row + dr, col + dc
                while 0 <= r < 10 and 0 <= c < 9 and (r, c) not in clues:
                    cells.append((r, c)); r += dr; c += dc
                if 2 <= len(cells) <= 9:
                    slots.append(gen.Slot(direction, (row, col), tuple(cells), arrow))
    return slots


def topologies():
    refined = json.loads((ROOT / "output/quality/agent-dynamic-c-refined.json").read_text(encoding="utf-8"))
    c02 = next(grid for grid in refined["grids"] if grid["id"] == "dynamic-reference-c-02-refined")
    base = set(map(tuple, c02["clueCells"]))
    v2 = base - {(4, 4), (6, 2), (7, 5), (6, 0)}
    # V1's border removal created UE as an undeclared segment.  Restore [6,0]
    # exactly as in the audited owner-review artifact.
    v1_doc = json.loads((ROOT / "output/quality/agent-merged-v1-renovated-b.json").read_text(encoding="utf-8"))
    v1 = set(map(tuple, v1_doc["grids"][0]["clueCells"]))
    return [("motsflex-adapter-b-v1", v1), ("motsflex-adapter-b-v2", v2)], c02


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--beam", type=int, default=48)
    parser.add_argument("--branch", type=int, default=14)
    parser.add_argument("--seconds", type=float, default=45)
    parser.add_argument("--output", type=Path, default=ROOT / "output/quality/motsflex-adapter-b.json")
    args = parser.parse_args()

    entries = gen.load_entries()
    indexes = gen.build_index(entries, min_frequency=1, difficulty="normal")
    by_length, _, frequency, concept_group, semantic_conflicts, _, image_answers = indexes
    entry_by = {}
    for entry in entries:
        score = (4 if entry.get("editorialStatus") == "human-reviewed" else 0) + (2 if entry.get("clue") else 0)
        if entry["answer"] not in entry_by or score > entry_by[entry["answer"]][0]:
            entry_by[entry["answer"]] = (score, entry)

    catalog = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    blacklist = json.loads((ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8"))
    quarantined = set(blacklist.get("quarantinedGridIds", []))
    active_usage = Counter(
        word["answer"] for grid in catalog["grids"] if grid["id"] not in quarantined
        for word in grid["words"]
    )
    forms = sorted({word for words in by_length.values() for word in words} | set(active_usage))
    family, _ = build_lexical_families(forms)
    family_usage = Counter()
    for answer, count in active_usage.items():
        family_usage[family.get(answer, answer)] += count
    frequent = {answer for answer in forms if family_usage[family.get(answer, answer)] >= 2}

    topology_specs, source_grid = topologies()
    source_answers = {word["answer"] for word in source_grid["words"]}
    excluded = WEAK | source_answers | frequent
    pools = {length: tuple(word for word in words if word not in excluded) for length, words in by_length.items()}
    source_score = {}
    for answer in forms:
        entry = entry_by.get(answer, (0, {}))[1]
        sid = str(entry.get("sourceId", "")).lower()
        source_score[answer] = (6 if any(marker in sid for marker in PREFERRED) else 0) + math.log1p(float(frequency.get(answer, 0)))

    results = []
    reports = []
    used_batch = set()
    rng = random.Random(26075000)
    for grid_id, clues in topology_specs:
        slots = derive_slots(clues)
        cell_owners = defaultdict(list)
        for index, slot in enumerate(slots):
            for position, cell in enumerate(slot.cells):
                cell_owners[cell].append((index, position))
        started = time.monotonic(); expanded = 0; max_depth = 0; dead = Counter()
        beam = [State(assigned=(), active_rare=0, editorial=0.0)]
        solved = None

        def domains(state):
            assigned = dict(state.assigned)
            letters = {}
            used = set(assigned.values()) | used_batch
            groups = {concept_group.get(word, word) for word in used}
            for index, word in assigned.items():
                for pos, cell in enumerate(slots[index].cells): letters[cell] = word[pos]
            result = {}
            for index, slot in enumerate(slots):
                if index in assigned: continue
                candidates = []
                for word in pools.get(len(slot.cells), ()):
                    if word in used or concept_group.get(word, word) in groups: continue
                    if any(letters.get(cell, word[pos]) != word[pos] for pos, cell in enumerate(slot.cells)): continue
                    if any(conflict in groups for conflict in semantic_conflicts.get(word, set())): continue
                    candidates.append(word)
                if not candidates: return None
                result[index] = candidates
            return result

        def heat_score(state, current):
            assigned = dict(state.assigned); total = 0.0
            for cell, owners in cell_owners.items():
                if len(owners) != 2: continue
                (left, lp), (right, rp) = owners
                if left in assigned and right in assigned: continue
                lc = Counter([assigned[left][lp]]) if left in assigned else Counter(word[lp] for word in current[left])
                rc = Counter([assigned[right][rp]]) if right in assigned else Counter(word[rp] for word in current[right])
                support = sum(min(lc[ch], rc[ch]) for ch in set(lc) & set(rc))
                if support == 0: return -math.inf
                total += math.log1p(support)
            return total + len(assigned) * 18 + state.editorial - state.active_rare * 8

        while beam and time.monotonic() - started < args.seconds:
            next_states = []
            for state in beam:
                current = domains(state)
                if current is None: dead["zero-domain"] += 1; continue
                if not current:
                    solved = state; break
                slot_index = min(current, key=lambda index: (len(current[index]), -len(slots[index].cells), index))
                candidates = current[slot_index]
                ranked = []
                for word in candidates:
                    support = 0.0
                    for pos, cell in enumerate(slots[slot_index].cells):
                        for other, other_pos in cell_owners[cell]:
                            if other == slot_index or other not in current: continue
                            matches = sum(candidate[other_pos] == word[pos] for candidate in current[other])
                            if matches == 0: support = -math.inf; break
                            support += math.log1p(matches)
                        if support == -math.inf: break
                    if support != -math.inf:
                        ranked.append((support + source_score.get(word, 0) - 20 * int(active_usage[word] == 1), word))
                ranked.sort(reverse=True)
                # Preserve limited diversity among near-equal choices.
                head = ranked[: args.branch * 2]; rng.shuffle(head); head.sort(reverse=True)
                for _, word in head[:args.branch]:
                    rare = state.active_rare + int(active_usage[word] == 1)
                    if rare > 3: continue
                    child = State(tuple(sorted((*state.assigned, (slot_index, word)))), rare,
                                  state.editorial + source_score.get(word, 0))
                    max_depth = max(max_depth, len(child.assigned))
                    child_domains = domains(child); expanded += 1
                    if child_domains is None: dead["zero-domain"] += 1; continue
                    score = heat_score(child, child_domains)
                    if score != -math.inf: next_states.append((score, child))
            if solved: break
            dedup = {}
            for score, state in sorted(next_states, reverse=True, key=lambda item: item[0]):
                dedup.setdefault(state.assigned, (score, state))
                if len(dedup) >= args.beam: break
            beam = [state for _, state in dedup.values()]
        if solved is None and beam:
            for state in beam:
                if len(state.assigned) == len(slots): solved = state; break

        if solved:
            answers = dict(solved.assigned)
            illustrable = [answer for answer in answers.values() if answer in image_answers]
            if len(illustrable) < 6:
                dead["fewer-than-six-reviewed-images"] += 1; solved = None
        if solved:
            answers = dict(solved.assigned); used_batch.update(answers.values())
            image_set = set(sorted((answer for answer in answers.values() if answer in image_answers), key=lambda a: (-len(a), a))[:6])
            words = []
            for index, slot in enumerate(slots):
                answer = answers[index]; entry = entry_by[answer][1]
                word = {
                    "wordId": f"{grid_id}:word:{index + 1:02d}", "answer": answer,
                    "clue": entry.get("clue", ""), "sourceClue": entry.get("sourceClue", entry.get("clue", "")),
                    "sourceId": entry.get("sourceId"), "sourceUrl": entry.get("sourceUrl"),
                    "sourceType": entry.get("sourceType"), "editorialStatus": "agent-review-required",
                    "conceptGroup": entry.get("conceptGroup", answer), "semanticConflicts": entry.get("semanticConflicts", []),
                    "direction": slot.direction, "arrow": slot.arrow, "clueCell": list(slot.clue),
                    "cells": [list(cell) for cell in slot.cells],
                }
                if answer in image_set and entry.get("image"):
                    word.update(clue="", sourceType="image", editorialStatus="image-reviewed", image=entry["image"])
                words.append(word)
            results.append({"id": grid_id, "columns": 9, "rows": 10, "editorialProfile": "motsflex-beam-adapter",
                            "clueCells": [list(cell) for cell in sorted(clues)], "words": words,
                            "publicationStatus": "owner-review-required"})
        reports.append({"id": grid_id, "solved": solved is not None, "expandedStates": expanded,
                        "elapsedSeconds": round(time.monotonic() - started, 3), "deadStates": dict(dead),
                        "bestAssigned": max(max_depth, max((len(state.assigned) for state in beam), default=0))})

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.write_text(json.dumps({
        "version": 1, "kind": "motman-motsflex-mit-inspired-beam-adapter-b",
        "licenseReference": "MotsFlex repository inspected locally under MIT; clean Python adaptation, no copied source.",
        "policy": {"beamWidth": args.beam, "branchWidth": args.branch, "secondsPerTopology": args.seconds,
                   "maxRareActiveRepeats": 3, "imagesChosenAfterFill": True},
        "reports": reports, "grids": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"grids": len(results), "reports": reports}, ensure_ascii=False))


if __name__ == "__main__": main()
