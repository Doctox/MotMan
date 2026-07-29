from __future__ import annotations

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_grid_catalog import current_audience_answers, pilot_two_letter_answers


class PilotAudienceAnchorTests(unittest.TestCase):
    def test_extracts_only_two_letter_answers_for_the_pilot_quota(self) -> None:
        self.assertEqual(
            ["OR", "IA"],
            pilot_two_letter_answers([
                {"answer": "OR"}, {"answer": "MARIO"}, {"answer": "IA"},
            ]),
        )

    def test_counts_current_pop_and_common_anglicisms(self) -> None:
        words = [
            {"answer": "FERRARI", "culturalStatus": "current-pop", "languageStatus": "known-proper-name"},
            {"answer": "STATUT", "culturalStatus": "current-common", "languageStatus": "french"},
            {"answer": "STREAM", "culturalStatus": "everyday", "languageStatus": "common-anglicism"},
            {"answer": "ESTOMAC", "culturalStatus": "everyday", "languageStatus": "french"},
        ]
        self.assertEqual(current_audience_answers(words), ["FERRARI", "STATUT", "STREAM"])

    def test_raw_frequency_never_masquerades_as_youth_signal(self) -> None:
        words = [
            {
                "answer": "CIERGE",
                "culturalStatus": "general-culture",
                "languageStatus": "french",
                "familiarityScore": 99,
            }
        ]
        self.assertEqual(current_audience_answers(words), [])


if __name__ == "__main__":
    unittest.main()
