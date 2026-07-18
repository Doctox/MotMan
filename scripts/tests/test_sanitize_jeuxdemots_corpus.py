from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from sanitize_jeuxdemots_corpus import (  # noqa: E402
    is_morphological_near_duplicate,
    levenshtein,
)


class SanitizeJeuxDeMotsCorpusTests(unittest.TestCase):
    def test_levenshtein(self) -> None:
        self.assertEqual(1, levenshtein("CHAT", "CHATS"))
        self.assertEqual(4, levenshtein("CHAT", "LION"))

    def test_morphological_variants_are_rejected(self) -> None:
        self.assertTrue(is_morphological_near_duplicate("NOMINAL", "NOMINALE"))
        self.assertTrue(is_morphological_near_duplicate("CAUSANT", "CAUSANTE"))
        self.assertTrue(is_morphological_near_duplicate("CHAT", "CHATS"))

    def test_real_synonyms_are_not_morphological_variants(self) -> None:
        self.assertFalse(is_morphological_near_duplicate("JOYEUX", "GAI"))
        self.assertFalse(is_morphological_near_duplicate("DIMINUER", "REDUIRE"))


if __name__ == "__main__":
    unittest.main()
