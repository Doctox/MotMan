from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from craft_flexible_common_grid import (  # noqa: E402
    editorial_quality_scores,
    morphalou_structural_entry_allowed,
)


class MorphalouStructuralFilterTests(unittest.TestCase):
    def test_lemma_only_rejects_inflected_verbs(self):
        inflected = {
            "answer": "EPOUSERAI",
            "partOfSpeech": "verb",
            "formType": "inflected",
        }
        self.assertTrue(morphalou_structural_entry_allowed(inflected))
        self.assertFalse(
            morphalou_structural_entry_allowed(inflected, lemmas_only=True)
        )

    def test_lemma_only_keeps_dictionary_headwords(self):
        lemma = {
            "answer": "TRACTEUR",
            "partOfSpeech": "common-noun",
            "formType": "lemma",
        }
        self.assertTrue(
            morphalou_structural_entry_allowed(lemma, lemmas_only=True)
        )

    def test_unusable_parts_of_speech_stay_excluded(self):
        proper_name = {
            "answer": "ASTOR",
            "partOfSpeech": "proper-noun",
            "formType": "lemma",
        }
        self.assertFalse(morphalou_structural_entry_allowed(proper_name))

    def test_reviewed_definition_backed_answers_get_an_editorial_bonus(self):
        entries = [
            {"answer": "TRACTEUR", "difficulty": "easy"},
            {"answer": "ASTOR", "difficulty": "hard"},
        ]
        with patch("generate_grid_catalog.load_entries", return_value=entries):
            quality, reviewed_count = editorial_quality_scores(
                {"TRACTEUR": 4.0, "ASTOR": 4.0, "BUS": 4.0}
            )
        self.assertEqual(1, reviewed_count)
        self.assertEqual(4.75, quality["TRACTEUR"])
        self.assertEqual(4.0, quality["ASTOR"])
        self.assertEqual(4.0, quality["BUS"])


if __name__ == "__main__":
    unittest.main()
