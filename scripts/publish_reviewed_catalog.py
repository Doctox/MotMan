"""Publie le lot standard 9x10 comme unique catalogue jouable."""
from __future__ import annotations

import json
from pathlib import Path

from grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "data"
ACTIVE = DATA / "grid.catalog.json"
STAGING = DATA / "grid-generation-handcrafted" / "standard.batch.staging.json"
AUDIT = ROOT / "output" / "quality" / "standard-batch-audit.json"
RUNTIME_VERSION = 4
EXPECTED_GRIDS = 30
EXPECTED_COLUMNS = 9
EXPECTED_ROWS = 10


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    staging = read_json(STAGING)
    audit = read_json(AUDIT)
    grids = staging.get("grids", [])
    if not audit.get("valid"):
        raise SystemExit("Publication bloquée : l'audit du lot standard n'est pas valide.")
    if len(grids) != EXPECTED_GRIDS:
        raise SystemExit(f"{EXPECTED_GRIDS} grilles attendues, {len(grids)} obtenues.")

    seen_ids: set[str] = set()
    image_clues = 0
    for grid in grids:
        grid_id = grid.get("id")
        if not grid_id or grid_id in seen_ids:
            raise SystemExit(f"ID absent ou dupliqué : {grid_id!r}")
        seen_ids.add(grid_id)
        if (grid.get("columns"), grid.get("rows")) != (EXPECTED_COLUMNS, EXPECTED_ROWS):
            raise SystemExit(f"{grid_id}: dimensions différentes de 9x10.")
        if grid.get("publicationStatus") not in {"editorially-reviewed-staging", "owner-approved-staging"}:
            raise SystemExit(f"{grid_id}: revue humaine manquante.")
        topology = audit_grid_topology(grid)
        if not topology["valid"]:
            raise SystemExit(f"{grid_id}: topologie invalide {topology['errorCounts']}")
        for word in grid.get("words", []):
            if not str(word.get("clue", "")).strip() and not word.get("image"):
                raise SystemExit(f"{grid_id}: indice vide sans image pour {word.get('answer')}.")
            image_clues += int(bool(word.get("image")))

    runtime = {
        "version": RUNTIME_VERSION,
        "kind": "motman-standard-runtime",
        "generatorSeed": 20260714,
        "selectionPolicy": "active-standard-only",
        "editorialProfile": staging.get("editorialProfile", "motman-standard"),
        "source": str(STAGING.relative_to(ROOT)).replace("\\", "/"),
        "grids": grids,
        "batchMetrics": staging.get("batchMetrics", {}),
    }
    write_json(ACTIVE, runtime)
    print(
        f"Catalogue v{RUNTIME_VERSION} publié : {len(grids)} grilles 9x10, "
        f"{image_clues} indices-images ; aucune grille 9x9 conservée."
    )


if __name__ == "__main__":
    main()
