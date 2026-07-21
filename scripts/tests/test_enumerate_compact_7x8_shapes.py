from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from enumerate_compact_7x8_shapes import (  # noqa: E402
    build_markdown_report,
    build_payload,
    enumerate_shape_space,
    enumerate_shapes,
    valid_row_patterns,
)


class EnumerateCompact7x8ShapesTests(unittest.TestCase):
    def test_only_four_row_patterns_can_avoid_short_across_answers(self) -> None:
        self.assertEqual(
            ["......", ".....#", "....##", "...###"],
            [
                "".join("#" if is_clue else "." for is_clue in pattern)
                for pattern in valid_row_patterns()
            ],
        )

    def test_exhaustive_strict_contract_has_four_silhouettes(self) -> None:
        shapes = enumerate_shapes()
        self.assertEqual(4, len(shapes))
        self.assertEqual(
            [[], [[4, 6]], [[4, 5], [4, 6]], [[4, 4], [4, 5], [4, 6]]],
            [shape["pivots"] for shape in shapes],
        )

    def test_enumeration_statistics_prove_the_search_is_exhaustive(self) -> None:
        shapes, stats = enumerate_shape_space()
        self.assertEqual(4**7, stats["rawLayoutCount"])
        self.assertEqual(len(shapes), stats["acceptedShapeCount"])
        self.assertEqual(4**7 - len(shapes), stats["rejectedLayoutCount"])
        self.assertEqual(
            stats["rejectedLayoutCount"],
            sum(stats["rejectedByReason"].values()),
        )
        self.assertEqual(2, stats["visualFamilyCount"])
        self.assertTrue(stats["allPivotSetsNested"])

    def test_every_pivot_is_a_central_right_edge_suffix(self) -> None:
        for shape in enumerate_shapes():
            pivots = [tuple(cell) for cell in shape["pivots"]]
            self.assertTrue(all(row == 4 for row, _ in pivots))
            if pivots:
                columns = [column for _, column in pivots]
                self.assertEqual(list(range(columns[0], 7)), columns)

    def test_every_slot_has_length_three_or_more(self) -> None:
        for shape in enumerate_shapes():
            self.assertGreaterEqual(shape["metrics"]["minimumAnswerLength"], 3)
            coverage = {}
            for slot in shape["slots"]:
                for cell in map(tuple, slot["cells"]):
                    coverage.setdefault(cell, set()).add(slot["direction"])
            self.assertEqual(shape["metrics"]["letterCells"], len(coverage))
            self.assertTrue(all(value == {"across", "down"} for value in coverage.values()))

    def test_coverage_audit_names_exactly_one_slot_per_axis(self) -> None:
        for shape in enumerate_shapes():
            audit = shape["coverageAudit"]
            self.assertTrue(audit["valid"])
            self.assertEqual(
                shape["metrics"]["letterCells"],
                audit["coveredExactlyOnceAcrossAndDown"],
            )
            self.assertEqual([], audit["isolatedClueCells"])
            self.assertEqual([], audit["orphanLetterCells"])
            for cell in audit["cells"]:
                self.assertTrue(cell["acrossSlotId"])
                self.assertTrue(cell["downSlotId"])

    def test_payload_and_report_state_the_visual_limit(self) -> None:
        payload = build_payload()
        self.assertEqual(2, payload["version"])
        self.assertEqual(4, payload["shapeCount"])
        report = build_markdown_report(payload)
        self.assertIn("4 silhouettes mathématiques", report)
        self.assertIn("2 familles visuelles", report)
        self.assertIn("flèches vers la gauche ou le haut", report)


if __name__ == "__main__":
    unittest.main()
