#!/usr/bin/env python3
"""Generate many definition-free 9x10 fills, then shortlist by lexical quality."""
from __future__ import annotations

import argparse
import gzip
import itertools
import json
import random
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import craft_flexible_common_grid as craft  # noqa: E402
from bitset_grid_filler import fill_bitset  # noqa: E402


DEFAULT_WORDLIST = ROOT / "src/data/fill.wordlist.large.json.gz"
DEFAULT_SHAPE = ROOT / "output/quality/professional-large-three-pivots-shape.json"
DEFAULT_CENTRAL_CORPUS = ROOT / "src/data/crossword.central.json.gz"
OWNER_APPROVED_SHORT = {
    "BAC", "CB", "CDI", "CLAC", "CPE", "HLM", "LIT", "LOT", "MAP",
    "MIG", "NIL", "PAC", "PNG", "POP", "RAP", "SAC", "TIG", "TOM",
    "TOT", "TPE",
}


def normalized_answer(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.upper())
    return "".join(character for character in folded if "A" <= character <= "Z")


def is_editorially_confirmed(answer: str, entry: dict) -> bool:
    """Require meaningful French usage, not one accidental corpus sighting."""
    if entry.get("formType") == "curated" or answer in OWNER_APPROVED_SHORT:
        return True
    source_frequency = float(entry.get("sourceFrequency", 0.0))
    school_frequency = float(entry.get("schoolFrequency", 0.0))
    threshold = 2.0 if len(answer) == 3 else (1.0 if len(answer) == 4 else 0.5)
    return source_frequency >= threshold or school_frequency >= 100


def candidate_quality(answers: list[str], metadata: dict[str, dict], usage) -> dict:
    items = [metadata[answer] for answer in answers]
    scores = [float(item["constructorScore"]) for item in items]
    return {
        "minimumScore": round(min(scores), 2),
        "averageScore": round(sum(scores) / len(scores), 2),
        "reserveAnswers": sum(score < 30 for score in scores),
        "zeroScoreAnswers": sum(score <= 0 for score in scores),
        "unattestedInflections": sum(
            item.get("formType") == "inflected"
            and not item.get("attestedCommonForm", False)
            for item in items
        ),
        "unconfirmedAnswers": sum(
            not item.get("editoriallyConfirmed", False) for item in items
        ),
        "activeCatalogAnswers": sum(bool(usage.get(answer, 0)) for answer in answers),
        "twoLetterAnswers": sum(len(answer) == 2 for answer in answers),
        "threeLetterAnswers": sum(len(answer) == 3 for answer in answers),
        "longAnswers": sum(len(answer) >= 6 for answer in answers),
    }


def shortlist_key(candidate: dict) -> tuple:
    quality = candidate["quality"]
    return (
        -quality["unattestedInflections"],
        -quality.get("unconfirmedAnswers", 0),
        -quality["zeroScoreAnswers"],
        -quality["reserveAnswers"],
        -quality["activeCatalogAnswers"],
        quality["minimumScore"],
        quality["averageScore"],
        quality["longAnswers"],
        -quality.get("twoLetterAnswers", 0),
        -quality["threeLetterAnswers"],
    )


def select_diverse_shortlist(candidates: list[dict], limit: int) -> list[dict]:
    """Choose the group whose combined vocabulary has the least repetition."""
    if not candidates or limit <= 0:
        return []

    def answer_set(candidate: dict) -> set[str]:
        return {item["answer"] for item in candidate["answers"]}

    def lemma_set(candidate: dict) -> set[str]:
        return {
            item.get("lemma", item["answer"]) for item in candidate["answers"]
        }

    def build_from(first: dict) -> list[dict]:
        remaining = [candidate for candidate in candidates if candidate is not first]
        selected = [first]
        lemma_counts = Counter(lemma_set(first))
        answer_counts = Counter(answer_set(first))
        shape_usage = Counter({first.get("sourceShapeId", "unknown"): 1})
        while remaining and len(selected) < limit:
            def diversity_key(candidate: dict) -> tuple:
                answers = answer_set(candidate)
                lemmas = lemma_set(candidate)
                repeated_lemma_excess = sum(lemma_counts[lemma] for lemma in lemmas)
                repeated_answer_excess = sum(
                    answer_counts[answer] for answer in answers
                )
                shape_id = candidate.get("sourceShapeId", "unknown")
                return (
                    -repeated_lemma_excess,
                    -repeated_answer_excess,
                    -shape_usage[shape_id],
                    *shortlist_key(candidate),
                )

            chosen = max(remaining, key=diversity_key)
            remaining.remove(chosen)
            selected.append(chosen)
            lemma_counts.update(lemma_set(chosen))
            answer_counts.update(answer_set(chosen))
            shape_usage[chosen.get("sourceShapeId", "unknown")] += 1
        return selected

    def group_key(group: list[dict]) -> tuple:
        lemma_counts = Counter(
            lemma for candidate in group for lemma in lemma_set(candidate)
        )
        answer_counts = Counter(
            answer for candidate in group for answer in answer_set(candidate)
        )
        lemma_excess = sum(count - 1 for count in lemma_counts.values() if count > 1)
        answer_excess = sum(count - 1 for count in answer_counts.values() if count > 1)
        return (
            -lemma_excess,
            -max(lemma_counts.values(), default=0),
            -answer_excess,
            len({candidate.get("sourceShapeId", "unknown") for candidate in group}),
            sum(candidate["quality"]["minimumScore"] for candidate in group),
            sum(candidate["quality"]["averageScore"] for candidate in group),
        )

    # Every raw fill gets a chance to be the first choice.  This bounded
    # multi-start avoids the common greedy trap where one attractive grid
    # forces dozens of repeats into the remaining nine.
    best = max((build_from(first) for first in candidates), key=group_key)
    selected_lemmas: set[str] = set()
    selected_answers: set[str] = set()
    shape_usage = Counter()
    for candidate in best:
        answers = answer_set(candidate)
        lemmas = lemma_set(candidate)
        candidate["diversity"] = {
            "reusedAnswersWithEarlierShortlist": len(answers & selected_answers),
            "reusedLemmasWithEarlierShortlist": len(lemmas & selected_lemmas),
            "earlierUsesOfShape": shape_usage[
                candidate.get("sourceShapeId", "unknown")
            ],
        }
        selected_answers.update(answers)
        selected_lemmas.update(lemmas)
        shape_usage[candidate.get("sourceShapeId", "unknown")] += 1
    return best


def safe_shape_pool() -> list[tuple[set, list, list, dict]]:
    """Enumerate compact central-pivot masks with no 1- or 2-letter run."""
    pivot_cells = [
        (row, column)
        for row in (4, 5, 6)
        for column in (4, 5, 8)
    ]
    pool = []
    for count in (1, 2, 3):
        for pivots in itertools.combinations(pivot_cells, count):
            clues = craft.FRAME | set(pivots)
            raw_slots = craft.direct_slots(clues)
            lengths = [slot["length"] for slot in raw_slots]
            if (
                not lengths
                or min(lengths) < 3
                or sum(length >= 5 for length in lengths) < 5
                or max(lengths) < 7
            ):
                continue
            audit = craft.validate_geometry(
                "large-lexical-pivots-" + "-".join(
                    f"{row}{column}" for row, column in pivots
                ),
                clues,
                raw_slots,
            )
            if not audit.get("valid"):
                continue
            slots = [
                craft.Slot(
                    index=index,
                    slot_id=item["slotId"],
                    direction=item["direction"],
                    clue_cell=tuple(item["clueCell"]),
                    cells=tuple(tuple(cell) for cell in item["cells"]),
                )
                for index, item in enumerate(raw_slots)
            ]
            pool.append((clues, raw_slots, slots, audit))
    return pool


def sampled_shape_pool(
    rng: random.Random,
    maximum_two_letter: int,
    target: int = 80,
) -> list[tuple[set, list, list, dict]]:
    """Build strict-frame masks; only the mathematically free zone is reused."""
    document = json.loads(
        (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
    )
    bases = []
    fingerprints = set()
    for grid in document.get("grids", []):
        # With every top/left cell acting as a clue, an interior clue in rows
        # 1-2 or columns 1-2 would cut a border answer below length two.  The
        # remaining zone is genuinely free; old answers and clues are ignored.
        original = {tuple(cell) for cell in grid.get("clueCells", [])}
        clues = craft.FRAME | {
            cell for cell in original if cell[0] >= 3 and cell[1] >= 3
        }
        fingerprint = tuple(sorted(clues))
        if fingerprint in fingerprints:
            continue
        raw_slots = craft.direct_slots(clues)
        lengths = [slot["length"] for slot in raw_slots]
        if (
            not lengths
            or min(lengths) < 2
            or lengths.count(2) > maximum_two_letter
        ):
            continue
        shape_id = f"strict-frame-base-{len(bases) + 1:03d}"
        audit = craft.validate_geometry(shape_id, clues, raw_slots)
        if not audit.get("valid"):
            continue
        fingerprints.add(fingerprint)
        bases.append(clues)

    # Insert one additional definition everywhere it remains topologically
    # legal.  This deliberately breaks the large interior rectangles while
    # preserving the strict frame and the two-letter quota.
    free_zone = {
        (row, column)
        for row in range(3, craft.ROWS)
        for column in range(3, craft.COLUMNS)
    }
    variants = []
    variant_fingerprints = set()
    for base in bases:
        for cell in sorted(free_zone - base):
            clues = set(base) | {cell}
            fingerprint = tuple(sorted(clues))
            if fingerprint in variant_fingerprints:
                continue
            raw_slots = craft.direct_slots(clues)
            lengths = [slot["length"] for slot in raw_slots]
            if (
                not lengths
                or min(lengths) < 2
                or lengths.count(2) > maximum_two_letter
            ):
                continue
            shape_id = f"strict-frame-insert-{len(variants) + 1:03d}"
            audit = craft.validate_geometry(shape_id, clues, raw_slots)
            if not audit.get("valid"):
                continue
            audit = dict(audit)
            audit["sourceShapeId"] = shape_id
            slots = [
                craft.Slot(
                    index=index,
                    slot_id=item["slotId"],
                    direction=item["direction"],
                    clue_cell=tuple(item["clueCell"]),
                    cells=tuple(tuple(path_cell) for path_cell in item["cells"]),
                )
                for index, item in enumerate(raw_slots)
            ]
            variant_fingerprints.add(fingerprint)
            variants.append((clues, raw_slots, slots, audit))
    rng.shuffle(variants)
    frontier = variants[:120]
    deepest = list(frontier)
    for depth in (2, 3):
        next_variants = []
        next_fingerprints = set()
        for base_clues, _base_raw, _base_slots, _base_audit in frontier:
            for cell in sorted(free_zone - base_clues):
                clues = set(base_clues) | {cell}
                fingerprint = tuple(sorted(clues))
                if fingerprint in next_fingerprints:
                    continue
                raw_slots = craft.direct_slots(clues)
                lengths = [slot["length"] for slot in raw_slots]
                if (
                    not lengths
                    or min(lengths) < 2
                    or lengths.count(2) > maximum_two_letter
                ):
                    continue
                shape_id = (
                    f"strict-frame-insert{depth}-{len(next_variants) + 1:03d}"
                )
                audit = craft.validate_geometry(shape_id, clues, raw_slots)
                if not audit.get("valid"):
                    continue
                audit = dict(audit)
                audit["sourceShapeId"] = shape_id
                slots = [
                    craft.Slot(
                        index=index,
                        slot_id=item["slotId"],
                        direction=item["direction"],
                        clue_cell=tuple(item["clueCell"]),
                        cells=tuple(
                            tuple(path_cell) for path_cell in item["cells"]
                        ),
                    )
                    for index, item in enumerate(raw_slots)
                ]
                next_fingerprints.add(fingerprint)
                next_variants.append((clues, raw_slots, slots, audit))
        if not next_variants:
            break
        rng.shuffle(next_variants)
        frontier = next_variants[:120]
        deepest = list(frontier)
    pool = deepest[:target]
    rng.shuffle(pool)
    return pool


def catalog_shape_pool(
    catalog_path: Path,
    maximum_two_letter: int,
) -> list[tuple[set, list, list, dict]]:
    """Reuse only the geometry of active grids; discard every old answer/clue."""
    document = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
    pool = []
    fingerprints = set()
    for grid in document.get("grids", []):
        clues = {tuple(cell) for cell in grid.get("clueCells", [])}
        fingerprint = tuple(sorted(clues))
        if not clues or fingerprint in fingerprints:
            continue
        raw_slots = craft.direct_slots(clues)
        lengths = [slot["length"] for slot in raw_slots]
        if (
            not lengths
            or min(lengths) < 2
            or lengths.count(2) > maximum_two_letter
        ):
            continue
        audit = craft.validate_geometry(
            str(grid.get("id", f"catalog-shape-{len(pool) + 1:03d}")),
            clues,
            raw_slots,
        )
        if not audit.get("valid"):
            continue
        audit = dict(audit)
        audit["sourceShapeId"] = str(grid.get("id", "catalog-shape"))
        slots = [
            craft.Slot(
                index=index,
                slot_id=item["slotId"],
                direction=item["direction"],
                clue_cell=tuple(item["clueCell"]),
                cells=tuple(tuple(cell) for cell in item["cells"]),
            )
            for index, item in enumerate(raw_slots)
        ]
        fingerprints.add(fingerprint)
        pool.append((clues, raw_slots, slots, audit))
    return pool


def sample_strict_frame_anchors(
    slots: list,
    words8_by_prefix: dict[str, list[str]],
    common9: list[str],
    rng: random.Random,
) -> dict[int, str]:
    """Seed the unavoidable 8×9 corner rectangle with common answers."""
    index_by_launch = {
        (slot.direction, slot.clue_cell, len(slot.cells)): slot.index
        for slot in slots
    }
    required = {
        "across1": ("across", (1, 0), 8),
        "across2": ("across", (2, 0), 8),
        "down1": ("down", (0, 1), 9),
        "down2": ("down", (0, 2), 9),
    }
    if any(key not in index_by_launch for key in required.values()):
        return {}
    for _attempt in range(300):
        down1 = rng.choice(common9)
        down2 = rng.choice(common9)
        if down1 == down2:
            continue
        prefix1 = down1[0] + down2[0]
        prefix2 = down1[1] + down2[1]
        across1_options = words8_by_prefix.get(prefix1, [])
        across2_options = words8_by_prefix.get(prefix2, [])
        if not across1_options or not across2_options:
            continue
        across1 = rng.choice(across1_options)
        across2 = rng.choice(across2_options)
        answers = {across1, across2, down1, down2}
        if len(answers) != 4:
            continue
        return {
            index_by_launch[required["across1"]]: across1,
            index_by_launch[required["across2"]]: across2,
            index_by_launch[required["down1"]]: down1,
            index_by_launch[required["down2"]]: down2,
        }
    return {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wordlist", type=Path, default=DEFAULT_WORDLIST)
    parser.add_argument("--shape-report", type=Path, default=DEFAULT_SHAPE)
    parser.add_argument(
        "--shape-catalog",
        type=Path,
        help=(
            "Load every unique valid silhouette from a grid catalogue while "
            "ignoring all of its old answers and definitions."
        ),
    )
    parser.add_argument(
        "--shape-id",
        help="When loading a shape catalogue, solve only this exact silhouette.",
    )
    parser.add_argument(
        "--one-per-shape",
        action="store_true",
        help="Accept at most one fill for each silhouette in the loaded pool.",
    )
    parser.add_argument(
        "--vary-shapes",
        action="store_true",
        help="Systematically scan all safe central-pivot masks.",
    )
    parser.add_argument(
        "--exclude-batch-answers",
        action="store_true",
        help="Hard-exclude answers used by earlier raw candidates.",
    )
    parser.add_argument(
        "--maximum-batch-lemma-uses",
        type=int,
        default=0,
        help=(
            "Hard-cap reuse of a lexical family across accepted raw fills; "
            "0 disables the cap, 1 means no repeats."
        ),
    )
    parser.add_argument(
        "--exclude-active",
        action="store_true",
        help="Hard-exclude every answer already used by the active catalogue.",
    )
    parser.add_argument(
        "--exclude-answer",
        action="append",
        default=[],
        help="Reject one normalized answer for this construction pass (repeatable).",
    )
    parser.add_argument(
        "--repair-search",
        action="store_true",
        help="Explore neighboring fills by excluding one weak answer at a time.",
    )
    parser.add_argument(
        "--repair-branch-count",
        type=int,
        default=12,
        help=(
            "How many answers from each closure may seed a forced-replacement "
            "branch; use the slot count to challenge every repeated answer."
        ),
    )
    parser.add_argument(
        "--explore-randomly",
        action="store_true",
        help=(
            "Randomize closure choices above the lexical quality floor so "
            "different seeds do not reproduce the same locally optimal fill."
        ),
    )
    parser.add_argument(
        "--strict-frame-anchor",
        action="store_true",
        help=(
            "Seed the two unavoidable 8-letter rows and 9-letter columns "
            "with score-30 answers before solving the rest."
        ),
    )
    parser.add_argument(
        "--strict-frame-fixed-anchor",
        action="store_true",
        help=(
            "Rotate a compatible 8x9 corner rectangle on every attempt, then "
            "solve the remaining slots without changing those four entries."
        ),
    )
    parser.add_argument(
        "--strict-frame-anchor-candidates",
        type=Path,
        help="Cycle through pre-ranked compatible anchor rectangles from JSON.",
    )
    parser.add_argument(
        "--strict-frame-anchor-minimum-score",
        type=float,
        default=30.0,
        help="Independent lexical floor for the four unavoidable 8/9-letter anchors.",
    )
    parser.add_argument("--raw-target", type=int, default=100)
    parser.add_argument("--shortlist", type=int, default=10)
    parser.add_argument(
        "--maximum-two-letter", type=int, default=2, choices=range(0, 3)
    )
    parser.add_argument("--attempt-limit", type=int, default=600)
    parser.add_argument("--seconds", type=float, default=180.0)
    parser.add_argument("--seconds-per-attempt", type=float, default=1.5)
    parser.add_argument(
        "--minimum-constructor-score",
        type=float,
        default=30.0,
        help="Quality floor applied during solving; the full reserve stays on disk.",
    )
    parser.add_argument(
        "--minimum-source-frequency",
        type=float,
        default=0.0,
        help=(
            "Reject dictionary-only forms below this attested corpus frequency; "
            "curated short answers and school-attested forms remain available."
        ),
    )
    parser.add_argument(
        "--allow-central-reviewed",
        action="store_true",
        help=(
            "Keep zero-frequency answers only when the central corpus already "
            "contains a generator-eligible reviewed clue for that answer."
        ),
    )
    parser.add_argument(
        "--minimum-wordfreq-zipf",
        type=float,
        default=0.0,
        help=(
            "Use the independent French wordfreq ranking as a human-usage "
            "gate; accents are normalized only after the frequency lookup."
        ),
    )
    parser.add_argument(
        "--solution-limit",
        type=int,
        default=1,
        help=(
            "Compare this many complete fills per attempt and retain the best "
            "one; 1 preserves the historical first-feasible behavior."
        ),
    )
    parser.add_argument(
        "--branching-strategy",
        choices=("cell", "slot"),
        default="cell",
        help="Branch on a crossing letter or on the most constrained answer slot.",
    )
    parser.add_argument(
        "--maximum-unconfirmed-answers",
        type=int,
        default=-1,
        help=(
            "Maximum answers supported only by wordfreq; -1 disables the "
            "quota, 0 requires every answer to have a French editorial source."
        ),
    )
    parser.add_argument("--seed", type=int, default=718400)
    parser.add_argument(
        "--resume-from",
        type=Path,
        help=(
            "Resume a previous raw batch, preserving its vocabulary usage "
            "before searching for additional closures."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    craft.MAX_TWO_LETTER = args.maximum_two_letter
    live_usage = craft.active_usage()
    loaded = craft.load_large_constructor_candidates(
        args.wordlist, set(), args.minimum_constructor_score
    )
    if loaded is None:
        raise RuntimeError("Expected the large definition-free constructor wordlist")
    (
        words_by_length,
        scores,
        spellings,
        lemmas,
        _recorded_usage,
        wordlist_meta,
    ) = loaded
    with gzip.open(args.wordlist, "rt", encoding="utf-8") as handle:
        wordlist_document = json.load(handle)
    metadata = {
        entry["answer"]: entry for entry in wordlist_document.get("entries", [])
        if entry.get("answer") in scores
    }
    central_reviewed_answers: set[str] = set()
    if args.allow_central_reviewed:
        with gzip.open(DEFAULT_CENTRAL_CORPUS, "rt", encoding="utf-8") as handle:
            central_document = json.load(handle)
        central_reviewed_answers = {
            str(entry.get("answer", ""))
            for entry in central_document.get("entries", [])
            if entry.get("generatorEligible")
        }
    if args.minimum_source_frequency > 0:
        allowed_answers = {
            answer
            for answer, entry in metadata.items()
            if entry.get("formType") == "curated"
            or float(entry.get("sourceFrequency", 0.0))
            >= args.minimum_source_frequency
            or float(entry.get("schoolFrequency", 0.0)) > 0
            or answer in central_reviewed_answers
        }
        words_by_length = {
            length: [
                answer for answer in answers if answer in allowed_answers
            ]
            for length, answers in words_by_length.items()
        }
        scores = {
            answer: score for answer, score in scores.items()
            if answer in allowed_answers
        }
        spellings = {
            answer: spelling for answer, spelling in spellings.items()
            if answer in allowed_answers
        }
        lemmas = {
            answer: lemma for answer, lemma in lemmas.items()
            if answer in allowed_answers
        }
        metadata = {
            answer: entry for answer, entry in metadata.items()
            if answer in allowed_answers
        }
    if args.minimum_wordfreq_zipf > 0:
        from wordfreq import iter_wordlist, zipf_frequency

        wordfreq_scores: dict[str, float] = {}
        wordfreq_spellings: dict[str, str] = {}
        for spelling in iter_wordlist("fr"):
            zipf = float(zipf_frequency(spelling, "fr"))
            if zipf < args.minimum_wordfreq_zipf:
                break
            if not spelling.isalpha():
                continue
            answer = normalized_answer(spelling)
            if answer not in scores:
                continue
            if zipf > wordfreq_scores.get(answer, -1.0):
                wordfreq_scores[answer] = zipf
                wordfreq_spellings[answer] = spelling
        allowed_answers = set(wordfreq_scores) | central_reviewed_answers | {
            answer for answer, entry in metadata.items()
            if entry.get("formType") == "curated"
        }
        words_by_length = {
            length: [
                answer for answer in answers if answer in allowed_answers
            ]
            for length, answers in words_by_length.items()
        }
        scores = {
            answer: max(score, wordfreq_scores.get(answer, 0.0) * 10.0)
            for answer, score in scores.items()
            if answer in allowed_answers
        }
        spellings = {
            answer: wordfreq_spellings.get(answer, spelling)
            for answer, spelling in spellings.items()
            if answer in allowed_answers
        }
        lemmas = {
            answer: lemma for answer, lemma in lemmas.items()
            if answer in allowed_answers
        }
        metadata = {
            answer: {
                **entry,
                "wordfreqZipf": wordfreq_scores.get(answer, 0.0),
                "constructorScore": scores[answer],
            }
            for answer, entry in metadata.items()
            if answer in allowed_answers
        }
    confirmed_answers = {
        answer
        for answer, entry in metadata.items()
        if is_editorially_confirmed(answer, entry)
    }
    metadata = {
        answer: {
            **entry,
            "editoriallyConfirmed": answer in confirmed_answers,
        }
        for answer, entry in metadata.items()
    }
    common8 = [
        answer for answer in words_by_length.get(8, [])
        if scores[answer] >= args.strict_frame_anchor_minimum_score
        and (not args.exclude_active or answer not in live_usage)
    ]
    common9 = [
        answer for answer in words_by_length.get(9, [])
        if scores[answer] >= args.strict_frame_anchor_minimum_score
        and (not args.exclude_active or answer not in live_usage)
    ]
    words8_by_prefix: dict[str, list[str]] = {}
    for answer in common8:
        words8_by_prefix.setdefault(answer[:2], []).append(answer)
    ranked_anchor_candidates = []
    if args.strict_frame_anchor_candidates:
        ranked_anchor_document = json.loads(
            args.strict_frame_anchor_candidates.read_text(encoding="utf-8")
        )
        ranked_anchor_candidates = list(
            ranked_anchor_document.get("candidates", [])
        )
        if not ranked_anchor_candidates:
            raise RuntimeError("The ranked anchor candidate file is empty")
    conflicts = craft.load_rejected_cooccurrence_map()
    indexes = (
        words_by_length,
        None,
        scores,
        lemmas,
        {answer: set(conflicts.get(answer, set())) for answer in scores},
        {answer: "normal" for answer in scores},
        set(),
    )

    shape_document = json.loads(args.shape_report.read_text(encoding="utf-8"))
    shape_grid = shape_document.get("grid", shape_document)
    fixed_clues = {tuple(cell) for cell in shape_grid["clueCells"]}
    fixed_raw_slots = craft.direct_slots(fixed_clues)
    fixed_geometry_audit = craft.validate_geometry(
        str(shape_grid.get("id", "large-lexical-fixed-shape")),
        fixed_clues,
        fixed_raw_slots,
    )
    if not fixed_geometry_audit.get("valid"):
        raise RuntimeError("The batch shape failed geometry validation")
    fixed_slots = [
        craft.Slot(
            index=index,
            slot_id=item["slotId"],
            direction=item["direction"],
            clue_cell=tuple(item["clueCell"]),
            cells=tuple(tuple(cell) for cell in item["cells"]),
        )
        for index, item in enumerate(fixed_raw_slots)
    ]
    rng = random.Random(args.seed)
    if args.shape_catalog:
        shape_pool = catalog_shape_pool(
            args.shape_catalog,
            args.maximum_two_letter,
        )
        if not shape_pool:
            raise RuntimeError("The shape catalogue contains no eligible geometry")
    elif args.vary_shapes:
        shape_pool = (
            safe_shape_pool()
            if args.maximum_two_letter == 0
            else sampled_shape_pool(rng, args.maximum_two_letter)
        )
    else:
        shape_pool = [(
            fixed_clues, fixed_raw_slots, fixed_slots, fixed_geometry_audit
        )]
    if not shape_pool:
        raise RuntimeError("No valid silhouette was produced for this policy")
    if args.shape_id:
        shape_pool = [
            item for item in shape_pool
            if item[3].get("sourceShapeId") == args.shape_id
        ]
        if not shape_pool:
            raise RuntimeError(f"Unknown or invalid shape id: {args.shape_id}")
    rng.shuffle(shape_pool)
    started = time.monotonic()
    resumed_candidates = []
    if args.resume_from:
        resumed_document = json.loads(args.resume_from.read_text(encoding="utf-8"))
        resumed_candidates = list(resumed_document.get("rawCandidates", []))
    resumed_count = len(resumed_candidates)
    raw_candidates = list(resumed_candidates)
    accepted_shape_ids = {
        str(candidate.get("sourceShapeId", ""))
        for candidate in raw_candidates
    }
    seen_fills = {
        tuple(sorted(item["answer"] for item in candidate["answers"]))
        for candidate in raw_candidates
    }
    batch_usage = Counter()
    batch_lemma_usage = Counter()
    answers_by_lemma: dict[str, set[str]] = {}
    if args.maximum_batch_lemma_uses > 0:
        for answer, lemma in lemmas.items():
            answers_by_lemma.setdefault(lemma, set()).add(answer)
    batch_lemma_exclusions: set[str] = set()
    for candidate in raw_candidates:
        answers = [item["answer"] for item in candidate["answers"]]
        batch_usage.update(answers)
        batch_lemma_usage.update(
            item.get("lemma", lemmas[item["answer"]])
            for item in candidate["answers"]
        )
    if args.maximum_batch_lemma_uses > 0:
        for lemma, count in batch_lemma_usage.items():
            if count >= args.maximum_batch_lemma_uses:
                batch_lemma_exclusions.update(answers_by_lemma.get(lemma, set()))
    failure_reasons = Counter()
    attempts = 0
    valid_shapes = 0
    cache_hits = 0
    repair_queue = [frozenset()]
    seen_repairs = {frozenset()}
    while (
        len(raw_candidates) < args.raw_target
        and attempts < args.attempt_limit
        and time.monotonic() - started < args.seconds
    ):
        attempts += 1
        if args.repair_search and not repair_queue:
            break
        repair_exclusions = (
            repair_queue.pop(0) if args.repair_search else frozenset()
        )
        current_shape_pool = (
            [
                item for item in shape_pool
                if str(item[3].get("sourceShapeId", ""))
                not in accepted_shape_ids
            ]
            if args.one_per_shape
            else shape_pool
        )
        if not current_shape_pool:
            break
        clues, raw_slots, slots, geometry_audit = current_shape_pool[
            (attempts - 1) % len(current_shape_pool)
        ]
        valid_shapes += 1
        telemetry = {}
        anchor_domains = {}
        fixed_anchors = {}
        if ranked_anchor_candidates:
            record = ranked_anchor_candidates[
                (attempts - 1) % len(ranked_anchor_candidates)
            ]
            fixed_anchors = {
                int(index): answer
                for index, answer in record.get("answers", {}).items()
            }
            if len(fixed_anchors) != 4:
                failure_reasons["ranked-anchor-invalid"] += 1
                continue
        elif args.strict_frame_fixed_anchor:
            fixed_anchors = sample_strict_frame_anchors(
                slots,
                words8_by_prefix,
                common9,
                random.Random(args.seed * 1009 + attempts),
            )
            if len(fixed_anchors) != 4:
                failure_reasons["strict-frame-fixed-anchor-unavailable"] += 1
                continue
        elif args.strict_frame_anchor:
            for slot in slots:
                launch = (slot.direction, slot.clue_cell, len(slot.cells))
                if launch in {
                    ("across", (1, 0), 8),
                    ("across", (2, 0), 8),
                }:
                    anchor_domains[slot.index] = set(common8)
                elif launch in {
                    ("down", (0, 1), 9),
                    ("down", (0, 2), 9),
                }:
                    anchor_domains[slot.index] = set(common9)
        if args.strict_frame_anchor and len(anchor_domains) != 4:
            failure_reasons["strict-frame-anchor-unavailable"] += 1
            continue
        combined_usage = {
            answer: int(live_usage.get(answer, 0)) * 10_000
            + int(batch_usage.get(answer, 0))
            for answer in scores
            if live_usage.get(answer, 0) or batch_usage.get(answer, 0)
        }
        remaining = args.seconds - (time.monotonic() - started)
        solved = fill_bitset(
            slots,
            indexes,
            random.Random(args.seed + attempts),
            None,
            unavailable_answers=(
                (set(live_usage) if args.exclude_active else set())
                | {normalized_answer(answer) for answer in args.exclude_answer}
                | set(repair_exclusions)
                | (set(batch_usage) if args.exclude_batch_answers else set())
                | batch_lemma_exclusions
            ),
            answer_usage=combined_usage,
            allowed_answers_by_slot=anchor_domains,
            fixed_answers=fixed_anchors,
            max_grammar_answers=99,
            grammar_answers=set(),
            undesirable_answers=set(scores) - confirmed_answers,
            max_undesirable_answers=(
                None
                if args.maximum_unconfirmed_answers < 0
                else args.maximum_unconfirmed_answers
            ),
            max_seconds=min(args.seconds_per_attempt, max(0.05, remaining)),
            node_limit=4_000_000,
            require_image=False,
            prefer_constraint_support=True,
            constraint_support_bucket_size=8,
            branching_strategy=args.branching_strategy,
            quality_scores=scores,
            solution_limit=args.solution_limit,
            explore_randomly=args.explore_randomly,
            telemetry=telemetry,
        )
        cache_hits += bool(telemetry.get("indexCacheHit"))
        if solved is None:
            failure_reasons[str(telemetry.get("reason", "unsolved"))] += 1
            continue
        answers = [solved[index] for index in sorted(solved)]
        if args.repair_search:
            repair_seeds = sorted(
                answers,
                key=lambda answer: (
                    -int(batch_usage.get(answer, 0)),
                    scores[answer],
                    answer,
                ),
            )[: max(1, args.repair_branch_count)]
            for answer in repair_seeds:
                child = frozenset(set(repair_exclusions) | {answer})
                if child not in seen_repairs:
                    seen_repairs.add(child)
                    repair_queue.append(child)
        fingerprint = tuple(sorted(answers))
        if fingerprint in seen_fills:
            failure_reasons["duplicate-fill"] += 1
            continue
        seen_fills.add(fingerprint)
        batch_usage.update(answers)
        batch_lemma_usage.update(lemmas[answer] for answer in answers)
        if args.maximum_batch_lemma_uses > 0:
            for answer in answers:
                lemma = lemmas[answer]
                if batch_lemma_usage[lemma] >= args.maximum_batch_lemma_uses:
                    batch_lemma_exclusions.update(answers_by_lemma[lemma])
        quality = candidate_quality(answers, metadata, live_usage)
        raw_candidates.append({
            "id": f"large-lexical-raw-{len(raw_candidates) + 1:03d}",
            "seed": args.seed + attempts,
            "sourceShapeId": geometry_audit.get(
                "sourceShapeId", shape_grid.get("id", "fixed-shape")
            ),
            "repairExclusions": sorted(repair_exclusions),
            "fixedAnchors": {
                str(index): solved[index]
                for index in sorted(set(anchor_domains) | set(fixed_anchors))
            },
            "clueCells": [list(cell) for cell in sorted(clues)],
            "internalClueCells": [
                list(cell) for cell in sorted(clues - craft.FRAME)
            ],
            "rawSlots": raw_slots,
            "answers": [
                {
                    "slotIndex": index,
                    "answer": solved[index],
                    "spelling": spellings[solved[index]],
                    "constructorScore": scores[solved[index]],
                    "lemma": lemmas[solved[index]],
                    "formType": metadata[solved[index]].get("formType"),
                    "attestedCommonForm": metadata[solved[index]].get(
                        "attestedCommonForm", False
                    ),
                    "editoriallyConfirmed": metadata[solved[index]].get(
                        "editoriallyConfirmed", False
                    ),
                    "wordfreqZipf": metadata[solved[index]].get(
                        "wordfreqZipf", 0.0
                    ),
                }
                for index in sorted(solved)
            ],
            "quality": quality,
            "geometryAudit": geometry_audit,
            "solverTelemetry": telemetry,
            "publicationEligible": False,
        })
        accepted_shape_ids.add(str(geometry_audit.get("sourceShapeId", "")))
        if len(raw_candidates) % 10 == 0:
            print(json.dumps({
                "progress": len(raw_candidates),
                "target": args.raw_target,
                "attempts": attempts,
                "elapsedSeconds": round(time.monotonic() - started, 1),
            }), flush=True)

    shortlisted = select_diverse_shortlist(raw_candidates, args.shortlist)
    for rank, candidate in enumerate(shortlisted, 1):
        candidate["shortlistRank"] = rank
    payload = {
        "version": 1,
        "kind": "definition-free-large-lexical-grid-batch",
        "catalogModified": False,
        "publicationEligible": False,
        "policy": {
            "definitionsUsedForPlacement": False,
            "definitionsRequiredAfterShortlist": True,
            "maximumTwoLetterAnswers": args.maximum_two_letter,
            "minimumConstructorScore": args.minimum_constructor_score,
            "minimumSourceFrequency": args.minimum_source_frequency,
            "centralReviewedFallback": args.allow_central_reviewed,
            "minimumWordfreqZipf": args.minimum_wordfreq_zipf,
            "explicitlyExcludedAnswers": sorted({
                normalized_answer(answer) for answer in args.exclude_answer
            }),
            "solutionLimit": args.solution_limit,
            "branchingStrategy": args.branching_strategy,
            "maximumUnconfirmedAnswers": args.maximum_unconfirmed_answers,
            "onePerShape": args.one_per_shape,
            "rawTarget": args.raw_target,
            "shortlistTarget": args.shortlist,
            "randomExploration": args.explore_randomly,
            "maximumBatchLemmaUses": args.maximum_batch_lemma_uses,
            "strictFrameAnchor": args.strict_frame_anchor,
            "strictFrameFixedAnchor": args.strict_frame_fixed_anchor,
            "rankedAnchorCandidates": (
                str(args.strict_frame_anchor_candidates)
                if args.strict_frame_anchor_candidates else None
            ),
            "strictFrameAnchorMinimumScore": (
                args.strict_frame_anchor_minimum_score
            ),
            "resumedFrom": str(args.resume_from) if args.resume_from else None,
        },
        "wordlist": wordlist_meta,
        "metrics": {
            "attempts": attempts,
            "validShapes": valid_shapes,
            "rawCandidates": len(raw_candidates),
            "shortlisted": len(shortlisted),
            "elapsedSeconds": round(time.monotonic() - started, 2),
            "indexCacheHits": cache_hits,
            "failureReasons": dict(sorted(failure_reasons.items())),
            "resumedCandidates": resumed_count,
        },
        "shortlist": shortlisted,
        "rawCandidates": raw_candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "rawCandidates": len(raw_candidates),
        "shortlisted": len(shortlisted),
        "attempts": attempts,
        "elapsedSeconds": payload["metrics"]["elapsedSeconds"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if raw_candidates else 2


if __name__ == "__main__":
    raise SystemExit(main())
