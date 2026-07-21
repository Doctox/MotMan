from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from solve_compact_7x8_strict_bands import build_bands, solve_bands  # noqa: E402


class StrictBandSolverTests(unittest.TestCase):
    def test_decomposed_solver_closes_exact_crossings(self) -> None:
        six = ["AAACAT", "BBBDOG", "CCCHEN", "DDDOWL", "EEEFOX", "FFFCOW"]
        short = {"CDH", "AOE", "TGN", "OFC", "WOO", "LXW", "XYZ"}
        seven = ["ABCXDEF", "ABCYDEF", "ABCZDEF"]
        scores = {word: 10.0 for word in [*six, *short, *seven]}
        bands = build_bands(six, short, scores, 100, long_columns=3)
        solutions = solve_bands(bands, short, seven, scores, solution_limit=10)
        self.assertTrue(solutions)
        answers = solutions[0]["answers"]
        self.assertEqual(16, len(answers))
        self.assertEqual(["ABCXDEF", "ABCYDEF", "ABCZDEF"], answers[:3])
        self.assertEqual("XYZ", answers[9])


if __name__ == "__main__":
    unittest.main()
