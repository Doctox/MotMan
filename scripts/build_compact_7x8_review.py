#!/usr/bin/env python3
"""Assemble reviewed 7x8 fills into one interactive owner checkpoint."""
from __future__ import annotations

import argparse
import base64
import copy
import gzip
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402


EMOJI_BY_ANSWER = {
    "REPASSE": "👔", "AGE": "🎂", "GRAPPE": "🍇", "PICOLER": "🍺",
    "CAP": "🗺️", "ESCALE": "✈️", "EPREUVE": "📝", "RUE": "🛣️",
    "MERLOT": "🍷", "EPUISE": "😩", "DON": "🎁", "IVOIRE": "🐘",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument(
        "--reference",
        action="append",
        type=Path,
        default=[ROOT / "src/data/grid.catalog.json"],
        help="Lot déjà validé dont les réponses et familles doivent rester absentes.",
    )
    parser.add_argument(
        "--allow-reference-repeat",
        action="append",
        default=[],
        help="Mot-outil court explicitement autorisé à revenir depuis le catalogue actif.",
    )
    parser.add_argument(
        "--allow-internal-repeat",
        action="append",
        default=[],
        help="Charnière courte explicitement autorisée dans deux grilles du lot.",
    )
    parser.add_argument("--include-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument(
        "--playtest-html",
        type=Path,
        help="vue joueur autonome sans réponses ni tableau des solutions",
    )
    return parser.parse_args()


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.upper())
    return "".join(character for character in folded if "A" <= character <= "Z")


@lru_cache(maxsize=1)
def lexical_family_index() -> dict[str, tuple[str, str]]:
    with gzip.open(
        ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8"
    ) as stream:
        entries = json.load(stream).get("entries", [])
    index: dict[str, tuple[str, str]] = {}
    scores: dict[str, float] = {}
    for item in entries:
        answer = normalize(str(item.get("answer", "")))
        lemma = normalize(str(item.get("lemma") or answer))
        if not answer or not lemma:
            continue
        score = float(item.get("constructorScore", 0.0))
        if answer not in index or score > scores[answer]:
            index[answer] = (lemma, str(item.get("partOfSpeech") or ""))
            scores[answer] = score
    return index


def family_key_from_parts(
    answer: str,
    lemma: str,
    part_of_speech: str = "",
    lexical_lookup: dict[str, tuple[str, str]] | None = None,
) -> str:
    """Collapse obvious French inflections without loading the lexicon again."""
    value = normalize(answer)
    if value in {"ELU", "ELUE", "ELUS", "ELUES", "REELU", "REELUE", "REELUS", "REELUES"}:
        return "ELIRE"
    if len(value) <= 3:
        return value
    lexical_lemma = normalize(lemma) or value
    family = lexical_lemma
    # Verb infinitives share the same construction root, while nouns such as
    # SENTIER must keep their final -ER.  This removes the old false positive
    # SENTIER/SENTIS without losing ADAPTER/ADAPTÉE or RESTER/RESTÉE.
    if (
        part_of_speech == "verb"
        and family.endswith(("ER", "IR"))
        and len(family) >= 6
    ):
        family = family[:-2]
    elif (
        part_of_speech == "adjective"
        and family.endswith("I")
        and (lexical_lookup or {}).get(family + "R", ("", ""))[1] == "verb"
    ):
        family = family[:-1]
    if lexical_lemma in {"ELIRE", "REELIRE"}:
        return "ELIRE"
    # The lexical source occasionally labels an inflected feminine form as a
    # noun (SUJETTE) and separates a participle from its noun (TRESSEE /
    # TRESSE). Collapse only these characteristic French endings; a broad
    # double-consonant rule would damage roots such as TRESS-.
    if family.endswith("TTE") and len(family) >= 6:
        family = family[:-2]
    elif family.endswith("SSE") and len(family) >= 6:
        family = family[:-1]
    for suffix in ("EES", "EE"):
        if family.endswith(suffix) and len(family) - len(suffix) >= 4:
            family = family[:-len(suffix)]
            break
    if family.endswith("E") and len(family) >= 5:
        candidate = family[:-1]
        if part_of_speech in {"adjective", "verb"} or candidate.endswith(("T", "D", "R", "V")):
            family = candidate
    if (
        part_of_speech != "verb"
        and family.endswith("S")
        and not family.endswith("SS")
        and len(family) >= 5
    ):
        family = family[:-1]
    return family


def family_key(answer: str) -> str:
    value = normalize(answer)
    index = lexical_family_index()
    lexical_lemma, part_of_speech = index.get(value, (value, ""))
    return family_key_from_parts(value, lexical_lemma, part_of_speech, index)


def emoji_asset(emoji: str) -> str:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" '
        'viewBox="0 0 96 96"><rect width="96" height="96" rx="18" fill="#fff"/>'
        f'<text x="48" y="66" text-anchor="middle" font-size="58">{escape(emoji)}</text></svg>'
    )
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def local_asset_data_uri(asset: str) -> str:
    """Embed a reviewed clue asset in the standalone owner-review page."""
    if not asset.startswith("/assets/"):
        raise ValueError(f"chemin d'image non pris en charge: {asset}")
    path = (ROOT / "public" / asset.removeprefix("/")).resolve()
    allowed_root = (ROOT / "public" / "assets" / "clues").resolve()
    if not path.is_relative_to(allowed_root) or not path.is_file():
        raise ValueError(f"image introuvable ou hors bibliothèque d'indices: {asset}")
    mime_by_suffix = {".svg": "image/svg+xml", ".png": "image/png"}
    mime = mime_by_suffix.get(path.suffix.lower())
    if mime is None:
        raise ValueError(f"format d'image non pris en charge: {asset}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def image_items(grid: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for item in grid.get("imageAnswers", []):
        if isinstance(item, str):
            answer = normalize(item)
            concept = answer.title()
            alt = concept
            emoji = EMOJI_BY_ANSWER.get(answer)
            asset = ""
            source = "MotMan editorial"
            license_name = "MotMan original"
        else:
            answer = normalize(str(item.get("answer", "")))
            concept = str(item.get("concept") or answer.title())
            alt = str(item.get("alt") or concept)
            emoji = str(item.get("emoji") or EMOJI_BY_ANSWER.get(answer, ""))
            asset = str(item.get("asset") or "")
            source = str(item.get("source") or "MotMan editorial")
            license_name = str(item.get("license") or "MotMan original")
        if not answer or not (emoji or asset):
            raise ValueError(f"{grid.get('id')}: visuel manquant pour l'image {answer}")
        result[answer] = {
            "answer": answer,
            "concept": concept,
            "alt": alt,
            "emoji": emoji,
            "sourceAsset": asset,
            "source": source,
            "license": license_name,
        }
    minimum_images = int(grid.get("minimumImages", 4))
    if not minimum_images <= len(result) <= 6:
        raise ValueError(
            f"{grid.get('id')}: {minimum_images} à 6 images requises, reçu {len(result)}"
        )
    return result


def definition_for(grid: dict, item: dict) -> str:
    definition = str(item.get("definition") or item.get("clue") or "").strip()
    if not definition and isinstance(grid.get("clues"), list):
        match = next(
            (clue for clue in grid["clues"] if clue.get("answer") == item.get("answer")),
            None,
        )
        definition = str((match or {}).get("clue") or "").strip()
    return definition


def build_grid(source: dict, sequence: int) -> dict:
    images = image_items(source)
    words = []
    for number, item in enumerate(source.get("answers", []), 1):
        if "slotIndex" in item:
            slot = source["rawSlots"][int(item["slotIndex"])]
        else:
            slot = next(
                raw_slot for raw_slot in source["rawSlots"]
                if raw_slot.get("slotId") == item.get("slotId")
            )
        answer = normalize(str(item["answer"]))
        definition = definition_for(source, item)
        image = images.get(answer)
        if image is None and (not definition or "?" in definition):
            raise ValueError(
                f"{source.get('id')}: définition absente ou corrompue pour {answer}: {definition!r}"
            )
        word = {
            "wordId": f"compact-7x8-review-{sequence:02d}:word:{number:02d}",
            "answer": answer,
            # Keep a textual fallback in staging so the editorial audit can
            # still validate the pair before a permanent image asset exists.
            "clue": image["alt"] if image else definition,
            "sourceClue": image["alt"] if image else definition,
            "definitionStatus": str(item.get("definitionStatus") or (
                "image-review" if image else "manually-reviewed"
            )),
            "editorialStatus": str(item.get("editorialStatus") or "owner-review-required"),
            "sourceType": str(item.get("sourceType") or (
                "image-concept" if image else "editorial-original"
            )),
            "sourceId": str(item.get("sourceId") or "motman-compact-7x8-20260721"),
            "sourceUrl": str(item.get("sourceUrl") or "internal://motman/editorial/compact-7x8"),
            "license": str(item.get("license") or "MotMan original"),
            "direction": slot["direction"],
            "arrow": "right" if slot["direction"] == "across" else "down",
            "clueCell": slot["clueCell"],
            "cells": slot["cells"],
            "conceptGroup": family_key(answer),
            "semanticConflicts": [],
        }
        if image:
            word["image"] = {
                "asset": (
                    local_asset_data_uri(image["sourceAsset"])
                    if image["sourceAsset"]
                    else emoji_asset(image["emoji"])
                ),
                "alt": image["alt"],
                "concept": image["concept"],
                "source": image["source"],
                "license": image["license"],
            }
            if image["emoji"]:
                word["image"]["emoji"] = image["emoji"]
            if image["sourceAsset"]:
                word["image"]["sourceAsset"] = image["sourceAsset"]
        for field in (
            "familiarityScore", "familiarityBand", "partOfSpeech",
            "languageStatus", "culturalStatus", "clueStyle", "imageStatus",
            "editorialReview",
        ):
            if field in item:
                word[field] = item[field]
        words.append(word)
    return {
        "id": f"compact-7x8-review-{sequence:02d}",
        "sourceGridId": source["id"],
        "sourceShapeId": source.get("sourceShapeId", ""),
        "columns": 7,
        "rows": 8,
        "clueCells": source["clueCells"],
        "words": words,
        "minimumImages": int(source.get("minimumImages", 4)),
        "publicationStatus": "owner-review-required",
        "catalogModified": False,
    }


def load_sources(paths: list[Path], include_ids: set[str]) -> list[dict]:
    sources = []
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        for grid in document.get("grids", []):
            if not include_ids or grid.get("id") in include_ids:
                sources.append(grid)
    return sources


def reference_answer_index(paths: list[Path]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    exact: dict[str, set[str]] = defaultdict(set)
    families: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        grids = document.get("grids")
        if not isinstance(grids, list):
            grids = [document.get("grid") or document]
        for grid in grids:
            grid_id = str(grid.get("id") or path.name)
            for item in grid.get("words") or grid.get("answers") or []:
                answer = normalize(str(item.get("answer", "")))
                if not answer:
                    continue
                exact[answer].add(grid_id)
                families[family_key(answer)].add(f"{grid_id}:{answer}")
    return exact, families


def add_decision_ui(page: str, grid_count: int) -> str:
    buttons = (
        '<div class="owner-decision">'
        '<button type="button" data-decision="accept">✅ Je valide</button>'
        '<button type="button" data-decision="reject">❌ Je refuse</button>'
        '<span class="decision-state">À décider</span></div>'
    )
    page = page.replace("</h2>", "</h2>" + buttons)
    summary = (
        '<section class="checkpoint"><b>À RELIRE — '
        f'{grid_count} grilles compactes 7×8</b><br>'
        'Aucune n’est publiée. Clique sur les définitions pour voir leur trajet, '
        'puis valide ou refuse chaque grille. '
        '<button id="export-decisions" type="button">Télécharger mes décisions</button>'
        '</section>'
    )
    css = """
    <style>
    .checkpoint{max-width:980px;margin:18px auto;background:#e9f7ef!important;border:2px solid #277a54}
    .checkpoint button,.owner-decision button{margin:8px 5px 0 0;padding:8px 12px;border:1px solid #555;border-radius:8px;background:#fff;font-weight:700;cursor:pointer}
    .owner-decision{display:flex;align-items:center;gap:8px;margin:8px 0 14px}.decision-state{font-weight:800}.owner-decision.accept .decision-state{color:#147443}.owner-decision.reject .decision-state{color:#a22222}
    </style>
    """
    script = """
    <script>
    (() => {
      const key = 'motman-compact-7x8-decisions-v1';
      const load = () => { try { return JSON.parse(localStorage.getItem(key) || '{}'); } catch { return {}; } };
      const decisions = load();
      const paint = section => {
        const value = decisions[section.dataset.gridId] || '';
        const box = section.querySelector('.owner-decision');
        box.classList.toggle('accept', value === 'accept'); box.classList.toggle('reject', value === 'reject');
        box.querySelector('.decision-state').textContent = value === 'accept' ? 'Validée' : value === 'reject' ? 'Refusée' : 'À décider';
      };
      document.querySelectorAll('.grid-review').forEach(section => {
        paint(section);
        section.querySelectorAll('[data-decision]').forEach(button => button.addEventListener('click', () => {
          decisions[section.dataset.gridId] = button.dataset.decision;
          localStorage.setItem(key, JSON.stringify(decisions)); paint(section);
        }));
      });
      document.querySelector('#export-decisions').addEventListener('click', () => {
        const blob = new Blob([JSON.stringify({version:1, decisions}, null, 2)], {type:'application/json'});
        const link = document.createElement('a'); link.href = URL.createObjectURL(blob);
        link.download = 'compact-7x8-owner-decisions.json'; link.click(); URL.revokeObjectURL(link.href);
      });
    })();
    </script>
    """
    return page.replace("</head>", css + "</head>").replace("</h1>", "</h1>" + summary, 1).replace("</body>", script + "</body>")


def render_playtest_html(reports: list[dict]) -> str:
    """Render a separate owner playtest without leaking answer letters.

    The editorial report intentionally contains solutions and provenance.  A
    playtest must not: even its HTML source receives copies with answers and
    solved letters removed.  Route highlighting remains available so the
    owner can judge whether each arrow is understandable.
    """
    sanitized = copy.deepcopy(reports)
    for report in sanitized:
        for cell in report.get("cells", []):
            if cell.get("kind") == "letter":
                cell["solution"] = ""
        for word in report.get("words", []):
            word["answer"] = ""
            if isinstance(word.get("image"), dict):
                word["clue"] = "Indice illustré"
                word["image"]["alt"] = "Indice illustré"
    page = render_topology_html(
        sanitized,
        title=f"MotMan — playtest sans solutions ({len(sanitized)} grilles)",
    )
    page = page.replace(
        "<b class='letter-value'>?</b><span class='step-number'></span>",
        "<input class='playtest-letter' maxlength='1' inputmode='text' "
        "autocomplete='off' autocapitalize='characters' aria-label='Lettre à saisir'>"
        "<span class='step-number'></span>",
    )
    # Keep the existing button in the DOM for the renderer's tiny script, but
    # make it unavailable: there are no solution values left to reveal.
    playtest_css = """
    <style>
    .solution-toggle,details,.grid-review>h3,.grid-review>ul{display:none!important}
    .playtest-letter{width:100%;height:100%;border:0;background:transparent;
      text-align:center;text-transform:uppercase;font:800 25px system-ui;outline:0}
    .playtest-letter:focus{background:#eef6ff;box-shadow:inset 0 0 0 3px #3374c6}
    .playtest-note{max-width:980px;margin:18px auto;background:#fff8dc!important;
      border:2px solid #b78215}
    </style>
    """
    note = (
        "<section class='playtest-note'><b>PLAYTEST — solutions absentes</b><br>"
        "Clique sur un indice pour voir son trajet, puis saisis les lettres. "
        "Cette page ne contient ni réponses ni tableau de correction.</section>"
    )
    return page.replace("</head>", playtest_css + "</head>").replace(
        "</h1>", "</h1>" + note, 1
    )


def main() -> None:
    args = parse_args()
    include_ids = set(args.include_id)
    sources = load_sources(args.input, include_ids)
    if len(sources) < args.limit:
        raise ValueError(f"{args.limit} grilles requises, seulement {len(sources)} disponibles")
    sources = sources[:args.limit]
    grids = [build_grid(source, index) for index, source in enumerate(sources, 1)]
    reference_exact, reference_families = reference_answer_index(args.reference)
    allowed_reference_repeats = {
        normalize(answer) for answer in args.allow_reference_repeat if normalize(answer)
    }
    allowed_reference_families = {
        family_key(answer) for answer in allowed_reference_repeats
    }
    allowed_internal_repeats = {
        normalize(answer) for answer in args.allow_internal_repeat if normalize(answer)
    }
    allowed_internal_families = {
        family_key(answer) for answer in allowed_internal_repeats
    }

    blacklist = json.loads((ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8"))
    rejected_answers = set(blacklist.get("rejectedAnswers", []))
    all_answers: dict[str, list[str]] = defaultdict(list)
    all_families: dict[str, list[tuple[str, str]]] = defaultdict(list)
    reports = []
    metrics = []
    for grid in grids:
        report = audit_grid_topology(
            grid, enforce_layout=False, topology_profile="pilot"
        )
        if not report["valid"]:
            raise ValueError(f"{grid['id']}: {report['errors']}")
        answers = [word["answer"] for word in grid["words"]]
        blocked = sorted(set(answers) & rejected_answers)
        if blocked:
            raise ValueError(f"{grid['id']}: blacklist {blocked}")
        for answer in answers:
            all_answers[answer].append(grid["id"])
            all_families[family_key(answer)].append((grid["id"], answer))
        letter_cells = [cell for cell in report["cells"] if cell["kind"] == "letter"]
        metrics.append({
            "gridId": grid["id"], "sourceGridId": grid["sourceGridId"],
            "answers": len(answers), "letterCells": len(letter_cells),
            "coveredLetterCells": sum(bool(cell["wordIds"]) for cell in letter_cells),
            "orphanLetters": sum(not cell["wordIds"] for cell in letter_cells),
            "orphanSegments": len(report["orphanSegments"]),
            "unusedDefinitionCells": sum(
                cell["kind"] == "clue" and not cell["wordIds"] for cell in report["cells"]
            ),
            "twoLetterAnswers": [answer for answer in answers if len(answer) == 2],
            "lengthProfile": dict(sorted(Counter(map(len, answers)).items())),
            "imageCount": sum(bool(word.get("image")) for word in grid["words"]),
        })
        reports.append(report)

    exact_repeats = {answer: ids for answer, ids in all_answers.items() if len(ids) > 1}
    family_repeats = {
        family: occurrences for family, occurrences in all_families.items()
        if len({answer for _grid_id, answer in occurrences}) > 1
    }
    forbidden_exact_repeats = {
        answer: ids for answer, ids in exact_repeats.items()
        if answer not in allowed_internal_repeats
    }
    forbidden_family_repeats = {
        family: occurrences for family, occurrences in family_repeats.items()
        if family not in allowed_internal_families
    }
    overused_allowed_repeats = {
        answer: ids for answer, ids in exact_repeats.items()
        if answer in allowed_internal_repeats and len(ids) > 2
    }
    if forbidden_exact_repeats:
        raise ValueError(f"Répétitions exactes : {forbidden_exact_repeats}")
    if forbidden_family_repeats:
        raise ValueError(f"Répétitions de familles : {forbidden_family_repeats}")
    if overused_allowed_repeats:
        raise ValueError(f"Charnières surutilisées : {overused_allowed_repeats}")
    reference_exact_repeats = {
        answer: sorted(reference_exact[answer])
        for answer in all_answers
        if answer in reference_exact and answer not in allowed_reference_repeats
    }
    reference_family_repeats = {
        family: {
            "new": all_families[family],
            "reference": sorted(reference_families[family]),
        }
        for family in all_families
        if family in reference_families and family not in allowed_reference_families
    }
    freshness_warnings = []
    if reference_exact_repeats:
        freshness_warnings.append({
            "reason": "referenceExactRepeats",
            "answers": reference_exact_repeats,
        })
    if reference_family_repeats:
        freshness_warnings.append({
            "reason": "referenceFamilyRepeats",
            "families": reference_family_repeats,
        })

    document = {
        "version": 1, "kind": "compact-7x8-owner-review-batch",
        "catalogModified": False, "publicationEligible": False,
        "allowedReferenceRepeats": sorted(allowed_reference_repeats),
        "allowedInternalRepeats": sorted(allowed_internal_repeats),
        "grids": grids, "metrics": metrics,
        "freshnessWarnings": freshness_warnings,
    }
    audit = {
        "version": 1, "valid": True, "gridCount": len(grids),
        "exactRepeats": exact_repeats, "familyRepeats": family_repeats,
        "referenceExactRepeats": reference_exact_repeats,
        "referenceFamilyRepeats": reference_family_repeats,
        "warnings": freshness_warnings,
        "allowedReferenceRepeats": sorted(allowed_reference_repeats),
        "allowedInternalRepeats": sorted(allowed_internal_repeats),
        "metrics": metrics, "grids": reports,
    }
    args.staging.parent.mkdir(parents=True, exist_ok=True)
    args.staging.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    page = render_topology_html(
        reports,
        title=f"MotMan — {len(grids)} grilles compactes 7×8 à relire",
    )
    args.html.parent.mkdir(parents=True, exist_ok=True)
    args.html.write_text(add_decision_ui(page, len(grids)), encoding="utf-8")
    if args.playtest_html:
        args.playtest_html.parent.mkdir(parents=True, exist_ok=True)
        args.playtest_html.write_text(render_playtest_html(reports), encoding="utf-8")
    print(json.dumps({
        "complete": True,
        "grids": len(grids),
        "html": str(args.html),
        "playtestHtml": str(args.playtest_html) if args.playtest_html else None,
        "metrics": metrics,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
