from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import publish_repetition_renovation as publish  # noqa: E402


class PublishRepetitionRenovationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.staging = json.loads(publish.STAGING.read_text(encoding="utf-8"))

    def make_prepublication_catalog(self) -> dict:
        grids = []
        for staged in self.staging["grids"]:
            old = copy.deepcopy(staged)
            old["id"] = staged["replacesGridId"]
            old.pop("replacesGridId", None)
            grids.append(old)
        return {"version": 11, "grids": grids, "batchMetrics": {}}

    def test_publication_replaces_three_grids_without_changing_total(self) -> None:
        active = self.make_prepublication_catalog()
        result, feedback, report = publish.prepare_publication(
            active, self.staging, {"positiveGridReviews": []}
        )
        ids = {grid["id"] for grid in result["grids"]}
        self.assertEqual(3, len(result["grids"]))
        self.assertFalse(set(publish.EXPECTED_REPLACEMENTS) & ids)
        self.assertTrue(set(publish.EXPECTED_REPLACEMENTS.values()) <= ids)
        self.assertEqual(12, result["version"])
        self.assertEqual(3, report["replaced"])
        self.assertEqual(3, len(feedback["positiveGridReviews"]))

    def test_publication_is_idempotent(self) -> None:
        first, feedback, _ = publish.prepare_publication(
            self.make_prepublication_catalog(),
            self.staging,
            {"positiveGridReviews": []},
        )
        second, second_feedback, report = publish.prepare_publication(
            first, self.staging, feedback
        )
        self.assertEqual(first, second)
        self.assertEqual(feedback, second_feedback)
        self.assertEqual("already-published", report["status"])
        self.assertEqual(12, second["version"])


if __name__ == "__main__":
    unittest.main()
