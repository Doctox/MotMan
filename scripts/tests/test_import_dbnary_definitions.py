from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from import_dbnary_definitions import (  # noqa: E402
    decode_turtle_string,
    definition_registers,
    has_blocked_register,
    iter_turtle_blocks,
    normalize_answer,
)


class DbnaryDefinitionImportTests(unittest.TestCase):
    def test_turtle_blocks_are_streamed_without_losing_the_last_block(self) -> None:
        blocks = list(iter_turtle_blocks(io.StringIO("a ;\n  b .\n\nc .\n")))
        self.assertEqual(["a ;\n  b .\n", "c .\n"], blocks)

    def test_turtle_literal_decoding_preserves_french(self) -> None:
        self.assertEqual("Café d’été", decode_turtle_string('"Café d’été"'))
        self.assertEqual("ILE", normalize_answer("île"))

    def test_problematic_registers_are_detected(self) -> None:
        registers = definition_registers("(Vieilli) (Argot) Ancien usage.")
        self.assertEqual(["Vieilli", "Argot"], registers)
        self.assertTrue(has_blocked_register(registers))
        self.assertFalse(has_blocked_register(["Botanique"]))


if __name__ == "__main__":
    unittest.main()
