from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from search_compact_word_rectangle import grid_payload  # noqa: E402


class CompactWordRectangleTests(unittest.TestCase):
    def test_payload_is_a_complete_7x8_frame(self) -> None:
        rows = ["ABCDEF"] * 7
        columns = ["AAAAAAA", "BBBBBBB", "CCCCCCC", "DDDDDDD", "EEEEEEE", "FFFFFFF"]
        metadata = {
            answer: {"spelling": answer.lower(), "lemma": answer, "wordfreqZipf": 5.0, "constructorScore": 20.0}
            for answer in set(rows + columns)
        }
        payload = grid_payload(rows, columns, metadata)
        self.assertEqual((7, 8), (payload["columns"], payload["rows"]))
        self.assertEqual(13, len(payload["rawSlots"]))
        self.assertEqual(14, len(payload["clueCells"]))


if __name__ == "__main__":
    unittest.main()
