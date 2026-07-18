"""Apply an incremental owner export from the complete JDM doubt page.

The export contains every review row, but only explicit accept/reject/doubt
choices are persisted. Pending rows remain untouched. Re-running this script
with a later export is idempotent and can update previous owner choices.
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
import os
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path

try:
    from .review_jeuxdemots_full_doubts import stable_id
    from .review_jeuxdemots_strict_candidates import approved_entry
except ImportError:  # direct execution from scripts/
    from review_jeuxdemots_full_doubts import stable_id
    from review_jeuxdemots_strict_candidates import approved_entry


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
REVIEW_SOURCE = ROOT / "output/quality/jeuxdemots-owner-full-doubt.json"
TRIAGE_SOURCE = DATA / "crossword.jeuxdemots.full-triage.json.gz"
APPROVED = DATA / "crossword.jeuxdemots.approved.json"
BLACKLIST = DATA / "editorial.blacklist.json"
OWNER_DECISIONS = DATA / "jeuxdemots.owner-full-decisions.json"
REPORT_JSON = ROOT / "output/quality/jeuxdemots-owner-full-decisions-applied.json"
REPORT_HTML = ROOT / "output/quality/jeuxdemots-owner-full-decisions-applied.html"
REVIEWED_AT = "2026-07-15"
ALLOWED_DECISIONS = {"accept", "reject", "doubt", "pending"}


def normalize(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.upper())
        if unicodedata.category(char) != "Mn" and char.isalpha()
    )


def atomic_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def pair_key(answer: str, clue: str) -> tuple[str, str]:
    return normalize(answer), normalize(clue)


def load_export(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_export(export: dict, source: dict) -> list[dict]:
    if export.get("version") != 2:
        raise ValueError("version de l'export complet JeuxDeMots non prise en charge")
    if export.get("sourceDigest") != source["sourceDigest"]:
        raise ValueError("le digest de l'export ne correspond pas à la page actuelle")
    decisions = export.get("decisions")
    expected = source["entries"]
    if not isinstance(decisions, list) or len(decisions) != len(expected):
        raise ValueError("l'export ne contient pas les 4 679 lignes de la page")
    if len({item.get("id") for item in decisions}) != len(decisions):
        raise ValueError("un identifiant de décision est dupliqué")
    by_id = {item["id"]: item for item in decisions}
    validated = []
    for wanted in expected:
        actual = by_id.get(wanted["id"])
        if actual is None:
            raise ValueError(f"décision absente : {wanted['id']}")
        for field, source_field in (
            ("answer", "answer"),
            ("clue", "clue"),
            ("category", "status"),
        ):
            if actual.get(field) != wanted[source_field]:
                raise ValueError(f"{wanted['id']} ne correspond plus à la page source")
        if actual.get("decision") not in ALLOWED_DECISIONS:
            raise ValueError(f"décision invalide pour {wanted['id']}")
        validated.append(actual)
    declared = export.get("counts", {})
    decided = sum(item["decision"] != "pending" for item in validated)
    if declared.get("total") != len(expected) or declared.get("decided") != decided:
        raise ValueError("les compteurs de l'export sont incohérents")
    return validated


def triage_by_id() -> dict[str, dict]:
    with gzip.open(TRIAGE_SOURCE, "rt", encoding="utf-8") as handle:
        triage = json.load(handle)
    return {
        stable_id(entry): entry
        for entry in triage["entries"]
        if entry.get("triageStatus") in {
            "selected-editorial-candidate",
            "doubt-alternative-candidate",
            "doubt-reciprocal",
            "doubt-cross-source-nonreciprocal",
        }
    }


def reviewed_entry(entry: dict, decision: dict, digest: str) -> dict:
    return {
        **approved_entry(entry),
        "manualReview": "owner-approved-full-doubt-review",
        "reviewedBy": "motman-owner",
        "reviewedAt": REVIEWED_AT,
        "editorialBatch": "jdm-owner-full-review-20260715",
        "ownerFullDecisionId": decision["id"],
        "ownerFullReviewDigest": digest,
    }


def load_previous(digest: str) -> dict[str, str]:
    if not OWNER_DECISIONS.exists():
        return {}
    document = json.loads(OWNER_DECISIONS.read_text(encoding="utf-8"))
    if document.get("sourceDigest") != digest:
        raise ValueError("un autre lot de décisions propriétaire est déjà enregistré")
    return {item["id"]: item["decision"] for item in document["decisions"]}


def apply(export_path: Path) -> dict:
    source = json.loads(REVIEW_SOURCE.read_text(encoding="utf-8"))
    export = load_export(export_path)
    validated = validate_export(export, source)
    digest = source["sourceDigest"]
    previous = load_previous(digest)
    explicit = [item for item in validated if item["decision"] != "pending"]
    explicit_by_id = {item["id"]: item for item in explicit}
    regressed = sorted(set(previous) - set(explicit_by_id))
    if regressed:
        raise ValueError(
            "l'export ferait disparaître des décisions déjà appliquées; "
            "reprendre avec le même stockage navigateur"
        )

    triage = triage_by_id()
    missing = sorted(set(item["id"] for item in explicit) - set(triage))
    if missing:
        raise ValueError(f"décisions absentes du registre de triage : {missing[:3]}")

    accepted = [item for item in explicit if item["decision"] == "accept"]
    rejected = [item for item in explicit if item["decision"] == "reject"]
    doubts = [item for item in explicit if item["decision"] == "doubt"]

    approved_document = json.loads(APPROVED.read_text(encoding="utf-8"))
    baseline_approved = [
        entry for entry in approved_document["entries"]
        if entry.get("ownerFullReviewDigest") != digest
    ]
    approved_by_pair = {
        pair_key(entry["answer"], entry["clue"]): entry
        for entry in baseline_approved
    }

    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    baseline_rejections = [
        item for item in blacklist.get("rejectedPairs", [])
        if item.get("ownerFullReviewDigest") != digest
    ]
    baseline_rejection_keys = {
        pair_key(item["answer"], item["clue"]) for item in baseline_rejections
    }

    conflicts = [
        item for item in accepted
        if pair_key(item["answer"], item["clue"]) in baseline_rejection_keys
    ]
    if conflicts:
        raise ValueError(
            f"{len(conflicts)} validation(s) contredisent une blacklist antérieure"
        )

    for decision in accepted:
        entry = reviewed_entry(triage[decision["id"]], decision, digest)
        approved_by_pair[pair_key(entry["answer"], entry["clue"])] = entry

    # The owner's current decision supersedes earlier editorial batches. A
    # reject or doubt must therefore remove a formerly approved version of the
    # exact same pair instead of leaving contradictory approved/blacklisted
    # history in the production-reviewed corpus.
    for decision in [*rejected, *doubts]:
        approved_by_pair.pop(pair_key(decision["answer"], decision["clue"]), None)

    owner_rejections = [
        {
            "answer": item["answer"],
            "clue": item["clue"],
            "reason": (
                "refus explicite du propriétaire "
                f"({item['id']}, revue JeuxDeMots complète 2026-07-15)"
            ),
            "ownerFullDecisionId": item["id"],
            "ownerFullReviewDigest": digest,
        }
        for item in rejected
    ]
    blacklist["rejectedPairs"] = [*baseline_rejections, *owner_rejections]
    approved_document.update({
        "version": max(4, int(approved_document.get("version", 1))),
        "publicationPolicy": (
            "Couples relus explicitement; refus blacklistés au niveau du couple; "
            "doutes et lignes en attente exclus."
        ),
        "entries": sorted(
            approved_by_pair.values(),
            key=lambda entry: (entry["answer"], entry["clue"].casefold()),
        ),
    })

    changed = sum(
        previous.get(item["id"]) not in {None, item["decision"]}
        for item in explicit
    )
    newly_decided = sum(item["id"] not in previous for item in explicit)
    counts = Counter(item["decision"] for item in explicit)
    owner_document = {
        "version": 1,
        "kind": "jeuxdemots-owner-full-review-decisions",
        "sourceDigest": digest,
        "sourceCount": len(validated),
        "reviewedAt": REVIEWED_AT,
        "reviewedBy": "motman-owner",
        "counts": {
            "decided": len(explicit),
            "accept": counts["accept"],
            "reject": counts["reject"],
            "doubt": counts["doubt"],
            "pending": len(validated) - len(explicit),
        },
        "decisions": explicit,
    }
    report = {
        "valid": True,
        "sourceDigest": digest,
        "totalRows": len(validated),
        "decided": len(explicit),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "doubt": len(doubts),
        "pending": len(validated) - len(explicit),
        "newlyDecided": newly_decided,
        "changedDecisions": changed,
        "approvedTotal": len(approved_document["entries"]),
        "blacklistedPairsTotal": len(blacklist["rejectedPairs"]),
    }

    atomic_json(APPROVED, approved_document)
    atomic_json(BLACKLIST, blacklist)
    atomic_json(OWNER_DECISIONS, owner_document)
    atomic_json(REPORT_JSON, report)
    REPORT_HTML.parent.mkdir(parents=True, exist_ok=True)
    REPORT_HTML.write_text(render_report(report, accepted, rejected, doubts), encoding="utf-8")
    return report


def render_report(
    report: dict, accepted: list[dict], rejected: list[dict], doubts: list[dict]
) -> str:
    def rows(entries: list[dict]) -> str:
        return "".join(
            f"<tr><td>{html.escape(item['answer'])}</td>"
            f"<td>{html.escape(item['clue'])}</td><td>{html.escape(item['id'])}</td></tr>"
            for item in entries
        )

    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Décisions JDM complètes appliquées</title><style>
body{{font:15px system-ui;max-width:1100px;margin:30px auto;padding:0 18px;color:#17251f}}
.ok{{background:#e7f7ed;border:1px solid #83c59b;padding:14px}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #bdc9c3;padding:7px;text-align:left}}th{{background:#eef5f1}}
</style></head><body><h1>Revue propriétaire JeuxDeMots</h1>
<p class="ok"><b>{report['decided']}</b> décisions appliquées : <b>{report['accepted']}</b> validées, <b>{report['rejected']}</b> refusées et <b>{report['doubt']}</b> conservées en doute. Il reste <b>{report['pending']}</b> lignes.</p>
<h2>Validés</h2><table><tr><th>Réponse</th><th>Indice</th><th>ID</th></tr>{rows(accepted)}</table>
<h2>Refusés</h2><table><tr><th>Réponse</th><th>Indice</th><th>ID</th></tr>{rows(rejected)}</table>
<h2>Doutes</h2><table><tr><th>Réponse</th><th>Indice</th><th>ID</th></tr>{rows(doubts)}</table>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("decisions", type=Path)
    args = parser.parse_args()
    print(json.dumps(apply(args.decisions), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
