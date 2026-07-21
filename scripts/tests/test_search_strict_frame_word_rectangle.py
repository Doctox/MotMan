from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from search_strict_frame_word_rectangle import (  # noqa: E402
    REVIEWED_IMAGE_NUCLEUS,
    cache_signature,
    checkpoint_signature,
    load_cached_payload,
    load_root_checkpoint,
    ordered_domain_digest,
)
from word_rectangle_filler import RectangleEntry  # noqa: E402


def signature_args(**overrides):
    values = {
        "minimum_zipf": 2.0,
        "minimum_constructor_score": 5.0,
        "minimum_familiarity_zipf": 2.8,
        "max_unfamiliar_answers": 3,
        "maximum_grammar_answers": 1,
        "minimum_images": 0,
        "seed": 1,
        "seconds": 10.0,
        "node_limit": 1000,
        "orientation": "row-first",
        "explore_randomly": False,
        "pilot_safe_short_only": True,
        "solution_limit": 8,
        "minimum_solution_distance": 1,
        "reference_catalog": [],
        "avoid_fill": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class StrictFrameWordRectangleTests(unittest.TestCase):
    def test_reviewed_image_nucleus_has_only_usable_rectangle_lengths(self) -> None:
        self.assertIn("ANANAS", REVIEWED_IMAGE_NUCLEUS)
        self.assertIn("ABEILLE", REVIEWED_IMAGE_NUCLEUS)
        self.assertTrue(all(len(answer) in {6, 7} for answer in REVIEWED_IMAGE_NUCLEUS))

    def test_cache_signature_includes_search_budget(self) -> None:
        short_key, short_inputs = cache_signature(signature_args(seconds=10.0))
        long_key, _ = cache_signature(signature_args(seconds=20.0))
        self.assertNotEqual(short_key, long_key)
        self.assertEqual(10.0, short_inputs["configuration"]["maxSeconds"])

    def test_checkpoint_signature_excludes_only_time_and_node_budgets(self) -> None:
        first_key, first_inputs = checkpoint_signature(
            signature_args(seconds=10.0, node_limit=1_000)
        )
        increased_key, _ = checkpoint_signature(
            signature_args(seconds=90.0, node_limit=9_000)
        )
        changed_seed_key, _ = checkpoint_signature(signature_args(seed=2))

        self.assertEqual(first_key, increased_key)
        self.assertNotEqual(first_key, changed_seed_key)
        self.assertNotIn("maxSeconds", first_inputs["configuration"])
        self.assertNotIn("nodeLimit", first_inputs["configuration"])

    def test_checkpoint_signature_invalidates_a_domain_order_change(self) -> None:
        first = RectangleEntry("MAISON", "MAISON", 10.0, 5.0)
        second = RectangleEntry("SOLEIL", "SOLEIL", 9.0, 5.0)
        ordered = ordered_domain_digest([first, second], [])
        reversed_order = ordered_domain_digest([second, first], [])
        ordered_key, _ = checkpoint_signature(
            signature_args(), domain_order_digest=ordered
        )
        reversed_key, _ = checkpoint_signature(
            signature_args(), domain_order_digest=reversed_order
        )

        self.assertNotEqual(ordered, reversed_order)
        self.assertNotEqual(ordered_key, reversed_key)

    def test_cache_signature_is_reproducible(self) -> None:
        first, _ = cache_signature(signature_args())
        second, _ = cache_signature(signature_args())
        self.assertEqual(first, second)

    def test_matching_cache_key_reuses_terminal_output(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "attempt.json"
            output.write_text(
                '{"kind":"compact-7x8-strict-word-rectangle-search",'
                '"cacheKey":"abc","complete":false,"solverTelemetry":{}}',
                encoding="utf-8",
            )
            self.assertIsNotNone(load_cached_payload(output, "abc"))
            self.assertIsNone(load_cached_payload(output, "different"))
            self.assertIsNone(load_cached_payload(output, "abc", force=True))

    def test_root_checkpoint_requires_matching_domain_signature(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "attempt.json"
            output.write_text(
                '{"kind":"compact-7x8-strict-word-rectangle-search",'
                '"rootCheckpoint":{"version":1,"checkpointKey":"domain-abc",'
                '"completedRootBranches":["MAISON"],"provenSolutions":[]}}',
                encoding="utf-8",
            )
            checkpoint = load_root_checkpoint(output, "domain-abc")
            self.assertEqual(["MAISON"], checkpoint["completedRootBranches"])
            self.assertIsNone(load_root_checkpoint(output, "changed-domain"))
            self.assertIsNone(load_root_checkpoint(output, "domain-abc", force=True))


if __name__ == "__main__":
    unittest.main()
