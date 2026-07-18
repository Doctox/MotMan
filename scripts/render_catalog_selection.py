"""Render selected active catalog grids for a short owner review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from grid_topology import audit_grid_topology, render_topology_html


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("grid_ids", nargs="+")
    parser.add_argument("--catalog", type=Path, default=ROOT / "src/data/grid.catalog.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="MotMan — sélection du catalogue actif")
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    by_id = {grid["id"]: grid for grid in catalog["grids"]}
    missing = [grid_id for grid_id in args.grid_ids if grid_id not in by_id]
    if missing:
        raise ValueError(f"grilles absentes du catalogue: {missing}")
    reports = [audit_grid_topology(by_id[grid_id]) for grid_id in args.grid_ids]
    invalid = [report["gridId"] for report in reports if not report["valid"]]
    if invalid:
        raise ValueError(f"grilles topologiquement invalides: {invalid}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_topology_html(reports, title=args.title), encoding="utf-8")
    print(json.dumps({"rendered": args.grid_ids, "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
