#!/usr/bin/env python3
"""Build the mandatory unavailable-answer brief for every LLM fill agent."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from build_compact_7x8_review import family_key, normalize


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "src/data/grid.catalog.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
OUTPUT = ROOT / "src/data/grid-generation-handcrafted/llm-first-unavailable-answers.json"


def answer_from_cooldown(item: object) -> str:
    return normalize(str(item.get("answer", "") if isinstance(item, dict) else item))


def build_brief() -> dict:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    active_occurrences: dict[str, list[str]] = {}
    counts: Counter[str] = Counter()
    for grid in catalog.get("grids", []):
        for word in grid.get("words", []):
            answer = normalize(str(word.get("answer", "")))
            if not answer:
                continue
            counts[answer] += 1
            active_occurrences.setdefault(answer, []).append(str(grid.get("id", "")))
    rejected = {
        normalize(str(answer))
        for key in ("rejectedAnswers", "rejectedEasyAnswers", "rejectedNormalAnswers")
        for answer in blacklist.get(key, [])
        if normalize(str(answer))
    }
    cooldown = {
        answer_from_cooldown(item)
        for item in blacklist.get("rotationCooldownAnswers", [])
        if answer_from_cooldown(item)
    }
    active = set(counts)
    forbidden = rejected | cooldown
    return {
        "version": 1,
        "generatedOn": "2026-07-21",
        "sourceCatalogVersion": catalog.get("version"),
        "activeGridCount": len(catalog.get("grids", [])),
        "policy": {
            "activeExactAnswer": "score-penalty-check-occurrences-and-cooldown",
            "activeSemanticFamily": "score-penalty-not-global-ban",
            "blacklist": "hard-block-no-agent-exception",
            "rotationCooldown": "hard-block-no-agent-exception",
            "newBatchExactAnswer": "hard-block-after-first-use",
            "newBatchSemanticFamily": "hard-block-after-first-use"
        },
        "activeAnswerCount": len(active),
        "activeAnswers": sorted(active),
        "activeOccurrences": {
            answer: active_occurrences[answer]
            for answer in sorted(active_occurrences)
        },
        "activeFamilies": sorted({family_key(answer) for answer in active}),
        "blacklistedAnswers": sorted(rejected),
        "rotationCooldownAnswers": sorted(cooldown),
        "forbiddenAnswerCount": len(forbidden),
        "forbiddenAnswers": sorted(forbidden),
        "highFatigueAnswers": [
            "EGO", "EN", "LE", "OSE", "PC", "TE", "TOM", "OM"
        ]
    }


def main() -> None:
    brief = build_brief()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(brief, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(OUTPUT),
        "activeGridCount": brief["activeGridCount"],
        "activeAnswerCount": brief["activeAnswerCount"],
        "forbiddenAnswerCount": brief["forbiddenAnswerCount"],
        "activeFamilies": len(brief["activeFamilies"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
