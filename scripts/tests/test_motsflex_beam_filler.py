import random
import sys
import unittest
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from motsflex_beam_filler import fill_motsflex_beam


def indexes(words):
    by_length = defaultdict(list)
    frequency = {}
    concept_group = {}
    semantic_conflicts = {}
    difficulty = {}
    for word in words:
        by_length[len(word)].append(word)
        frequency[word] = 1
        concept_group[word] = word
        semantic_conflicts[word] = set()
        difficulty[word] = "normal"
    return by_length, {}, frequency, concept_group, semantic_conflicts, difficulty, set()


class MotsflexBeamFillerTest(unittest.TestCase):
    def test_required_image_slot_restricts_domain(self):
        slot = SimpleNamespace(
            cells=((1, 1), (1, 2), (1, 3), (1, 4)),
            direction="across",
            clue=(1, 0),
        )
        source_indexes = list(indexes(["CHAT", "LION"]))
        source_indexes[6] = {"LION"}
        result = fill_motsflex_beam(
            [slot],
            tuple(source_indexes),
            random.Random(7),
            required_image_slots={0},
            image_answers={"LION"},
            max_seconds=1,
        )
        self.assertEqual(result, {0: "LION"})

    def test_required_image_slot_without_matching_length_is_rejected(self):
        slot = SimpleNamespace(
            cells=((1, 1), (1, 2), (1, 3), (1, 4)),
            direction="across",
            clue=(1, 0),
        )
        telemetry = {}
        result = fill_motsflex_beam(
            [slot],
            indexes(["CHAT", "LION"]),
            random.Random(7),
            required_image_slots={0},
            image_answers={"BUS"},
            max_seconds=1,
            telemetry=telemetry,
        )
        self.assertIsNone(result)
        self.assertEqual(telemetry["reason"], "initial-zero-domain")


if __name__ == "__main__":
    unittest.main()
