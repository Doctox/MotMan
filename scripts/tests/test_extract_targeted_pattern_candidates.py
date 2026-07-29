from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from extract_targeted_pattern_candidates import (  # noqa: E402
    aggregated_failures,
    matches,
)


class TargetedPatternCandidateTests(unittest.TestCase):
    def test_pattern_match_uses_question_mark_as_only_wildcard(self) -> None:
        self.assertTrue(matches("C?SQUE", "CASQUE"))
        self.assertFalse(matches("C?SQUE", "CASTOR"))

    def test_failure_patterns_are_aggregated_across_attempts(self) -> None:
        item = {
            "leftPattern": "C?SQUE", "leftPosition": 1, "leftLetters": ["A"],
            "rightPattern": "?RI", "rightPosition": 0, "rightLetters": ["O"],
            "count": 2,
        }
        failures = aggregated_failures({"results": [
            {"telemetry": {"failurePatterns": [item]}},
            {"telemetry": {"failurePatterns": [{**item, "count": 3}]}},
        ]})
        self.assertEqual(5, next(iter(failures.values())))


if __name__ == "__main__":
    unittest.main()
