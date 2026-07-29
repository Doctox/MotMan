"""Publish the owner-approved 15-grid editorial sublot 111bca5d3810.

The editorial preparation script deliberately cannot mutate either MotMan
catalog.  This module is the narrow publication bridge: it pins every reviewed
artifact by SHA-256, rechecks topology and blacklist policy, then atomically
updates the source and runtime catalogs.  Supabase remains a separate,
auditable step generated from the resulting runtime catalog.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology  # noqa: E402


SOURCE_VERSION = 20
TARGET_VERSION = 21
SOURCE_GRID_COUNT = 29
ADDED_GRID_COUNT = 15
TARGET_GRID_COUNT = SOURCE_GRID_COUNT + ADDED_GRID_COUNT

OUTPUT_DIR = ROOT / "output/quality/certified-editorial-111bca5d3810"
STAGING_PATH = OUTPUT_DIR / "staging.json"
AUDIT_PATH = OUTPUT_DIR / "audit.json"
SELECTION_PATH = OUTPUT_DIR / "selection-report.json"
MANIFEST_PATH = OUTPUT_DIR / "artifact-manifest.json"
CATALOG_PATH = ROOT / "src/data/grid.catalog.json"
RUNTIME_PATH = ROOT / "src/data/runtime.grid.catalog.json"
BLACKLIST_PATH = ROOT / "src/data/editorial.blacklist.json"
SNAPSHOT_PATH = (
    ROOT
    / "src/data/grid-generation-handcrafted"
    / "certified-editorial-111bca5d3810.json"
)
REPORT_PATH = OUTPUT_DIR / "publication-report.json"

EXPECTED_HASHES = {
    STAGING_PATH: "64c3358395c66768072b60899662645f7ee2445b299541de1e88b0c7879f62b5",
    AUDIT_PATH: "eb46f27a919e40aaa878542ee8ebeb2d9cb5049d8fa9e14ecad29a8152cf6080",
    SELECTION_PATH: "1e9ae4e96e2d020741394d1818de04ac039aba08657d08b4f5fec7ed5cc83e46",
    MANIFEST_PATH: "a73c408c317114349dfdbe2fa1da459e16938b7a0b42350e9cebae722ec6e43f",
}
EXPECTED_SOURCE_CATALOG_SHA256 = (
    "a8f835fe665d2bc4465153064ab16983e5d2d1804ae635b97808f65b019870f3"
)
EXPECTED_SOURCE_RUNTIME_SHA256 = (
    "4827f6882e92e13cb8a3577f329f3ceb30f5b137f0fb59c3914dd323dec023f4"
)
OWNER_APPROVAL_DATE = "2026-07-29"
OWNER_APPROVAL_REFERENCE = "owner-explicit-publication-approval"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Objet JSON attendu : {path}")
    return value


def atomic_json(path: Path, value: object, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=None if compact else 2,
            separators=(",", ":") if compact else None,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def verify_artifacts() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    for path, expected in EXPECTED_HASHES.items():
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(
                f"Artefact éditorial modifié : {path.name}={actual}; attendu {expected}"
            )

    staging = read_json(STAGING_PATH)
    audit = read_json(AUDIT_PATH)
    selection = read_json(SELECTION_PATH)
    if staging.get("schema") != "motman-grid-certified-editorial-staging":
        raise ValueError("Schéma staging inattendu")
    if audit.get("schema") != "motman-certified-editorial-staging-audit":
        raise ValueError("Schéma audit inattendu")
    if not audit.get("valid"):
        raise ValueError("Audit éditorial invalide")
    grids = staging.get("grids")
    if not isinstance(grids, list) or len(grids) != ADDED_GRID_COUNT:
        raise ValueError("Le sous-lot doit contenir exactement 15 grilles")
    if (
        selection.get("sourceGridCount") != 33
        or selection.get("retainedGridCount") != ADDED_GRID_COUNT
        or selection.get("excludedGridCount") != 18
    ):
        raise ValueError("Comptage de sélection inattendu")
    if len({str(grid.get("id")) for grid in grids}) != ADDED_GRID_COUNT:
        raise ValueError("Identifiants de grille dupliqués dans le staging")
    return staging, audit, selection


def owner_approved_grid(source: dict[str, Any]) -> dict[str, Any]:
    grid = copy.deepcopy(source)
    grid["publicationStatus"] = "owner-approved-editorial-reviewed"
    grid["ownerReview"] = {
        "status": "approved",
        "reviewedAt": OWNER_APPROVAL_DATE,
        "decision": "publish",
        "reference": OWNER_APPROVAL_REFERENCE,
    }
    review = dict(grid.get("editorialReview") or {})
    review["status"] = "owner-approved"
    review["ownerApprovalDate"] = OWNER_APPROVAL_DATE
    grid["editorialReview"] = review
    return grid


def verify_grids(
    grids: list[dict[str, Any]], blacklist: dict[str, Any]
) -> list[dict[str, Any]]:
    rejected_answers = set(blacklist.get("rejectedAnswers") or [])
    rejected_pairs = {
        (str(item.get("answer")), str(item.get("clue", "")).casefold())
        for item in blacklist.get("rejectedPairs") or []
    }
    quarantined = set(blacklist.get("quarantinedGridIds") or [])
    topology: list[dict[str, Any]] = []
    for grid in grids:
        if grid["id"] in quarantined:
            raise ValueError(f"Grille mise en quarantaine : {grid['id']}")
        if grid.get("columns") != 7 or grid.get("rows") != 8:
            raise ValueError(f"Dimensions non 7x8 : {grid['id']}")
        for word in grid.get("words", []):
            answer = str(word.get("answer", ""))
            clue = str(word.get("clue", ""))
            if answer in rejected_answers:
                raise ValueError(f"Réponse blacklistée : {grid['id']} / {answer}")
            if (answer, clue.casefold()) in rejected_pairs:
                raise ValueError(f"Couple blacklisté : {grid['id']} / {answer}")
            if not clue.strip() and not word.get("image"):
                raise ValueError(f"Indice absent : {grid['id']} / {answer}")
        item = audit_grid_topology(
            grid,
            require_word_ids=True,
            enforce_layout=False,
            topology_profile="pilot",
        )
        if not item["valid"]:
            raise ValueError(f"Topologie invalide : {grid['id']} / {item['errors']}")
        topology.append(item)
    return topology


def runtime_projection(catalog: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": catalog["version"],
        "grids": [
            {
                "id": grid["id"],
                "columns": grid["columns"],
                "rows": grid["rows"],
                "clueCells": grid["clueCells"],
                "words": [
                    {
                        "wordId": word["wordId"],
                        "answer": word["answer"],
                        "clue": word["clue"],
                        **({"image": word["image"]} if word.get("image") else {}),
                        "direction": word["direction"],
                        "arrow": word["arrow"],
                        "clueCell": word["clueCell"],
                        "cells": word["cells"],
                    }
                    for word in grid["words"]
                ],
            }
            for grid in catalog["grids"]
        ],
    }


def build_updated_catalog(
    catalog: dict[str, Any],
    staged_grids: list[dict[str, Any]],
    selection: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    approved = [owner_approved_grid(grid) for grid in staged_grids]
    existing = {grid["id"]: grid for grid in catalog.get("grids", [])}
    incoming_ids = {grid["id"] for grid in approved}
    present = incoming_ids & set(existing)

    if present:
        if present != incoming_ids or catalog.get("version") != TARGET_VERSION:
            raise ValueError(f"Publication partielle détectée : {sorted(present)}")
        for grid in approved:
            if existing[grid["id"]] != grid:
                raise ValueError(f"Grille publiée différente du lot approuvé : {grid['id']}")
        return copy.deepcopy(catalog), approved

    if catalog.get("version") != SOURCE_VERSION:
        raise ValueError(
            f"Version source {catalog.get('version')} au lieu de {SOURCE_VERSION}"
        )
    if len(catalog.get("grids", [])) != SOURCE_GRID_COUNT:
        raise ValueError("Le catalogue source ne contient plus 29 grilles")

    updated = copy.deepcopy(catalog)
    updated["version"] = TARGET_VERSION
    updated["source"] = str(SNAPSHOT_PATH.relative_to(ROOT)).replace("\\", "/")
    updated["grids"].extend(approved)
    uses = Counter(
        word["answer"] for grid in updated["grids"] for word in grid["words"]
    )
    updated["batchMetrics"] = {
        "gridCount": len(updated["grids"]),
        "columns": 7,
        "rows": 8,
        "letterCells": sum(
            len(
                {
                    tuple(cell)
                    for word in grid["words"]
                    for cell in word["cells"]
                }
            )
            for grid in updated["grids"]
        ),
        "answers": sum(len(grid["words"]) for grid in updated["grids"]),
        "distinctAnswers": len(uses),
        "imageCount": sum(
            bool(word.get("image"))
            for grid in updated["grids"]
            for word in grid["words"]
        ),
        "factoryCertifiedBatchAdded": 4,
        "factoryCertifiedGridWithheld": 1,
        "certifiedEditorial111bca5d3810Added": ADDED_GRID_COUNT,
        "certifiedEditorial111bca5d3810Excluded": selection["excludedGridCount"],
    }
    updated["publicationNote"] = (
        "44 grilles 7x8 actives : 29 grilles précédentes conservées et "
        "15 grilles Grid Factory certifiées, éditorialisées puis explicitement "
        "validées par le propriétaire le 2026-07-29. Les 18 autres grilles du "
        "handoff restent exclues selon le rapport de sélection."
    )
    return updated, approved


def build_snapshot(
    approved: list[dict[str, Any]],
    selection: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "motman-certified-editorial-publication-source",
        "version": 1,
        "catalogVersion": TARGET_VERSION,
        "ownerApproval": {
            "status": "approved",
            "date": OWNER_APPROVAL_DATE,
            "reference": OWNER_APPROVAL_REFERENCE,
        },
        "artifactHashes": {
            path.name: digest for path, digest in EXPECTED_HASHES.items()
        },
        "selection": {
            "sourceGridCount": selection["sourceGridCount"],
            "retainedGridCount": selection["retainedGridCount"],
            "excludedGridCount": selection["excludedGridCount"],
            "retainedCandidateIds": selection["retainedCandidateIds"],
            "excluded": selection["excluded"],
        },
        "grids": approved,
    }


def publish() -> dict[str, Any]:
    staging, _audit, selection = verify_artifacts()
    catalog = read_json(CATALOG_PATH)
    if catalog.get("version") == SOURCE_VERSION:
        if sha256_file(CATALOG_PATH) != EXPECTED_SOURCE_CATALOG_SHA256:
            raise ValueError("Le catalogue v20 ne correspond plus au baseline revu")
        if sha256_file(RUNTIME_PATH) != EXPECTED_SOURCE_RUNTIME_SHA256:
            raise ValueError("Le catalogue runtime v20 ne correspond plus au baseline revu")

    approved_preview = [owner_approved_grid(grid) for grid in staging["grids"]]
    topology = verify_grids(approved_preview, read_json(BLACKLIST_PATH))
    updated, approved = build_updated_catalog(catalog, staging["grids"], selection)
    runtime = runtime_projection(updated)
    changed = catalog != updated

    if changed:
        atomic_json(OUTPUT_DIR / "prepublish-grid-catalog-v20.json", catalog)
        atomic_json(
            OUTPUT_DIR / "prepublish-runtime-grid-catalog-v20.json",
            read_json(RUNTIME_PATH),
            compact=True,
        )
        atomic_json(SNAPSHOT_PATH, build_snapshot(approved, selection))
        atomic_json(CATALOG_PATH, updated)
        atomic_json(RUNTIME_PATH, runtime, compact=True)
    elif read_json(RUNTIME_PATH) != runtime:
        raise ValueError("Projection runtime divergente après publication")

    previous_report = read_json(REPORT_PATH) if REPORT_PATH.is_file() else {}
    previous_supabase = previous_report.get("supabase")
    supabase_status = (
        previous_supabase
        if isinstance(previous_supabase, dict)
        and previous_supabase.get("status") == "published-and-verified"
        else {"status": "pending"}
    )
    report = {
        "schema": "motman-certified-editorial-publication-report",
        "version": 1,
        "generatedAt": date.today().isoformat(),
        "changed": changed,
        "ownerApproval": OWNER_APPROVAL_REFERENCE,
        "sourceCatalogVersion": SOURCE_VERSION,
        "targetCatalogVersion": TARGET_VERSION,
        "previousGridCount": SOURCE_GRID_COUNT,
        "addedGridCount": ADDED_GRID_COUNT,
        "excludedGridCount": selection["excludedGridCount"],
        "finalGridCount": len(updated["grids"]),
        "addedGridIds": [grid["id"] for grid in approved],
        "topologyValid": sum(item["valid"] for item in topology),
        "imageCountAdded": sum(
            bool(word.get("image")) for grid in approved for word in grid["words"]
        ),
        "answerSlotsAdded": sum(len(grid["words"]) for grid in approved),
        "catalogSha256": sha256_file(CATALOG_PATH),
        "runtimeCatalogSha256": sha256_file(RUNTIME_PATH),
        "supabase": supabase_status,
    }
    if previous_report.get("supabaseSqlSha256"):
        report["supabaseSqlSha256"] = previous_report["supabaseSqlSha256"]
    if previous_report.get("validation"):
        report["validation"] = previous_report["validation"]
    atomic_json(REPORT_PATH, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Écrit atomiquement les catalogues après tous les contrôles.",
    )
    args = parser.parse_args()
    if not args.publish:
        staging, _audit, selection = verify_artifacts()
        preview = [owner_approved_grid(grid) for grid in staging["grids"]]
        topology = verify_grids(preview, read_json(BLACKLIST_PATH))
        print(
            json.dumps(
                {
                    "valid": True,
                    "publishable": len(preview),
                    "excluded": selection["excludedGridCount"],
                    "topologyValid": sum(item["valid"] for item in topology),
                    "catalogVersionTarget": TARGET_VERSION,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    print(json.dumps(publish(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
