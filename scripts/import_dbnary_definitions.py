"""Extract a large, traceable French definition reservoir from DBnary.

The output is an editorial source reservoir, not a playable clue file.  It
keeps complete Wiktionary definitions so a short MotMan clue can later be
written and reviewed without guessing the meaning of the answer.
"""
from __future__ import annotations

import argparse
import bz2
import gzip
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
DEFAULT_SOURCE = DATA / "sources/fr_dbnary_ontolex.ttl.bz2"
DEFAULT_OUTPUT = DATA / "crossword.dbnary-definitions.review.json.gz"

MINIMUM_DISTINCT_ANSWERS = 15_000
# This reservoir must also cover uncommon but legitimate answers.  Frequency
# remains available for downstream difficulty gates; it is not a publication
# permit.  At 0.1 occurrence per million, a word is attested rather than an
# arbitrary spelling while the reservoir can exceed 15,000 distinct answers.
MINIMUM_SOURCE_FREQUENCY = 0.1
MAXIMUM_SENSES_PER_ANSWER = 3
ANSWER_LENGTH = (3, 8)
MAXIMUM_DEFINITION_LENGTH = 320

POS_MAP = {
    "noun": "NOM",
    "verb": "VER",
    "adjective": "ADJ",
    "adverb": "ADV",
}
TURTLE_STRING = r'"(?:\\.|[^"\\])*"'
SUBJECT_RE = re.compile(r"^\s*(\S+)")
LABEL_RE = re.compile(rf"rdfs:label\s+({TURTLE_STRING})@fr")
POS_RE = re.compile(r"lexinfo:partOfSpeech\s+lexinfo:(\w+)")
SENSE_RE = re.compile(r"fra:__ws_[^\s,;.]+")
DEFINITION_RE = re.compile(
    rf"skos:definition\s+\[\s*rdf:value\s+({TURTLE_STRING})@fr\s*\]",
    re.S,
)
REGISTER_RE = re.compile(r"^\s*((?:\([^)]*\)\s*)+)")

BLOCKED_REGISTER_MARKERS = {
    "ARCHAIQUE",
    "ARGOT",
    "BELGIQUE",
    "CANADA",
    "DESUET",
    "FAMILIER",
    "FRANCHE COMTE",
    "LORRAINE",
    "PEJORATIF",
    "PROVENCE",
    "QUEBEC",
    "REGIONAL",
    "RARE",
    "SUISSE",
    "VIEILLI",
    "VULGAIRE",
}


def fold(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.upper())
        if unicodedata.category(char) != "Mn"
    )


def normalize_answer(value: str) -> str:
    return re.sub(r"[^A-Z]", "", fold(value.replace("œ", "oe")))


def decode_turtle_string(token: str) -> str:
    """Decode the JSON-compatible string escapes used by Turtle literals."""
    return json.loads(token)


def iter_turtle_blocks(handle):
    block: list[str] = []
    for line in handle:
        if line.strip():
            block.append(line)
        elif block:
            yield "".join(block)
            block = []
    if block:
        yield "".join(block)


def definition_registers(definition: str) -> list[str]:
    match = REGISTER_RE.match(definition)
    if not match:
        return []
    return [
        value.strip()
        for value in re.findall(r"\(([^)]*)\)", match.group(1))
        if value.strip()
    ]


def has_blocked_register(registers: list[str]) -> bool:
    normalized = fold(" ".join(registers)).replace("-", " ")
    return any(marker in normalized for marker in BLOCKED_REGISTER_MARKERS)


def load_context() -> tuple[dict[str, dict], set[str]]:
    lexique = json.loads((DATA / "lexique.lemmas.json").read_text(encoding="utf-8"))
    metadata = {entry["answer"]: entry for entry in lexique["entries"]}
    blacklist = json.loads(
        (DATA / "editorial.blacklist.json").read_text(encoding="utf-8")
    )
    blocked = set(blacklist.get("rejectedAnswers", []))
    blocked.update(
        entry["answer"] for entry in blacklist.get("rotationCooldownAnswers", [])
    )
    return metadata, blocked


def extract_entries(
    source: Path,
    metadata: dict[str, dict],
    blocked_answers: set[str],
) -> tuple[list[dict], Counter]:
    sense_owners: dict[str, dict] = {}
    definitions: dict[str, list[dict]] = defaultdict(list)
    metrics = Counter()

    with bz2.open(source, "rt", encoding="utf-8", errors="strict") as handle:
        for block in iter_turtle_blocks(handle):
            metrics["turtleBlocks"] += 1
            if "ontolex:LexicalEntry" in block and "rdfs:label" in block:
                label_match = LABEL_RE.search(block)
                pos_match = POS_RE.search(block)
                if not label_match or not pos_match:
                    metrics["entryBlocksWithoutSupportedShape"] += 1
                    continue
                label = decode_turtle_string(label_match.group(1))
                if not re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]+", label):
                    metrics["entryLabelsRejectedAsNonSingleWord"] += 1
                    continue
                answer = normalize_answer(label)
                pos = POS_MAP.get(pos_match.group(1))
                answer_metadata = metadata.get(answer)
                if (
                    not pos
                    or not answer_metadata
                    or answer_metadata.get("partOfSpeech") != pos
                    or not ANSWER_LENGTH[0] <= len(answer) <= ANSWER_LENGTH[1]
                    or float(answer_metadata.get("sourceFrequency", 0))
                    < MINIMUM_SOURCE_FREQUENCY
                    or answer in blocked_answers
                ):
                    metrics["entryLabelsRejectedByEligibility"] += 1
                    continue
                owner = {
                    "answer": answer,
                    "sourceLabel": label,
                    "partOfSpeech": pos,
                    "sourceFrequency": float(answer_metadata["sourceFrequency"]),
                    "schoolFrequency": float(answer_metadata.get("schoolFrequency", 0)),
                }
                for sense_id in SENSE_RE.findall(block):
                    sense_owners[sense_id] = owner
                metrics["eligibleLexicalEntries"] += 1
                continue

            if "ontolex:LexicalSense" not in block or "skos:definition" not in block:
                continue
            subject_match = SUBJECT_RE.search(block)
            definition_match = DEFINITION_RE.search(block)
            if not subject_match or not definition_match:
                metrics["senseBlocksWithoutSupportedDefinition"] += 1
                continue
            sense_id = subject_match.group(1)
            owner = sense_owners.get(sense_id)
            if not owner:
                metrics["senseDefinitionsWithoutEligibleOwner"] += 1
                continue
            definition = re.sub(
                r"\s+", " ", decode_turtle_string(definition_match.group(1)).strip()
            )
            registers = definition_registers(definition)
            if (
                len(definition) < 8
                or len(definition) > MAXIMUM_DEFINITION_LENGTH
                or has_blocked_register(registers)
            ):
                metrics["senseDefinitionsRejectedByEditorialGate"] += 1
                continue
            definitions[owner["answer"]].append(
                {
                    **owner,
                    "definition": definition,
                    "registers": registers,
                    "sourceSenseId": sense_id,
                }
            )
            metrics["eligibleSenseDefinitions"] += 1

    entries: list[dict] = []
    for answer in sorted(definitions):
        seen_definitions: set[str] = set()
        retained = 0
        for raw in definitions[answer]:
            definition_key = fold(raw["definition"])
            if definition_key in seen_definitions:
                metrics["duplicateDefinitionsRemoved"] += 1
                continue
            seen_definitions.add(definition_key)
            if retained >= MAXIMUM_SENSES_PER_ANSWER:
                metrics["definitionsRemovedByAnswerCap"] += 1
                continue
            retained += 1
            frequency = raw["sourceFrequency"]
            entries.append(
                {
                    "answer": answer,
                    "clue": raw["definition"],
                    "sourceClue": raw["definition"],
                    "sourceDefinition": raw["definition"],
                    "length": len(answer),
                    "partOfSpeech": raw["partOfSpeech"],
                    "answerSourceFrequency": frequency,
                    "schoolFrequency": raw["schoolFrequency"],
                    "difficulty": (
                        "easy" if frequency >= 15 else "normal" if frequency >= 3 else "hard"
                    ),
                    "clueType": "full-dictionary-definition",
                    "sourceType": "dictionary",
                    "sourceId": "dbnary-fr-wiktionary-definitions",
                    "sourceUrl": "https://kaiko.getalp.org/about-dbnary/download/",
                    "sourceEntry": f"https://fr.wiktionary.org/wiki/{quote(raw['sourceLabel'])}",
                    "sourceSenseId": raw["sourceSenseId"],
                    "license": "CC-BY-SA-3.0",
                    "registers": raw["registers"],
                    "editorialStatus": "source-definition-needs-short-clue-review",
                    "reviewRequired": True,
                    "playableAsIs": False,
                    "conceptGroup": f"dbnary-definition:{raw['sourceSenseId']}",
                    "semanticConflicts": [],
                }
            )
    return entries, metrics


def build_document(source: Path, entries: list[dict], metrics: Counter) -> dict:
    answers = {entry["answer"] for entry in entries}
    by_length = Counter(entry["length"] for entry in entries)
    distinct_by_length = {
        str(length): len({
            entry["answer"] for entry in entries if entry["length"] == length
        })
        for length in sorted(by_length)
    }
    milestone = len(answers) >= MINIMUM_DISTINCT_ANSWERS
    return {
        "version": 1,
        "kind": "licensed-french-definition-editorial-reservoir",
        "publicationPolicy": (
            "Source de sens uniquement. Une definition courte MotMan doit etre "
            "redigee puis revue avant toute utilisation dans une grille."
        ),
        "source": {
            "id": "dbnary-fr-wiktionary-definitions",
            "url": "https://kaiko.getalp.org/about-dbnary/download/",
            "license": "CC-BY-SA-3.0",
            "archive": source.name,
            "archiveBytes": source.stat().st_size,
            "archiveSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
        "eligibilityPolicy": {
            "minimumDistinctAnswers": MINIMUM_DISTINCT_ANSWERS,
            "minimumLexiqueFrequency": MINIMUM_SOURCE_FREQUENCY,
            "answerLength": list(ANSWER_LENGTH),
            "maximumSensesPerAnswer": MAXIMUM_SENSES_PER_ANSWER,
            "maximumSourceDefinitionLength": MAXIMUM_DEFINITION_LENGTH,
            "singleWordsOnly": True,
            "blacklistAndRotationCooldownApplied": True,
            "blockedRegisterMarkers": sorted(BLOCKED_REGISTER_MARKERS),
            "playableWithoutEditorialRewrite": False,
        },
        "metrics": {
            "milestoneReached": milestone,
            "sourceBackedDefinitionPairs": len(entries),
            "distinctAnswers": len(answers),
            "distinctAnswersByLength": distinct_by_length,
            "pairsByLength": {
                str(length): count for length, count in sorted(by_length.items())
            },
            "sourceProcessing": dict(metrics),
        },
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    metadata, blocked_answers = load_context()
    entries, metrics = extract_entries(args.source, metadata, blocked_answers)
    document = build_document(args.source, entries, metrics)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(document["metrics"], ensure_ascii=False, indent=2))
    if not document["metrics"]["milestoneReached"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
