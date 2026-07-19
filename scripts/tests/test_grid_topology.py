from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from grid_topology import audit_grid_topology, render_topology_html  # noqa: E402


def valid_grid() -> dict:
    clue_cells = [[0, col] for col in range(7)] + [[row, 0] for row in range(1, 8)]
    letters = [
        "ABCDEF",
        "BCDEFG",
        "CDEFGH",
        "DEFGHI",
        "EFGHIJ",
        "FGHIJK",
        "GHIJKL",
    ]
    words = []
    for row, answer in enumerate(letters, start=1):
        words.append({
            "wordId": f"h{row}", "answer": answer, "clue": f"Ligne {row}",
            "direction": "across", "clueCell": [row, 0],
            "cells": [[row, col] for col in range(1, 7)],
        })
    for col in range(1, 7):
        answer = "".join(row[col - 1] for row in letters)
        words.append({
            "wordId": f"v{col}", "answer": answer, "clue": f"Colonne {col}",
            "direction": "down", "clueCell": [0, col],
            "cells": [[row, col] for row in range(1, 8)],
        })
    return {"id": "test-grid", "columns": 7, "rows": 8, "clueCells": clue_cells, "words": words}


def codes(report: dict) -> set[str]:
    return {error["code"] for error in report["errors"]}


def valid_rectangular_grid(columns: int = 9, rows: int = 10) -> dict:
    clue_cells = [[0, col] for col in range(columns)] + [
        [row, 0] for row in range(1, rows)
    ]
    words = []
    for row in range(1, rows):
        words.append({
            "wordId": f"rh{row}", "answer": "A" * (columns - 1),
            "clue": f"Ligne {row}", "direction": "across",
            "clueCell": [row, 0],
            "cells": [[row, col] for col in range(1, columns)],
        })
    for col in range(1, columns):
        words.append({
            "wordId": f"rv{col}", "answer": "A" * (rows - 1),
            "clue": f"Colonne {col}", "direction": "down",
            "clueCell": [0, col],
            "cells": [[row, col] for row in range(1, rows)],
        })
    return {
        "id": f"test-grid-{columns}x{rows}", "columns": columns, "rows": rows,
        "clueCells": clue_cells, "words": words,
    }


class GridTopologyTests(unittest.TestCase):
    def test_complete_grid_is_valid_and_reports_56_cells(self) -> None:
        report = audit_grid_topology(valid_grid(), enforce_layout=False)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(56, len(report["cells"]))
        centre = next(cell for cell in report["cells"] if (cell["row"], cell["col"]) == (4, 4))
        self.assertEqual(["h4", "v4"], centre["wordIds"])

    def test_rectangular_9_by_10_grid_is_rejected(self) -> None:
        report = audit_grid_topology(valid_rectangular_grid(9, 10), enforce_layout=False)
        self.assertFalse(report["valid"])
        self.assertIn("invalid_dimensions", codes(report))

    def test_compact_7_by_8_grid_reports_56_cells(self) -> None:
        report = audit_grid_topology(valid_rectangular_grid(7, 8), enforce_layout=False)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual((7, 8), (report["columns"], report["rows"]))
        self.assertEqual(56, len(report["cells"]))

    def test_definition_borders_are_allowed_but_missing_doubles_are_blocking(self) -> None:
        report = audit_grid_topology(valid_grid())
        self.assertNotIn("clue_wall", codes(report))
        self.assertIn("insufficient_double_clues", codes(report))

    def test_internal_clue_wall_is_blocking(self) -> None:
        grid = valid_grid()
        grid["clueCells"].extend([[4, 2], [4, 3], [4, 4]])
        self.assertIn("clue_wall", codes(audit_grid_topology(grid)))

    def test_bent_arrow_is_blocking_even_when_its_path_is_geometrically_valid(self) -> None:
        grid = valid_grid()
        horizontal = next(word for word in grid["words"] if word["wordId"] == "h1")
        horizontal["clueCell"] = [0, 1]
        horizontal["arrow"] = "downright"
        report = audit_grid_topology(grid, enforce_layout=False)
        self.assertIn("bent_arrow_forbidden", codes(report))
        self.assertNotIn("ambiguous_arrow", codes(report))

    def test_visible_undeclared_run_is_rejected(self) -> None:
        grid = valid_grid()
        grid["words"] = [word for word in grid["words"] if word["wordId"] != "h4"]
        report = audit_grid_topology(grid)
        self.assertIn("orphan_segment", codes(report))
        self.assertEqual([[4, col] for col in range(1, 7)], report["orphanSegments"][0]["cells"])

    def test_crossing_letters_must_match(self) -> None:
        grid = valid_grid()
        vertical = next(word for word in grid["words"] if word["wordId"] == "v4")
        vertical["answer"] = "Z" + vertical["answer"][1:]
        self.assertIn("crossing_letter_mismatch", codes(audit_grid_topology(grid)))

    def test_arrow_must_start_in_adjacent_cell(self) -> None:
        grid = valid_grid()
        horizontal = next(word for word in grid["words"] if word["wordId"] == "h2")
        horizontal["cells"] = horizontal["cells"][1:] + [[2, 9]]
        report = audit_grid_topology(grid)
        self.assertIn("ambiguous_arrow", codes(report))
        self.assertIn("path_out_of_bounds", codes(report))

    def test_missing_word_id_is_blocking(self) -> None:
        grid = valid_grid()
        del grid["words"][0]["wordId"]
        self.assertIn("missing_word_id", codes(audit_grid_topology(grid)))
        self.assertNotIn("missing_word_id", codes(
            audit_grid_topology(grid, require_word_ids=False)
        ))

    def test_missing_definition_border_is_blocking(self) -> None:
        grid = copy.deepcopy(valid_grid())
        grid["clueCells"] = [cell for cell in grid["clueCells"] if cell[0] != 0]
        self.assertIn("missing_definition_border", codes(audit_grid_topology(grid)))

    def test_human_report_explains_and_highlights_word_paths(self) -> None:
        report = audit_grid_topology(valid_grid(), enforce_layout=False)
        html = render_topology_html([report])
        self.assertIn("Comment lire la grille", html)
        self.assertIn("Afficher les solutions", html)
        self.assertIn("data-path='1-1,1-2,1-3,1-4,1-5,1-6'", html)
        self.assertIn("class='selection-status'", html)
        self.assertIn("class='step-number'", html)
        self.assertIn("Liste humaine des réponses et trajets", html)


if __name__ == "__main__":
    unittest.main()
