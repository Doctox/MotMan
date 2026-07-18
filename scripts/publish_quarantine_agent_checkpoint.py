"""Remove the stored quarantines and publish the reviewed agent checkpoint."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

from grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "src/data/grid.catalog.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
STAGING = (
    ROOT
    / "src/data/grid-generation-handcrafted/quarantine-agent-checkpoint.review.json"
)
PROPOSAL = ROOT / "output/quality/agent-blacklist-proposal.json"
REMOVED_GRID_IDS = {
    "reference-standard-20",
    "reference-standard-29",
    "corpus-aware-review-01",
    "corpus-aware-review-02",
    "corpus-aware-review-04",
}
EXPECTED_NEW_ID = "dynamic-reference-c-02-refined"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, document: dict) -> None:
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_publication(
    active: dict, staging: dict, blacklist: dict, proposal: dict
) -> tuple[dict, dict, dict]:
    if set(staging.get("removedGridIds", [])) != REMOVED_GRID_IDS:
        raise ValueError("Le staging ne déclare pas exactement les cinq quarantaines.")
    staged = staging.get("grids", [])
    if len(staged) != 1 or staged[0].get("id") != EXPECTED_NEW_ID:
        raise ValueError("Le staging doit contenir l'unique grille revue.")

    candidate = copy.deepcopy(staged[0])
    topology = audit_grid_topology(candidate, enforce_layout=False)
    if not topology["valid"] or topology["orphanSegments"]:
        raise ValueError(f"Topologie candidate invalide : {topology['errorCounts']}")
    if sum(bool(word.get("image")) for word in candidate["words"]) != 6:
        raise ValueError("La candidate ne contient pas exactement six images.")

    existing = active.get("grids", [])
    existing_ids = [grid.get("id") for grid in existing]
    missing = REMOVED_GRID_IDS - set(existing_ids)
    if missing:
        # Idempotence: after publication all five old IDs are absent and the new
        # one is present.  Any mixed state is considered a conflict.
        if missing == REMOVED_GRID_IDS and EXPECTED_NEW_ID in existing_ids:
            return copy.deepcopy(active), copy.deepcopy(blacklist), {
                "status": "already-published",
                "removed": 0,
                "added": 0,
                "total": len(existing),
                "version": active.get("version"),
            }
        raise ValueError(f"État partiel du catalogue, anciennes grilles absentes : {sorted(missing)}")
    if EXPECTED_NEW_ID in existing_ids:
        raise ValueError(f"ID candidat déjà utilisé : {EXPECTED_NEW_ID}")

    published = copy.deepcopy(active)
    preserved = [grid for grid in existing if grid.get("id") not in REMOVED_GRID_IDS]
    preserved.append(candidate)
    if len(preserved) != len(existing) - 4:
        raise ValueError("Le checkpoint doit retirer cinq grilles et en ajouter une.")
    published["version"] = int(published.get("version", 0)) + 1
    published["selectionPolicy"] = "active-standard-plus-owner-directed-agents"
    source = (
        "src/data/grid-generation-handcrafted/"
        "quarantine-agent-checkpoint.review.json"
    )
    sources = list(published.get("additionalSources", []))
    if source not in sources:
        sources.append(source)
    published["additionalSources"] = sources
    published["grids"] = preserved
    published["batchMetrics"] = {
        **published.get("batchMetrics", {}),
        "activeCatalogGrids": len(preserved),
        "physicallyRemovedQuarantinedGrids": 5,
        "referenceInspiredAgentGrids": 1,
        "pendingReplacementSlots": 4,
    }

    updated_blacklist = copy.deepcopy(blacklist)
    rejected_answers = list(updated_blacklist.get("rejectedAnswers", []))
    rejected_answer_set = set(rejected_answers)
    for item in proposal.get("rejectedAnswers", []):
        answer = item["answer"]
        if answer not in rejected_answer_set:
            rejected_answers.append(answer)
            rejected_answer_set.add(answer)
    updated_blacklist["rejectedAnswers"] = rejected_answers

    rejected_pairs = list(updated_blacklist.get("rejectedPairs", []))
    rejected_pair_keys = {
        (item.get("answer"), str(item.get("clue", "")).casefold())
        for item in rejected_pairs
    }
    for item in proposal.get("rejectedPairs", []):
        key = (item["answer"], item["clue"].casefold())
        if key in rejected_pair_keys:
            continue
        rejected_pairs.append(
            {
                "answer": item["answer"],
                "clue": item["clue"],
                "reason": item["reason"],
            }
        )
        rejected_pair_keys.add(key)
    updated_blacklist["rejectedPairs"] = rejected_pairs

    report = {
        "status": "published",
        "removed": 5,
        "removedIds": sorted(REMOVED_GRID_IDS),
        "added": 1,
        "addedIds": [EXPECTED_NEW_ID],
        "preserved": len(existing) - 5,
        "total": len(preserved),
        "pendingReplacementSlots": 4,
        "blacklistAnswersAdded": len(rejected_answer_set) - len(set(blacklist.get("rejectedAnswers", []))),
        "blacklistPairsAdded": len(rejected_pair_keys) - len({
            (item.get("answer"), str(item.get("clue", "")).casefold())
            for item in blacklist.get("rejectedPairs", [])
        }),
        "version": published["version"],
    }
    return published, updated_blacklist, report


def main() -> None:
    published, blacklist, report = prepare_publication(
        read(ACTIVE), read(STAGING), read(BLACKLIST), read(PROPOSAL)
    )
    atomic_write(ACTIVE, published)
    atomic_write(BLACKLIST, blacklist)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
