#!/usr/bin/env python3
"""Render the editorial 100 -> 10 checkpoint for definition-free fills."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_large_lexical_batch import select_diverse_shortlist  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


def conflict_map() -> dict[str, set[str]]:
    document = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    result: dict[str, set[str]] = {}
    for rule in document.get("rejectedCooccurrences", []):
        answers = {str(answer).upper() for answer in rule.get("answers", [])}
        for answer in answers:
            result.setdefault(answer, set()).update(answers - {answer})
    return result


def candidate_conflicts(candidate: dict, conflicts: dict[str, set[str]]) -> list[list[str]]:
    answers = {item["answer"] for item in candidate["answers"]}
    pairs = {
        tuple(sorted((answer, other)))
        for answer in answers
        for other in conflicts.get(answer, set()) & answers
    }
    return [list(pair) for pair in sorted(pairs)]


def image_answers() -> set[str]:
    path = ROOT / "src/data/crossword.images-reviewed.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(entry.get("answer", "")).upper()
        for entry in document.get("entries", [])
        if isinstance(entry.get("image"), dict)
    }


def fill_letters(candidate: dict) -> dict[tuple[int, int], str]:
    result: dict[tuple[int, int], str] = {}
    slots = candidate["rawSlots"]
    for item in candidate["answers"]:
        answer = item["answer"]
        slot = slots[int(item["slotIndex"])]
        for cell, letter in zip(slot["cells"], answer):
            key = tuple(cell)
            if key in result and result[key] != letter:
                raise ValueError(f"Crossing conflict in {candidate['id']} at {key}")
            result[key] = letter
    return result


def render_grid(candidate: dict) -> str:
    clues = {tuple(cell) for cell in candidate["clueCells"]}
    letters = fill_letters(candidate)
    cells = []
    for row in range(10):
        for column in range(9):
            cell = (row, column)
            if cell == (0, 0):
                cells.append('<div class="cell neutral">∅</div>')
            elif cell in clues:
                arrows = []
                for slot in candidate["rawSlots"]:
                    if tuple(slot["clueCell"]) == cell:
                        arrows.append("→" if slot["direction"] == "across" else "↓")
                cells.append(f'<div class="cell clue">{" ".join(arrows)}</div>')
            else:
                cells.append(f'<div class="cell letter">{escape(letters.get(cell, "?"))}</div>')
    return '<div class="grid">' + "".join(cells) + "</div>"


def render_card(candidate: dict, images: set[str]) -> str:
    quality = candidate["quality"]
    answer_rows = []
    for item in candidate["answers"]:
        answer = item["answer"]
        badges = []
        if answer in images:
            badges.append('<span class="image">image</span>')
        if item.get("formType") == "inflected":
            badges.append('<span class="inflected">forme fléchie</span>')
        answer_rows.append(
            "<tr>"
            f"<td>{int(item['slotIndex']) + 1}</td>"
            f"<td><b>{escape(answer)}</b></td>"
            f"<td>{float(item['constructorScore']):.1f}</td>"
            f"<td>{escape(str(item.get('lemma', answer)))}</td>"
            f"<td>{' '.join(badges)}</td>"
            "</tr>"
        )
    image_count = sum(item["answer"] in images for item in candidate["answers"])
    diversity = candidate.get("diversity", {})
    return f"""
    <article>
      <h2>#{candidate['shortlistRank']} — {escape(candidate['sourceShapeId'])}</h2>
      <p class="status">Structure fermée, non publiable tant que les définitions et images ne sont pas relues.</p>
      <div class="metrics">
        <span>score min <b>{quality['minimumScore']}</b></span>
        <span>score moyen <b>{quality['averageScore']}</b></span>
        <span>2 lettres <b>{quality['twoLetterAnswers']}</b></span>
        <span>images possibles <b>{image_count}</b></span>
        <span>lemmes reprises du lot <b>{diversity.get('reusedLemmasWithEarlierShortlist', 0)}</b></span>
      </div>
      <div class="card-body">{render_grid(candidate)}
        <div class="table-wrap"><table><thead><tr><th>#</th><th>Réponse</th><th>Score</th><th>Lemme</th><th>Contrôle</th></tr></thead>
        <tbody>{''.join(answer_rows)}</tbody></table></div>
      </div>
    </article>"""


def main() -> int:
    args = parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8"))
    conflicts = conflict_map()
    rejected = []
    eligible = []
    for candidate in document.get("rawCandidates", []):
        pairs = candidate_conflicts(candidate, conflicts)
        if pairs:
            rejected.append({"id": candidate["id"], "conflicts": pairs})
        else:
            eligible.append(candidate)
    selected = select_diverse_shortlist(eligible, args.limit)
    for rank, candidate in enumerate(selected, 1):
        candidate["shortlistRank"] = rank

    images = image_answers()
    shape_count = len({candidate["sourceShapeId"] for candidate in selected})
    answer_counts = Counter(
        item["answer"] for candidate in selected for item in candidate["answers"]
    )
    repeated = {answer: count for answer, count in answer_counts.items() if count > 1}
    cards = "".join(render_card(candidate, images) for candidate in selected)
    payload = {
        "input": str(args.input),
        "rawCandidates": len(document.get("rawCandidates", [])),
        "rejectedByCooccurrence": rejected,
        "selected": [candidate["id"] for candidate in selected],
        "selectedShapes": shape_count,
        "repeatedExactAnswers": dict(sorted(repeated.items())),
    }
    html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>100 fermetures lexicales → 10 à relire</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f0e8;color:#173b35;font:15px/1.4 system-ui,sans-serif}}main{{max-width:1450px;margin:auto;padding:24px}}h1,h2{{color:#174d43}}.lead,.status{{background:#fff8d9;border-left:5px solid #d5a323;padding:10px 12px}}.summary{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}}.summary span,.metrics span{{background:#e4efe9;border-radius:999px;padding:6px 10px}}article{{background:#fffdf8;border:1px solid #bdccc5;border-radius:14px;padding:16px;margin:18px 0}}.metrics{{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}}.card-body{{display:grid;grid-template-columns:minmax(360px,520px) 1fr;gap:18px;align-items:start}}.grid{{display:grid;grid-template-columns:repeat(9,1fr);aspect-ratio:9/10;border:2px solid #315b52;background:white}}.cell{{border:1px solid #aab7b1;display:grid;place-items:center;min-width:0;font-weight:750}}.letter{{font-size:clamp(15px,2vw,26px)}}.clue{{background:#dfece6;color:#176050;font-size:14px}}.neutral{{background:#1f2825;color:white;font-size:22px}}.table-wrap{{max-height:590px;overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border-bottom:1px solid #d9e1dd;padding:6px;text-align:left}}th{{position:sticky;top:0;background:#e7f0eb}}.image{{background:#dff3ff;color:#075b7a;padding:2px 5px;border-radius:5px}}.inflected{{background:#fff0ca;color:#785000;padding:2px 5px;border-radius:5px}}code{{font-size:12px}}@media(max-width:850px){{.card-body{{grid-template-columns:1fr}}}}
</style></head><body><main><h1>Grande base lexicale : 100 fermetures → 10 à relire</h1>
<p class="lead"><b>Aucune définition n’a servi au placement.</b> Cette page montre les mots avant rédaction des indices. Une grille reste rejetée dès qu’un seul mot est incompréhensible.</p>
<div class="summary"><span>100 brutes</span><span>{len(rejected)} rejetées automatiquement par cooccurrence</span><span>{len(selected)} retenues pour lecture</span><span>{shape_count} silhouettes</span><span>{len(repeated)} réponses exactes répétées dans les 10</span></div>
{cards}<details><summary>Rapport machine</summary><pre>{escape(json.dumps(payload, ensure_ascii=False, indent=2))}</pre></details>
</main></body></html>"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
