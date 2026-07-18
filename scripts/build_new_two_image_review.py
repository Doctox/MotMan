"""Polish two zero-overlap 9x10 grids with six image clues each."""
from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as generator  # noqa: E402
from editorial_quality import editorial_errors, grid_semantic_errors  # noqa: E402
from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402


RAW_FILES = (
    ROOT / "output/quality/new-two-grid-01.raw.json",
    ROOT / "output/quality/new-two-grid-02.raw.json",
)
STAGING = ROOT / "src/data/grid-generation-handcrafted/new-two-image-rich.review.json"
AUDIT = ROOT / "output/quality/new-two-image-rich-audit.json"
HTML = ROOT / "output/quality/new-two-image-rich-review.html"

IMAGE_ANSWERS = (
    {"CANARD", "AUTO", "BD", "TV", "TGV", "DUEL"},
    {"PC", "PAIN", "SKI", "SMS", "CD", "PUB"},
)

CLUE_OVERRIDES = (
    {
        "NIA": "Refusa",
        "BERNE": "Trompe",
        "ANIS": "Épice du pastis",
        "ROND": "Bien en chair",
    },
    {
        "ALANGUIR": "Affaiblir",
        "PUS": "Liquide infecté",
        "PLI": "Marque du tissu",
        "RIRA": "S'amusera",
        "CRISE": "Épisode aigu",
        "CRUT": "Fut persuadé",
    },
)


def answer_family(answer: str) -> str:
    if len(answer) >= 4 and answer.endswith(("S", "X")):
        return answer[:-1]
    return answer


def load_grid(path: Path) -> tuple[dict, dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return copy.deepcopy(document["grids"][0]), document


def main() -> None:
    entries = generator.load_entries()
    sources = {entry["answer"]: entry for entry in entries}
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    rejected = set(blacklist.get("rejectedAnswers", []))
    rejected_pairs = {
        (item["answer"], item["clue"].casefold())
        for item in blacklist.get("rejectedPairs", [])
    }
    cooldown = {
        item["answer"] for item in blacklist.get("rotationCooldownAnswers", [])
    }

    grids = []
    raw_documents = []
    reports = []
    strict_warnings = {}
    batch_answers: set[str] = set()

    for grid_index, path in enumerate(RAW_FILES):
        grid, raw = load_grid(path)
        raw_documents.append(raw)
        grid_id = f"image-rich-review-{grid_index + 2:02d}"
        grid.update({
            "id": grid_id,
            "publicationStatus": "owner-review-required",
            "editorialProfile": "motman-free-craft-six-images",
            "reviewCycle": "2026-07-16",
            "corpusPolicy": "full-central-corpus-plus-human-editorial-pass",
        })
        expected_images = IMAGE_ANSWERS[grid_index]
        answers = {word["answer"] for word in grid["words"]}
        missing_images = expected_images - answers
        if missing_images:
            raise ValueError(f"{grid_id}: réponses-images absentes {sorted(missing_images)}")
        common = batch_answers & answers
        if common:
            raise ValueError(f"réponses répétées entre les deux grilles : {sorted(common)}")
        batch_answers.update(answers)

        for number, word in enumerate(grid["words"], 1):
            answer = word["answer"]
            if answer in rejected or answer in cooldown:
                raise ValueError(f"{grid_id}: réponse bloquée {answer}")
            word.update({
                "wordId": f"{grid_id}:word:{number:02d}",
                "definitionStatus": "manually-edited",
                "manualReview": "reviewed-awaiting-owner",
                "editorialReviewId": "new-two-six-images-20260716",
            })
            source = sources[answer]
            for field in ("sourceId", "sourceUrl", "sourceType", "license"):
                if not word.get(field) and source.get(field):
                    word[field] = source[field]
            if answer in expected_images:
                image = source.get("image")
                if not image:
                    raise ValueError(f"{grid_id}: image centrale absente pour {answer}")
                word.update({
                    "clue": "",
                    "sourceClue": source.get("sourceClue", f"Indice illustré : {answer}"),
                    "sourceId": source.get("sourceId"),
                    "sourceUrl": source.get("sourceUrl"),
                    "sourceType": "image",
                    "editorialStatus": "image-reviewed",
                    "image": image,
                    "license": source.get("license", "CC BY 4.0"),
                    "conceptGroup": source.get("conceptGroup", answer),
                    "semanticConflicts": source.get("semanticConflicts", []),
                })
            else:
                word.pop("image", None)
                word["clue"] = CLUE_OVERRIDES[grid_index].get(answer, word["clue"])
                word["editorialStatus"] = "human-reviewed"
            if word.get("clue") and (answer, word["clue"].casefold()) in rejected_pairs:
                raise ValueError(f"{grid_id}: couple bloqué {answer} / {word['clue']}")
            errors = editorial_errors(word, root=ROOT)
            if errors:
                raise ValueError(f"{grid_id} / {answer}: {errors}")

        image_words = [word for word in grid["words"] if word.get("image")]
        if len(image_words) != 6:
            raise ValueError(f"{grid_id}: {len(image_words)} images au lieu de 6")
        semantic = grid_semantic_errors(grid["words"])
        if semantic:
            raise ValueError(f"{grid_id}: doublon sémantique {semantic}")
        families = [answer_family(word["answer"]) for word in grid["words"]]
        if len(families) != len(set(families)):
            raise ValueError(f"{grid_id}: famille singulier/pluriel répétée")

        report = audit_grid_topology(grid, enforce_layout=False)
        if not report["valid"]:
            raise ValueError(f"{grid_id}: {report['errors']}")
        strict = audit_grid_topology(grid, enforce_layout=True)
        strict_warnings[grid_id] = strict.get("errorCounts", {})
        reports.append(report)
        grids.append(grid)

    catalog = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    reviewed_ids = {grid["id"] for grid in grids}
    active_usage = Counter(
        word["answer"]
        for grid in catalog.get("grids", [])
        if grid.get("id") not in reviewed_ids
        for word in grid.get("words", [])
    )
    per_grid = []
    for grid in grids:
        answers = [word["answer"] for word in grid["words"]]
        repeats = {answer: active_usage[answer] for answer in answers if active_usage[answer]}
        per_grid.append({
            "id": grid["id"],
            "answers": len(answers),
            "images": sorted(word["answer"] for word in grid["words"] if word.get("image")),
            "lengthProfile": dict(sorted(Counter(map(len, answers)).items())),
            "activeRepeats": repeats,
            "newAgainstActive": len(answers) - len(repeats),
            "topologyValid": True,
            "orphanLetters": 0,
            "layoutWarningsForOwnerReview": strict_warnings[grid["id"]],
        })
    metrics = {
        "grids": 2,
        "answers": sum(item["answers"] for item in per_grid),
        "uniqueAnswers": len(batch_answers),
        "repeatedAnswersInsideBatch": [],
        "images": 12,
        "reviewedImageAnswersAvailable": sum(bool(entry.get("image")) for entry in entries),
        "perGrid": per_grid,
    }
    document = {
        "version": 1,
        "kind": "motman-two-free-craft-six-images-owner-review",
        "publicationPolicy": "Non publié ; validation explicite du propriétaire requise.",
        "hardRules": ["9x10", "zero orphan letter", "declared contiguous paths", "exact crossings"],
        "metrics": metrics,
        "grids": grids,
    }
    STAGING.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    AUDIT.write_text(json.dumps({
        "version": 1,
        "valid": True,
        "metrics": metrics,
        "grids": reports,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    page = render_topology_html(reports, title="MotMan — deux nouvelles grilles à six images")
    cards = []
    for item in per_grid:
        repeats = ", ".join(
            f"{answer} ({count}× avant)" for answer, count in sorted(item["activeRepeats"].items())
        ) or "aucune"
        cards.append(
            f'<div style="padding:10px 12px;background:#fff;border:1px solid #b7cdbf;border-radius:8px">'
            f'<b>{item["id"]}</b> · {item["answers"]} réponses · '
            f'{item["newAgainstActive"]} nouvelles · 6 images : {", ".join(item["images"])}<br>'
            f'<small>Reprises rares : {repeats}</small></div>'
        )
    summary = (
        '<section style="max-width:1100px;margin:18px auto;padding:14px 18px;'
        'background:#eef8f1;border:1px solid #77ad87;border-radius:10px">'
        '<h2 style="margin-top:0">Deux grilles non publiées — à valider franchement</h2>'
        '<p>Règles bloquantes appliquées : 9×10, chemins déclarés, croisements exacts, '
        'aucune lettre ni aucun segment orphelin. Les densités de définitions sont montrées '
        'telles quelles pour votre jugement visuel.</p>'
        f'<div style="display:grid;gap:8px">{"".join(cards)}</div></section>'
    )
    HTML.write_text(page.replace("<body>", "<body>" + summary, 1), encoding="utf-8")
    print(json.dumps({
        "status": "built-not-published",
        "html": str(HTML),
        "staging": str(STAGING),
        "audit": str(AUDIT),
        "metrics": metrics,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
