from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_single_anchor_campaign_report import summarize_matrix  # noqa: E402


class SingleAnchorCampaignReportTests(unittest.TestCase):
    def test_matrix_separates_root_survivors_and_rejections(self) -> None:
        rows = summarize_matrix({"placements": [
            {
                "anchor": "CONSOLE", "shapeId": "shape-1", "survives": True,
                "minimumRemainingDomain": 12,
            },
            {
                "anchor": "CONSOLE", "shapeId": "shape-1", "survives": False,
                "reason": "crossing-domain-wipeout",
            },
        ]})
        self.assertEqual(1, len(rows))
        self.assertEqual(2, rows[0]["placementCount"])
        self.assertEqual(1, rows[0]["rootSurvivorCount"])
        self.assertEqual(1, rows[0]["rootRejectedCount"])
        self.assertEqual(12, rows[0]["bestMinimumRemainingDomain"])
        self.assertEqual(
            {"crossing-domain-wipeout": 1}, rows[0]["rejectionCauses"]
        )


if __name__ == "__main__":
    unittest.main()
