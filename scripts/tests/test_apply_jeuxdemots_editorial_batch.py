from __future__ import annotations

import json
import gzip
import unicodedata
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/data"


def normalize(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value.upper())
        if unicodedata.category(char) != "Mn" and char.isalpha()
    )


class ApplyJeuxDeMotsEditorialBatchTests(unittest.TestCase):
    def owner_overrides(self) -> dict[tuple[str, str], str]:
        document = json.loads(
            (DATA / "jeuxdemots.owner-full-decisions.json").read_text(encoding="utf-8")
        )
        return {
            (item["answer"], normalize(item["clue"])): item["decision"]
            for item in document["decisions"]
        }

    def test_all_421_candidates_have_a_durable_decision(self) -> None:
        decisions = json.loads(
            (DATA / "jeuxdemots.editorial-batch-20260715.json").read_text(encoding="utf-8")
        )
        approved = json.loads(
            (DATA / "crossword.jeuxdemots.approved.json").read_text(encoding="utf-8")
        )
        blacklist = json.loads(
            (DATA / "editorial.blacklist.json").read_text(encoding="utf-8")
        )
        self.assertEqual(421, len(decisions["decisions"]))
        self.assertEqual(421, sum(decisions["counts"].values()))
        approved_pairs = {
            (entry["answer"], normalize(entry["clue"])) for entry in approved["entries"]
        }
        rejected_pairs = {
            (entry["answer"], normalize(entry["clue"])) for entry in blacklist["rejectedPairs"]
        }
        overrides = self.owner_overrides()
        for item in decisions["decisions"]:
            key = item["answer"], normalize(item["clue"])
            final_decision = overrides.get(key, item["decision"])
            if final_decision == "accept":
                self.assertIn(key, approved_pairs)
                self.assertNotIn(key, rejected_pairs)
            elif final_decision == "reject":
                self.assertIn(key, rejected_pairs)
                self.assertNotIn(key, approved_pairs)
            else:
                self.assertNotIn(key, approved_pairs)
                self.assertNotIn(key, rejected_pairs)

    def test_second_pass_decisions_are_also_enforced(self) -> None:
        decisions = json.loads(
            (DATA / "jeuxdemots.editorial-batch-20260715-b.json").read_text(encoding="utf-8")
        )
        approved = json.loads(
            (DATA / "crossword.jeuxdemots.approved.json").read_text(encoding="utf-8")
        )
        blacklist = json.loads(
            (DATA / "editorial.blacklist.json").read_text(encoding="utf-8")
        )
        approved_pairs = {
            (entry["answer"], normalize(entry["clue"])) for entry in approved["entries"]
        }
        rejected_pairs = {
            (entry["answer"], normalize(entry["clue"])) for entry in blacklist["rejectedPairs"]
        }
        overrides = self.owner_overrides()
        self.assertEqual({"accepted": 19, "rejected": 6, "doubt": 11}, decisions["counts"])
        for item in decisions["decisions"]:
            key = item["answer"], normalize(item["clue"])
            final_decision = overrides.get(key, item["decision"])
            if final_decision == "accept":
                self.assertIn(key, approved_pairs)
                self.assertNotIn(key, rejected_pairs)
            elif final_decision == "reject":
                self.assertIn(key, rejected_pairs)
                self.assertNotIn(key, approved_pairs)
            else:
                self.assertNotIn(key, approved_pairs)
                self.assertNotIn(key, rejected_pairs)

    def test_wave_c_has_500_explicit_enforced_decisions(self) -> None:
        decisions = json.loads(
            (DATA / "jeuxdemots.editorial-wave-c-decisions.json").read_text(encoding="utf-8")
        )
        approved = json.loads(
            (DATA / "crossword.jeuxdemots.approved.json").read_text(encoding="utf-8")
        )
        blacklist = json.loads(
            (DATA / "editorial.blacklist.json").read_text(encoding="utf-8")
        )
        self.assertEqual(500, len(decisions["decisions"]))
        self.assertEqual(500, sum(decisions["counts"].values()))
        approved_pairs = {
            (entry["answer"], normalize(entry["clue"])) for entry in approved["entries"]
        }
        rejected_pairs = {
            (entry["answer"], normalize(entry["clue"])) for entry in blacklist["rejectedPairs"]
        }
        overrides = self.owner_overrides()
        for item in decisions["decisions"]:
            key = item["answer"], normalize(item["clue"])
            final_decision = overrides.get(key, item["decision"])
            if final_decision == "accept":
                self.assertIn(key, approved_pairs)
                self.assertNotIn(key, rejected_pairs)
            elif final_decision == "reject":
                self.assertIn(key, rejected_pairs)
                self.assertNotIn(key, approved_pairs)
            else:
                self.assertNotIn(key, approved_pairs)
                self.assertNotIn(key, rejected_pairs)

    def test_all_editorial_rejections_are_absent_from_rebuilt_reservoir(self) -> None:
        rejected = set()
        for filename in (
            "jeuxdemots.editorial-batch-20260715.json",
            "jeuxdemots.editorial-batch-20260715-b.json",
            "jeuxdemots.editorial-wave-c-decisions.json",
        ):
            document = json.loads((DATA / filename).read_text(encoding="utf-8"))
            rejected.update(
                (item["answer"], normalize(item["clue"]))
                for item in document["decisions"] if item["decision"] == "reject"
            )
        with gzip.open(
            DATA / "crossword.jeuxdemots.review.json.gz", "rt", encoding="utf-8"
        ) as handle:
            reservoir = json.load(handle)
        reservoir_pairs = {
            (item["answer"], normalize(item["clue"])) for item in reservoir["entries"]
        }
        self.assertEqual(248, len(rejected))
        self.assertTrue(rejected.isdisjoint(reservoir_pairs))


if __name__ == "__main__":
    unittest.main()
