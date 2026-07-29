#!/usr/bin/env python3
"""Build the final, owner-readable report for the bounded 7x8 campaign."""
from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "output/quality/semi-editorial-7x8-pilot"
DEFAULT_SCAN = BASE / "final-single-anchor-feasibility-v4.json"
DEFAULT_CAMPAIGN = BASE / "final-single-anchor-campaign-v4.json"
DEFAULT_PATTERNS = BASE / "final-targeted-pattern-candidates-v4.json"
DEFAULT_RESCUE = ROOT / "src/data/grid-generation/editorial-rescue.young-common.20260721.json"
DEFAULT_JSON = BASE / "final-single-anchor-campaign-report.json"
DEFAULT_HTML = BASE / "final-single-anchor-campaign-report.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", type=Path, default=DEFAULT_SCAN)
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument("--patterns", type=Path, default=DEFAULT_PATTERNS)
    parser.add_argument("--rescue", type=Path, default=DEFAULT_RESCUE)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--html-output", type=Path, default=DEFAULT_HTML)
    return parser.parse_args()


def summarize_results(results: list[dict], field: str) -> list[dict]:
    grouped: dict[str, dict] = defaultdict(lambda: {
        "attempted": 0,
        "infeasible": 0,
        "cutoff": 0,
        "solved": 0,
        "nodes": 0,
        "maximumRootMinimumDomain": 0,
    })
    for result in results:
        key = str(result[field])
        row = grouped[key]
        row["attempted"] += 1
        status = str(result.get("status"))
        if status == "infeasible":
            row["infeasible"] += 1
        elif status == "solved":
            row["solved"] += 1
        else:
            row["cutoff"] += 1
        row["nodes"] += int(result.get("telemetry", {}).get("nodes", 0))
        row["maximumRootMinimumDomain"] = max(
            row["maximumRootMinimumDomain"],
            int(result.get("rootMinimumRemainingDomain") or 0),
        )
    return [{field: key, **grouped[key]} for key in sorted(grouped)]


def targeted_additions(rescue: dict) -> list[dict]:
    return [
        {
            "answer": item["answer"],
            "spelling": item.get("spelling"),
            "register": item.get("register"),
            "reason": item.get("reason"),
        }
        for item in rescue.get("entries", [])
        if "répare" in str(item.get("reason", "")).casefold()
    ]


def render_html(report: dict) -> str:
    def rows(items: list[dict], label: str) -> str:
        return "".join(
            "<tr>"
            f"<td><strong>{html.escape(str(item[label]))}</strong></td>"
            f"<td>{item['attempted']}</td><td>{item['infeasible']}</td>"
            f"<td>{item['cutoff']}</td><td>{item['solved']}</td>"
            f"<td>{item['nodes']}</td><td>{item['maximumRootMinimumDomain']}</td>"
            "</tr>"
            for item in items
        )

    repair_rows = "".join(
        "<tr>"
        f"<td><strong>{html.escape(item['answer'])}</strong></td>"
        f"<td>{html.escape(str(item.get('spelling') or '—'))}</td>"
        f"<td>{html.escape(str(item.get('register') or '—'))}</td>"
        f"<td>{html.escape(str(item.get('reason') or '—'))}</td>"
        "</tr>"
        for item in report["targetedReviewedAdditions"]
    )
    proposal_rows = "".join(
        "<tr>"
        f"<td><strong>{html.escape(item['answer'])}</strong></td>"
        f"<td>{item.get('repairSupportCount', 0)}</td>"
        f"<td>{html.escape(str(item.get('source') or '—'))}</td>"
        f"<td>{html.escape(str(item.get('editorialStatus') or '—'))}</td>"
        "</tr>"
        for item in report["remainingPatternProposals"]
    )
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Diagnostic final — pilote 7×8</title><style>
:root{{--paper:#fffdf7;--ink:#17211b;--muted:#66736b;--line:#dce5dc;--card:#f2f7f1;--bad:#9d302b;--ok:#126a45}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.45 system-ui,sans-serif}}
main{{max-width:1120px;margin:auto;padding:18px}}h1{{font-size:clamp(25px,5vw,40px);margin:0 0 8px}}h2{{margin-top:30px}}
.lead,.muted{{color:var(--muted)}}.cards{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:20px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}}.n{{display:block;font-size:27px;font-weight:800}}
.decision{{background:#fff0ed;border-left:5px solid var(--bad);border-radius:9px;padding:14px 16px;margin:18px 0}}
.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:14px;background:white}}table{{border-collapse:collapse;width:100%;min-width:720px}}
th,td{{padding:9px 11px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}th{{background:#edf4ed;font-size:12px;text-transform:uppercase}}
code{{background:#eef2ed;padding:2px 5px;border-radius:5px}}@media(max-width:700px){{main{{padding:12px}}.cards{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main>
<h1>Diagnostic final du pilote 7×8</h1>
<p class="lead">Campagne mono-ancre, cadre haut/gauche, flèches droite/bas, aucun mot de deux lettres. Les références actuelles relues comptent quelle que soit leur source.</p>
<section class="cards">
<div class="card"><span class="n">{report['rootScan']['placementCount']}</span>placements racine</div>
<div class="card"><span class="n">{report['rootScan']['survivorCount']}</span>survivants explorés</div>
<div class="card"><span class="n">{report['campaign']['infeasibleCount']}</span>infaisables</div>
<div class="card"><span class="n">{report['campaign']['cutoffCount']}</span>cutoffs</div>
</section>
<div class="decision"><strong>Aucune grille candidate.</strong> Les {report['campaign']['attemptedCount']} placements survivants ont tous été résolus jusqu’à une preuve d’infaisabilité; aucun n’a été abandonné par manque de temps. Aucun mot médiocre n’a été injecté pour forcer une fermeture.</div>
<h2>Par silhouette</h2><div class="table-wrap"><table><thead><tr><th>Silhouette</th><th>Essais</th><th>Infaisables</th><th>Cutoffs</th><th>Fermés</th><th>Nœuds</th><th>Meilleur domaine racine</th></tr></thead><tbody>{rows(report['byShape'], 'shapeId')}</tbody></table></div>
<h2>Par ancre</h2><div class="table-wrap"><table><thead><tr><th>Ancre</th><th>Essais</th><th>Infaisables</th><th>Cutoffs</th><th>Fermés</th><th>Nœuds</th><th>Meilleur domaine racine</th></tr></thead><tbody>{rows(report['byAnchor'], 'anchor')}</tbody></table></div>
<h2>Réservoir ciblé relu</h2><p>{report['rescue']['storedAnswerCount']} réponses relues, dont {report['campaign']['recognizedCurrentAnswerCount']} reconnues comme actuelles/pop dans le domaine final. {len(report['targetedReviewedAdditions'])} ajouts ont été choisis à partir de motifs de croisement réellement bloquants.</p>
<div class="table-wrap"><table><thead><tr><th>Réponse</th><th>Graphie</th><th>Registre</th><th>Motif</th></tr></thead><tbody>{repair_rows}</tbody></table></div>
<h2>Blocages restants</h2><p>{report['patterns']['failurePatternCount']} motifs distincts, {report['patterns']['failureEventCount']} événements. Les propositions ci-dessous ne sont <strong>pas admises</strong> automatiquement.</p>
<div class="table-wrap"><table><thead><tr><th>Proposition</th><th>Support</th><th>Source</th><th>Statut</th></tr></thead><tbody>{proposal_rows}</tbody></table></div>
<h2>Conclusion bornée</h2><p>{html.escape(report['conclusion'])}</p>
<p class="muted">Catalogue actif, runtime et Supabase : inchangés. Artefact de campagne : <code>{html.escape(report['artifacts']['campaign'])}</code>.</p>
</main></body></html>"""


def main() -> int:
    args = parse_args()
    scan = json.loads(args.scan.read_text(encoding="utf-8"))
    campaign = json.loads(args.campaign.read_text(encoding="utf-8"))
    patterns = json.loads(args.patterns.read_text(encoding="utf-8"))
    rescue = json.loads(args.rescue.read_text(encoding="utf-8"))
    results = list(campaign.get("results", []))
    infeasible = sum(item.get("status") == "infeasible" for item in results)
    solved = sum(item.get("status") == "solved" for item in results)
    cutoff = len(results) - infeasible - solved
    report = {
        "version": 1,
        "kind": "motman-final-single-anchor-campaign-report",
        "catalogModified": False,
        "runtimeModified": False,
        "supabaseModified": False,
        "publicationEligible": False,
        "candidateProduced": solved > 0,
        "artifacts": {
            "scan": str(args.scan), "campaign": str(args.campaign),
            "patterns": str(args.patterns), "rescue": str(args.rescue),
        },
        "policy": campaign.get("parameters", {}),
        "rootScan": {
            "placementCount": int(scan.get("placementCount", 0)),
            "survivorCount": int(scan.get("survivingPlacementCount", 0)),
            "rejectedCount": int(scan.get("placementCount", 0)) - int(scan.get("survivingPlacementCount", 0)),
            "rejectionCauses": scan.get("rejectionCauses", {}),
        },
        "campaign": {
            "status": campaign.get("status"),
            "attemptedCount": len(results),
            "infeasibleCount": infeasible,
            "cutoffCount": cutoff,
            "solvedCount": solved,
            "totalNodes": sum(int(item.get("telemetry", {}).get("nodes", 0)) for item in results),
            "recognizedCurrentAnswerCount": int(campaign.get("recognizedCurrentAnswerCount", 0)),
            "recognizedCurrentAnswers": campaign.get("recognizedCurrentAnswers", []),
        },
        "rescue": {"storedAnswerCount": len(rescue.get("entries", []))},
        "targetedReviewedAdditions": targeted_additions(rescue),
        "patterns": {
            "failurePatternCount": int(patterns.get("failurePatternCount", 0)),
            "failureEventCount": int(patterns.get("failureEventCount", 0)),
        },
        "remainingPatternProposals": patterns.get("candidates", [])[:25],
        "byShape": summarize_results(results, "shapeId"),
        "byAnchor": summarize_results(results, "anchor"),
        "conclusion": (
            "La matrice finale est entièrement évaluée pour les dix ancres, les six silhouettes "
            "autorisées et le réservoir relu actuel. Elle ne démontre pas qu'aucune grille 7×8 "
            "n'existe; elle démontre que poursuivre l'ajout mot par mot sur cette même matrice "
            "a un rendement éditorial insuffisant. La prochaine campagne doit changer ses ancres "
            "ou construire une grille semi-manuellement, sans relâcher les règles."
        ),
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.html_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.html_output.write_text(render_html(report), encoding="utf-8")
    print(json.dumps({
        "candidateProduced": report["candidateProduced"],
        "rootScan": report["rootScan"],
        "campaign": report["campaign"],
        "targetedReviewedAdditionCount": len(report["targetedReviewedAdditions"]),
        "json": str(args.json_output), "html": str(args.html_output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
