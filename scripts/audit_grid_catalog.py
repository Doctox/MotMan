"""Fail fast when a generated MotMan catalog violates its playable contract."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from import_crossword_corpus import clue_tokens
from grid_topology import audit_grid_topology, render_topology_html


ROOT = Path(__file__).resolve().parents[1]
LEVELS = ("easy", "normal", "hard")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=ROOT / "src" / "data" / "grid.catalog.json")
    parser.add_argument("--library", type=Path, default=ROOT / "src" / "data" / "crossword.corpus.json")
    parser.add_argument("--expected-per-level", type=int, default=10)
    parser.add_argument("--expected-easy", type=int)
    parser.add_argument("--expected-normal", type=int)
    parser.add_argument("--expected-hard", type=int)
    parser.add_argument("--report-json", type=Path,
                        help="rapport cellulaire complet, y compris les 81 cases")
    parser.add_argument("--report-html", type=Path,
                        help="rendu 9×9 autonome pour la revue humaine")
    parser.add_argument("--allow-legacy-word-ids", action="store_true",
                        help="diagnostic seulement : infère les wordId absents")
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    library = json.loads(args.library.read_text(encoding="utf-8"))
    editorial = json.loads((ROOT / "src" / "data" / "editorial.blacklist.json").read_text(encoding="utf-8"))
    quarantined_ids = set(editorial["quarantinedGridIds"])
    rejected_pairs = {(item["answer"], item["clue"].casefold()) for item in editorial["rejectedPairs"]}
    entries = {entry["answer"]: entry for entry in library["entries"]}
    entries.update({entry["answer"]: entry for entry in json.loads(
        (ROOT / "src" / "data" / "crossword.curated.json").read_text(encoding="utf-8")
    )["entries"]})
    reviewed_document = json.loads(
        (ROOT / "src" / "data" / "crossword.reference-reviewed.json").read_text(encoding="utf-8")
    )
    reviewed_defaults = reviewed_document.get("defaults", {})
    entries.update({
        entry["answer"]: {
            **entries.get(entry["answer"], {}),
            **reviewed_defaults,
            **entry,
            "sourceClue": entry["clue"],
        }
        for entry in reviewed_document["entries"]
    })
    errors = []
    report = {}
    topology_reports = []

    for grid in catalog["grids"]:
        topology = audit_grid_topology(
            grid,
            require_word_ids=not args.allow_legacy_word_ids,
            enforce_layout=False,
        )
        topology["quarantined"] = grid["id"] in quarantined_ids
        topology_reports.append(topology)
        if not topology["valid"] and not topology["quarantined"]:
            counts = ", ".join(
                f"{code}={count}" for code, count in topology["errorCounts"].items()
            )
            errors.append(f"{grid['id']}: topologie invalide ({counts})")

    # The owner replaced the three artificial difficulty buckets with one
    # handcrafted MotMan profile.  Audit that catalog globally instead of
    # assuming every grid still carries a ``difficulty`` field.
    standard_profile = (
        catalog.get("editorialProfile") == "motman-standard"
        or all("difficulty" not in grid for grid in catalog["grids"])
    )
    if standard_profile:
        active_grids = [
            grid for grid in catalog["grids"]
            if grid["id"] not in quarantined_ids
        ]
        uses = Counter(
            word["answer"] for grid in active_grids for word in grid["words"]
        )
        shape_uses = Counter(
            tuple(sorted(map(tuple, grid["clueCells"]))) for grid in active_grids
        )
        for grid in active_grids:
            image_count = sum(bool(word.get("image")) for word in grid["words"])
            if not 1 <= image_count <= 6:
                errors.append(f"{grid['id']}: {image_count} images")
            for word in grid["words"]:
                clue = word.get("clue") or ""
                if clue and (word["answer"], clue.casefold()) in rejected_pairs:
                    errors.append(
                        f"{grid['id']}: couple rejeté {clue} -> {word['answer']}"
                    )
                if not all(word.get(field) for field in ("sourceId", "sourceUrl", "sourceType")):
                    errors.append(
                        f"{grid['id']}: provenance incomplète pour {word['answer']}"
                    )

        result = {
            "valid": not errors,
            "profiles": {
                "standard": {
                    "grids": len(active_grids),
                    "quarantinedGrids": len(catalog["grids"]) - len(active_grids),
                    "slots": sum(uses.values()),
                    "uniqueAnswers": len(uses),
                    "repeatedAnswerOccurrences": sum(
                        count - 1 for count in uses.values()
                    ),
                    "maximumAnswerUse": max(uses.values(), default=0),
                    "uniqueShapes": len(shape_uses),
                    "images": sum(
                        bool(word.get("image"))
                        for grid in active_grids for word in grid["words"]
                    ),
                }
            },
            "topology": {
                "auditedGrids": len(topology_reports),
                "validGrids": sum(item["valid"] for item in topology_reports),
                "validActiveGrids": sum(
                    item["valid"] and not item["quarantined"]
                    for item in topology_reports
                ),
                "errorCounts": dict(sorted(Counter(
                    error["code"]
                    for item in topology_reports if not item["quarantined"]
                    for error in item["errors"]
                ).items())),
            },
            "errors": errors,
        }
        if args.report_json:
            args.report_json.parent.mkdir(parents=True, exist_ok=True)
            args.report_json.write_text(json.dumps({
                "summary": result,
                "grids": topology_reports,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.report_html:
            args.report_html.parent.mkdir(parents=True, exist_ok=True)
            args.report_html.write_text(
                render_topology_html(topology_reports), encoding="utf-8"
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if errors:
            raise SystemExit(1)
        return

    for level in LEVELS:
        quarantined = [grid for grid in catalog["grids"] if grid["difficulty"] == level and grid["id"] in quarantined_ids]
        grids = [grid for grid in catalog["grids"] if grid["difficulty"] == level and grid["id"] not in quarantined_ids]
        expected = getattr(args, f"expected_{level}")
        expected = args.expected_per_level if expected is None else expected
        if len(grids) != expected:
            errors.append(f"{level}: {len(grids)} grilles au lieu de {expected}")
        uses = Counter(word["answer"] for grid in grids for word in grid["words"])
        maximum_uses = catalog.get("maximumAnswerUsesPerLevel", 1)
        maximum_short_uses = catalog.get("maximumShortAnswerUsesPerLevel", maximum_uses)
        repeated = {
            answer: count for answer, count in uses.items()
            if count > (maximum_short_uses if len(answer) <= 3 else maximum_uses)
        }
        if repeated:
            errors.append(f"{level}: réponses trop répétées {repeated}")
        shape_uses = Counter(tuple(map(tuple, grid["clueCells"])) for grid in grids)
        if shape_uses and max(shape_uses.values()) > 2:
            errors.append(f"{level}: une silhouette apparaît plus de deux fois")
        for previous, current in zip(grids, grids[1:]):
            repeated_between_games = (
                {word["answer"] for word in previous["words"]}
                & {word["answer"] for word in current["words"]}
            )
            if repeated_between_games:
                errors.append(
                    f"{level}: répétition entre {previous['id']} et {current['id']} "
                    f"{sorted(repeated_between_games)}"
                )

        for grid in grids:
            word_count = len(grid["words"])
            ranges = catalog["difficultyRanges"][level]
            difficulty_mix = grid.get("difficultyMix") or Counter(
                word.get("difficulty", "normal") for word in grid["words"]
            )
            if not all(ranges[tier][0] <= difficulty_mix[tier] / word_count <= ranges[tier][1]
                       for tier in ranges):
                errors.append(f"{grid['id']}: répartition de difficulté invalide")
            image_count = sum("image" in word for word in grid["words"])
            if not 1 <= image_count <= 6:
                errors.append(f"{grid['id']}: {image_count} images")

            clue_cells = {tuple(cell) for cell in grid["clueCells"]}
            columns = grid.get("columns", grid.get("size", 9))
            rows = grid.get("rows", grid.get("size", 9))
            letters = {}
            lengths = Counter()
            for word in grid["words"]:
                answer = word["answer"]
                clue = word.get("clue") or ""
                if not clue and "image" not in word:
                    errors.append(f"{grid['id']}: définition vide pour {answer}")
                if (answer, clue.casefold()) in rejected_pairs:
                    errors.append(f"{grid['id']}: couple rejeté {word['clue']} -> {answer}")
                if len(answer) != len(word["cells"]):
                    errors.append(f"{grid['id']}: longueur incohérente pour {answer}")
                lengths[len(answer)] += 1
                for letter, cell in zip(answer, word["cells"]):
                    position = tuple(cell)
                    if position in letters and letters[position] != letter:
                        errors.append(f"{grid['id']}: croisement incohérent en {position}")
                    letters[position] = letter
                entry = entries.get(answer)
                if entry is None:
                    errors.append(f"{grid['id']}: {answer} absent de la bibliothèque")
                    continue
                if entry.get("sourceType") not in {"crossword", "image", "dictionary"} or not entry.get("sourceClue"):
                    errors.append(f"{grid['id']}: {answer} n'a pas d'indice sourcé")
                if clue != entry["clue"]:
                    errors.append(f"{grid['id']}: définition modifiée pour {answer}")
                if len(clue_tokens(clue)) > 3:
                    errors.append(f"{grid['id']}: définition trop longue pour {answer}")
            expected_cells = rows * columns
            if len(clue_cells | set(letters)) != expected_cells:
                errors.append(
                    f"{grid['id']}: les {expected_cells} cases ne sont pas toutes utilisées"
                )
            total_lengths = sum(lengths.values())
            varied = (
                len(lengths) >= 4
                and any(lengths[n] for n in (2, 3))
                and any(lengths[n] for n in (4, 5))
                and any(lengths[n] for n in (6, 7, 8))
                and max(lengths.values(), default=0) / max(total_lengths, 1) <= .35
            )
            if not varied:
                errors.append(f"{grid['id']}: distribution de longueurs invalide")

        report[level] = {
            "grids": len(grids),
            "quarantinedGrids": len(quarantined),
            "slots": sum(uses.values()),
            "uniqueAnswers": len(uses),
            "maximumAnswerUse": max(uses.values(), default=0),
            "uniqueShapes": len(shape_uses),
        }

    result = {
        "valid": not errors,
        "levels": report,
        "topology": {
            "auditedGrids": len(topology_reports),
            "validGrids": sum(item["valid"] for item in topology_reports),
            "validActiveGrids": sum(
                item["valid"] and not item["quarantined"] for item in topology_reports
            ),
            "errorCounts": dict(sorted(Counter(
                error["code"]
                for item in topology_reports if not item["quarantined"]
                for error in item["errors"]
            ).items())),
        },
        "errors": errors,
    }
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(json.dumps({
            "summary": result,
            "grids": topology_reports,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.report_html:
        args.report_html.parent.mkdir(parents=True, exist_ok=True)
        args.report_html.write_text(
            render_topology_html(topology_reports), encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
