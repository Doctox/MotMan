#!/usr/bin/env python3
"""Collect explicitly selected raw 7x8 grids without touching the active catalog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_selection(value: str) -> tuple[Path, int]:
    path_value, separator, index_value = value.rpartition("::")
    if not separator:
        raise argparse.ArgumentTypeError("Format attendu : CHEMIN::INDEX (index à partir de 1)")
    try:
        index = int(index_value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("L'index doit être un entier") from error
    if index < 1:
        raise argparse.ArgumentTypeError("L'index commence à 1")
    return Path(path_value), index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--select", action="append", type=parse_selection, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def selected_grid(path: Path, index: int) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    grids = document.get("grids")
    if not isinstance(grids, list):
        grids = [document]
    if index > len(grids):
        raise ValueError(f"{path}: index {index} hors limites ({len(grids)} grille(s))")
    grid = dict(grids[index - 1])
    if not grid.get("answers"):
        raise ValueError(f"{path}: la grille {index} n'est pas complète")
    grid["selectionSource"] = str(path).replace("\\", "/")
    grid["selectionIndex"] = index
    return grid


def main() -> None:
    args = parse_args()
    grids = [selected_grid(path, index) for path, index in args.select]
    payload = {
        "version": 1,
        "kind": "compact-7x8-raw-selection",
        "catalogModified": False,
        "grids": grids,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"selected": len(grids), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
