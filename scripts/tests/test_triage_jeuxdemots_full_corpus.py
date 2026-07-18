from __future__ import annotations

import gzip
import json
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/data"


class FullJeuxDeMotsTriageTests(unittest.TestCase):
    def test_every_retained_relation_has_one_durable_status(self) -> None:
        with gzip.open(DATA / "crossword.jeuxdemots.review.json.gz", "rt", encoding="utf-8") as handle:
            source = json.load(handle)
        with gzip.open(DATA / "crossword.jeuxdemots.full-triage.json.gz", "rt", encoding="utf-8") as handle:
            triage = json.load(handle)
        self.assertEqual(len(source["entries"]), len(triage["entries"]))
        self.assertEqual(0, triage["metrics"]["unclassifiedRelations"])
        self.assertTrue(all(entry.get("triageStatus") for entry in triage["entries"]))
        self.assertTrue(all(entry.get("triageReasons") for entry in triage["entries"]))
        counted = Counter(entry["triageStatus"] for entry in triage["entries"])
        self.assertEqual(dict(sorted(counted.items())), triage["metrics"]["statusCounts"])

    def test_candidate_file_has_at_most_one_non_playable_pair_per_answer(self) -> None:
        document = json.loads(
            (DATA / "crossword.jeuxdemots.editorial-candidates.json").read_text(encoding="utf-8")
        )
        answers = [entry["answer"] for entry in document["entries"]]
        self.assertEqual(len(answers), len(set(answers)))
        self.assertTrue(all(not entry["generatorEligible"] for entry in document["entries"]))
        self.assertTrue(all(not entry["playableAsIs"] for entry in document["entries"]))


if __name__ == "__main__":
    unittest.main()
