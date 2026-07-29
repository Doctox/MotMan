import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from find_semi_editorial_rectangle_bridge import (  # noqa: E402
    compatible_bridge_pairs,
    compatible_bridge_triples,
    compatible_bridges,
)
from word_rectangle_filler import RectangleEntry, build_prefix_trie  # noqa: E402


def entry(answer: str) -> RectangleEntry:
    return RectangleEntry(answer, answer, 1.0, 4.0)


class SemiEditorialBridgeTests(unittest.TestCase):
    def test_bridge_must_terminate_every_vertical_prefix(self) -> None:
        vertical = [
            entry("AAAAAAX"), entry("BBBBBBY"), entry("CCCCCCZ"),
            entry("DDDDDDQ"), entry("EEEEEEW"), entry("FFFFFFR"),
        ]
        trie = build_prefix_trie(vertical)
        nodes = []
        for prefix in ("AAAAAA", "BBBBBB", "CCCCCC", "DDDDDD", "EEEEEE", "FFFFFF"):
            node = trie
            for letter in prefix:
                node = node.children[letter]
            nodes.append(node)
        valid = entry("XYZQWR")
        invalid = entry("XYZQWA")
        matches = compatible_bridges(tuple(nodes), [invalid, valid])
        self.assertEqual([valid], [item[0] for item in matches])

    def test_two_bridge_rows_must_complete_each_column(self) -> None:
        vertical = [
            entry("AAAAAXY"), entry("BBBBBYZ"), entry("CCCCCZQ"),
            entry("DDDDDQR"), entry("EEEEEWS"), entry("FFFFFRT"),
        ]
        trie = build_prefix_trie(vertical)
        nodes = []
        for prefix in ("AAAAA", "BBBBB", "CCCCC", "DDDDD", "EEEEE", "FFFFF"):
            node = trie
            for letter in prefix:
                node = node.children[letter]
            nodes.append(node)
        first = entry("XYZQWR")
        second = entry("YZQRST")
        invalid = entry("YZQRSA")
        matches = compatible_bridge_pairs(tuple(nodes), [first], [invalid, second])
        self.assertEqual([(first, second)], [(a, b) for a, b, _ in matches])

    def test_three_bridge_rows_must_complete_each_column(self) -> None:
        vertical = [
            entry("AAAAXYZ"), entry("BBBBYZA"), entry("CCCCZAB"),
            entry("DDDDABC"), entry("EEEEBCD"), entry("FFFFCDE"),
        ]
        trie = build_prefix_trie(vertical)
        nodes = []
        for prefix in ("AAAA", "BBBB", "CCCC", "DDDD", "EEEE", "FFFF"):
            node = trie
            for letter in prefix:
                node = node.children[letter]
            nodes.append(node)
        first = entry("XYZABC")
        second = entry("YZABCD")
        third = entry("ZABCDE")
        invalid = entry("ZABCDF")
        matches = compatible_bridge_triples(
            tuple(nodes), [first], [second, invalid, third]
        )
        self.assertEqual(
            [(first, second, third)],
            [(a, b, c) for a, b, c, _ in matches],
        )


if __name__ == "__main__":
    unittest.main()
