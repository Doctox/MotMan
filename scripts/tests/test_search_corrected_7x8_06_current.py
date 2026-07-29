import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from search_corrected_7x8_06_current import (  # noqa: E402
    CURRENT,
    EXPECTED_LENGTHS,
    STRONG,
    CurrentShape06Search,
    Policy,
    Selection,
    WordRecord,
    load_shape,
)


class Corrected06CurrentSearchTests(unittest.TestCase):
    def test_shape_slot_order_is_locked(self) -> None:
        shape = load_shape(
            ROOT / "output/quality/corrected-7x8-shapes/corrected-shape-library.json"
        )
        self.assertEqual(
            tuple(slot["length"] for slot in shape["slots"]), EXPECTED_LENGTHS
        )

    def test_current_and_strong_quota_are_independent(self) -> None:
        search = CurrentShape06Search(
            six=[WordRecord("STREAM")], seven=[WordRecord("NETFLIX")],
            short=[WordRecord("WEB")], active_usage=Counter(),
            policy=Policy(), seed=1,
        )
        selection = search._add(
            Selection(), (search.records["STREAM"], search.records["WEB"])
        )
        self.assertIsNotNone(selection)
        self.assertEqual(selection.current, 2)
        self.assertEqual(selection.strong, 2)
        self.assertIn("STREAM", CURRENT)
        self.assertIn("WEB", STRONG)

    def test_active_answer_is_penalized_but_stays_available(self) -> None:
        search = CurrentShape06Search(
            six=[WordRecord("STREAM"), WordRecord("CASQUE")],
            seven=[WordRecord("NETFLIX")], short=[WordRecord("WEB")],
            active_usage=Counter({"STREAM": 1}), policy=Policy(), seed=1,
        )
        self.assertIn("STREAM", search.records)
        self.assertIn("CASQUE", search.records)

    def test_explicit_cooldown_is_a_hard_pool_exclusion(self) -> None:
        search = CurrentShape06Search(
            six=[WordRecord("STREAM"), WordRecord("CASQUE")],
            seven=[WordRecord("NETFLIX")], short=[WordRecord("WEB")],
            active_usage=Counter({"STREAM": 1}),
            cooldown_answers={"STREAM"}, policy=Policy(), seed=1,
        )
        self.assertNotIn("STREAM", search.records)
        self.assertIn("CASQUE", search.records)


if __name__ == "__main__":
    unittest.main()
