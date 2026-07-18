from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from build_open_synonym_corpus import (  # noqa: E402
    display_clue,
    is_visible_inflection,
    normalize_answer,
    pair_is_eligible,
)


class OpenSynonymCorpusTests(unittest.TestCase):
    def test_normalization_preserves_a_complete_word(self) -> None:
        self.assertEqual("ECORCHER", normalize_answer("écorcher"))
        self.assertEqual("Écorcher", display_clue("écorcher"))
        self.assertIsNone(display_clue("mettre à nu"))

    def test_visible_singular_plural_pair_is_rejected(self) -> None:
        self.assertTrue(is_visible_inflection("MOT", "MOTS"))
        self.assertFalse(is_visible_inflection("DO", "DOS"))

    def test_pair_requires_frequency_pos_and_no_cooldown(self) -> None:
        metadata = {
            "RAPIDE": {"sourceFrequency": 12, "partOfSpeech": "ADJ"},
            "VIF": {"sourceFrequency": 8, "partOfSpeech": "ADJ"},
            "LENT": {"sourceFrequency": 20, "partOfSpeech": "ADJ"},
            "COURIR": {"sourceFrequency": 30, "partOfSpeech": "VER"},
        }
        self.assertTrue(pair_is_eligible(
            "RAPIDE", "VIF", metadata, set(), set(), required_pos="ADJ"
        ))
        self.assertFalse(pair_is_eligible(
            "RAPIDE", "COURIR", metadata, set(), set()
        ))
        self.assertFalse(pair_is_eligible(
            "RAPIDE", "LENT", metadata, {"RAPIDE"}, set()
        ))

    def test_rejected_pair_matches_accented_editorial_clue(self) -> None:
        metadata = {
            "EPONGE": {"sourceFrequency": 12, "partOfSpeech": "NOM"},
            "REDUIT": {"sourceFrequency": 8, "partOfSpeech": "NOM"},
        }
        # load_context canonicalizes the editorial pair "ÉPONGE / Réduit".
        blocked_pairs = {("EPONGE", "REDUIT")}
        self.assertFalse(pair_is_eligible(
            "EPONGE", "REDUIT", metadata, set(), blocked_pairs
        ))


if __name__ == "__main__":
    unittest.main()
