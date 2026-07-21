from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_llm_fill_brief import build_brief  # noqa: E402


class LlmFillBriefTests(unittest.TestCase):
    def test_active_answers_are_visible_but_not_globally_blocked(self) -> None:
        brief = build_brief()
        active = set(brief["activeAnswers"])
        forbidden = set(brief["forbiddenAnswers"])
        self.assertEqual(brief["activeAnswerCount"], len(active))
        self.assertTrue(active - forbidden)
        self.assertEqual(
            "score-penalty-check-occurrences-and-cooldown",
            brief["policy"]["activeExactAnswer"],
        )

    def test_owner_reported_repeats_are_explicitly_exhausted(self) -> None:
        brief = build_brief()
        forbidden = set(brief["forbiddenAnswers"])
        exhausted = set(brief["highFatigueAnswers"])
        self.assertTrue({"EGO", "EN", "LE", "OSE", "PC", "TE", "TOM"} <= exhausted)
        self.assertTrue({"EGO", "OM"} <= forbidden)


if __name__ == "__main__":
    unittest.main()
