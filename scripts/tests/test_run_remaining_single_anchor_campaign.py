from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from run_remaining_single_anchor_campaign import (  # noqa: E402
    ordered_remaining_placements,
    placement_key,
)


class RemainingSingleAnchorCampaignTests(unittest.TestCase):
    def test_remaining_placements_skip_deep_attempts_and_rank_flexibility(self) -> None:
        scan = {"placements": [
            {"shapeId": "s", "anchor": "A", "slotIndex": 1, "survives": True,
             "minimumRemainingDomain": 4, "narrowDomainCount": 1, "domainFlexibility": 8},
            {"shapeId": "s", "anchor": "B", "slotIndex": 2, "survives": True,
             "minimumRemainingDomain": 12, "narrowDomainCount": 0, "domainFlexibility": 7},
            {"shapeId": "s", "anchor": "C", "slotIndex": 3, "survives": False},
        ]}
        remaining = ordered_remaining_placements(
            scan, {placement_key("s", "A", 1)}
        )
        self.assertEqual(["B"], [item["anchor"] for item in remaining])


if __name__ == "__main__":
    unittest.main()
