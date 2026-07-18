from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from build_owner_flexible_complete_grid import FILL, _build_grid  # noqa: E402
from grid_topology import audit_grid_topology  # noqa: E402


class OwnerFlexibleCompleteGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fill = json.loads(FILL.read_text(encoding="utf-8"))
        cls.grid = _build_grid(fill)
        cls.report = audit_grid_topology(cls.grid, enforce_layout=False)

    def test_full_top_and_left_definition_frame(self) -> None:
        clues = {tuple(cell) for cell in self.grid["clueCells"]}
        self.assertTrue(all((0, col) in clues for col in range(9)))
        self.assertTrue(all((row, 0) in clues for row in range(10)))

    def test_every_letter_cell_is_covered(self) -> None:
        self.assertTrue(self.report["valid"], self.report["errors"])
        letters = [cell for cell in self.report["cells"] if cell["kind"] == "letter"]
        self.assertEqual(61, len(letters))
        self.assertTrue(all(cell["wordIds"] for cell in letters))
        self.assertEqual([], self.report["orphanSegments"])

    def test_every_answer_has_a_human_clue_and_exact_path(self) -> None:
        self.assertEqual(28, len(self.grid["words"]))
        for word in self.grid["words"]:
            self.assertTrue(word["clue"].strip(), word["answer"])
            self.assertEqual(len(word["answer"]), len(word["cells"]), word["answer"])


if __name__ == "__main__":
    unittest.main()
