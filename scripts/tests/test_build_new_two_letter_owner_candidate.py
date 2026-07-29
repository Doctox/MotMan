from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scripts.build_new_two_letter_owner_candidate import (
    CURRENT_ANCHORS,
    EDITORIAL,
    GRID_ID,
    SHAPE_ID,
    build_grid,
    compare_with_active,
    render_editorial_review,
)
from scripts.build_compact_7x8_review import render_playtest_html
from scripts.editorial_quality import grid_semantic_errors, pilot_editorial_errors
from scripts.grid_topology import audit_grid_topology


ROOT = Path(__file__).resolve().parents[2]


class BuildNewTwoLetterOwnerCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = json.loads(
            (ROOT / "output/quality/agent-new-two-letter/selected-candidate.json")
            .read_text(encoding="utf-8")
        )
        cls.shapes = json.loads(
            (ROOT / "output/quality/new-two-letter-shapes/shape-library.json")
            .read_text(encoding="utf-8")
        )
        cls.active = json.loads(
            (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
        )
        cls.active_snapshot = copy.deepcopy(cls.active)
        cls.grid = build_grid(cls.source, cls.shapes)
        cls.report = audit_grid_topology(
            cls.grid, enforce_layout=False, topology_profile="pilot"
        )

    def test_builds_one_unpublished_grid_without_mutating_active_catalog(self) -> None:
        self.assertEqual(GRID_ID, self.grid["id"])
        self.assertEqual("owner-review-required", self.grid["publicationStatus"])
        self.assertFalse(self.grid["catalogModified"])
        self.assertFalse(self.grid["runtimeModified"])
        self.assertFalse(self.grid["supabaseModified"])
        self.assertEqual(self.active_snapshot, self.active)

    def test_uses_the_certified_new_shape_and_answer_fingerprint(self) -> None:
        self.assertEqual(SHAPE_ID, self.grid["sourceShapeId"])
        comparison = compare_with_active(self.grid, self.active)
        self.assertTrue(comparison["newShape"])
        self.assertTrue(comparison["newAnswerFingerprint"])
        self.assertEqual([], comparison["shapeMatches"])
        self.assertEqual([], comparison["exactAnswerFingerprintMatches"])

    def test_topology_is_complete_with_only_two_reviewed_short_answers(self) -> None:
        self.assertTrue(self.report["valid"], self.report["errors"])
        answers = [word["answer"] for word in self.grid["words"]]
        self.assertEqual(["OS", "OR"], [answer for answer in answers if len(answer) == 2])
        self.assertEqual(0, len(self.report["orphanSegments"]))
        self.assertEqual(
            0,
            sum(
                cell["kind"] == "letter" and not cell["wordIds"]
                for cell in self.report["cells"]
            ),
        )

    def test_every_pair_passes_strict_editorial_and_semantic_gates(self) -> None:
        self.assertEqual(set(EDITORIAL), {word["answer"] for word in self.grid["words"]})
        for word in self.grid["words"]:
            self.assertEqual([], pilot_editorial_errors(word, root=ROOT), word["answer"])
        self.assertEqual([], grid_semantic_errors(self.grid["words"]))

    def test_tone_and_images_match_the_owner_profile(self) -> None:
        current = {
            word["answer"] for word in self.grid["words"]
            if word["culturalStatus"] in {"current-common", "current-pop"}
        }
        self.assertEqual(CURRENT_ANCHORS, current)
        self.assertEqual(5, sum(bool(word.get("image")) for word in self.grid["words"]))
        self.assertEqual(2, sum(word["familiarityBand"] == "thoughtful" for word in self.grid["words"]))

    def test_playtest_contains_no_answers_or_solution_letters(self) -> None:
        page = render_playtest_html([self.report])
        # Two/three-letter answers such as OS/OR/RAP can occur incidentally in
        # HTML/CSS words. Longer answers are a reliable leak detector.
        for answer in (answer for answer in EDITORIAL if len(answer) >= 4):
            self.assertNotIn(answer, page)
        self.assertIn("solutions absentes", page)
        self.assertIn("playtest-letter", page)

    def test_editorial_review_exposes_newness_and_nonpublication(self) -> None:
        comparison = compare_with_active(self.grid, self.active)
        comparison["activeCatalogGridIds"] = [item["id"] for item in self.active["grids"]]
        page = render_editorial_review(self.report, self.grid, comparison)
        self.assertIn("Silhouette inédite", page)
        self.assertIn("staging uniquement", page)
        self.assertIn("MAGNETO", page)
        self.assertIn("Twemoji", page)


if __name__ == "__main__":
    unittest.main()
