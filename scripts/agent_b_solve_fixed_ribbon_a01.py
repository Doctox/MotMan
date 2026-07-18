"""Exact agent-B feasibility search for the immutable ribbon A01 shape.

This is deliberately not a grid generator: the shape and its 22 paths are read
verbatim from the approved review artifact.  CP-SAT only chooses one already
reviewed central-corpus answer per fixed path and enforces every crossing.
"""
from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import sys

from ortools.sat.python import cp_model


ROOT = Path(__file__).resolve().parents[1]
SHAPE_PATH = ROOT / "output/quality/reference-style-shapes-a.json"
CENTRAL_PATH = ROOT / "src/data/crossword.central.json.gz"
CATALOG_PATH = ROOT / "src/data/grid.catalog.json"
OUTPUT_PATH = ROOT / "output/quality/agent-b-ribbon-a01-fill.json"
SHAPE_ID = "reference-ribbon-a-01"
ALLOWED_STATUSES = {"source-backed", "human-reviewed", "image-reviewed"}
MINIMUM_IMAGES = 6


def load_shape() -> dict:
    payload = json.loads(SHAPE_PATH.read_text(encoding="utf-8"))
    matches = [shape for shape in payload.get("shapes", []) if shape.get("id") == SHAPE_ID]
    if len(matches) != 1:
        raise RuntimeError(f"Silhouette {SHAPE_ID!r} introuvable ou dupliquée")
    shape = matches[0]
    if len(shape.get("slots", [])) != 22:
        raise RuntimeError("La silhouette A01 ne possède plus exactement 22 slots")
    return shape


def entry_score(entry: dict, active_counts: Counter[str]) -> tuple:
    answer = entry.get("answer", "")
    return (
        1 if entry.get("sourceType") == "image" and entry.get("image") else 0,
        1 if entry.get("editorialStatus") == "human-reviewed" else 0,
        1 if entry.get("generatorEligible") else 0,
        1 if entry.get("sourceType") == "crossword" else 0,
        -active_counts[answer],
        float(entry.get("frequency") or 0),
    )


def load_candidates(lengths: set[int]) -> tuple[dict[int, list[str]], dict[str, dict], dict[str, dict], dict]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    active_counts = Counter(
        word.get("answer", "")
        for grid in catalog.get("grids", [])
        for word in grid.get("words", [])
    )
    with gzip.open(CENTRAL_PATH, "rt", encoding="utf-8") as handle:
        central = json.load(handle)

    entries_by_answer: dict[str, list[dict]] = defaultdict(list)
    status_counts: Counter[str] = Counter()
    accepted_entry_count = 0
    for entry in central.get("entries", []):
        answer = entry.get("answer", "")
        if len(answer) not in lengths:
            continue
        if entry.get("editorialStatus") not in ALLOWED_STATUSES:
            continue
        if not entry.get("clue") and not entry.get("image"):
            continue
        entries_by_answer[answer].append(entry)
        accepted_entry_count += 1
        status_counts[str(entry.get("editorialStatus"))] += 1

    best_entry: dict[str, dict] = {}
    best_image_entry: dict[str, dict] = {}
    for answer, entries in entries_by_answer.items():
        best_entry[answer] = max(entries, key=lambda entry: entry_score(entry, active_counts))
        images = [entry for entry in entries if entry.get("sourceType") == "image" and entry.get("image")]
        if images:
            best_image_entry[answer] = max(images, key=lambda entry: entry_score(entry, active_counts))

    candidates_by_length: dict[int, list[str]] = defaultdict(list)
    for answer in best_entry:
        candidates_by_length[len(answer)].append(answer)
    for length, answers in candidates_by_length.items():
        answers.sort(
            key=lambda answer: (
                answer in best_image_entry,
                -active_counts[answer],
                entry_score(best_entry[answer], active_counts),
                answer,
            ),
            reverse=True,
        )

    metrics = {
        "centralEntryCount": len(central.get("entries", [])),
        "acceptedEntryRows": accepted_entry_count,
        "uniqueAcceptedAnswers": len(best_entry),
        "candidateCountsByLength": {
            str(length): len(candidates_by_length.get(length, [])) for length in sorted(lengths)
        },
        "imageAnswerCountsByLength": {
            str(length): sum(
                answer in best_image_entry for answer in candidates_by_length.get(length, [])
            )
            for length in sorted(lengths)
        },
        "acceptedRowsByEditorialStatus": dict(sorted(status_counts.items())),
        "activeCatalogGridCount": len(catalog.get("grids", [])),
    }
    return dict(candidates_by_length), best_entry, best_image_entry, metrics


def build_model(shape: dict, candidates_by_length: dict[int, list[str]], *, require_images: bool):
    model = cp_model.CpModel()
    slots = shape["slots"]
    all_answers = sorted({answer for answers in candidates_by_length.values() for answer in answers})
    global_answer_id = {answer: index for index, answer in enumerate(all_answers)}

    slot_choice = []
    slot_global_id = []
    slot_image = []
    cell_letters: dict[tuple[int, int], cp_model.IntVar] = {}

    for slot_index, slot in enumerate(slots):
        length = slot["length"]
        answers = candidates_by_length.get(length, [])
        if not answers:
            raise RuntimeError(f"Aucun candidat de longueur {length}")
        choice = model.new_int_var(0, len(answers) - 1, f"choice_{slot_index:02d}")
        answer_id = model.new_int_var(0, len(all_answers) - 1, f"answer_id_{slot_index:02d}")
        image = model.new_int_var(0, 1, f"image_{slot_index:02d}")
        model.add_element(choice, [global_answer_id[answer] for answer in answers], answer_id)
        model.add_element(
            choice,
            [int(any(
                entry.get("sourceType") == "image" and entry.get("image")
                for entry in _ENTRIES_BY_ANSWER[answer]
            )) for answer in answers],
            image,
        )
        slot_choice.append(choice)
        slot_global_id.append(answer_id)
        slot_image.append(image)

        for position, raw_cell in enumerate(slot["cells"]):
            cell = tuple(raw_cell)
            letter = cell_letters.setdefault(
                cell, model.new_int_var(0, 25, f"cell_{cell[0]}_{cell[1]}")
            )
            model.add_element(
                choice,
                [ord(answer[position]) - ord("A") for answer in answers],
                letter,
            )

    model.add_all_different(slot_global_id)
    if require_images:
        model.add(sum(slot_image) >= MINIMUM_IMAGES)
    return model, slot_choice, slot_image


def solve_once(model: cp_model.CpModel, *, seconds: float) -> tuple[cp_model.CpSolver, int, dict]:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.cp_model_presolve = True
    solver.parameters.symmetry_level = 2
    status = solver.solve(model)
    telemetry = {
        "status": solver.status_name(status),
        "wallTimeSeconds": solver.wall_time,
        "userTimeSeconds": solver.user_time,
        "branches": solver.num_branches,
        "conflicts": solver.num_conflicts,
        "responseStats": solver.response_stats(),
    }
    return solver, status, telemetry


def candidate_entry_maps(lengths: set[int]):
    """Populate exact source rows used by the CP-SAT image indicators."""
    with gzip.open(CENTRAL_PATH, "rt", encoding="utf-8") as handle:
        central = json.load(handle)
    result: dict[str, list[dict]] = defaultdict(list)
    for entry in central.get("entries", []):
        answer = entry.get("answer", "")
        if (
            len(answer) in lengths
            and entry.get("editorialStatus") in ALLOWED_STATUSES
            and (entry.get("clue") or entry.get("image"))
        ):
            result[answer].append(entry)
    return result


def main() -> None:
    shape = load_shape()
    lengths = {slot["length"] for slot in shape["slots"]}
    global _ENTRIES_BY_ANSWER
    _ENTRIES_BY_ANSWER = candidate_entry_maps(lengths)
    candidates_by_length, best_entry, best_image_entry, corpus_metrics = load_candidates(lengths)

    base_model, base_choice, base_images = build_model(
        shape, candidates_by_length, require_images=False
    )
    base_solver, base_status, base_telemetry = solve_once(base_model, seconds=180.0)

    payload = {
        "version": 1,
        "kind": "agent-b-fixed-ribbon-a01-exact-search",
        "generatedOn": str(date.today()),
        "shapeId": SHAPE_ID,
        "shapeSource": str(SHAPE_PATH.relative_to(ROOT)).replace("\\", "/"),
        "shapeFingerprint": shape.get("reproduction", {}).get("fixedMaskDerivedFromSeed"),
        "dimensions": {"columns": shape["columns"], "rows": shape["rows"]},
        "fixedClueCells": shape["clueCells"],
        "fixedSlots": shape["slots"],
        "slotCount": len(shape["slots"]),
        "catalogModified": False,
        "blacklistModified": False,
        "interfaceModified": False,
        "method": {
            "engine": "OR-Tools CP-SAT",
            "exactFixedPaths": True,
            "allCrossingsAsSharedLetterVariables": True,
            "allAnswersDistinct": True,
            "candidatePolicy": sorted(ALLOWED_STATUSES),
            "unreviewedJeuxDeMotsExcluded": True,
            "lexiqueExcluded": True,
            "minimumImagesRequested": MINIMUM_IMAGES,
        },
        "corpusMetrics": corpus_metrics,
        "baseFeasibility": base_telemetry,
    }

    if base_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        payload.update({
            "status": (
                "infeasible-exact-shape"
                if base_status == cp_model.INFEASIBLE
                else "unresolved-time-limit"
            ),
            "grid": None,
            "blockingConclusion": (
                "Aucune affectation des 22 slots n’existe avec les couples déjà relus, "
                "avant même d’imposer les six images."
                if base_status == cp_model.INFEASIBLE
                else "Le solveur exact n’a pas fermé la preuve dans la limite impartie."
            ),
        })
        OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({
            "output": str(OUTPUT_PATH),
            "status": payload["status"],
            "telemetry": base_telemetry,
        }, ensure_ascii=False, indent=2))
        return

    image_model, image_choice, image_flags = build_model(
        shape, candidates_by_length, require_images=True
    )
    image_solver, image_status, image_telemetry = solve_once(image_model, seconds=180.0)
    payload["imageQuotaFeasibility"] = image_telemetry
    if image_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        payload.update({
            "status": "infeasible-six-images" if image_status == cp_model.INFEASIBLE else "unresolved-image-quota",
            "grid": None,
            "blockingConclusion": "La forme se remplit, mais pas avec six réponses-images déjà relues.",
        })
        OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return

    chosen_answers = []
    image_budget = MINIMUM_IMAGES
    words = []
    for index, (slot, choice_var, image_var) in enumerate(
        zip(shape["slots"], image_choice, image_flags), 1
    ):
        answer = candidates_by_length[slot["length"]][image_solver.value(choice_var)]
        use_image = bool(image_solver.value(image_var)) and image_budget > 0
        entry = best_image_entry.get(answer) if use_image else best_entry[answer]
        if use_image:
            image_budget -= 1
        chosen_answers.append(answer)
        words.append({
            "wordId": f"agent-b-ribbon-a01:word:{index:02d}",
            "answer": answer,
            "clue": "" if use_image else entry.get("clue", ""),
            "sourceClue": entry.get("sourceClue", entry.get("clue", "")),
            "sourceId": entry.get("sourceId"),
            "sourceUrl": entry.get("sourceUrl"),
            "sourceType": entry.get("sourceType"),
            "editorialStatus": entry.get("editorialStatus"),
            "definitionStatus": entry.get("definitionStatus", "reviewed"),
            "manualReview": "agent-b-exact-corpus-selection-20260717",
            "conceptGroup": entry.get("conceptGroup", answer),
            "semanticConflicts": entry.get("semanticConflicts", []),
            "direction": slot["direction"],
            "arrow": slot["arrow"],
            "clueCell": slot["clueCell"],
            "cells": slot["cells"],
            **({"image": entry["image"]} if use_image else {}),
        })

    sys.path.insert(0, str(ROOT / "scripts"))
    from grid_topology import audit_grid_topology

    grid = {
        "id": "agent-b-ribbon-a01",
        "columns": shape["columns"],
        "rows": shape["rows"],
        "clueCells": shape["clueCells"],
        "words": words,
        "imageCount": sum("image" in word for word in words),
        "publicationStatus": "owner-review-required",
        "humanReview": "agent-b-exact-corpus-selection-20260717",
    }
    audit = audit_grid_topology(grid, require_word_ids=True, enforce_layout=False)
    payload.update({
        "status": "complete-owner-review-required" if audit["valid"] else "rejected-final-audit",
        "grid": grid,
        "topologyAudit": audit,
        "chosenAnswers": chosen_answers,
    })
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


_ENTRIES_BY_ANSWER: dict[str, list[dict]] = {}


if __name__ == "__main__":
    main()
