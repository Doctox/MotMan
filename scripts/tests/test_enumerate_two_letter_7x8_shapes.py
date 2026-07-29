from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from enumerate_two_letter_7x8_shapes import (  # noqa: E402
    analyze_line,
    build_payload,
    compatible_symmetry_fingerprints,
    enumerate_shape_space,
    valid_line_patterns,
)
from search_compact_grid_pilot import build_slots_from_shape  # noqa: E402


class EnumerateTwoLetter7x8ShapesTests(unittest.TestCase):
    def test_line_automata_keep_a_real_frame_answer(self) -> None:
        self.assertIsNone(analyze_line((True, False, False, False, False, False)))
        self.assertIsNone(analyze_line((False, True, False, False, False, False)))
        self.assertIsNotNone(analyze_line((False, False, True, False, False, False)))
        self.assertEqual(16, len(valid_line_patterns(6)))
        self.assertEqual(32, len(valid_line_patterns(7)))

    def test_exhaustive_enumeration_has_188_unique_shapes(self) -> None:
        shapes, stats = enumerate_shape_space()
        self.assertTrue(stats["exhaustive"])
        self.assertEqual(2**20, stats["rawLayoutCount"])
        self.assertEqual(2**20, stats["enumeratedMaskCount"])
        self.assertEqual(3_199, stats["structurallyValidBeforeTwoLetterQuota"])
        self.assertEqual(188, len(shapes))
        self.assertEqual(188, stats["acceptedShapeCount"])
        self.assertEqual(0, stats["duplicateFingerprintCount"])
        self.assertEqual({1: 41, 2: 147}, stats["twoLetterDistribution"])
        self.assertEqual(
            "0f3130a6a203365bd7c7203670261b57f16bf45152cf937b36692bc2df05a070",
            stats["acceptedMaskSha256"],
        )
        self.assertEqual(
            {1: 14, 2: 69, 3: 67, 4: 35, 5: 3},
            stats["acceptedPivotCountDistribution"],
        )

    def test_every_shape_respects_quota_coverage_and_canonical_builder(self) -> None:
        shapes, _stats = enumerate_shape_space()
        for shape in shapes:
            lengths = [slot["length"] for slot in shape["slots"]]
            self.assertIn(lengths.count(2), {1, 2})
            self.assertTrue(all(length == 2 or length >= 3 for length in lengths))
            self.assertEqual([], shape["coverageAudit"]["orphanLetterCells"])
            self.assertEqual([], shape["coverageAudit"]["isolatedClueCells"])
            parsed = build_slots_from_shape(shape)
            self.assertEqual(len(shape["slots"]), len(parsed[-1]))

    def test_no_direction_preserving_reflection_is_claimed(self) -> None:
        shapes, _stats = enumerate_shape_space()
        for shape in shapes[:20]:
            equivalents = compatible_symmetry_fingerprints({
                tuple(cell) for cell in shape["pivots"]
            })
            self.assertEqual({shape["fingerprint"]}, equivalents)

    def test_payload_is_staging_only_and_ranked(self) -> None:
        payload = build_payload()
        self.assertFalse(payload["catalogModified"])
        self.assertFalse(payload["runtimeModified"])
        self.assertFalse(payload["publicationEligible"])
        self.assertEqual(188, payload["shapeCount"])
        self.assertEqual(24, len(payload["recommendedShapeIds"]))
        scores = [shape["metrics"]["overallScore"] for shape in payload["shapes"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(17, payload["comparison"]["matchedActiveShapeCount"])
        self.assertEqual(5, payload["comparison"]["activeShapesOutsideNewContractCount"])


if __name__ == "__main__":
    unittest.main()
