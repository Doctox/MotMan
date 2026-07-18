"""Build three conservative, image-rich repetition renovations for owner review.

The active catalog is never edited here.  Each draft keeps the exact 9x10
topology of an older high-repeat grid.  Only answers that can be changed
without altering any crossing letter are replaced.
"""
from __future__ import annotations

import copy
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as generator  # noqa: E402
from audit_active_answer_repetition import build_lexical_families  # noqa: E402
from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402


CATALOG = ROOT / "src/data/grid.catalog.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
LEGACY_IMAGE_CORPUS = ROOT / "src/data/crossword.corpus.json"
STAGING = ROOT / "src/data/grid-generation-handcrafted/repetition-renovation.review.json"
AUDIT = ROOT / "output/quality/repetition-renovation-audit.json"
HTML = ROOT / "output/quality/repetition-renovation-review.html"
ASSETS = ROOT / "public/assets/clues/twemoji"
TWEMOJI_RAW = "https://raw.githubusercontent.com/jdecked/twemoji/master/assets/svg/{code}.svg"
TWEMOJI_PAGE = "https://github.com/jdecked/twemoji/blob/master/assets/svg/{code}.svg"

TARGETS = (
    "reference-standard-26",
    "reference-standard-09",
    "reference-standard-19",
)

REPLACEMENTS = {
    "reference-standard-26": {
        "AN": "CP",
        "DO": "IP",
    },
    "reference-standard-09": {
        "ON": "HS",
        "LA": "JT",
        "RUSE": "BUSE",
    },
    "reference-standard-19": {
        "IF": "QI",
        "MI": "ZI",
    },
}

REPLACEMENT_OVERRIDES = {
    "BUSE": {
        "clue": "Rapace",
        "sourceClue": "Gros rapace diurne",
        "sourceId": "larousse-buse",
        "sourceUrl": "https://www.larousse.fr/dictionnaires/francais/buse/11752",
        "sourceType": "dictionary",
        "editorialStatus": "human-reviewed",
    },
}

IMAGE_ANSWERS = {
    "reference-standard-26": {"EAU", "FEU", "LIT", "CREPE", "MANUCURE", "BUEE"},
    "reference-standard-09": {"EAU", "NEZ", "LAIT", "BLE", "RIZ", "VENT"},
    "reference-standard-19": {"ROI", "LIT", "VENT", "PILE", "ASTRE", "STOP"},
}

# Only missing assets are downloaded.  Existing reviewed image records remain
# the source of truth for EAU, FEU, NEZ, LAIT, ROI, PILE and STOP.
NEW_IMAGE_SPECS = {
    "BLE": "1f33e",       # sheaf of rice / wheat
    "RIZ": "1f35a",       # cooked rice
    "VENT": "1f32c",      # wind face
    "LIT": "1f6cf",       # bed
    "ASTRE": "2b50",      # star
    "CREPE": "1f95e",     # pancakes
    "MANUCURE": "1f485",  # nail polish
    "BUEE": "1f32b",      # fog
}


def ensure_twemoji_asset(answer: str, code: str) -> dict:
    ASSETS.mkdir(parents=True, exist_ok=True)
    asset = ASSETS / f"{answer.lower()}.svg"
    if not asset.exists():
        request = urllib.request.Request(
            TWEMOJI_RAW.format(code=code),
            headers={"User-Agent": "MotMan-repetition-renovation/1.0"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = response.read()
        if b"<svg" not in payload[:500]:
            raise ValueError(f"Twemoji invalide pour {answer}: {code}")
        asset.write_bytes(payload)
    return {
        "asset": f"/assets/clues/twemoji/{answer.lower()}.svg",
        "alt": answer.title(),
        "source": "Twemoji",
        "license": "CC BY 4.0",
    }


def repetition_metrics(grids: list[dict]) -> dict:
    answers = [word["answer"] for grid in grids for word in grid.get("words", [])]
    concept_by_answer, _ = build_lexical_families(sorted(set(answers)))
    concepts = [concept_by_answer[answer] for answer in answers]
    counts = Counter(concepts)
    return {
        "grids": len(grids),
        "answerSlots": len(answers),
        "uniqueConcepts": len(counts),
        "conceptExcessSlots": len(answers) - len(counts),
        "conceptExcessRate": round(
            (len(answers) - len(counts)) / max(1, len(answers)), 3
        ),
        "conceptsUsedAtLeastFourTimes": sum(count >= 4 for count in counts.values()),
    }


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    quarantined = set(blacklist.get("quarantinedGridIds", []))
    playable_before = [
        grid for grid in catalog["grids"] if grid["id"] not in quarantined
    ]
    by_id = {grid["id"]: grid for grid in catalog["grids"]}
    sources = {entry["answer"]: entry for entry in generator.load_entries()}
    legacy_image_sources = {
        entry["answer"]: entry
        for entry in json.loads(
            LEGACY_IMAGE_CORPUS.read_text(encoding="utf-8")
        ).get("entries", [])
        if entry.get("image")
    }

    image_records = {
        answer: ensure_twemoji_asset(answer, code)
        for answer, code in NEW_IMAGE_SPECS.items()
    }
    image_provenance = {}
    for answer in {
        "EAU", "FEU", "NEZ", "LAIT", "ROI", "PILE", "STOP"
    }:
        source = sources.get(answer, {})
        if not source.get("image"):
            source = legacy_image_sources.get(answer, {})
        if not source.get("image"):
            raise ValueError(f"image centrale attendue mais absente : {answer}")
        image_records[answer] = source["image"]
        image_provenance[answer] = source

    drafts = []
    reports = []
    changes = []
    for target_id in TARGETS:
        original = by_id[target_id]
        draft = copy.deepcopy(original)
        draft_id = target_id.replace("reference-standard", "repetition-renovation")
        draft.update({
            "id": draft_id,
            "publicationStatus": "owner-review-required",
            "editorialProfile": "motman-conservative-repetition-renovation",
            "replacesGridId": target_id,
            "reviewCycle": "2026-07-16",
        })
        replacement_map = REPLACEMENTS[target_id]
        expected_images = IMAGE_ANSWERS[target_id]
        seen_replacements = set()

        for number, word in enumerate(draft["words"], 1):
            old_answer = word["answer"]
            new_answer = replacement_map.get(old_answer, old_answer)
            if new_answer != old_answer:
                source = {
                    **sources[new_answer],
                    **REPLACEMENT_OVERRIDES.get(new_answer, {}),
                }
                if len(new_answer) != len(old_answer):
                    raise ValueError(f"longueur incompatible : {old_answer}/{new_answer}")
                word.update({
                    "answer": new_answer,
                    "clue": source["clue"],
                    "sourceClue": source.get("sourceClue", source["clue"]),
                    "sourceId": source.get("sourceId"),
                    "sourceUrl": source.get("sourceUrl"),
                    "sourceType": source.get("sourceType"),
                    "editorialStatus": "human-reviewed",
                    "manualReview": "reviewed-awaiting-owner",
                    "definitionStatus": "reviewed-repetition-replacement",
                    "conceptGroup": source.get("conceptGroup", new_answer),
                    "semanticConflicts": source.get("semanticConflicts", []),
                })
                seen_replacements.add(old_answer)
                changes.append({
                    "gridId": draft_id,
                    "oldAnswer": old_answer,
                    "newAnswer": new_answer,
                    "newClue": source["clue"],
                })
            word["wordId"] = f"{draft_id}:word:{number:02d}"
            word["manualReview"] = "reviewed-awaiting-owner"
            word["editorialReviewId"] = "repetition-renovation-20260716"

            if word["answer"] in expected_images:
                answer = word["answer"]
                code = NEW_IMAGE_SPECS.get(answer)
                image = image_records[answer]
                word.update({
                    "clue": "",
                    "sourceClue": f"Indice illustré : {answer.lower()}",
                    "sourceId": (
                        f"twemoji-{code}"
                        if code else image_provenance[answer].get("sourceId")
                    ),
                    "sourceUrl": (
                        TWEMOJI_PAGE.format(code=code)
                        if code else image_provenance[answer].get("sourceUrl")
                    ),
                    "sourceType": "image",
                    "editorialStatus": "image-reviewed",
                    "definitionStatus": "reviewed-image",
                    "license": "CC BY 4.0",
                    "image": image,
                })
            else:
                word.pop("image", None)

        if seen_replacements != set(replacement_map):
            missing = set(replacement_map) - seen_replacements
            raise ValueError(f"{target_id}: remplacements absents {sorted(missing)}")
        actual_images = {word["answer"] for word in draft["words"] if word.get("image")}
        if actual_images != expected_images:
            raise ValueError(
                f"{draft_id}: images {sorted(actual_images)} au lieu de {sorted(expected_images)}"
            )
        report = audit_grid_topology(draft, enforce_layout=False)
        if not report["valid"]:
            raise ValueError(f"{draft_id}: {report['errors']}")
        drafts.append(draft)
        reports.append(report)

    playable_after = [
        grid for grid in playable_before if grid["id"] not in set(TARGETS)
    ] + drafts
    before = repetition_metrics(playable_before)
    after = repetition_metrics(playable_after)
    metrics = {
        "drafts": len(drafts),
        "replacements": len(changes),
        "images": sum(
            bool(word.get("image")) for grid in drafts for word in grid["words"]
        ),
        "before": before,
        "afterIfApproved": after,
        "conceptExcessSlotsRemoved": (
            before["conceptExcessSlots"] - after["conceptExcessSlots"]
        ),
        "activeCatalogModified": False,
    }
    document = {
        "version": 1,
        "kind": "motman-conservative-repetition-renovation-owner-review",
        "publicationPolicy": "Non publié ; validation explicite du propriétaire requise.",
        "metrics": metrics,
        "changes": changes,
        "grids": drafts,
    }
    STAGING.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    AUDIT.write_text(json.dumps({
        "version": 1,
        "valid": True,
        "metrics": metrics,
        "changes": changes,
        "grids": reports,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    change_cards = "".join(
        f'<li><code>{item["gridId"]}</code> : '
        f'<b>{item["oldAnswer"]}</b> → <b>{item["newAnswer"]}</b> '
        f'({item["newClue"]})</li>'
        for item in changes
    )
    summary = (
        '<section style="max-width:1100px;margin:18px auto;padding:14px 18px;'
        'background:#eef8f1;border:1px solid #77ad87;border-radius:10px">'
        '<h2 style="margin-top:0">Trois rénovations prudentes — non publiées</h2>'
        '<p>Mêmes silhouettes 9×10, chemins inchangés, aucune lettre orpheline. '
        'Chaque grille contient exactement six images. Le catalogue actif reste intact.</p>'
        f'<p><b>Effet mesuré :</b> {metrics["conceptExcessSlotsRemoved"]} utilisations '
        'répétées retirées sans modifier un seul croisement.</p>'
        f'<ul>{change_cards}</ul></section>'
    )
    page = render_topology_html(
        reports, title="MotMan — rénovation prudente de trois grilles"
    )
    HTML.write_text(page.replace("<body>", "<body>" + summary, 1), encoding="utf-8")
    print(json.dumps({
        "status": "built-not-published",
        "html": str(HTML),
        "staging": str(STAGING),
        "audit": str(AUDIT),
        "metrics": metrics,
        "changes": changes,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
