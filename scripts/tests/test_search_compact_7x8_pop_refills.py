from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from search_compact_7x8_pop_refills import approved_shapes, parse_args  # noqa: E402


class CompactPopRefillTests(unittest.TestCase):
    def test_extracts_only_unique_playable_shapes(self) -> None:
        catalog = json.loads(
            (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
        )
        shapes = approved_shapes(catalog)
        fingerprints = {tuple(shape["pivots"]) for shape in shapes}
        self.assertEqual(len(shapes), len(fingerprints))
        self.assertGreaterEqual(len(shapes), 10)
        self.assertTrue(all(shape["slots"] for shape in shapes))

    def test_plain_fallback_and_short_active_pool_are_opt_in(self) -> None:
        argv = [
            "refill", "--output", "candidate.json", "--allow-plain",
            "--allow-active-answer-max-length", "3",
        ]
        with patch.object(sys, "argv", argv):
            args = parse_args()
        self.assertTrue(args.allow_plain)
        self.assertEqual(3, args.allow_active_answer_max_length)


if __name__ == "__main__":
    unittest.main()
