from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from publish_quarantine_agent_checkpoint import (  # noqa: E402
    ACTIVE,
    BLACKLIST,
    EXPECTED_NEW_ID,
    PROPOSAL,
    REMOVED_GRID_IDS,
    STAGING,
    prepare_publication,
)


class PublishQuarantineAgentCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.active = json.loads(ACTIVE.read_text(encoding="utf-8"))
        cls.staging = json.loads(STAGING.read_text(encoding="utf-8"))
        cls.blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
        cls.proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))

    def test_atomic_replacement_removes_five_and_adds_one(self) -> None:
        current_ids = {grid["id"] for grid in self.active["grids"]}
        if EXPECTED_NEW_ID in current_ids:
            published, updated_blacklist, report = prepare_publication(
                self.active,
                self.staging,
                self.blacklist,
                self.proposal,
            )
            self.assertEqual("already-published", report["status"])
            self.assertEqual(self.active, published)
            self.assertEqual(self.blacklist, updated_blacklist)
            self.assertFalse(current_ids & REMOVED_GRID_IDS)
            return

        published, updated_blacklist, report = prepare_publication(
            self.active,
            self.staging,
            self.blacklist,
            self.proposal,
        )
        ids = {grid["id"] for grid in published["grids"]}
        self.assertFalse(ids & REMOVED_GRID_IDS)
        self.assertIn(EXPECTED_NEW_ID, ids)
        self.assertEqual(len(self.active["grids"]) - 4, len(published["grids"]))
        self.assertEqual(5, report["removed"])
        self.assertEqual(1, report["added"])
        self.assertTrue(
            {item["answer"] for item in self.proposal["rejectedAnswers"]}
            <= set(updated_blacklist["rejectedAnswers"])
        )

    def test_staged_grid_has_six_images_and_no_old_id(self) -> None:
        self.assertEqual([EXPECTED_NEW_ID], self.staging["acceptedGridIds"])
        self.assertEqual(REMOVED_GRID_IDS, set(self.staging["removedGridIds"]))
        grid = self.staging["grids"][0]
        self.assertEqual(6, sum(bool(word.get("image")) for word in grid["words"]))
        self.assertNotIn(grid["id"], REMOVED_GRID_IDS)


if __name__ == "__main__":
    unittest.main()
