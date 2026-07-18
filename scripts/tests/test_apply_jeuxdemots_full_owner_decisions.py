from __future__ import annotations

import gzip
import json
import tempfile
import unicodedata
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/data"

from scripts.review_jeuxdemots_full_doubts import load_owner_seed, render


def normalized(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", value.upper())
        if unicodedata.category(char) != "Mn" and char.isalpha()
    )


class ApplyJeuxDeMotsFullOwnerDecisionsTests(unittest.TestCase):
    def test_review_page_restores_applied_owner_choices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "owner.json"
            path.write_text(json.dumps({
                "sourceDigest": "digest-test",
                "decisions": [
                    {"id": "JDM-a", "decision": "accept"},
                    {"id": "JDM-b", "decision": "reject"},
                    {"id": "JDM-c", "decision": "pending"},
                ],
            }), encoding="utf-8")
            seed = load_owner_seed("digest-test", path)

        self.assertEqual({"JDM-a": "accept", "JDM-b": "reject"}, seed)
        page = render({
            "entries": [],
            "metrics": {"totalReviewablePairs": 0},
            "sourceDigest": "digest-test",
        }, initial_decisions=seed)
        self.assertIn('const restoredDecisions={"JDM-a":"accept","JDM-b":"reject"};', page)
        self.assertIn("2 décisions déjà remises", page)
        self.assertIn('<option value="pending" selected>', page)

    def test_owner_batch_is_durable_and_enforced(self) -> None:
        owner = json.loads(
            (DATA / "jeuxdemots.owner-full-decisions.json").read_text(encoding="utf-8")
        )
        approved = json.loads(
            (DATA / "crossword.jeuxdemots.approved.json").read_text(encoding="utf-8")
        )
        blacklist = json.loads(
            (DATA / "editorial.blacklist.json").read_text(encoding="utf-8")
        )
        with gzip.open(DATA / "crossword.central.json.gz", "rt", encoding="utf-8") as handle:
            central = json.load(handle)

        counted = Counter(item["decision"] for item in owner["decisions"])
        self.assertGreaterEqual(owner["counts"]["decided"], 1_100)
        self.assertEqual(owner["counts"]["decided"], len(owner["decisions"]))
        self.assertEqual(owner["counts"]["accept"], counted["accept"])
        self.assertEqual(owner["counts"]["reject"], counted["reject"])
        self.assertEqual(owner["counts"]["doubt"], counted["doubt"])
        self.assertEqual(4_679, owner["counts"]["decided"] + owner["counts"]["pending"])
        accepted_ids = {
            item["id"] for item in owner["decisions"] if item["decision"] == "accept"
        }
        rejected_ids = {
            item["id"] for item in owner["decisions"] if item["decision"] == "reject"
        }
        doubt_ids = {
            item["id"] for item in owner["decisions"] if item["decision"] == "doubt"
        }
        applied_accepted_ids = {
            item["ownerFullDecisionId"]
            for item in approved["entries"]
            if item.get("ownerFullReviewDigest") == owner["sourceDigest"]
        }
        applied_rejected_ids = {
            item["ownerFullDecisionId"]
            for item in blacklist["rejectedPairs"]
            if item.get("ownerFullReviewDigest") == owner["sourceDigest"]
        }
        self.assertEqual(accepted_ids, applied_accepted_ids)
        self.assertEqual(rejected_ids, applied_rejected_ids)
        self.assertTrue(doubt_ids.isdisjoint(applied_accepted_ids | applied_rejected_ids))

        canonical_answers = {
            item["answer"] for item in central["entries"] if item["canonicalForGenerator"]
        }
        accepted_answers = {
            item["answer"] for item in owner["decisions"] if item["decision"] == "accept"
        }
        # A pair-level owner acceptance cannot override a durable global answer
        # rejection (for example adult content). Those accepted pairs remain in
        # review history but must stay outside generator canonicals.
        globally_blocked = set(blacklist.get("rejectedAnswers", []))
        self.assertTrue((accepted_answers - globally_blocked) <= canonical_answers)
        self.assertTrue((accepted_answers & globally_blocked).isdisjoint(canonical_answers))

        canonical_pairs = {
            (item["answer"], normalized(item.get("clue", "")))
            for item in central["entries"]
            if item["canonicalForGenerator"]
        }
        rejected_pairs = {
            (item["answer"], normalized(item["clue"]))
            for item in owner["decisions"]
            if item["decision"] == "reject"
        }
        self.assertTrue(canonical_pairs.isdisjoint(rejected_pairs))


if __name__ == "__main__":
    unittest.main()
