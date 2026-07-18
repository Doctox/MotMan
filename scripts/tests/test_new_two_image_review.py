from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from grid_topology import audit_grid_topology  # noqa: E402


class NewTwoImageReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(
            (ROOT / "src/data/grid-generation-handcrafted/new-two-image-rich.review.json")
            .read_text(encoding="utf-8")
        )

    def test_two_grids_are_structurally_complete_and_unpublished(self) -> None:
        self.assertEqual(2, len(self.document["grids"]))
        for grid in self.document["grids"]:
            self.assertEqual((9, 10), (grid["columns"], grid["rows"]))
            self.assertEqual("owner-review-required", grid["publicationStatus"])
            report = audit_grid_topology(grid, enforce_layout=False)
            self.assertTrue(report["valid"], report["errors"])
            self.assertFalse(report["orphanSegments"])

    def test_every_grid_has_exactly_six_real_image_assets(self) -> None:
        for grid in self.document["grids"]:
            image_words = [word for word in grid["words"] if word.get("image")]
            self.assertEqual(6, len(image_words))
            for word in image_words:
                asset = ROOT / "public" / word["image"]["asset"].lstrip("/")
                self.assertTrue(asset.is_file(), asset)

    def test_no_answer_is_repeated_between_the_two_grids(self) -> None:
        first, second = (
            {word["answer"] for word in grid["words"]}
            for grid in self.document["grids"]
        )
        self.assertFalse(first & second)
        self.assertEqual(
            self.document["metrics"]["answers"],
            self.document["metrics"]["uniqueAnswers"],
        )


if __name__ == "__main__":
    unittest.main()
