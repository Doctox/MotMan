from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from diagnose_fixed_shape_corpus_gaps import load_shape
from fill_fixed_ribbon_a01 import (
    DEFAULT_SHAPES,
    ROW_SEGMENTS,
    VERTICAL_SPECS,
    Trie,
    validate_fixed_layout,
)


class FixedRibbonA01Test(unittest.TestCase):
    def test_fixed_ribbon_plan_matches_reference_shape(self) -> None:
        shape, slots = load_shape(DEFAULT_SHAPES, "reference-ribbon-a-01")
        validate_fixed_layout(slots)
        self.assertEqual(shape["columns"], 9)
        self.assertEqual(shape["rows"], 10)
        self.assertEqual(len(slots), 22)
        self.assertEqual(
            sum(len(segment.columns) for row in ROW_SEGMENTS for segment in row),
            69,
        )
        self.assertEqual(len(VERTICAL_SPECS), 9)
        self.assertTrue(all(len(row) == 8 for row in VERTICAL_SPECS))

    def test_trie_keeps_only_exact_complete_words(self) -> None:
        trie = Trie.build(3, ("BUS", "BUT", "CAR"))
        b = trie.children[0]["B"]
        bu = trie.children[b]["U"]
        self.assertIsNone(trie.terminal[bu])
        self.assertEqual(trie.terminal[trie.children[bu]["S"]], "BUS")

    def test_reference_shape_file_itself_is_not_modified_by_solver(self) -> None:
        before = json.loads(DEFAULT_SHAPES.read_text(encoding="utf-8"))
        shape = next(
            item for item in before["shapes"]
            if item["id"] == "reference-ribbon-a-01"
        )
        self.assertTrue(shape["topology"]["valid"])
        self.assertEqual(shape["topology"]["orphanSegments"], [])


if __name__ == "__main__":
    unittest.main()
