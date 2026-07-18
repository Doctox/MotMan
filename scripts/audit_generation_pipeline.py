"""Produce a reproducible factual audit of MotMan's corpus and active catalog."""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

import generate_grid_catalog as generator
from editorial_quality import editorial_errors
from grid_topology import audit_grid_topology
from import_crossword_corpus import clue_tokens


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "data"


def counter(values) -> dict:
    return dict(sorted(Counter(values).items(), key=lambda item: str(item[0])))


def frequency_band(value: float) -> str:
    if value < 3:
        return "<3"
    if value < 4:
        return "3–4"
    if value < 5:
        return "4–5"
    return "≥5"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, default=DATA / "crossword.corpus.json")
    parser.add_argument("--catalog", type=Path, default=DATA / "grid.catalog.json")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "output" / "quality" / "pipeline-audit.json")
    args = parser.parse_args()

    library = json.loads(args.library.read_text(encoding="utf-8"))
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    editorial = json.loads((DATA / "editorial.blacklist.json").read_text(encoding="utf-8"))
    entries = library["entries"]
    entry_by_answer = {entry["answer"]: entry for entry in entries}

    indexes = generator.build_index(entries)
    eligible_answers = {answer for words in indexes[0].values() for answer in words}
    eligible = [entry for entry in entries if entry["answer"] in eligible_answers]
    ineligible = [entry for entry in entries if entry["answer"] not in eligible_answers]
    corpus_editorial_failures = [
        {
            "answer": entry["answer"], "clue": entry.get("clue", ""),
            "sourceId": entry.get("sourceId"),
            "errors": editorial_errors(entry, root=ROOT),
        }
        for entry in entries if editorial_errors(entry, root=ROOT)
    ]

    quarantined_ids = set(editorial["quarantinedGridIds"])
    active_grids = [grid for grid in catalog["grids"] if grid["id"] not in quarantined_ids]
    all_uses = Counter(word["answer"] for grid in active_grids for word in grid["words"])

    levels = {}
    for level in ("easy", "normal", "hard"):
        grids = [grid for grid in active_grids if grid["difficulty"] == level]
        uses = Counter(word["answer"] for grid in grids for word in grid["words"])
        sources = Counter(
            entry_by_answer[word["answer"]].get("sourceId", "unknown")
            for grid in grids for word in grid["words"]
            if word["answer"] in entry_by_answer
        )
        levels[level] = {
            "activeGrids": len(grids),
            "answerSlots": sum(uses.values()),
            "uniqueAnswers": len(uses),
            "repeatedAnswers": dict(sorted(
                ((answer, count) for answer, count in uses.items() if count > 1),
                key=lambda item: (-item[1], item[0]),
            )),
            "bySource": dict(sorted(sources.items())),
        }

    topology = [audit_grid_topology(grid) for grid in catalog["grids"]]
    source_documents = {}
    for name in ("crossword.ouestfrance.json", "crossword.leparisien.json"):
        document = json.loads((DATA / name).read_text(encoding="utf-8"))
        source_documents[name] = {
            "entries": len(document["entries"]),
            "byLength": counter(entry["length"] for entry in document["entries"]),
            "byDifficulty": counter(entry["difficulty"] for entry in document["entries"]),
            "source": document.get("source"),
        }
    dbnary_path = DATA / "crossword.dbnary.staging.json.gz"
    if dbnary_path.exists():
        with gzip.open(dbnary_path, "rt", encoding="utf-8") as handle:
            document = json.load(handle)
        source_documents[dbnary_path.name] = {
            "entries": len(document["entries"]),
            "uniqueAnswers": len({entry["answer"] for entry in document["entries"]}),
            "byLength": counter(entry["length"] for entry in document["entries"]),
            "editorialStatus": "staging-unreviewed",
            "source": document.get("source"),
        }

    result = {
        "version": 1,
        "inputs": {
            "library": str(args.library),
            "catalog": str(args.catalog),
            "sourceDocuments": source_documents,
        },
        "corpus": {
            "mergedEntries": len(entries),
            "generatorEligibleEntries": len(eligible),
            "generatorIneligibleEntries": len(ineligible),
            "eligibleByLength": counter(entry["length"] for entry in eligible),
            "eligibleByDifficulty": counter(entry["difficulty"] for entry in eligible),
            "eligibleBySource": counter(entry.get("sourceId") for entry in eligible),
            "eligibleByEditorialStatus": counter(entry.get("editorialStatus") for entry in eligible),
            "eligibleByClueTokenCount": counter(len(clue_tokens(entry["clue"])) for entry in eligible),
            "eligibleByFrequencyBand": counter(frequency_band(entry["frequency"]) for entry in eligible),
            "eligibleWithImageMetadata": sum("image" in entry for entry in eligible),
            "eligibleWithExplicitLicense": sum(bool(entry.get("license")) for entry in eligible),
            "ineligibleByLength": counter(entry["length"] for entry in ineligible),
            "editorialRuleFailures": corpus_editorial_failures,
            "twoLetterEligiblePairs": [
                {"answer": entry["answer"], "clue": entry["clue"], "difficulty": entry["difficulty"]}
                for entry in eligible if entry["length"] == 2
            ],
        },
        "catalog": {
            "storedGrids": len(catalog["grids"]),
            "quarantinedGrids": len(catalog["grids"]) - len(active_grids),
            "activeGrids": len(active_grids),
            "levels": levels,
            "activeAnswerSlots": sum(all_uses.values()),
            "activeUniqueAnswers": len(all_uses),
            "activeRepeatedAnswerCount": sum(count > 1 for count in all_uses.values()),
            "mostRepeatedAnswers": all_uses.most_common(20),
            "topology": {
                "validStoredGrids": sum(report["valid"] for report in topology),
                "validActiveGrids": sum(
                    report["valid"] and report["gridId"] not in quarantined_ids
                    for report in topology
                ),
                "activeErrorCounts": counter(
                    error["code"]
                    for report in topology if report["gridId"] not in quarantined_ids
                    for error in report["errors"]
                ),
            },
            "storedEditorialRuleFailures": [
                {
                    "gridId": grid["id"], "difficulty": grid["difficulty"],
                    "answer": word.get("answer"), "clue": word.get("clue", ""),
                    "errors": editorial_errors(word, root=ROOT),
                    "quarantined": grid["id"] in quarantined_ids,
                }
                for grid in catalog["grids"] for word in grid["words"]
                if editorial_errors(word, root=ROOT)
            ],
        },
        "structuralFindings": [
            "Le même index de 8 375 réponses est actuellement proposé aux trois niveaux; la difficulté est imposée seulement par quota pendant la recherche.",
            "Les silhouettes historiques autorisent des suites visibles sans réponse déclarée.",
            "Le faible stock de réponses de deux lettres explique leur répétition lorsque les patrons en exigent plusieurs.",
            "La provenance est enregistrée, mais les entrées textuelles ne portent pas de champ de licence explicite.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "eligibleEntries": len(eligible),
        "activeGrids": len(active_grids),
        "validActiveTopologies": result["catalog"]["topology"]["validActiveGrids"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
