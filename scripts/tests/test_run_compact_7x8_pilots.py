from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from run_compact_7x8_pilots import (  # noqa: E402
    attempt_status,
    candidate_key,
    parse_args,
    rank_fill,
    reusable_attempt,
)


class RunCompact7x8PilotsTests(unittest.TestCase):
    def test_candidate_key_depends_on_order_and_shape(self) -> None:
        self.assertNotEqual(
            candidate_key("a", ["CHAT", "CHIEN"]),
            candidate_key("a", ["CHIEN", "CHAT"]),
        )
        self.assertNotEqual(candidate_key("a", ["CHAT"]), candidate_key("b", ["CHAT"]))

    def test_inflected_verb_is_heavily_penalized(self) -> None:
        clean_score, clean = rank_fill(
            ["RESTER"],
            {"RESTER": {
                "spelling": "rester", "constructorScore": 50,
                "partOfSpeech": "verb", "formType": "lemma",
            }},
            set(),
        )
        bad_score, bad = rank_fill(
            ["FILAIT"],
            {"FILAIT": {
                "spelling": "filait", "constructorScore": 50,
                "partOfSpeech": "verb", "formType": "inflected",
            }},
            set(),
        )
        self.assertGreater(clean_score, bad_score)
        self.assertEqual(1, bad["inflectedVerbs"])
        self.assertEqual(0, clean["inflectedVerbs"])

    def test_attempt_status_preserves_dead_and_cutoff_states(self) -> None:
        self.assertEqual("solved", attempt_status({"complete": True}))
        self.assertEqual(
            "dead",
            attempt_status({
                "complete": False,
                "solverTelemetry": {"reason": "infeasible"},
            }),
        )
        self.assertEqual(
            "cutoff",
            attempt_status({
                "complete": False,
                "solverTelemetry": {"reason": "timeout"},
            }),
        )

    def test_exact_cutoff_is_reused_but_missing_output_is_not(self) -> None:
        self.assertTrue(reusable_attempt({"status": "cutoff"}, Path(__file__)))
        self.assertFalse(
            reusable_attempt(
                {"status": "cutoff"}, Path(__file__).with_suffix(".missing")
            )
        )

    def test_canonical_runner_accepts_the_hybrid_domain(self) -> None:
        with patch.object(sys, "argv", [
            "runner", "--lexicon", "hybrid", "--branching-strategy", "slot",
            "--cell-letter-order", "support", "--deterministic",
        ]):
            args = parse_args()
        self.assertEqual("hybrid", args.lexicon)
        self.assertEqual("slot", args.branching_strategy)
        self.assertEqual("support", args.cell_letter_order)
        self.assertTrue(args.deterministic)
        self.assertEqual(4, args.minimum_images)


if __name__ == "__main__":
    unittest.main()
