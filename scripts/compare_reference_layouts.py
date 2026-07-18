"""Compare MotMan silhouettes with published/open arrowword layouts.

Only anonymous geometry is retained: no third-party clues or answers are
written to the report.
"""
from __future__ import annotations

import argparse
import gzip
import json
import statistics
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from generate_grid_catalog import SHAPES, slots_for
from import_leparisien_corpus import (
    CELL_ARROW_SPECS, DEPRECATED_ARROW_SPECS, GRID_URL, parse_mfj,
)


ROOT = Path(__file__).resolve().parents[1]
MOTSFLEX_URL = (
    "https://raw.githubusercontent.com/Leo-Nicolle/mots-fleches/"
    "8eca4072530cf5b961ce4b7b32e8bd8345dd8852/client/public/debug-db-8.json"
)


def fetch_json_or_text(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "MotMan-layout-audit/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def base_metrics(rows: int, cols: int, clues: set[tuple[int, int]]) -> dict:
    adjacent = sum(
        neighbor in clues
        for row, col in clues
        for neighbor in ((row + 1, col), (row, col + 1))
    )
    return {
        "rows": rows, "cols": cols, "area": rows * cols,
        "clueCells": len(clues),
        "clueDensity": round(len(clues) / (rows * cols), 4),
        "adjacentCluePairs": adjacent,
        "cluePositions": [list(cell) for cell in sorted(clues)],
    }


def leparisien_metric(item: tuple[int, str]) -> dict:
    force, puzzle_id = item
    number = puzzle_id.rsplit("_", 1)[-1]
    url = GRID_URL.format(force=force, number=number)
    data = parse_mfj(fetch_json_or_text(url).decode("utf-8-sig"))
    grid = data["grille"]
    specs = []
    clues = set()
    for row, line in enumerate(grid):
        for col, character in enumerate(line):
            spec = DEPRECATED_ARROW_SPECS.get(character)
            if spec:
                clues.add((row, col)); specs.append(spec)
    result = base_metrics(len(grid), len(grid[0]), clues)
    result.update({
        "source": "Le Parisien/RCI", "force": force, "puzzleId": puzzle_id,
        "doubleClueCells": sum(spec.startswith("d") for spec in specs),
        "directRightDownDoubles": specs.count("d2"),
        "arrowSpecs": dict(sorted(Counter(
            arrow for spec in specs for arrow in CELL_ARROW_SPECS[spec]
        ).items())),
    })
    return result


def motman_metrics() -> list[dict]:
    reports = []
    for index, shape in enumerate(SHAPES, 1):
        clues = set(shape) - {(0, 0)}
        slots = slots_for(set(shape))
        grouped = defaultdict(list)
        for slot in slots:
            grouped[slot.clue].append(slot.arrow)
        result = base_metrics(9, 9, clues)
        result.update({
            "source": "MotMan", "family": index,
            "doubleClueCells": sum(len(arrows) == 2 for arrows in grouped.values()),
            "directRightDownDoubles": sum(
                set(arrows) == {"right", "down"} for arrows in grouped.values()
            ),
            "words": len(slots),
        })
        reports.append(result)
    return reports


def motsflex_metrics() -> list[dict]:
    data = json.loads(fetch_json_or_text(MOTSFLEX_URL).decode("utf-8"))
    reports = []
    for index, grid in enumerate(data["grids"]):
        clues = {
            (row, col)
            for row, line in enumerate(grid["cells"])
            for col, cell in enumerate(line) if cell["definition"]
        }
        result = base_metrics(grid["rows"], grid["cols"], clues)
        double_count = direct_count = 0
        for row, col in clues:
            arrows = [arrow for arrow in grid["cells"][row][col].get("arrows", [])
                      if arrow != "none"]
            if len(arrows) >= 2:
                double_count += 1
                direct_count += set(arrows) == {"right", "down"}
        result.update({
            "source": "MotsFlex", "example": index,
            "doubleClueCells": double_count,
            "directRightDownDoubles": direct_count,
        })
        reports.append(result)
    return reports


def aggregate(rows: list[dict]) -> dict:
    def summary(key: str) -> dict:
        values = [row[key] for row in rows]
        return {
            "minimum": min(values), "median": round(statistics.median(values), 3),
            "maximum": max(values),
        }
    return {
        "count": len(rows),
        "sizes": dict(sorted(Counter(f"{row['rows']}x{row['cols']}" for row in rows).items())),
        "clueCells": summary("clueCells"),
        "clueDensity": summary("clueDensity"),
        "adjacentCluePairs": summary("adjacentCluePairs"),
        "doubleClueCells": summary("doubleClueCells"),
        "directRightDownDoubles": summary("directRightDownDoubles"),
    }


def common_anchors(rows: list[dict], minimum_share: float = .75) -> list[dict]:
    counts = Counter(
        tuple(position)
        for row in rows
        for position in row["cluePositions"]
    )
    return [
        {"row": position[0], "col": position[1], "families": count}
        for position, count in counts.most_common()
        if count >= len(rows) * minimum_share
    ]


def html_report(result: dict) -> str:
    def mask(grid: dict) -> str:
        clues = {tuple(cell) for cell in grid["cluePositions"]}
        cells = "".join(
            f"<i class={'clue' if (row, col) in clues else 'letter'}></i>"
            for row in range(grid["rows"]) for col in range(grid["cols"])
        )
        return (
            f"<div class='mask' style='grid-template-columns:repeat({grid['cols']},12px)'>{cells}</div>"
        )
    rows = []
    for name, stats in result["summary"].items():
        rows.append(
            f"<tr><th>{name}</th><td>{stats['count']}</td><td>{stats['sizes']}</td>"
            f"<td>{stats['clueDensity']}</td><td>{stats['adjacentCluePairs']}</td>"
            f"<td>{stats['doubleClueCells']}</td><td>{stats['directRightDownDoubles']}</td></tr>"
        )
    examples = []
    for name, grids in result["details"].items():
        examples.append(
            f"<section><h3>{name}</h3><div class='examples'>"
            + "".join(mask(grid) for grid in grids[:4]) + "</div></section>"
        )
    anchors = ", ".join(
        f"({item['row'] + 1}, {item['col'] + 1}) : {item['families']}/12"
        for item in result["motmanCommonAnchors"]
    )
    published_anchors = ", ".join(
        f"({item['row'] + 1}, {item['col'] + 1})"
        for item in result["leParisienFixedAnchors"]
    )
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>Comparaison des placements</title>
<style>body{{font:15px system-ui;margin:28px;background:#f4f1eb;color:#28241f}}main{{max-width:1100px;margin:auto;background:white;padding:24px;border-radius:14px}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #c9c1b5;padding:8px;text-align:left}}th{{background:#eee9df}}code{{background:#eee9df;padding:2px 4px}}li{{margin:8px 0}}
.examples{{display:flex;gap:16px;flex-wrap:wrap}}.mask{{display:grid;gap:1px;background:#aaa;padding:1px;width:max-content}}.mask i{{width:12px;height:12px;background:white}}.mask i.clue{{background:#777066}}</style></head>
<body><main><h1>MotMan comparé à des mots fléchés existants</h1>
<p>Les valeurs sont min/médiane/max. Aucun mot ni définition tiers n’est reproduit.</p>
<table><thead><tr><th>Source</th><th>Grilles</th><th>Formats</th><th>Densité déf.</th><th>Paires voisines</th><th>Doubles</th><th>Doubles → + ↓</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<h2>Silhouettes anonymisées</h2>{''.join(examples)}
<h2>Ce qu’ils font différemment</h2><ul>
<li>Le Parisien utilise principalement un format <b>9×14</b>, beaucoup moins contraint horizontalement que notre 9×9.</li>
<li>MotsFlex emploie surtout des formats <b>13×10</b>; son fichier est une base de démonstration/éditeur, pas un catalogue publié homogène.</li>
<li>Les références mélangent elles aussi les quatre combinaisons de doubles. Toutes leurs doubles ne sont pas <code>→ + ↓</code>.</li>
<li>Notre répétition vient surtout du format carré compact, du coin neutre et des réponses uniquement gauche→droite / haut→bas.</li>
<li>Le squelette MotMan est objectivement répétitif : cases communes à au moins 9 familles sur 12 : <code>{anchors}</code>.</li>
<li>Ce principe existe aussi dans les grilles publiées : les 40 échantillons Le Parisien partagent exactement les mêmes onze ancrages de bord : <code>{published_anchors}</code>. Leur variation se concentre à l’intérieur.</li>
</ul>
<h2>Sources</h2><ul><li><a href='https://static.rcijeux.fr/drupal_game/leparisien/'>Le Parisien / RCI</a></li>
<li><a href='https://github.com/Leo-Nicolle/mots-fleches'>MotsFlex, licence MIT</a></li></ul>
</main></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-per-force", type=int, default=10)
    parser.add_argument("--json-output", type=Path,
                        default=ROOT / "output/quality/reference-layout-comparison.json")
    parser.add_argument("--html-output", type=Path,
                        default=ROOT / "output/quality/reference-layout-comparison.html")
    args = parser.parse_args()
    with gzip.open(ROOT / "src/data/crossword.leparisien.raw.json.gz", "rt", encoding="utf-8") as stream:
        raw = json.load(stream)
    by_force = defaultdict(list)
    for pair in raw["pairs"]:
        puzzle_id = pair["puzzleId"]
        if puzzle_id not in by_force[pair["force"]]:
            by_force[pair["force"]].append(puzzle_id)
    sample = [
        (force, puzzle_id)
        for force in range(1, 5)
        for puzzle_id in by_force[force][:args.sample_per_force]
    ]
    with ThreadPoolExecutor(max_workers=8) as executor:
        leparisien = list(executor.map(leparisien_metric, sample))
    motman = motman_metrics()
    motsflex = motsflex_metrics()
    groups = {
        "MotMan 9x9": motman,
        "Le Parisien/RCI": leparisien,
        "MotsFlex MIT": [row for row in motsflex if row["rows"] <= 15 and row["cols"] <= 15],
    }
    result = {
        "version": 1,
        "method": "anonymous geometry only",
        "summary": {name: aggregate(rows) for name, rows in groups.items()},
        "motmanCommonAnchors": common_anchors(motman),
        "leParisienFixedAnchors": common_anchors(leparisien, 1.0),
        "details": groups,
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    args.html_output.write_text(html_report(result), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
