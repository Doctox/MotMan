from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/quality"


class ReviewJeuxDeMotsFullDoubtsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(
            (OUTPUT / "jeuxdemots-owner-full-doubt.json").read_text(encoding="utf-8")
        )
        self.page = (OUTPUT / "jeuxdemots-owner-doubt.html").read_text(encoding="utf-8")

    def test_every_unresolved_pair_is_exposed_once(self) -> None:
        entries = self.document["entries"]
        counts = Counter(entry["status"] for entry in entries)
        self.assertEqual(4679, len(entries))
        self.assertEqual(4679, self.document["metrics"]["totalReviewablePairs"])
        self.assertEqual(
            self.document["metrics"]["statusCounts"], dict(sorted(counts.items()))
        )
        self.assertEqual(len(entries), len({entry["id"] for entry in entries}))
        self.assertTrue(all(entry["id"].startswith("JDM-") for entry in entries))

    def test_page_is_paginated_searchable_and_persistent(self) -> None:
        self.assertIn("4 679 couples sont bien présents", self.page)
        self.assertIn('id="search"', self.page)
        self.assertIn('id="pageSize"', self.page)
        self.assertIn("localStorage.setItem", self.page)
        self.assertIn("Télécharger le JSON", self.page)
        self.assertIn("function matching()", self.page)
        self.assertIn("items.slice", self.page)


if __name__ == "__main__":
    unittest.main()
