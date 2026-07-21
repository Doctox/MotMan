from __future__ import annotations

import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from enumerate_corrected_7x8_shapes import (  # noqa: E402
    build_payload,
    enumerate_shape_space,
    pattern_text,
    valid_line_patterns,
)


class CorrectedSevenByEightShapeTests(unittest.TestCase):
    def test_singletons_expand_each_row_to_seven_legal_patterns(self):
        self.assertEqual(
            ["......", ".....#", "....#.", "....##", "...#.#", "...##.", "...###"],
            [pattern_text(audit.clues) for audit in valid_line_patterns(6)],
        )

    def test_exhaustive_space_contains_exactly_seven_shapes(self):
        shapes, stats = enumerate_shape_space()
        self.assertEqual(7**7, stats["rawLayoutCount"])
        self.assertEqual(7, stats["acceptedShapeCount"])
        self.assertEqual(7, len(shapes))
        self.assertEqual(
            stats["rawLayoutCount"],
            stats["columnPrefixPrunedLayoutCount"] + stats["columnCompatibleLayoutCount"],
        )
        self.assertEqual(
            stats["columnCompatibleLayoutCount"],
            len(shapes) + sum(stats["rejectedByReason"].values()),
        )

    def test_all_internal_clues_are_forced_onto_row_four(self):
        shapes, stats = enumerate_shape_space()
        self.assertEqual([4], stats["independentInternalClueRows"])
        self.assertEqual(
            [
                [],
                [[4, 6]],
                [[4, 5]],
                [[4, 5], [4, 6]],
                [[4, 4], [4, 6]],
                [[4, 4], [4, 5]],
                [[4, 4], [4, 5], [4, 6]],
            ],
            [shape["pivots"] for shape in shapes],
        )

    def test_every_clue_launches_and_every_letter_is_covered(self):
        shapes, _ = enumerate_shape_space()
        for shape in shapes:
            launches = Counter(tuple(slot["clueCell"]) for slot in shape["slots"])
            for clue in map(tuple, shape["clueCells"]):
                if clue != (0, 0):
                    self.assertGreaterEqual(launches[clue], 1)
            coverage = defaultdict(set)
            for slot in shape["slots"]:
                self.assertGreaterEqual(slot["length"], 3)
                self.assertIn(slot["arrow"], {"right", "down"})
                self.assertEqual(len(slot["cells"]), slot["length"])
                for cell in map(tuple, slot["cells"]):
                    coverage[cell].add(slot["direction"])
            audit = shape["coverageAudit"]
            self.assertTrue(audit["valid"])
            self.assertEqual(audit["letterCellCount"], len(coverage))
            self.assertEqual([], audit["orphanLetterCells"])
            self.assertTrue(all(coverage.values()))

    def test_corrected_contract_keeps_safe_single_axis_cells(self):
        shapes, _ = enumerate_shape_space()
        broken = next(shape for shape in shapes if shape["pivots"] == [[4, 5]])
        singleton_cell = next(
            cell for cell in broken["coverageAudit"]["cells"]
            if cell["cell"] == [4, 6]
        )
        self.assertIsNone(singleton_cell["acrossSlotId"])
        self.assertIsNotNone(singleton_cell["downSlotId"])
        self.assertEqual(1, singleton_cell["coveredAxes"])

    def test_recommended_pilot_is_the_low_short_no_singleton_compromise(self):
        payload = build_payload()
        self.assertFalse(payload["genuinelyDiverseTripletExists"])
        self.assertEqual("corrected-7x8-02", payload["recommendedPilotShapeId"])
        recommended = next(
            shape for shape in payload["shapes"]
            if shape["shapeId"] == payload["recommendedPilotShapeId"]
        )
        self.assertEqual([[4, 6]], recommended["pivots"])
        self.assertEqual(2, recommended["metrics"]["threeLetterAnswers"])
        self.assertEqual(0, recommended["metrics"]["singletonAcrossRuns"])
        self.assertEqual(0, recommended["metrics"]["singletonDownRuns"])
        self.assertEqual(
            {"3": 2, "5": 1, "6": 6, "7": 5},
            recommended["metrics"]["lengthHistogram"],
        )


if __name__ == "__main__":
    unittest.main()
