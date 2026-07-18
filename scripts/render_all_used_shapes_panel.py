"""Render every playable catalog silhouette plus approved future templates."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "src/data/grid.catalog.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
TEMPLATES = ROOT / "src/data/grid-generation-handcrafted/long-answer-shapes.review.json"
OUTPUT_JSON = ROOT / "output/quality/all-used-shapes-panel.json"
OUTPUT_HTML = ROOT / "output/quality/all-used-shapes-panel.html"


def fingerprint(clue_cells: list[list[int]]) -> str:
    payload = json.dumps(sorted(clue_cells), separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def band_counts(slots: list[dict]) -> tuple[int, int]:
    lengths = Counter(int(slot["length"]) for slot in slots)
    return (
        sum(lengths[length] for length in range(2, 5)),
        sum(lengths[length] for length in range(5, 9)),
    )


def grid_slots(grid: dict) -> list[dict]:
    return [
        {
            "clue": word["clueCell"],
            "direction": word["direction"],
            "arrow": word.get("arrow", "right" if word["direction"] == "across" else "down"),
            "length": len(word["answer"]),
        }
        for word in grid["words"]
    ]


def record(source: str, item: dict, slots: list[dict]) -> dict:
    launches = Counter(tuple(slot["clue"]) for slot in slots)
    lengths = Counter(int(slot["length"]) for slot in slots)
    short, long = band_counts(slots)
    return {
        "id": item["id"],
        "source": source,
        "columns": item["columns"],
        "rows": item["rows"],
        "clueCells": item["clueCells"],
        "slots": slots,
        "fingerprint": fingerprint(item["clueCells"]),
        "metrics": {
            "definitions": len(item["clueCells"]) - 1,
            "doubleDefinitions": sum(count == 2 for count in launches.values()),
            "answers": len(slots),
            "shortAnswers2To4": short,
            "longAnswers5To8": long,
            "lengths": dict(sorted(lengths.items())),
        },
    }


def render_card(item: dict) -> str:
    clues = {tuple(cell) for cell in item["clueCells"]}
    launches: dict[tuple[int, int], list[tuple[str, int]]] = {}
    for slot in item["slots"]:
        launches.setdefault(tuple(slot["clue"]), []).append(
            ("→" if slot["direction"] == "across" else "↓", slot["length"])
        )
    cells = []
    for row in range(item["rows"]):
        for col in range(item["columns"]):
            cell = (row, col)
            if cell == (0, 0):
                cells.append('<div class="cell neutral">Ø</div>')
            elif cell in clues:
                labels = "".join(
                    f'<span>{escape(arrow)}{length}</span>'
                    for arrow, length in launches.get(cell, [])
                )
                cells.append(f'<div class="cell clue">{labels}</div>')
            else:
                cells.append('<div class="cell letter"></div>')
    metrics = item["metrics"]
    profile = " · ".join(
        f"{count}×{length}" for length, count in sorted(metrics["lengths"].items())
    )
    label = "Gabarit approuvé" if item["source"] == "approved-template" else "En jeu"
    return f"""<article class="{'template' if item['source'] == 'approved-template' else 'active'}">
    <header><h3>{escape(item['id'])}</h3><b>{label}</b></header>
    <div class="grid">{''.join(cells)}</div>
    <p>{escape(profile)}</p>
    <small>{metrics['definitions']} déf. · {metrics['doubleDefinitions']} doubles · {metrics['answers']} réponses<br>
    5–8 lettres : {metrics['longAnswers5To8']} · 2–4 lettres : {metrics['shortAnswers2To4']}</small></article>"""


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    templates = json.loads(TEMPLATES.read_text(encoding="utf-8"))
    quarantined = set(blacklist.get("quarantinedGridIds", []))

    active_records = [
        record("active-catalog", grid, grid_slots(grid))
        for grid in catalog["grids"]
        if grid["id"] not in quarantined
    ]
    approved_ids = set(templates["ownerApprovedShapeIds"])
    template_records = [
        record("approved-template", shape, shape["slots"])
        for shape in templates["shapes"]
        if shape["id"] in approved_ids
    ]
    rejected_ids = set(templates.get("ownerRejectedShapeIds", []))
    if approved_ids & rejected_ids:
        raise ValueError("Une silhouette est à la fois approuvée et rejetée")
    records = [*template_records, *active_records]
    fingerprints = [item["fingerprint"] for item in records]
    if len(fingerprints) != len(set(fingerprints)):
        repeated = sorted(key for key, count in Counter(fingerprints).items() if count > 1)
        raise ValueError(f"Silhouettes utilisées en double : {repeated}")

    document = {
        "version": 1,
        "kind": "all-used-shapes-panel",
        "metrics": {
            "approvedTemplates": len(template_records),
            "playableCatalogShapes": len(active_records),
            "totalUniqueShapes": len(records),
            "rejectedTemplatesExcluded": sorted(rejected_ids),
        },
        "approvedTemplates": template_records,
        "playableCatalogShapes": active_records,
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    template_cards = "".join(render_card(item) for item in template_records)
    active_cards = "".join(render_card(item) for item in active_records)
    OUTPUT_HTML.write_text(f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MotMan — panel des silhouettes utilisées</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f1e8;color:#173b35;font-family:system-ui,sans-serif}}main{{max-width:1500px;margin:auto;padding:24px}}
.summary{{background:#e7f4ec;border-left:5px solid #2f815d;padding:13px 16px;max-width:900px;line-height:1.5}}h2{{margin-top:32px}}.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(205px,1fr));gap:15px}}
article{{background:#fffdf8;border:1px solid #c6d3cc;border-radius:12px;padding:10px;box-shadow:0 6px 18px #315b4d10}}article.template{{border:3px solid #2f8b61}}
header{{min-height:38px}}h3{{font-size:12px;margin:0;overflow-wrap:anywhere}}header b{{font-size:10px;color:#2e7657}}.grid{{display:grid;grid-template-columns:repeat(9,1fr);aspect-ratio:9/10;border:1px solid #315b4d;background:#315b4d;gap:1px;margin-top:7px}}
.cell{{min-width:0;background:#fffdf8;display:flex;align-items:center;justify-content:center}}.neutral{{background:#243d38;color:white;font-size:12px}}.clue{{background:#dce9e2;flex-direction:column;font-size:6px;font-weight:800;line-height:7px}}.clue span{{white-space:nowrap}}
article p,article small{{font-size:9px;color:#587068;line-height:1.35}}article p{{margin:7px 0 3px}}@media(max-width:480px){{main{{padding:10px}}.cards{{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}}}}
</style></head><body><main><h1>Panel des silhouettes conservées</h1>
<p class="summary"><b>{len(records)} silhouettes uniques</b> : {len(template_records)} nouveaux gabarits approuvés et {len(active_records)} silhouettes actuellement jouables. Les variantes 2 et 3 refusées pour ressemblance sont exclues de cette planche.</p>
<h2>Nouveaux gabarits approuvés</h2><section class="cards">{template_cards}</section>
<h2>Silhouettes actuellement dans le jeu</h2><section class="cards">{active_cards}</section>
</main></body></html>""", encoding="utf-8")
    print(json.dumps({
        "status": "built",
        "html": str(OUTPUT_HTML),
        "json": str(OUTPUT_JSON),
        **document["metrics"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
