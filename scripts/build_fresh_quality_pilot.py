"""Build one manually edited, non-publishable fresh-grid pilot for owner review."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

from editorial_quality import editorial_errors, grid_semantic_errors
from grid_topology import audit_grid_topology, render_topology_html


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output/quality/fresh-quota6-smoke.json"
STAGING = ROOT / "src/data/grid-generation-handcrafted/fresh-quality-pilot.review.json"
AUDIT = ROOT / "output/quality/fresh-quality-pilot-audit.json"
HTML = ROOT / "output/quality/fresh-quality-pilot-review.html"

CLUES = {
    "CB": "Carte bancaire",
    "ISBAS": "Maisons russes",
    "MAINMISE": "Emprise",
    "ASSASSIN": "Meurtrier",
    "LCI": "La Chaîne Info",
    "BLAME": "Réprimande",
    "RASE": "Coupe court",
    "PAC": "Politique agricole",
    "TOUT": "Entier",
    "UVEE": "Tunique oculaire",
    "POP": "Musique populaire",
    "SOT": "Peu malin",
    "PAIE": "Salaire",
    "IMAM": "Guide musulman",
    "SAS": "Passage étanche",
    "BIS": "Encore",
    "SMS": "Message mobile",
    "GENIE": "Esprit brillant",
    "ISLE": "Rivière périgourdine",
    "SIC": "Ainsi écrit",
    "CV": "Parcours professionnel",
    "BRAVO": "Acclamation",
    "LACET": "Cordon",
    "MET": "Dispose",
    "QUOI": "Mot interrogatif",
    "PUS": "Liquide infecté",
    "OPA": "Offre d'achat",
    "TPE": "Terminal de paiement",
}

IMAGE_ANSWER = "ANANAS"

# These three short forms came from the owner's editorial suggestions rather
# than from the imported crossword corpus. Keep an authoritative reference on
# the runtime record so each manually shortened clue remains traceable.
SOURCE_OVERRIDES = {
    "PAC": {
        "sourceId": "commission-europeenne-pac",
        "sourceUrl": "https://agriculture.ec.europa.eu/common-agricultural-policy_fr",
        "sourceType": "authoritative-reference",
    },
    "POP": {
        "sourceId": "cnrtl-pop",
        "sourceUrl": "https://www.cnrtl.fr/definition/pop",
        "sourceType": "authoritative-reference",
    },
    "TPE": {
        "sourceId": "banque-de-france-tpe",
        "sourceUrl": "https://www.banque-france.fr/system/files/2025-04/EI_2025.pdf",
        "sourceType": "authoritative-reference",
    },
}


def answer_family(answer: str) -> str:
    if len(answer) >= 4 and answer.endswith(("S", "X")):
        return answer[:-1]
    return answer


def shape_fingerprint(grid: dict) -> str:
    payload = json.dumps(sorted(grid["clueCells"]), separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def image_record() -> dict:
    return {
        "asset": "/assets/clues/twemoji/ananas.svg",
        "alt": "Ananas",
        "source": "Twemoji",
        "sourceUrl": "https://github.com/jdecked/twemoji/blob/main/assets/svg/1f34d.svg",
        "license": "CC BY 4.0",
    }


def load_grid() -> dict:
    document = json.loads(SOURCE.read_text(encoding="utf-8"))
    grid = copy.deepcopy(document["grids"][0])
    grid_id = "fresh-quality-pilot-01"
    grid.update({
        "id": grid_id,
        "publicationStatus": "owner-review-required",
        "editorialProfile": "motman-fresh-quality-pilot",
        "reviewCycle": "2026-07-16",
        "shapeFingerprint": shape_fingerprint(grid),
        "corpusPolicy": "full-central-placement-with-six-rescue-cap",
    })
    seen = set()
    for number, word in enumerate(grid["words"], 1):
        answer = word["answer"]
        if answer in seen:
            raise ValueError(f"réponse répétée : {answer}")
        seen.add(answer)
        word.update({
            "wordId": f"{grid_id}:word:{number:02d}",
            "definitionStatus": "manually-edited",
            "manualReview": "reviewed-awaiting-owner",
            "editorialStatus": "image-reviewed" if answer == IMAGE_ANSWER else "human-reviewed",
            "editorialReviewId": "fresh-quality-pilot-20260716",
        })
        if answer == IMAGE_ANSWER:
            word["clue"] = ""
            word["image"] = image_record()
        else:
            if answer not in CLUES:
                raise ValueError(f"définition manuelle absente : {answer}")
            word["clue"] = CLUES[answer]
            word.pop("image", None)
        if answer in SOURCE_OVERRIDES:
            word.update(SOURCE_OVERRIDES[answer])
        errors = editorial_errors(word, root=ROOT)
        if errors:
            raise ValueError(f"{answer}: {errors}")
    semantic = grid_semantic_errors(grid["words"])
    if semantic:
        raise ValueError(f"doublon sémantique : {semantic}")
    return grid


def assert_fresh(grid: dict) -> dict:
    active = json.loads(
        (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
    )
    active_answers = {
        word["answer"] for previous in active["grids"] for word in previous["words"]
    }
    active_families = {answer_family(answer) for answer in active_answers}
    answers = [word["answer"] for word in grid["words"]]
    families = [answer_family(answer) for answer in answers]
    exact_repeats = sorted(set(answers) & active_answers)
    family_repeats = sorted(set(families) & active_families)
    if exact_repeats or family_repeats:
        raise ValueError({
            "activeAnswerRepeats": exact_repeats,
            "activeFamilyRepeats": family_repeats,
        })
    if len(families) != len(set(families)):
        raise ValueError("famille singulier/pluriel répétée dans la grille")
    active_shapes = {
        tuple(sorted(map(tuple, previous.get("clueCells", []))))
        for previous in active["grids"]
    }
    shape_is_new = tuple(sorted(map(tuple, grid["clueCells"]))) not in active_shapes
    if not shape_is_new:
        raise ValueError("silhouette déjà active")
    return {
        "activeAnswerRepeats": exact_repeats,
        "activeFamilyRepeats": family_repeats,
        "shapeIsNew": shape_is_new,
    }


def assert_blacklist(grid: dict) -> None:
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    blocked = set(blacklist.get("rejectedAnswers", []))
    blocked.update(item["answer"] for item in blacklist.get("rotationCooldownAnswers", []))
    blocked_pairs = {
        (item["answer"], item["clue"].casefold())
        for item in blacklist.get("rejectedPairs", [])
    }
    for word in grid["words"]:
        if word["answer"] in blocked:
            raise ValueError(f"réponse blacklistée : {word['answer']}")
        pair = (word["answer"], word.get("clue", "").casefold())
        if word.get("clue") and pair in blocked_pairs:
            raise ValueError(f"couple blacklisté : {pair}")


def main() -> None:
    grid = load_grid()
    assert_blacklist(grid)
    freshness = assert_fresh(grid)
    report = audit_grid_topology(grid)
    if not report["valid"]:
        raise ValueError(report["errors"])
    answers = [word["answer"] for word in grid["words"]]
    lengths = Counter(map(len, answers))
    metrics = {
        "grids": 1,
        "answers": len(answers),
        "uniqueAnswers": len(set(answers)),
        "lengthProfile": dict(sorted(lengths.items())),
        "twoLetterAnswers": sorted(answer for answer in answers if len(answer) == 2),
        "images": sum(bool(word.get("image")) for word in grid["words"]),
        "manualDefinitions": sum(bool(word.get("clue")) for word in grid["words"]),
        "topologyValid": True,
        **freshness,
    }
    document = {
        "version": 1,
        "kind": "fresh-quality-owner-review-pilot",
        "publicationPolicy": "Non publié ; validation explicite du propriétaire requise.",
        "batchMetrics": metrics,
        "grids": [grid],
    }
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    AUDIT.write_text(
        json.dumps({
            "version": 1,
            "valid": True,
            "metrics": metrics,
            "grids": [report],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    page = render_topology_html([report], title="MotMan — pilote frais à relire")
    summary = (
        '<section style="max-width:1100px;margin:18px auto;padding:14px 18px;'
        'background:#eaf7ef;border:1px solid #79b88e;border-radius:10px">'
        '<b>Pilote non publié — à valider</b><br>'
        f'{metrics["answers"]} réponses toutes inédites face au catalogue actif · '
        f'zéro famille singulier/pluriel répétée · '
        f'{metrics["images"]} image · silhouette nouvelle · topologie valide.'
        '</section>'
    )
    page = page.replace("<body>", "<body>" + summary, 1)
    HTML.write_text(page, encoding="utf-8")
    print(json.dumps({
        "status": "built",
        "html": str(HTML),
        "staging": str(STAGING),
        "audit": str(AUDIT),
        "metrics": metrics,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
