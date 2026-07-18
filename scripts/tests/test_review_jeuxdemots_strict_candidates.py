from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ReviewJeuxDeMotsStrictCandidatesTests(unittest.TestCase):
    def test_approved_and_doubt_sets_are_separate_and_complete(self) -> None:
        approved = json.loads(
            (ROOT / "src/data/crossword.jeuxdemots.approved.json").read_text(encoding="utf-8")
        )
        decisions = json.loads(
            (ROOT / "src/data/jeuxdemots.editorial-decisions.json").read_text(encoding="utf-8")
        )
        approved_pairs = {(entry["answer"], entry["clue"]) for entry in approved["entries"]}
        rejected_pairs = {tuple(pair) for pair in decisions["rejectedPairs"]}
        self.assertGreaterEqual(len(approved_pairs), 326)
        self.assertEqual(166, len(rejected_pairs))
        self.assertTrue(approved_pairs.isdisjoint(rejected_pairs))
        self.assertEqual(0, decisions["doubtCount"])
        self.assertTrue(all(entry["editorialStatus"] == "human-reviewed" for entry in approved["entries"]))

    def test_owner_page_has_one_click_controls_and_persistence(self) -> None:
        page = (ROOT / "output/quality/jeuxdemots-owner-doubt.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("4 679 couples sont bien présents", page)
        self.assertIn('data-decision="accept"', page)
        self.assertIn('data-decision="reject"', page)
        self.assertIn('data-decision="doubt"', page)
        self.assertIn("localStorage.setItem", page)
        self.assertIn("Copier le bilan", page)
        self.assertIn("Télécharger le JSON", page)


if __name__ == "__main__":
    unittest.main()
