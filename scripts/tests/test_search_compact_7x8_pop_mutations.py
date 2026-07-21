from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from search_compact_7x8_pop_mutations import anchor_sources  # noqa: E402


class CompactPopMutationTests(unittest.TestCase):
    def test_reads_fixed_pop_paths_from_raw_batches(self) -> None:
        anchors = anchor_sources([
            ROOT / "output/quality/compact-7x8-young-refills-soft-wave-03.json"
        ])
        answers = {anchor["answer"] for anchor in anchors}
        self.assertIn("OLAF", answers)
        self.assertIn("MARVEL", answers)
        for anchor in anchors:
            self.assertEqual(len(anchor["answer"]), len(anchor["cells"]))


if __name__ == "__main__":
    unittest.main()
