"""Render the curated silhouette library for quick human review."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from generate_grid_catalog import SHAPES, SIZE, shape_errors, slots_for


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "quality" / "shape-library.html"
AUDIT_OUTPUT = ROOT / "output" / "quality" / "shape-library-audit.json"
ARROWS = {"right": "→", "down": "↓", "downright": "↳→", "rightdown": "↳↓"}


def main() -> None:
    position_usage = Counter(
        cell for shape in SHAPES for cell in set(shape) - {(0, 0)}
    )
    structural_anchors = {
        cell for cell, count in position_usage.items() if count >= len(SHAPES) * .75
    }
    global_pair_usage = Counter()
    for shape in SHAPES:
        visible = set(shape) - {(0, 0)}
        global_pair_usage.update({
            tuple(sorted((cell, neighbor)))
            for cell in visible
            for neighbor in ((cell[0] + 1, cell[1]), (cell[0], cell[1] + 1))
            if neighbor in visible
        })
    cards = []
    for index, raw_shape in enumerate(SHAPES, 1):
        clues = set(raw_shape)
        slots = slots_for(clues)
        errors = shape_errors(clues, slots)
        if errors:
            raise SystemExit(f"silhouette {index}: {errors}")
        arrows_by_clue = defaultdict(list)
        for slot in slots:
            arrows_by_clue[slot.clue].append(ARROWS[slot.arrow])
        rows = []
        for row in range(SIZE):
            cells = []
            for col in range(SIZE):
                cell = (row, col)
                if cell == (0, 0):
                    cells.append("<td class='neutral'>∅</td>")
                elif cell in clues:
                    arrows = "<br>".join(arrows_by_clue[cell])
                    scaffold = " scaffold" if cell in structural_anchors else ""
                    cells.append(f"<td class='clue{scaffold}'>{arrows}</td>")
                else:
                    cells.append("<td></td>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        uses = Counter(slot.clue for slot in slots)
        lengths = Counter(len(slot.cells) for slot in slots)
        visible = clues - {(0, 0)}
        adjacent_pairs = sum(
            neighbor in visible
            for row, col in visible
            for neighbor in ((row + 1, col), (row, col + 1))
        )
        cards.append(f"""
        <article><h2>Famille {index}</h2><table>{''.join(rows)}</table>
        <p>{len(clues) - 1} définitions · {sum(value == 2 for value in uses.values())} doubles ·
        {len(slots)} mots · {adjacent_pairs} paires collées</p>
        <small>Longueurs : {dict(sorted(lengths.items()))}</small></article>""")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    audit = {
        "version": 1,
        "familyCount": len(SHAPES),
        "structuralAnchors": [
            {"cell": list(cell), "families": position_usage[cell]}
            for cell in sorted(structural_anchors)
        ],
        "uniqueAdjacentPairPlacements": len(global_pair_usage),
        "maximumAdjacentPairReuse": max(global_pair_usage.values()),
        "adjacentPairUsage": [
            {"cells": [list(cell) for cell in pair], "families": count}
            for pair, count in global_pair_usage.most_common()
        ],
    }
    AUDIT_OUTPUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT.write_text(f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>Silhouettes MotMan</title>
<style>body{{font:14px system-ui;margin:24px;background:#f4f1eb;color:#29251f}}h1{{margin-bottom:4px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:18px}}article{{background:white;padding:15px;border-radius:12px}}
table{{border-collapse:collapse}}td{{width:25px;height:25px;border:1px solid #aaa;text-align:center;font-size:9px;line-height:10px}}
.clue{{background:#ddd7cb;font-weight:700}}.clue.scaffold{{background:#c7b99f}}.neutral{{background:#29251f;color:white}}p{{margin-bottom:4px}}small{{color:#655f56}}</style>
</head><body><h1>{len(SHAPES)} familles de silhouettes</h1><p>Les rotations et miroirs ne comptent pas comme familles supplémentaires.</p>
<p><b>Cadre structurel</b> (beige foncé) : {len(structural_anchors)} ancrages communs à au moins 75 % des familles. L’intérieur conserve {len(global_pair_usage)} placements distincts pour les deux voisinages, avec un maximum de {max(global_pair_usage.values())}/{len(SHAPES)} réutilisations.</p>
<main class='cards'>{''.join(cards)}</main></body></html>""", encoding="utf-8")
    print(OUTPUT)
    print(AUDIT_OUTPUT)


if __name__ == "__main__":
    main()
