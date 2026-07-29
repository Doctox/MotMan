from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_certified_editorial_sublot_111bca5d3810 as preparation


class CertifiedEditorialSublot111bca5d3810Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document, cls.lexical_audit = preparation.verify_source()
        cls.by_candidate = {
            grid["candidateId"]: grid for grid in cls.document["grids"]
        }
        cls.retained_sources = [
            cls.by_candidate[candidate_id]
            for candidate_id in preparation.RETAINED_CANDIDATES
        ]
        cls.grids = [
            preparation.build_grid(source) for source in cls.retained_sources
        ]

    def test_source_contract_and_hashes_are_valid(self) -> None:
        self.assertEqual(self.document["schema"], preparation.EXPECTED_SCHEMA)
        self.assertEqual(
            self.document["manifest"]["payloadSha256"],
            preparation.EXPECTED_PAYLOAD_SHA256,
        )
        self.assertTrue(
            self.lexical_audit["contract_validation"]["contract_valid"]
        )
        self.assertTrue(self.lexical_audit["contract_validation"]["words_only"])

    def test_selection_is_exhaustive_and_owner_rules_are_applied(self) -> None:
        self.assertEqual(len(self.by_candidate), 33)
        self.assertEqual(len(preparation.RETAINED_CANDIDATES), 15)
        self.assertEqual(len(preparation.EXCLUSIONS), 18)
        self.assertEqual(
            set(self.by_candidate),
            set(preparation.RETAINED_CANDIDATES) | set(preparation.EXCLUSIONS),
        )
        self.assertEqual(
            preparation.EXCLUSIONS[
                "e9a3ddde-9e24-4fe1-9e42-9a9ff2f6a1c9"
            ]["category"],
            "owner-avoid-next-lot",
        )

    def test_all_retained_answers_have_short_mutualized_definitions(self) -> None:
        retained_answers = set().union(
            *(
                preparation.source_answer_set(source)
                for source in self.retained_sources
            )
        )
        self.assertEqual(retained_answers, set(preparation.CLUES))
        self.assertEqual(len(preparation.CLUES), 200)
        for answer, clue in preparation.CLUES.items():
            with self.subTest(answer=answer):
                words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]+", clue)
                self.assertGreater(len(words), 0)
                self.assertLessEqual(len(words), 3)

    def test_real_blacklist_is_clear_and_cooldown_is_not_a_gate(self) -> None:
        report = preparation.blacklist_audit(self.retained_sources)
        self.assertTrue(report["valid"])
        self.assertEqual(report["answerHits"], {})
        self.assertEqual(report["cooccurrenceHits"], {})
        self.assertEqual(
            report["rotationCooldownHandling"],
            "warning-and-penalty-owner-override; never treated as a hard gate",
        )

    def test_active_retired_and_definition_crosschecks_are_clear(self) -> None:
        catalog_summary = self.lexical_audit["catalog_summary"]
        active_duplicates = preparation.duplicate_candidate_ids(
            catalog_summary["exact_active_duplicates"]
        )
        self.assertEqual(
            active_duplicates,
            {
                "0092d1d2-c124-4493-bca6-37703e8764d0",
                "081c89e3-c392-4258-a0e0-cffec95b2f43",
                "5354b8e2-bf35-45ce-9cbd-d96f1bbf7012",
            },
        )
        self.assertFalse(
            set(preparation.RETAINED_CANDIDATES) & active_duplicates
        )
        self.assertFalse(
            set(preparation.RETAINED_CANDIDATES)
            & preparation.duplicate_candidate_ids(
                catalog_summary["exact_retired_duplicates"]
            )
        )
        crosscheck = preparation.active_definition_crosscheck(self.grids)
        self.assertTrue(crosscheck["valid"])
        self.assertEqual(
            crosscheck["sameLengthDifferentAnswerConflicts"],
            [],
        )

    def test_stable_ids_and_pilot_topology_are_valid(self) -> None:
        self.assertEqual(len(self.grids), 15)
        self.assertEqual(
            sum(len(grid["words"]) for grid in self.grids),
            242,
        )
        word_ids = [
            word["wordId"] for grid in self.grids for word in grid["words"]
        ]
        self.assertEqual(len(word_ids), len(set(word_ids)))
        for grid in self.grids:
            with self.subTest(grid=grid["id"]):
                report = preparation.audit_grid_topology(
                    grid,
                    require_word_ids=True,
                    enforce_layout=False,
                    topology_profile="pilot",
                )
                self.assertTrue(report["valid"], report["errors"])

    def test_image_clues_are_reviewed_existing_assets(self) -> None:
        image_words = [
            word
            for grid in self.grids
            for word in grid["words"]
            if word.get("image")
        ]
        self.assertEqual(len(image_words), 22)
        for word in image_words:
            with self.subTest(answer=word["answer"]):
                self.assertEqual(word["clue"], "")
                self.assertTrue(word["editorialDefinition"])
                self.assertEqual(
                    word["imageStatus"],
                    "reviewed-recognizable-licensed",
                )
                self.assertTrue(word["image"]["alreadyAvailableInMotMan"])
                self.assertFalse(word["image"]["requiresNewAabAsset"])
                self.assertTrue(word["image"]["asset"].startswith("data:image/"))

    def test_requested_flagged_forms_have_explicit_decisions(self) -> None:
        self.assertEqual(
            set(preparation.FLAGGED_FORM_REVIEWS),
            {
                "ALIAGAS",
                "DEFACER",
                "FOSTER",
                "LOPEZ",
                "LOUNGE",
                "TAUTOU",
                "DRE",
                "ETAGEE",
                "REFERE",
            },
        )
        retained = {
            answer
            for answer, review in preparation.FLAGGED_FORM_REVIEWS.items()
            if review["status"] == "accepted-retained"
        }
        self.assertEqual(
            retained,
            {"ALIAGAS", "DEFACER", "LOPEZ", "TAUTOU", "DRE", "REFERE"},
        )
        self.assertEqual(
            {item["answer"] for item in preparation.HUMAN_DECISION_ITEMS},
            {"ALIAGAS", "SUE", "LURONNE", "PARTNER"},
        )

    def test_review_artifacts_exist_and_playtest_hides_answers(self) -> None:
        for path in (
            preparation.STAGING_PATH,
            preparation.AUDIT_PATH,
            preparation.SELECTION_PATH,
            preparation.REVIEW_PATH,
            preparation.PLAYTEST_PATH,
            preparation.ARTIFACT_MANIFEST_PATH,
        ):
            self.assertTrue(path.is_file(), path)
        playtest = preparation.PLAYTEST_PATH.read_text(encoding="utf-8")
        self.assertIn("solutions absentes", playtest)
        self.assertIn("playtest-letter", playtest)
        for answer in (
            "PLACARD",
            "ALIAGAS",
            "DEFACER",
            "TAUTOU",
            "MALOTRU",
            "OCARINA",
            "TRUANDE",
        ):
            self.assertNotIn(answer, playtest)

    def test_catalogs_remain_exactly_on_v20_baseline(self) -> None:
        baseline = preparation.verify_catalog_baseline()
        self.assertEqual(baseline["version"], 20)
        self.assertEqual(baseline["gridCount"], 29)
        self.assertEqual(
            baseline["catalogSha256"],
            preparation.EXPECTED_CATALOG_SHA256,
        )
        self.assertEqual(
            baseline["runtimeSha256"],
            preparation.EXPECTED_RUNTIME_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
