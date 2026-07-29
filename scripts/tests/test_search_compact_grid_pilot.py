from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from search_compact_grid_pilot import (  # noqa: E402
    PILOT_REVIEWED_NATURAL_FORMS,
    OWNER_SHORT,
    PILOT_CONCEPT_FAMILY_OVERRIDES,
    PILOT_SAFE_SHORT,
    build_slots,
    build_slots_from_shape,
    hybrid_metadata_is_eligible,
    load_editorial_rescue_entries,
    load_shape_definition,
    load_reference_solutions,
    parse_fixed_answer,
    pilot_answer_length_is_eligible,
    rotation_cooldown_usage,
)
from pilot_two_letter_policy import (  # noqa: E402
    PENALIZED_TWO_LETTER_ANSWERS,
    PILOT_TWO_LETTER_WHITELIST,
    PREFERRED_TWO_LETTER_ANSWERS,
)


class SearchCompactGridPilotTests(unittest.TestCase):
    def test_fixed_answer_is_normalized(self) -> None:
        self.assertEqual((4, "POPPINS"), parse_fixed_answer("4:Poppins"))

    def test_fixed_answer_rejects_empty_value(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_fixed_answer("2:")

    def test_two_letter_vocabulary_is_exactly_the_reviewed_whitelist(self) -> None:
        self.assertEqual(
            set(PILOT_TWO_LETTER_WHITELIST),
            {answer for answer in OWNER_SHORT if len(answer) == 2},
        )
        self.assertEqual(
            set(PILOT_TWO_LETTER_WHITELIST),
            {answer for answer in PILOT_SAFE_SHORT if len(answer) == 2},
        )

    def test_raw_lexicons_cannot_add_an_unreviewed_two_letter_form(self) -> None:
        self.assertTrue(pilot_answer_length_is_eligible("IA"))
        self.assertFalse(pilot_answer_length_is_eligible("SS"))
        self.assertTrue(pilot_answer_length_is_eligible("CHAT"))

    def test_short_relief_prefers_lexical_answers_over_grammar(self) -> None:
        self.assertEqual(
            set(PILOT_TWO_LETTER_WHITELIST),
            PREFERRED_TWO_LETTER_ANSWERS | PENALIZED_TWO_LETTER_ANSWERS,
        )
        self.assertEqual({"IL", "ON", "UN"}, PENALIZED_TWO_LETTER_ANSWERS)
        self.assertFalse(PREFERRED_TWO_LETTER_ANSWERS & PENALIZED_TWO_LETTER_ANSWERS)

    def test_modern_three_letter_answers_are_available(self) -> None:
        self.assertTrue({"APP", "BOT", "BUG", "GIF", "GPS", "MDR", "USB", "WOW"} <= OWNER_SHORT)

    def test_reviewable_modern_three_letter_answers_are_available(self) -> None:
        self.assertTrue(
            {"APP", "BOT", "BUG", "GIF", "GPS", "LED", "MDR", "PDF", "SIM", "USB", "WII", "ZEN"}
            <= OWNER_SHORT
        )

    def test_reviewed_short_vocabulary_includes_everyday_crossing_words(self) -> None:
        self.assertTrue({"AMI", "ARC", "BEC", "CLE", "COU", "MIE", "TOI", "TRI"} <= OWNER_SHORT)

    def test_pilot_short_vocabulary_covers_current_everyday_language(self) -> None:
        self.assertTrue(
            {"ADN", "API", "DVD", "FUN", "MEC", "OUF", "SPA", "TOP", "URL"}
            <= PILOT_SAFE_SHORT
        )

    def test_reviewed_natural_plural_forms_are_explicit_and_common(self) -> None:
        self.assertTrue(
            {"JOUEURS", "IMAGES", "MATCHS", "SPORTS", "VOYAGES"}
            <= PILOT_REVIEWED_NATURAL_FORMS
        )
        self.assertNotIn("PEUVENT", PILOT_REVIEWED_NATURAL_FORMS)

    def test_latent_and_latence_share_one_editorial_family(self) -> None:
        self.assertEqual(
            PILOT_CONCEPT_FAMILY_OVERRIDES["LATENT"],
            PILOT_CONCEPT_FAMILY_OVERRIDES["LATENCE"],
        )

    def test_hybrid_domain_rejects_inflected_verbs_by_default(self) -> None:
        inflected = {
            "partOfSpeech": "verb",
            "formType": "inflected",
            "attestedCommonForm": True,
        }
        lemma = {
            "partOfSpeech": "verb",
            "formType": "lemma",
            "attestedCommonForm": True,
        }
        self.assertFalse(hybrid_metadata_is_eligible(inflected))
        self.assertTrue(hybrid_metadata_is_eligible(lemma))
        self.assertTrue(
            hybrid_metadata_is_eligible(inflected, allow_inflected_verbs=True)
        )

    def test_hybrid_domain_requires_an_attested_common_form(self) -> None:
        self.assertFalse(hybrid_metadata_is_eligible({
            "partOfSpeech": "common-noun",
            "formType": "inflected",
            "attestedCommonForm": False,
        }))

    def test_editorial_rescue_rejects_a_finite_verb(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rescue.json"
            path.write_text(json.dumps({"entries": [{
                "answer": "STOPPE",
                "partOfSpeech": "verb",
                "formType": "finite",
                "editorialStatus": "human-reviewed",
            }]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "infinitifs"):
                load_editorial_rescue_entries(path)

    def test_editorial_rescue_accepts_reviewed_noun_and_infinitive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rescue.json"
            path.write_text(json.dumps({"entries": [
                {
                    "answer": "PODCAST",
                    "partOfSpeech": "common-noun",
                    "formType": "lemma",
                    "editorialStatus": "human-reviewed",
                },
                {
                    "answer": "JOUER",
                    "partOfSpeech": "verb",
                    "formType": "infinitive",
                    "editorialStatus": "human-reviewed",
                },
            ]}), encoding="utf-8")
            self.assertEqual(
                ["PODCAST", "JOUER"],
                [item["answer"] for item in load_editorial_rescue_entries(path)],
            )

    def test_reference_fill_loader_keeps_slot_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference.json"
            path.write_text(json.dumps({
                "grids": [{"slotAnswers": {"0": "Épi", "1": "TER"}}]
            }), encoding="utf-8")
            self.assertEqual(
                [{0: "EPI", 1: "TER"}], load_reference_solutions([path])
            )

    def test_reference_fill_loader_accepts_answer_record_lists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference.json"
            path.write_text(json.dumps({
                "answers": [
                    {"slotIndex": 0, "answer": "Estomac"},
                    {"slotIndex": 1, "answer": "Ferrari"},
                ]
            }), encoding="utf-8")
            self.assertEqual(
                [{0: "ESTOMAC", 1: "FERRARI"}],
                load_reference_solutions([path]),
            )

    def test_zero_two_letter_slots_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "une ou deux réponses"):
            build_slots(7, 8, set())

    def test_one_two_letter_slot_preserves_complete_coverage(self) -> None:
        _, raw_slots, _ = build_slots(7, 8, {(4, 3)})
        coverage = {}
        for slot in raw_slots:
            self.assertGreaterEqual(slot["length"], 2)
            for cell in map(tuple, slot["cells"]):
                coverage.setdefault(cell, set()).add(slot["direction"])
        self.assertEqual(41, len(coverage))
        self.assertEqual(1, sum(slot["length"] == 2 for slot in raw_slots))
        self.assertTrue(all(coverage.values()))

    def test_two_two_letter_slots_are_accepted(self) -> None:
        _, raw_slots, _ = build_slots(7, 8, {(4, 3), (6, 4)})
        self.assertEqual(2, sum(slot["length"] == 2 for slot in raw_slots))

    def test_three_two_letter_slots_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "trouvé : 3"):
            build_slots(7, 8, {(3, 5), (4, 3), (6, 4)})

    def test_singleton_in_one_axis_is_allowed_when_other_axis_covers_it(self) -> None:
        _, raw_slots, _ = build_slots(7, 8, {(4, 3), (4, 5)})
        coverage = {}
        for slot in raw_slots:
            for cell in map(tuple, slot["cells"]):
                coverage.setdefault(cell, set()).add(slot["direction"])
        self.assertEqual({"down"}, coverage[(4, 6)])
        self.assertTrue(all(coverage.values()))

    def test_one_two_letter_run_is_accepted(self) -> None:
        _, raw_slots, _ = build_slots(7, 8, {(4, 3)})
        self.assertEqual(1, sum(slot["length"] == 2 for slot in raw_slots))

    def test_shape_library_slots_are_loaded_and_revalidated(self) -> None:
        clues, raw_slots, _ = build_slots(7, 8, {(4, 3), (4, 5)})
        shape = {
            "shapeId": "singleton-smoke",
            "columns": 7,
            "rows": 8,
            "pivots": [[4, 5]],
            "clueCells": clues,
            "slots": [
                {**slot, "slotIndex": index}
                for index, slot in enumerate(raw_slots)
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shapes.json"
            path.write_text(json.dumps({"shapes": [shape]}), encoding="utf-8")
            loaded = load_shape_definition(path, "singleton-smoke")
        columns, rows, shape_id, loaded_clues, loaded_raw, loaded_slots = (
            build_slots_from_shape(loaded)
        )
        self.assertEqual((7, 8, "singleton-smoke"), (columns, rows, shape_id))
        self.assertEqual(clues, loaded_clues)
        self.assertEqual(len(raw_slots), len(loaded_raw))
        self.assertEqual(list(range(len(loaded_slots))), [slot.index for slot in loaded_slots])

    def test_shape_without_the_required_short_relief_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "une ou deux réponses"):
            build_slots(8, 8, set())

    def test_rotation_cooldown_becomes_a_penalty_not_a_hard_ban(self) -> None:
        usage = rotation_cooldown_usage({
            "rotationCooldownAnswers": [
                {"answer": "Égo", "observedActiveUses": 4},
                "MUR",
            ]
        })
        self.assertEqual(4, usage["EGO"])
        self.assertEqual(1, usage["MUR"])


if __name__ == "__main__":
    unittest.main()
