from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from build_long_answer_shape_pilot import band_counts  # noqa: E402
from optimize_grid_shapes import optimize  # noqa: E402


class LongAnswerShapePolicyTests(unittest.TestCase):
    def test_counts_requested_length_bands(self) -> None:
        self.assertEqual((7, 9), band_counts({2: 1, 3: 2, 4: 4, 5: 3, 6: 2, 7: 1, 8: 3}))

    def test_ignores_lengths_outside_owner_comparison(self) -> None:
        self.assertEqual((1, 2), band_counts({1: 9, 4: 1, 5: 1, 8: 1, 9: 8}))

    def test_optimizer_can_hard_cap_all_two_to_four_letter_answers(self) -> None:
        shape = optimize(
            timeout=5,
            seed=20260716,
            visible_clue_cells=22,
            minimum_double_clues=3,
            maximum_double_clues=8,
            maximum_adjacent_pairs=4,
            maximum_length_two_answers=2,
            maximum_short_answers_2_to_4=18,
            only_direct_arrows=True,
            require_length_bands=True,
            enforce_length_balance=False,
            enforce_clue_spacing=False,
            enforce_interior_line_limits=True,
            enforce_clue_triples=True,
            enforce_solid_clue_blocks=True,
            minimum_border_clues=6,
            maximum_top_border_clues=6,
            maximum_left_border_clues=7,
            columns=9,
            rows=10,
            maximum_answer_length=9,
        )
        self.assertIsNotNone(shape)
        self.assertLessEqual(shape["metrics"]["shortAnswers2To4"], 18)


if __name__ == "__main__":
    unittest.main()
