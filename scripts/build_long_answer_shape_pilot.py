"""Build one 9x10 silhouette where 5-8-letter answers outnumber 2-4s."""
from __future__ import annotations

import json
import sys
from collections import Counter
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology  # noqa: E402


OUTPUT = ROOT / "output/quality/long-answer-shape-pilot.json"
HTML = ROOT / "output/quality/long-answer-shape-pilot.html"
CURATED_CLUE_CELLS = {
    (0, 0), (0, 1), (0, 2),
    (1, 0), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),
    (2, 0), (3, 0), (4, 0), (5, 0), (5, 2),
    (6, 1), (7, 1), (8, 1), (9, 1),
}


def band_counts(lengths: dict[int | str, int]) -> tuple[int, int]:
    normalized = {int(length): int(count) for length, count in lengths.items()}
    short = sum(normalized.get(length, 0) for length in range(2, 5))
    long = sum(normalized.get(length, 0) for length in range(5, 9))
    return short, long


def template_grid(shape: dict) -> dict:
    return {
        "id": "long-answer-shape-pilot-01",
        "columns": shape["columns"],
        "rows": shape["rows"],
        "clueCells": shape["clueCells"],
        "words": [
            {
                "wordId": f"long-answer-shape-pilot-01:slot:{number:02d}",
                "answer": "X" * slot["length"],
                "clue": f"Gabarit {slot['length']}",
                "direction": slot["direction"],
                "arrow": slot["arrow"],
                "clueCell": slot["clue"],
                "cells": slot["cells"],
            }
            for number, slot in enumerate(shape["slots"], 1)
        ],
    }


def shape_from_clues(clues: set[tuple[int, int]]) -> dict:
    slots = []
    launches = Counter()
    for clue in sorted(clues - {(0, 0)}):
        for direction, arrow, (dr, dc) in (
            ("across", "right", (0, 1)),
            ("down", "down", (1, 0)),
        ):
            cells = []
            row, col = clue[0] + dr, clue[1] + dc
            while 0 <= row < 10 and 0 <= col < 9 and (row, col) not in clues:
                cells.append([row, col])
                row += dr
                col += dc
            if len(cells) < 2:
                continue
            slots.append({
                "direction": direction,
                "arrow": arrow,
                "clue": list(clue),
                "cells": cells,
                "length": len(cells),
            })
            launches[clue] += 1
    lengths = Counter(slot["length"] for slot in slots)
    short, long = band_counts(lengths)
    return {
        "seed": "handcrafted-long-shape-20260716",
        "columns": 9,
        "rows": 10,
        "requestedVisibleClueCells": len(clues) - 1,
        "clueCells": [list(cell) for cell in sorted(clues)],
        "slots": slots,
        "metrics": {
            "clueCells": len(clues) - 1,
            "doubleClueCells": sum(count == 2 for count in launches.values()),
            "lengths": dict(sorted(lengths.items())),
            "shortAnswers2To4": short,
            "longAnswers5To8": long,
            "longAnswerAdvantage": long - short,
            "arrows": dict(sorted(Counter(slot["arrow"] for slot in slots).items())),
        },
    }


def find_shape() -> dict:
    active = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    active_shapes = [
        {tuple(cell) for cell in grid["clueCells"]}
        for grid in active.get("grids", [])
    ]
    shape = shape_from_clues(CURATED_CLUE_CELLS)
    if CURATED_CLUE_CELLS in active_shapes:
        raise SystemExit("La silhouette longue est déjà présente dans le catalogue actif.")
    short, long = band_counts(shape["metrics"]["lengths"])
    required = {5, 6, 7, 8}
    if long <= short or not required.issubset(shape["metrics"]["lengths"]):
        raise SystemExit("La silhouette ne respecte plus le contrat de longueurs.")
    grid = template_grid(shape)
    topology = audit_grid_topology(grid, enforce_layout=False)
    if not topology["valid"]:
        raise SystemExit(f"Topologie invalide : {topology['errorCounts']}")
    strict_layout = audit_grid_topology(grid, enforce_layout=True)
    allowed_layout_warnings = {
        "clue_wall", "too_many_adjacent_clue_pairs", "insufficient_double_clues"
    }
    unexpected = [
        error for error in strict_layout["errors"]
        if error["code"] not in allowed_layout_warnings
    ]
    if unexpected:
        raise SystemExit(f"Erreur hors exception visuelle : {unexpected}")
    shape["acceptedSeed"] = shape["seed"]
    shape["topology"] = {
        "valid": True,
        "letterCells": sum(cell["kind"] == "letter" for cell in topology["cells"]),
        "orphanSegments": topology["errorCounts"].get("orphan-segment", 0),
        "uncoveredLetters": topology["errorCounts"].get("uncovered-letter", 0),
        "layoutWarningsAcceptedForPilot": strict_layout["errorCounts"],
    }
    return shape


def render(shape: dict) -> str:
    rows, columns = shape["rows"], shape["columns"]
    clues = {tuple(cell) for cell in shape["clueCells"]}
    launches: dict[tuple[int, int], list[tuple[str, int]]] = {}
    for slot in shape["slots"]:
        launches.setdefault(tuple(slot["clue"]), []).append(
            ("→" if slot["direction"] == "across" else "↓", slot["length"])
        )
    cells = []
    for row in range(rows):
        for col in range(columns):
            cell = (row, col)
            if cell == (0, 0):
                cells.append('<div class="cell neutral">Ø</div>')
            elif cell in clues:
                labels = "".join(
                    f'<span>{escape(arrow)} {length}</span>'
                    for arrow, length in launches.get(cell, [])
                )
                cells.append(f'<div class="cell clue">{labels}</div>')
            else:
                cells.append('<div class="cell letter"></div>')
    lengths = {int(k): v for k, v in shape["metrics"]["lengths"].items()}
    short, long = band_counts(lengths)
    profile = " · ".join(
        f"{count}×{length} lettres" for length, count in sorted(lengths.items())
    )
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MotMan — silhouette à réponses longues</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f1e8;color:#173b35;font-family:system-ui,sans-serif}}
main{{max-width:760px;margin:auto;padding:26px}}.card{{background:#fffdf8;border:1px solid #bfd0c7;border-radius:16px;padding:18px;box-shadow:0 10px 28px #315b4d18}}
.summary{{background:#e4f4e9;border-left:5px solid #2f7d5b;padding:12px 14px;margin:14px 0}}
.grid{{display:grid;grid-template-columns:repeat(9,1fr);aspect-ratio:9/10;border:2px solid #315b4d;background:#315b4d;gap:1px;max-width:530px;margin:auto}}
.cell{{min-width:0;background:#fffdf8;display:flex;align-items:center;justify-content:center}}.neutral{{background:#243d38;color:#fff;font-size:22px}}
.clue{{background:#dce9e2;flex-direction:column;gap:2px;color:#174d43;font-weight:800;font-size:10px}}.clue span{{white-space:nowrap}}
.legend{{font-size:13px;color:#536b63;line-height:1.55}}@media(max-width:520px){{main{{padding:12px}}.clue{{font-size:8px}}}}
</style></head><body><main><h1>Test : priorité aux mots longs</h1>
<p>Prototype géométrique non publié. Les nombres indiquent la longueur et le sens de chaque réponse.</p>
<div class="summary"><b>{long} réponses de 5 à 8 lettres</b> contre <b>{short} réponses de 2 à 4</b>.</div>
<section class="card"><div class="grid">{''.join(cells)}</div>
<p class="legend">{escape(profile)}<br>{shape['metrics']['clueCells']} cases-définition · {shape['metrics']['doubleClueCells']} cases doubles · flèches directes uniquement · couverture topologique complète.</p></section>
</main></body></html>"""


def main() -> None:
    shape = find_shape()
    short, long = band_counts(shape["metrics"]["lengths"])
    document = {
        "version": 1,
        "kind": "long-answer-shape-owner-pilot",
        "publicationStatus": "geometry-only-owner-review",
        "criteria": {
            "shortLengths": [2, 3, 4],
            "longLengths": [5, 6, 7, 8],
            "minimumLongAdvantage": 1,
            "allowAdjacentDefinitionCells": True,
        },
        "metrics": {"shortAnswers": short, "longAnswers": long},
        "shape": shape,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    HTML.write_text(render(shape), encoding="utf-8")
    print(json.dumps({
        "status": "built",
        "json": str(OUTPUT),
        "html": str(HTML),
        "seed": shape["acceptedSeed"],
        "lengths": shape["metrics"]["lengths"],
        "shortAnswers": short,
        "longAnswers": long,
        "topology": shape["topology"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
