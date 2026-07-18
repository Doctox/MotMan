#!/usr/bin/env python3
"""Recherche éditoriale en lecture seule dans le corpus central.

Exemple : python scripts/query_central_pairs.py "A..I....."
Le point représente une lettre inconnue. Ce script ne combine pas les mots et ne
remplit aucune grille : il sert uniquement d'index consultable par le rédacteur.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CENTRAL = ROOT / "src/data/crossword.central.json.gz"
CATALOG = ROOT / "src/data/grid.catalog.json"
IMAGES = ROOT / "public/assets/clues/twemoji"


def normalized(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.upper())
    return "".join(char for char in folded if "A" <= char <= "Z")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pattern", help="Lettres et points, ex. A..I.....")
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--all", action="store_true", help="inclure les non-éligibles")
    args = parser.parse_args()

    pattern = normalized(args.pattern.replace(".", "X")).replace("X", ".")
    matcher = re.compile(f"^{pattern}$")

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    active = Counter(
        normalized(word.get("answer", ""))
        for grid in catalog.get("grids", [])
        for word in grid.get("words", [])
    )
    image_stems = {normalized(path.stem): path.name for path in IMAGES.glob("*.svg")}

    with gzip.open(CENTRAL, "rt", encoding="utf-8") as stream:
        entries = json.load(stream)["entries"]

    rows = []
    seen = set()
    for entry in entries:
        answer = normalized(entry.get("answer", ""))
        if not matcher.fullmatch(answer):
            continue
        if not args.all and not entry.get("generatorEligible"):
            continue
        key = (answer, entry.get("clue", ""))
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            (
                active[answer],
                0 if answer in image_stems else 1,
                -float(entry.get("frequency") or 0),
                answer,
                entry,
            )
        )
    rows.sort(key=lambda row: row[:4])
    for repeats, image_order, _frequency, answer, entry in rows[: args.limit]:
        image = image_stems.get(answer, "-")
        print(
            f"{answer:<12} | {entry.get('clue',''):<32} | "
            f"actif={repeats:<2} img={image:<18} "
            f"diff={entry.get('difficulty','?'):<6} src={entry.get('sourceId','?')}"
        )
    print(f"-- {len(rows)} couple(s), {len({row[3] for row in rows})} réponse(s) --")


if __name__ == "__main__":
    main()
