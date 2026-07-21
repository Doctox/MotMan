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
        self.assertEqual(2, centre["coverageCount"])
        self.assertTrue(centre["coverageValid"])

    def test_complete_grid_is_valid_under_corrected_pilot_profile(self) -> None:
        report = audit_grid_topology(
            valid_grid(), enforce_layout=False, topology_profile="pilot"
        )
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual("pilot", report["topologyProfile"])

    def test_rectangular_9_by_10_grid_is_rejected(self) -> None:
        report = audit_grid_topology(valid_rectangular_grid(9, 10), enforce_layout=False)
        self.assertFalse(report["valid"])
        self.assertIn("invalid_dimensions", codes(report))

    def test_compact_7_by_8_grid_reports_56_cells(self) -> None:
        report = audit_grid_topology(valid_rectangular_grid(7, 8), enforce_layout=False)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual((7, 8), (report["columns"], report["rows"]))
        self.assertEqual(56, len(report["cells"]))

    def test_definition_borders_are_valid_without_internal_double_clues(self) -> None:
        report = audit_grid_topology(valid_grid())
        self.assertNotIn("clue_wall", codes(report))
        self.assertNotIn("insufficient_double_clues", codes(report))
        self.assertTrue(report["valid"], report["errors"])

    def test_first_row_and_column_are_a_complete_definition_frame(self) -> None:
        grid = valid_grid()
        grid["clueCells"].remove([0, 3])
        report = audit_grid_topology(grid, enforce_layout=False)
        self.assertIn("missing_definition_border", codes(report))
        error = next(error for error in report["errors"] if error["code"] == "missing_definition_border")
        self.assertIn([0, 3], error["cells"])

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
        self.assertIn("letter_not_double_covered", codes(report))
        self.assertEqual([[4, col] for col in range(1, 7)], report["orphanSegments"][0]["cells"])

    def test_single_axis_letter_is_rejected_even_when_other_axis_is_valid(self) -> None:
        grid = valid_grid()
        grid["words"] = [word for word in grid["words"] if word["wordId"] != "v2"]
        report = audit_grid_topology(grid, enforce_layout=False)
        self.assertIn("letter_not_double_covered", codes(report))
        cell = next(cell for cell in report["cells"] if (cell["row"], cell["col"]) == (1, 2))
        self.assertEqual("h1", cell["acrossWordId"])
        self.assertIsNone(cell["downWordId"])
        self.assertFalse(cell["coverageValid"])

    def test_pilot_allows_a_perpendicular_singleton_without_word_id(self) -> None:
        grid = valid_grid()
        grid["clueCells"].extend(
            [[row, 3] for row in (1, 2, 3, 5, 6, 7)]
        )
        grid["words"] = [
            word for word in grid["words"] if word["wordId"] != "v3"
        ]
        report = audit_grid_topology(
            grid, enforce_layout=False, topology_profile="pilot"
        )
        centre = next(
            cell for cell in report["cells"]
            if (cell["row"], cell["col"]) == (4, 3)
        )
        self.assertEqual("h4", centre["acrossWordId"])
        self.assertIsNone(centre["downWordId"])
        self.assertEqual(1, centre["coverageCount"])
        self.assertTrue(centre["coverageValid"])
        self.assertNotIn("letter_not_double_covered", codes(report))
        self.assertFalse(any(
            error["code"] == "singleton_visual_segment"
            and error.get("direction") == "down"
            and error.get("cells") == [[4, 3]]
            for error in report["errors"]
        ))

    def test_pilot_still_rejects_a_letter_with_zero_total_coverage(self) -> None:
        grid = valid_grid()
        grid["words"] = [
            word for word in grid["words"]
            if word["wordId"] not in {"h4", "v4"}
        ]
        report = audit_grid_topology(
            grid, enforce_layout=False, topology_profile="pilot"
        )
        self.assertIn("uncovered_letter", codes(report))
        centre = next(
            cell for cell in report["cells"]
            if (cell["row"], cell["col"]) == (4, 4)
        )
        self.assertEqual(0, centre["coverageCount"])
        self.assertFalse(centre["coverageValid"])

    def test_singleton_visual_segment_is_blocking(self) -> None:
        grid = valid_grid()
        grid["clueCells"].extend([[4, 3], [4, 5], [3, 4], [5, 4]])
        report = audit_grid_topology(grid, enforce_layout=False)
        self.assertIn("singleton_visual_segment", codes(report))

    def test_pilot_rejects_every_maximal_two_letter_run(self) -> None:
        grid = valid_grid()
        grid["clueCells"].extend([[4, 3], [4, 6]])
        report = audit_grid_topology(
            grid, enforce_layout=False, topology_profile="pilot"
        )
        self.assertIn("two_letter_segment", codes(report))

    def test_pilot_rejects_a_declared_path_shorter_than_its_maximal_run(self) -> None:
        grid = valid_grid()
        horizontal = next(word for word in grid["words"] if word["wordId"] == "h4")
        horizontal["answer"] = horizontal["answer"][:3]
        horizontal["cells"] = horizontal["cells"][:3]
        report = audit_grid_topology(
            grid, enforce_layout=False, topology_profile="pilot"
        )
        self.assertIn("non_maximal_declared_path", codes(report))
        self.assertIn("orphan_segment", codes(report))

    def test_unknown_topology_profile_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "topology_profile inconnu"):
            audit_grid_topology(valid_grid(), topology_profile="inconnu")

    def test_answer_shorter_than_three_letters_is_blocking(self) -> None:
        grid = valid_grid()
        word = next(word for word in grid["words"] if word["wordId"] == "h1")
        word["answer"] = "AB"
        word["cells"] = word["cells"][:2]
        report = audit_grid_topology(grid, enforce_layout=False)
        self.assertIn("answer_too_short", codes(report))

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
