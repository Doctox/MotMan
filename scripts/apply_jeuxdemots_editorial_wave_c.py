"""Apply the line-by-line editorial decisions for the 500-row JDM wave C."""
from __future__ import annotations

import hashlib
import json

from apply_jeuxdemots_editorial_batch import DATA, atomic_json, normalize
from review_jeuxdemots_strict_candidates import approved_entry


SOURCE = DATA / "crossword.jeuxdemots.editorial-wave-c.json"
APPROVED = DATA / "crossword.jeuxdemots.approved.json"
BLACKLIST = DATA / "editorial.blacklist.json"
DECISIONS = DATA / "jeuxdemots.editorial-wave-c-decisions.json"
EXPECTED_COUNT = 500
EXPECTED_DIGEST = "66148e8788d062b997a4c27346c2c652e05d067f70a2ef0d16e4ba32380997c7"
DOUBT_IDS = {22, 68, 195, 216, 296}
REJECT_IDS = {
    7, 17, 26, 27, 32, 37, 46, 47, 49, 51, 56, 59, 60, 62, 65,
    73, 75, 76, 81, 82, 96, 97, 102, 110, 111, 112, 113, 114, 117,
    118, 119, 120, 124, 127, 130, 133, 147, 155, 158, 161, 169, 174,
    177, 181, 186, 187, 189, 191, 192, 197, 199, 204, 212, 214, 220,
    222, 225, 228, 230, 234, 235, 236, 242, 257, 260, 264, 270, 273,
    274, 275, 276, 286, 297, 301, 302, 303, 304, 310, 316, 322, 324,
    325, 326, 328, 329, 330, 342, 344, 347, 353, 358, 359, 366, 368,
    369, 370, 371, 372, 375, 376, 380, 388, 408, 411, 414, 415, 419,
    420, 421, 422, 423, 425, 428, 431, 439, 447, 461, 462, 468, 469,
    473, 476, 478, 482, 488,
}
OVERUSED_IDS = {56}
REGISTER_IDS = {37, 59, 62, 65, 81, 82, 117, 127, 155, 181, 225, 301, 302, 322, 330, 353, 482}
FORM_IDS = {174, 212, 214, 257, 368, 414, 415, 447, 461, 462, 488}


def digest(entries: list[dict]) -> str:
    return hashlib.sha256(json.dumps(
        [(entry["answer"], entry["clue"]) for entry in entries],
        ensure_ascii=False, separators=(",", ":"),
    ).encode()).hexdigest()


def reason(index: int) -> str:
    if index in OVERUSED_IDS:
        return "réponse volontairement écartée pour éviter sa surutilisation"
    if index in REGISTER_IDS:
        return "registre familier, offensant, archaïque ou anglais gratuit"
    if index in FORM_IDS:
        return "forme grammaticale, accentuée ou morphologique ambiguë"
    return "relation trop contextuelle, large ou non univoque pour être devinable"


def main() -> int:
    entries = json.loads(SOURCE.read_text(encoding="utf-8"))["entries"]
    if len(entries) != EXPECTED_COUNT or digest(entries) != EXPECTED_DIGEST:
        raise ValueError("la vague éditoriale C a changé")
    if REJECT_IDS & DOUBT_IDS:
        raise ValueError("une ligne ne peut être à la fois rejetée et douteuse")
    accept_ids = set(range(1, EXPECTED_COUNT + 1)) - REJECT_IDS - DOUBT_IDS

    approved = json.loads(APPROVED.read_text(encoding="utf-8"))
    approved_by_pair = {
        (entry["answer"], normalize(entry["clue"])): entry
        for entry in approved["entries"]
    }
    for index in sorted(accept_ids):
        entry = entries[index - 1]
        approved_by_pair[(entry["answer"], normalize(entry["clue"]))] = {
            **approved_entry(entry),
            "manualReview": "editorial-exhaustive-triage-approved",
            "reviewedBy": "motman-editorial",
            "editorialBatch": "jdm-exhaustive-20260715-c",
            "editorialDecisionId": f"JDM-C-{index:03d}",
        }
    approved.update({
        "version": 5,
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
    added = 0
    for index in sorted(REJECT_IDS):
        entry = entries[index - 1]
        key = (normalize(entry["answer"]), normalize(entry["clue"]))
        if key in existing:
            continue
        rejected_pairs.append({
            "answer": entry["answer"],
            "clue": entry["clue"],
            "reason": f"{reason(index)} (JDM-C-{index:03d})",
        })
        existing.add(key)
        added += 1

    decisions = {
        "version": 1,
        "batch": "jdm-exhaustive-20260715-c",
        "sourceDigest": EXPECTED_DIGEST,
        "counts": {
            "accepted": len(accept_ids), "rejected": len(REJECT_IDS), "doubt": len(DOUBT_IDS)
        },
        "decisions": [
            {
                "id": f"JDM-C-{index:03d}",
                "answer": entry["answer"],
                "clue": entry["clue"],
                "decision": "accept" if index in accept_ids else "reject" if index in REJECT_IDS else "doubt",
                "reason": "couple direct et devinable" if index in accept_ids else reason(index) if index in REJECT_IDS else "nuance conservée pour une revue ultérieure",
            }
            for index, entry in enumerate(entries, start=1)
        ],
    }
    atomic_json(APPROVED, approved)
    atomic_json(BLACKLIST, blacklist)
    atomic_json(DECISIONS, decisions)
    print(json.dumps({
        **decisions["counts"], "newlyBlacklisted": added,
        "approvedTotal": len(approved["entries"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
