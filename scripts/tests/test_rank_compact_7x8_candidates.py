from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from rank_compact_7x8_candidates import (  # noqa: E402
    editorial_score_summary,
    has_no_isolated_clues,
)


class RankCompact7x8CandidatesTests(unittest.TestCase):
    def test_accepts_frame_cells_used_by_an_answer(self) -> None:
        grid = {
            "clueCells": [[0, 0], [0, 1], [1, 0]],
            "rawSlots": [
                {"clueCell": [0, 1]},
                {"clueCell": [1, 0]},
            ],
        }
        self.assertTrue(has_no_isolated_clues(grid))

    def test_rejects_an_isolated_definition_cell(self) -> None:
        grid = {
            "clueCells": [[0, 0], [0, 1], [1, 0]],
            "rawSlots": [{"clueCell": [1, 0]}],
        }
        self.assertFalse(has_no_isolated_clues(grid))

    def test_editorial_summary_exposes_mechanical_inflection(self) -> None:
        summary = editorial_score_summary([
            {
                "answer": "NIERA", "lemma": "NIER", "wordfreqZipf": 2.37,
                "centralClue": "Contestera", "editorialStatus": "source-backed",
            },
            {
                "answer": "VACARME", "lemma": "VACARME", "wordfreqZipf": 3.05,
                "centralClue": "Bruit", "editorialStatus": "human-reviewed",
            },
        ])
        self.assertEqual(["NIERA"], summary["mechanicalAnswers"])
        self.assertGreater(summary["scores"]["VACARME"], 60)


if __name__ == "__main__":
    unittest.main()
