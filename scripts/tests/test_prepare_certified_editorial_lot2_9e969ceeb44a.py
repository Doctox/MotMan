from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_certified_editorial_lot2_9e969ceeb44a as preparation


class CertifiedEditorialLot29e969ceeb44aTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document, cls.lexical_audit, cls.provenance = preparation.verify_source()
        cls.by_candidate = {
            str(grid["candidateId"]): grid for grid in cls.document["grids"]
        }
        cls.retained_sources = [
            cls.by_candidate[candidate_id]
            for candidate_id in preparation.RETAINED_CANDIDATES
        ]
        cls.grids = [preparation.build_grid(source) for source in cls.retained_sources]

    def test_source_contract_digest_lineage_and_words_only_are_valid(self) -> None:
        self.assertEqual(self.document["schema"], preparation.EXPECTED_SCHEMA)
        self.assertEqual(len(self.document["grids"]), 54)
        self.assertEqual(len(self.document["manifest"]["candidateStates"]), 286)
        self.assertEqual(
            self.document["manifest"]["payloadSha256"],
            preparation.EXPECTED_PAYLOAD_SHA256,
        )
        self.assertEqual(preparation.walk_editorial_fields(self.document), [])
        self.assertTrue(self.provenance["intrinsicContractValid"])
        self.assertEqual(
            self.provenance["externalSnapshotStatus"],
            "expected-divergence-recorded",
        )
        self.assertFalse(self.provenance["externalContractValid"])

    def test_selection_is_exhaustive_disjoint_and_diverse(self) -> None:
        retained = set(preparation.RETAINED_CANDIDATES)
        excluded = set(preparation.EXCLUSIONS)
        self.assertEqual(len(retained), 12)
        self.assertEqual(len(excluded), 42)
        self.assertFalse(retained & excluded)
        self.assertEqual(set(self.by_candidate), retained | excluded)
        pairwise = preparation.selected_pairwise(self.retained_sources)
        self.assertEqual(len(pairwise), 66)
        self.assertEqual(max(item["proximityPercent"] for item in pairwise), 6.9)
        self.assertTrue(all(item["proximityPercent"] < 80 for item in pairwise))

    def test_active_catalog_and_blacklist_crosschecks_are_clear(self) -> None:
        active = preparation.active_catalog_crosscheck(self.retained_sources)
        self.assertTrue(active["valid"])
        self.assertEqual(active["catalogVersion"], 22)
        self.assertEqual(active["activeGridCount"], 44)
        self.assertEqual(active["exactDuplicates"], [])
        blacklist = preparation.base.blacklist_audit(self.retained_sources)
        self.assertTrue(blacklist["valid"])
        self.assertEqual(blacklist["answerHits"], {})
        self.assertEqual(blacklist["cooccurrenceHits"], {})

    def test_all_answers_have_short_mutualized_definitions(self) -> None:
        retained_answers = set().union(
            *(preparation.source_answer_set(source) for source in self.retained_sources)
        )
        self.assertEqual(retained_answers, set(preparation.CLUES))
        self.assertEqual(len(preparation.CLUES), 166)
        for answer, clue in preparation.CLUES.items():
            with self.subTest(answer=answer):
                words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]+", clue)
                self.assertGreater(len(words), 0)
                if len(words) > 3:
                    self.assertIn(answer, preparation.OWNER_APPROVED_LONG_CLUES)
        self.assertEqual(
            set(preparation.OWNER_APPROVED_LONG_CLUES),
            {"BEIGNET", "RACHAT", "SETTER", "TEE"},
        )

    def test_stable_ids_and_all_pilot_topologies_are_valid(self) -> None:
        self.assertEqual(len(self.grids), 12)
        self.assertEqual(sum(len(grid["words"]) for grid in self.grids), 190)
        word_ids = [word["wordId"] for grid in self.grids for word in grid["words"]]
        self.assertEqual(len(word_ids), len(set(word_ids)))
        grid_ids = [grid["id"] for grid in self.grids]
        self.assertEqual(len(grid_ids), len(set(grid_ids)))
        for grid in self.grids:
            with self.subTest(grid=grid["id"]):
                report = preparation.base.audit_grid_topology(
                    grid,
                    require_word_ids=True,
                    enforce_layout=False,
                    topology_profile="pilot",
                )
                self.assertTrue(report["valid"], report["errors"])

    def test_latest_owner_definition_decisions_are_applied(self) -> None:
        expected = {
            "BEIGNET": "Pâtisserie du flic américain",
            "BRAVOS": "Applaudissements",
            "CALMANT": "Apaisant",
            "ECAILLE": "Armure du poisson",
            "ECHELLE": "Suite progressive",
            "ERRE": "Vagabonde",
            "LASCAR": "Homme rusé",
            "ONDE": "Vibration propagée",
            "PISTARD": "Motard sur piste",
            "RACHAT": "Acquérir une nouvelle fois",
            "SETTER": "Chien de chasse à poil long",
            "TEE": "Support de balle de golf",
        }
        for answer, definition in expected.items():
            with self.subTest(answer=answer):
                self.assertEqual(preparation.CLUES[answer], definition)

    def test_images_are_reviewed_licensed_and_require_no_aab(self) -> None:
        image_words = [
            word
            for grid in self.grids
            for word in grid["words"]
            if word.get("image")
        ]
        self.assertEqual(
            {word["answer"] for word in image_words},
            {"ART", "FRAISES", "LION", "MIEL", "OIE", "RAISIN", "ROI", "SEAU", "SMS"},
        )
        self.assertEqual(len(image_words), 10)
        self.assertNotIn("PIC", {word["answer"] for word in image_words})
        self.assertNotIn("ONDE", {word["answer"] for word in image_words})
        for word in image_words:
            with self.subTest(answer=word["answer"]):
                self.assertEqual(word["clue"], "")
                self.assertTrue(word["editorialDefinition"])
                self.assertEqual(word["imageStatus"], "reviewed-recognizable-licensed")
                self.assertEqual(
                    word["image"]["alreadyAvailableInMotMan"],
                    word["answer"] != "MIEL",
                )
                self.assertFalse(word["image"]["requiresNewAabAsset"])
                self.assertTrue(word["image"]["asset"].startswith("data:image/"))

    def test_human_decisions_are_limited_and_explicit(self) -> None:
        self.assertEqual(
            {item["answer"] for item in preparation.HUMAN_DECISION_ITEMS},
            {"MATETA", "MERDIER"},
        )
        self.assertEqual(
            preparation.FLAGGED_FORM_REVIEWS["MATETA"]["status"],
            "décision-propriétaire",
        )
        self.assertEqual(
            preparation.FLAGGED_FORM_REVIEWS["MERDIER"]["status"],
            "décision-propriétaire",
        )

    def test_review_artifacts_exist_and_playtest_hides_answers(self) -> None:
        paths = (
            preparation.SELECTION_PATH,
            preparation.STAGING_PATH,
            preparation.AUDIT_PATH,
            preparation.REVIEW_PATH,
            preparation.PLAYTEST_PATH,
            preparation.ARTIFACT_MANIFEST_PATH,
        )
        for path in paths:
            self.assertTrue(path.is_file(), path)
        review = preparation.REVIEW_PATH.read_text(encoding="utf-8")
        playtest = preparation.PLAYTEST_PATH.read_text(encoding="utf-8")
        self.assertIn("REVUE PROPRIÉTAIRE", review)
        self.assertIn("solutions absentes", playtest)
        self.assertIn("playtest-letter", playtest)
        self.assertIn(
            ".solution-toggle,details,.grid-review>h3,.grid-review>ul{display:none!important}",
            playtest,
        )
        self.assertNotIn("class='letter-value'", playtest)
        for answer in sorted(preparation.CLUES, key=len, reverse=True):
            if len(answer) >= 6:
                with self.subTest(answer=answer):
                    self.assertNotRegex(playtest, rf"\b{re.escape(answer)}\b")

    def test_artifact_manifest_hashes_match_and_publication_is_disabled(self) -> None:
        manifest = json.loads(
            preparation.ARTIFACT_MANIFEST_PATH.read_text(encoding="utf-8")
        )
        self.assertFalse(manifest["catalogMutation"])
        self.assertFalse(manifest["supabaseMutation"])
        self.assertFalse(manifest["publicationAuthorized"])
        for artifact in manifest["artifacts"]:
            path = Path(artifact["path"])
            with self.subTest(path=path):
                self.assertEqual(preparation.base.sha256_file(path), artifact["sha256"])
                self.assertEqual(path.stat().st_size, artifact["bytes"])

    def test_catalogs_remain_exactly_on_v22_baseline(self) -> None:
        baseline = preparation.verify_catalog_baseline()
        self.assertEqual(baseline["version"], 22)
        self.assertEqual(baseline["gridCount"], 44)
        self.assertEqual(
            baseline["catalogSha256"], preparation.EXPECTED_CATALOG_SHA256
        )
        self.assertEqual(
            baseline["runtimeSha256"], preparation.EXPECTED_RUNTIME_SHA256
        )
        self.assertEqual(baseline["supabase"]["activeGridCount"], 44)
        self.assertTrue(baseline["supabase"]["matchesLocalRuntimeIds"])


if __name__ == "__main__":
    unittest.main()
