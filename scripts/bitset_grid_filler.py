"""Fast deterministic crossword CSP using integer bitset domains."""
from __future__ import annotations

import time
from collections import Counter, defaultdict


LEVELS = ("easy", "normal", "hard")
_COMPILED_WORDLIST_CACHE: dict[tuple, tuple] = {}


def _bits(value: int):
    while value:
        least = value & -value
        yield least.bit_length() - 1
        value ^= least


def fill_bitset(
    slots,
    indexes,
    rng,
    target_mix: dict[str, int] | None,
    *,
    unavailable_answers: set[str] | None = None,
    answer_usage: dict[str, int] | None = None,
    max_grammar_answers: int = 1,
    grammar_answers: set[str] | None = None,
    max_seconds: float = 5.0,
    node_limit: int = 100_000,
    require_image: bool = True,
    minimum_images: int = 1,
    required_image_slots: set[int] | None = None,
    fixed_answers: dict[int, str] | None = None,
    allowed_answers_by_slot: dict[int, set[str]] | None = None,
    undesirable_answers: set[str] | None = None,
    max_undesirable_answers: int | None = None,
    prefer_constraint_support: bool = False,
    constraint_support_bucket_size: int = 1,
    branching_strategy: str = "slot",
    cell_branch_window: int = 15,
    quality_scores: dict[str, float] | None = None,
    solution_limit: int = 1,
    explore_randomly: bool = False,
    telemetry: dict | None = None,
) -> dict[int, str] | None:
    """Fill every declared slot with a real answer and exact crossing letters.

    ``solution_limit`` turns the usual first-feasible search into a bounded
    editorial search.  Complete fills are compared on active-catalog reuse,
    their weakest answer score, then their total answer score.  This mirrors
    constructor tools that keep several viable fills instead of accepting the
    first mathematical closure.
    """
    started = time.monotonic()
    deadline = started + max_seconds
    telemetry = telemetry if telemetry is not None else {}
    unavailable_answers = unavailable_answers or set()
    answer_usage = answer_usage or {}
    grammar_answers = grammar_answers or set()
    fixed_answers = fixed_answers or {}
    allowed_answers_by_slot = allowed_answers_by_slot or {}
    required_image_slots = required_image_slots or set()
    undesirable_answers = undesirable_answers or set()
    if solution_limit < 1:
        raise ValueError("solution_limit must be at least 1")
    if branching_strategy not in {"slot", "cell"}:
        raise ValueError(f"Unknown branching strategy: {branching_strategy}")
    by_length, _, frequency, concept_group, semantic_conflicts, word_difficulty, image_answers = indexes
    quality_scores = quality_scores or frequency
    variables = [index for index, slot in enumerate(slots) if slot.cells]

    cache_key = (
        id(by_length),
        id(word_difficulty),
        id(image_answers),
        frozenset(grammar_answers),
        frozenset(undesirable_answers),
    )
    compiled = _COMPILED_WORDLIST_CACHE.get(cache_key)
    index_cache_hit = compiled is not None and compiled[0] is by_length
    if index_cache_hit:
        (
            _source,
            words_by_length,
            word_index,
            masks,
            tier_masks,
            image_masks,
            grammar_masks,
            undesirable_masks,
        ) = compiled
    else:
        words_by_length = {length: list(words) for length, words in by_length.items()}
        word_index = {
            length: {word: index for index, word in enumerate(words)}
            for length, words in words_by_length.items()
        }
        masks = defaultdict(lambda: defaultdict(dict))
        tier_masks = defaultdict(dict)
        image_masks = {}
        grammar_masks = {}
        undesirable_masks = {}
        for length, words in words_by_length.items():
            for position in range(length):
                for letter_code in range(26):
                    masks[length][position][letter_code] = 0
            for index, word in enumerate(words):
                bit = 1 << index
                for position, letter in enumerate(word):
                    masks[length][position][ord(letter) - 65] |= bit
            tier_masks[length] = {
                level: sum(1 << index for index, word in enumerate(words)
                           if word_difficulty[word] == level)
                for level in LEVELS
            }
            image_masks[length] = sum(
                1 << index for index, word in enumerate(words)
                if word in image_answers
            )
            grammar_masks[length] = sum(
                1 << index for index, word in enumerate(words)
                if word in grammar_answers
            )
            undesirable_masks[length] = sum(
                1 << index for index, word in enumerate(words)
                if word in undesirable_answers
            )
        if len(_COMPILED_WORDLIST_CACHE) >= 4:
            _COMPILED_WORDLIST_CACHE.clear()
        _COMPILED_WORDLIST_CACHE[cache_key] = (
            by_length,
            words_by_length,
            word_index,
            masks,
            tier_masks,
            image_masks,
            grammar_masks,
            undesirable_masks,
        )

    domains = {}
    for variable in variables:
        length = len(slots[variable].cells)
        words = words_by_length.get(length, [])
        domain = (1 << len(words)) - 1
        for answer in unavailable_answers:
            index = word_index.get(length, {}).get(answer)
            if index is not None:
                domain &= ~(1 << index)
        fixed = fixed_answers.get(variable)
        if fixed is not None:
            fixed_index = word_index.get(length, {}).get(fixed)
            if fixed_index is None:
                telemetry.update(
                    reason="fixed_answer_missing", slot=variable,
                    answer=fixed, elapsedSeconds=0,
                )
                return None
            domain &= 1 << fixed_index
        allowed = allowed_answers_by_slot.get(variable)
        if allowed is not None:
            allowed_mask = 0
            for answer in allowed:
                allowed_index = word_index.get(length, {}).get(answer)
                if allowed_index is not None:
                    allowed_mask |= 1 << allowed_index
            domain &= allowed_mask
        if variable in required_image_slots:
            domain &= image_masks[length]
        if not domain:
            telemetry.update(
                reason=(
                    "required_image_slot_empty"
                    if variable in required_image_slots else "empty_domain"
                ),
                slot=variable,
                elapsedSeconds=0,
            )
            return None
        domains[variable] = domain

    cell_links = defaultdict(list)
    for variable in variables:
        for position, cell in enumerate(slots[variable].cells):
            cell_links[cell].append((variable, position))
    arcs = []
    neighbor_links = defaultdict(list)
    for links in cell_links.values():
        if len(links) == 2:
            left, right = links
            arcs.extend(((left[0], left[1], right[0], right[1]),
                         (right[0], right[1], left[0], left[1])))
            neighbor_links[left[0]].append((left[1], right[0], right[1]))
            neighbor_links[right[0]].append((right[1], left[0], left[1]))

    crossing_cells = []
    for cell, links in cell_links.items():
        if len(links) != 2:
            continue
        left, right = links
        crossing_cells.append((
            cell,
            left[0], left[1],
            right[0], right[1],
            len(slots[left[0]].cells) + len(slots[right[0]].cells),
        ))
    crossing_cells.sort(key=lambda item: (-item[5], item[0]))

    same_length_groups = defaultdict(list)
    for variable in variables:
        same_length_groups[len(slots[variable].cells)].append(variable)

    last_contradiction: dict = {}

    def propagate(current: dict[int, int]) -> bool:
        nonlocal timeout
        changed = True
        while changed:
            if time.monotonic() >= deadline:
                timeout = True
                return False
            changed = False
            # AllDifferent for answers sharing a length.
            for length, group in same_length_groups.items():
                singles = [current[var] for var in group if current[var].bit_count() == 1]
                if len(singles) != len(set(singles)):
                    last_contradiction.update(
                        kind="duplicate_singleton",
                        length=length,
                    )
                    return False
                used = 0
                for singleton in singles:
                    used |= singleton
                for variable in group:
                    domain = current[variable]
                    if domain.bit_count() == 1:
                        continue
                    revised = domain & ~used
                    if not revised:
                        last_contradiction.update(
                            kind="all_different_domain_wipeout",
                            slot=variable,
                            length=length,
                        )
                        return False
                    if revised != domain:
                        current[variable] = revised
                        changed = True

            for arc_index, (left, left_position, right, right_position) in enumerate(arcs):
                if arc_index % 16 == 0 and time.monotonic() >= deadline:
                    timeout = True
                    return False
                right_domain = current[right]
                right_length = len(slots[right].cells)
                supported_letters = [
                    code for code in range(26)
                    if right_domain & masks[right_length][right_position][code]
                ]
                left_length = len(slots[left].cells)
                allowed = 0
                for code in supported_letters:
                    allowed |= masks[left_length][left_position][code]
                revised = current[left] & allowed
                if not revised:
                    last_contradiction.update(
                        kind="crossing_domain_wipeout",
                        slot=left,
                        slotId=getattr(slots[left], "slot_id", str(left)),
                        position=left_position,
                        neighbor=right,
                        neighborSlotId=getattr(slots[right], "slot_id", str(right)),
                        neighborPosition=right_position,
                    )
                    return False
                if revised != current[left]:
                    current[left] = revised
                    changed = True
        return True

    def global_feasible(current: dict[int, int]) -> bool:
        if target_mix is not None:
            for level, target in target_mix.items():
                certain = 0
                possible = 0
                for variable, domain in current.items():
                    length = len(slots[variable].cells)
                    tier_domain = domain & tier_masks[length][level]
                    if tier_domain:
                        possible += 1
                    if tier_domain == domain:
                        certain += 1
                if not certain <= target <= possible:
                    return False
        certain_images = possible_images = 0
        certain_grammar = 0
        certain_undesirable = 0
        for variable, domain in current.items():
            length = len(slots[variable].cells)
            image_domain = domain & image_masks[length]
            if image_domain:
                possible_images += 1
            if image_domain == domain:
                certain_images += 1
            if domain & grammar_masks[length] == domain:
                certain_grammar += 1
            if domain & undesirable_masks[length] == domain:
                certain_undesirable += 1
        return ((not require_image or (possible_images >= minimum_images and certain_images <= 6))
                and certain_grammar <= max_grammar_answers
                and (
                    max_undesirable_answers is None
                    or certain_undesirable <= max_undesirable_answers
                ))

    nodes = 0
    timeout = False
    cell_branch_nodes = 0
    complete_solutions = 0
    best_domains: dict[int, int] | None = None
    best_quality: tuple | None = None

    def completed_quality(chosen: dict[int, str]) -> tuple:
        """Prefer fresh fills whose weakest entry is still editorially good."""
        usages = [int(answer_usage.get(word, 0)) for word in chosen.values()]
        scores = [float(quality_scores.get(word, frequency[word])) for word in chosen.values()]
        return (
            -sum(usage > 0 for usage in usages),
            -max(usages, default=0),
            -sum(usages),
            min(scores, default=0.0),
            -sum(score < 20 for score in scores),
            -sum(score < 30 for score in scores),
            sum(scores),
        )

    def search(current: dict[int, int]) -> dict[int, int] | None:
        nonlocal nodes, timeout, cell_branch_nodes, complete_solutions
        nonlocal best_domains, best_quality
        nodes += 1
        if nodes > node_limit or time.monotonic() >= deadline:
            timeout = True
            return None
        if not propagate(current) or not global_feasible(current):
            return None
        unresolved = [variable for variable in variables if current[variable].bit_count() > 1]
        if not unresolved:
            chosen = {
                variable: words_by_length[len(slots[variable].cells)][current[variable].bit_length() - 1]
                for variable in variables
            }
            mix = Counter(word_difficulty[word] for word in chosen.values())
            if target_mix is not None and any(mix[level] != target for level, target in target_mix.items()):
                return None
            if require_image and not minimum_images <= sum(
                    word in image_answers for word in chosen.values()) <= 6:
                return None
            if sum(word in grammar_answers for word in chosen.values()) > max_grammar_answers:
                return None
            if (
                max_undesirable_answers is not None
                and sum(word in undesirable_answers for word in chosen.values())
                > max_undesirable_answers
            ):
                return None
            concepts = [concept_group[word] for word in chosen.values()]
            if len(concepts) != len(set(concepts)):
                return None
            selected = set(chosen.values())
            if any(semantic_conflicts[word].intersection(selected) for word in selected):
                return None
            complete_solutions += 1
            quality = completed_quality(chosen)
            if best_quality is None or quality > best_quality:
                best_quality = quality
                best_domains = current.copy()
            # Preserve the historical fast path.  With a larger budget, keep
            # searching until the requested number of complete alternatives
            # has actually been compared.
            if solution_limit == 1 or complete_solutions >= solution_limit:
                return best_domains
            return None

        certain_images = 0
        if require_image:
            for item, domain in current.items():
                length = len(slots[item].cells)
                image_domain = domain & image_masks[length]
                if image_domain and image_domain == domain:
                    certain_images += 1
        images_still_needed = require_image and certain_images < minimum_images

        # Orca-style branching: propagation still works on slot domains, but
        # the speculative choice is one crossing letter.  A failed letter
        # eliminates every word carrying it at that position in one branch,
        # instead of rediscovering the same contradiction word by word.
        if branching_strategy == "cell" and not images_still_needed:
            active_crossings = []
            for crossing in crossing_cells:
                (_cell, left, left_position, right, right_position, length_sum) = crossing
                left_domain = current[left]
                right_domain = current[right]
                left_length = len(slots[left].cells)
                right_length = len(slots[right].cells)
                letter_work = []
                for code in range(26):
                    left_count = (
                        left_domain & masks[left_length][left_position][code]
                    ).bit_count()
                    if not left_count:
                        continue
                    right_count = (
                        right_domain & masks[right_length][right_position][code]
                    ).bit_count()
                    if right_count:
                        letter_work.append((code, left_count * right_count))
                if len(letter_work) > 1:
                    active_crossings.append((crossing, letter_work, sum(
                        work for _code, work in letter_work
                    )))
                    if len(active_crossings) >= max(1, cell_branch_window):
                        break
            if active_crossings:
                crossing, letter_work, _score = min(
                    active_crossings,
                    key=lambda item: (item[2], -item[0][5], item[0][0]),
                )
                (_cell, left, left_position, right, right_position, _length_sum) = crossing
                left_length = len(slots[left].cells)
                right_length = len(slots[right].cells)
                if explore_randomly:
                    # Batch construction already applies a lexical floor.
                    # Vary the crossing letter so repeated seeds explore
                    # genuinely different closures instead of returning the
                    # same locally optimal fill every time.
                    rng.shuffle(letter_work)
                else:
                    # Least-constraining letters first; ties remain deterministic.
                    letter_work.sort(key=lambda item: (-item[1], item[0]))
                cell_branch_nodes += 1
                for code, _work in letter_work:
                    next_domains = current.copy()
                    next_domains[left] &= masks[left_length][left_position][code]
                    next_domains[right] &= masks[right_length][right_position][code]
                    result = search(next_domains)
                    if result is not None:
                        return result
                    if timeout:
                        return None
                return None

        variable = min(unresolved, key=lambda item: (
            # Cardinality constraints are otherwise only checked at the end of
            # the search.  Branch on an image-capable slot while images are
            # still missing, so impossible three-image fills fail early and
            # valid ones do not waste the whole deadline on text-only paths.
            0 if (
                images_still_needed
                and current[item] & image_masks[len(slots[item].cells)]
            ) else 1,
            current[item].bit_count(),
            -sum(current[neighbor].bit_count() > 1
                 for _, neighbor, _ in neighbor_links[item]),
        ))
        length = len(slots[variable].cells)
        candidate_indices = list(_bits(current[variable]))
        rng.shuffle(candidate_indices)

        def support_score(index: int) -> int:
            word = words_by_length[length][index]
            score = 0
            for position, neighbor, neighbor_position in neighbor_links[variable]:
                neighbor_length = len(slots[neighbor].cells)
                letter_code = ord(word[position]) - 65
                support = (current[neighbor] & masks[neighbor_length][neighbor_position][letter_code]).bit_count()
                if support == 0:
                    return -1
                # Integer bit length is a cheap logarithmic least-constraining
                # value score; one huge domain cannot hide a nearly dead arc.
                score += support.bit_length()
            return score

        def candidate_priority(index: int) -> tuple:
            word = words_by_length[length][index]
            shared = (
                answer_usage.get(word, 0),
                int(word in undesirable_answers),
                0 if images_still_needed and word in image_answers else 1,
            )
            if explore_randomly:
                # candidate_indices was shuffled immediately above.  Keep
                # freshness and hard editorial classes as leading criteria,
                # then preserve that shuffled order inside each class.
                return shared
            if prefer_constraint_support:
                support = support_score(index)
                bucket_size = max(1, int(constraint_support_bucket_size))
                # Bucketing preserves the least-constraining-value heuristic
                # while letting editorial frequency decide between candidates
                # with nearly equivalent crossing support.
                return (
                    *shared,
                    -(support // bucket_size),
                    -quality_scores.get(word, frequency[word]),
                    -support,
                )
            return (
                *shared,
                -quality_scores.get(word, frequency[word]),
                -support_score(index),
            )

        candidate_indices.sort(key=candidate_priority)
        for index in candidate_indices:
            next_domains = current.copy()
            next_domains[variable] = 1 << index
            result = search(next_domains)
            if result is not None:
                return result
            if timeout:
                return None
        return None

    solved_domains = search(domains.copy()) or best_domains
    elapsed = round(time.monotonic() - started, 3)
    telemetry.update(
        solver="bitset-csp", nodes=nodes, elapsedSeconds=elapsed,
        branchingStrategy=branching_strategy,
        cellBranchNodes=cell_branch_nodes,
        solutionLimit=solution_limit,
        indexCacheHit=index_cache_hit,
        completeSolutions=complete_solutions,
        qualityOptimized=solution_limit > 1,
        randomExploration=explore_randomly,
        bestQuality=list(best_quality) if best_quality is not None else None,
        lastContradiction=last_contradiction or None,
        reason="solved" if solved_domains is not None else ("timeout" if timeout else "infeasible"),
    )
    if solved_domains is None:
        return None
    return {
        variable: words_by_length[len(slots[variable].cells)][solved_domains[variable].bit_length() - 1]
        for variable in variables
    }
