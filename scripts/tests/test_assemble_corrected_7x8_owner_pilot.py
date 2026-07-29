from __future__ import annotations

import json
import unittest

from scripts.assemble_corrected_7x8_owner_pilot import DEFAULT_CANDIDATE, build


class AssembleCorrectedOwnerPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = build(json.loads(DEFAULT_CANDIDATE.read_text(encoding="utf-8")))
        cls.grid = cls.payload["grids"][0]

    def test_keeps_locked_dimensions_and_four_images(self) -> None:
        self.assertEqual((self.grid["columns"], self.grid["rows"]), (7, 8))
        self.assertEqual(self.grid["minimumImages"], 4)
        self.assertEqual(len(self.grid["imageAnswers"]), 4)

    def test_all_answers_are_editorialized_and_at_least_three_letters(self) -> None:
        answers = self.grid["answers"]
        self.assertEqual(len(answers), 14)
        self.assertTrue(all(len(item["answer"]) >= 3 for item in answers))
        self.assertTrue(all(item["definition"].strip() for item in answers))

    def test_never_marks_the_pilot_as_published(self) -> None:
        self.assertFalse(self.payload["catalogModified"])
        self.assertFalse(self.payload["runtimeModified"])
        self.assertEqual(self.grid["publicationStatus"], "owner-review-required")


if __name__ == "__main__":
    unittest.main()
