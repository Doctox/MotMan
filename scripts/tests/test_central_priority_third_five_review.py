from __future__ import annotations

import json
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from grid_topology import audit_grid_topology  # noqa: E402


class CentralPriorityThirdFiveReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(
            (ROOT / "src/data/grid-generation-handcrafted/central-priority-third-five.review.json")
            .read_text(encoding="utf-8")
        )
        cls.blacklist = json.loads(
            (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
        )

    def test_five_distinct_valid_topologies(self) -> None:
        grids = self.document["grids"]
        self.assertEqual(5, len(grids))
        self.assertEqual(5, len({grid["shapeFingerprint"] for grid in grids}))
        for grid in grids:
            report = audit_grid_topology(grid)
            self.assertTrue(report["valid"], (grid["id"], report["errors"]))
            self.assertEqual(9, grid["columns"])
            self.assertEqual(10, grid["rows"])
            self.assertGreaterEqual(len(grid["words"]), 26)

    def test_rejected_batch_stays_out_of_runtime(self) -> None:
        active = json.loads(
            (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
        )
        active_ids = {grid["id"] for grid in active["grids"]}
        rejected_ids = {grid["id"] for grid in self.document["grids"]}
        self.assertTrue(rejected_ids.isdisjoint(active_ids))
        self.assertEqual(
            {"owner-rejected"},
            {grid["publicationStatus"] for grid in self.document["grids"]},
        )

    def test_clues_images_and_explicit_forbidden_answers(self) -> None:
        forbidden = {"AMAS", "BOL", "AN", "ANS"}
        for grid in self.document["grids"]:
            images = 0
            for word in grid["words"]:
                answer = word["answer"]
                self.assertNotIn(answer, forbidden)
                if word.get("image"):
                    images += 1
                    asset = ROOT / "public" / word["image"]["asset"].lstrip("/")
                    self.assertTrue(asset.exists(), asset)
                    self.assertTrue(word["image"].get("alt"))
                else:
                    self.assertTrue(word.get("clue", "").strip(), answer)
                    self.assertLessEqual(len(word["clue"].split()), 3, answer)
            self.assertGreaterEqual(images, 1, grid["id"])
            self.assertLessEqual(images, 6, grid["id"])

    def test_only_declared_repetitions_and_no_inflection_pair(self) -> None:
        answers = [
            word["answer"] for grid in self.document["grids"] for word in grid["words"]
        ]
        usage = Counter(answers)
        self.assertEqual({"SI": 2}, {
            answer: count for answer, count in usage.items() if count > 1
        })
        answer_set = set(answers)
        self.assertFalse([
            answer for answer in answer_set
            if len(answer) >= 3 and f"{answer}S" in answer_set
        ])

    def test_batch_provenance_is_explicit(self) -> None:
        metrics = self.document["batchMetrics"]
        self.assertEqual(131, metrics["answers"])
        self.assertEqual(130, metrics["uniqueAnswers"])
        self.assertGreaterEqual(metrics["centralCorpusEligibleAnswers"], 9_000)
        self.assertEqual(
            131,
            metrics["centralCorpusAnswersUsed"] + metrics["lexiqueRescueAnswersUsed"],
        )
        self.assertGreaterEqual(metrics["centralCorpusAnswersUsed"], 90)


if __name__ == "__main__":
    unittest.main()
