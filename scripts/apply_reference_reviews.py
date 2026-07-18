"""Apply reviewed clues to staging candidates and compute publication gates."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import generate_grid_catalog as generator
from editorial_quality import editorial_errors
from grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--publishable-output", type=Path)
    args = parser.parse_args()
    input_path = args.input if args.input.is_absolute() else ROOT / args.input
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    document = json.loads(input_path.read_text(encoding="utf-8"))
    document.setdefault("difficultyRanges", generator.DIFFICULTY_RANGES)
    document.setdefault("maximumAnswerUsesPerLevel", 1)
    document.setdefault("maximumShortAnswerUsesPerLevel", 2)
    sources = {entry["answer"]: entry for entry in generator.load_entries()}
    for grid in document["grids"]:
        failures = []
        for word in grid["words"]:
            source = sources.get(word["answer"])
            if source and source.get("editorialStatus") in {"human-reviewed", "image-reviewed"}:
                word["clue"] = source["clue"]
                word["definitionStatus"] = "reviewed"
                word["sourceId"] = source["sourceId"]
                word["sourceUrl"] = source["sourceUrl"]
                if source.get("image"):
                    word["image"] = source["image"]
            if word["definitionStatus"] != "reviewed":
                failures.append({"answer": word["answer"], "code": "review_required"})
            failures.extend({"answer": word["answer"], **error}
                            for error in editorial_errors(word, root=ROOT))
        topology = audit_grid_topology(grid)
        grid["difficultyMix"] = dict(Counter(
            word["difficulty"] for word in grid["words"]
        ))
        for level in ("easy", "normal", "hard"):
            grid["difficultyMix"].setdefault(level, 0)
        if not topology["valid"]:
            failures.append({"code": "topology", "counts": topology["errorCounts"]})
        image_count = sum(bool(word.get("image")) for word in grid["words"])
        if not 1 <= image_count <= 6:
            failures.append({"code": "image_count", "count": image_count})
        grid["reviewSummary"] = {
            "topologyValid": topology["valid"],
            "images": image_count,
            "failures": failures,
        }
        grid["publicationStatus"] = "publishable" if not failures else "editorial-review-required"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.publishable_output:
        publishable_path = (args.publishable_output if args.publishable_output.is_absolute()
                            else ROOT / args.publishable_output)
        publishable_path.parent.mkdir(parents=True, exist_ok=True)
        publishable_path.write_text(json.dumps({
            **{key: value for key, value in document.items() if key != "grids"},
            "kind": "reviewed-reference-staging",
            "grids": [grid for grid in document["grids"]
                      if grid["publicationStatus"] == "publishable"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output_path),
        "publishable": [grid["id"] for grid in document["grids"]
                        if grid["publicationStatus"] == "publishable"],
        "pending": {
            grid["id"]: len(grid["reviewSummary"]["failures"])
            for grid in document["grids"] if grid["publicationStatus"] != "publishable"
        },
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
