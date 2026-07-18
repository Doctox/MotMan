from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class AllUsedShapesPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.panel = json.loads(
            (ROOT / "output/quality/all-used-shapes-panel.json").read_text(encoding="utf-8")
        )

    def test_only_approved_new_templates_are_shown(self) -> None:
        self.assertEqual(
            {"long-answer-shape-01", "long-answer-shape-04", "long-answer-shape-05"},
            {shape["id"] for shape in self.panel["approvedTemplates"]},
        )
        self.assertEqual(
            ["long-answer-shape-02", "long-answer-shape-03"],
            self.panel["metrics"]["rejectedTemplatesExcluded"],
        )

    def test_every_displayed_shape_is_unique(self) -> None:
        shapes = [
            *self.panel["approvedTemplates"],
            *self.panel["playableCatalogShapes"],
        ]
        self.assertEqual(
            self.panel["metrics"]["totalUniqueShapes"], len(shapes)
        )
        self.assertEqual(len(shapes), len({shape["fingerprint"] for shape in shapes}))


if __name__ == "__main__":
    unittest.main()
