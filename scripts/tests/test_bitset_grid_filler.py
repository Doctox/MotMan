from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from bitset_grid_filler import fill_bitset  # noqa: E402
from generate_grid_catalog import Slot  # noqa: E402


class BitsetGridFillerTests(unittest.TestCase):
    def test_minimum_image_count_is_enforced_before_acceptance(self) -> None:
        slots = [
            Slot("across", (row, -1), ((row, 0), (row, 1), (row, 2)))
            for row in range(3)
        ]
        words = ["CAT", "DOG", "FOX", "HEN"]
        indexes = (
            {3: words}, {},
            {word: 5.0 for word in words},
            {word: word for word in words},
            {word: set() for word in words},
            {word: "easy" for word in words},
            {"CAT", "DOG", "FOX"},
        )
        result = fill_bitset(
            slots, indexes, random.Random(4), None,
            require_image=True,
            minimum_images=3,
            max_seconds=1,
        )
        self.assertIsNotNone(result)
        self.assertEqual(3, sum(word in indexes[6] for word in result.values()))

    def test_undesirable_answer_quota_is_enforced_during_search(self) -> None:
        slots = [
            Slot("across", (0, -1), ((0, 0), (0, 1), (0, 2))),
            Slot("across", (1, -1), ((1, 0), (1, 1), (1, 2))),
        ]
        words = ["BAD", "CAT", "DOG"]
        indexes = (
            {3: words}, {},
            {"BAD": 100.0, "CAT": 1.0, "DOG": 1.0},
            {word: word for word in words},
            {word: set() for word in words},
            {word: "easy" for word in words},
            set(),
        )
        result = fill_bitset(
            slots, indexes, random.Random(2), None,
            require_image=False,
            undesirable_answers={"BAD"},
            max_undesirable_answers=0,
            max_seconds=1,
        )
        self.assertIsNotNone(result)
        self.assertNotIn("BAD", result.values())

    def test_required_image_slot_is_constrained_before_search(self) -> None:
        slots = [
            Slot("across", (row, -1), ((row, 0), (row, 1), (row, 2)))
            for row in range(2)
        ]
        words = ["CAT", "DOG", "FOX"]
        indexes = (
            {3: words}, {},
            {word: 5.0 for word in words},
            {word: word for word in words},
            {word: set() for word in words},
            {word: "easy" for word in words},
            {"CAT"},
        )
        result = fill_bitset(
            slots, indexes, random.Random(5), None,
            require_image=True,
            minimum_images=1,
            required_image_slots={1},
            max_seconds=1,
        )
        self.assertIsNotNone(result)
        self.assertEqual("CAT", result[1])
        self.assertNotEqual("CAT", result[0])

    def test_crossing_slots_share_the_exact_letter(self) -> None:
        slots = [
            Slot("across", (1, -1), ((1, 0), (1, 1), (1, 2))),
            Slot("down", (-1, 1), ((0, 1), (1, 1), (2, 1))),
        ]
        words = ["BAR", "CAT", "RAT"]
        indexes = (
            {3: words}, {},
            {word: 5.0 for word in words},
            {word: word for word in words},
            {word: set() for word in words},
            {word: "easy" for word in words},
            {"CAT"},
        )
        telemetry = {}
        result = fill_bitset(
            slots, indexes, random.Random(7), {"easy": 2, "normal": 0, "hard": 0},
            max_seconds=1, telemetry=telemetry,
        )
        self.assertIsNotNone(result)
        self.assertNotEqual(result[0], result[1])
        self.assertEqual(result[0][1], result[1][1])
        self.assertEqual("solved", telemetry["reason"])

    def test_cell_branching_groups_words_by_crossing_letter(self) -> None:
        slots = [
            Slot("across", (1, -1), ((1, 0), (1, 1), (1, 2))),
            Slot("down", (-1, 1), ((0, 1), (1, 1), (2, 1))),
        ]
        words = ["BAR", "BAT", "BIR", "BIT"]
        indexes = (
            {3: words}, {},
            {word: 5.0 for word in words},
            {word: word for word in words},
            {word: set() for word in words},
            {word: "easy" for word in words},
            set(),
        )
        telemetry = {}
        result = fill_bitset(
            slots, indexes, random.Random(8), None,
            require_image=False,
            branching_strategy="cell",
            max_seconds=1,
            telemetry=telemetry,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result[0][1], result[1][1])
        self.assertGreater(telemetry["cellBranchNodes"], 0)
        self.assertEqual("cell", telemetry["branchingStrategy"])

    def test_bounded_editorial_search_keeps_the_best_complete_fill(self) -> None:
        slots = [
            Slot("across", (1, -1), ((1, 0), (1, 1), (1, 2))),
            Slot("down", (-1, 1), ((0, 1), (1, 1), (2, 1))),
        ]
        # Greedy order starts with AXA (score 10), but that crossing forces
        # BXB (score 1).  Comparing both closures must retain AYA/BYB, whose
        # weakest answer is much better.
        words = ["AXA", "AYA", "BXB", "BYB"]
        scores = {"AXA": 10.0, "AYA": 8.0, "BXB": 1.0, "BYB": 8.0}
        indexes = (
            {3: words}, {}, scores,
            {word: word for word in words},
            {word: set() for word in words},
            {word: "easy" for word in words},
            set(),
        )
        telemetry = {}
        result = fill_bitset(
            slots, indexes, random.Random(9), None,
            require_image=False,
            quality_scores=scores,
            solution_limit=8,
            max_seconds=1,
            telemetry=telemetry,
        )
        self.assertIsNotNone(result)
        self.assertEqual({"AYA", "BYB"}, set(result.values()))
        self.assertEqual(4, telemetry["completeSolutions"])
        self.assertTrue(telemetry["qualityOptimized"])

    def test_slot_domain_can_be_restricted_without_fixing_one_answer(self) -> None:
        words = ["CAT", "DOG", "FOX"]
        indexes = (
            {3: words}, {}, {word: 5.0 for word in words},
            {word: word for word in words},
            {word: set() for word in words},
            {word: "easy" for word in words}, set(),
        )
        slots = [Slot("across", (0, -1), ((0, 0), (0, 1), (0, 2)))]
        result = fill_bitset(
            slots, indexes, random.Random(10), None,
            require_image=False,
            allowed_answers_by_slot={0: {"DOG", "FOX"}},
            max_seconds=1,
        )
        self.assertIsNotNone(result)
        self.assertIn(result[0], {"DOG", "FOX"})
        self.assertNotEqual("CAT", result[0])

    def test_compiled_wordlist_index_is_reused_between_shapes(self) -> None:
        words = ["CAT", "DOG", "FOX"]
        by_length = {3: words}
        difficulty = {word: "easy" for word in words}
        images = set()
        indexes = (
            by_length, {}, {word: 5.0 for word in words},
            {word: word for word in words},
            {word: set() for word in words}, difficulty, images,
        )
        slots = [Slot("across", (0, -1), ((0, 0), (0, 1), (0, 2)))]
        first = {}
        second = {}
        self.assertIsNotNone(fill_bitset(
            slots, indexes, random.Random(1), None,
            require_image=False, telemetry=first,
        ))
        self.assertIsNotNone(fill_bitset(
            slots, indexes, random.Random(2), None,
            require_image=False, telemetry=second,
        ))
        self.assertFalse(first["indexCacheHit"])
        self.assertTrue(second["indexCacheHit"])


if __name__ == "__main__":
    unittest.main()
