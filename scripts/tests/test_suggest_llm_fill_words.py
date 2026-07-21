from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from suggest_llm_fill_words import compile_pattern  # noqa: E402


class SuggestLlmFillWordsTests(unittest.TestCase):
    def test_unknown_letters_and_accents_are_supported(self) -> None:
        matcher = compile_pattern("C?ENE")
        self.assertIsNotNone(matcher.fullmatch("CHENE"))
        self.assertIsNone(matcher.fullmatch("CHAINE"))

    def test_invalid_pattern_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            compile_pattern("AB*CD")


if __name__ == "__main__":
    unittest.main()
