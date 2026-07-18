"""Import exact clue-answer pairs from published Le Parisien/RCI arrowwords.

The grid decoding follows the public FlecheBench research format. Definitions
are kept verbatim apart from joining line-break fragments and display casing.
"""
from __future__ import annotations

import argparse
import ast
import gzip
import json
import re
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from import_crossword_corpus import (
    KNOWLEDGE_RE, ROOT, clue_tokens, display_clue, image_for, normalize_answer,
    normalize_clue_key, pair_is_eligible, pair_score, token_frequency,
)
from wordfreq import zipf_frequency


DEFAULT_OUTPUT = ROOT / "src" / "data" / "crossword.leparisien.json"
DEFAULT_CACHE = ROOT / "src" / "data" / "crossword.leparisien.raw.json.gz"
MENU_URL = "https://static.rcijeux.fr/drupal_game/leparisien/menu/js/jeux_mfleches{force}.js"
GRID_URL = (
    "https://static.rcijeux.fr/drupal_game/leparisien/"
    "mfleches1/grids/mfleches_{force}_{number}.mfj"
)
SOURCE_REPOSITORY = "https://github.com/AlexandreEDMOND/flechebench"

DEPRECATED_ARROW_SPECS = {
    "a": "s1", "b": "s2", "c": "s0", "d": "s3", "y": "s4", "é": "s5",
    "l": "d0", "v": "d1", "g": "d2", "q": "d3", "m": "d0", "w": "d1",
    "h": "d2", "r": "d3", "k": "d0", "u": "d1", "f": "d2", "p": "d3",
    "n": "d0", "x": "d1", "i": "d2", "s": "d3", "j": "d0", "t": "d1",
    "e": "d2", "o": "d3", "z": "d0",
}
CELL_ARROW_SPECS = {
    "s0": ["hb"], "s1": ["hd"], "s2": ["bb"], "s3": ["bd"],
    "s4": ["td"], "s5": ["gb"],
    "d0": ["hb", "bb"], "d1": ["hb", "bd"],
    "d2": ["hd", "bb"], "d3": ["hd", "bd"],
}
ARROWS = {
    "hd": (0, 1, "across"), "hb": (0, 1, "down"),
    "bd": (1, 0, "across"), "bb": (1, 0, "down"),
    "td": (-1, 0, "across"), "gb": (0, -1, "down"),
}


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "MotMan-corpus-importer/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8-sig")


def menu_issues(force: int, count: int) -> list[tuple[date, str, int]]:
    text = fetch_text(MENU_URL.format(force=force))
    issues = []
    for token, number, _flag in re.findall(r'"(\d{6})"\s*:\s*\["(\d+)"\s*,\s*"(\d+)"', text):
        published = date(2000 + int(token[4:6]), int(token[2:4]), int(token[0:2]))
        if published <= date.today():
            issues.append((published, number, force))
    return sorted(issues)[-count:]


def parse_mfj(text: str) -> dict:
    match = re.search(r"var\s+gamedata\s*=\s*\{(.*)\};?\s*$", text, re.S)
    if not match:
        raise ValueError("gamedata absent")
    body = re.sub(
        r"(\n\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', match.group(1)
    )
    return ast.literal_eval("{" + body + "}")


def clean_clue(lines: list[str]) -> str:
    return " ".join(lines).replace("– ", "").replace("–", "").replace("- ", "-").strip()


def read_answer(grid: list[str], row: int, col: int, direction: str) -> str:
    answer = ""
    while 0 <= row < len(grid) and 0 <= col < len(grid[row]):
        value = grid[row][col]
        if not value.isalpha() or not value.isupper():
            break
        answer += value
        if direction == "across":
            col += 1
        else:
            row += 1
    return normalize_answer(answer)


def extract_pairs(issue: tuple[date, str, int]) -> list[dict]:
    published, number, force = issue
    data = parse_mfj(fetch_text(GRID_URL.format(force=force, number=number)))
    grid = data["grille"]
    definitions = data["definitions"]
    definition_index = 0
    pairs = []
    for row, line in enumerate(grid):
        for col, character in enumerate(line):
            if not (character.isalpha() and character.islower()):
                continue
            modern = DEPRECATED_ARROW_SPECS.get(character)
            if modern is None:
                continue
            for arrow_spec in CELL_ARROW_SPECS[modern]:
                dr, dc, direction = ARROWS[arrow_spec]
                clue = clean_clue(definitions[definition_index])
                answer = read_answer(grid, row + dr, col + dc, direction)
                pairs.append({
                    "answer": answer,
                    "clue": clue,
                    "force": force,
                    "puzzleId": f"mfleches_{force}_{number}",
                    "publishedOn": published.isoformat(),
                })
                definition_index += 1
    if definition_index != len(definitions):
        raise ValueError(f"mfleches_{force}_{number}: définitions non consommées")
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count-per-force", type=int, default=100)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()

    editorial = json.loads(
        (ROOT / "src" / "data" / "editorial.blacklist.json").read_text(encoding="utf-8")
    )
    rejected_pairs = {
        (item["answer"], item["clue"].casefold()) for item in editorial["rejectedPairs"]
    }
    cache = args.cache if args.cache.is_absolute() else ROOT / args.cache
    cached = None
    if cache.exists():
        with gzip.open(cache, "rt", encoding="utf-8") as stream:
            cached = json.load(stream)
    if cached and cached.get("countPerForce", 0) >= args.count_per_force:
        raw_pairs = cached["pairs"]
        failures = cached.get("failures", [])
        issues = [None] * cached["issueCount"]
    else:
        issues = [
            issue for force in range(1, 5)
            for issue in menu_issues(force, args.count_per_force)
        ]
        raw_pairs = []
        failures = []
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(extract_pairs, issue): issue for issue in issues}
            for future in as_completed(futures):
                try:
                    raw_pairs.extend(future.result())
                except Exception as error:
                    failures.append({"issue": str(futures[future]), "error": str(error)})
        cache.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(cache, "wt", encoding="utf-8") as stream:
            json.dump({
                "countPerForce": args.count_per_force,
                "issueCount": len(issues),
                "failures": failures,
                "pairs": raw_pairs,
            }, stream, ensure_ascii=False)

    candidates: dict[str, list[dict]] = defaultdict(list)
    for pair in raw_pairs:
        if pair_is_eligible(pair["answer"], pair["clue"], rejected_pairs):
            candidates[pair["answer"]].append(pair)

    selected = {}
    for answer, pairs in candidates.items():
        unique = {}
        for pair in pairs:
            unique.setdefault(normalize_clue_key(pair["clue"]), pair)
        selected[answer] = max(
            unique.values(),
            key=lambda pair: (pair_score(answer, pair["clue"]), -pair["force"]),
        )

    entries = []
    for answer, pair in sorted(selected.items()):
        answer_frequency = zipf_frequency(answer.lower(), "fr")
        clue_frequency = min(
            (token_frequency(token) for token in clue_tokens(pair["clue"])), default=0
        )
        if pair["force"] >= 3 or answer_frequency < 3.0:
            difficulty = "hard"
        elif (pair["force"] == 1 and answer_frequency >= 3.6
              and clue_frequency >= 3.5 and not KNOWLEDGE_RE.search(pair["clue"])):
            difficulty = "easy"
        else:
            difficulty = "normal"
        entry = {
            "answer": answer,
            "clue": display_clue(pair["clue"]),
            "sourceClue": pair["clue"],
            "length": len(answer),
            "frequency": round(zipf_frequency(answer.lower(), "fr"), 3),
            "difficulty": difficulty,
            "sourceDifficulty": pair["force"],
            "clueType": "crossword-source",
            "sourceType": "crossword",
            "sourceId": "leparisien-rcijeux",
            "sourceUrl": GRID_URL.format(force=pair["force"], number=pair["puzzleId"].split("_")[-1]),
            "sourcePuzzleId": pair["puzzleId"],
            "sourcePublishedOn": pair["publishedOn"],
            "editorialStatus": "source-backed",
            "conceptGroup": answer,
            "semanticConflicts": [],
        }
        image = image_for(answer)
        if image:
            entry["image"] = image
        entries.append(entry)

    counts = Counter(entry["difficulty"] for entry in entries)
    lengths = Counter(entry["length"] for entry in entries)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 1,
        "format": "webcrow-cwdb-compatible",
        "publicationPolicy": "Exact published clue only; no generated or rewritten clue.",
        "source": {
            "id": "leparisien-rcijeux",
            "researchParser": SOURCE_REPOSITORY,
            "menus": [MENU_URL.format(force=force) for force in range(1, 5)],
            "requestedGrids": len(issues),
            "failedGrids": failures,
        },
        "counts": {
            "rawPairs": len(raw_pairs),
            "entries": len(entries),
            "byDifficulty": dict(sorted(counts.items())),
            "byLength": {str(length): count for length, count in sorted(lengths.items())},
            "withImage": sum("image" in entry for entry in entries),
        },
        "entries": entries,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "imported", "grids": len(issues) - len(failures),
        "rawPairs": len(raw_pairs), "entries": len(entries),
        "byDifficulty": dict(counts), "failures": len(failures), "output": str(output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
