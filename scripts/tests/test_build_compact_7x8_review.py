from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_compact_7x8_review import (  # noqa: E402
    add_decision_ui,
    build_grid,
    emoji_asset,
    family_key,
    local_asset_data_uri,
    parse_args,
    reference_answer_index,
    render_playtest_html,
)


class Compact7x8ReviewTests(unittest.TestCase):
    def test_inflected_answers_share_a_family(self) -> None:
        self.assertEqual(family_key("ADAPTER"), family_key("ADAPTÉE"))
        self.assertEqual(family_key("ÉTEINT"), family_key("ÉTEINTE"))
        self.assertEqual(family_key("RESTER"), family_key("RESTÉE"))
        self.assertEqual(family_key("REPÈRE"), family_key("REPÈRES"))
        self.assertEqual(family_key("ESPÉRER"), family_key("ESPÈRE"))
        self.assertEqual(family_key("OMBRE"), family_key("OMBRES"))
        self.assertEqual(family_key("SUJET"), family_key("SUJETTE"))
        self.assertEqual(family_key("TRESSEE"), family_key("TRESSES"))
        self.assertEqual(family_key("APLATIR"), family_key("APLATIE"))
        self.assertEqual(family_key("REELUE"), family_key("ELU"))

    def test_noun_ending_er_is_not_cut_like_a_verb(self) -> None:
        self.assertNotEqual(family_key("SENTIER"), family_key("SENTIS"))

    def test_reference_index_groups_inflections(self) -> None:
        exact, families = reference_answer_index([
            ROOT / "output" / "quality" / "compact-7x8-owner-review-staging.json"
        ])
        self.assertIn("RESTERA", exact)
        self.assertIn(family_key("RESTÉE"), families)

    def test_short_answers_remain_distinct(self) -> None:
        self.assertNotEqual(family_key("MER"), family_key("ME"))

    def test_emoji_asset_is_embedded_svg(self) -> None:
        uri = emoji_asset("🐘")
        prefix = "data:image/svg+xml;base64,"
        self.assertTrue(uri.startswith(prefix))
        svg = base64.b64decode(uri[len(prefix):]).decode("utf-8")
        self.assertIn("🐘", svg)

    def test_reviewed_local_asset_is_embedded_svg(self) -> None:
        uri = local_asset_data_uri("/assets/clues/custom/poids-musculation.svg")
        prefix = "data:image/svg+xml;base64,"
        self.assertTrue(uri.startswith(prefix))
        svg = base64.b64decode(uri[len(prefix):]).decode("utf-8")
        self.assertIn("Poids de musculation", svg)

    def test_decision_ui_is_injected_for_each_grid_title(self) -> None:
        page = "<html><head></head><body><h1>Lot</h1><h2>A</h2><h2>B</h2></body></html>"
        result = add_decision_ui(page, 2)
        self.assertEqual(2, result.count('data-decision="accept"'))
        self.assertIn("Télécharger mes décisions", result)

    def test_active_catalog_is_the_default_repeat_reference(self) -> None:
        argv = [
            "review", "--input", "input.json", "--staging", "staging.json",
            "--audit", "audit.json", "--html", "review.html",
        ]
        with patch.object(sys, "argv", argv):
            args = parse_args()
        self.assertEqual([ROOT / "src/data/grid.catalog.json"], args.reference)

    def test_playtest_path_is_optional(self) -> None:
        argv = [
            "review", "--input", "input.json", "--staging", "staging.json",
            "--audit", "audit.json", "--html", "review.html",
            "--playtest-html", "playtest.html",
        ]
        with patch.object(sys, "argv", argv):
            args = parse_args()
        self.assertEqual(Path("playtest.html"), args.playtest_html)

    def test_short_reference_repeats_must_be_explicit(self) -> None:
        argv = [
            "review", "--input", "input.json", "--staging", "staging.json",
            "--audit", "audit.json", "--html", "review.html",
            "--allow-reference-repeat", "EN",
        ]
        with patch.object(sys, "argv", argv):
            args = parse_args()
        self.assertEqual(["EN"], args.allow_reference_repeat)

    def test_internal_short_repeats_must_be_explicit(self) -> None:
        argv = [
            "review", "--input", "input.json", "--staging", "staging.json",
            "--audit", "audit.json", "--html", "review.html",
            "--allow-internal-repeat", "PC",
        ]
        with patch.object(sys, "argv", argv):
            args = parse_args()
        self.assertEqual(["PC"], args.allow_internal_repeat)

    def test_strict_editorial_metadata_is_forwarded_to_staging_word(self) -> None:
        review = {
            "semanticFit": True,
            "grammaticalFit": True,
            "unambiguous": True,
            "answerNotRevealed": True,
            "languageAcceptable": True,
            "allAudience": True,
        }
        grid = build_grid({
            "id": "metadata-test",
            "sourceShapeId": "test",
            "clueCells": [[0, 0], [1, 0]],
            "rawSlots": [{
                "slotId": "slot-01", "direction": "across",
                "clueCell": [1, 0], "cells": [[1, 1], [1, 2], [1, 3]],
            }],
            "minimumImages": 0,
            "imageAnswers": [],
            "answers": [{
                "slotIndex": 0, "answer": "WEB", "definition": "Toile numérique",
                "familiarityScore": 96, "familiarityBand": "common",
                "partOfSpeech": "common-noun", "languageStatus": "common-anglicism",
                "culturalStatus": "everyday", "clueStyle": "direct",
                "editorialReview": review,
            }],
        }, 1)
        word = grid["words"][0]
        self.assertEqual(96, word["familiarityScore"])
        self.assertEqual("common-anglicism", word["languageStatus"])
        self.assertEqual(review, word["editorialReview"])

    def test_playtest_html_does_not_contain_answers_or_solution_letters(self) -> None:
        report = {
            "gridId": "pilot-secret",
            "rows": 2,
            "columns": 2,
            "valid": True,
            "errorCount": 0,
            "errors": [],
            "layoutMetrics": {},
            "cells": [
                {"row": 0, "col": 0, "kind": "neutral", "wordIds": []},
                {"row": 0, "col": 1, "kind": "clue", "wordIds": ["w1"]},
                {"row": 1, "col": 0, "kind": "clue", "wordIds": ["w1"]},
                {"row": 1, "col": 1, "kind": "letter", "solution": "W", "wordIds": ["w1"]},
            ],
            "words": [{
                "wordId": "w1", "answer": "WEB", "clue": "WEB",
                "direction": "across", "cells": [[1, 1], [1, 2], [1, 3]],
                "image": {"asset": "data:image/svg+xml;base64,AA==", "alt": "WEB"},
            }],
        }
        page = render_playtest_html([report])
        self.assertNotIn(">WEB<", page)
        self.assertNotIn("data-clue='WEB'", page)
        self.assertNotIn("alt='WEB'", page)
        self.assertNotIn("class='letter-value'>W", page)
        self.assertIn("class='playtest-letter'", page)
        self.assertIn("solutions absentes", page)


if __name__ == "__main__":
    unittest.main()
