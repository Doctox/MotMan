"""Render five corpus-aware silhouettes without leaking rejected draft words."""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from optimize_grid_shapes import optimize  # noqa: E402
SOURCES = (
    ROOT / "output/quality/corpus-aware-handcrafted-five-drafts.json",
    ROOT / "output/quality/corpus-aware-full-candidate-pool.json",
)
OUTPUT = ROOT / "output/quality/corpus-aware-shape-pilot.html"


def load_unique_shapes(limit: int = 5) -> list[dict]:
    selected: list[dict] = []
    fingerprints: set[tuple[tuple[int, int], ...]] = set()
    for path in SOURCES:
        if not path.exists():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        for grid in document.get("grids", []):
            fingerprint = tuple(sorted(tuple(cell) for cell in grid["clueCells"]))
            if fingerprint in fingerprints:
                continue
            fingerprints.add(fingerprint)
            selected.append(grid)
            if len(selected) == limit:
                return selected
    previous_shapes = [
        {tuple(cell) for cell in grid["clueCells"]} for grid in selected
    ]
    rng = random.Random(26071580)
    for attempt in range(80):
        penalties = {
            (row, col): rng.randint(0, 3)
            for row in range(1, 10) for col in range(1, 9)
        }
        shape = optimize(
            timeout=1.5,
            seed=26071580 + attempt,
            visible_clue_cells=22,
            minimum_double_clues=3,
            maximum_double_clues=10,
            maximum_adjacent_pairs=3,
            maximum_top_border_clues=8,
            maximum_left_border_clues=9,
            maximum_border_clue_run=8,
            maximum_length_two_answers=2,
            only_direct_arrows=True,
            required_lengths=(5, 6),
            require_length_bands=False,
            enforce_length_balance=False,
            enforce_clue_spacing=False,
            enforce_interior_line_limits=False,
            enforce_clue_triples=True,
            enforce_solid_clue_blocks=True,
            columns=9,
            rows=10,
            maximum_answer_length=8,
            short_answer_penalty=100,
            answer_length_penalties={2: 260, 3: 80, 4: 20, 5: 6, 6: 2, 7: 0, 8: 1},
            position_penalties=penalties,
            previous_shapes=previous_shapes,
            maximum_shape_overlap=16,
        )
        if not shape:
            continue
        fingerprint = tuple(sorted(tuple(cell) for cell in shape["clueCells"]))
        if fingerprint in fingerprints:
            continue
        profile = Counter(slot["length"] for slot in shape["slots"])
        if profile[2] > 2 or profile[3] > 7:
            continue
        dummy_words = [{
            "direction": slot["direction"],
            "arrow": slot["arrow"],
            "clueCell": slot["clue"],
            "cells": slot["cells"],
            "answer": "X" * slot["length"],
        } for slot in shape["slots"]]
        grid = {
            "clueCells": shape["clueCells"],
            "words": dummy_words,
            "lengthProfile": dict(sorted(profile.items())),
        }
        fingerprints.add(fingerprint)
        selected.append(grid)
        previous_shapes.append(set(fingerprint))
        if len(selected) == limit:
            break
    return selected


def render_grid(grid: dict, number: int) -> str:
    clue_cells = {tuple(cell) for cell in grid["clueCells"]}
    launches: dict[tuple[int, int], list[tuple[str, int]]] = {}
    for word in grid["words"]:
        arrow = "→" if word["direction"] == "across" else "↓"
        launches.setdefault(tuple(word["clueCell"]), []).append(
            (arrow, len(word["answer"]))
        )
    cells = []
    for row in range(10):
        for col in range(9):
            cell = (row, col)
            if cell == (0, 0):
                cells.append('<div class="cell neutral">Ø</div>')
            elif cell in clue_cells:
                labels = "".join(
                    f'<span>{escape(arrow)} {length}</span>'
                    for arrow, length in launches.get(cell, [])
                )
                cells.append(f'<div class="cell clue">{labels}</div>')
            else:
                cells.append('<div class="cell letter"></div>')
    profile = grid.get("lengthProfile", {})
    profile_text = " · ".join(
        f'{count}×{length} lettres'
        for length, count in sorted(profile.items(), key=lambda item: int(item[0]))
        if count
    )
    short = int(profile.get("2", profile.get(2, 0))) + int(
        profile.get("3", profile.get(3, 0))
    )
    long = sum(
        int(profile.get(str(length), profile.get(length, 0)))
        for length in (5, 6, 7, 8)
    )
    return f"""
    <article>
      <header><h2>Silhouette {number}</h2><span>{short} courtes · {long} longues</span></header>
      <div class="grid">{''.join(cells)}</div>
      <p>{escape(profile_text)}</p>
    </article>"""


def main() -> None:
    grids = load_unique_shapes()
    if len(grids) < 5:
        raise SystemExit(f"Seulement {len(grids)} silhouettes distinctes disponibles")
    cards = "".join(render_grid(grid, number) for number, grid in enumerate(grids, 1))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>MotMan — silhouettes guidées par le corpus</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f1e8;color:#173b35;font-family:system-ui,sans-serif}}
main{{max-width:1180px;margin:auto;padding:28px}}h1{{margin:0 0 8px}}.intro{{max-width:780px;line-height:1.5;margin-bottom:24px}}
.pilot{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:22px}}
article{{background:#fffdf8;border:1px solid #c9d7ce;border-radius:16px;padding:16px;box-shadow:0 8px 24px #315b4d14}}
article header{{display:flex;align-items:baseline;justify-content:space-between;gap:12px}}h2{{font-size:18px;margin:0 0 12px}}
article header span,article p{{font-size:12px;color:#587068}}article p{{margin:12px 0 0;line-height:1.4}}
.grid{{display:grid;grid-template-columns:repeat(9,1fr);aspect-ratio:9/10;border:2px solid #315b4d;background:#315b4d;gap:1px}}
.cell{{min-width:0;background:#fffdf8;display:flex;align-items:center;justify-content:center}}
.neutral{{background:#243d38;color:#fff;font-size:20px}}.clue{{background:#dce9e2;flex-direction:column;gap:2px;color:#174d43;font-weight:750;font-size:10px}}
.letter{{background:#fffefb}}.clue span{{white-space:nowrap}}
@media(max-width:430px){{main{{padding:14px}}.pilot{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Silhouettes guidées par le corpus</h1>
<p class="intro">Pilote visuel uniquement : les mots automatiques rejetés ne sont pas affichés. Les flèches restent directes, chaque case-lettre est couverte, aucune rangée intérieure de trois définitions n’est autorisée et les formes privilégient les longueurs 5 à 8.</p>
<section class="pilot">{cards}</section>
</main></body></html>""", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
