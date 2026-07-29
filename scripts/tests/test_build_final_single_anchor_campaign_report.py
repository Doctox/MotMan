from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_final_single_anchor_campaign_report import (  # noqa: E402
    summarize_results,
    targeted_additions,
)


class FinalSingleAnchorCampaignReportTests(unittest.TestCase):
    def test_summary_separates_proofs_and_cutoffs(self) -> None:
        rows = summarize_results([
            {"shapeId": "s1", "status": "infeasible", "rootMinimumRemainingDomain": 8,
             "telemetry": {"nodes": 4}},
            {"shapeId": "s1", "status": "time-limit", "rootMinimumRemainingDomain": 12,
             "telemetry": {"nodes": 6}},
        ], "shapeId")
        self.assertEqual(1, len(rows))
        self.assertEqual(1, rows[0]["infeasible"])
        self.assertEqual(1, rows[0]["cutoff"])
        self.assertEqual(10, rows[0]["nodes"])
        self.assertEqual(12, rows[0]["maximumRootMinimumDomain"])

    def test_targeted_additions_are_derived_from_review_reason(self) -> None:
        additions = targeted_additions({"entries": [
            {"answer": "ALERTE", "reason": "Répare 3 contradictions."},
            {"answer": "MARIO", "reason": "Référence connue."},
        ]})
        self.assertEqual(["ALERTE"], [item["answer"] for item in additions])


if __name__ == "__main__":
    unittest.main()
