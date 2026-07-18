"""Apply the first exhaustive-triage editorial pass over 421 JDM candidates."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import tempfile
import unicodedata
from pathlib import Path

from review_jeuxdemots_strict_candidates import approved_entry


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
SOURCE = DATA / "crossword.jeuxdemots.editorial-candidates.json"
APPROVED = DATA / "crossword.jeuxdemots.approved.json"
BLACKLIST = DATA / "editorial.blacklist.json"
DECISIONS = DATA / "jeuxdemots.editorial-batch-20260715.json"
REPORT = ROOT / "output/quality/jeuxdemots-editorial-batch-20260715.html"
EXPECTED_COUNT = 421
EXPECTED_DIGEST = "2a10d81d2c7985c0b062c090d440e616a7226d28a4d05d49c4b6083a7e6bded3"

# Eleven relations remain genuinely debatable and are neither promoted nor
# blacklisted. Every other row was explicitly read and decided in this pass.
DOUBT_IDS = {33, 83, 86, 95, 123, 173, 192, 228, 285, 308, 349}
REJECT_IDS = {
    2, 4, 7, 12, 18, 20, 22, 25, 27, 29, 30, 34, 36, 46, 47, 54,
    60, 61, 62, 64, 70, 72, 76, 77, 78, 85, 93, 96, 97, 106, 109,
    112, 113, 114, 117, 120, 121, 125, 131, 140, 142, 144, 148, 150,
    152, 154, 155, 159, 160, 163, 165, 166, 167, 169, 171, 174, 180,
    181, 191, 193, 199, 200, 202, 204, 205, 206, 209, 212, 217, 220,
    221, 223, 224, 233, 239, 241, 249, 259, 260, 261, 268, 278, 280,
    283, 286, 288, 295, 296, 297, 299, 302, 303, 304, 306, 307, 310,
    319, 320, 324, 328, 342, 346, 348, 360, 361, 363, 364, 365, 367,
    374, 379, 383, 392, 398, 399, 402, 412,
}
ACCENT_OR_FORM_IDS = {47, 60, 61, 70, 97, 167, 241}
REGISTER_OR_RARITY_IDS = {7, 152, 296}


def normalize(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value.upper())
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


def digest(entries: list[dict]) -> str:
    payload = [(entry["answer"], entry["clue"]) for entry in entries]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def rejection_reason(index: int) -> str:
    if index == 2:
        return "réponse MOT volontairement écartée pour éviter sa surutilisation"
    if index in ACCENT_OR_FORM_IDS:
        return "forme accentuée ou grammaticale ambiguë une fois affichée sans accents"
    if index in REGISTER_OR_RARITY_IDS:
        return "registre ou vocabulaire inadapté à une définition courte et naturelle"
    return "relation contextuelle, trop large ou insuffisamment univoque après relecture"


def reviewed(entry: dict, index: int) -> dict:
    return {
        **approved_entry(entry),
        "manualReview": "editorial-exhaustive-triage-approved",
        "reviewedBy": "motman-editorial",
        "editorialBatch": "jdm-exhaustive-20260715-a",
        "editorialDecisionId": f"JDM-A-{index:03d}",
    }


def apply() -> dict:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    entries = source["entries"]
    if len(entries) != EXPECTED_COUNT or digest(entries) != EXPECTED_DIGEST:
        raise ValueError("le lot de 421 candidats a changé; la relecture n'est plus applicable")
    if DOUBT_IDS & REJECT_IDS or max(DOUBT_IDS | REJECT_IDS) > len(entries):
        raise ValueError("les décisions éditoriales sont incohérentes")

    accepted_indexes = set(range(1, len(entries) + 1)) - DOUBT_IDS - REJECT_IDS
    accepted = [(index, entries[index - 1]) for index in sorted(accepted_indexes)]
    rejected = [(index, entries[index - 1]) for index in sorted(REJECT_IDS)]
    doubts = [(index, entries[index - 1]) for index in sorted(DOUBT_IDS)]

    approved_document = json.loads(APPROVED.read_text(encoding="utf-8"))
    approved_by_pair = {
        (entry["answer"], normalize(entry["clue"])): entry
        for entry in approved_document["entries"]
    }
    for index, entry in accepted:
        approved_by_pair[(entry["answer"], normalize(entry["clue"]))] = reviewed(entry, index)
    approved_document.update({
        "version": 3,
        "publicationPolicy": "Couples relus individuellement; refus blacklistés au niveau du couple; doutes exclus.",
        "entries": sorted(
            approved_by_pair.values(),
            key=lambda entry: (entry["answer"], entry["clue"].casefold()),
        ),
    })

    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    blacklist_pairs = blacklist.setdefault("rejectedPairs", [])
    existing = {
        (normalize(item["answer"]), normalize(item["clue"]))
        for item in blacklist_pairs
    }
    newly_blacklisted = 0
    for index, entry in rejected:
        key = (normalize(entry["answer"]), normalize(entry["clue"]))
        if key in existing:
            continue
        blacklist_pairs.append({
            "answer": entry["answer"],
            "clue": entry["clue"],
            "reason": f"{rejection_reason(index)} (JDM-A-{index:03d})",
        })
        existing.add(key)
        newly_blacklisted += 1

    decisions = {
        "version": 1,
        "batch": "jdm-exhaustive-20260715-a",
        "sourceDigest": EXPECTED_DIGEST,
        "sourceCount": len(entries),
        "reviewedAt": "2026-07-15",
        "reviewedBy": "motman-editorial",
        "counts": {
            "accepted": len(accepted), "rejected": len(rejected), "doubt": len(doubts)
        },
        "decisions": [
            {
                "id": f"JDM-A-{index:03d}",
                "answer": entry["answer"],
                "clue": entry["clue"],
                "decision": "accept" if index in accepted_indexes else "reject" if index in REJECT_IDS else "doubt",
                "reason": "couple direct et devinable" if index in accepted_indexes else rejection_reason(index) if index in REJECT_IDS else "nuance sémantique à conserver en doute",
            }
            for index, entry in enumerate(entries, start=1)
        ],
    }
    atomic_json(APPROVED, approved_document)
    atomic_json(BLACKLIST, blacklist)
    atomic_json(DECISIONS, decisions)

    report = {
        "accepted": len(accepted),
        "rejected": len(rejected),
        "doubt": len(doubts),
        "newlyBlacklisted": newly_blacklisted,
        "approvedTotal": len(approved_document["entries"]),
    }
    rows = "".join(
        f"<tr><td>{html.escape(item['id'])}</td><td>{html.escape(item['answer'])}</td><td>{html.escape(item['clue'])}</td><td>{html.escape(item['decision'])}</td><td>{html.escape(item['reason'])}</td></tr>"
        for item in decisions["decisions"]
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Relecture JDM A</title><style>body{{font:15px system-ui;max-width:1100px;margin:30px auto;padding:0 18px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #bbb;padding:7px;text-align:left}}th{{background:#eef5f1;position:sticky;top:0}}</style></head><body><h1>Relecture éditoriale JeuxDeMots — lot A</h1><p><b>{len(accepted)}</b> validés · <b>{len(rejected)}</b> refusés · <b>{len(doubts)}</b> doutes.</p><table><tr><th>ID</th><th>Réponse</th><th>Indice</th><th>Décision</th><th>Motif</th></tr>{rows}</table></body></html>""",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print(json.dumps(apply(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
