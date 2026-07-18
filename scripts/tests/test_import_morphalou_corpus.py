from __future__ import annotations

import csv
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from import_morphalou_corpus import build_document


class MorphalouImportTest(unittest.TestCase):
    def test_lemma_and_inflection_remain_structural_only(self) -> None:
        header = [
            "GRAPHIE", "ID", "CATÉGORIE", "SOUS CATÉGORIE", "LOCUTION",
            "GENRE", "AUTRES LEMMES LIÉS", "PHONÉTIQUE", "ORIGINES",
            "GRAPHIE", "ID", "NOMBRE", "MODE", "GENRE", "TEMPS",
            "PERSONNE", "PHONÉTIQUE", "ORIGINES",
        ]
        rows = [
            header,
            [
                "chat", "1", "Nom commun", "", "", "masculine", "", "",
                "morphalou2", "chat", "1", "singular", "-", "-", "-", "-",
                "", "morphalou2",
            ],
            [
                "", "", "", "", "", "", "", "", "", "chats", "2",
                "plural", "-", "-", "-", "-", "", "morphalou2",
            ],
        ]
        stream = io.StringIO()
        writer = csv.writer(stream, delimiter=";", lineterminator="\n")
        writer.writerows(rows)
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "morphalou.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    "Morphalou3.1_formatCSV/commonNoun_Morphalou3.1_CSV.csv",
                    stream.getvalue(),
                )
            document = build_document(archive_path)
        by_answer = {entry["answer"]: entry for entry in document["entries"]}
        self.assertEqual(set(by_answer), {"CHAT", "CHATS"})
        self.assertEqual(by_answer["CHAT"]["formType"], "lemma")
        self.assertEqual(by_answer["CHATS"]["formType"], "inflected")
        self.assertEqual(by_answer["CHATS"]["lemmaAnswer"], "CHAT")
        self.assertFalse(by_answer["CHAT"]["generatorEligible"])
        self.assertFalse(by_answer["CHATS"]["generatorEligible"])


if __name__ == "__main__":
    unittest.main()
