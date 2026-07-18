from __future__ import annotations

import sys
import json
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from generate_large_lexical_batch import (  # noqa: E402
    catalog_shape_pool,
    is_editorially_confirmed,
    select_diverse_shortlist,
    shortlist_key,
)
from build_strict_frame_neighbor_shapes import build_neighbors  # noqa: E402
from construct_strict_frame_word_first import endpoints_are_compatible  # noqa: E402


class LargeLexicalBatchTests(unittest.TestCase):
    def test_word_first_endpoints_cannot_cut_another_boundary_answer(self):
        vertical = {column: "A" * 4 for column in range(1, 9)}
        horizontal = {row: "A" * 4 for row in range(1, 10)}
        self.assertFalse(endpoints_are_compatible(vertical, horizontal))
        vertical = {column: "A" * 9 for column in range(1, 9)}
        horizontal = {row: "A" * 8 for row in range(1, 10)}
        self.assertTrue(endpoints_are_compatible(vertical, horizontal))

    def test_neighbor_shapes_preserve_frame_and_topology(self):
        panel = json.loads((
            SCRIPTS.parent
            / "output/quality/strict-frame-free-shapes-panel.json"
        ).read_text(encoding="utf-8"))
        source = next(
            grid for grid in panel["grids"]
            if grid["id"] == "strict-frame-panel-06"
        )
        source_clues = {tuple(cell) for cell in source["clueCells"]}
        neighbors = build_neighbors(source_clues, 2, 6)
        self.assertTrue(neighbors)
        for _score, clues, raw_slots, audit in neighbors:
            self.assertTrue(audit["valid"])
            self.assertLessEqual(
                sum(slot["length"] == 2 for slot in raw_slots), 2
            )
            self.assertLessEqual(
                sum(slot["length"] == 3 for slot in raw_slots), 6
            )

    def test_editorial_confirmation_rejects_tiny_short_word_frequency(self):
        rare_three = {
            "formType": "lemma", "sourceFrequency": 0.01,
            "schoolFrequency": 0,
        }
        common_three = {**rare_three, "sourceFrequency": 2.0}
        self.assertFalse(is_editorially_confirmed("ERG", rare_three))
        self.assertTrue(is_editorially_confirmed("BAC", rare_three))
        self.assertTrue(is_editorially_confirmed("MER", common_three))

    def test_shortlist_rejects_unattested_inflections_before_average_score(self):
        clean = {"quality": {
            "unattestedInflections": 0, "zeroScoreAnswers": 0,
            "reserveAnswers": 2, "activeCatalogAnswers": 0,
            "minimumScore": 20, "averageScore": 35,
            "longAnswers": 10, "threeLetterAnswers": 2,
        }}
        flashy_but_bad = {"quality": {
            "unattestedInflections": 1, "zeroScoreAnswers": 0,
            "reserveAnswers": 0, "activeCatalogAnswers": 0,
            "minimumScore": 60, "averageScore": 70,
            "longAnswers": 15, "threeLetterAnswers": 0,
        }}
        self.assertGreater(shortlist_key(clean), shortlist_key(flashy_but_bad))

    def test_diverse_shortlist_prefers_a_new_shape_and_new_lemmas(self):
        quality = {
            "unattestedInflections": 0, "zeroScoreAnswers": 0,
            "reserveAnswers": 0, "activeCatalogAnswers": 0,
            "minimumScore": 40, "averageScore": 50,
            "longAnswers": 1, "threeLetterAnswers": 1,
        }
        candidates = [
            {"id": "one", "sourceShapeId": "a", "quality": quality,
             "answers": [{"answer": "CHAT", "lemma": "CHAT"}]},
            {"id": "two", "sourceShapeId": "a", "quality": quality,
             "answers": [{"answer": "CHATS", "lemma": "CHAT"}]},
            {"id": "three", "sourceShapeId": "b", "quality": quality,
             "answers": [{"answer": "LIVRE", "lemma": "LIVRE"}]},
        ]
        chosen = select_diverse_shortlist(candidates, 2)
        self.assertEqual([item["id"] for item in chosen], ["one", "three"])
        self.assertEqual(chosen[1]["diversity"]["reusedLemmasWithEarlierShortlist"], 0)

    def test_active_catalog_provides_multiple_valid_geometry_only_shapes(self):
        root = SCRIPTS.parent
        pool = catalog_shape_pool(root / "src/data/grid.catalog.json", 2)
        self.assertGreater(len(pool), 1)
        self.assertTrue(all(item[3]["valid"] for item in pool))


if __name__ == "__main__":
    unittest.main()
