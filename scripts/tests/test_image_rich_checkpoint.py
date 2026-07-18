from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as generator  # noqa: E402
from grid_topology import audit_grid_topology  # noqa: E402


class ImageRichCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(
            (ROOT / "src/data/grid-generation-handcrafted/image-rich-checkpoint.review.json")
            .read_text(encoding="utf-8")
        )
        cls.grid = cls.document["grids"][0]

    def test_checkpoint_is_not_published_and_topology_is_complete(self) -> None:
        self.assertEqual("owner-review-required", self.grid["publicationStatus"])
        report = audit_grid_topology(self.grid)
        self.assertTrue(report["valid"], report["errors"])
        self.assertFalse(report["orphanSegments"])

    def test_three_small_screen_images_are_real_assets(self) -> None:
        image_words = [word for word in self.grid["words"] if word.get("image")]
        self.assertEqual({"BRAS", "MUR", "TV"}, {word["answer"] for word in image_words})
        for word in image_words:
            asset = ROOT / "public" / word["image"]["asset"].lstrip("/")
            self.assertTrue(asset.is_file(), asset)

    def test_corpus_proof_matches_the_actual_generator_input(self) -> None:
        entries = generator.load_entries()
        proof = self.document["corpusProof"]
        self.assertEqual(len(entries), proof["indexedAnswers"])
        self.assertEqual(len(entries), proof["generatorEligibleAnswersLoaded"])
        self.assertEqual(
            sum(bool(entry.get("image")) for entry in entries),
            proof["reviewedImageAnswersAvailable"],
        )

    def test_repeats_are_rare_and_fatigue_list_is_absent(self) -> None:
        repeats = self.document["batchMetrics"]["rareActiveRepeats"]
        self.assertTrue(repeats)
        self.assertTrue(all(count == 1 for count in repeats.values()))
        fatigue = {"AMAS", "AN", "ANS", "BOL", "FER", "ILE", "ILES", "MER", "SEL"}
        answers = {word["answer"] for word in self.grid["words"]}
        self.assertFalse(fatigue & answers)


if __name__ == "__main__":
    unittest.main()
