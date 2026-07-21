from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from search_corrected_7x8_02_columns import (  # noqa: E402
    CorrectedShape02ColumnSearch,
    SearchPolicy,
)
from strict_ribbon_row_dfs import SearchResult, WordRecord  # noqa: E402


ROWS = (
    "SPKMKF",
    "YYTXJD",
    "AHNZPJ",
    "SLWXZ",
    "ETBEGE",
    "YTTXGL",
    "TDYWCK",
)


def make(answer: str, *, family: str | None = None) -> WordRecord:
    return WordRecord(
        answer=answer, score=10.0, zipf=5.0,
        family=family or answer, image=False, grammar=False,
    )


def fixture(*, duplicate_short_family: bool = False):
    verticals = tuple(
        "".join(ROWS[row][column] for row in range(7))
        for column in range(5)
    )
    top_short = "".join(ROWS[row][5] for row in range(3))
    bottom_short = "".join(ROWS[row][5] for row in range(4, 7))
    top = tuple(ROWS[:3])
    bottom = tuple(ROWS[4:])
    expected = (*verticals, top_short, *top, ROWS[3], bottom_short, *bottom)
    short_records = [
        make(top_short),
        make(bottom_short, family=top_short if duplicate_short_family else bottom_short),
    ]
    return {
        "six": [make(answer) for answer in (*top, *bottom)],
        "seven": [make(answer) for answer in verticals],
        "short": short_records,
        "five": [make(ROWS[3])],
        "expected": expected,
    }


class CorrectedShape02ColumnSearchTests(unittest.TestCase):
    def test_five_columns_induce_the_complete_exact_fill(self):
        data = fixture()
        search = CorrectedShape02ColumnSearch(
            six=data["six"], seven=data["seven"], short=data["short"],
            five=data["five"], active_usage=Counter(),
            policy=SearchPolicy(seconds=2, solution_limit=3, minimum_solution_distance=1),
            seed=4,
        )
        result, candidates = search.solve()
        self.assertEqual(SearchResult.FOUND, result)
        self.assertEqual(1, len(candidates))
        candidate = candidates[0]
        self.assertEqual(list(data["expected"]), candidate["answers"])
        self.assertTrue(candidate["audit"]["valid"])
        self.assertTrue(candidate["audit"]["crossingLettersMatch"])
        self.assertTrue(candidate["audit"]["shortExtensionsMatch"])
        self.assertEqual(14, candidate["audit"]["uniqueAnswerCount"])
        self.assertEqual(14, candidate["audit"]["uniqueFamilyCount"])

    def test_duplicate_family_blocks_an_otherwise_complete_fill(self):
        data = fixture(duplicate_short_family=True)
        search = CorrectedShape02ColumnSearch(
            six=data["six"], seven=data["seven"], short=data["short"],
            five=data["five"], active_usage=Counter(),
            policy=SearchPolicy(seconds=2, solution_limit=3), seed=4,
        )
        result, candidates = search.solve()
        self.assertEqual(SearchResult.DEAD, result)
        self.assertEqual([], candidates)
        self.assertGreater(search.rejections["duplicate-family"], 0)

    def test_active_answer_gate_is_hard_and_reported(self):
        data = fixture()
        search = CorrectedShape02ColumnSearch(
            six=data["six"], seven=data["seven"], short=data["short"],
            five=data["five"], active_usage=Counter({data["expected"][0]: 1}),
            policy=SearchPolicy(seconds=2, solution_limit=3, maximum_active_answers=0),
            seed=4,
        )
        result, candidates = search.solve()
        self.assertEqual(SearchResult.DEAD, result)
        self.assertEqual([], candidates)
        self.assertGreater(search.rejections["active-answer"], 0)

    def test_zero_budget_is_an_honest_cutoff(self):
        data = fixture()
        search = CorrectedShape02ColumnSearch(
            six=data["six"], seven=data["seven"], short=data["short"],
            five=data["five"],
            policy=SearchPolicy(seconds=0, solution_limit=1), seed=4,
        )
        result, candidates = search.solve()
        self.assertEqual(SearchResult.CUTOFF, result)
        self.assertEqual([], candidates)
        self.assertEqual("deadline reached; no infeasibility claim", search.telemetry(result)["proof"])


if __name__ == "__main__":
    unittest.main()
