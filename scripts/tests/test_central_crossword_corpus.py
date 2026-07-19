from __future__ import annotations

import gzip
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_jeuxdemots_corpus import relation_priority  # noqa: E402
import generate_grid_catalog as generator  # noqa: E402


class CentralCrosswordCorpusTests(unittest.TestCase):
    def test_stronger_jeuxdemots_relation_has_priority(self) -> None:
        weak = {"sourceRelationWeight": 30, "minimumSourceFrequency": 20, "clueSourceFrequency": 20, "clue": "Faible"}
        strong = {"sourceRelationWeight": 120, "minimumSourceFrequency": 3, "clueSourceFrequency": 3, "clue": "Fort"}
        self.assertGreater(relation_priority(strong), relation_priority(weak))

    def test_built_central_corpus_is_large_and_excludes_dbnary(self) -> None:
        path = ROOT / "src/data/crossword.central.json.gz"
        if not path.exists():
            self.skipTest("corpus central pas encore construit")
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            document = json.load(handle)
        self.assertGreaterEqual(document["metrics"]["distinctAnswers"], 15_000)
        self.assertGreaterEqual(document["metrics"]["jeuxDeMotsDistinctAnswers"], 14_000)
        self.assertFalse(document["metrics"]["dbnaryIncluded"])
        self.assertEqual(
            document["metrics"]["generatorEligibleDistinctAnswers"],
            sum(entry["canonicalForGenerator"] for entry in document["entries"]),
        )
        canonical_pairs = {
            (entry["answer"], entry.get("clue", ""))
            for entry in document["entries"]
            if entry["canonicalForGenerator"]
        }
        self.assertNotIn(("BEE", "Grande ouverte"), canonical_pairs)
        self.assertNotIn(("GIS", "Es couché"), canonical_pairs)
        approved_jdm = [
            entry for entry in document["entries"]
            if entry.get("canonicalForGenerator")
            and entry.get("sourceId") == "jeuxdemots-r_syn-sanitized"
        ]
        approved_document = json.loads(
            (ROOT / "src/data/crossword.jeuxdemots.approved.json").read_text(
                encoding="utf-8"
            )
        )
        blacklist = json.loads(
            (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
        )
        blocked_answers = set(blacklist.get("rejectedAnswers", []))
        blocked_answers.update(blacklist.get("rejectedEasyAnswers", []))
        blocked_answers.update(blacklist.get("rejectedNormalAnswers", []))
        blocked_answers.update(
            item["answer"] for item in blacklist.get("rotationCooldownAnswers", [])
        )
        expected_active_answers = {
            entry["answer"] for entry in approved_document["entries"]
            if entry["answer"] not in blocked_answers
        }
        self.assertEqual(len(expected_active_answers), len(approved_jdm))
        self.assertGreaterEqual(len(approved_jdm), 1_144)
        self.assertTrue(all(entry.get("editorialStatus") == "human-reviewed" for entry in approved_jdm))

    def test_owner_reviewed_short_answers_are_preserved(self) -> None:
        path = ROOT / "src/data/crossword.central.json.gz"
        if not path.exists():
            self.skipTest("corpus central pas encore construit")
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            document = json.load(handle)
        expected = {
            ("CPE", "Conseiller scolaire"),
            ("TOM", "Prénom de Voldemort"),
            ("POP", "Musique populaire"),
            ("RAP", "Musique scandée"),
            ("TRAP", "Rap électronique"),
            ("JAZZ", "Musique improvisée"),
            ("SAC", "Bagage dorsal"),
            ("CLAC", "Bruit de porte"),
            ("MAP", "Carte en anglais"),
            ("TPE", "Terminal de paiement"),
            ("CB", "Carte bancaire"),
            ("PNG", "Format d'image"),
            ("LOT", "Groupement"),
            ("TOT", "De bonne heure"),
            ("LIT", "Dodo"),
            ("NIL", "Fleuve d'Afrique"),
            ("BAC", "Examen du lycée"),
            ("PAC", "Politique agricole"),
            ("TIG", "Soudure électrode tungstène"),
            ("MIG", "Soudure fil continu"),
        }
        actual = {
            (entry["answer"], entry.get("clue", ""))
            for entry in document["entries"]
            if entry.get("sourceId") == "motman-owner-review-20260715"
        }
        self.assertTrue(expected <= actual)
        canonical_answers = {
            entry["answer"] for entry in document["entries"]
            if entry.get("canonicalForGenerator")
            and entry.get("sourceId") == "motman-owner-review-20260715"
        }
        self.assertTrue(({
            "CPE", "TOM", "POP", "RAP", "TRAP", "JAZZ", "SAC", "CLAC", "MAP",
            "TPE", "CB", "PNG", "LOT", "TOT", "NIL",
            "BAC", "PAC", "TIG", "MIG",
        }) <= canonical_answers)
        self.assertNotIn("LIT", canonical_answers)

    def test_approved_two_letter_answers_are_explicit_and_usable(self) -> None:
        entries = generator.load_entries()
        approved = {
            entry["answer"] for entry in entries
            if entry.get("shortAnswerApproved") is True
        }
        sourced_short = {
            "CD", "CP", "EP", "GI", "HS", "IP", "JT", "KO", "MO", "OB",
            "PC", "PS", "QI", "RH", "RN", "TP", "VO", "WC", "ZI",
        }
        self.assertTrue({"CB", "TV", "BD", "UE", "CV"} | sourced_short <= approved)
        self.assertFalse({"DO", "RE", "MI", "FA", "SOL", "LA", "SI"} & approved)
        index = generator.build_index(
            entries,
            min_frequency=0,
            difficulty="normal",
            allow_dictionary_derived=False,
        )
        self.assertTrue(
            {"CB", "TV", "BD", "UE", "CV"} | sourced_short
            <= set(index[0][2])
        )

    def test_reviewed_images_survive_a_jeuxdemots_canonical_text_pair(self) -> None:
        entries = {entry["answer"]: entry for entry in generator.load_entries()}
        horse = entries["CHEVAL"]
        self.assertEqual("jeuxdemots-r_syn-sanitized", horse["sourceId"])
        self.assertEqual("/assets/clues/twemoji/cheval.svg", horse["image"]["asset"])
        self.assertGreaterEqual(
            sum(bool(entry.get("image")) for entry in entries.values()),
            145,
        )
        self.assertNotIn("ABETI", entries)
        self.assertNotIn("PIU", entries)


if __name__ == "__main__":
    unittest.main()
