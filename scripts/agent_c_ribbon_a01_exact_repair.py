"""Audit the exact Agent-C repair of immutable reference-ribbon-a-01.

The answer assignment was found by AC-3 + exact search over whole answers from
the current central corpus and the licensed Morphalou structural staging.  The
script does not invent clues: structural-only forms keep an empty clue and are
explicitly blocked from publication.
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology  # noqa: E402


SHAPE_FILE = ROOT / "output/quality/reference-style-shapes-a.json"
CENTRAL = ROOT / "src/data/crossword.central.json.gz"
MORPHALOU = ROOT / "src/data/crossword.morphalou.staging.json.gz"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
OUTPUT = ROOT / "output/quality/agent-c-ribbon-a01-fill.json"

ANSWERS = {
    0: "RAMAGERAS",
    1: "AMARINERA",
    2: "SENATEURS",
    3: "SUT",
    4: "OTES",
    5: "RELACERAS",
    6: "TRACERAIS",
    7: "SAS",
    8: "RASSORTS",
    9: "AMEUTERA",
    10: "MANTELAS",
    11: "ARA",
    12: "SAC",
    13: "ARNIS",
    14: "SASSE",
    15: "GITA",
    16: "CES",
    17: "VISA",
    18: "ENERVERA",
    19: "REUNIRAS",
    20: "ARRISAIS",
    21: "SASSASSE",
}

ORIGINAL_ASSIGNMENT = {
    0: "RAMARDERA",
    1: "AMARRERAI",
    2: "SENATRICE",
    3: "SUT",
    4: "OTES",
    5: "RELACERAS",
    6: "TRACERAIT",
    7: "ILS",
    8: "RASSORTI",
    9: "AMEUTERA",
    10: "MANTELAS",
    11: "ARA",
    12: "SAC",
    13: "SAGAN",
    14: "SASSE",
    15: "ARTS",
    16: "CES",
    17: "BENI",
    18: "DERABERA",
    19: "ERIGERAS",
    20: "RACINAIS",
    21: "RIENISTE",
}

# Manual editorial gate.  These are lexical forms, not approved pairs.
EDITORIAL_BLOCKERS = {
    "RAMAGERAS": "forme conjuguée de RAMAGER, peu courante et sans définition relue",
    "AMARINERA": "verbe maritime spécialisé, forme future sans définition relue",
    "SENATEURS": "pluriel compréhensible mais couple encore absent du corpus canonique",
    "OTES": "forme conjuguée accentuée en français, sans couple relu dans cette source",
    "RELACERAS": "forme future à la deuxième personne, formulation d'indice à revoir",
    "TRACERAIS": "conditionnel/deuxième personne, formulation d'indice à revoir",
    "RASSORTS": "nom très rare et facilement confondu avec RESSORTS",
    "AMEUTERA": "forme future sans définition relue",
    "MANTELAS": "passé simple d'un verbe rare",
    "ARNIS": "pluriel d'ARNI, réponse obscure pour le jeu",
    "GITA": "passé simple sans définition relue",
    "ENERVERA": "forme future sans définition relue",
    "REUNIRAS": "forme future à la deuxième personne, définition à revoir",
    "ARRISAIS": "verbe nautique spécialisé à l'imparfait",
    "SASSASSE": "subjonctif imparfait artificiel pour une grille grand public",
}


def main() -> None:
    shape_document = json.loads(SHAPE_FILE.read_text(encoding="utf-8"))
    shape = next(
        item for item in shape_document["shapes"]
        if item["id"] == "reference-ribbon-a-01"
    )
    with gzip.open(CENTRAL, "rt", encoding="utf-8") as handle:
        central_document = json.load(handle)
    central = {
        item["answer"]: item
        for item in central_document["entries"]
        if item.get("canonicalForGenerator")
    }
    with gzip.open(MORPHALOU, "rt", encoding="utf-8") as handle:
        morphalou_document = json.load(handle)
    morphalou = {item["answer"]: item for item in morphalou_document["entries"]}
    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    rejected_answers = set(blacklist.get("rejectedAnswers", []))
    cooldown_answers = {
        item["answer"] for item in blacklist.get("rotationCooldownAnswers", [])
    }

    grid_id = "agent-c-ribbon-a01-exact-lexical-closure"
    words = []
    missing_sources = []
    for index, slot in enumerate(shape["slots"]):
        answer = ANSWERS[index]
        if len(answer) != slot["length"]:
            raise ValueError(f"slot {index}: longueur incohérente")
        source = central.get(answer) or morphalou.get(answer)
        if source is None:
            missing_sources.append(answer)
            continue
        canonical = answer in central
        record = {
            "wordId": f"{grid_id}:word:{index + 1:02d}",
            "slotIndex": index,
            "slotId": slot["slotId"],
            "answer": answer,
            "clue": central[answer]["clue"] if canonical else "",
            "sourceClue": central[answer].get("sourceClue") if canonical else None,
            "direction": slot["direction"],
            "arrow": slot["arrow"],
            "clueCell": slot["clueCell"],
            "cells": slot["cells"],
            "sourceId": (
                central[answer].get("sourceId") if canonical else "morphalou-3.1"
            ),
            "sourceUrl": (
                central[answer].get("sourceUrl")
                if canonical else source["sourceUrl"]
            ),
            "license": (
                central[answer].get("license")
                if canonical else source["license"]
            ),
            "lexicalSource": "central-canonical" if canonical else "Morphalou 3.1",
            "definitionStatus": (
                "central-canonical" if canonical else "missing-editorial-clue"
            ),
            "editorialBlocker": EDITORIAL_BLOCKERS.get(answer),
        }
        if not canonical:
            record["morphology"] = {
                "lemma": source.get("lemma"),
                "lemmaAnswer": source.get("lemmaAnswer"),
                "partOfSpeech": source.get("partOfSpeech"),
                "formType": source.get("formType"),
                "inflection": source.get("inflection"),
            }
        words.append(record)
    if missing_sources:
        raise ValueError(f"réponses sans source: {missing_sources}")

    grid = {
        "id": grid_id,
        "columns": shape["columns"],
        "rows": shape["rows"],
        "sourceShapeId": shape["id"],
        "clueCells": shape["clueCells"],
        "words": words,
        "publicationStatus": "editorial-rejected-lexical-closure-only",
    }
    topology = audit_grid_topology(grid, enforce_layout=False)

    cell_links = defaultdict(list)
    for word in words:
        for position, cell in enumerate(word["cells"]):
            cell_links[tuple(cell)].append((word["slotIndex"], position))
    conflicts = []
    for cell, links in sorted(cell_links.items()):
        if len(links) != 2:
            conflicts.append({"cell": list(cell), "coverage": len(links)})
            continue
        (left, left_position), (right, right_position) = links
        left_answer = ANSWERS[left]
        right_answer = ANSWERS[right]
        if left_answer[left_position] != right_answer[right_position]:
            conflicts.append({
                "cell": list(cell),
                "leftSlot": left,
                "leftLetter": left_answer[left_position],
                "rightSlot": right,
                "rightLetter": right_answer[right_position],
            })

    answer_counts = Counter(ANSWERS.values())
    duplicates = sorted(answer for answer, count in answer_counts.items() if count > 1)
    blacklisted = sorted(
        answer for answer in ANSWERS.values()
        if answer in rejected_answers or answer in cooldown_answers
    )
    topology_errors = topology.get("errors", [])
    core_topology_errors = [
        error for error in topology_errors
        if error.get("code") != "empty_clue"
    ]
    empty_clue_errors = [
        error for error in topology_errors
        if error.get("code") == "empty_clue"
    ]
    if core_topology_errors or conflicts or duplicates or blacklisted:
        raise ValueError({
            "topology": core_topology_errors,
            "conflicts": conflicts,
            "duplicates": duplicates,
            "blacklisted": blacklisted,
        })

    changed_slots = [
        {
            "slotIndex": index,
            "before": ORIGINAL_ASSIGNMENT[index],
            "after": ANSWERS[index],
        }
        for index in sorted(ANSWERS)
        if ORIGINAL_ASSIGNMENT[index] != ANSWERS[index]
    ]
    result = {
        "version": 1,
        "kind": "agent-c-reference-ribbon-a01-exact-repair",
        "status": "zero-conflict-lexical-closure-editorial-rejected",
        "conclusion": (
            "La silhouette ferme lexicalement à 0 conflit, mais le candidat "
            "est interdit de publication: 15 réponses n'ont pas de définition "
            "éditoriale sourcée et plusieurs formes sont faibles ou obscures."
        ),
        "catalogModified": False,
        "blacklistModified": False,
        "interfaceModified": False,
        "sourceState": {
            "report": "output/quality/reference-ribbon-a01-inflected-local-717208.json",
            "seed": 717208,
            "startingCrossingConflicts": 4,
            "startingConflictedSlots": [0, 7, 9, 13, 15, 20, 21],
        },
        "repair": {
            "method": "progressive anchor relaxation, AC-3 and exact bitset search",
            "structuralPool": "src/data/crossword.morphalou.staging.json.gz",
            "structuralPoolAnswers": morphalou_document["metrics"].get(
                "distinctAnswers", len(morphalou)
            ),
            "anchorSubsetTests": 11040,
            "minimumAdditionalAnchorsReleasedForArcConsistency": 6,
            "sixAnchorArcConsistentSubsets": 6,
            "sixAnchorExactSolutions": 0,
            "solutionAdditionalAnchorsReleased": [1, 2, 6, 8, 17, 18, 19],
            "solutionFixedAnchors": [3, 4, 5, 10, 11, 12, 14, 16],
            "changedSlots": changed_slots,
            "forcedLetters": 0,
        },
        "audit": {
            "shapeId": shape["id"],
            "columns": shape["columns"],
            "rows": shape["rows"],
            "clueCellsUnchanged": True,
            "pathsUnchanged": True,
            "slotCount": len(words),
            "letterCells": len(cell_links),
            "crossingConstraints": sum(len(links) == 2 for links in cell_links.values()),
            "crossingConflicts": len(conflicts),
            "duplicateAnswers": duplicates,
            "blacklistedOrCooldownAnswers": blacklisted,
            "coreTopologyValid": not core_topology_errors,
            "publicationQualityGateValid": topology["valid"],
            "emptyClueAuditErrors": len(empty_clue_errors),
            "topologyErrors": topology_errors,
            "centralCanonicalPairs": sum(
                word["definitionStatus"] == "central-canonical" for word in words
            ),
            "missingEditorialClues": sum(not word["clue"] for word in words),
            "editorialBlockers": len(EDITORIAL_BLOCKERS),
        },
        "publication": {
            "allowed": False,
            "reason": (
                "Fermeture structurelle seulement; aucune définition n'a été "
                "inventée pour les formes Morphalou."
            ),
        },
        "grid": grid,
    }
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"],
        "crossingConflicts": result["audit"]["crossingConflicts"],
        "missingEditorialClues": result["audit"]["missingEditorialClues"],
        "output": str(OUTPUT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
