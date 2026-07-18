from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from audit_definition_corpus import (  # noqa: E402
    definition_mentions_answer,
    frequency_tier,
)


class DefinitionCorpusAuditTests(unittest.TestCase):
    def test_frequency_tiers_are_stable(self) -> None:
        self.assertEqual("tres-courant", frequency_tier(15))
        self.assertEqual("courant", frequency_tier(3))
        self.assertEqual("moins-courant", frequency_tier(0.5))
        self.assertEqual("rare", frequency_tier(0.49))

    def test_direct_answer_mentions_are_flagged(self) -> None:
        self.assertTrue(definition_mentions_answer({
            "answer": "CHAT", "sourceDefinition": "Un chat domestique."
        }))
        self.assertFalse(definition_mentions_answer({
            "answer": "CHAT", "sourceDefinition": "Petit félin domestique."
        }))


if __name__ == "__main__":
    unittest.main()
