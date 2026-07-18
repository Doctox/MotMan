from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from build_large_lexical_wordlist import lexical_score, normalized  # noqa: E402


class LargeLexicalWordlistTests(unittest.TestCase):
    def test_accents_are_normalized_for_grid_crossings(self) -> None:
        self.assertEqual("CHENE", normalized("chêne"))

    def test_common_lemma_outranks_unseen_inflection(self) -> None:
        common = lexical_score(
            100.0, 500.0, form_type="lemma", part_of_speech="common-noun",
            attested_common_form=True,
        )
        reserve = lexical_score(
            0.0, 0.0, form_type="inflected", part_of_speech="verb",
            attested_common_form=False,
        )
        self.assertGreater(common, reserve)

    def test_unattested_inflection_is_far_below_common_form(self) -> None:
        common = lexical_score(
            100.0, 0.0, form_type="inflected", part_of_speech="verb",
            attested_common_form=True,
        )
        rare = lexical_score(
            100.0, 0.0, form_type="inflected", part_of_speech="verb",
            attested_common_form=False,
        )
        self.assertGreaterEqual(common - rare, 30.0)
        self.assertLess(rare, 20.0)


if __name__ == "__main__":
    unittest.main()
