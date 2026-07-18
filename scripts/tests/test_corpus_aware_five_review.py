from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_corpus_aware_five_review as review  # noqa: E402
from editorial_quality import editorial_errors  # noqa: E402
from grid_topology import audit_grid_topology  # noqa: E402


class CorpusAwareFiveReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.grids = review.build_grids()

    def test_approved_shapes_are_frozen_and_topologically_valid(self) -> None:
        self.assertEqual(
            tuple(grid["shapeFingerprint"] for grid in self.grids),
            review.EXPECTED_SHAPE_FINGERPRINTS,
        )
        self.assertEqual(len(self.grids), 5)
        for grid in self.grids:
            report = audit_grid_topology(grid)
            self.assertTrue(report["valid"], report["errors"])
            self.assertEqual(len(report["cells"]), 90)

    def test_batch_has_no_answer_or_inflection_repetition(self) -> None:
        answers = [
            word["answer"] for grid in self.grids for word in grid["words"]
        ]
        self.assertEqual(len(answers), 127)
        self.assertEqual(len(set(answers)), 127)
        answer_set = set(answers)
        self.assertFalse([
            answer for answer in answer_set
            if len(answer) >= 3 and f"{answer}S" in answer_set
        ])

    def test_every_clue_is_manual_or_a_valid_image(self) -> None:
        images_per_grid = []
        for grid in self.grids:
            image_count = 0
            for word in grid["words"]:
                self.assertFalse(editorial_errors(word, root=ROOT), word["answer"])
                if word.get("image"):
                    image_count += 1
                    self.assertEqual(word["clue"], "")
                else:
                    self.assertEqual(word["clue"], review.CLUES[word["answer"]])
                    self.assertEqual(word["editorialStatus"], "human-reviewed")
            images_per_grid.append(image_count)
        self.assertEqual(images_per_grid, [2, 1, 2, 1, 2])
        self.assertEqual(Counter(images_per_grid), Counter({2: 3, 1: 2}))


if __name__ == "__main__":
    unittest.main()
