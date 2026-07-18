"""Audit exact and lexical-family answer repetition in the playable catalog."""
from __future__ import annotations

import json
from collections import defaultdict
from html import escape
from itertools import combinations
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "src/data/grid.catalog.json"
EDITORIAL = ROOT / "src/data/editorial.blacklist.json"
JSON_OUT = ROOT / "output/quality/active-answer-repetition-audit.json"
HTML_OUT = ROOT / "output/quality/active-answer-repetition-audit.html"

# These look like number variants but are different answers in the active catalog.
# Their clues were checked before excluding them from lexical-family grouping.
NON_LEXICAL_SUFFIX_PAIRS = {
    ("COTE", "COTES"),  # Valeur boursière / Bords marins
    ("DO", "DOS"),      # Note musicale / Partie arrière
    ("ERRE", "ERRES"),  # Élan du navire / Vagabondes
    ("FIL", "FILS"),    # Fibre / Descendant masculin
    ("MOI", "MOIS"),    # Ego / Douzième d'année
    ("PAN", "PANS"),    # Bruit sec / Parties de mur
    ("PRE", "PRES"),    # Prairie / À proximité
}
SHORT_PLURAL_BASES = {"AN", "IF"}


def is_lexical_number_pair(left: str, right: str) -> bool:
    """Return True when two active answers are number variants of one lexeme."""
    singular, plural = sorted((left, right), key=lambda value: (len(value), value))
    if (singular, plural) in NON_LEXICAL_SUFFIX_PAIRS:
        return False
    if plural == singular + "S":
        return len(singular) >= 3 or singular in SHORT_PLURAL_BASES
    if singular.endswith("AL") and plural == singular[:-2] + "AUX":
        return True
    if singular.endswith(("EAU", "EU")) and plural == singular + "X":
        return True
    return False


def build_lexical_families(forms: list[str]) -> tuple[dict[str, str], list[list[str]]]:
    """Build answer-to-concept mapping and multi-form lexical families."""
    parent = {form: form for form in forms}

    def find(form: str) -> str:
        while parent[form] != form:
            parent[form] = parent[parent[form]]
            form = parent[form]
        return form

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left, right in combinations(forms, 2):
        if is_lexical_number_pair(left, right):
            union(left, right)

    components: dict[str, list[str]] = defaultdict(list)
    for form in forms:
        components[find(form)].append(form)

    families = [
        sorted(items, key=lambda value: (len(value), value))
        for items in components.values()
        if len(items) > 1
    ]
    families.sort(key=lambda items: (items[0], items))

    concept_by_answer: dict[str, str] = {}
    for items in components.values():
        canonical = min(items, key=lambda value: (len(value), value))
        for item in items:
            concept_by_answer[item] = canonical
    return concept_by_answer, families


def main() -> None:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    editorial = json.loads(EDITORIAL.read_text(encoding="utf-8"))
    quarantined = set(editorial.get("quarantinedGridIds", []))
    cooldown = {
        item["answer"]: item for item in editorial.get("rotationCooldownAnswers", [])
    }
    grids = [
        grid for grid in catalog.get("grids", [])
        if grid.get("id") not in quarantined
    ]

    occurrences: dict[str, list[dict]] = defaultdict(list)
    answers_by_grid: dict[str, set[str]] = {}
    for grid in grids:
        grid_answers = set()
        for word in grid.get("words", []):
            answer = word["answer"]
            grid_answers.add(answer)
            occurrences[answer].append({
                "gridId": grid["id"],
                "clue": word.get("clue", ""),
                "image": bool(word.get("image")),
                "wordId": word.get("wordId"),
            })
        answers_by_grid[grid["id"]] = grid_answers

    repeated_exact = []
    for answer, uses in occurrences.items():
        if len(uses) < 2:
            continue
        repeated_exact.append({
            "answer": answer,
            "uses": len(uses),
            "excessUses": len(uses) - 1,
            "cooldown": answer in cooldown,
            "occurrences": sorted(uses, key=lambda item: item["gridId"]),
            "distinctClues": sorted({
                item["clue"] or "[image]" for item in uses
            }),
        })
    repeated_exact.sort(key=lambda item: (-item["uses"], item["answer"]))

    forms = sorted(occurrences)
    concept_by_answer, lexical_families = build_lexical_families(forms)
    forms_by_concept: dict[str, set[str]] = defaultdict(set)
    concept_occurrences: dict[str, list[dict]] = defaultdict(list)
    for answer, uses in occurrences.items():
        concept = concept_by_answer[answer]
        forms_by_concept[concept].add(answer)
        concept_occurrences[concept].extend(
            {**use, "answer": answer} for use in uses
        )

    def concept_label(concept: str) -> str:
        return " / ".join(sorted(
            forms_by_concept[concept], key=lambda value: (len(value), value)
        ))

    repeated_concepts = []
    for concept, uses in concept_occurrences.items():
        if len(uses) < 2:
            continue
        concept_forms = sorted(
            forms_by_concept[concept], key=lambda value: (len(value), value)
        )
        repeated_concepts.append({
            "concept": concept,
            "label": concept_label(concept),
            "forms": concept_forms,
            "uses": len(uses),
            "excessUses": len(uses) - 1,
            "cooldown": any(form in cooldown for form in concept_forms),
            "occurrences": sorted(
                uses, key=lambda item: (item["gridId"], item["answer"])
            ),
            "distinctClues": sorted({
                item["clue"] or "[image]" for item in uses
            }),
        })
    repeated_concepts.sort(key=lambda item: (-item["uses"], item["label"]))

    concepts_by_grid = {
        grid_id: {concept_by_answer[answer] for answer in answers}
        for grid_id, answers in answers_by_grid.items()
    }
    pair_overlaps = []
    for left, right in combinations(grids, 2):
        common = sorted(
            concepts_by_grid[left["id"]] & concepts_by_grid[right["id"]],
            key=concept_label,
        )
        if common:
            labels = [concept_label(concept) for concept in common]
            pair_overlaps.append({
                "leftGridId": left["id"],
                "rightGridId": right["id"],
                "sharedConceptCount": len(common),
                "answers": labels,
            })
    pair_overlaps.sort(key=lambda item: (
        -item["sharedConceptCount"], item["leftGridId"], item["rightGridId"]
    ))

    lexical_family_rows = []
    for family in lexical_families:
        concept = concept_by_answer[family[0]]
        lexical_family_rows.append({
            "concept": concept,
            "forms": family,
            "totalUses": len(concept_occurrences[concept]),
            "occurrences": {
                form: sorted(item["gridId"] for item in occurrences[form])
                for form in family
            },
        })
    lexical_family_rows.sort(
        key=lambda item: (-item["totalUses"], item["forms"])
    )

    concept_grid_ids: dict[str, set[str]] = defaultdict(set)
    for grid_id, concepts in concepts_by_grid.items():
        for concept in concepts:
            concept_grid_ids[concept].add(grid_id)

    per_grid = []
    for grid in grids:
        answers = sorted(answers_by_grid[grid["id"]])
        repeated_answer_forms = [
            answer for answer in answers
            if len(concept_grid_ids[concept_by_answer[answer]]) > 1
        ]
        repeated_labels = sorted({
            concept_label(concept_by_answer[answer])
            for answer in repeated_answer_forms
        })
        overlaps = [
            item for item in pair_overlaps
            if grid["id"] in {item["leftGridId"], item["rightGridId"]}
        ]
        per_grid.append({
            "gridId": grid["id"],
            "answers": len(answers),
            "answersRepeatedElsewhere": len(repeated_answer_forms),
            "repeatShare": round(
                len(repeated_answer_forms) / max(1, len(answers)), 3
            ),
            "repeatedAnswers": repeated_answer_forms,
            "repeatedConcepts": repeated_labels,
            "maximumOverlapWithOneGrid": max(
                (item["sharedConceptCount"] for item in overlaps), default=0
            ),
        })
    per_grid.sort(key=lambda item: (-item["repeatShare"], item["gridId"]))

    total_slots = sum(len(grid.get("words", [])) for grid in grids)
    unique_exact_answers = len(occurrences)
    unique_concepts = len(concept_occurrences)
    exact_excess = total_slots - unique_exact_answers
    concept_excess = total_slots - unique_concepts
    metrics = {
        "catalogVersion": catalog.get("version"),
        "playableGrids": len(grids),
        "quarantinedStoredGrids": len(catalog.get("grids", [])) - len(grids),
        "answerSlots": total_slots,
        "uniqueExactAnswers": unique_exact_answers,
        "uniqueAnswerConcepts": unique_concepts,
        "exactRepetitionExcessSlots": exact_excess,
        "exactRepetitionExcessRate": round(exact_excess / max(1, total_slots), 3),
        "conceptRepetitionExcessSlots": concept_excess,
        "conceptRepetitionExcessRate": round(concept_excess / max(1, total_slots), 3),
        "conceptsUsedAtLeastTwice": len(repeated_concepts),
        "conceptsUsedAtLeastThreeTimes": sum(
            item["uses"] >= 3 for item in repeated_concepts
        ),
        "conceptsUsedAtLeastFourTimes": sum(
            item["uses"] >= 4 for item in repeated_concepts
        ),
        "maximumConceptUse": max(
            (len(items) for items in concept_occurrences.values()), default=0
        ),
        "gridPairsWithAnyOverlap": len(pair_overlaps),
        "gridPairsWithAtLeastFiveSharedConcepts": sum(
            item["sharedConceptCount"] >= 5 for item in pair_overlaps
        ),
        "lexicalNumberFamilies": len(lexical_family_rows),
    }
    document = {
        "version": 2,
        "kind": "active-catalog-answer-repetition-audit",
        "metrics": metrics,
        "repeatedAnswerConcepts": repeated_concepts,
        "repeatedExactAnswers": repeated_exact,
        "lexicalNumberFamilies": lexical_family_rows,
        "highestGridPairOverlaps": pair_overlaps,
        "perGrid": per_grid,
    }
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    concept_rows = []
    for item in repeated_concepts:
        grids_text = "<br>".join(
            f'<code>{escape(use["gridId"])}</code> — '
            f'<b>{escape(use["answer"])}</b> : '
            f'{escape(use["clue"] or "[image]")}'
            for use in item["occurrences"]
        )
        concept_rows.append(
            f'<tr><td><b>{escape(item["label"])}</b></td><td>{item["uses"]}</td>'
            f'<td>{"oui" if item["cooldown"] else "non"}</td><td>{grids_text}</td></tr>'
        )
    exact_rows = []
    for item in repeated_exact:
        grids_text = "<br>".join(
            f'<code>{escape(use["gridId"])}</code> — '
            f'{escape(use["clue"] or "[image]")}'
            for use in item["occurrences"]
        )
        exact_rows.append(
            f'<tr><td><b>{escape(item["answer"])}</b></td><td>{item["uses"]}</td>'
            f'<td>{"oui" if item["cooldown"] else "non"}</td><td>{grids_text}</td></tr>'
        )
    pair_rows = "".join(
        f'<tr><td><code>{escape(item["leftGridId"])}</code></td>'
        f'<td><code>{escape(item["rightGridId"])}</code></td>'
        f'<td>{item["sharedConceptCount"]}</td>'
        f'<td>{escape(", ".join(item["answers"]))}</td></tr>'
        for item in pair_overlaps[:40]
    )
    family_rows = "".join(
        f'<tr><td><b>{escape(" / ".join(item["forms"]))}</b></td>'
        f'<td>{item["totalUses"]}</td>'
        f'<td>{escape(json.dumps(item["occurrences"], ensure_ascii=False))}</td></tr>'
        for item in lexical_family_rows
    ) or '<tr><td colspan="3">Aucune famille détectée.</td></tr>'
    grid_rows = "".join(
        f'<tr><td><code>{escape(item["gridId"])}</code></td><td>{item["answers"]}</td>'
        f'<td>{item["answersRepeatedElsewhere"]}</td><td>{item["repeatShare"]:.1%}</td>'
        f'<td>{item["maximumOverlapWithOneGrid"]}</td></tr>'
        for item in per_grid
    )
    HTML_OUT.write_text(f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MotMan — audit des répétitions</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#f4f1e8;color:#173b35;font-family:system-ui,sans-serif}}main{{max-width:1250px;margin:auto;padding:24px}}h1,h2{{color:#174d43}}.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}}.metric{{background:#fff;border:1px solid #b9ccc3;border-radius:10px;padding:12px}}.metric b{{display:block;font-size:25px}}section{{background:#fffdf8;border:1px solid #c9d5cf;border-radius:14px;padding:16px;margin:16px 0;overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border-bottom:1px solid #dce5e0;padding:8px;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#e6f0eb}}code{{font-size:11px}}.note{{background:#fff3cd;border-left:5px solid #d39b22;padding:10px 12px}}</style></head>
<body><main><h1>Répétitions dans les grilles jouables</h1>
<p class="note"><b>Règle :</b> les formes d'une même réponse sont regroupées. AME et AMES comptent donc comme un seul concept répété. Les homographes sans rapport, comme DO et DOS, restent séparés.</p>
<div class="summary">
<div class="metric"><b>{metrics['playableGrids']}</b>grilles jouables</div>
<div class="metric"><b>{metrics['answerSlots']}</b>emplacements-réponses</div>
<div class="metric"><b>{metrics['uniqueAnswerConcepts']}</b>réponses conceptuelles</div>
<div class="metric"><b>{metrics['conceptRepetitionExcessRate']:.1%}</b>excès conceptuel</div>
<div class="metric"><b>{metrics['conceptsUsedAtLeastThreeTimes']}</b>réponses utilisées 3× ou plus</div>
<div class="metric"><b>{metrics['maximumConceptUse']}×</b>maximum pour une réponse</div></div>
<section><h2>Liste principale : réponses regroupées par concept</h2><table><thead><tr><th>Réponse</th><th>Usages</th><th>Cooldown</th><th>Formes, grilles et indices</th></tr></thead><tbody>{''.join(concept_rows)}</tbody></table></section>
<section><h2>Paires de grilles les plus proches</h2><table><thead><tr><th>Grille A</th><th>Grille B</th><th>Réponses communes</th><th>Liste</th></tr></thead><tbody>{pair_rows}</tbody></table></section>
<section><h2>Variantes lexicales regroupées</h2><table><thead><tr><th>Formes</th><th>Usages cumulés</th><th>Grilles</th></tr></thead><tbody>{family_rows}</tbody></table></section>
<section><h2>Charge de répétition par grille</h2><table><thead><tr><th>Grille</th><th>Réponses</th><th>Répétées ailleurs</th><th>Part</th><th>Chevauchement max</th></tr></thead><tbody>{grid_rows}</tbody></table></section>
<section><h2>Détail secondaire : orthographes strictement identiques</h2><table><thead><tr><th>Forme exacte</th><th>Usages</th><th>Cooldown</th><th>Grilles et indices</th></tr></thead><tbody>{''.join(exact_rows)}</tbody></table></section>
</main></body></html>""", encoding="utf-8")
    print(json.dumps({
        "status": "audited",
        "json": str(JSON_OUT),
        "html": str(HTML_OUT),
        "metrics": metrics,
        "topRepeatedConcepts": [
            {"answer": item["label"], "uses": item["uses"]}
            for item in repeated_concepts[:20]
        ],
        "topGridPairs": pair_overlaps[:10],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
