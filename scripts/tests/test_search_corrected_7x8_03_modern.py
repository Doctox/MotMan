import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from search_corrected_7x8_03_modern import (  # noqa: E402
    EXPECTED_LENGTHS,
    MODERN,
    ModernShape03Search,
    Policy,
    Selection,
    WordRecord,
    load_shape,
)


class Corrected03ModernSearchTests(unittest.TestCase):
    def test_shape_slot_order_is_locked(self) -> None:
        shape = load_shape(
            ROOT / "output/quality/corrected-7x8-shapes/corrected-shape-library.json"
        )
        self.assertEqual(
            tuple(slot["length"] for slot in shape["slots"]), EXPECTED_LENGTHS
        )

    def test_modern_quota_counts_answers_in_any_slot(self) -> None:
        search = ModernShape03Search(
            six=[WordRecord("STREAM")],
            seven=[WordRecord("NETFLIX")],
            short=[WordRecord("WEB")],
            four=[WordRecord("MEME")],
            active_usage=Counter(),
            avoid=None,
            policy=Policy(minimum_modern_answers=2),
            seed=1,
        )
        selected = search._add(
            search._add(Selection(), (search.records["NETFLIX"],)),
            (search.records["WEB"],),
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected.modern, 2)
        self.assertIn("NETFLIX", MODERN)
        self.assertIn("WEB", MODERN)

    def test_band_pattern_places_short_in_fifth_column(self) -> None:
        search = ModernShape03Search(
            six=[WordRecord("ABCDXY"), WordRecord("EFGHZI"), WordRecord("JKLMMO")],
            seven=[WordRecord("AAAAAAA")],
            short=[WordRecord("XZM")],
            four=[WordRecord("TEST")],
            active_usage=Counter(),
            avoid=None,
            policy=Policy(),
            seed=1,
        )
        options = search._band_options(
            ("ABCD", "EFGH", "JKLM", "TEST", "ABCD", "EFGH", "JKLM"),
            "YIOAAAA",
            (0, 1, 2),
        )
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0][0].answer, "XZM")

    def test_active_answer_stays_in_domain_with_score_penalty(self) -> None:
        search = ModernShape03Search(
            six=[WordRecord("MAISON", score=100.0)],
            seven=[WordRecord("NETFLIX")],
            short=[WordRecord("WEB")],
            four=[WordRecord("MEME")],
            active_usage=Counter({"MAISON": 2}),
            avoid=None,
            policy=Policy(active_repeat_penalty=30.0),
            seed=1,
        )
        self.assertIn("MAISON", search.records)
        self.assertEqual(search.records["MAISON"].score, 40.0)

    def test_rotation_cooldown_answer_is_hard_excluded(self) -> None:
        search = ModernShape03Search(
            six=[WordRecord("MAISON"), WordRecord("STREAM")],
            seven=[WordRecord("NETFLIX")],
            short=[WordRecord("WEB")],
            four=[WordRecord("MEME")],
            active_usage=Counter({"MAISON": 2}),
            avoid=None,
            policy=Policy(),
            seed=1,
            rotation_cooldown={"STREAM"},
        )
        self.assertIn("MAISON", search.records)
        self.assertNotIn("STREAM", search.records)


if __name__ == "__main__":
    unittest.main()
