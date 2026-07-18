from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from audit_crossword_sources import RIGHTS_CLEARED, request_template  # noqa: E402


class CrosswordSourceRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(
            (ROOT / "src/data/crossword.sources.json").read_text(encoding="utf-8")
        )
        cls.sources = {source["id"]: source for source in cls.registry["sources"]}

    def test_prototype_scrapes_are_not_marked_as_rights_cleared(self) -> None:
        for source_id in ("leparisien-rcijeux", "ouestfrance-via-ychalier"):
            source = self.sources[source_id]
            self.assertNotIn(source["publicationRights"], RIGHTS_CLEARED)

    def test_acquisition_candidates_are_never_active_automatically(self) -> None:
        candidates = [source for source in self.sources.values() if "priority" in source]
        self.assertGreaterEqual(len(candidates), 5)
        self.assertEqual(
            "fortissimots",
            min(candidates, key=lambda source: source["priority"])["id"],
        )
        self.assertTrue(all(not source["status"].startswith("active-") for source in candidates))
        self.assertTrue(all(source["publicationRights"] not in RIGHTS_CLEARED for source in candidates))

    def test_request_demands_machine_readable_9_by_10_content_and_rights(self) -> None:
        message = request_template()
        self.assertIn("9 colonnes × 10 lignes", message)
        self.assertIn("JSON, CSV ou XML", message)
        self.assertIn("droits", message.casefold())
        self.assertIn("aucune lettre ni suite de lettres orpheline", message.casefold())


if __name__ == "__main__":
    unittest.main()
