"""Prefix-trie filler for full-interior word rectangles.

Unlike the generic crossword CSP, a rectangle has no internal clue cells: all
horizontal words are the same length and every vertical word is built one
prefix at a time.  This helper exploits that special structure while keeping
the editorial budgets (families, familiarity, grammar, images and no-goods)
explicit and testable.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RectangleEntry:
    answer: str
    family: str
    quality: float
    zipf: float
    unfamiliar: bool = False
    grammar: bool = False
    active_uses: int = 0
    has_image: bool = False
    metadata: dict | None = None


class PrefixNode:
    __slots__ = (
        "children",
        "terminal_index",
        "min_unfamiliar",
        "min_grammar",
        "max_images",
        "families",
    )

    def __init__(self) -> None:
        self.children: dict[str, PrefixNode] = {}
        self.terminal_index: int | None = None
        self.min_unfamiliar = 1_000_000
        self.min_grammar = 1_000_000
        self.max_images = 0
        self.families: frozenset[str] = frozenset()


def build_prefix_trie(entries: list[RectangleEntry]) -> PrefixNode:
    root = PrefixNode()
    for index, entry in enumerate(entries):
        node = root
        for letter in entry.answer:
            node = node.children.setdefault(letter, PrefixNode())
        node.terminal_index = index

    def finalize(node: PrefixNode) -> tuple[int, int, int, frozenset[str]]:
        unfamiliar = []
        grammar = []
        images = []
        families: set[str] = set()
        if node.terminal_index is not None:
            entry = entries[node.terminal_index]
            unfamiliar.append(int(entry.unfamiliar))
            grammar.append(int(entry.grammar))
            images.append(int(entry.has_image))
            families.add(entry.family)
        for child in node.children.values():
            child_unfamiliar, child_grammar, child_images, child_families = finalize(child)
            unfamiliar.append(child_unfamiliar)
            grammar.append(child_grammar)
            images.append(child_images)
            families.update(child_families)
        node.min_unfamiliar = min(unfamiliar, default=1_000_000)
        node.min_grammar = min(grammar, default=1_000_000)
        node.max_images = max(images, default=0)
        node.families = frozenset(families)
        return node.min_unfamiliar, node.min_grammar, node.max_images, node.families

    finalize(root)
    return root


def _reference_distance(
    slot_answers: tuple[str, ...], reference_solutions: list[dict[int, str]]
) -> int | None:
    compatible = [
        reference
        for reference in reference_solutions
        if set(reference) == set(range(len(slot_answers)))
    ]
    if not compatible:
        return None
    return min(
        sum(slot_answers[index] != reference[index] for index in range(len(slot_answers)))
        for reference in compatible
    )


def fill_word_rectangle(
    horizontal_entries: list[RectangleEntry],
    vertical_entries: list[RectangleEntry],
    *,
    row_count: int,
    column_count: int,
    seed: int,
    max_seconds: float,
    node_limit: int = 100_000_000,
    solution_limit: int = 8,
    max_unfamiliar_answers: int | None = None,
    max_grammar_answers: int = 1,
    minimum_images: int = 0,
    reference_solutions: list[dict[int, str]] | None = None,
    minimum_solution_distance: int = 1,
    orientation: str = "auto",
    explore_randomly: bool = False,
    completed_root_branches: Iterable[str] | None = None,
    initial_solutions: list[dict] | None = None,
) -> dict:
    """Return complete rectangles plus a conservative root-branch checkpoint.

    Only roots whose entire subtree returned normally are added to the
    checkpoint.  A timeout, node cutoff or solution-limit exit never marks its
    current root, so resuming cannot silently skip an unproved partial state.
    """

    if orientation not in {"auto", "row-first", "column-first"}:
        raise ValueError(f"Orientation inconnue : {orientation}")
    if solution_limit < 1:
        raise ValueError("solution_limit doit etre positif")
    if any(len(entry.answer) != column_count for entry in horizontal_entries):
        raise ValueError("Longueur horizontale incompatible avec le rectangle")
    if any(len(entry.answer) != row_count for entry in vertical_entries):
        raise ValueError("Longueur verticale incompatible avec le rectangle")

    reference_solutions = reference_solutions or []
    # On 7x6 French domains, row-first reaches roughly 20% more prefix nodes
    # per second and fails earlier on impossible six-column prefix tuples.  The
    # choice is fixed rather than data-dependent so a cache key stays fully
    # reproducible across machines.
    chosen_orientation = "row-first" if orientation == "auto" else orientation
    if chosen_orientation == "row-first":
        primary_entries = horizontal_entries
        secondary_entries = vertical_entries
        primary_count = row_count
        secondary_count = column_count
    else:
        primary_entries = vertical_entries
        secondary_entries = horizontal_entries
        primary_count = column_count
        secondary_count = row_count

    trie = build_prefix_trie(secondary_entries)
    position_masks: list[dict[str, int]] = [dict() for _ in range(secondary_count)]
    for index, entry in enumerate(primary_entries):
        bit = 1 << index
        for position, letter in enumerate(entry.answer):
            position_masks[position][letter] = (
                position_masks[position].get(letter, 0) | bit
            )
    all_primary = (1 << len(primary_entries)) - 1

    rng = random.Random(seed)
    jitter = [rng.random() if explore_randomly else 0.0 for _ in primary_entries]
    rank = {
        index: position
        for position, index in enumerate(sorted(
            range(len(primary_entries)),
            key=lambda index: (
                primary_entries[index].quality,
                primary_entries[index].has_image,
                primary_entries[index].zipf,
                jitter[index],
                primary_entries[index].answer,
            ),
            reverse=True,
        ))
    }

    started = time.monotonic()
    deadline = started + max_seconds
    nodes = 0
    prefix_wipeouts = 0
    family_prunes = 0
    budget_prunes = 0
    leaf_candidates = 0
    diversity_rejected: dict[int, int] = {}
    duplicate_solutions = 0
    timed_out = False
    node_limited = False
    solutions: list[dict] = [dict(solution) for solution in (initial_solutions or [])]
    solution_keys = {
        tuple(
            str(solution.get("slotAnswers", {}).get(str(index), ""))
            for index in range(primary_count + secondary_count)
        )
        for solution in solutions
    }
    supplied_completed_roots = set(completed_root_branches or ())
    valid_root_keys = {entry.answer for entry in primary_entries}
    completed_roots = supplied_completed_roots & valid_root_keys
    completed_roots_this_run: set[str] = set()
    skipped_root_branches = 0
    root_branch_count = 0

    def should_stop() -> bool:
        nonlocal timed_out, node_limited
        if nodes >= node_limit:
            node_limited = True
            return True
        if time.monotonic() >= deadline:
            timed_out = True
            return True
        return False

    def dfs(
        chosen: tuple[int, ...],
        prefix_nodes: tuple[PrefixNode, ...],
        used_families: frozenset[str],
        unfamiliar_count: int,
        grammar_count: int,
        image_count: int,
    ) -> bool:
        nonlocal nodes, prefix_wipeouts, family_prunes, budget_prunes
        nonlocal leaf_candidates, duplicate_solutions, skipped_root_branches
        nonlocal root_branch_count, node_limited
        nodes += 1
        if nodes >= node_limit:
            node_limited = True
            return True
        if nodes % 512 == 0 and should_stop():
            return True

        if len(chosen) == primary_count:
            leaf_candidates += 1
            secondary_indexes = [node.terminal_index for node in prefix_nodes]
            if any(index is None for index in secondary_indexes):
                prefix_wipeouts += 1
                return False
            secondary = [secondary_entries[int(index)] for index in secondary_indexes]
            combined = [primary_entries[index] for index in chosen] + secondary
            families = [entry.family for entry in combined]
            if len(families) != len(set(families)):
                family_prunes += 1
                return False
            total_unfamiliar = sum(entry.unfamiliar for entry in combined)
            total_grammar = sum(entry.grammar for entry in combined)
            total_images = sum(entry.has_image for entry in combined)
            if (
                max_unfamiliar_answers is not None
                and total_unfamiliar > max_unfamiliar_answers
            ) or total_grammar > max_grammar_answers or total_images < minimum_images:
                budget_prunes += 1
                return False

            if chosen_orientation == "row-first":
                rows = tuple(primary_entries[index].answer for index in chosen)
                columns = tuple(entry.answer for entry in secondary)
            else:
                columns = tuple(primary_entries[index].answer for index in chosen)
                rows = tuple(entry.answer for entry in secondary)
            slot_answers = columns + rows
            distance = _reference_distance(slot_answers, reference_solutions)
            if distance is not None and distance < minimum_solution_distance:
                diversity_rejected[distance] = diversity_rejected.get(distance, 0) + 1
                return False

            solution_key = tuple(slot_answers)
            if solution_key in solution_keys:
                duplicate_solutions += 1
                return False

            active_repeats = sum(entry.active_uses > 0 for entry in combined)
            quality = (
                -total_unfamiliar,
                -total_grammar,
                -active_repeats,
                min(total_images, 6),
                min(entry.quality for entry in combined),
                sum(entry.quality for entry in combined),
            )
            solution = {
                "rows": list(rows),
                "columns": list(columns),
                "slotAnswers": {
                    str(index): answer for index, answer in enumerate(slot_answers)
                },
                "quality": list(quality),
                "metrics": {
                    "unfamiliarAnswers": total_unfamiliar,
                    "grammarAnswers": total_grammar,
                    "activeRepeatAnswers": active_repeats,
                    "imagePotentialAnswers": total_images,
                    "referenceDistance": distance,
                },
            }
            solutions.append(solution)
            solution_keys.add(solution_key)
            return len(solutions) >= solution_limit

        # Cheap lower/upper bounds over every possible secondary completion.
        minimum_secondary_unfamiliar = sum(node.min_unfamiliar for node in prefix_nodes)
        minimum_secondary_grammar = sum(node.min_grammar for node in prefix_nodes)
        maximum_secondary_images = sum(node.max_images for node in prefix_nodes)
        if (
            max_unfamiliar_answers is not None
            and unfamiliar_count + minimum_secondary_unfamiliar > max_unfamiliar_answers
        ) or grammar_count + minimum_secondary_grammar > max_grammar_answers:
            budget_prunes += 1
            return False
        if image_count + maximum_secondary_images < minimum_images:
            budget_prunes += 1
            return False
        if any(node.families and node.families.issubset(used_families) for node in prefix_nodes):
            family_prunes += 1
            return False

        mask = all_primary
        for position, node in enumerate(prefix_nodes):
            allowed = 0
            for letter in node.children:
                allowed |= position_masks[position].get(letter, 0)
            mask &= allowed
            if not mask:
                prefix_wipeouts += 1
                return False

        candidate_indexes = []
        while mask:
            bit = mask & -mask
            candidate_indexes.append(bit.bit_length() - 1)
            mask ^= bit
        candidate_indexes.sort(key=rank.__getitem__)
        is_root = not chosen
        if is_root:
            root_branch_count = len(candidate_indexes)
        for index in candidate_indexes:
            entry = primary_entries[index]
            root_key = entry.answer if is_root else None
            if is_root and root_key in completed_roots:
                skipped_root_branches += 1
                continue
            if is_root and should_stop():
                return True
            if entry.family in used_families:
                family_prunes += 1
                if is_root:
                    completed_roots.add(str(root_key))
                    completed_roots_this_run.add(str(root_key))
                continue
            next_unfamiliar = unfamiliar_count + int(entry.unfamiliar)
            next_grammar = grammar_count + int(entry.grammar)
            if (
                max_unfamiliar_answers is not None
                and next_unfamiliar > max_unfamiliar_answers
            ) or next_grammar > max_grammar_answers:
                budget_prunes += 1
                if is_root:
                    completed_roots.add(str(root_key))
                    completed_roots_this_run.add(str(root_key))
                continue
            next_nodes = tuple(
                prefix_nodes[position].children[entry.answer[position]]
                for position in range(secondary_count)
            )
            interrupted = dfs(
                chosen + (index,),
                next_nodes,
                used_families | {entry.family},
                next_unfamiliar,
                next_grammar,
                image_count + int(entry.has_image),
            )
            if interrupted:
                return True
            if is_root:
                completed_roots.add(str(root_key))
                completed_roots_this_run.add(str(root_key))
        return False

    if len(solutions) < solution_limit:
        dfs(tuple(), (trie,) * secondary_count, frozenset(), 0, 0, 0)
    elapsed = time.monotonic() - started
    solutions.sort(key=lambda item: tuple(item["quality"]), reverse=True)
    reason = (
        "solution_limit" if len(solutions) >= solution_limit
        else "timeout_with_solutions" if timed_out and solutions
        else "timeout" if timed_out
        else "node_limit_with_solutions" if node_limited and solutions
        else "node_limit" if node_limited
        else "exhausted_with_solutions" if solutions
        else "infeasible"
    )
    return {
        "complete": bool(solutions),
        "solutions": solutions,
        "telemetry": {
            "solver": "prefix-trie-word-rectangle-v3",
            "orientation": chosen_orientation,
            "nodes": nodes,
            "elapsedSeconds": round(elapsed, 3),
            "nodesPerSecond": round(nodes / max(elapsed, 0.001), 1),
            "prefixWipeouts": prefix_wipeouts,
            "familyPrunes": family_prunes,
            "budgetPrunes": budget_prunes,
            "leafCandidates": leaf_candidates,
            "completeSolutions": len(solutions),
            "resumedProvenSolutions": len(initial_solutions or []),
            "resumedDuplicateSolutions": duplicate_solutions,
            "solutionLimit": solution_limit,
            "rootBranches": root_branch_count,
            "completedRootBranches": len(completed_roots),
            "completedRootBranchesThisRun": len(completed_roots_this_run),
            "skippedRootBranches": skipped_root_branches,
            "diversityRejectedSolutions": sum(diversity_rejected.values()),
            "diversityRejectedByDistance": {
                str(distance): count for distance, count in sorted(diversity_rejected.items())
            },
            "reason": reason,
        },
        "checkpoint": {
            "completedRootBranches": sorted(completed_roots),
            "provenSolutions": solutions,
        },
    }
