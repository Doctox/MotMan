from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from audit_flexible_batch_candidates import (  # noqa: E402
    apply_cross_candidate_repeat_gates,
    audit_candidate,
    find_rejected_cooccurrences,
)
from build_owner_low_short_review import RAW  # noqa: E402
from craft_flexible_common_grid import build_replacement_exclusions  # noqa: E402


class FlexibleBatchCandidateAuditTests(unittest.TestCase):
    def test_known_complete_candidate_passes_hard_geometry_gates(self) -> None:
        report = audit_candidate(
            RAW,
            lemmas={},
            blacklist=set(),
            active_usage=Counter(),
            images={},
        )
        self.assertTrue(report["topologyValid"], report["topologyErrors"])
        self.assertLessEqual(len(report["twoLetterAnswers"]), 2)
        self.assertEqual(26, report["answerCount"])

    def test_cross_candidate_exact_and_family_repeats_are_blocking(self) -> None:
        reports = [
            {
                "gridId": "a",
                "answers": ["SET", "SEC", "AME"],
                "familyByAnswer": {"SET": "SET", "SEC": "SEC", "AME": "AME"},
                "hardErrors": [],
                "hardValid": True,
            },
            {
                "gridId": "b",
                "answers": ["NETS", "SEC", "AMES"],
                "familyByAnswer": {"NETS": "NETS", "SEC": "SEC", "AMES": "AME"},
                "hardErrors": [],
                "hardValid": True,
            },
        ]
        collisions = apply_cross_candidate_repeat_gates(reports)
        self.assertEqual(["a", "b"], collisions["answerCollisions"]["SEC"])
        self.assertIn("AME", collisions["familyCollisions"])
        self.assertFalse(reports[0]["hardValid"])
        self.assertFalse(reports[1]["hardValid"])

    def test_reference_exclusion_imports_answers_before_solving(self) -> None:
        excluded, families = build_replacement_exclusions(
            set(),
            [SCRIPTS.parent / "src/data/grid-generation-handcrafted/owner-low-short-02.review.json"],
        )
        self.assertIn("SET", excluded)
        self.assertIn("ETRE", excluded)
        self.assertGreaterEqual(len(families), 20)

    def test_owner_rejected_cooccurrence_is_blocking(self) -> None:
        rules = [{"answers": ["MIG", "TIG"], "reason": "same welding theme"}]
        conflicts = find_rejected_cooccurrences({"MIG", "TIG", "LAMA"}, rules)
        self.assertEqual(rules, conflicts)
        self.assertEqual([], find_rejected_cooccurrences({"MIG", "LAMA"}, rules))


if __name__ == "__main__":
    unittest.main()
