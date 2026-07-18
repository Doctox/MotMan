"""Freeze the single agent grid that passed the human checkpoint.

The agents produced many technically complete candidates.  Only one survived
the independent editorial review, so this builder deliberately stages one
grid and records the four still-missing replacement slots instead of silently
promoting weaker candidates.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output/quality/agent-dynamic-c-refined.json"
STAGING = (
    ROOT
    / "src/data/grid-generation-handcrafted/quarantine-agent-checkpoint.review.json"
)
SOURCE_GRID_ID = "dynamic-reference-c-02-refined"
REMOVED_GRID_IDS = (
    "reference-standard-20",
    "reference-standard-29",
    "corpus-aware-review-01",
    "corpus-aware-review-02",
    "corpus-aware-review-04",
)


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    grid = next(
        (item for item in source.get("grids", []) if item.get("id") == SOURCE_GRID_ID),
        None,
    )
    if grid is None:
        raise SystemExit(f"Grille source absente : {SOURCE_GRID_ID}")

    staged = copy.deepcopy(grid)
    staged["publicationStatus"] = "owner-directed-runtime"
    staged["manualReview"] = "agent-reviewed-owner-directed"
    staged["approvedOn"] = "2026-07-17"
    staged["reviewNote"] = (
        "Seule candidate du lot agents ayant passé la revue humaine indépendante; "
        "inspirée des longues bandes et doubles départs de la référence fournie."
    )
    for word in staged["words"]:
        word["manualReview"] = "agent-reviewed-owner-directed"

    topology = audit_grid_topology(staged, enforce_layout=False)
    if not topology["valid"] or topology["orphanSegments"]:
        raise SystemExit(
            f"{SOURCE_GRID_ID}: topologie invalide {topology['errorCounts']}"
        )
    image_words = [word for word in staged["words"] if word.get("image")]
    if len(image_words) != 6:
        raise SystemExit(f"{SOURCE_GRID_ID}: {len(image_words)} images au lieu de 6")
    for word in image_words:
        asset = ROOT / "public" / word["image"]["asset"].lstrip("/")
        if not asset.is_file():
            raise SystemExit(f"Asset image absent : {asset}")

    document = {
        "version": 1,
        "kind": "quarantine-agent-replacement-checkpoint",
        "generatedOn": "2026-07-17",
        "reference": {
            "source": "owner-provided-arrowword-screenshot",
            "principles": [
                "longues réponses structurantes",
                "doubles départs droite et bas espacés",
                "indices internes lisibles",
                "six images littérales",
            ],
            "contentCopied": False,
        },
        "removedGridIds": list(REMOVED_GRID_IDS),
        "acceptedGridIds": [SOURCE_GRID_ID],
        "pendingReplacementSlots": 4,
        "publicationPolicy": (
            "Suppression des cinq quarantaines; publication uniquement de la "
            "candidate qui passe la revue humaine."
        ),
        "grids": [staged],
    }
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "staged",
                "staging": str(STAGING),
                "removed": len(REMOVED_GRID_IDS),
                "accepted": 1,
                "pending": 4,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
