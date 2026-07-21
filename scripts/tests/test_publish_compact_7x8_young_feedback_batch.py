from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from publish_compact_7x8_young_feedback_batch import (  # noqa: E402
    APPROVED_SOURCE_IDS,
    prepare_publication,
)


class PublishYoungFeedbackBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.active = json.loads(
            (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
        )
        cls.active["grids"] = [
            grid for grid in cls.active["grids"]
            if grid["id"] not in APPROVED_SOURCE_IDS
        ]
        cls.staging = json.loads(
            (ROOT / "output/quality/compact-7x8-young-feedback-staging.json").read_text(
                encoding="utf-8"
            )
        )
        cls.blacklist = json.loads(
            (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
        )

    def test_seven_owner_approved_grids_are_published(self) -> None:
        published, report = prepare_publication(
            self.active, self.staging, self.blacklist
        )
        self.assertEqual(report["added"], 7)
        self.assertEqual(set(report["addedIds"]), APPROVED_SOURCE_IDS)
        self.assertEqual(len(published["grids"]), len(self.active["grids"]) + 7)
        self.assertTrue(all(grid["columns"] == 7 for grid in published["grids"]))
        self.assertTrue(all(grid["rows"] == 8 for grid in published["grids"]))

    def test_condor_uses_the_owner_requested_text_definition(self) -> None:
        published, _report = prepare_publication(
            self.active, self.staging, self.blacklist
        )
        condor = next(
            word
            for grid in published["grids"]
            for word in grid["words"]
            if grid["id"] == "compact-7x8-young-balanced-02"
            and word["answer"] == "CONDOR"
        )
        self.assertEqual(condor["clue"], "Grand vautour")
        self.assertNotIn("image", condor)


if __name__ == "__main__":
    unittest.main()
