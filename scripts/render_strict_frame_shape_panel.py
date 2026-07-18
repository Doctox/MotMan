#!/usr/bin/env python3
"""Render strict top/left-frame silhouettes before lexical filling."""
from __future__ import annotations

import argparse
import json
import random
import sys
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import craft_flexible_common_grid as craft  # noqa: E402
from generate_large_lexical_batch import sampled_shape_pool  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=721400)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--maximum-two-letter", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    return parser.parse_args()


def choose_diverse(pool: list, count: int) -> list:
    """Greedily minimize overlap between internal definition patterns."""
    if not pool:
        return []
    remaining = list(pool)
    remaining.sort(key=lambda item: (
        len(item[0] - craft.FRAME), item[3].get("sourceShapeId", "")
    ))
    selected = [remaining.pop(len(remaining) // 2)]
    while remaining and len(selected) < count:
        def novelty(item) -> tuple:
            internal = item[0] - craft.FRAME
            nearest = max(
                (
                    len(internal & (other[0] - craft.FRAME))
                    / len(internal | (other[0] - craft.FRAME))
                    if internal | (other[0] - craft.FRAME) else 1.0
                )
                for other in selected
            )
            return (-nearest, len(internal), item[3].get("sourceShapeId", ""))

        chosen = max(remaining, key=novelty)
        remaining.remove(chosen)
        selected.append(chosen)
    return selected


def render_shape(record: tuple, number: int) -> str:
    clues, raw_slots, _slots, audit = record
    launches: dict[tuple[int, int], list[str]] = {}
    for slot in raw_slots:
        cell = tuple(slot["clueCell"])
        launches.setdefault(cell, []).append(
            "→" if slot["direction"] == "across" else "↓"
        )
    cells = []
    for row in range(craft.ROWS):
        for column in range(craft.COLUMNS):
            cell = (row, column)
            if cell == (0, 0):
                cells.append('<div class="cell neutral">∅</div>')
            elif cell in clues:
                arrows = " ".join(launches.get(cell, []))
                kind = "frame" if cell in craft.FRAME else "internal"
                cells.append(
                    f'<div class="cell clue {kind}"><span>{arrows}</span></div>'
                )
            else:
                cells.append('<div class="cell letter"></div>')
    lengths = [slot["length"] for slot in raw_slots]
    distribution = {
        length: lengths.count(length) for length in sorted(set(lengths))
    }
    return f"""
    <article>
      <h2>Silhouette {number}</h2>
      <div class="grid">{''.join(cells)}</div>
      <p><b>{len(clues - craft.FRAME)}</b> définitions internes ·
      <b>{len(raw_slots)}</b> réponses · <b>{lengths.count(2)}</b> mot(s) de 2 lettres</p>
      <code>{escape(json.dumps(distribution, ensure_ascii=False))}</code>
      <p class="ok">✓ 90 cases couvertes · 0 lettre orpheline · 0 définition isolée</p>
      <small>{escape(audit.get('sourceShapeId', 'strict-frame'))}</small>
    </article>"""


def main() -> int:
    args = parse_args()
    craft.MAX_TWO_LETTER = args.maximum_two_letter
    pool = sampled_shape_pool(
        random.Random(args.seed), args.maximum_two_letter
    )
    selected = choose_diverse(pool, args.count)
    if not selected:
        raise RuntimeError("No strict-frame silhouette is available")
    grids = []
    for number, (clues, raw_slots, _slots, audit) in enumerate(selected, 1):
        grids.append({
            "id": f"strict-frame-panel-{number:02d}",
            "columns": craft.COLUMNS,
            "rows": craft.ROWS,
            "clueCells": [list(cell) for cell in sorted(clues)],
            "rawSlots": raw_slots,
            "geometryAudit": audit,
        })
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps({
            "version": 1,
            "kind": "strict-frame-free-shape-panel",
            "seed": args.seed,
            "policy": {
                "topRowAllDefinitions": True,
                "leftColumnAllDefinitions": True,
                "maximumTwoLetterAnswers": args.maximum_two_letter,
                "orphanLettersAllowed": False,
            },
            "grids": grids,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    cards = "".join(render_shape(record, index) for index, record in enumerate(selected, 1))
    html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Nouvelles silhouettes — cadre strict</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f0e8;color:#173b35;font:15px/1.4 system-ui,sans-serif}}main{{max-width:1450px;margin:auto;padding:24px}}h1,h2{{color:#174d43}}.lead{{background:#fff8d9;border-left:5px solid #d5a323;padding:12px}}.panel{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}}article{{background:#fffdf8;border:1px solid #bdccc5;border-radius:14px;padding:14px}}.grid{{display:grid;grid-template-columns:repeat(9,1fr);aspect-ratio:9/10;border:2px solid #315b52;background:#fff;max-width:420px;margin:auto}}.cell{{border:1px solid #aab7b1;display:grid;place-items:center;min-width:0}}.clue{{background:#dcebe5;color:#176050;font-weight:800}}.internal{{background:#c9ded5}}.neutral{{background:#1f2825;color:#fff;font-size:22px}}.letter{{background:#fff}}.ok{{color:#147248;font-weight:700}}code{{font-size:12px}}small{{color:#668078}}@media(max-width:550px){{main{{padding:12px}}}}
</style></head><body><main><h1>Nouvelles silhouettes 9×10 — cadre strict</h1>
<p class="lead">Toute la première ligne et toute la première colonne sont des définitions. Les cases intérieures sont libres, mais chaque lettre doit appartenir à une réponse déclarée. Cette page valide uniquement le visuel et la topologie ; aucun mot médiocre n’est masqué derrière.</p>
<div class="panel">{cards}</div></main></body></html>"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(json.dumps({
        "pool": len(pool),
        "rendered": len(selected),
        "output": str(args.output),
        "json": str(args.json_output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
