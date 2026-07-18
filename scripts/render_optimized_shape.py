"""Render one or more CP-SAT silhouette JSON files without fake clue text."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from html import escape
from pathlib import Path


ARROWS = {
    "right": "→", "down": "↓", "downright": "↳→", "rightdown": "↳↓",
}


def render_shape(shape: dict, source: Path) -> str:
    rows, columns = shape["rows"], shape["columns"]
    clues = {tuple(cell) for cell in shape["clueCells"]}
    arrows = defaultdict(list)
    for slot in shape["slots"]:
        arrows[tuple(slot["clue"])].append(ARROWS[slot["arrow"]])
    rendered_rows = []
    for row in range(rows):
        cells = []
        for col in range(columns):
            cell = (row, col)
            if cell == (0, 0):
                cells.append("<td class='neutral'>∅</td>")
            elif cell in clues:
                cells.append(f"<td class='clue'>{'<br>'.join(arrows[cell])}</td>")
            else:
                cells.append("<td></td>")
        rendered_rows.append("<tr>" + "".join(cells) + "</tr>")
    metrics = shape["metrics"]
    return f"""
    <article><h2>{escape(source.stem)}</h2><table>{''.join(rendered_rows)}</table>
    <p>{columns}×{rows} · {metrics['clueCells']} définitions ·
    {metrics['doubleClueCells']} doubles · {len(shape['slots'])} réponses</p>
    <small>Longueurs : {escape(str(metrics['lengths']))}</small></article>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cards = [render_shape(json.loads(path.read_text(encoding="utf-8")), path)
             for path in args.inputs]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>Pilotes de silhouettes</title>
<style>body{{font:14px system-ui;margin:24px;background:#f4f1eb;color:#29251f}}article{{background:white;padding:18px;border-radius:12px;width:max-content}}
table{{border-collapse:collapse}}td{{width:32px;height:32px;border:1px solid #aaa;text-align:center;font-size:10px;line-height:11px}}
.clue{{background:#ddd7cb;font-weight:700}}.neutral{{background:#29251f;color:white}}</style>
</head><body><h1>Pilotes non publiés</h1><p>Comparaison géométrique uniquement : aucune fausse définition n’est affichée.</p>
{''.join(cards)}</body></html>""", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
