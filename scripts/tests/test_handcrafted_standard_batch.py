from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from build_handcrafted_standard_batch import (  # noqa: E402
    MANUAL_CLUES,
    SELECTED_DRAFTS,
    edited_grid,
    load_selected_drafts,
)
from editorial_quality import editorial_errors, grid_semantic_errors  # noqa: E402


REPAIRED_ACTIVE_GRIDS = {
    "reference-standard-21",
    "reference-standard-27",
}


class HandcraftedStandardBatchTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.drafts = load_selected_drafts()

    def test_batch_uses_twenty_four_explicitly_selected_drafts(self) -> None:
        self.assertEqual(24, len(SELECTED_DRAFTS))
        self.assertEqual(24, len(self.drafts))

    def test_every_selected_answer_has_a_manual_clue(self) -> None:
        answers = {
            word["answer"]
            for grid in self.drafts
            for word in grid["words"]
        }
        missing = sorted(answer for answer in answers if not MANUAL_CLUES.get(answer))
        self.assertEqual([], missing)

    def test_manual_clues_pass_the_deterministic_editorial_gate(self) -> None:
        answers = {
            word["answer"]
            for grid in self.drafts
            for word in grid["words"]
        }
        failures = {
            answer: editorial_errors({"answer": answer, "clue": MANUAL_CLUES[answer]})
            for answer in sorted(answers)
            if editorial_errors({"answer": answer, "clue": MANUAL_CLUES[answer]})
        }
        self.assertEqual({}, failures)

    def test_edited_grids_have_no_semantic_or_inflection_duplicates(self) -> None:
        blacklist = json.loads(
            (SCRIPTS.parent / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
        )
        quarantined = set(blacklist["quarantinedGridIds"])
        failures = {}
        for offset, draft in enumerate(self.drafts, start=7):
            grid = edited_grid(offset, draft)
            if grid["id"] in REPAIRED_ACTIVE_GRIDS:
                continue
            errors = grid_semantic_errors(grid["words"])
            if errors and grid["id"] not in quarantined:
                failures[grid["id"]] = errors
        self.assertEqual({}, failures)

    def test_unrepaired_inflection_duplicates_are_quarantined(self) -> None:
        blacklist = json.loads(
            (SCRIPTS.parent / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
        )
        quarantined = set(blacklist["quarantinedGridIds"])
        self.assertTrue({
            "reference-standard-20",
            "reference-standard-29",
        }.issubset(quarantined))

    def test_repaired_active_grids_are_semantically_clean(self) -> None:
        catalog = json.loads(
            (SCRIPTS.parent / "src/data/grid.catalog.json").read_text(encoding="utf-8")
        )
        by_id = {grid["id"]: grid for grid in catalog["grids"]}
        failures = {
            grid_id: errors
            for grid_id in sorted(REPAIRED_ACTIVE_GRIDS)
            if (errors := grid_semantic_errors(by_id[grid_id]["words"]))
        }
        self.assertEqual({}, failures)

        grid21_answers = {word["answer"] for word in by_id["reference-standard-21"]["words"]}
        self.assertTrue({"BAC", "EXIL", "BEAU", "AXE", "CIRER", "LAPIN"}.issubset(grid21_answers))
        self.assertTrue({"EVE", "TIRS", "ETAT", "VIE", "ERRER", "SAPIN"}.isdisjoint(grid21_answers))

        grid27_clues = {
            word["answer"]: word["clue"]
            for word in by_id["reference-standard-27"]["words"]
            if word["answer"] in {"IRIS", "LIS"}
        }
        self.assertEqual({"IRIS": "Fleur violette", "LIS": "Fleur royale"}, grid27_clues)

    def test_missing_manual_clue_never_falls_back_to_the_draft(self) -> None:
        answer = next(
            word["answer"]
            for word in self.drafts[0]["words"]
            if not word.get("image")
        )
        with patch.dict(MANUAL_CLUES, {answer: ""}, clear=False):
            with self.assertRaisesRegex(ValueError, "définition manuelle absente"):
                edited_grid(7, self.drafts[0])


if __name__ == "__main__":
    unittest.main()
