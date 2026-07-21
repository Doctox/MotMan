from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from publish_compact_7x8_pop_owner_batch import (  # noqa: E402
    APPROVED_SOURCE_IDS,
    prepare_publication,
)
from publish_compact_7x8_young_feedback_batch import (  # noqa: E402
    APPROVED_SOURCE_IDS as YOUNG_APPROVED_SOURCE_IDS,
)


class PublishCompactOwnerBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.active = json.loads(
            (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
        )
        cls.active["grids"] = [
            grid for grid in cls.active["grids"]
            if grid["id"] not in APPROVED_SOURCE_IDS | YOUNG_APPROVED_SOURCE_IDS
        ]
        cls.staging = json.loads(
            (ROOT / "output/quality/compact-7x8-pop-owner-review-staging.json").read_text(
                encoding="utf-8"
            )
        )
        cls.blacklist = json.loads(
            (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
        )

    def test_only_owner_approved_grids_are_published(self) -> None:
        published, report = prepare_publication(
            self.active, self.staging, self.blacklist
        )
        self.assertEqual(report["added"], 9)
        self.assertEqual(set(report["addedIds"]), APPROVED_SOURCE_IDS)
        self.assertEqual(report["excludedIds"], ["compact-7x8-pop-owner-08"])
        self.assertEqual(len(published["grids"]), len(self.active["grids"]) + 9)
        self.assertNotIn(
            "VE",
            {word["answer"] for grid in published["grids"] for word in grid["words"]},
        )

    def test_blacklisted_candidate_cannot_be_published(self) -> None:
        staging = copy.deepcopy(self.staging)
        grid = next(
            item for item in staging["grids"]
            if item["sourceGridId"] == "compact-7x8-pop-owner-01"
        )
        grid["words"][0]["answer"] = "VE"
        with self.assertRaisesRegex(ValueError, "blacklist"):
            prepare_publication(self.active, staging, self.blacklist)

    def test_frotte_uses_owner_requested_replacement_clue(self) -> None:
        published, _report = prepare_publication(
            self.active, self.staging, self.blacklist
        )
        grid = next(
            item for item in published["grids"]
            if item["id"] == "compact-7x8-pop-owner-01"
        )
        frotte = next(word for word in grid["words"] if word["answer"] == "FROTTE")
        self.assertEqual(frotte["clue"], "Astique")


if __name__ == "__main__":
    unittest.main()
