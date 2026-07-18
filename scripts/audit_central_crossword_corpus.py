"""Produce a concise, deterministic audit of the central crossword corpus."""
from __future__ import annotations

import argparse
import gzip
import html
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"


def load_json(path: Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(corpus: dict, catalog: dict, blacklist: dict) -> dict:
    entries = corpus["entries"]
    answers = {entry["answer"] for entry in entries}
    generator_entries = [entry for entry in entries if entry.get("canonicalForGenerator")]
    jdm_entries = [entry for entry in entries if entry.get("sourceId") == "jeuxdemots-r_syn"]
    dbnary_entries = [
        entry for entry in entries
        if "dbnary" in str(entry.get("sourceId", "")).lower()
    ]
    rejected_entries = [
        entry for entry in entries if entry.get("corpusStage") == "editorial-rejected"
    ]
    approved_jdm_entries = [
        entry for entry in generator_entries
        if entry.get("sourceId") == "jeuxdemots-r_syn-sanitized"
    ]
    pairs_per_answer = Counter(entry["answer"] for entry in entries)
    source_counts = Counter(entry.get("sourceId", "unknown") for entry in entries)
    quarantined = set(blacklist.get("quarantinedGridIds", []))
    active_grids = [grid for grid in catalog["grids"] if grid["id"] not in quarantined]
    return {
        "valid": len(answers) >= 15_000 and not dbnary_entries and len(generator_entries) >= 8_000,
        "centralCorpus": {
            "distinctAnswers": len(answers),
            "distinctPairs": len(entries),
            "answersWithSeveralPairs": sum(count > 1 for count in pairs_per_answer.values()),
            "generatorReviewedCanonicalPairs": len(generator_entries),
            "humanReviewedJeuxDeMotsPairs": len(approved_jdm_entries),
            "blacklistedPairsKeptAsHistory": len(rejected_entries),
            "generatorPairsDisabledByBlacklist": corpus.get("metrics", {}).get(
                "generatorPairsDisabledByBlacklist", 0
            ),
            "jeuxDeMotsDistinctAnswers": len({entry["answer"] for entry in jdm_entries}),
            "jeuxDeMotsReviewPairs": len(jdm_entries),
            "dbnaryPairs": len(dbnary_entries),
            "byLength": dict(sorted(Counter(map(len, answers)).items())),
            "largestSources": source_counts.most_common(12),
        },
        "catalog": {
            "storedGrids": len(catalog["grids"]),
            "activeGrids": len(active_grids),
            "quarantinedStoredGrids": sorted(
                grid["id"] for grid in catalog["grids"] if grid["id"] in quarantined
            ),
        },
        "policy": {
            "generatorInput": "crossword.central.json.gz",
            "jeuxDeMots": "centralisé, mais revue humaine obligatoire avant promotion",
            "dbnary": "exclu du corpus central et du générateur",
        },
    }


def render_html(report: dict) -> str:
    central = report["centralCorpus"]
    catalog = report["catalog"]
    rows = [
        ("Réponses distinctes centrales", central["distinctAnswers"]),
        ("Couples distincts conservés", central["distinctPairs"]),
        ("Réponses avec plusieurs pistes", central["answersWithSeveralPairs"]),
        ("Couples relus utilisables par le générateur", central["generatorReviewedCanonicalPairs"]),
        ("Nouveaux couples JeuxDeMots relus humainement", central["humanReviewedJeuxDeMotsPairs"]),
        ("Couples bloqués par la blacklist", central["generatorPairsDisabledByBlacklist"]),
        ("Réponses JeuxDeMots centralisées", central["jeuxDeMotsDistinctAnswers"]),
        ("Pistes JeuxDeMots à relire", central["jeuxDeMotsReviewPairs"]),
        ("Couples DBnary dans le central", central["dbnaryPairs"]),
        ("Grilles stockées", catalog["storedGrids"]),
        ("Grilles actuellement jouables", catalog["activeGrids"]),
    ]
    table = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{value:,}</td></tr>".replace(",", " ")
        for label, value in rows
    )
    quarantined = ", ".join(catalog["quarantinedStoredGrids"]) or "Aucune"
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>Audit corpus central MotMan</title>
<style>body{{font:16px system-ui;max-width:900px;margin:40px auto;padding:0 20px;color:#17251f}}h1{{margin-bottom:8px}}.ok{{background:#e7f7ed;border:1px solid #8ccaa2;padding:14px}}table{{border-collapse:collapse;width:100%;margin:24px 0}}th,td{{border:1px solid #bac7c0;padding:10px;text-align:left}}th{{width:70%;background:#f3f7f5}}code{{background:#eef2f0;padding:2px 5px}}</style></head>
<body><h1>Corpus central : JeuxDeMots, sans DBnary</h1>
<p class="ok"><strong>Contrôle {'réussi' if report['valid'] else 'échoué'}.</strong> Le générateur lit <code>crossword.central.json.gz</code>. Les relations JeuxDeMots sont centralisées mais restent non publiables tant qu’un humain ne les a pas promues.</p>
<table>{table}</table>
<p><strong>Grilles encore en quarantaine :</strong> {html.escape(quarantined)}</p>
<p><strong>Règle :</strong> corpus central ≠ publication automatique. Une relation brute n’est jamais affichée comme définition.</p>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DATA / "crossword.central.json.gz")
    parser.add_argument("--json", type=Path, default=ROOT / "output/quality/central-corpus-jdm-audit.json")
    parser.add_argument("--html", type=Path, default=ROOT / "output/quality/central-corpus-jdm-audit.html")
    args = parser.parse_args()
    report = build_report(
        load_json(args.corpus),
        load_json(DATA / "grid.catalog.json"),
        load_json(DATA / "editorial.blacklist.json"),
    )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.html.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.html.write_text(render_html(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
