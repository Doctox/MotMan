from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from word_rectangle_filler import RectangleEntry, fill_word_rectangle  # noqa: E402


def entry(answer: str, **overrides) -> RectangleEntry:
    values = {
        "answer": answer,
        "family": answer,
        "quality": 10.0,
        "zipf": 5.0,
    }
    values.update(overrides)
    return RectangleEntry(**values)


class WordRectangleFillerTests(unittest.TestCase):
    def test_closes_two_distinct_rectangles_and_exports_telemetry(self) -> None:
        horizontal = [entry(word) for word in ("AB", "CD", "EF", "GH")]
        vertical = [entry(word) for word in ("AC", "BD", "EG", "FH")]
        result = fill_word_rectangle(
            horizontal,
            vertical,
            row_count=2,
            column_count=2,
            seed=1,
            max_seconds=1,
            solution_limit=2,
            orientation="column-first",
        )
        self.assertTrue(result["complete"])
        self.assertEqual(2, len(result["solutions"]))
        self.assertEqual("prefix-trie-word-rectangle-v3", result["telemetry"]["solver"])
        self.assertEqual("solution_limit", result["telemetry"]["reason"])

    def test_family_collision_is_rejected(self) -> None:
        horizontal = [entry("AB", family="SAME"), entry("CD")]
        vertical = [entry("AC", family="SAME"), entry("BD")]
        result = fill_word_rectangle(
            horizontal,
            vertical,
            row_count=2,
            column_count=2,
            seed=1,
            max_seconds=1,
            solution_limit=1,
        )
        self.assertFalse(result["complete"])
        self.assertGreater(result["telemetry"]["familyPrunes"], 0)

    def test_familiarity_budget_is_applied_to_both_axes(self) -> None:
        horizontal = [entry("AB", unfamiliar=True), entry("CD")]
        vertical = [entry("AC"), entry("BD", unfamiliar=True)]
        result = fill_word_rectangle(
            horizontal,
            vertical,
            row_count=2,
            column_count=2,
            seed=1,
            max_seconds=1,
            solution_limit=1,
            max_unfamiliar_answers=1,
        )
        self.assertFalse(result["complete"])
        self.assertGreater(result["telemetry"]["budgetPrunes"], 0)

    def test_no_good_distance_rejects_an_exact_rectangle(self) -> None:
        horizontal = [entry("AB"), entry("CD")]
        vertical = [entry("AC"), entry("BD")]
        reference = [{0: "AC", 1: "BD", 2: "AB", 3: "CD"}]
        result = fill_word_rectangle(
            horizontal,
            vertical,
            row_count=2,
            column_count=2,
            seed=1,
            max_seconds=1,
            solution_limit=1,
            reference_solutions=reference,
            minimum_solution_distance=1,
        )
        self.assertFalse(result["complete"])
        self.assertEqual(
            {"0": 1}, result["telemetry"]["diversityRejectedByDistance"]
        )

    def test_node_cutoff_resumes_only_after_fully_completed_roots(self) -> None:
        horizontal = [entry(word) for word in ("AB", "CD", "EF", "GH")]
        vertical = [entry(word) for word in ("AC", "BD", "EG", "FH")]
        interrupted = fill_word_rectangle(
            horizontal,
            vertical,
            row_count=2,
            column_count=2,
            seed=1,
            max_seconds=1,
            node_limit=4,
            solution_limit=10,
        )
        checkpoint = interrupted["checkpoint"]

        self.assertEqual("node_limit_with_solutions", interrupted["telemetry"]["reason"])
        self.assertEqual(["EF"], checkpoint["completedRootBranches"])
        self.assertEqual(1, len(checkpoint["provenSolutions"]))

        resumed = fill_word_rectangle(
            horizontal,
            vertical,
            row_count=2,
            column_count=2,
            seed=1,
            max_seconds=1,
            node_limit=100,
            solution_limit=10,
            completed_root_branches=checkpoint["completedRootBranches"],
            initial_solutions=checkpoint["provenSolutions"],
        )

        self.assertEqual(1, resumed["telemetry"]["skippedRootBranches"])
        self.assertEqual(1, resumed["telemetry"]["completedRootBranchesThisRun"])
        self.assertEqual(2, resumed["telemetry"]["completedRootBranches"])
        self.assertEqual(2, len(resumed["solutions"]))
        self.assertEqual("exhausted_with_solutions", resumed["telemetry"]["reason"])


if __name__ == "__main__":
    unittest.main()
