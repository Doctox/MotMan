from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from select_compact_7x8_raw import parse_selection  # noqa: E402


class SelectCompact7x8RawTests(unittest.TestCase):
    def test_selection_index_is_one_based(self) -> None:
        self.assertEqual((Path("lot.json"), 3), parse_selection("lot.json::3"))

    def test_selection_requires_positive_index(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_selection("lot.json::0")


if __name__ == "__main__":
    unittest.main()
