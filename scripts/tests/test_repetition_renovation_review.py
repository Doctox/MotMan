from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology  # noqa: E402


class RepetitionRenovationReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(
            (ROOT / "src/data/grid-generation-handcrafted/repetition-renovation.review.json")
            .read_text(encoding="utf-8")
        )

    def test_three_drafts_are_complete_and_unpublished(self) -> None:
        self.assertEqual(3, len(self.document["grids"]))
        for grid in self.document["grids"]:
            self.assertEqual((9, 10), (grid["columns"], grid["rows"]))
            self.assertEqual("owner-review-required", grid["publicationStatus"])
            report = audit_grid_topology(grid, enforce_layout=False)
            self.assertTrue(report["valid"], report["errors"])
            self.assertFalse(report["orphanSegments"])

    def test_every_draft_has_six_real_images(self) -> None:
        for grid in self.document["grids"]:
            image_words = [word for word in grid["words"] if word.get("image")]
            self.assertEqual(6, len(image_words))
            for word in image_words:
                asset = ROOT / "public" / word["image"]["asset"].lstrip("/")
                self.assertTrue(asset.is_file(), asset)

    def test_repetition_is_reduced_without_touching_active_catalog(self) -> None:
        metrics = self.document["metrics"]
        self.assertFalse(metrics["activeCatalogModified"])
        self.assertEqual(7, metrics["replacements"])
        self.assertGreater(metrics["conceptExcessSlotsRemoved"], 0)
        self.assertLess(
            metrics["afterIfApproved"]["conceptExcessRate"],
            metrics["before"]["conceptExcessRate"],
        )


if __name__ == "__main__":
    unittest.main()
