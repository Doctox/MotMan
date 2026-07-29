#!/usr/bin/env python3
"""Find a 7x6 word rectangle with one editorially supplied horizontal row.

The strict construction lexicon is deliberately conservative.  That is useful
for eleven or twelve support answers, but it can make an otherwise excellent
rectangle impossible merely because one current word (brand, pop reference or
common anglicism) is absent from the paper-style list.  This search keeps six
rows and all six columns inside the reviewed construction domain, then admits
exactly one six-letter bridge from a high-frequency/current reservoir.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace

from wordfreq import iter_wordlist, zipf_frequency

from build_compact_7x8_review import family_key
from search_compact_grid_pilot import normalized
from search_corrected_7x8_06_current import CURRENT, STRONG
from search_strict_frame_word_rectangle import load_domain
from word_rectangle_filler import RectangleEntry, build_prefix_trie


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output/quality/semi-editorial-7x8-pilot/bridge-search.json"

BRAND_OR_FRANCHISE = {
    "BARBIE", "DISNEY", "NETFLIX", "POKEMON", "SPOTIFY", "TWITCH", "YOUTUBE",
}


@dataclass(frozen=True)
class BridgePolicy:
    seconds: float = 60.0
    solution_limit: int = 20
    minimum_current: int = 2
    maximum_current: int = 4
    minimum_strong: int = 1
    maximum_unfamiliar: int = 2
    maximum_grammar: int = 1
    maximum_brands: int = 2
    bridge_minimum_zipf: float = 3.0


def soft_exclusions() -> set[str]:
    document = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    return {
        normalized(str(item.get("answer", "")))
        for item in document.get("registerPenaltyAnswers", [])
        if item.get("excludeFromNextPilot") is True
    }


def bridge_reservoir(minimum_zipf: float, excluded: set[str]) -> list[RectangleEntry]:
    words: dict[str, RectangleEntry] = {}
    for spelling in iter_wordlist("fr"):
        zipf = float(zipf_frequency(spelling, "fr"))
        if zipf < minimum_zipf:
            break
        if not spelling.isalpha():
            continue
        answer = normalized(spelling)
        if len(answer) != 6 or answer in excluded:
            continue
        words.setdefault(answer, RectangleEntry(
            answer=answer,
            family=family_key(answer),
            quality=20.0 + 8.0 * zipf,
            zipf=zipf,
            unfamiliar=zipf < 3.0,
            grammar=False,
            metadata={"spelling": spelling, "source": "wordfreq-bridge"},
        ))
    for answer in CURRENT:
        if len(answer) != 6 or answer in excluded:
            continue
        zipf = float(zipf_frequency(answer.lower(), "fr"))
        words[answer] = RectangleEntry(
            answer=answer,
            family=family_key(answer),
            quality=140.0 + (40.0 if answer in STRONG else 0.0),
            zipf=max(zipf, 3.0),
            unfamiliar=False,
            grammar=False,
            metadata={"spelling": answer.lower(), "source": "current-reviewed-bridge"},
        )
    return sorted(words.values(), key=lambda item: (-item.quality, item.answer))


def terminal_letters(node) -> set[str]:
    return {
        letter for letter, child in node.children.items()
        if child.terminal_index is not None
    }


def compatible_bridges(
    prefix_nodes, bridges: list[RectangleEntry]
) -> list[tuple[RectangleEntry, tuple]]:
    """Return bridge rows whose letters terminate every vertical prefix."""
    allowed = [terminal_letters(node) for node in prefix_nodes]
    if any(not letters for letters in allowed):
        return []
    result = []
    for entry in bridges:
        if all(letter in allowed[position] for position, letter in enumerate(entry.answer)):
            children = tuple(
                prefix_nodes[position].children[letter]
                for position, letter in enumerate(entry.answer)
            )
            result.append((entry, children))
    return result


def compatible_bridge_pairs(
    prefix_nodes,
    first_rows: list[RectangleEntry],
    second_rows: list[RectangleEntry],
) -> list[tuple[RectangleEntry, RectangleEntry, tuple]]:
    """Close five-letter column prefixes with two editorial rows."""
    masks: list[dict[str, int]] = [dict() for _ in range(6)]
    for index, entry in enumerate(second_rows):
        bit = 1 << index
        for position, letter in enumerate(entry.answer):
            masks[position][letter] = masks[position].get(letter, 0) | bit
    all_second = (1 << len(second_rows)) - 1
    result = []
    for first in first_rows:
        allowed_second = []
        first_children = []
        valid = True
        for position, first_letter in enumerate(first.answer):
            child = prefix_nodes[position].children.get(first_letter)
            if child is None:
                valid = False
                break
            letters = {
                letter for letter, grandchild in child.children.items()
                if grandchild.terminal_index is not None
            }
            if not letters:
                valid = False
                break
            first_children.append(child)
            allowed_second.append(letters)
        if not valid:
            continue
        mask = all_second
        for position, letters in enumerate(allowed_second):
            allowed_mask = 0
            for letter in letters:
                allowed_mask |= masks[position].get(letter, 0)
            mask &= allowed_mask
            if not mask:
                break
        while mask:
            bit = mask & -mask
            second = second_rows[bit.bit_length() - 1]
            mask ^= bit
            terminal_nodes = tuple(
                first_children[position].children[second.answer[position]]
                for position in range(6)
            )
            result.append((first, second, terminal_nodes))
    return result


def compatible_bridge_triples(
    prefix_nodes,
    first_rows: list[RectangleEntry],
    remaining_rows: list[RectangleEntry],
) -> list[tuple[RectangleEntry, RectangleEntry, RectangleEntry, tuple]]:
    """Close four-letter column prefixes with three editorial rows."""
    masks: list[dict[str, int]] = [dict() for _ in range(6)]
    for index, entry in enumerate(remaining_rows):
        bit = 1 << index
        for position, letter in enumerate(entry.answer):
            masks[position][letter] = masks[position].get(letter, 0) | bit
    all_rows = (1 << len(remaining_rows)) - 1
    result = []
    for first in first_rows:
        first_children = []
        second_letters = []
        valid = True
        for position, first_letter in enumerate(first.answer):
            child = prefix_nodes[position].children.get(first_letter)
            if child is None:
                valid = False
                break
            letters = {
                second for second, second_child in child.children.items()
                if any(grandchild.terminal_index is not None
                       for grandchild in second_child.children.values())
            }
            if not letters:
                valid = False
                break
            first_children.append(child)
            second_letters.append(letters)
        if not valid:
            continue
        second_mask = all_rows
        for position, letters in enumerate(second_letters):
            allowed = 0
            for letter in letters:
                allowed |= masks[position].get(letter, 0)
            second_mask &= allowed
            if not second_mask:
                break
        while second_mask:
            bit = second_mask & -second_mask
            second = remaining_rows[bit.bit_length() - 1]
            second_mask ^= bit
            second_children = []
            third_letters = []
            valid_second = True
            for position, second_letter in enumerate(second.answer):
                child = first_children[position].children.get(second_letter)
                if child is None:
                    valid_second = False
                    break
                letters = {
                    third for third, terminal in child.children.items()
                    if terminal.terminal_index is not None
                }
                if not letters:
                    valid_second = False
                    break
                second_children.append(child)
                third_letters.append(letters)
            if not valid_second:
                continue
            third_mask = all_rows
            for position, letters in enumerate(third_letters):
                allowed = 0
                for letter in letters:
                    allowed |= masks[position].get(letter, 0)
                third_mask &= allowed
                if not third_mask:
                    break
            while third_mask:
                bit = third_mask & -third_mask
                third = remaining_rows[bit.bit_length() - 1]
                third_mask ^= bit
                terminal_nodes = tuple(
                    second_children[position].children[third.answer[position]]
                    for position in range(6)
                )
                result.append((first, second, third, terminal_nodes))
    return result


def search(
    horizontal: list[RectangleEntry],
    vertical: list[RectangleEntry],
    bridges: list[RectangleEntry],
    *,
    policy: BridgePolicy,
    seed: int,
) -> dict:
    started = time.monotonic()
    deadline = started + policy.seconds
    rng = random.Random(seed)
    vertical_trie = build_prefix_trie(vertical)
    vertical_by_index = {index: entry for index, entry in enumerate(vertical)}
    first_bridge_rows = [entry for entry in bridges if entry.answer in CURRENT]

    position_masks: list[dict[str, int]] = [dict() for _ in range(6)]
    for index, entry in enumerate(horizontal):
        bit = 1 << index
        for position, letter in enumerate(entry.answer):
            position_masks[position][letter] = (
                position_masks[position].get(letter, 0) | bit
            )
    all_rows = (1 << len(horizontal)) - 1
    order = sorted(
        range(len(horizontal)),
        key=lambda index: (
            horizontal[index].answer in STRONG,
            horizontal[index].answer in CURRENT,
            horizontal[index].quality,
            rng.random(),
        ),
        reverse=True,
    )
    rank = {index: position for position, index in enumerate(order)}
    nodes = 0
    bridge_checks = 0
    bridge_states = 0
    anchor_ready_states = 0
    deepest = 0
    solutions = []
    seen = set()

    def dfs(chosen: tuple[int, ...], prefix_nodes: tuple, families: frozenset[str]) -> bool:
        nonlocal nodes, bridge_checks, bridge_states, anchor_ready_states, deepest
        nodes += 1
        deepest = max(deepest, len(chosen))
        if nodes % 512 == 0 and time.monotonic() >= deadline:
            return True
        if len(chosen) == 4:
            bridge_states += 1
            chosen_current = {
                horizontal[index].answer for index in chosen
                if horizontal[index].answer in CURRENT
            }
            chosen_strong = chosen_current & STRONG
            # One strong anchor already placed is enough to let the two bridge
            # rows come from the whole current/everyday reservoir. The final
            # grid still has to meet the full 2-to-4 current-answer quota.
            anchors_ready = bool(chosen_current and chosen_strong)
            if anchors_ready:
                anchor_ready_states += 1
            candidates = compatible_bridge_triples(
                prefix_nodes,
                bridges if anchors_ready else first_bridge_rows,
                bridges,
            )
            bridge_checks += len(candidates)
            chosen_answers = {horizontal[index].answer for index in chosen}
            for first_bridge, second_bridge, third_bridge, terminal_nodes in candidates:
                if (
                    first_bridge.answer in chosen_answers
                    or second_bridge.answer in chosen_answers
                    or third_bridge.answer in chosen_answers
                    or first_bridge.answer == second_bridge.answer
                    or first_bridge.answer == third_bridge.answer
                    or second_bridge.answer == third_bridge.answer
                    or first_bridge.family in families
                    or second_bridge.family in families
                    or third_bridge.family in families
                    or first_bridge.family == second_bridge.family
                    or first_bridge.family == third_bridge.family
                    or second_bridge.family == third_bridge.family
                ):
                    continue
                columns = tuple(
                    vertical_by_index[int(node.terminal_index)] for node in terminal_nodes
                )
                rows = (
                    tuple(horizontal[index] for index in chosen)
                    + (first_bridge, second_bridge, third_bridge)
                )
                combined = rows + columns
                answers = tuple(entry.answer for entry in combined)
                all_families = tuple(entry.family for entry in combined)
                if len(set(answers)) != len(answers) or len(set(all_families)) != len(all_families):
                    continue
                current = sorted({answer for answer in answers if answer in CURRENT})
                strong = sorted({answer for answer in answers if answer in STRONG})
                unfamiliar = sum(entry.unfamiliar for entry in combined)
                grammar = sum(entry.grammar for entry in combined)
                brands = sorted({answer for answer in answers if answer in BRAND_OR_FRANCHISE})
                if not (
                    policy.minimum_current <= len(current) <= policy.maximum_current
                    and len(strong) >= policy.minimum_strong
                    and unfamiliar <= policy.maximum_unfamiliar
                    and grammar <= policy.maximum_grammar
                    and len(brands) <= policy.maximum_brands
                ):
                    continue
                key = answers
                if key in seen:
                    continue
                seen.add(key)
                quality = (
                    len(current), len(strong), -unfamiliar, -grammar,
                    -sum(entry.active_uses > 0 for entry in combined),
                    min(entry.quality for entry in combined),
                    sum(entry.quality for entry in combined),
                )
                solutions.append({
                    "rows": [entry.answer for entry in rows],
                    "columns": [entry.answer for entry in columns],
                    "bridgeAnswers": [
                        first_bridge.answer, second_bridge.answer, third_bridge.answer
                    ],
                    "currentAnswers": current,
                    "strongAnswers": strong,
                    "brandAnswers": brands,
                    "quality": list(quality),
                    "entries": [
                        {"answer": entry.answer, "zipf": entry.zipf,
                         "family": entry.family, "activeUses": entry.active_uses,
                         "source": (entry.metadata or {}).get("source", "construction")}
                        for entry in combined
                    ],
                })
                if len(solutions) >= policy.solution_limit:
                    return True
            return False

        mask = all_rows
        for position, node in enumerate(prefix_nodes):
            allowed = 0
            for letter in node.children:
                allowed |= position_masks[position].get(letter, 0)
            mask &= allowed
            if not mask:
                return False
        indexes = []
        while mask:
            bit = mask & -mask
            indexes.append(bit.bit_length() - 1)
            mask ^= bit
        indexes.sort(key=rank.__getitem__)
        for index in indexes:
            entry = horizontal[index]
            if entry.family in families:
                continue
            next_nodes = tuple(
                prefix_nodes[position].children[entry.answer[position]]
                for position in range(6)
            )
            if dfs(chosen + (index,), next_nodes, families | {entry.family}):
                return True
        return False

    stopped = dfs(tuple(), (vertical_trie,) * 6, frozenset())
    elapsed = time.monotonic() - started
    solutions.sort(key=lambda item: tuple(item["quality"]), reverse=True)
    return {
        "status": "solved" if solutions else "cutoff" if stopped else "dead",
        "solutions": solutions,
        "telemetry": {
            "elapsedSeconds": round(elapsed, 3),
            "nodes": nodes,
            "deepestConstructionRows": deepest,
            "bridgeStates": bridge_states,
            "anchorReadyBridgeStates": anchor_ready_states,
            "bridgeChecks": bridge_checks,
            "candidateCount": len(solutions),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--solution-limit", type=int, default=20)
    parser.add_argument("--minimum-zipf", type=float, default=2.2)
    parser.add_argument("--minimum-constructor-score", type=float, default=5.0)
    parser.add_argument("--bridge-minimum-zipf", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=818500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy = BridgePolicy(
        seconds=args.seconds,
        solution_limit=args.solution_limit,
        bridge_minimum_zipf=args.bridge_minimum_zipf,
    )
    domain_args = SimpleNamespace(
        minimum_zipf=args.minimum_zipf,
        minimum_constructor_score=args.minimum_constructor_score,
        minimum_familiarity_zipf=3.0,
        reference_catalog=[ROOT / "src/data/grid.catalog.json"],
        pilot_safe_short_only=True,
    )
    horizontal, vertical, stats = load_domain(domain_args)
    excluded = soft_exclusions()
    horizontal = [entry for entry in horizontal if entry.answer not in excluded]
    vertical = [entry for entry in vertical if entry.answer not in excluded]
    bridges = bridge_reservoir(policy.bridge_minimum_zipf, excluded)
    result = search(horizontal, vertical, bridges, policy=policy, seed=args.seed)
    payload = {
        "version": 1,
        "kind": "motman-semi-editorial-7x8-one-row-bridge",
        "columns": 7,
        "rows": 8,
        "shapeId": "corrected-7x8-01",
        "catalogModified": False,
        "runtimeModified": False,
        "publicationEligible": False,
        "policy": asdict(policy),
        "softRegisterExclusions": sorted(excluded),
        "domainStats": {**stats, "bridgeCandidates": len(bridges)},
        **result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "output": str(args.output), "status": result["status"],
        **result["telemetry"],
    }, ensure_ascii=False, indent=2))
    return 0 if result["solutions"] else 2 if result["status"] == "dead" else 3


if __name__ == "__main__":
    raise SystemExit(main())
