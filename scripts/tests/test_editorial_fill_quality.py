from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from editorial_fill_quality import (  # noqa: E402
    audit_candidate_batch,
    blocking_pair_reasons,
    editorial_entry_score,
)


class EditorialFillQualityTests(unittest.TestCase):
    def test_reviewed_root_outranks_rare_mechanical_inflection(self) -> None:
        root = editorial_entry_score(
            "NIER",
            {
                "lemma": "NIER",
                "wordfreqZipf": 4.03,
                "centralClue": "Contester",
                "editorialStatus": "source-backed",
            },
        )
        inflection = editorial_entry_score(
            "NIERA",
            {
                "lemma": "NIER",
                "wordfreqZipf": 2.37,
                "centralClue": "Contestera",
                "editorialStatus": "source-backed",
            },
        )
        self.assertGreater(root, inflection + 25)

    def test_active_catalog_use_dominates_frequency(self) -> None:
        metadata = {
            "lemma": "EGO",
            "wordfreqZipf": 4.0,
            "centralClue": "Moi profond",
            "editorialStatus": "source-backed",
        }
        self.assertGreater(
            editorial_entry_score("EGO", metadata),
            editorial_entry_score("EGO", metadata, active_uses=1),
        )

    def test_human_review_label_never_overrides_known_semantic_error(self) -> None:
        metadata = {
            "centralClue": "Galaxie lointaine",
            "editorialStatus": "human-reviewed",
            "semanticStatus": "rejected",
        }
        self.assertIn("rejected-pair-status", blocking_pair_reasons("UNIVERS", metadata))
        self.assertEqual(0.0, editorial_entry_score("UNIVERS", metadata))

    def test_batch_gate_blocks_blacklist_and_repeats_but_warns_on_cooldown(self) -> None:
        blacklist = {
            "rejectedAnswers": ["SARCLE", "NIERA"],
            "rotationCooldownAnswers": [{"answer": "EGO"}, {"answer": "OM"}],
        }
        grids = [
            {"id": "new-1", "answers": [
                {"answer": "EGO"}, {"answer": "SARCLE"}, {"answer": "FRAIS"},
            ]},
            {"id": "new-2", "answers": [
                {"answer": "FRAIS"}, {"answer": "OM"}, {"answer": "NIERA"},
            ]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "catalog.json"
            reference.write_text(json.dumps({
                "grids": [{"id": "active", "words": [{"answer": "EGO"}]}]
            }), encoding="utf-8")
            report = audit_candidate_batch(
                grids,
                blacklist_document=blacklist,
                reference_paths=[reference],
            )
        self.assertFalse(report["valid"])
        self.assertEqual(["new-1", "new-2"], report["internalRepeats"]["FRAIS"])
        reasons = {error["reason"] for error in report["errors"]}
        self.assertTrue({"blacklistedAnswers", "internalRepeats"} <= reasons)
        self.assertNotIn("cooldownAnswers", reasons)
        warning_reasons = {warning["reason"] for warning in report["warnings"]}
        self.assertIn("activeCatalogRepeats", warning_reasons)
        self.assertIn("cooldownAnswers", warning_reasons)


if __name__ == "__main__":
    unittest.main()
