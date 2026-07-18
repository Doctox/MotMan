from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from build_owner_low_short_review import RAW, build_grid  # noqa: E402
from craft_flexible_common_grid import normalized  # noqa: E402
from grid_topology import audit_grid_topology  # noqa: E402
from agent_editorialize_shifted import family_audit, load_lemmas  # noqa: E402


class OwnerLowShortReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.grid = build_grid(json.loads(RAW.read_text(encoding="utf-8")))
        cls.report = audit_grid_topology(cls.grid, enforce_layout=False)

    def test_accents_are_normalized_for_crossings(self) -> None:
        self.assertEqual("CHENE", normalized("CHÊNE"))
        self.assertEqual("EMERAUDE", normalized("ÉMERAUDE"))
        self.assertEqual("AOUT", normalized("AOÛT"))

    def test_grid_has_at_most_two_two_letter_answers(self) -> None:
        answers = [word["answer"] for word in self.grid["words"]]
        self.assertEqual(["RA", "NI"], [word for word in answers if len(word) == 2])

    def test_topology_is_complete(self) -> None:
        self.assertTrue(self.report["valid"], self.report["errors"])
        letters = [cell for cell in self.report["cells"] if cell["kind"] == "letter"]
        self.assertTrue(all(cell["wordIds"] for cell in letters))
        self.assertEqual([], self.report["orphanSegments"])

    def test_etre_and_est_are_detected_as_one_repeated_family(self) -> None:
        answers = [word["answer"] for word in self.grid["words"]]
        audit = family_audit(answers, load_lemmas())
        self.assertEqual(["ETRE", "EST"], audit["duplicateFamilies"]["ETRE"])


if __name__ == "__main__":
    unittest.main()
