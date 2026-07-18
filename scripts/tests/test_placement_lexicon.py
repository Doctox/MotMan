from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import generate_grid_catalog as generator  # noqa: E402
from placement_lexicon import build_placement_index  # noqa: E402


class PlacementLexiconTests(unittest.TestCase):
    def test_rotation_cooldown_is_excluded_from_new_placement_pools(self) -> None:
        normal_words = {
            answer
            for answers in build_placement_index(generator, "normal")[0].values()
            for answer in answers
        }
        self.assertTrue(generator.ROTATION_COOLDOWN_ANSWERS)
        self.assertFalse(normal_words & generator.ROTATION_COOLDOWN_ANSWERS)

    def test_tison_is_reserved_for_hard_grids(self) -> None:
        normal_words = {
            answer
            for answers in build_placement_index(generator, "normal")[0].values()
            for answer in answers
        }
        hard_words = {
            answer
            for answers in build_placement_index(generator, "hard")[0].values()
            for answer in answers
        }
        self.assertNotIn("TISON", normal_words)
        self.assertNotIn("TISONS", normal_words)
        self.assertIn("TISON", hard_words)
        self.assertIn("TISONS", hard_words)


if __name__ == "__main__":
    unittest.main()
