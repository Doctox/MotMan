from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import publish_factory_certified_editorial_batch_20260727 as publisher


class FactoryCertifiedEditorialBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = publisher.verify_handoff()
        cls.grids, cls.withheld = publisher.build_batch(cls.document)

    def test_handoff_digest_and_words_only_schema_are_verified(self) -> None:
        self.assertEqual(self.document["schema"], publisher.EXPECTED_SCHEMA)
        self.assertEqual(
            self.document["manifest"]["payloadSha256"],
            publisher.EXPECTED_PAYLOAD_SHA256,
        )

    def test_four_grids_are_built_and_near_duplicate_is_withheld(self) -> None:
        self.assertEqual(len(self.grids), 4)
        self.assertEqual(self.withheld["sharedAnswerCount"], 16)
        self.assertGreaterEqual(self.withheld["jaccardSimilarity"], 0.88)

    def test_every_grid_has_reviewed_images_and_valid_topology(self) -> None:
        for grid in self.grids:
            self.assertGreaterEqual(grid["imageCount"], 4)
            self.assertLessEqual(grid["imageCount"], 6)
            audit = publisher.audit_grid_topology(
                grid,
                require_word_ids=True,
                enforce_layout=False,
                topology_profile="pilot",
            )
            self.assertTrue(audit["valid"], audit["errors"])

    def test_foster_and_sien_have_explicit_human_decisions(self) -> None:
        words = {
            word["answer"]: word
            for grid in self.grids
            for word in grid["words"]
        }
        self.assertEqual(
            words["FOSTER"]["lexicalExceptionReview"]["status"],
            "human-reviewed-exception",
        )
        self.assertEqual(
            words["FOSTER"]["properNameReview"]["status"],
            "human-reviewed-distinctive",
        )
        self.assertEqual(
            words["SIEN"]["lexicalExceptionReview"]["acceptedAs"],
            "pronom possessif",
        )

    def test_image_clues_may_intentionally_have_empty_text(self) -> None:
        image_words = [
            word
            for grid in self.grids
            for word in grid["words"]
            if word.get("image")
        ]
        self.assertTrue(image_words)
        self.assertTrue(all(word["clue"] == "" for word in image_words))
        self.assertTrue(
            all(
                all(word["image"].get(key) for key in ("asset", "alt", "source", "license"))
                for word in image_words
            )
        )


if __name__ == "__main__":
    unittest.main()
