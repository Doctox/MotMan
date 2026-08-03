from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import publish_certified_editorial_lot2_9e969ceeb44a as publisher


class CertifiedEditorialLot2PublisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.staging, cls.audit, cls.selection = publisher.verify_artifacts()
        cls.approved = [
            publisher.owner_approved_grid(grid) for grid in cls.staging["grids"]
        ]

    def source_catalog(self) -> dict:
        catalog = publisher.read_json(publisher.CATALOG_PATH)
        if catalog["version"] == publisher.SOURCE_VERSION:
            return catalog
        return publisher.read_json(
            publisher.OUTPUT_DIR / "prepublish-grid-catalog-v22.json"
        )

    def test_artifacts_and_all_twelve_topologies_are_valid(self) -> None:
        self.assertTrue(self.audit["valid"])
        self.assertEqual(len(self.approved), 12)
        self.assertEqual(self.audit["topology"]["validGridCount"], 12)
        self.assertEqual(self.audit["topology"]["invalidGridCount"], 0)
        self.assertEqual(self.selection["sourceGridCount"], 54)
        self.assertEqual(self.selection["excludedGridCount"], 42)

    def test_owner_approval_is_explicit_on_every_grid(self) -> None:
        for grid in self.approved:
            self.assertEqual(grid["ownerReview"]["status"], "approved")
            self.assertEqual(grid["ownerReview"]["decision"], "publish")
            self.assertEqual(grid["editorialReview"]["status"], "owner-approved")

    def test_blacklist_and_topology_are_rechecked(self) -> None:
        reports = publisher.verify_grids(
            self.approved, publisher.read_json(publisher.BLACKLIST_PATH)
        )
        self.assertEqual(len(reports), 12)
        self.assertTrue(all(report["valid"] for report in reports))

    def test_catalog_update_keeps_44_and_adds_exactly_12(self) -> None:
        previous = self.source_catalog()
        updated, approved = publisher.build_updated_catalog(
            previous, self.staging["grids"], self.selection
        )
        self.assertEqual(updated["version"], 23)
        self.assertEqual(len(updated["grids"]), 56)
        self.assertEqual(len(approved), 12)
        previous_ids = {grid["id"] for grid in previous["grids"]}
        approved_ids = {grid["id"] for grid in approved}
        self.assertFalse(previous_ids & approved_ids)

    def test_partial_publication_is_rejected(self) -> None:
        previous = self.source_catalog()
        partial = copy.deepcopy(previous)
        partial["grids"].append(self.approved[0])
        with self.assertRaisesRegex(ValueError, "Publication partielle"):
            publisher.build_updated_catalog(
                partial, self.staging["grids"], self.selection
            )

    def test_runtime_projection_only_contains_gameplay_fields(self) -> None:
        catalog, _ = publisher.build_updated_catalog(
            self.source_catalog(), self.staging["grids"], self.selection
        )
        runtime = publisher.runtime_projection(catalog)
        self.assertEqual(runtime["version"], 23)
        self.assertEqual(len(runtime["grids"]), 56)
        for grid in runtime["grids"]:
            self.assertEqual(
                set(grid), {"id", "columns", "rows", "clueCells", "words"}
            )
            for word in grid["words"]:
                self.assertNotIn("sourceClue", word)
                self.assertNotIn("factoryMetadata", word)

    def test_images_are_embedded_and_need_no_new_aab_asset(self) -> None:
        image_words = [
            word
            for grid in self.approved
            for word in grid["words"]
            if word.get("image")
        ]
        self.assertEqual(len(image_words), 10)
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
