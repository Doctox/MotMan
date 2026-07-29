from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.build_current_two_letter_owner_pilot import (
    EDITORIAL,
    PILOT_GRID_ID,
    SOURCE_GRID_ID,
    build_grid,
    render_editorial_review,
)
from scripts.grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[2]


class BuildCurrentTwoLetterOwnerPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(
            (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
        )
        cls.original = next(
            grid for grid in cls.catalog["grids"] if grid["id"] == SOURCE_GRID_ID
        )
        cls.original_snapshot = copy.deepcopy(cls.original)
        cls.grid = build_grid(cls.catalog)

    def test_builds_a_non_published_temporary_grid_without_mutating_source(self) -> None:
        self.assertEqual(PILOT_GRID_ID, self.grid["id"])
        self.assertEqual("owner-review-required", self.grid["publicationStatus"])
        self.assertFalse(self.grid["catalogModified"])
        self.assertFalse(self.grid["runtimeModified"])
        self.assertFalse(self.grid["supabaseModified"])
        self.assertEqual(self.original_snapshot, self.original)

    def test_keeps_locked_dimensions_and_directions(self) -> None:
        self.assertEqual((7, 8), (self.grid["columns"], self.grid["rows"]))
        self.assertEqual(
            {"across", "down"},
            {word["direction"] for word in self.grid["words"]},
        )
        self.assertTrue(
            all(word.get("arrow") in (None, "right", "down") for word in self.grid["words"])
        )

    def test_contains_exactly_one_reviewed_two_letter_answer(self) -> None:
        short = [word for word in self.grid["words"] if len(word["answer"]) == 2]
        self.assertEqual(["AN"], [word["answer"] for word in short])
        self.assertEqual(
            "human-reviewed-whitelist", short[0]["twoLetterReview"]["status"]
        )
        self.assertTrue(
            all(len(word["answer"]) >= 3 for word in self.grid["words"] if word not in short)
        )

    def test_every_answer_has_a_reviewed_natural_clue(self) -> None:
        self.assertEqual(set(EDITORIAL), {word["answer"] for word in self.grid["words"]})
        self.assertTrue(all(word["clue"].strip() for word in self.grid["words"]))
        self.assertTrue(
            all(all(word["editorialReview"].values()) for word in self.grid["words"])
        )

    def test_tone_has_three_current_anchors_and_five_images(self) -> None:
        current = {
            word["answer"]
            for word in self.grid["words"]
            if word["culturalStatus"] == "current-common"
        }
        self.assertEqual({"SEGMENT", "STATUT", "NET"}, current)
        self.assertEqual(5, sum(bool(word.get("image")) for word in self.grid["words"]))

    def test_editorial_review_exposes_register_sources_and_nonpublication(self) -> None:
        report = audit_grid_topology(
            self.grid, enforce_layout=False, topology_profile="pilot"
        )
        page = render_editorial_review(report, self.grid)
        self.assertIn("Relecture éditoriale", page)
        self.assertIn("Staging uniquement", page)
        self.assertIn("Vocabulaire vidéo courant", page)
        self.assertIn("motman-current-two-letter-pilot-20260722", page)


if __name__ == "__main__":
    unittest.main()
