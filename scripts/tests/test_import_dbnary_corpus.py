from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from import_dbnary_corpus import parse_entries  # noqa: E402


class DbnaryImportTests(unittest.TestCase):
    def test_extracts_only_direct_single_word_synonyms(self) -> None:
        sample = '''fra:chat__nom__1 rdf:type ontolex:Word;
 rdfs:label "chat"@fr;
 dbnary:synonym fra:matou , <http://kaiko.getalp.org/dbnary/fra/chat_domestique>;
 lexinfo:partOfSpeech lexinfo:noun .

fra:Paris__nom_propre__1 rdf:type ontolex:Word;
 rdfs:label "Paris"@fr;
 dbnary:synonym fra:Paname;
 lexinfo:partOfSpeech lexinfo:properNoun .
'''
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.ttl.bz2"
            import bz2
            source.write_bytes(bz2.compress(sample.encode("utf-8")))
            entries = list(parse_entries(source))
        self.assertEqual([("CHAT", "Matou")], [(item["answer"], item["clue"]) for item in entries])


if __name__ == "__main__":
    unittest.main()
