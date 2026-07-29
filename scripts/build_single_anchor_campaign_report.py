#!/usr/bin/env python3
"""Build the bounded single-anchor campaign report (JSON + mobile HTML)."""
from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCAN = ROOT / "output/quality/semi-editorial-7x8-pilot/single-anchor-feasibility.json"
DEFAULT_ATTEMPTS = ROOT / "output/quality/semi-editorial-7x8-pilot"
DEFAULT_JSON = ROOT / "output/quality/semi-editorial-7x8-pilot/single-anchor-campaign-report.json"
DEFAULT_HTML = ROOT / "output/quality/semi-editorial-7x8-pilot/single-anchor-campaign-report.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", type=Path, default=DEFAULT_SCAN)
    parser.add_argument("--attempts-dir", type=Path, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--html-output", type=Path, default=DEFAULT_HTML)
    return parser.parse_args()


def summarize_matrix(scan: dict) -> list[dict]:
    grouped: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "placementCount": 0,
        "rootSurvivorCount": 0,
        "rootRejectedCount": 0,
        "rejectionCauses": defaultdict(int),
        "bestMinimumRemainingDomain": None,
    })
    for item in scan.get("placements", []):
        key = (str(item["anchor"]), str(item["shapeId"]))
        row = grouped[key]
        row["placementCount"] += 1
        if item.get("survives"):
            row["rootSurvivorCount"] += 1
            value = int(item["minimumRemainingDomain"])
            previous = row["bestMinimumRemainingDomain"]
            row["bestMinimumRemainingDomain"] = value if previous is None else max(previous, value)
        else:
            row["rootRejectedCount"] += 1
            row["rejectionCauses"][str(item.get("reason"))] += 1
    return [
        {
            "anchor": anchor,
            "shapeId": shape_id,
            **{key: value for key, value in values.items() if key != "rejectionCauses"},
            "rejectionCauses": dict(sorted(values["rejectionCauses"].items())),
        }
        for (anchor, shape_id), values in sorted(grouped.items())
    ]


def load_deep_attempts(directory: Path) -> list[dict]:
    attempts = []
    for path in sorted(directory.glob("deep-*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        requested = document.get("requestedFixedAnswers", {})
        if len(requested) != 1:
            continue
        slot_index, anchor = next(iter(requested.items()))
        telemetry = document.get("solverTelemetry", {})
        attempts.append({
            "artifact": path.name,
            "shapeId": document.get("sourceShapeId"),
            "anchor": anchor,
            "slotIndex": int(slot_index),
            "status": "solved" if document.get("complete") else telemetry.get("reason", "unknown"),
            "nodes": telemetry.get("nodes"),
            "elapsedSeconds": telemetry.get("elapsedSeconds"),
            "completeSolutions": telemetry.get("completeSolutions", 0),
            "contradiction": telemetry.get("lastContradiction"),
            "answers": [item.get("answer") for item in document.get("answers", [])],
        })
    return attempts


def render_html(report: dict) -> str:
    matrix_rows = []
    for row in report["rootMatrix"]:
        causes = ", ".join(
            f"{key}: {value}" for key, value in row["rejectionCauses"].items()
        ) or "—"
        matrix_rows.append(
            "<tr>"
            f"<td><strong>{html.escape(row['anchor'])}</strong></td>"
            f"<td>{html.escape(row['shapeId'].replace('corrected-7x8-', 'shape '))}</td>"
            f"<td>{row['placementCount']}</td>"
            f"<td class='ok'>{row['rootSurvivorCount']}</td>"
            f"<td>{row['bestMinimumRemainingDomain'] if row['bestMinimumRemainingDomain'] is not None else '—'}</td>"
            f"<td class='muted'>{html.escape(causes)}</td>"
            "</tr>"
        )
    attempt_rows = []
    for item in report["deepAttempts"]:
        contradiction = item.get("contradiction") or {}
        detail = contradiction.get("kind", "—")
        if contradiction.get("slot") is not None:
            detail += f" · slot {contradiction['slot']}"
        attempt_rows.append(
            "<tr>"
            f"<td><strong>{html.escape(item['anchor'])}</strong></td>"
            f"<td>{html.escape(str(item['shapeId']).replace('corrected-7x8-', 'shape '))}</td>"
            f"<td>{item['slotIndex']}</td>"
            f"<td class='bad'>{html.escape(item['status'])}</td>"
            f"<td>{item['nodes']}</td>"
            f"<td class='muted'>{html.escape(detail)}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Campagne mono-ancre 7×8</title>
<style>
:root{{--paper:#fffdf7;--ink:#17211b;--muted:#66736b;--line:#dce5dc;--ok:#176b45;--bad:#a33a32;--card:#f4f8f3}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 system-ui,sans-serif}}
main{{max-width:1120px;margin:auto;padding:20px}} h1{{font-size:clamp(25px,5vw,40px);margin:0 0 8px}} h2{{margin-top:30px}}
.lead{{max-width:760px;color:var(--muted)}} .cards{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:20px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}} .n{{display:block;font-size:27px;font-weight:800}}
.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:14px;background:white}} table{{border-collapse:collapse;width:100%;min-width:760px}}
th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}} th{{position:sticky;top:0;background:#edf4ed;font-size:12px;text-transform:uppercase}}
.ok{{color:var(--ok);font-weight:700}} .bad{{color:var(--bad);font-weight:700}} .muted{{color:var(--muted);font-size:13px}}
.decision{{border-left:5px solid var(--bad);background:#fff2ee;padding:14px 16px;border-radius:8px;margin-top:22px}}
@media(max-width:700px){{main{{padding:14px}}.cards{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main>
<h1>Campagne mono-ancre 7×8</h1>
<p class="lead">Une seule ancre relue est imposée. La seconde doit provenir librement du même réservoir. Les noms propres bruts et les verbes conjugués sont interdits.</p>
<section class="cards">
<div class="card"><span class="n">{report['rootScan']['placementCount']}</span>placements racine</div>
<div class="card"><span class="n">{report['rootScan']['rootRejectedCount']}</span>éliminés immédiatement</div>
<div class="card"><span class="n">{report['rootScan']['rootSurvivorCount']}</span>passent la propagation</div>
<div class="card"><span class="n">{len(report['deepAttempts'])}</span>recherches profondes</div>
</section>
<div class="decision"><strong>Aucune candidate produite.</strong> Les essais profonds sélectionnés sont tous infaisables avec deux entrées du réservoir strict. Aucun filtre n'a été relâché.</div>
<h2>Explorations profondes bornées</h2><div class="table-wrap"><table><thead><tr><th>Ancre</th><th>Silhouette</th><th>Slot</th><th>Statut</th><th>Nœuds</th><th>Dernier blocage</th></tr></thead><tbody>{''.join(attempt_rows)}</tbody></table></div>
<h2>Matrice de propagation racine</h2><div class="table-wrap"><table><thead><tr><th>Ancre</th><th>Silhouette</th><th>Placements</th><th>Survivants</th><th>Meilleur domaine min.</th><th>Rejets</th></tr></thead><tbody>{''.join(matrix_rows)}</tbody></table></div>
<p class="muted">Ce rapport ne prouve pas que toute construction semi-éditoriale est impossible. Il borne exactement les ancres, slots et silhouettes testés.</p>
</main></body></html>"""


def main() -> int:
    args = parse_args()
    scan = json.loads(args.scan.read_text(encoding="utf-8"))
    attempts = load_deep_attempts(args.attempts_dir)
    survivors = int(scan.get("survivingPlacementCount", 0))
    report = {
        "version": 1,
        "kind": "motman-bounded-single-anchor-campaign-report",
        "catalogModified": False,
        "runtimeModified": False,
        "supabaseModified": False,
        "publicationEligible": False,
        "candidateProduced": any(item["status"] == "solved" for item in attempts),
        "policy": {
            "columns": 7,
            "rows": 8,
            "oneFixedAnchorPerSearch": True,
            "minimumReviewedRescueAnswers": 2,
            "finiteVerbs": "forbidden",
            "rawProperNames": "forbidden",
            "excludedShape": "corrected-7x8-03",
        },
        "rootScan": {
            "artifact": args.scan.name,
            "placementCount": int(scan.get("placementCount", 0)),
            "rootSurvivorCount": survivors,
            "rootRejectedCount": int(scan.get("placementCount", 0)) - survivors,
            "rejectionCauses": scan.get("rejectionCauses", {}),
        },
        "deepAttemptCount": len(attempts),
        "deepSolvedCount": sum(item["status"] == "solved" for item in attempts),
        "deepAttempts": attempts,
        "rootMatrix": summarize_matrix(scan),
        "conclusion": (
            "Aucun des onze placements sélectionnés ne ferme avec deux entrées "
            "du petit réservoir relu. Cette conclusion ne s'étend pas aux 43 autres "
            "placements qui survivent seulement à la propagation racine."
        ),
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.html_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.html_output.write_text(render_html(report), encoding="utf-8")
    print(json.dumps({
        "candidateProduced": report["candidateProduced"],
        "rootScan": report["rootScan"],
        "deepAttemptCount": report["deepAttemptCount"],
        "deepSolvedCount": report["deepSolvedCount"],
        "json": str(args.json_output),
        "html": str(args.html_output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
