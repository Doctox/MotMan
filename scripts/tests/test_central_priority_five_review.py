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


class CentralPriorityFiveReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(
            (ROOT / "src/data/grid-generation-handcrafted/central-priority-five.review.json")
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
            self.assertTrue(audit_grid_topology(grid)["valid"], grid["id"])
            self.assertEqual(9, grid["columns"])
            self.assertEqual(10, grid["rows"])
            self.assertEqual(26, len(grid["words"]))

    def test_clues_images_and_blacklist(self) -> None:
        blocked = set(self.blacklist.get("rejectedAnswers", []))
        for grid in self.document["grids"]:
            images = 0
            for word in grid["words"]:
                self.assertNotIn(word["answer"], blocked)
                if word.get("image"):
                    images += 1
                    asset = ROOT / "public" / word["image"]["asset"].lstrip("/")
                    self.assertTrue(asset.exists(), asset)
                    self.assertTrue(word["image"].get("alt"))
                else:
                    self.assertTrue(word.get("clue", "").strip(), word["answer"])
                    self.assertLessEqual(len(word["clue"].split()), 3, word["answer"])
            self.assertGreaterEqual(images, 1, grid["id"])
            self.assertLessEqual(images, 6, grid["id"])

    def test_only_two_declared_repetitions_and_no_inflection_pair(self) -> None:
        answers = [
            word["answer"] for grid in self.document["grids"] for word in grid["words"]
        ]
        usage = Counter(answers)
        self.assertEqual({"NET": 2, "TETE": 2}, {
            answer: count for answer, count in usage.items() if count > 1
        })
        answer_set = set(answers)
        self.assertFalse([
            answer for answer in answer_set
            if len(answer) >= 3 and f"{answer}S" in answer_set
        ])

    def test_corpus_provenance_is_explicit(self) -> None:
        metrics = self.document["batchMetrics"]
        self.assertEqual(9491, metrics["centralCorpusSize"])
        self.assertEqual(130, metrics["answers"])
        self.assertEqual(
            130,
            metrics["centralCorpusAnswersUsed"] + metrics["lexiqueRescueAnswersUsed"],
        )
        self.assertGreaterEqual(metrics["centralCorpusAnswersUsed"], 95)


if __name__ == "__main__":
    unittest.main()
