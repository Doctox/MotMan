"""Build the approved long-answer shape plus four owner-review variants."""
from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_long_answer_shape_pilot import (  # noqa: E402
    CURATED_CLUE_CELLS,
    band_counts,
    shape_from_clues,
    template_grid,
)
from grid_topology import audit_grid_topology  # noqa: E402


STAGING = ROOT / "src/data/grid-generation-handcrafted/long-answer-shapes.review.json"
HTML = ROOT / "output/quality/long-answer-shape-library.html"
ALLOWED_LAYOUT_WARNINGS = {
    "clue_wall", "too_many_adjacent_clue_pairs", "insufficient_double_clues"
}

# The first geometry is the one approved by the owner. The following four use
# different upper-border widths, left-border depths and pivot arrangements.
# They are fixed editorial masks, not random solver output.
SPECS = (
    ("long-answer-shape-01", None, None, None, "owner-approved"),
    ("long-answer-shape-02", 2, 4, (4,), "owner-rejected-similar"),
    ("long-answer-shape-03", 3, 3, (3, 3), "owner-rejected-similar"),
    ("long-answer-shape-04", 4, 4, (4, 4, 4), "owner-approved"),
    ("long-answer-shape-05", 4, 7, (7, 4, 6), "owner-approved"),
)


def structured_clues(k: int, left_depth: int, pivot_rows: tuple[int, ...]) -> set[tuple[int, int]]:
    clues = {(0, col) for col in range(k + 1)}
    clues.update((row, 0) for row in range(1, left_depth + 1))
    clues.update((1, col) for col in range(k + 1, 9))
    clues.update((row, 1) for row in range(left_depth + 1, 10))
    clues.update(
        (pivot_row, col)
        for col, pivot_row in zip(range(2, k + 1), pivot_rows, strict=True)
    )
    return clues


def review_record(
    shape_id: str,
    clues: set[tuple[int, int]],
    publication_status: str,
) -> dict:
    shape = shape_from_clues(clues)
    core = audit_grid_topology(template_grid(shape), enforce_layout=False)
    if not core["valid"]:
        raise ValueError(f"{shape_id}: topologie invalide {core['errorCounts']}")
    strict = audit_grid_topology(template_grid(shape), enforce_layout=True)
    unexpected = [
        error for error in strict["errors"]
        if error["code"] not in ALLOWED_LAYOUT_WARNINGS
    ]
    if unexpected:
        raise ValueError(f"{shape_id}: erreur hors exception visuelle {unexpected}")
    short, long = band_counts(shape["metrics"]["lengths"])
    if long <= short:
        raise ValueError(f"{shape_id}: les réponses longues ne sont pas majoritaires")
    if max(shape["metrics"]["lengths"]) > 8:
        raise ValueError(f"{shape_id}: réponse de plus de 8 lettres")
    return {
        "id": shape_id,
        "columns": 9,
        "rows": 10,
        "publicationStatus": publication_status,
        "approvedOn": "2026-07-16" if publication_status == "owner-approved" else None,
        "clueCells": shape["clueCells"],
        "slots": shape["slots"],
        "metrics": {
            **shape["metrics"],
            "letterCells": sum(cell["kind"] == "letter" for cell in core["cells"]),
            "orphanSegments": len(core["orphanSegments"]),
            "uncoveredLetters": core["errorCounts"].get("uncovered_letter", 0),
            "layoutWarningsAcceptedForPilot": strict["errorCounts"],
        },
    }


def render_grid(record: dict, number: int) -> str:
    clues = {tuple(cell) for cell in record["clueCells"]}
    launches: dict[tuple[int, int], list[tuple[str, int]]] = {}
    for slot in record["slots"]:
        launches.setdefault(tuple(slot["clue"]), []).append(
            ("→" if slot["direction"] == "across" else "↓", slot["length"])
        )
    cells = []
    for row in range(10):
        for col in range(9):
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
    metrics = record["metrics"]
    short, long = band_counts(metrics["lengths"])
    profile = " · ".join(
        f"{count}×{length}" for length, count in sorted(metrics["lengths"].items())
    )
    approved = record["publicationStatus"] == "owner-approved"
    rejected = record["publicationStatus"] == "owner-rejected-similar"
    status = "Validée" if approved else ("Écartée : trop proche" if rejected else "À relire")
    css_class = "approved" if approved else ("rejected" if rejected else "pending")
    return f"""<article class="{css_class}"><header><h2>Silhouette {number}</h2><b>{status}</b></header>
    <div class="ratio"><strong>{long} longues</strong><span>contre {short} courtes</span></div>
    <div class="grid">{''.join(cells)}</div>
    <p>{escape(profile)}</p><small>{metrics['clueCells']} définitions · {metrics['doubleClueCells']} doubles · {metrics['letterCells']} lettres couvertes</small></article>"""


def main() -> None:
    active = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    active_shapes = {
        tuple(sorted(tuple(cell) for cell in grid["clueCells"]))
        for grid in active["grids"]
    }
    records = []
    for shape_id, k, left_depth, pivot_rows, status in SPECS:
        clues = (
            set(CURATED_CLUE_CELLS)
            if k is None
            else structured_clues(k, left_depth, pivot_rows)
        )
        fingerprint = tuple(sorted(clues))
        if fingerprint in active_shapes:
            raise ValueError(f"{shape_id}: silhouette déjà utilisée par une grille active")
        records.append(review_record(shape_id, clues, status))
    fingerprints = {
        tuple(sorted(tuple(cell) for cell in record["clueCells"]))
        for record in records
    }
    if len(fingerprints) != len(records):
        raise ValueError("La bibliothèque contient deux silhouettes identiques")

    document = {
        "version": 1,
        "kind": "long-answer-shape-library",
        "policy": (
            "Réponses de 5 à 8 lettres strictement majoritaires face aux 2 à 4; "
            "flèches directes; couverture topologique complète; murs de définitions "
            "autorisés uniquement dans cette famille approuvée expérimentalement."
        ),
        "ownerApprovedShapeIds": [
            record["id"] for record in records
            if record["publicationStatus"] == "owner-approved"
        ],
        "ownerRejectedShapeIds": [
            record["id"] for record in records
            if record["publicationStatus"] == "owner-rejected-similar"
        ],
        "ownerReviewRequiredShapeIds": [],
        "shapes": records,
    }
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    HTML.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cards = "".join(render_grid(record, number) for number, record in enumerate(records, 1))
    HTML.write_text(f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MotMan — silhouettes longues</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f1e8;color:#173b35;font-family:system-ui,sans-serif}}main{{max-width:1180px;margin:auto;padding:26px}}
.intro{{max-width:850px;line-height:1.5}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:22px}}
article{{background:#fffdf8;border:1px solid #bfd0c7;border-radius:16px;padding:16px;box-shadow:0 10px 28px #315b4d12}}article.approved{{border:3px solid #2f8b61}}article.rejected{{opacity:.55;filter:grayscale(.65)}}
header,.ratio{{display:flex;align-items:baseline;justify-content:space-between;gap:12px}}h2{{margin:0;font-size:19px}}header b{{font-size:12px;color:#2f7658}}.pending header b{{color:#8a6234}}
.ratio{{margin:10px 0;font-size:13px}}.ratio strong{{font-size:17px}}.grid{{display:grid;grid-template-columns:repeat(9,1fr);aspect-ratio:9/10;border:2px solid #315b4d;background:#315b4d;gap:1px}}
.cell{{min-width:0;background:#fffdf8;display:flex;align-items:center;justify-content:center}}.neutral{{background:#243d38;color:white;font-size:20px}}.clue{{background:#dce9e2;flex-direction:column;gap:2px;font-weight:800;font-size:9px}}.clue span{{white-space:nowrap}}
article p,article small{{color:#587068;font-size:12px}}@media(max-width:430px){{main{{padding:12px}}.cards{{grid-template-columns:1fr}}.clue{{font-size:8px}}}}
</style></head><body><main><h1>Bibliothèque de silhouettes à réponses longues</h1>
<p class="intro">La première est celle que tu viens de valider. Les quatre suivantes sont de nouveaux prototypes non publiés. Chaque case-lettre est couverte, les flèches sont directes et les longueurs affichées permettent de juger la forme sans faux couples mot/définition.</p>
<section class="cards">{cards}</section></main></body></html>""", encoding="utf-8")
    print(json.dumps({
        "status": "built",
        "html": str(HTML),
        "staging": str(STAGING),
        "approved": 3,
        "rejectedSimilar": 2,
        "ownerReviewRequired": 0,
        "ratios": [
            {"id": record["id"], "short": band_counts(record["metrics"]["lengths"])[0], "long": band_counts(record["metrics"]["lengths"])[1]}
            for record in records
        ],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
