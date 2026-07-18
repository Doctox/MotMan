"""Apply the second editorial pass exposed after JDM batch A."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from apply_jeuxdemots_editorial_batch import atomic_json, normalize
from review_jeuxdemots_strict_candidates import approved_entry


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
SOURCE = DATA / "crossword.jeuxdemots.editorial-candidates.json"
APPROVED = DATA / "crossword.jeuxdemots.approved.json"
BLACKLIST = DATA / "editorial.blacklist.json"
DECISIONS = DATA / "jeuxdemots.editorial-batch-20260715-b.json"
EXPECTED_COUNT = 36
EXPECTED_DIGEST = "53567830b22eb7ff648a1ed987a7972c389cf9d3c9230234968e2807e646e115"
ACCEPT_IDS = {1, 3, 4, 9, 10, 11, 12, 15, 16, 17, 21, 22, 27, 29, 32, 33, 34, 35, 36}
REJECT_IDS = {8, 14, 18, 19, 26, 30}
DOUBT_IDS = set(range(1, EXPECTED_COUNT + 1)) - ACCEPT_IDS - REJECT_IDS


def digest(entries: list[dict]) -> str:
    payload = [(entry["answer"], entry["clue"]) for entry in entries]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    entries = json.loads(SOURCE.read_text(encoding="utf-8"))["entries"]
    if len(entries) != EXPECTED_COUNT or digest(entries) != EXPECTED_DIGEST:
        raise ValueError("le lot éditorial B a changé")
    approved = json.loads(APPROVED.read_text(encoding="utf-8"))
    approved_by_pair = {
        (entry["answer"], normalize(entry["clue"])): entry
        for entry in approved["entries"]
    }
    for index in sorted(ACCEPT_IDS):
        entry = entries[index - 1]
        approved_by_pair[(entry["answer"], normalize(entry["clue"]))] = {
            **approved_entry(entry),
            "manualReview": "editorial-exhaustive-triage-approved",
            "reviewedBy": "motman-editorial",
            "editorialBatch": "jdm-exhaustive-20260715-b",
            "editorialDecisionId": f"JDM-B-{index:02d}",
        }
    approved.update({
        "version": 4,
        "entries": sorted(
            approved_by_pair.values(),
            key=lambda entry: (entry["answer"], entry["clue"].casefold()),
        ),
    })

    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    rejected_pairs = blacklist.setdefault("rejectedPairs", [])
    existing = {
        (normalize(item["answer"]), normalize(item["clue"])) for item in rejected_pairs
    }
    for index in sorted(REJECT_IDS):
        entry = entries[index - 1]
        key = (normalize(entry["answer"]), normalize(entry["clue"]))
        if key not in existing:
            rejected_pairs.append({
                "answer": entry["answer"],
                "clue": entry["clue"],
                "reason": f"relation non univoque, contextuelle ou trop rare après relecture (JDM-B-{index:02d})",
            })
            existing.add(key)

    decisions = {
        "version": 1,
        "batch": "jdm-exhaustive-20260715-b",
        "sourceDigest": EXPECTED_DIGEST,
        "counts": {
            "accepted": len(ACCEPT_IDS), "rejected": len(REJECT_IDS), "doubt": len(DOUBT_IDS)
        },
        "decisions": [
            {
                "id": f"JDM-B-{index:02d}",
                "answer": entry["answer"],
                "clue": entry["clue"],
                "decision": "accept" if index in ACCEPT_IDS else "reject" if index in REJECT_IDS else "doubt",
            }
            for index, entry in enumerate(entries, start=1)
        ],
    }
    atomic_json(APPROVED, approved)
    atomic_json(BLACKLIST, blacklist)
    atomic_json(DECISIONS, decisions)
    print(json.dumps({**decisions["counts"], "approvedTotal": len(approved["entries"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
