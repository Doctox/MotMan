"""Import sourced French synonym pairs from the DBnary Wiktionary extract.

The result is staging data, never publication data.  DBnary gives us a large,
licensed relation corpus; the editorial gate still decides whether a short
synonym is sufficiently precise and age-appropriate for a clue cell.
"""
from __future__ import annotations

import argparse
import bz2
import gzip
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://kaiko.getalp.org/static/ontolex/latest/fr_dbnary_ontolex.ttl.bz2"
LICENSE = "CC-BY-SA-3.0"
LABEL_RE = re.compile(r'rdfs:label\s+"((?:\\.|[^"\\])*)"@fr')
POS_RE = re.compile(r"lexinfo:partOfSpeech\s+lexinfo:([A-Za-z]+)")
SYNONYM_SECTION_RE = re.compile(r"dbnary:synonym\s+(.+?)(?:;|\.)", re.S)
URI_RE = re.compile(r"fra:([^\s,;]+)|<http://kaiko\.getalp\.org/dbnary/fra/([^>]+)>")
WORD_RE = re.compile(r"^[A-Z]{2,9}$")
ALLOWED_POS = {"noun", "adjective", "verb", "adverb", "interjection"}


def normalize_word(value: str) -> str:
    value = unquote(value).replace("_", " ").replace("’", "'")
    value = "".join(
        character for character in unicodedata.normalize("NFD", value)
        if unicodedata.category(character) != "Mn"
    ).upper()
    return re.sub(r"[^A-Z]", "", value) if " " not in value and "'" not in value else ""


def decode_turtle_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace(r'\"', '"').replace(r"\\", "\\")


def iter_blocks(source: Path):
    with bz2.open(source, "rt", encoding="utf-8", errors="replace") as handle:
        block = []
        for line in handle:
            if line.strip():
                block.append(line)
            elif block:
                yield "".join(block)
                block.clear()
        if block:
            yield "".join(block)


def parse_entries(source: Path):
    seen = set()
    for block in iter_blocks(source):
        label_match = LABEL_RE.search(block)
        synonym_match = SYNONYM_SECTION_RE.search(block)
        pos_match = POS_RE.search(block)
        if not (label_match and synonym_match and pos_match):
            continue
        if pos_match.group(1) not in ALLOWED_POS:
            continue
        label = decode_turtle_string(label_match.group(1))
        answer = normalize_word(label)
        if not WORD_RE.fullmatch(answer):
            continue
        for match in URI_RE.finditer(synonym_match.group(1)):
            clue = normalize_word(match.group(1) or match.group(2))
            key = answer, clue
            if not WORD_RE.fullmatch(clue) or answer == clue or key in seen:
                continue
            seen.add(key)
            yield {
                "answer": answer,
                "clue": clue.title(),
                "length": len(answer),
                "difficulty": "unrated",
                "clueType": "direct-synonym",
                "sourceType": "dictionary",
                "sourceId": "dbnary-fr-wiktionary",
                "sourceUrl": SOURCE_URL,
                "sourceEntry": f"https://fr.wiktionary.org/wiki/{label}",
                "editorialStatus": "staging-unreviewed",
                "license": LICENSE,
            }


def write_document(entries: list[dict], output: Path) -> None:
    lengths = Counter(entry["length"] for entry in entries)
    payload = {
        "version": 1,
        "source": {
            "id": "dbnary-fr-wiktionary",
            "url": SOURCE_URL,
            "license": LICENSE,
            "role": "synonym relations for editorial staging; never auto-published",
        },
        "policy": "Direct sourced synonym relations only; editorial review remains mandatory.",
        "metrics": {"entries": len(entries), "byLength": dict(sorted(lengths.items()))},
        "entries": entries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if output.suffix == ".gz":
        with gzip.open(output, "wb", compresslevel=9) as handle:
            handle.write(encoded)
    else:
        output.write_bytes(encoded)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "src/data/sources/fr_dbnary_ontolex.ttl.bz2")
    parser.add_argument("--output", type=Path, default=ROOT / "src/data/crossword.dbnary.staging.json.gz")
    args = parser.parse_args()
    entries = sorted(parse_entries(args.source), key=lambda item: (item["length"], item["answer"], item["clue"]))
    write_document(entries, args.output)
    print(json.dumps({"output": str(args.output), "entries": len(entries)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
