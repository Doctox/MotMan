from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import generate_grid_catalog as generator  # noqa: E402


class GeneratorGeometryTests(unittest.TestCase):
    @staticmethod
    def canonical_shape(shape: set[tuple[int, int]]) -> tuple:
        variants = []
        for transform in range(8):
            variant = set()
            for row, col in shape:
                if transform >= 4:
                    col = generator.SIZE - 1 - col
                for _ in range(transform % 4):
                    row, col = col, generator.SIZE - 1 - row
                variant.add((row, col))
            variants.append(tuple(sorted(variant)))
        return min(variants)

    def test_index_excludes_blocked_editorial_pairs(self) -> None:
        def entry(answer: str, clue: str) -> dict:
            return {
                "answer": answer, "clue": clue, "sourceClue": clue,
                "length": len(answer), "frequency": 5.0, "difficulty": "easy",
                "sourceType": "dictionary", "sourceId": "test",
                "editorialStatus": "human-reviewed",
            }

        indexes = generator.build_index([
            entry("BEL", "Joli"),
            entry("III", "Chiffres romains"),
            entry("XII", "Douze romain"),
            entry("VERS", ""),
            entry("XII", "12 romain"),
        ])
        self.assertEqual(["XII"], indexes[0][3])

    def test_crossword_inflection_not_marked_as_lemma_is_excluded(self) -> None:
        entry = {
            "answer": "TUA", "clue": "Descendit", "sourceClue": "Descendit",
            "length": 3, "frequency": 5.0, "difficulty": "normal",
            "sourceType": "crossword", "sourceId": "test",
            "editorialStatus": "source-backed",
        }
        self.assertNotIn("TUA", generator.build_index([entry])[0][3])

    def test_all_shipping_shapes_have_complete_declared_topology(self) -> None:
        for shape in generator.SHAPES:
            clues = set(shape)
            slots = generator.slots_for(clues)
            self.assertEqual([], generator.shape_errors(clues, slots))
            self.assertTrue(all(slot.arrow in {"right", "down"} for slot in slots))
            for slot in slots:
                row, col = slot.clue
                expected_start = (row, col + 1) if slot.direction == "across" else (row + 1, col)
                self.assertEqual(expected_start, slot.cells[0])
            clue_uses = Counter(slot.clue for slot in slots)
            self.assertGreaterEqual(sum(uses == 2 for uses in clue_uses.values()), 3)
            visible = clues - {(0, 0)}
            interior_adjacent_pairs = sum(
                neighbor in visible
                for row, col in visible
                for neighbor in ((row + 1, col), (row, col + 1))
                if not (row == 0 and neighbor[0] == 0)
                and not (col == 0 and neighbor[1] == 0)
            )
            self.assertLessEqual(interior_adjacent_pairs, 2)
            counts = Counter(len(slot.cells) for slot in slots)
            self.assertGreaterEqual(len(counts), 4)
            self.assertLessEqual(max(counts.values()) / sum(counts.values()), .35)
            covered = {cell for slot in slots for cell in slot.cells}
            expected_letters = {
                (row, col)
                for row in range(generator.SIZE)
                for col in range(generator.SIZE)
            } - clues
            self.assertEqual(expected_letters, covered)

    def test_transposed_shipping_shapes_keep_direct_starts(self) -> None:
        for shape in generator.SHAPES:
            clues = {(col, row) for row, col in shape}
            slots = generator.slots_for(clues)
            self.assertEqual([], generator.shape_errors(clues, slots))
            self.assertTrue(all(slot.arrow in {"right", "down"} for slot in slots))

    def test_shipping_shapes_are_distinct_beyond_rotations_and_reflections(self) -> None:
        canonical = [self.canonical_shape(set(shape)) for shape in generator.SHAPES]
        self.assertEqual(len(canonical), len(set(canonical)))

    def test_library_spreads_non_structural_clues_and_adjacent_pairs(self) -> None:
        position_usage = Counter(
            cell for shape in generator.SHAPES for cell in set(shape) - {(0, 0)}
        )
        # Direct arrows necessarily repeat part of the top/left launch border;
        # variation must happen in the interior.
        structural = {
            (row, col) for row in range(generator.SIZE) for col in range(generator.SIZE)
            if row == 0 or col == 0
        }
        self.assertLessEqual(
            max(count for cell, count in position_usage.items() if cell not in structural),
            len(generator.SHAPES),
        )

        pair_usage = Counter()
        for shape in generator.SHAPES:
            visible = set(shape) - {(0, 0)}
            pairs = {
                tuple(sorted((cell, neighbor)))
                for cell in visible
                for neighbor in ((cell[0] + 1, cell[1]), (cell[0], cell[1] + 1))
                if neighbor in visible
            }
            pair_usage.update(pairs)
        self.assertGreaterEqual(len(pair_usage), 8)

    def test_legacy_shape_with_fake_border_runs_is_rejected(self) -> None:
        legacy = {
            (0, 0), (0, 3), (0, 8), (1, 1), (1, 6), (2, 1), (2, 2),
            (2, 7), (3, 2), (3, 4), (3, 5), (4, 3), (5, 3), (6, 8),
            (7, 1), (8, 0),
        }
        errors = generator.shape_errors(legacy, generator.slots_for(legacy))
        self.assertTrue(any(error.startswith("segment orphelin") for error in errors))


if __name__ == "__main__":
    unittest.main()
