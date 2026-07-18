from __future__ import annotations

import json
import gzip
import unicodedata
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/data"


def normalized(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.upper())
        if unicodedata.category(char) != "Mn" and char.isalpha()
    )


class ApplyJeuxDeMotsOwnerDecisionsTests(unittest.TestCase):
    def test_every_owner_decision_is_durable_and_enforced(self) -> None:
        owner = json.loads((DATA / "jeuxdemots.owner-decisions.json").read_text(encoding="utf-8"))
        approved = json.loads((DATA / "crossword.jeuxdemots.approved.json").read_text(encoding="utf-8"))
        blacklist = json.loads((DATA / "editorial.blacklist.json").read_text(encoding="utf-8"))
        accepted = {
            (item["answer"], normalized(item["clue"]))
            for item in owner["decisions"] if item["decision"] == "accept"
        }
        rejected = {
            (item["answer"], normalized(item["clue"]))
            for item in owner["decisions"] if item["decision"] == "reject"
        }
        approved_pairs = {
            (item["answer"], normalized(item["clue"])) for item in approved["entries"]
        }
        blacklisted_pairs = {
            (item["answer"], normalized(item["clue"])) for item in blacklist["rejectedPairs"]
        }
        self.assertEqual({"total": 299, "accept": 133, "reject": 166}, owner["counts"])
        self.assertGreaterEqual(len(approved_pairs), 326)
        self.assertTrue(accepted <= approved_pairs)
        self.assertTrue(rejected <= blacklisted_pairs)
        self.assertTrue(approved_pairs.isdisjoint(rejected))
        self.assertTrue(all(item["decision"] in {"accept", "reject"} for item in owner["decisions"]))

        with gzip.open(DATA / "crossword.jeuxdemots.review.json.gz", "rt", encoding="utf-8") as handle:
            reservoir = json.load(handle)
        reservoir_pairs = {
            (item["answer"], normalized(item["clue"])) for item in reservoir["entries"]
        }
        self.assertTrue(reservoir_pairs.isdisjoint(rejected))


if __name__ == "__main__":
    unittest.main()
