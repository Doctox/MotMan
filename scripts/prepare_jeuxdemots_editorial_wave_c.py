"""Select the best 500 lower-tier JDM relations for manual editorial pass C."""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
TRIAGE = DATA / "crossword.jeuxdemots.full-triage.json.gz"
OUTPUT = DATA / "crossword.jeuxdemots.editorial-wave-c.json"
PRIOR_DECISIONS = (
    DATA / "jeuxdemots.editorial-batch-20260715.json",
    DATA / "jeuxdemots.editorial-batch-20260715-b.json",
)
LIMIT = 500


def score(entry: dict) -> tuple:
    return (
        bool(entry["reciprocal"]),
        bool(entry["wolfCorroborated"]),
        int(entry.get("mutualRelationWeight") or entry.get("sourceRelationWeight") or 0),
        -int(entry.get("maximumRelationRank") or entry.get("answerRelationRank") or 99),
        float(entry["minimumSourceFrequency"]),
        -len(entry["clue"]),
    )


def main() -> int:
    with gzip.open(TRIAGE, "rt", encoding="utf-8") as handle:
        triage = json.load(handle)
    prior_doubts = set()
    for path in PRIOR_DECISIONS:
        document = json.loads(path.read_text(encoding="utf-8"))
        prior_doubts.update(
            (item["answer"], item["clue"])
            for item in document["decisions"] if item["decision"] == "doubt"
        )
    grouped = defaultdict(list)
    for entry in triage["entries"]:
        if entry["triageStatus"] not in {
            "doubt-reciprocal", "doubt-cross-source-nonreciprocal"
        }:
            continue
        if (entry["answer"], entry["clue"]) in prior_doubts:
            continue
        weight = int(entry.get("mutualRelationWeight") or entry.get("sourceRelationWeight") or 0)
        rank = int(entry.get("maximumRelationRank") or entry.get("answerRelationRank") or 99)
        if float(entry["minimumSourceFrequency"]) < 2 or weight < 100 or rank > 5:
            continue
        grouped[entry["answer"]].append(entry)
    selected = [max(entries, key=score) for entries in grouped.values()]
    selected.sort(key=lambda entry: (
        not entry["wolfCorroborated"],
        not entry["reciprocal"],
        -int(entry.get("mutualRelationWeight") or entry.get("sourceRelationWeight") or 0),
        -float(entry["minimumSourceFrequency"]),
        entry["answer"],
    ))
    document = {
        "version": 1,
        "kind": "jeuxdemots-editorial-wave-c",
        "publicationPolicy": "Lot relu ligne par ligne; aucune promotion automatique.",
        "eligibleAnswers": len(selected),
        "entries": selected[:LIMIT],
    }
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "eligibleAnswers": len(selected),
        "waveSize": len(document["entries"]),
        "wolfCorroborated": sum(entry["wolfCorroborated"] for entry in document["entries"]),
        "reciprocal": sum(entry["reciprocal"] for entry in document["entries"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
