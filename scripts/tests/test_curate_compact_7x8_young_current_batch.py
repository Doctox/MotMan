from __future__ import annotations

import json
import re
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import curate_compact_7x8_young_current_round2 as curation  # noqa: E402
from build_compact_7x8_review import build_grid  # noqa: E402
from grid_topology import audit_grid_topology  # noqa: E402


class YoungCurrentCurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = curation.build_payload()

    def test_rejected_batch_preserves_the_observed_internal_repeats(self) -> None:
        self.assertEqual(10, len(self.payload["grids"]))
        self.assertEqual("rejected", self.payload["ownerDecision"])
        self.assertFalse(self.payload["publicationEligible"])
        counts = Counter(
            item["answer"]
            for grid in self.payload["grids"]
            for item in grid["answers"]
        )
        repeated = {answer for answer, count in counts.items() if count > 1}
        self.assertEqual(curation.OBSERVED_INTERNAL_REPEATS, repeated)
        self.assertTrue(all(counts[answer] == 2 for answer in repeated))
        self.assertEqual(155, len(counts))

    def test_topology_is_complete_but_blacklist_now_catches_owner_rejections(self) -> None:
        blacklist = json.loads(
            (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
        )
        rejected = set(blacklist.get("rejectedAnswers", []))
        blocked = set()
        for index, source in enumerate(self.payload["grids"], 1):
            grid = build_grid(source, index)
            report = audit_grid_topology(grid, enforce_layout=False)
            answers = {word["answer"] for word in grid["words"]}
            self.assertTrue(report["valid"], report["errors"])
            self.assertEqual([], report["orphanSegments"])
            blocked.update(answers & rejected)
        self.assertEqual({"NIERA", "SARCLE"}, blocked)

    def test_images_and_visible_clues_stay_mobile_readable(self) -> None:
        for grid in self.payload["grids"]:
            images = {item["answer"]: item for item in grid["imageAnswers"]}
            self.assertTrue(4 <= len(images) <= 6)
            for item in grid["answers"]:
                clue = images.get(item["answer"], {}).get("alt") or item["definition"]
                word_count = len(re.findall(r"[\wÀ-ÿ]+", clue))
                self.assertTrue(1 <= word_count <= 3, (item["answer"], clue))

    def test_pop_culture_is_dosed_across_the_batch(self) -> None:
        anchors = {"NEMO", "LEGO", "INOXTAG", "MATRIX"}
        present = {
            item["answer"]
            for grid in self.payload["grids"]
            for item in grid["answers"]
            if item["answer"] in anchors
        }
        self.assertEqual(anchors, present)
        for grid in self.payload["grids"]:
            answers = {item["answer"] for item in grid["answers"]}
            self.assertLessEqual(len(answers & anchors), 1)

    def test_active_catalog_repeats_are_observed_not_allowed(self) -> None:
        self.assertEqual(
            sorted(curation.OBSERVED_REFERENCE_REPEATS),
            self.payload["observedReferenceRepeats"],
        )
        self.assertNotIn("allowedReferenceRepeats", self.payload)


if __name__ == "__main__":
    unittest.main()
