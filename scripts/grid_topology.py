"""Strict rectangular arrowword topology validation and review rendering.

This module deliberately knows nothing about vocabulary quality.  Its contract is
geometric: every visible run is declared, every arrow starts the declared path,
and every letter can be traced back to one or two valid word identifiers.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from typing import Iterable

from editorial_quality import editorial_errors, grid_semantic_errors


LEGACY_SIZE = 9
SUPPORTED_DIMENSIONS = {(9, 9), (9, 10)}  # (columns, rows)
ROOT = Path(__file__).resolve().parents[1]
DIRECTIONS = {"across": (0, 1), "down": (1, 0)}
ARROW_STARTS = {
    ("across", "right"): (0, -1),
    ("across", "downright"): (-1, 0),
    ("down", "down"): (-1, 0),
    ("down", "rightdown"): (0, -1),
}


def _coordinate(value: object) -> tuple[int, int] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    row, col = value
    if not isinstance(row, int) or not isinstance(col, int):
        return None
    return row, col


def _inside(cell: tuple[int, int], rows: int, columns: int) -> bool:
    return 0 <= cell[0] < rows and 0 <= cell[1] < columns


def _maximal_runs(
    letter_cells: set[tuple[int, int]], rows: int, columns: int, direction: str
) -> Iterable[tuple[tuple[int, int], ...]]:
    dr, dc = DIRECTIONS[direction]
    for row in range(rows):
        for col in range(columns):
            cell = (row, col)
            previous = (row - dr, col - dc)
            if cell not in letter_cells or previous in letter_cells:
                continue
            run = []
            current = cell
            while current in letter_cells:
                run.append(current)
                current = (current[0] + dr, current[1] + dc)
            yield tuple(run)


def audit_grid_topology(
    grid: dict, *, require_word_ids: bool = True, enforce_layout: bool = True
) -> dict:
    """Return a serialisable, cell-level topology report for one catalog grid."""
    grid_id = str(grid.get("id", "<sans-id>"))
    legacy_size = grid.get("size")
    columns = grid.get("columns", legacy_size)
    rows = grid.get("rows", legacy_size)
    errors: list[dict] = []

    def reject(code: str, message: str, **details: object) -> None:
        item = {"code": code, "message": message}
        item.update(details)
        errors.append(item)

    if not isinstance(columns, int) or not isinstance(rows, int):
        reject("invalid_dimensions", "rows et columns doivent être des entiers")
        columns = rows = LEGACY_SIZE
    elif (columns, rows) not in SUPPORTED_DIMENSIONS:
        reject(
            "invalid_dimensions",
            f"grille {columns}×{rows}, formats acceptés : 9×9 ou 9×10",
        )

    raw_clues = grid.get("clueCells", [])
    clue_cells: set[tuple[int, int]] = set()
    if not isinstance(raw_clues, list):
        reject("invalid_clue_cells", "clueCells doit être une liste")
        raw_clues = []
    for raw in raw_clues:
        cell = _coordinate(raw)
        if cell is None or not _inside(cell, rows, columns):
            reject("invalid_clue_cell", "case-définition hors grille ou mal formée", value=raw)
        elif cell in clue_cells:
            reject("duplicate_clue_cell", "case-définition déclarée deux fois", cell=list(cell))
        else:
            clue_cells.add(cell)

    if (0, 0) not in clue_cells:
        reject(
            "missing_neutral_corner",
            "l’angle supérieur gauche neutre doit être déclaré",
            cell=[0, 0],
        )
    if not any(row == 0 and col > 0 for row, col in clue_cells):
        reject("missing_definition_border", "la première ligne ne contient aucune définition")
    if not any(col == 0 and row > 0 for row, col in clue_cells):
        reject("missing_definition_border", "la première colonne ne contient aucune définition")
    if enforce_layout:
        top_definitions = sum(row == 0 and col > 0 for row, col in clue_cells)
        left_definitions = sum(col == 0 and row > 0 for row, col in clue_cells)
        if top_definitions < 2 or left_definitions < 2:
            reject(
                "insufficient_definition_border",
                "chaque bord supérieur et gauche doit porter au moins deux définitions",
                topDefinitions=top_definitions,
                leftDefinitions=left_definitions,
            )

    words = grid.get("words", [])
    if not isinstance(words, list):
        reject("invalid_words", "words doit être une liste")
        words = []

    seen_word_ids: set[str] = set()
    direction_by_word_id: dict[str, str] = {}
    paths_by_direction: dict[str, dict[tuple[tuple[int, int], ...], list[str]]] = {
        direction: defaultdict(list) for direction in DIRECTIONS
    }
    words_by_clue: dict[tuple[int, int], list[str]] = defaultdict(list)
    cell_directions: dict[tuple[int, int], dict[str, str]] = defaultdict(dict)
    cell_letters: dict[tuple[int, int], str] = {}
    word_reports: list[dict] = []

    for index, word in enumerate(words):
        if not isinstance(word, dict):
            reject("invalid_word", "entrée word mal formée", index=index)
            continue
        supplied_id = word.get("wordId")
        fallback_id = f"{grid_id}:word:{index}"
        has_supplied_id = isinstance(supplied_id, str) and bool(supplied_id.strip())
        word_id = supplied_id if has_supplied_id else fallback_id
        if require_word_ids and not has_supplied_id:
            reject("missing_word_id", "wordId stable absent", wordIndex=index, inferredWordId=fallback_id)
        if word_id in seen_word_ids:
            reject("duplicate_word_id", "wordId utilisé plusieurs fois", wordId=word_id)
        seen_word_ids.add(word_id)

        answer = word.get("answer", "")
        if not isinstance(answer, str) or not answer:
            reject("invalid_answer", "réponse vide ou mal formée", wordId=word_id)
            answer = ""
        direction = word.get("direction")
        raw_clue = word.get("clueCell")
        clue = _coordinate(raw_clue)
        raw_cells = word.get("cells", [])
        path = tuple(
            cell for cell in (_coordinate(raw) for raw in raw_cells if isinstance(raw_cells, list))
            if cell is not None
        )
        word_report = {
            "wordId": word_id,
            "answer": answer,
            "clue": word.get("clue", ""),
            "direction": direction,
            "arrow": word.get("arrow"),
            "clueCell": list(clue) if clue else raw_clue,
            "cells": [list(cell) for cell in path],
            "image": word.get("image"),
        }
        word_reports.append(word_report)

        for editorial_error in editorial_errors(word, root=ROOT):
            reject(
                editorial_error["code"], editorial_error["message"],
                wordId=word_id, answer=answer,
                **{key: value for key, value in editorial_error.items()
                   if key not in {"code", "message"}},
            )

        if direction not in DIRECTIONS:
            reject("invalid_direction", "direction inconnue", wordId=word_id, direction=direction)
            continue
        direction_by_word_id[word_id] = direction
        if clue is None or not _inside(clue, rows, columns) or clue not in clue_cells:
            reject("invalid_word_clue", "case-définition absente ou invalide", wordId=word_id, clueCell=raw_clue)
            continue
        words_by_clue[clue].append(word_id)
        if clue == (0, 0):
            reject("neutral_cell_has_arrow", "l’angle supérieur gauche doit rester neutre", wordId=word_id)
        if not isinstance(raw_cells, list) or len(path) != len(raw_cells):
            reject("invalid_path_cell", "trajet contenant une coordonnée invalide", wordId=word_id)
        if len(path) != len(answer):
            reject(
                "answer_path_length_mismatch",
                "la réponse et son trajet n’ont pas la même longueur",
                wordId=word_id,
                answerLength=len(answer),
                pathLength=len(path),
            )
        dr, dc = DIRECTIONS[direction]
        default_arrow = "right" if direction == "across" else "down"
        arrow = word.get("arrow", default_arrow)
        if arrow != default_arrow:
            reject(
                "bent_arrow_forbidden",
                "la réponse doit commencer directement à droite ou sous sa définition",
                wordId=word_id,
                arrow=arrow,
                requiredArrow=default_arrow,
            )
        start_offset = ARROW_STARTS.get((direction, arrow))
        if start_offset is None:
            reject("invalid_arrow", "type de flèche incompatible avec la direction", wordId=word_id, arrow=arrow)
            start_offset = ARROW_STARTS[(direction, default_arrow)]
        start = (clue[0] - start_offset[0], clue[1] - start_offset[1])
        expected = tuple((start[0] + dr * offset, start[1] + dc * offset) for offset in range(len(path)))
        if path != expected:
            reject(
                "ambiguous_arrow",
                "la flèche ne désigne pas un chemin contigu commençant dans la case adjacente",
                wordId=word_id,
                expected=[list(cell) for cell in expected],
                actual=[list(cell) for cell in path],
            )
        for offset, cell in enumerate(path):
            if not _inside(cell, rows, columns):
                reject("path_out_of_bounds", "trajet hors grille", wordId=word_id, cell=list(cell))
                continue
            if cell in clue_cells:
                reject("path_crosses_clue", "une réponse traverse une case-définition", wordId=word_id, cell=list(cell))
                continue
            previous_word = cell_directions[cell].get(direction)
            if previous_word and previous_word != word_id:
                reject(
                    "overlapping_same_direction",
                    "deux réponses se superposent dans la même direction",
                    cell=list(cell),
                    wordIds=[previous_word, word_id],
                )
            cell_directions[cell][direction] = word_id
            if offset >= len(answer):
                continue
            letter = answer[offset]
            previous_letter = cell_letters.get(cell)
            if previous_letter is not None and previous_letter != letter:
                reject(
                    "crossing_letter_mismatch",
                    "les réponses croisées n’utilisent pas la même lettre",
                    cell=list(cell),
                    letters=[previous_letter, letter],
                    wordId=word_id,
                )
            else:
                cell_letters[cell] = letter
        paths_by_direction[direction][path].append(word_id)

    for semantic_error in grid_semantic_errors(words):
        reject(
            semantic_error["code"], semantic_error["message"],
            **{key: value for key, value in semantic_error.items()
               if key not in {"code", "message"}},
        )

    for clue in sorted(clue_cells):
        clue_word_ids = words_by_clue.get(clue, [])
        if clue == (0, 0):
            continue
        if not clue_word_ids:
            reject("isolated_clue", "case-définition sans réponse", cell=list(clue))
        if len(clue_word_ids) > 2:
            reject("overloaded_clue", "plus de deux définitions dans une case", cell=list(clue), wordIds=clue_word_ids)
        directions = [direction_by_word_id.get(word_id) for word_id in clue_word_ids]
        if len([direction for direction in directions if direction]) != len(set(direction for direction in directions if direction)):
            reject("ambiguous_clue_directions", "deux flèches partent dans la même direction", cell=list(clue))

    # Editorial layout gate. The neutral corner is not a visible definition and
    # therefore does not contribute to walls of beige clue cells.
    visible_clues = clue_cells - {(0, 0)}
    adjacent_clue_runs: list[dict] = []
    for axis in ("row", "column"):
        fixed_count = rows if axis == "row" else columns
        offset_count = columns if axis == "row" else rows
        for fixed in range(fixed_count):
            positions = [
                ((fixed, offset) if axis == "row" else (offset, fixed)) in visible_clues
                for offset in range(offset_count)
            ]
            start = None
            for offset, occupied in enumerate(positions + [False]):
                if occupied and start is None:
                    start = offset
                elif not occupied and start is not None:
                    length = offset - start
                    if length >= 2:
                        adjacent_clue_runs.append({
                            "axis": axis, "index": fixed, "start": start, "length": length,
                        })
                    start = None
    max_adjacent_clues = max((run["length"] for run in adjacent_clue_runs), default=0)
    adjacent_clue_pairs = sum(run["length"] - 1 for run in adjacent_clue_runs)
    interior_adjacent_runs = [
        run for run in adjacent_clue_runs
        if not (run["axis"] == "row" and run["index"] == 0)
        and not (run["axis"] == "column" and run["index"] == 0)
    ]
    max_interior_adjacent_clues = max(
        (run["length"] for run in interior_adjacent_runs), default=0
    )
    interior_adjacent_clue_pairs = sum(
        run["length"] - 1 for run in interior_adjacent_runs
    )
    double_clue_cells = sum(
        len(words_by_clue.get(clue, [])) == 2 for clue in visible_clues
    )
    single_clue_cells = sum(
        len(words_by_clue.get(clue, [])) == 1 for clue in visible_clues
    )
    if enforce_layout and max_interior_adjacent_clues >= 3:
        reject(
            "clue_wall",
            "trois cases-définition ou plus sont collées",
            maxAdjacentClues=max_interior_adjacent_clues,
            runs=[run for run in interior_adjacent_runs if run["length"] >= 3],
        )
    if enforce_layout and interior_adjacent_clue_pairs > 3:
        reject(
            "too_many_adjacent_clue_pairs",
            "plus de trois paires de cases-définition sont collées",
            adjacentCluePairs=interior_adjacent_clue_pairs,
            maximum=3,
        )
    if enforce_layout and words and double_clue_cells < 3:
        reject(
            "insufficient_double_clues",
            "la silhouette n’utilise pas assez de cases à double définition (droite + bas)",
            doubleClueCells=double_clue_cells,
            minimum=3,
        )

    all_cells = {(row, col) for row in range(rows) for col in range(columns)}
    letter_cells = all_cells - clue_cells
    for cell in sorted(letter_cells):
        if cell not in cell_directions:
            reject("uncovered_letter", "case-lettre sans wordId", cell=list(cell))

    orphan_segments: list[dict] = []
    for direction in DIRECTIONS:
        for run in _maximal_runs(letter_cells, rows, columns, direction):
            declared = paths_by_direction[direction].get(run, [])
            if len(run) >= 2 and not declared:
                segment = {
                    "direction": direction,
                    "cells": [list(cell) for cell in run],
                    "letters": "".join(cell_letters.get(cell, "?") for cell in run),
                }
                orphan_segments.append(segment)
                reject(
                    "orphan_segment",
                    "suite visible de deux lettres ou plus sans réponse déclarée",
                    **segment,
                )
            if len(declared) > 1:
                reject(
                    "duplicate_declared_segment",
                    "un même segment est déclaré par plusieurs réponses",
                    direction=direction,
                    cells=[list(cell) for cell in run],
                    wordIds=declared,
                )

    cells = []
    for row in range(rows):
        for col in range(columns):
            cell = (row, col)
            if cell == (0, 0):
                cells.append({"row": row, "col": col, "kind": "neutral", "wordIds": []})
            elif cell in clue_cells:
                cells.append({
                    "row": row,
                    "col": col,
                    "kind": "clue",
                    "wordIds": words_by_clue.get(cell, []),
                })
            else:
                coverage = cell_directions.get(cell, {})
                cells.append({
                    "row": row,
                    "col": col,
                    "kind": "letter",
                    "solution": cell_letters.get(cell),
                    "acrossWordId": coverage.get("across"),
                    "downWordId": coverage.get("down"),
                    "wordIds": [coverage[key] for key in ("across", "down") if key in coverage],
                })

    return {
        "gridId": grid_id,
        "columns": columns,
        "rows": rows,
        "valid": not errors,
        "errorCount": len(errors),
        "errorCounts": dict(sorted(Counter(error["code"] for error in errors).items())),
        "errors": errors,
        "orphanSegments": orphan_segments,
        "cells": cells,
        "words": word_reports,
        "layoutMetrics": {
            "clueCells": len(visible_clues),
            "singleClueCells": single_clue_cells,
            "doubleClueCells": double_clue_cells,
            "maxAdjacentClues": max_adjacent_clues,
            "adjacentCluePairs": adjacent_clue_pairs,
            "interiorAdjacentCluePairs": interior_adjacent_clue_pairs,
            "adjacentClueRuns": adjacent_clue_runs,
        },
    }


def render_topology_html(reports: list[dict], title: str = "Audit topologique MotMan") -> str:
    """Render a human-readable arrowword board plus its technical audit."""
    sections = []
    for report in reports:
        cell_by_position = {(cell["row"], cell["col"]): cell for cell in report["cells"]}
        word_by_id = {word["wordId"]: word for word in report["words"]}
        word_numbers = {
            word["wordId"]: index for index, word in enumerate(report["words"], start=1)
        }
        rows = []
        for row in range(report["rows"]):
            columns = []
            for col in range(report["columns"]):
                cell = cell_by_position[row, col]
                if cell["kind"] == "neutral":
                    content = "<span class='neutral-mark'>∅</span>"
                elif cell["kind"] == "clue":
                    entries = []
                    for word_id in cell["wordIds"]:
                        word = word_by_id.get(word_id, {})
                        arrow = {
                            "right": "→", "down": "↓",
                            "downright": "↘→", "rightdown": "↘↓",
                        }.get(word.get("arrow"), "→" if word.get("direction") == "across" else "↓")
                        direction = "vers la droite" if word.get("direction") == "across" else "vers le bas"
                        path = ",".join(f"{cell[0]}-{cell[1]}" for cell in word.get("cells", []))
                        image = word.get("image") if isinstance(word.get("image"), dict) else None
                        image_alt = str(image.get("alt", "Indice illustré")) if image else ""
                        clue_label = str(word.get("clue") or image_alt or "DÉFINITION VIDE")
                        clue = escape(clue_label)
                        if image:
                            asset = str(image.get("asset", ""))
                            review_asset = f"../../public{asset}" if asset.startswith("/assets/") else asset
                            clue_content = (
                                f"<img class='clue-image' src='{escape(review_asset)}' "
                                f"alt='{escape(image_alt)}'>"
                            )
                        else:
                            clue_content = clue
                        length = len(word.get("cells", []))
                        entries.append(
                            f"<button class='clue-entry' type='button' data-word-id='{escape(word_id)}' "
                            f"data-path='{escape(path)}' data-clue='{clue}' data-direction='{direction}' "
                            f"data-length='{length}' aria-label='{clue}, {length} cases {direction}'>"
                            f"<span class='clue-text'>{clue_content}</span>"
                            f"<span class='route'><b>{arrow}</b><small>{length}</small></span></button>"
                        )
                    content = "".join(entries) or "<span class='clue-entry invalid'>ISOLÉE</span>"
                else:
                    letter = escape(cell.get("solution") or "?")
                    content = f"<b class='letter-value'>{letter}</b><span class='step-number'></span>"
                coverage = ", ".join(cell.get("wordIds", [])) or "aucun wordId"
                word_ids = " ".join(cell.get("wordIds", []))
                columns.append(
                    f"<td class='{cell['kind']}' data-position='{row}-{col}' "
                    f"data-word-ids='{escape(word_ids)}' title='Ligne {row + 1}, colonne {col + 1} · {escape(coverage)}'>"
                    f"{content}</td>"
                )
            rows.append("<tr>" + "".join(columns) + "</tr>")
        errors = "".join(
            f"<li><code>{escape(error['code'])}</code> — {escape(error['message'])} "
            f"<small>{escape(str({key: value for key, value in error.items() if key not in {'code', 'message'}}))}</small></li>"
            for error in report["errors"]
        ) or "<li>Aucune erreur topologique.</li>"
        paths = ""
        for word in report["words"]:
            cells = word.get("cells", [])
            start = cells[0] if cells else ["?", "?"]
            end = cells[-1] if cells else ["?", "?"]
            direction = "Droite" if word.get("direction") == "across" else "Bas"
            image = word.get("image") if isinstance(word.get("image"), dict) else None
            clue_label = str(word.get("clue") or (
                f"🖼 {image.get('alt', 'Indice illustré')}" if image else "DÉFINITION VIDE"
            ))
            paths += (
                f"<tr><td>{word_numbers[word['wordId']]}</td><td>{escape(clue_label)}</td>"
                f"<td><b>{escape(word['answer'])}</b></td><td>{direction}</td>"
                f"<td>L{int(start[0]) + 1}C{int(start[1]) + 1} → L{int(end[0]) + 1}C{int(end[1]) + 1} "
                f"({len(cells)} cases)</td></tr>"
            )
        status = "VALIDE" if report["valid"] else "REJETÉE"
        metrics = report.get("layoutMetrics", {})
        sections.append(f"""
        <section class='grid-review' data-grid-id='{escape(report['gridId'])}'>
          <h2>{escape(report['gridId'])} — <span class='status'>{status}</span></h2>
          <p class='metrics'>Définitions : {metrics.get('clueCells', 0)} · doubles : {metrics.get('doubleClueCells', 0)} ·
          simples : {metrics.get('singleClueCells', 0)} · maximum collé : {metrics.get('maxAdjacentClues', 0)}</p>
          <div class='instructions'>
            <strong>Comment lire la grille :</strong> clique sur une définition. Son trajet devient bleu et la première case porte le numéro 1.
            <span><b>→</b> commence dans la case à droite · <b>↓</b> commence dans la case en dessous.</span>
          </div>
          <div class='toolbar'>
            <button type='button' class='solution-toggle' aria-pressed='false'>Afficher les solutions</button>
            <output class='selection-status' aria-live='polite'>Aucune définition sélectionnée.</output>
          </div>
          <div class='grid-scroll'><table class='grid' aria-label='Grille de mots fléchés'>{''.join(rows)}</table></div>
          <h3>Rejets ({report['errorCount']})</h3><ul>{errors}</ul>
          <details><summary>Liste humaine des réponses et trajets</summary>
            <table class='paths'><thead><tr><th>N°</th><th>Définition</th><th>Réponse</th><th>Sens</th><th>Trajet</th></tr></thead>
            <tbody>{paths}</tbody></table>
          </details>
        </section>""")
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(title)}</title>
<style>
body{{font:15px system-ui,sans-serif;margin:24px;background:#f6f3ed;color:#24211d}}section{{background:white;padding:20px;margin:0 0 28px;border-radius:12px;overflow:hidden}}
.instructions{{display:grid;gap:5px;padding:12px 14px;margin:12px 0;background:#f3f7ff;border-left:4px solid #316bca;border-radius:6px}}.instructions span{{font-size:13px}}
.toolbar{{display:flex;align-items:center;gap:14px;min-height:40px;margin:12px 0}}.toolbar button{{border:1px solid #315f9f;background:#fff;color:#214f8e;border-radius:8px;padding:8px 12px;font-weight:700;cursor:pointer}}.selection-status{{font-weight:650;color:#214f8e}}
.grid-scroll{{overflow:auto;padding:4px}}.grid{{border-collapse:collapse;table-layout:fixed;background:white;box-shadow:0 2px 9px #0002}}.grid td{{position:relative;width:78px;height:78px;min-width:78px;border:1px solid #807b72;text-align:center;vertical-align:middle;padding:0;box-sizing:border-box}}
.grid td.clue{{background:#e7e1d6}}.grid td.neutral{{background:#292723;color:white}}.neutral-mark{{font-size:22px}}.grid td.letter{{background:#fff;transition:background .12s,box-shadow .12s}}.grid td.letter.active{{background:#dcecff;box-shadow:inset 0 0 0 3px #3374c6}}.grid td.letter.first-cell{{background:#b9d7ff;box-shadow:inset 0 0 0 4px #164f9e}}
.letter-value{{display:none;font-size:25px}}.show-solutions .letter-value{{display:block}}.step-number{{display:none;position:absolute;left:4px;top:3px;width:18px;height:18px;border-radius:50%;background:#174f98;color:white;font:700 11px/18px system-ui}}.active .step-number{{display:block}}.active .step-number::after{{content:attr(data-step)}}
.clue-entry{{width:100%;min-height:50%;border:0;background:transparent;display:grid;grid-template-columns:1fr auto;align-items:center;gap:3px;font:650 10px/1.08 system-ui;padding:4px;overflow-wrap:anywhere;cursor:pointer;color:#24211d;box-sizing:border-box}}.clue-entry:hover,.clue-entry:focus-visible,.clue-entry.selected{{background:#cfe1fb;outline:2px solid #225da8;outline-offset:-2px}}.clue-entry+ .clue-entry{{border-top:1px solid #9e9688}}.clue-text{{min-width:0}}.clue-image{{display:block;width:34px;height:34px;object-fit:contain;margin:auto}}.route{{display:grid;place-items:center;min-width:20px}}.route b{{font-size:17px;line-height:1}}.route small{{font-size:9px;color:#555}}.invalid{{color:#a00}}.metrics{{font-weight:600}}
code{{background:#eee9df;padding:2px 4px;border-radius:3px}}li{{margin:6px 0}}details{{margin-top:12px}}summary{{cursor:pointer;font-weight:700}}.paths{{border-collapse:collapse;margin-top:10px;width:100%}}.paths td,.paths th{{border:1px solid #ccc;padding:6px;text-align:left}}
@media(max-width:760px){{body{{margin:10px}}section{{padding:12px}}.grid td{{width:62px;height:62px;min-width:62px}}.clue-entry{{font-size:8px;padding:2px}}.route b{{font-size:14px}}.toolbar{{align-items:flex-start;flex-direction:column;gap:8px}}}}
</style></head><body><h1>{escape(title)}</h1>{''.join(sections)}
<script>
document.querySelectorAll('.grid-review').forEach(section => {{
  const status = section.querySelector('.selection-status');
  const clear = () => {{
    section.querySelectorAll('.active,.first-cell,.selected').forEach(node => node.classList.remove('active','first-cell','selected'));
    section.querySelectorAll('.step-number').forEach(node => node.removeAttribute('data-step'));
  }};
  section.querySelectorAll('.clue-entry[data-word-id]').forEach(button => {{
    button.addEventListener('click', () => {{
      const wasSelected = button.classList.contains('selected');
      clear();
      if (wasSelected) {{ status.textContent = 'Aucune définition sélectionnée.'; return; }}
      button.classList.add('selected');
      const positions = button.dataset.path.split(',').filter(Boolean);
      positions.forEach((position, index) => {{
        const cell = section.querySelector(`[data-position="${{position}}"]`);
        if (!cell) return;
        cell.classList.add('active');
        if (index === 0) cell.classList.add('first-cell');
        const badge = cell.querySelector('.step-number');
        if (badge) badge.setAttribute('data-step', String(index + 1));
      }});
      status.textContent = `${{button.dataset.clue}} — ${{button.dataset.length}} cases ${{button.dataset.direction}}.`;
    }});
  }});
  section.querySelector('.solution-toggle').addEventListener('click', event => {{
    const visible = section.classList.toggle('show-solutions');
    event.currentTarget.textContent = visible ? 'Masquer les solutions' : 'Afficher les solutions';
    event.currentTarget.setAttribute('aria-pressed', String(visible));
  }});
}});
</script></body></html>"""
