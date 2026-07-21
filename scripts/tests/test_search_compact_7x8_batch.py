from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from search_compact_7x8_batch import (  # noqa: E402
    GRAMMAR_ANSWERS,
    POP_CLUES,
    candidate_pivots,
    central_index,
    expand_unavailable_by_family,
    main,
    parse_args,
)


class Compact7x8BatchSearchTests(unittest.TestCase):
    def test_candidate_pivots_stay_inside_the_frame(self) -> None:
        for seed in range(20):
            pivots = candidate_pivots(random.Random(seed))
            self.assertTrue(1 <= len(pivots) <= 4)
            self.assertTrue(all(2 <= row <= 6 and 2 <= column <= 5 for row, column in pivots))

    def test_old_inflection_blocks_every_available_form_of_lemma(self) -> None:
        expanded = expand_unavailable_by_family(
            {"ESPERER"},
            {"ESPERER": "ESPERER", "ESPERE": "ESPERER", "ESPERES": "ESPERER"},
            {"ESPERER": {"ESPERE", "ESPERES"}},
        )
        self.assertEqual(expanded, {"ESPERER", "ESPERE", "ESPERES"})

    def test_young_pop_references_fit_compact_slots(self) -> None:
        for answer in ("ROBLOX", "NARUTO", "LUFFY", "STITCH", "MARVEL"):
            self.assertIn(answer, POP_CLUES)
            self.assertLessEqual(len(answer), 7)

    def test_pronouns_and_possessives_are_counted_as_grammar_fillers(self) -> None:
        self.assertTrue({"IL", "ON", "TON"} <= GRAMMAR_ANSWERS)

    def test_lexical_full_scope_is_available(self) -> None:
        with patch.object(
            sys,
            "argv",
            ["search", "--output", "candidate.json", "--lexicon-scope", "lexical-full"],
        ):
            self.assertEqual(parse_args().lexicon_scope, "lexical-full")

    def test_adjacent_clue_pair_limit_defaults_to_three(self) -> None:
        with patch.object(sys, "argv", ["search", "--output", "candidate.json"]):
            self.assertEqual(parse_args().maximum_adjacent_clue_pairs, 3)

    def test_short_repeat_allowlist_is_explicit(self) -> None:
        with patch.object(
            sys,
            "argv",
            ["search", "--output", "candidate.json", "--allow-repeat-answer", "EN"],
        ):
            self.assertEqual(parse_args().allow_repeat_answer, ["EN"])

    def test_single_use_active_short_pool_is_retired(self) -> None:
        with patch.object(
            sys,
            "argv",
            [
                "search", "--output", "candidate.json",
                "--allow-active-answer-max-length", "3",
            ],
        ):
            with self.assertRaisesRegex(ValueError, "retiré"):
                main()

    def test_default_shape_limits_reduce_short_filler(self) -> None:
        with patch.object(sys, "argv", ["search", "--output", "candidate.json"]):
            args = parse_args()
        self.assertEqual(2, args.maximum_two_letter_slots)
        self.assertEqual(6, args.maximum_short_slots)
        self.assertEqual(3, args.minimum_engaging_answers)

    def test_lexical_scope_keeps_closed_owner_short_vocabulary(self) -> None:
        indexes, metadata, _family_answers, _all_families = central_index(
            set(), 3.2, "lexical-full"
        )
        self.assertTrue({"GO", "IA", "OM", "QR", "WC", "XL"} <= set(indexes[0][2]))
        self.assertEqual(
            metadata["QR"]["sourceId"],
            "motman-owner-short-vocabulary-20260719",
        )
        self.assertGreaterEqual(metadata["QR"]["editorialFillScore"], 30)


if __name__ == "__main__":
    unittest.main()
