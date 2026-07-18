"""Apply the owner's one-click JeuxDeMots review export deterministically.

Accepted pairs are promoted to the reviewed corpus. Rejected pairs are kept
as directed pair-level blacklist decisions; their answer remains available
with another clue. Pending or doubtful rows are never promoted.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path

from review_jeuxdemots_strict_candidates import (
    DOUBT_PAIRS,
    EXPECTED_DIGEST,
    approved_entry,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
DOUBT_SOURCE = ROOT / "output/quality/jeuxdemots-owner-doubt.json"
APPROVED = DATA / "crossword.jeuxdemots.approved.json"
BLACKLIST = DATA / "editorial.blacklist.json"
DECISIONS = DATA / "jeuxdemots.editorial-decisions.json"
OWNER_DECISIONS = DATA / "jeuxdemots.owner-decisions.json"
REPORT_JSON = ROOT / "output/quality/jeuxdemots-owner-decisions-applied.json"
REPORT_HTML = ROOT / "output/quality/jeuxdemots-owner-decisions-applied.html"
REVIEWED_AT = "2026-07-15"


def normalized(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.upper())
        if unicodedata.category(char) != "Mn" and char.isalpha()
    )


def atomic_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def expected_rows(source: dict) -> list[dict]:
    rows = []
    for prefix, category, key in (
        ("S", "strict-doubt", "strictReviewDoubts"),
        ("D", "borderline-doubt", "borderlineDoubts"),
    ):
        for index, entry in enumerate(source[key], start=1):
            rows.append({
                "id": f"{prefix}-{index:03d}",
                "answer": entry["answer"],
                "clue": entry["clue"],
                "category": category,
                "entry": entry,
            })
    return rows


def validate_export(export: dict, expected: list[dict]) -> list[dict]:
    if export.get("version") != 1:
        raise ValueError("version de décision propriétaire non prise en charge")
    if export.get("sourceDigest") != EXPECTED_DIGEST:
        raise ValueError("le digest ne correspond pas à la feuille remise au propriétaire")
    decisions = export.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != len(expected):
        raise ValueError("la feuille de décisions est incomplète")
    if len({item.get("id") for item in decisions}) != len(decisions):
        raise ValueError("un identifiant de décision est dupliqué")
    by_id = {item["id"]: item for item in decisions}
    validated = []
    for wanted in expected:
        actual = by_id.get(wanted["id"])
        if not actual:
            raise ValueError(f"décision absente : {wanted['id']}")
        for field in ("answer", "clue", "category"):
            if actual.get(field) != wanted[field]:
                raise ValueError(f"{wanted['id']} ne correspond plus à la feuille source")
        if actual.get("decision") not in {"accept", "reject"}:
            raise ValueError(f"{wanted['id']} doit être validé ou refusé")
        validated.append({**actual, "entry": wanted["entry"]})
    return validated


def owner_approved_entry(decision: dict) -> dict:
    return {
        **approved_entry(decision["entry"]),
        "manualReview": "owner-approved",
        "reviewedBy": "motman-owner",
        "ownerDecisionId": decision["id"],
        "ownerDecisionCategory": decision["category"],
    }


def render_report(report: dict) -> str:
    rejected = "".join(
        f"<tr><td>{html.escape(item['answer'])}</td><td>{html.escape(item['clue'])}</td></tr>"
        for item in report["rejectedPairs"]
    )
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Décisions JeuxDeMots appliquées</title><style>
body{{font:16px system-ui;max-width:900px;margin:35px auto;padding:0 18px;color:#17251f}}
.ok{{padding:14px;background:#e7f7ed;border:1px solid #83c59b}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #bdc9c3;padding:8px;text-align:left}}th{{background:#eef5f1}}
</style></head><body><h1>Décisions JeuxDeMots appliquées</h1>
<p class="ok"><b>{report['ownerAccepted']} couples validés</b> ajoutés au corpus relu et <b>{report['ownerRejected']} couples refusés</b> ajoutés à la blacklist. Aucun mot entier n’a été blacklisté par cette revue.</p>
<p>Corpus JeuxDeMots relu : {report['approvedTotal']} couples. Toutes les {report['reviewedRows']} lignes de la feuille ont une décision.</p>
<h2>Refus enregistrés</h2><table><tr><th>Réponse</th><th>Indice refusé</th></tr>{rejected}</table>
</body></html>"""


def apply(export_path: Path) -> dict:
    export = json.loads(export_path.read_text(encoding="utf-8"))
    doubt_source = json.loads(DOUBT_SOURCE.read_text(encoding="utf-8"))
    validated = validate_export(export, expected_rows(doubt_source))

    # Reuse only the already pinned editorial baseline. Recomputing the strict
    # set after blacklist changes could expose new first-ranked relations and
    # must never promote them without a new review cycle.
    current_approved = json.loads(APPROVED.read_text(encoding="utf-8"))
    baseline = [
        entry for entry in current_approved["entries"]
        if not entry.get("ownerDecisionId")
    ]
    accepted_decisions = [item for item in validated if item["decision"] == "accept"]
    rejected_decisions = [item for item in validated if item["decision"] == "reject"]
    promoted = [owner_approved_entry(item) for item in accepted_decisions]
    approved_by_pair = {
        (entry["answer"], normalized(entry["clue"])): entry
        for entry in [*baseline, *promoted]
    }
    approved_entries = sorted(
        approved_by_pair.values(), key=lambda entry: (entry["answer"], entry["clue"].casefold())
    )

    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    rejected_pairs = blacklist.setdefault("rejectedPairs", [])
    existing_rejections = {
        (normalized(item["answer"]), normalized(item["clue"]))
        for item in rejected_pairs
    }
    newly_blacklisted = 0
    for decision in rejected_decisions:
        key = (normalized(decision["answer"]), normalized(decision["clue"]))
        if key in existing_rejections:
            continue
        rejected_pairs.append({
            "answer": decision["answer"],
            "clue": decision["clue"],
            "reason": f"refus explicite du propriétaire ({decision['id']}, revue JeuxDeMots 2026-07-15)",
        })
        existing_rejections.add(key)
        newly_blacklisted += 1

    counts = Counter(item["decision"] for item in validated)
    category_counts = {
        category: dict(Counter(
            item["decision"] for item in validated if item["category"] == category
        ))
        for category in ("strict-doubt", "borderline-doubt")
    }
    owner_document = {
        "version": 1,
        "sourceDigest": export["sourceDigest"],
        "reviewedAt": REVIEWED_AT,
        "reviewedBy": "motman-owner",
        "counts": {"total": len(validated), **dict(counts)},
        "countsByCategory": category_counts,
        "decisions": [{key: item[key] for key in ("id", "answer", "clue", "category", "decision")} for item in validated],
    }
    approved_document = {
        "version": 2,
        "kind": "jeuxdemots-human-reviewed-crossword-pairs",
        "publicationPolicy": "Couples relus; les refus sont blacklistés au niveau du couple et les indécis restent exclus.",
        "reviewedCandidateDigest": EXPECTED_DIGEST,
        "entries": approved_entries,
    }
    editorial_document = {
        "version": 2,
        "reviewedAt": REVIEWED_AT,
        "sourceCandidateDigest": EXPECTED_DIGEST,
        "sourceCandidateCount": len(baseline) + len(DOUBT_PAIRS),
        "baselineAcceptedCount": len(baseline),
        "ownerReviewedCount": len(validated),
        "ownerAcceptedCount": counts["accept"],
        "ownerRejectedCount": counts["reject"],
        "acceptedCount": len(approved_entries),
        "doubtCount": 0,
        "acceptedPairs": [[entry["answer"], entry["clue"]] for entry in approved_entries],
        "rejectedPairs": [[item["answer"], item["clue"]] for item in rejected_decisions],
        "policy": "Seuls les ✓ du propriétaire sont promus; chaque ✕ est une blacklist de couple.",
    }
    report = {
        "valid": True,
        "sourceDigest": EXPECTED_DIGEST,
        "reviewedRows": len(validated),
        "ownerAccepted": counts["accept"],
        "ownerRejected": counts["reject"],
        "approvedBaseline": len(baseline),
        "approvedTotal": len(approved_entries),
        "newlyBlacklisted": newly_blacklisted,
        "countsByCategory": category_counts,
        "rejectedPairs": [
            {"answer": item["answer"], "clue": item["clue"], "id": item["id"]}
            for item in rejected_decisions
        ],
    }

    atomic_json(OWNER_DECISIONS, owner_document)
    atomic_json(APPROVED, approved_document)
    atomic_json(DECISIONS, editorial_document)
    atomic_json(BLACKLIST, blacklist)
    atomic_json(REPORT_JSON, report)
    REPORT_HTML.write_text(render_report(report), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("decisions", type=Path)
    args = parser.parse_args()
    report = apply(args.decisions)
    print(json.dumps({key: value for key, value in report.items() if key != "rejectedPairs"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
