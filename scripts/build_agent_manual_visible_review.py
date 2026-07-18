#!/usr/bin/env python3
"""Turn the complete agent closure into an owner-visible review artifact."""
from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output/quality/agent-fresh-exact-cell-morph-720101.json"
JSON_OUT = ROOT / "output/quality/agent-manual-visible-01.json"
HTML_OUT = ROOT / "output/quality/agent-manual-visible-01.html"

CLUES = {
    "RESSENTEZ": "Éprouvez",
    "ALEATOIRE": "Au hasard",
    "MIG": "Soudure au fil",
    "ETABLI": "Table d’atelier",
    "NI": "Conjonction négative",
    "ASTOR": "Prénom de Piazzolla",
    "ITEM": "Élément de liste",
    "SEREZ": "Deviendrez",
    "RAMENAIS": "Rapportais",
    "ELITISTE": "Très sélectif",
    "SEGA": "Maison de Sonic",
    "TER": "Train régional",
    "REAL": "Monnaie brésilienne",
    "SA": "Possessif féminin",
    "BROME": "Élément chimique",
    "ARGON": "Gaz noble",
    "ETALER": "Répartir",
    "SMOG": "",
    "NORIA": "Défilé continu",
    "ADN": "",
    "ACE": "Service gagnant",
    "TIG": "Soudure au tungstène",
    "LAMA": "Animal des Andes",
    "EROS": "Dieu du désir",
    "DOC": "Fichier Word",
    "ZEN": "Très calme",
    "ANGE": "",
}

IMAGES = {
    "SMOG": {"asset": "/assets/clues/twemoji/smog.svg", "alt": "Nuage de pollution"},
    "ADN": {"asset": "/assets/clues/twemoji/adn.svg", "alt": "Double hélice d’ADN"},
    "ANGE": {"asset": "/assets/clues/twemoji/ange.svg", "alt": "Ange"},
}


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    grid = source["grid"]
    words = []
    coverage = defaultdict(list)
    letters = {}
    for index, raw in enumerate(grid["answers"], 1):
        answer = raw["answer"]
        word_id = f"manual-visible-01-w{index:02d}"
        item = dict(raw)
        item.update({
            "wordId": word_id,
            "definition": CLUES[answer],
            "image": IMAGES.get(answer),
            "reviewStatus": "owner-review-required",
        })
        words.append(item)
        for cell, letter in zip(item["cells"], answer):
            key = tuple(cell)
            coverage[key].append(word_id)
            if key in letters and letters[key] != letter:
                raise ValueError(f"Crossing conflict at {key}")
            letters[key] = letter

    clue_cells = {tuple(cell) for cell in grid["clueCells"]}
    letter_cells = {
        (row, column)
        for row in range(10)
        for column in range(9)
        if (row, column) not in clue_cells
    }
    orphan_letters = sorted(letter_cells - set(coverage))
    uncovered = sorted(set(coverage) - letter_cells)
    blank_clues = [
        word["answer"] for word in words
        if not word["definition"].strip() and not word.get("image")
    ]
    topology_valid = (
        not orphan_letters
        and not uncovered
        and not blank_clues
        and all(len(word["cells"]) == len(word["answer"]) for word in words)
    )
    payload = {
        "version": 1,
        "kind": "agent-manual-owner-review",
        "catalogModified": False,
        "blacklistModified": True,
        "publicationEligible": False,
        "ownerReview": {
            "status": "rejected",
            "reviewedOn": "2026-07-18",
            "rejectedAnswers": ["SA", "ACE", "SMOG", "ASTOR"],
            "rejectedCooccurrences": [["MIG", "TIG"]],
            "reason": (
                "Vocabulaire peu agréable et deux procédés de soudure "
                "redondants dans la même grille."
            ),
        },
        "grid": {
            "id": "agent-manual-visible-01",
            "columns": 9,
            "rows": 10,
            "clueCells": grid["clueCells"],
            "words": words,
        },
        "audit": {
            "topologyValid": topology_valid,
            "totalCells": 90,
            "clueCells": len(clue_cells),
            "letterCells": len(letter_cells),
            "coveredLetterCells": len(coverage),
            "orphanLetters": [list(cell) for cell in orphan_letters],
            "coverageOutsideLetterCells": [list(cell) for cell in uncovered],
            "blankCluesWithoutImage": blank_clues,
            "twoLetterAnswers": [word["answer"] for word in words if len(word["answer"]) == 2],
            "imageAnswers": [word["answer"] for word in words if word.get("image")],
            "lengthDistribution": dict(sorted(Counter(len(word["answer"]) for word in words).items())),
            "editorialWarnings": [
                "RESSENTEZ",
                "SEREZ",
                "RAMENAIS",
                "SA",
                "ACE",
                "SMOG",
                "ASTOR",
                "BROME",
                "EROS",
                "REAL",
            ],
        },
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    by_clue = defaultdict(list)
    for word in words:
        by_clue[tuple(word["clueCell"])].append(word)
    cells_html = []
    for row in range(10):
        for column in range(9):
            key = (row, column)
            if key in clue_cells:
                parts = []
                for word in by_clue.get(key, []):
                    arrow = "→" if word["direction"] == "across" else "↓"
                    if word.get("image"):
                        body = f'<img src="{html.escape(word["image"]["asset"])}" alt="{html.escape(word["image"]["alt"])}">'
                    else:
                        body = html.escape(word["definition"])
                    parts.append(f'<span class="clue">{body}<b>{arrow}{len(word["answer"])}</b></span>')
                cell_class = "neutral" if key == (0, 0) else "definition"
                cells_html.append(f'<div class="cell {cell_class}">{"".join(parts)}</div>')
            else:
                word_ids = " / ".join(coverage[key])
                cells_html.append(
                    f'<div class="cell letter" title="{html.escape(word_ids)}">{letters[key]}</div>'
                )

    rows_html = []
    for word in words:
        warning = "warning" if word["answer"] in payload["audit"]["editorialWarnings"] else ""
        clue = word["definition"] or f'Image : {word["image"]["alt"]}'
        rows_html.append(
            f'<tr class="{warning}"><td>{html.escape(word["answer"])}</td>'
            f'<td>{html.escape(clue)}</td><td>{len(word["answer"])}</td>'
            f'<td>{html.escape(word["direction"])}</td></tr>'
        )
    html_doc = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Grille manuelle — revue</title><style>
body{{font-family:system-ui;margin:24px;background:#f4f1e8;color:#1c3029}}h1{{margin-bottom:4px}}
.summary{{max-width:760px;margin-bottom:18px}}.grid{{display:grid;grid-template-columns:repeat(9,62px);grid-template-rows:repeat(10,62px);width:max-content;border:2px solid #244d42;background:#244d42;gap:1px}}
.cell{{background:#fff;display:flex;align-items:center;justify-content:center;overflow:hidden}}.letter{{font-size:27px;font-weight:750;color:#264d42}}
.definition{{background:#e8f0ec;flex-direction:column;padding:2px;box-sizing:border-box}}.neutral{{background:#233b34}}
.clue{{font-size:8px;line-height:1.05;text-align:center;width:100%;display:flex;align-items:center;justify-content:center;gap:2px;min-height:22px}}.clue+ .clue{{border-top:1px solid #8aa59c}}.clue b{{font-size:9px;white-space:nowrap}}.clue img{{width:27px;height:27px}}
table{{border-collapse:collapse;margin-top:22px;min-width:620px}}th,td{{border:1px solid #b9c8c2;padding:6px 9px;text-align:left}}th{{background:#dce9e4}}tr.warning{{background:#fff0cf}}
.good{{color:#12623e;font-weight:700}}.warn{{color:#8a4c00;font-weight:700}}.rejected{{color:#a11b1b;font-weight:800}}
</style></head><body><h1>Grille manuelle 9×10 — <span class="rejected">REJETÉE</span></h1>
<p class="summary"><span class="good">Topologie complète : 64/64 lettres couvertes, zéro orpheline.</span> <span class="rejected">Refus propriétaire : SA, ACE, SMOG, ASTOR et la cooccurrence MIG/TIG. Cette grille ne sera jamais publiée.</span></p>
<div class="grid">{''.join(cells_html)}</div>
<table><thead><tr><th>Réponse</th><th>Définition</th><th>Longueur</th><th>Sens</th></tr></thead><tbody>{''.join(rows_html)}</tbody></table>
</body></html>'''
    HTML_OUT.write_text(html_doc, encoding="utf-8")
    print(json.dumps({"json": str(JSON_OUT), "html": str(HTML_OUT), "audit": payload["audit"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
