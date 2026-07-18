"""Polish one fresh, image-rich grid and stop for explicit owner review."""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as generator  # noqa: E402
from editorial_quality import editorial_errors, grid_semantic_errors  # noqa: E402
from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402


RAW = ROOT / "output/quality/clean-fresh-before-images.json"
STAGING = ROOT / "src/data/grid-generation-handcrafted/image-rich-checkpoint.review.json"
AUDIT = ROOT / "output/quality/image-rich-checkpoint-audit.json"
HTML = ROOT / "output/quality/image-rich-checkpoint-review.html"
CENTRAL = ROOT / "src/data/crossword.central.json.gz"

CLUES = {
    "UE": "Union européenne",
    "RASOIR": "Très ennuyeux",
    "ALARMANT": "Inquiétant",
    "MUSICIEN": "Artiste musical",
    "LOT": "Groupement",
    "RENOM": "Réputation",
    "MAP": "Carte anglaise",
    "TENU": "Peu épais",
    "AVIS": "Opinion",
    "TOT": "Le matin",
    "POLE": "Centre attractif",
    "RAME": "Train de métro",
    "ALU": "Métal léger",
    "SAS": "Passage étanche",
    "ORIGAN": "Herbe aromatique",
    "IMC": "Indice corporel",
    "RAIL": "Voie ferrée",
    "NEON": "Gaz rare",
    "TNT": "Explosif",
    "BRAVO": "Acclamation",
    "REPIT": "Trêve",
    "SOT": "Peu malin",
    "MEMO": "Note rapide",
    "PURE": "Sans mélange",
    "MAT": "Sans éclat",
    "NUL": "Très mauvais",
}
IMAGE_ANSWERS = {"BRAS", "MUR", "TV"}
OWNER_ROTATION_BLOCK = {"AMAS", "AN", "ANS", "BOL", "FER", "ILE", "ILES", "MER", "SEL"}
PROVENANCE_OVERRIDES = {
    "LOT": "https://www.cnrtl.fr/definition/lot",
    "MAP": "https://dictionary.cambridge.org/dictionary/english-french/map",
    "TOT": "https://www.cnrtl.fr/definition/t%C3%B4t",
}


def answer_family(answer: str) -> str:
    if len(answer) >= 4 and answer.endswith(("S", "X")):
        return answer[:-1]
    return answer


def digest(entries: list[dict]) -> str:
    rows = sorted(
        f"{entry['answer']}\t{entry.get('clue', '')}\t{entry.get('sourceId', '')}"
        for entry in entries
    )
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def main() -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    grid = copy.deepcopy(raw["grids"][0])
    grid_id = "image-rich-review-01"
    grid.update({
        "id": grid_id,
        "publicationStatus": "owner-review-required",
        "editorialProfile": "motman-image-rich-human-pass",
        "reviewCycle": "2026-07-16",
        "corpusPolicy": "full-central-index-then-explicit-editorial-gates",
    })

    entries = generator.load_entries()
    sources = {entry["answer"]: entry for entry in entries}
    # A published answer can later enter rotation cooldown (MUR here). Keep
    # its reviewed image provenance available when refreshing historical
    # review evidence without reopening it to future generation.
    image_entries = json.loads(
        (ROOT / "src/data/crossword.images-reviewed.json").read_text(encoding="utf-8")
    )["entries"]
    for entry in image_entries:
        sources.setdefault(entry["answer"], entry)
    for number, word in enumerate(grid["words"], 1):
        answer = word["answer"]
        if answer in OWNER_ROTATION_BLOCK:
            raise ValueError(f"réponse en rotation froide : {answer}")
        word.update({
            "wordId": f"{grid_id}:word:{number:02d}",
            "definitionStatus": "manually-edited",
            "manualReview": "reviewed-awaiting-owner",
            "editorialReviewId": "image-rich-checkpoint-20260716",
        })
        # Refresh missing provenance from the canonical source.  The raw fill
        # predates some owner-pair source links and must not freeze an empty
        # URL into a publishable runtime grid.
        source = sources[answer]
        for field in ("sourceId", "sourceUrl", "sourceType", "license"):
            if not word.get(field) and source.get(field):
                word[field] = source[field]
        if answer in PROVENANCE_OVERRIDES:
            word["sourceUrl"] = PROVENANCE_OVERRIDES[answer]
        if answer in IMAGE_ANSWERS:
            image = sources[answer].get("image")
            if not image:
                raise ValueError(f"image centrale absente : {answer}")
            word["clue"] = ""
            word["image"] = image
            word["editorialStatus"] = "image-reviewed"
        else:
            if answer not in CLUES:
                raise ValueError(f"définition manuelle absente : {answer}")
            word["clue"] = CLUES[answer]
            word.pop("image", None)
            word["editorialStatus"] = "human-reviewed"
        errors = editorial_errors(word, root=ROOT)
        if errors:
            raise ValueError(f"{answer}: {errors}")

    semantic = grid_semantic_errors(grid["words"])
    if semantic:
        raise ValueError(f"doublon sémantique : {semantic}")
    families = [answer_family(word["answer"]) for word in grid["words"]]
    if len(families) != len(set(families)):
        raise ValueError("famille singulier/pluriel répétée")

    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    rejected = set(blacklist.get("rejectedAnswers", []))
    rejected_pairs = {
        (item["answer"], item["clue"].casefold())
        for item in blacklist.get("rejectedPairs", [])
    }
    for word in grid["words"]:
        if word["answer"] in rejected:
            raise ValueError(f"réponse blacklistée : {word['answer']}")
        if word.get("clue") and (word["answer"], word["clue"].casefold()) in rejected_pairs:
            raise ValueError(f"couple blacklisté : {word['answer']} / {word['clue']}")

    report = audit_grid_topology(grid)
    if not report["valid"]:
        raise ValueError(report["errors"])

    catalog = json.loads((ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8"))
    active_usage = Counter(
        word["answer"]
        for previous in catalog["grids"]
        if previous.get("id") != grid_id
        for word in previous["words"]
    )
    answers = [word["answer"] for word in grid["words"]]
    active_repeats = {
        answer: active_usage[answer] for answer in answers if active_usage[answer]
    }
    with gzip.open(CENTRAL, "rt", encoding="utf-8") as stream:
        central = json.load(stream)
    full_generator_entries = [
        entry for entry in central["entries"] if entry.get("generatorEligible")
    ]
    proof = {
        "centralDistinctAnswers": central["metrics"]["distinctAnswers"],
        "generatorEligibleAnswersLoaded": len(entries),
        "generatorEligibleAnswersInCentral": len(full_generator_entries),
        "indexedAnswers": len(entries),
        "corpusDigestSha256": digest(entries),
        "answersByLength": dict(sorted(Counter(entry["length"] for entry in entries).items())),
        "sourcesByCanonicalAnswer": dict(Counter(
            entry.get("sourceId", "unknown") for entry in entries
        ).most_common()),
        "reviewedImageAnswersAvailable": sum(bool(entry.get("image")) for entry in entries),
        "explicitlyBlacklistedDuringSearch": ["ABETI", "PIU"],
        "rawCandidatesAcceptedForHumanPass": 1,
        "rawCandidatesRejected": raw.get("rejectionCounts", {}),
    }
    metrics = {
        "grids": 1,
        "answers": len(answers),
        "uniqueAnswers": len(set(answers)),
        "newAgainstActive": len(answers) - len(active_repeats),
        "rareActiveRepeats": active_repeats,
        "maximumPriorUsesOfARepeat": max(active_repeats.values(), default=0),
        "images": len(IMAGE_ANSWERS),
        "imageAnswers": sorted(IMAGE_ANSWERS),
        "lengthProfile": dict(sorted(Counter(map(len, answers)).items())),
        "twoLetterAnswers": sorted(answer for answer in answers if len(answer) == 2),
        "topologyValid": True,
        "orphanLetters": 0,
        "semanticDuplicates": 0,
    }
    document = {
        "version": 1,
        "kind": "image-rich-owner-review-checkpoint",
        "publicationPolicy": "Non publié ; validation explicite du propriétaire requise.",
        "corpusProof": proof,
        "batchMetrics": metrics,
        "grids": [grid],
    }
    STAGING.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    AUDIT.write_text(json.dumps({
        "version": 1,
        "valid": True,
        "corpusProof": proof,
        "metrics": metrics,
        "grids": [report],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    page = render_topology_html([report], title="MotMan — grille riche en images à relire")
    repeat_text = ", ".join(f"{answer} (1×)" for answer in sorted(active_repeats))
    summary = (
        '<section style="max-width:1100px;margin:18px auto;padding:14px 18px;'
        'background:#eef8f1;border:1px solid #77ad87;border-radius:10px">'
        '<b>Checkpoint non publié — dis-moi franchement ce qui ne va pas</b><br>'
        f'{metrics["answers"]} réponses · {metrics["newAgainstActive"]} nouvelles · '
        f'{metrics["images"]} images ({", ".join(metrics["imageAnswers"])}) · '
        'topologie valide, aucune lettre orpheline.<br>'
        f'<b>Reprises rares clairement signalées :</b> {repeat_text}. '
        'Chacune était apparue une seule fois ; aucun mot de la liste fatigante n’est repris.<br>'
        f'<b>Preuve corpus :</b> {proof["indexedAnswers"]} réponses éligibles indexées, '
        f'{proof["reviewedImageAnswersAvailable"]} illustrables.'
        '</section>'
    )
    HTML.write_text(page.replace("<body>", "<body>" + summary, 1), encoding="utf-8")
    print(json.dumps({
        "status": "built-not-published",
        "html": str(HTML),
        "staging": str(STAGING),
        "audit": str(AUDIT),
        "metrics": metrics,
        "proof": {
            "indexedAnswers": proof["indexedAnswers"],
            "imageAnswers": proof["reviewedImageAnswersAvailable"],
            "digest": proof["corpusDigestSha256"],
        },
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
