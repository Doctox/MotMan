from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from scan_modern_anchor_compatibility import compile_domains  # noqa: E402
from scan_reviewed_single_anchor_7x8 import (  # noqa: E402
    anchor_patterns,
    propagate_single_anchor,
    strict_construction_indexes,
)
from search_compact_grid_pilot import Slot  # noqa: E402


class ReviewedSingleAnchorScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.slots = [
            Slot(0, "a", "across", (0, -1), ((0, 0), (0, 1), (0, 2))),
            Slot(1, "d", "down", (-1, 0), ((0, 0), (1, 0), (2, 0))),
        ]

    def test_anchor_propagation_keeps_only_crossing_support(self) -> None:
        indexed = {3: ("ABC", "DEF", "AXX", "DXX")}
        word_index, masks = compile_domains(indexed)
        result = propagate_single_anchor(
            self.slots, indexed, word_index, masks, 0, "ABC"
        )
        self.assertTrue(result["survives"])
        self.assertEqual(1, result["minimumRemainingDomain"])

    def test_anchor_propagation_reports_root_wipeout(self) -> None:
        indexed = {3: ("ABC", "DEF", "DXX")}
        word_index, masks = compile_domains(indexed)
        result = propagate_single_anchor(
            self.slots, indexed, word_index, masks, 0, "ABC"
        )
        self.assertFalse(result["survives"])
        self.assertEqual("crossing-domain-wipeout", result["reason"])

    def test_anchor_patterns_show_only_imposed_letters(self) -> None:
        self.assertEqual({"1": "A??"}, anchor_patterns(self.slots, 0, "ABC"))

    def test_reviewed_rescue_noun_is_not_rejected_with_bad_inflected_family(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rescue.json"
            path.write_text(json.dumps({"entries": [{
                "answer": "ALERTE",
                "lemma": "alerte",
                "partOfSpeech": "common-noun",
                "formType": "lemma",
                "editorialStatus": "human-reviewed",
                "register": "daily-common",
            }]}), encoding="utf-8")
            indexes, _metadata, rescue, _current = strict_construction_indexes(
                {6}, path, 3.2, 5.0
            )
        self.assertIn("ALERTE", rescue)
        self.assertIn("ALERTE", indexes[0][6])


if __name__ == "__main__":
    unittest.main()
