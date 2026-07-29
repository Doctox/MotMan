from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import publish_certified_editorial_sublot_111bca5d3810 as publisher


class CertifiedEditorialSublotPublisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.staging, cls.audit, cls.selection = publisher.verify_artifacts()
        cls.approved = [
            publisher.owner_approved_grid(grid) for grid in cls.staging["grids"]
        ]

    def test_all_pinned_artifacts_and_counts_are_valid(self) -> None:
        self.assertTrue(self.audit["valid"])
        self.assertEqual(len(self.approved), 15)
        self.assertEqual(self.selection["sourceGridCount"], 33)
        self.assertEqual(self.selection["excludedGridCount"], 18)

    def test_owner_approval_is_explicit_on_every_grid(self) -> None:
        for grid in self.approved:
            self.assertEqual(grid["ownerReview"]["status"], "approved")
            self.assertEqual(grid["ownerReview"]["decision"], "publish")
            self.assertEqual(grid["editorialReview"]["status"], "owner-approved")

    def test_blacklist_and_topology_are_rechecked(self) -> None:
        reports = publisher.verify_grids(
            self.approved, publisher.read_json(publisher.BLACKLIST_PATH)
        )
        self.assertEqual(len(reports), 15)
        self.assertTrue(all(report["valid"] for report in reports))

    def test_catalog_update_keeps_29_and_adds_exactly_15(self) -> None:
        catalog = publisher.read_json(publisher.CATALOG_PATH)
        if catalog["version"] == publisher.TARGET_VERSION:
            previous = publisher.read_json(
                publisher.OUTPUT_DIR / "prepublish-grid-catalog-v20.json"
            )
        else:
            previous = catalog
        updated, approved = publisher.build_updated_catalog(
            previous, self.staging["grids"], self.selection
        )
        self.assertEqual(updated["version"], 21)
        self.assertEqual(len(updated["grids"]), 44)
        self.assertEqual(len(approved), 15)
        previous_ids = {grid["id"] for grid in previous["grids"]}
        approved_ids = {grid["id"] for grid in approved}
        self.assertFalse(previous_ids & approved_ids)

    def test_runtime_projection_contains_only_gameplay_fields(self) -> None:
        catalog = publisher.read_json(publisher.CATALOG_PATH)
        if catalog["version"] == publisher.SOURCE_VERSION:
            catalog, _ = publisher.build_updated_catalog(
                catalog, self.staging["grids"], self.selection
            )
        runtime = publisher.runtime_projection(catalog)
        self.assertEqual(runtime["version"], 21)
        self.assertEqual(len(runtime["grids"]), 44)
        for grid in runtime["grids"]:
            self.assertEqual(
                set(grid),
                {"id", "columns", "rows", "clueCells", "words"},
            )
            for word in grid["words"]:
                self.assertNotIn("sourceClue", word)
                self.assertNotIn("factoryMetadata", word)

    def test_22_images_are_embedded_without_new_aab_dependency(self) -> None:
        image_words = [
            word
            for grid in self.approved
            for word in grid["words"]
            if word.get("image")
        ]
        self.assertEqual(len(image_words), 22)
        self.assertTrue(
            all(word["image"]["asset"].startswith("data:") for word in image_words)
        )
        self.assertTrue(
            all(
                word["image"].get("requiresNewAabAsset") is False
                for word in image_words
            )
        )


if __name__ == "__main__":
    unittest.main()
