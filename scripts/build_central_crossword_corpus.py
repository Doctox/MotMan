"""Merge every production source into one central, status-aware corpus.

DBnary is deliberately excluded.  Existing playable data remains canonical;
JeuxDeMots relations enrich the same file as review candidates and can only
be promoted through an explicit editorial decision.
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
DEFAULT_JDM = DATA / "crossword.jeuxdemots.review.json.gz"
DEFAULT_OUTPUT = DATA / "crossword.central.json.gz"
BASE_FILES = (
    "crossword.corpus.json",
    "crossword.curated.json",
    "crossword.images-reviewed.json",
    "crossword.reference-reviewed.json",
    "crossword.short-source-reviewed.json",
    "crossword.jeuxdemots.approved.json",
)


def atomic_write_gzip_json(path: Path, document: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with gzip.open(temporary, "wt", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
        for attempt in range(6):
            try:
                temporary.replace(path)
                return
            except OSError:
                if attempt == 5:
                    raise
                time.sleep(0.5 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def normalize(value: str) -> str:
    folded = "".join(
        char
        for char in unicodedata.normalize("NFD", value.upper())
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"[^A-Z]", "", folded)


def load_base_entries() -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    documents = {
        name: json.loads((DATA / name).read_text(encoding="utf-8"))
        for name in BASE_FILES
    }
    corpus = documents["crossword.corpus.json"]["entries"]
    curated = documents["crossword.curated.json"]["entries"]
    images = documents["crossword.images-reviewed.json"]["entries"]
    reviewed_document = documents["crossword.reference-reviewed.json"]
    reviewed_short = documents["crossword.short-source-reviewed.json"]["entries"]
    defaults = reviewed_document.get("defaults", {})
    reviewed = [
        {
            **defaults,
            **entry,
            "sourceClue": entry["clue"],
            "conceptGroup": entry.get("conceptGroup", entry["answer"]),
        }
        for entry in reviewed_document["entries"]
    ]
    jdm_approved = documents["crossword.jeuxdemots.approved.json"]["entries"]

    canonical = {}
    canonical.update({entry["answer"]: entry for entry in corpus})
    canonical.update({entry["answer"]: entry for entry in curated})
    canonical.update({entry["answer"]: entry for entry in images})
    for entry in reviewed:
        canonical[entry["answer"]] = {**canonical.get(entry["answer"], {}), **entry}
    for entry in reviewed_short:
        canonical[entry["answer"]] = {**canonical.get(entry["answer"], {}), **entry}
    for entry in jdm_approved:
        # JeuxDeMots may improve the canonical textual couple, but it must not
        # erase a separately reviewed image clue for the same answer.  A plain
        # ``dict.update`` used to drop that image metadata silently.
        canonical[entry["answer"]] = {**canonical.get(entry["answer"], {}), **entry}
    for answer, entry in list(canonical.items()):
        if entry.get("image"):
            canonical[answer] = {
                **entry,
                "image": {**entry["image"], "alt": answer.title()},
            }
    raw = [*corpus, *curated, *images, *reviewed, *reviewed_short, *jdm_approved]
    return raw, canonical, documents


def pair_key(entry: dict) -> tuple[str, str]:
    return entry["answer"], normalize(entry.get("clue", ""))


def load_blacklist() -> tuple[set[str], dict[tuple[str, str], str]]:
    document = json.loads((DATA / "editorial.blacklist.json").read_text(encoding="utf-8"))
    blocked_answers = set(document.get("rejectedAnswers", []))
    blocked_answers.update(document.get("rejectedEasyAnswers", []))
    blocked_answers.update(document.get("rejectedNormalAnswers", []))
    blocked_answers.update(
        item["answer"] for item in document.get("rotationCooldownAnswers", [])
    )
    blocked_pairs = {
        (item["answer"], normalize(item["clue"])): item["reason"]
        for item in document.get("rejectedPairs", [])
    }
    return blocked_answers, blocked_pairs


def build_central(jdm_document: dict) -> dict:
    raw_base, canonical, documents = load_base_entries()
    blocked_answers, blocked_pairs = load_blacklist()
    pairs: dict[tuple[str, str], dict] = {}
    canonical_keys = {answer: pair_key(entry) for answer, entry in canonical.items()}

    for entry in raw_base:
        if entry.get("image"):
            entry = {
                **entry,
                "image": {**entry["image"], "alt": entry["answer"].title()},
            }
        key = pair_key(entry)
        current = pairs.get(key, {})
        # The canonical record can combine a textual pair from JeuxDeMots
        # with image metadata reviewed in ``crossword.images-reviewed``.
        # Materialize that combined record on the selected pair; otherwise
        # the canonical key is correct but the image silently disappears.
        selected = canonical.get(entry["answer"], {}) if key == canonical_keys.get(entry["answer"]) else entry
        merged = {**current, **entry, **selected}
        merged.update({
            "corpusStage": "production-legacy",
            "generatorEligible": key == canonical_keys.get(entry["answer"]),
            "canonicalForGenerator": key == canonical_keys.get(entry["answer"]),
            "evidenceSources": sorted(set(
                current.get("evidenceSources", []) + [entry.get("sourceId", "unknown")]
            )),
        })
        pairs[key] = merged

    for entry in jdm_document["entries"]:
        key = pair_key(entry)
        if key in pairs:
            pairs[key]["evidenceSources"] = sorted(set(
                pairs[key].get("evidenceSources", []) + ["jeuxdemots-r_syn"]
            ))
            pairs[key]["jeuxDeMotsRelationWeight"] = entry.get("sourceRelationWeight")
            continue
        pairs[key] = {
            **entry,
            "corpusStage": "editorial-review",
            "generatorEligible": False,
            "canonicalForGenerator": False,
            "playableAsIs": False,
            "evidenceSources": ["jeuxdemots-r_syn"],
        }

    rejected_generator_pairs = 0
    for key, entry in pairs.items():
        blocked_reason = blocked_pairs.get(key)
        if entry["answer"] in blocked_answers:
            blocked_reason = blocked_reason or "réponse rejetée ou placée en rotation froide"
        if not blocked_reason:
            continue
        if entry.get("canonicalForGenerator"):
            rejected_generator_pairs += 1
        entry["generatorEligible"] = False
        entry["canonicalForGenerator"] = False
        entry["corpusStage"] = "editorial-rejected"
        entry["blacklistReason"] = blocked_reason

    entries = sorted(
        pairs.values(),
        key=lambda entry: (entry["length"], entry["answer"], entry.get("clue", "").casefold()),
    )
    source_ids = Counter(entry.get("sourceId", "unknown") for entry in entries)
    answers = {entry["answer"] for entry in entries}
    generator_entries = [entry for entry in entries if entry["canonicalForGenerator"]]
    if any("dbnary" in source.casefold() for source in source_ids):
        raise ValueError("DBnary ne doit pas entrer dans le corpus central")
    if len(generator_entries) != len({entry["answer"] for entry in generator_entries}):
        raise ValueError("plusieurs couples canoniques pour une reponse")
    return {
        "version": 1,
        "kind": "motman-central-crossword-corpus",
        "publicationPolicy": "Seuls les couples canonicalForGenerator peuvent alimenter le generateur; les relations JDM exigent une promotion editoriale explicite.",
        "sources": [
            {"id": source, "pairs": count}
            for source, count in sorted(source_ids.items())
        ],
        "metrics": {
            "distinctAnswers": len(answers),
            "distinctPairs": len(entries),
            "generatorEligibleDistinctAnswers": len(generator_entries),
            "generatorPairsDisabledByBlacklist": rejected_generator_pairs,
            "jeuxDeMotsDistinctAnswers": len({
                entry["answer"] for entry in entries
                if "jeuxdemots-r_syn" in entry.get("evidenceSources", [])
            }),
            "dbnaryIncluded": False,
            "baseFiles": {
                name: len(document["entries"])
                for name, document in documents.items()
            },
        },
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jeuxdemots", type=Path, default=DEFAULT_JDM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    with gzip.open(args.jeuxdemots, "rt", encoding="utf-8") as handle:
        jdm_document = json.load(handle)
    document = build_central(jdm_document)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_gzip_json(args.output, document)
    print(json.dumps(document["metrics"], ensure_ascii=False, indent=2))
    if document["metrics"]["distinctAnswers"] < 15_000:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
