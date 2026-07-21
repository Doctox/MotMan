from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from strict_ribbon_row_dfs import (  # noqa: E402
    RibbonRowSolver,
    SearchConfig,
    SearchResult,
    WordRecord,
    parse_fixed_answer,
    ribbon_geometry,
    slot_lengths,
    validate_fixed_answers,
)


ROWS = (
    "SPKMKF",
    "YYTXJD",
    "AHNZPJ",
    "SLWXZN",
    "ETBEGE",
    "YTTXGL",
    "TDYWCK",
)


def fixture(long_columns: int):
    verticals = tuple(
        "".join(ROWS[row][column] for row in range(7))
        for column in range(long_columns)
    )
    top_shorts = tuple(
        "".join(ROWS[row][column] for row in range(3))
        for column in range(long_columns, 6)
    )
    bottom_shorts = tuple(
        "".join(ROWS[row][column] for row in range(4, 7))
        for column in range(long_columns, 6)
    )
    middle = ROWS[3][:long_columns]
    answers = (*verticals, *top_shorts, *ROWS[:3], middle, *bottom_shorts, *ROWS[4:])
    assert len(answers) == len(set(answers)) == 19 - long_columns
    make = lambda answer: WordRecord(answer, score=10.0, zipf=5.0, family=answer)
    return {
        "six": [make(answer) for answer in (*ROWS[:3], *ROWS[4:])],
        "seven": [make(answer) for answer in verticals],
        "short": [make(answer) for answer in (*top_shorts, *bottom_shorts)],
        "middle": [make(middle)],
        "answers": answers,
    }


class RibbonRowSolverTests(unittest.TestCase):
    def solve_fixture(self, long_columns: int, **kwargs):
        data = fixture(long_columns)
        solver = RibbonRowSolver(
            six=data["six"], seven=data["seven"], short=data["short"],
            middle=data["middle"],
            config=SearchConfig(long_columns=long_columns, seconds=5.0),
            seed=7, **kwargs,
        )
        result, solution = solver.solve()
        return data, solver, result, solution

    def test_closes_each_strict_ribbon_exactly(self):
        for long_columns in (3, 4, 5):
            with self.subTest(long_columns=long_columns):
                data, solver, result, solution = self.solve_fixture(long_columns)
                self.assertEqual(SearchResult.FOUND, result)
                self.assertIsNotNone(solution)
                self.assertEqual(list(data["answers"]), solution["answers"])
                self.assertEqual("exact complete fill", solver.telemetry(result)["proof"])

    def test_geometry_covers_all_56_cells(self):
        for long_columns in (3, 4, 5):
            geometry = ribbon_geometry(long_columns, fixture(long_columns)["answers"])
            clue_cells = {tuple(cell) for cell in geometry["clueCells"]}
            letter_cells = {
                tuple(cell) for slot in geometry["slots"] for cell in slot["cells"]
            }
            self.assertEqual(56, len(clue_cells | letter_cells))
            self.assertFalse(clue_cells & letter_cells)
            self.assertEqual(19 - long_columns, len(geometry["slots"]))
            for slot in geometry["slots"]:
                self.assertEqual(len(slot["answer"]), len(slot["cells"]))

    def test_fixed_answer_parser_normalizes_accents(self):
        self.assertEqual((9, "CHENE"), parse_fixed_answer("9:chêne"))

    def test_slot_lengths_follow_solution_payload_order(self):
        self.assertEqual(
            (7, 7, 7, 7, 7, 3, 6, 6, 6, 5, 3, 6, 6, 6),
            slot_lengths(5),
        )

    def test_fixed_answers_cover_each_structural_stage(self):
        data = fixture(5)
        fixed = {
            slot: data["answers"][slot]
            for slot in (0, 5, 6, 9, 10, 11)
        }
        _, _, result, solution = self.solve_fixture(5, fixed_answers=fixed)
        self.assertEqual(SearchResult.FOUND, result)
        self.assertEqual(list(data["answers"]), solution["answers"])

    def test_eligible_but_incompatible_fixed_answer_is_proven_dead(self):
        data = fixture(5)
        solver = RibbonRowSolver(
            six=data["six"], seven=data["seven"], short=data["short"],
            middle=data["middle"],
            config=SearchConfig(long_columns=5, seconds=5.0),
            fixed_answers={6: data["answers"][11]}, seed=7,
        )
        result, solution = solver.solve()
        self.assertEqual(SearchResult.DEAD, result)
        self.assertIsNone(solution)

    def test_fixed_answer_validation_rejects_length_domain_and_duplicates(self):
        data = fixture(5)
        arguments = {
            "long_columns": 5,
            "six": data["six"],
            "seven": data["seven"],
            "short": data["short"],
            "middle": data["middle"],
        }
        with self.assertRaisesRegex(ValueError, "Longueur invalide"):
            validate_fixed_answers([(0, "ABC")], **arguments)
        with self.assertRaisesRegex(ValueError, "domaine éligible"):
            validate_fixed_answers([(0, "XXXXXXX")], **arguments)
        with self.assertRaisesRegex(ValueError, "plusieurs fois"):
            validate_fixed_answers(
                [(0, data["answers"][0]), (0, data["answers"][0])],
                **arguments,
            )

    def test_fixed_answer_changes_context_hash(self):
        data = fixture(5)
        common = {
            "six": data["six"], "seven": data["seven"],
            "short": data["short"], "middle": data["middle"],
            "config": SearchConfig(long_columns=5, seconds=5.0), "seed": 7,
        }
        free = RibbonRowSolver(**common)
        fixed = RibbonRowSolver(**common, fixed_answers={0: data["answers"][0]})
        self.assertNotEqual(free.context_hash, fixed.context_hash)

    def test_unique_fill_becomes_proven_dead_when_forbidden_by_no_good(self):
        data = fixture(4)
        solver = RibbonRowSolver(
            six=data["six"], seven=data["seven"], short=data["short"],
            middle=data["middle"],
            config=SearchConfig(long_columns=4, seconds=5.0, minimum_solution_distance=1),
            avoid_fills=[data["answers"]], seed=7,
        )
        result, solution = solver.solve()
        self.assertEqual(SearchResult.DEAD, result)
        self.assertIsNone(solution)
        self.assertEqual("all structural branches exhausted", solver.telemetry(result)["proof"])

    def test_cutoff_is_never_persisted_as_dead(self):
        data = fixture(5)
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "dead.sqlite3"
            solver = RibbonRowSolver(
                six=data["six"], seven=data["seven"], short=data["short"],
                middle=data["middle"],
                config=SearchConfig(long_columns=5, seconds=0.0),
                cache_path=cache, fixed_answers={0: data["answers"][0]}, seed=7,
            )
            result, solution = solver.solve()
            self.assertEqual(SearchResult.CUTOFF, result)
            self.assertIsNone(solution)
            connection = sqlite3.connect(cache)
            try:
                count = connection.execute("SELECT COUNT(*) FROM dead_states").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(0, count)


if __name__ == "__main__":
    unittest.main()
