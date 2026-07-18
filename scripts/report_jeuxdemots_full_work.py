"""Build the owner-facing progress report for the exhaustive JDM corpus work."""
from __future__ import annotations

import gzip
import html
import json
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
OUTPUT_JSON = ROOT / "output/quality/jeuxdemots-full-work-report.json"
OUTPUT_HTML = ROOT / "output/quality/jeuxdemots-full-work-report.html"
BASELINE_GENERATOR_ANSWERS = 8_208
DECISION_FILES = (
    "jeuxdemots.owner-decisions.json",
    "jeuxdemots.editorial-batch-20260715.json",
    "jeuxdemots.editorial-batch-20260715-b.json",
    "jeuxdemots.editorial-wave-c-decisions.json",
    "jeuxdemots.owner-full-decisions.json",
)


def normalize(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value.upper())
        if unicodedata.category(char) != "Mn" and char.isalpha()
    )


def main() -> int:
    with gzip.open(DATA / "crossword.central.json.gz", "rt", encoding="utf-8") as handle:
        central = json.load(handle)
    with gzip.open(DATA / "crossword.jeuxdemots.full-triage.json.gz", "rt", encoding="utf-8") as handle:
        triage = json.load(handle)
    approved_document = json.loads(
        (DATA / "crossword.jeuxdemots.approved.json").read_text(encoding="utf-8")
    )
    approved = {
        (entry["answer"], normalize(entry["clue"])) for entry in approved_document["entries"]
    }
    rejected = set()
    doubts = set()
    for filename in DECISION_FILES:
        document = json.loads((DATA / filename).read_text(encoding="utf-8"))
        for item in document["decisions"]:
            key = item["answer"], normalize(item["clue"])
            if item["decision"] == "reject":
                rejected.add(key)
            elif item["decision"] == "doubt":
                doubts.add(key)
    doubts -= approved | rejected
    generator_answers = central["metrics"]["generatorEligibleDistinctAnswers"]
    report = {
        "valid": triage["metrics"]["unclassifiedRelations"] == 0,
        "reservoirRelations": triage["metrics"]["inputRelations"],
        "classifiedRelations": triage["metrics"]["classifiedRelations"],
        "unclassifiedRelations": triage["metrics"]["unclassifiedRelations"],
        "editoriallyReviewedDistinctPairs": len(approved | rejected | doubts),
        "approvedPairs": len(approved),
        "rejectedPairsFromThisReview": len(rejected),
        "remainingHumanDoubts": len(doubts),
        "generatorAnswersBeforeJdm": BASELINE_GENERATOR_ANSWERS,
        "generatorAnswersNow": generator_answers,
        "netNewGeneratorAnswers": generator_answers - BASELINE_GENERATOR_ANSWERS,
        "triageStatusCounts": triage["metrics"]["statusCounts"],
        "smoke": {
            "easy": {"indexedWords": 2592, "attempts": 4, "accepted": 0, "rejections": {"fill:infeasible": 4}},
            "normal": {"indexedWords": 5841, "attempts": 3, "accepted": 0, "rejections": {"fill:infeasible": 2, "fill:timeout": 1}},
            "hard": {"indexedWords": 5841, "attempts": 3, "accepted": 0, "rejections": {"fill:infeasible": 2, "fill:timeout": 1}},
        },
        "nextBottleneck": "Le corpus est chargé; le remplisseur/topologie ne trouve pas de solution dans un petit budget. Ne pas prolonger aveuglément.",
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    statuses = "".join(
        f"<tr><td>{html.escape(status)}</td><td>{count:,}</td></tr>"
        for status, count in report["triageStatusCounts"].items()
    )
    smoke = "".join(
        f"<tr><td>{level}</td><td>{data['indexedWords']:,}</td><td>{data['attempts']}</td><td>{data['accepted']}</td><td>{html.escape(str(data['rejections']))}</td></tr>"
        for level, data in report["smoke"].items()
    )
    OUTPUT_HTML.write_text(f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Travail complet JeuxDeMots</title><style>
body{{font:16px system-ui;max-width:1000px;margin:35px auto;padding:0 18px;color:#17251f}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}}.card{{padding:14px;border:1px solid #aec1b7;background:#f1f8f4}}table{{border-collapse:collapse;width:100%;margin:20px 0}}td,th{{border:1px solid #bdc9c3;padding:8px;text-align:left}}th{{background:#eef5f1}}.warn{{background:#fff3cd;border:1px solid #d8b84e;padding:13px}}</style></head><body>
<h1>JeuxDeMots — travail exhaustif du corpus</h1><div class="cards">
<div class="card"><b>{report['classifiedRelations']:,} / {report['reservoirRelations']:,}</b><br>relations classées</div>
<div class="card"><b>{report['editoriallyReviewedDistinctPairs']:,}</b><br>couples réellement relus</div>
<div class="card"><b>{report['approvedPairs']:,}</b><br>couples validés</div>
<div class="card"><b>{report['rejectedPairsFromThisReview']:,}</b><br>refus éditoriaux</div>
<div class="card"><b>{report['remainingHumanDoubts']}</b><br>doutes relus restants</div>
<div class="card"><b>+{report['netNewGeneratorAnswers']:,}</b><br>réponses générables</div></div>
<h2>Disposition de tout le réservoir</h2><table><tr><th>Statut</th><th>Relations</th></tr>{statuses}</table>
<h2>Smoke du générateur</h2><table><tr><th>Niveau</th><th>Mots indexés</th><th>Essais</th><th>Acceptés</th><th>Rejets</th></tr>{smoke}</table>
<p class="warn"><b>Prochain goulot :</b> {html.escape(report['nextBottleneck'])}</p>
</body></html>""", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
