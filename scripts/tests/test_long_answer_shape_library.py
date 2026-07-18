from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_long_answer_shape_pilot import band_counts, template_grid  # noqa: E402
from grid_topology import audit_grid_topology  # noqa: E402


class LongAnswerShapeLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(
            (ROOT / "src/data/grid-generation-handcrafted/long-answer-shapes.review.json")
            .read_text(encoding="utf-8")
        )

    def test_statuses_and_fingerprints(self) -> None:
        shapes = self.document["shapes"]
        self.assertEqual(5, len(shapes))
        statuses = {shape["id"]: shape["publicationStatus"] for shape in shapes}
        self.assertEqual({
            "long-answer-shape-01": "owner-approved",
            "long-answer-shape-02": "owner-rejected-similar",
            "long-answer-shape-03": "owner-rejected-similar",
            "long-answer-shape-04": "owner-approved",
            "long-answer-shape-05": "owner-approved",
        }, statuses)
        fingerprints = {
            tuple(sorted(tuple(cell) for cell in shape["clueCells"]))
            for shape in shapes
        }
        self.assertEqual(5, len(fingerprints))

    def test_every_shape_is_covered_and_long_majority(self) -> None:
        for shape in self.document["shapes"]:
            short, long = band_counts(shape["metrics"]["lengths"])
            self.assertGreater(long, short, shape["id"])
            self.assertLessEqual(max(map(int, shape["metrics"]["lengths"])), 8)
            topology = audit_grid_topology(template_grid(shape), enforce_layout=False)
            self.assertTrue(topology["valid"], (shape["id"], topology["errors"]))
            self.assertEqual([], topology["orphanSegments"])
            self.assertTrue(all(slot["arrow"] in {"right", "down"} for slot in shape["slots"]))


if __name__ == "__main__":
    unittest.main()
