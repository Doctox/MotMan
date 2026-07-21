from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from llm_fill_attempt_registry import (  # noqa: E402
    attempt_signature,
    select_state_path,
    should_skip,
)


class LlmFillAttemptRegistryTests(unittest.TestCase):
    def test_signature_is_order_independent(self) -> None:
        first = attempt_signature("shape-a", ["MARIO", "DOFUS"], ["CHAT", "PIZZA"], "p1")
        second = attempt_signature("shape-a", ["DOFUS", "MARIO"], ["PIZZA", "CHAT"], "p1")
        self.assertEqual(first, second)

    def test_policy_change_reopens_an_attempt(self) -> None:
        self.assertNotEqual(
            attempt_signature("shape-a", ["MARIO"], [], "policy-1"),
            attempt_signature("shape-a", ["MARIO"], [], "policy-2"),
        )

    def test_exact_partial_layout_distinguishes_same_words(self) -> None:
        first = attempt_signature(
            "shape-a",
            ["MARIO"],
            ["CASQUE"],
            "policy-1",
            {"placements": [{"answer": "CASQUE", "row": 2, "column": 1}]},
        )
        second = attempt_signature(
            "shape-a",
            ["MARIO"],
            ["CASQUE"],
            "policy-1",
            {"placements": [{"answer": "CASQUE", "row": 3, "column": 1}]},
        )
        self.assertNotEqual(first, second)

    def test_partial_layout_digest_is_key_order_independent(self) -> None:
        first = attempt_signature(
            "shape-a", [], [], "policy-1", {"rows": 8, "columns": 7}
        )
        second = attempt_signature(
            "shape-a", [], [], "policy-1", {"columns": 7, "rows": 8}
        )
        self.assertEqual(first, second)

    def test_select_state_path_from_report(self) -> None:
        report = {"conceptions": [{"id": "a"}, {"id": "b"}]}
        self.assertEqual(select_state_path(report, "conceptions.1"), {"id": "b"})

    def test_timeout_gets_one_deeper_retry(self) -> None:
        self.assertFalse(should_skip([{"status": "timeout"}]))
        self.assertTrue(should_skip([{"status": "timeout"}, {"status": "timeout"}]))
        self.assertTrue(should_skip([{"status": "unfillable"}]))


if __name__ == "__main__":
    unittest.main()
