from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from editorial_quality import (  # noqa: E402
    editorial_errors,
    grid_semantic_errors,
    pilot_editorial_errors,
)


def codes(answer: str, clue: str, **extra) -> set[str]:
    return {
        error["code"]
        for error in editorial_errors({"answer": answer, "clue": clue, **extra})
    }


class EditorialQualityTests(unittest.TestCase):

    def test_pilot_requires_explicit_semantic_and_grammatical_review(self) -> None:
        item = {
            "answer": "UNIVERS",
            "clue": "Galaxie lointaine",
            "sourceId": "manual",
            "sourceUrl": "local://pilot",
            "sourceType": "editorial",
            "familiarityScore": 90,
            "familiarityBand": "common",
            "partOfSpeech": "noun",
            "languageStatus": "french",
            "culturalStatus": "everyday",
            "clueStyle": "direct",
            "editorialReview": {
                "semanticFit": False,
                "grammaticalFit": True,
                "unambiguous": True,
                "answerNotRevealed": True,
                "languageAcceptable": True,
                "allAudience": True,
            },
        }
        self.assertIn(
            "pilot_editorial_review_failed",
            {error["code"] for error in pilot_editorial_errors(item)},
        )

    def test_pilot_human_review_label_does_not_waive_missing_evidence(self) -> None:
        errors = pilot_editorial_errors({
            "answer": "CHAT",
            "clue": "Félin",
            "editorialStatus": "human-reviewed",
        })
        self.assertIn("pilot_missing_provenance", {error["code"] for error in errors})
        self.assertIn("pilot_missing_editorial_review", {error["code"] for error in errors})

    def test_related_concepts_are_allowed_but_duplicate_concepts_are_rejected(self) -> None:
        related = [
            {"answer": "ROSE", "conceptGroup": "ROSE"},
            {"answer": "FLEUR", "conceptGroup": "FLEUR"},
        ]
        self.assertEqual([], grid_semantic_errors(related))

        duplicate = [
            {"answer": "RAT", "conceptGroup": "RAT"},
            {"answer": "RATS", "conceptGroup": "RAT"},
        ]
        self.assertEqual("duplicate_concept", grid_semantic_errors(duplicate)[0]["code"])

    def test_explicit_semantic_equivalence_is_rejected(self) -> None:
        words = [
            {"answer": "AUTO", "semanticConflicts": ["VOITURE"]},
            {"answer": "VOITURE"},
        ]
        self.assertEqual("semantic_conflict", grid_semantic_errors(words)[0]["code"])

    def test_singular_and_plural_with_inflected_clues_are_rejected(self) -> None:
        words = [
            {"answer": "AMI", "clue": "Proche apprécié", "conceptGroup": "AMI"},
            {"answer": "AMIS", "clue": "Proches appréciés", "conceptGroup": "AMIS"},
        ]
        self.assertIn(
            "duplicate_inflection",
            {error["code"] for error in grid_semantic_errors(words)},
        )

    def test_distinct_homographs_are_still_rejected_as_visual_repetition(self) -> None:
        words = [
            {"answer": "BAR", "clue": "Comptoir à boissons", "conceptGroup": "BAR-LIEU"},
            {"answer": "BARS", "clue": "Poissons marins", "conceptGroup": "BAR-POISSON"},
        ]
        self.assertIn(
            "duplicate_inflection",
            {error["code"] for error in grid_semantic_errors(words)},
        )

    def test_two_letter_word_is_not_confused_with_a_word_ending_in_s(self) -> None:
        words = [
            {"answer": "DO", "clue": "Note avant ré"},
            {"answer": "DOS", "clue": "Arrière du corps"},
        ]
        self.assertNotIn(
            "duplicate_inflection",
            {error["code"] for error in grid_semantic_errors(words)},
        )

    def test_same_clue_cannot_designate_two_answers(self) -> None:
        words = [
            {"answer": "SUD", "clue": "Direction"},
            {"answer": "SENS", "clue": " direction  "},
        ]
        self.assertIn(
            "ambiguous_duplicate_clue",
            {error["code"] for error in grid_semantic_errors(words)},
        )

    def test_same_answer_and_clue_is_not_reported_as_ambiguous(self) -> None:
        words = [
            {"answer": "BUS", "clue": "Autocar"},
            {"answer": "BUS", "clue": "Autocar"},
        ]
        self.assertNotIn(
            "ambiguous_duplicate_clue",
            {error["code"] for error in grid_semantic_errors(words)},
        )

    def test_fragment_punctuation_is_rejected(self) -> None:
        errors = editorial_errors({"answer": "AVEU", "clue": "/mea-culpa"})
        self.assertIn("clue_fragment_punctuation", {error["code"] for error in errors})

    def test_mobile_clue_is_limited_to_three_words(self) -> None:
        errors = editorial_errors({"answer": "ALIBI", "clue": "Preuve de son innocence"})
        self.assertIn("clue_too_long", {error["code"] for error in errors})

    def test_empty_clue_requires_a_complete_image_record(self) -> None:
        self.assertIn("empty_clue", codes("VERS", "   "))
        self.assertNotIn("empty_clue", codes(
            "CHAT", "", image={
                "asset": "/assets/clues/twemoji/chat.svg", "alt": "Chat",
                "source": "Twemoji", "license": "CC BY 4.0",
            },
        ))

    def test_contextual_morphological_form_is_rejected(self) -> None:
        self.assertIn("morphological_fragment", codes("BEL", "Joli"))

    def test_roman_category_without_value_is_rejected(self) -> None:
        self.assertIn("roman_value_missing", codes("III", "Chiffres romains"))

    def test_roman_value_must_be_canonical_and_exact(self) -> None:
        self.assertEqual(set(), codes("XII", "12 romain"))
        self.assertEqual(set(), codes("XII", "Douze, à Rome"))
        self.assertIn("roman_value_mismatch", codes("XIII", "12 romain"))

    def test_unnatural_spelled_number_is_rejected(self) -> None:
        self.assertIn("roman_clue_unnatural", codes("XII", "Douze romain"))


if __name__ == "__main__":
    unittest.main()
