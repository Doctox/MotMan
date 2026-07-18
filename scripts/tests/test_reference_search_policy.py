from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from search_low_short_reference_grid import answer_family  # noqa: E402


class ReferenceSearchPolicyTests(unittest.TestCase):
    def test_common_singular_plural_variants_share_a_family(self) -> None:
        self.assertEqual("FER", answer_family("FERS"))
        self.assertEqual("ORME", answer_family("ORMES"))
        self.assertEqual("MOT", answer_family("MOTS"))

    def test_short_words_are_not_truncated_into_false_families(self) -> None:
        self.assertEqual("BIS", answer_family("BIS"))
        self.assertEqual("ILS", answer_family("ILS"))


if __name__ == "__main__":
    unittest.main()
