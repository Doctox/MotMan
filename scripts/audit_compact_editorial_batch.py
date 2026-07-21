#!/usr/bin/env python3
"""Write a blocking editorial/freshness audit for a candidate grid batch."""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path

from editorial_fill_quality import audit_candidate_batch


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--reference", type=Path, action="append", default=[])
    parser.add_argument("--blacklist", type=Path, default=ROOT / "src/data/editorial.blacklist.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--html", type=Path)
    return parser.parse_args()


def render_html(report: dict) -> str:
    rows = []
    for item in report["gridReports"]:
        issues = []
        if item["blacklistedAnswers"]:
            issues.append("Blacklist : " + ", ".join(item["blacklistedAnswers"]))
        if item["cooldownAnswers"]:
            issues.append("Pause rotation : " + ", ".join(item["cooldownAnswers"]))
        if item["activeCatalogRepeats"]:
            issues.append("Déjà en jeu : " + ", ".join(item["activeCatalogRepeats"]))
        rows.append(
            "<tr><td>" + escape(item["gridId"]) + "</td><td>" +
            escape(" · ".join(issues) or "Aucun défaut individuel") + "</td></tr>"
        )
    repeats = ", ".join(
        f"{answer} ({len(grid_ids)}×)"
        for answer, grid_ids in report["internalRepeats"].items()
    ) or "Aucune"
    return f"""<!doctype html><html lang='fr'><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>MotMan — lot refusé</title><style>
body{{font:16px system-ui;margin:24px;background:#fff9f6;color:#261714}}
main{{max-width:980px;margin:auto}}h1{{color:#9b2418}}.banner{{padding:16px;border:2px solid #bd2d1d;background:#ffe3dc;border-radius:12px}}
table{{border-collapse:collapse;width:100%;margin-top:18px;background:white}}td,th{{border:1px solid #d8c6c1;padding:9px;text-align:left;vertical-align:top}}
code{{background:#f1ebe8;padding:2px 5px;border-radius:4px}}
</style><main><h1>Fournée du 20 juillet — refusée</h1>
<div class='banner'><b>Publication impossible.</b> {len(report['errors'])} contrôles bloquants.
Les 10 grilles restent hors du catalogue actif.</div>
<p><b>Répétitions internes :</b> {escape(repeats)}</p>
<table><thead><tr><th>Grille</th><th>Motifs de rejet automatiques</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></main></html>"""


def main() -> int:
    args = parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8"))
    blacklist = json.loads(args.blacklist.read_text(encoding="utf-8"))
    report = audit_candidate_batch(
        document.get("grids", []),
        blacklist_document=blacklist,
        reference_paths=args.reference,
    )
    report.update({
        "version": 1,
        "input": str(args.input),
        "references": [str(path) for path in args.reference],
        "publicationEligible": report["valid"],
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.html:
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(render_html(report), encoding="utf-8")
    print(json.dumps({
        "valid": report["valid"],
        "errors": len(report["errors"]),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
