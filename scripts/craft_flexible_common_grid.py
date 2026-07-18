#!/usr/bin/env python3
"""Craft one 9x10 word-first grid around common French answers.

Only the top row and left column are fixed as clue cells. Interior clue cells
are sampled freely, without orthogonally adjacent clues, until an exact lexical
closure is found. This is a staging tool: it writes no catalogue and invents
no clues.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import sys
import time
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

from wordfreq import iter_wordlist, zipf_frequency


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from bitset_grid_filler import fill_bitset  # noqa: E402
from build_reference_style_shapes_a import direct_slots, validate_geometry  # noqa: E402
from diagnose_fixed_shape_corpus_gaps import Slot  # noqa: E402


ROWS = 10
COLUMNS = 9
MAX_TWO_LETTER = 2
FRAME = {
    *((0, column) for column in range(COLUMNS)),
    *((row, 0) for row in range(1, ROWS)),
}
SAFE_SHORT = {
    "AS",
    "BD",
    "CB",
    "CD",
    "CP",
    "CV",
    "IA",
    "KO",
    "OR",
    "OS",
    "PC",
    "QI",
    "TV",
    "UE",
    "WC",
    "BAC",
    "CDI",
    "CPE",
    "HLM",
    "LIT",
    "LOT",
    "MIG",
    "NIL",
    "PAC",
    "PNG",
    "POP",
    "RAP",
    "SAC",
    "TIG",
    "TOM",
    "TPE",
    # Common two-letter French forms admitted by the owner's simplified rule.
    "AU",
    "CE",
    "DE",
    "DO",
    "DU",
    "EN",
    "ET",
    "EU",
    "IL",
    "LA",
    "LE",
    "LU",
    "MA",
    "ME",
    "NE",
    "NI",
    "ON",
    "OU",
    "PU",
    "RI",
    "SA",
    "SE",
    "SI",
    "TA",
    "TE",
    "TU",
    "UN",
    "VA",
    "VU",
    "AH",
    "EH",
    "OH",
    "OM",
}

# Unlike longer answers, a two-letter form cannot be rescued by crossings or a
# nuanced clue.  Keep only forms a normal French-speaking player can reasonably
# identify.  Musical notes and crossword-only syllables are intentionally out.
CURATED_TWO_LETTER = {
    "AH", "AS", "AU", "BD", "CB", "CD", "CE", "CP", "CV", "DE", "DU",
    "EH", "EN", "ET", "EU", "IA", "IL", "KO", "LA", "LE", "LU", "MA",
    "ME", "NE", "NI", "OH", "OM", "ON", "OR", "OS", "OU", "PC", "QI",
    "SA", "SE", "SI", "TA", "TE", "TU", "TV", "UE", "UN", "VA", "VU",
    "WC",
}


def normalized(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.upper())
    return "".join(char for char in folded if "A" <= char <= "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimum-zipf", type=float, default=3.35)
    parser.add_argument("--maximum-two-letter", type=int, default=2, choices=range(0, 7))
    parser.add_argument("--seconds", type=float, default=180.0)
    parser.add_argument("--seconds-per-shape", type=float, default=2.0)
    parser.add_argument(
        "--solution-candidates",
        type=int,
        default=24,
        help=(
            "Compare this many complete fills before retaining the best one. "
            "Use 1 for the historical first-feasible behaviour."
        ),
    )
    parser.add_argument(
        "--constructor-wordlist",
        type=Path,
        default=ROOT / "src/data/fill.wordlist.large.json.gz",
        help="Optional scored answer list used only to rank placement candidates.",
    )
    parser.add_argument(
        "--minimum-constructor-score",
        type=float,
        default=0.0,
        help="Retain the full lexical reserve by default; score only orders choices.",
    )
    parser.add_argument("--seed", type=int, default=718100)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude-answer", action="append", default=[])
    parser.add_argument(
        "--exclude-from",
        action="append",
        type=Path,
        default=[],
        help=(
            "Previously accepted/reviewed grid JSON. Its answers and every "
            "known lemma-family variant are removed before solving."
        ),
    )
    parser.add_argument(
        "--exclude-active",
        action="store_true",
        help="Reject every answer already present in the active catalogue.",
    )
    parser.add_argument("--mutations-only", action="store_true")
    parser.add_argument(
        "--random-only",
        action="store_true",
        help="Skip catalogue masks and mutations; sample new free-interior masks directly.",
    )
    parser.add_argument("--fixed-shape-report", type=Path)
    parser.add_argument(
        "--fixed-shape-only",
        action="store_true",
        help="Do not fall back to other masks when the supplied fixed shape fails.",
    )
    parser.add_argument(
        "--fixed-shape-id",
        help="Select one shape by id when the fixed report contains a shapes array.",
    )
    parser.add_argument("--include-child-forms", action="store_true")
    parser.add_argument(
        "--include-morphalou-forms",
        action="store_true",
        help=(
            "Use frequent Morphalou noun/verb forms as structural rescue. "
            "They remain unreviewed and cannot be published without editorial review."
        ),
    )
    parser.add_argument(
        "--morphalou-lemmas-only",
        action="store_true",
        help=(
            "When Morphalou is enabled, keep only dictionary headwords. "
            "This removes rare conjugations and inflected rescue forms."
        ),
    )
    parser.add_argument(
        "--branching-strategy", choices=("slot", "cell"), default="slot"
    )
    parser.add_argument(
        "--central-corpus-only",
        action="store_true",
        help="Use only easy/normal answers from the reviewed central corpus.",
    )
    parser.add_argument(
        "--minimum-images",
        type=int,
        default=0,
        choices=range(0, 7),
        help="Require this many reviewed image answers in the lexical closure.",
    )
    return parser.parse_args()


def extract_reference_words(document: dict) -> list[dict]:
    if isinstance(document.get("grid"), dict):
        grid = document["grid"]
    elif isinstance(document.get("grids"), list) and document["grids"]:
        grid = document["grids"][0]
    else:
        grid = document
    return list(grid.get("answers") or grid.get("words") or [])


@lru_cache(maxsize=1)
def load_morphalou_entries() -> tuple[dict, ...]:
    with gzip.open(
        ROOT / "src/data/crossword.morphalou.staging.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        return tuple(json.load(handle).get("entries", []))


@lru_cache(maxsize=1)
def load_rejected_cooccurrence_map() -> dict[str, set[str]]:
    document = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    conflicts: dict[str, set[str]] = {}
    for rule in document.get("rejectedCooccurrences", []):
        answers = {
            str(answer).upper() for answer in rule.get("answers", []) if answer
        }
        for answer in answers:
            conflicts.setdefault(answer, set()).update(answers - {answer})
    return conflicts


@lru_cache(maxsize=2)
def load_lemma_families(include_morphalou_forms: bool = False) -> dict[str, str]:
    families: dict[str, str] = {}
    for name in ("lexique.lemmas.json", "lexique.child-forms.json"):
        document = json.loads((ROOT / "src/data" / name).read_text(encoding="utf-8"))
        for entry in document.get("entries", []):
            answer = str(entry.get("answer", "")).upper()
            if answer:
                families[answer] = str(entry.get("lemma") or answer).upper()
    if include_morphalou_forms:
        for entry in load_morphalou_entries():
            answer = str(entry.get("answer", "")).upper()
            if answer:
                families[answer] = str(
                    entry.get("lemmaAnswer") or answer
                ).upper()
    return families


def build_replacement_exclusions(
    explicit: set[str], reference_paths: list[Path], *,
    include_morphalou_forms: bool = False,
) -> tuple[set[str], set[str]]:
    """Return exact answers and all known variants of referenced families."""
    families = load_lemma_families(include_morphalou_forms)
    excluded = {answer.upper() for answer in explicit}
    blocked_families = {families.get(answer, answer) for answer in excluded}
    for path in reference_paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        for item in extract_reference_words(document):
            answer = str(item.get("answer", "")).upper()
            if not answer:
                continue
            excluded.add(answer)
            concept = str(item.get("conceptGroup") or "").upper()
            blocked_families.add(concept or families.get(answer, answer))
    excluded.update(
        answer for answer, family in families.items() if family in blocked_families
    )
    return excluded, blocked_families


def morphalou_structural_entry_allowed(
    entry: dict, *, lemmas_only: bool = False
) -> bool:
    """Keep usable structural vocabulary; optionally reject every inflection."""
    answer = str(entry.get("answer", ""))
    part_of_speech = entry.get("partOfSpeech")
    form_type = entry.get("formType")
    if not 3 <= len(answer) <= 9:
        return False
    if part_of_speech not in {"common-noun", "verb", "adjective", "adverb"}:
        return False
    if lemmas_only:
        return form_type == "lemma"
    return part_of_speech in {"common-noun", "verb"} or form_type == "lemma"


def load_candidates(
    minimum_zipf: float,
    excluded: set[str],
    include_child_forms: bool,
    include_morphalou_forms: bool = False,
    morphalou_lemmas_only: bool = False,
):
    lemmas_document = json.loads(
        (ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8")
    )
    child_document = json.loads(
        (ROOT / "src/data/lexique.child-forms.json").read_text(encoding="utf-8")
    )
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    rejected = set(blacklist.get("rejectedAnswers", []))
    rejected.update(blacklist.get("rejectedEasyAnswers", []))
    rejected.update(blacklist.get("rejectedNormalAnswers", []))
    rejected.update(
        str(item.get("answer", "")).upper()
        for item in blacklist.get("rotationCooldownAnswers", [])
        if item.get("answer")
    )
    rejected.update(excluded)

    allowed = {
        entry["answer"]
        for entry in lemmas_document.get("entries", [])
        if entry.get("partOfSpeech") in {"NOM", "ADJ", "ADV", "VER"}
    }
    if include_child_forms:
        allowed.update(
            entry["answer"]
            for entry in child_document.get("entries", [])
            if entry.get("partOfSpeech") in {"NOM", "ADJ", "ADV", "VER"}
        )
    if include_morphalou_forms:
        allowed.update(
            entry["answer"]
            for entry in load_morphalou_entries()
            if morphalou_structural_entry_allowed(
                entry, lemmas_only=morphalou_lemmas_only
            )
        )

    # Short answers need stronger evidence than mere dictionary presence.
    # Three-letter forms must already have an accessible reviewed crossword
    # entry, unless the owner explicitly supplied them in SAFE_SHORT.
    import generate_grid_catalog as generator

    reviewed_entries = list(generator.load_entries())
    reviewed_short = {
        entry["answer"]
        for entry in reviewed_entries
        if entry.get("length") == 3 and entry.get("difficulty") in {"easy", "normal"}
    }

    scores: dict[str, float] = {}
    spellings: dict[str, str] = {}
    by_length: dict[int, list[str]] = {length: [] for length in range(2, 10)}
    for spelling in iter_wordlist("fr"):
        score = zipf_frequency(spelling, "fr")
        if score < minimum_zipf:
            break
        if not spelling.isalpha():
            continue
        answer = normalized(spelling)
        if (
            len(answer) not in by_length
            or answer not in allowed
            or answer in rejected
            or answer in scores
            or (len(answer) == 2 and answer not in CURATED_TWO_LETTER)
            or (len(answer) == 3 and answer not in reviewed_short and answer not in SAFE_SHORT)
        ):
            continue
        scores[answer] = score
        spellings[answer] = spelling
        by_length[len(answer)].append(answer)
    for answer in SAFE_SHORT:
        if len(answer) not in by_length or answer in rejected:
            continue
        if len(answer) == 2 and answer not in CURATED_TWO_LETTER:
            continue
        if answer not in scores:
            scores[answer] = 4.5
            spellings[answer] = answer.lower()
            by_length[len(answer)].append(answer)

    # The central catalogue is already definition-backed and editorially
    # filtered.  It must be UNIONED with the structural lexicon, not merely
    # used as evidence for words that happen to occur in both datasets.  The
    # old intersection silently discarded most of the owner's reviewed corpus
    # (and left only a few dozen three-letter candidates).
    for entry in reviewed_entries:
        answer = str(entry.get("answer", "")).upper()
        length = len(answer)
        score = float(entry.get("frequency", 0.0) or 0.0)
        if (
            length not in by_length
            or answer in rejected
            or entry.get("difficulty") not in {"easy", "normal"}
            or score < minimum_zipf
            or normalized(answer) != answer
            or (length == 2 and answer not in CURATED_TWO_LETTER)
        ):
            continue
        if answer not in scores:
            by_length[length].append(answer)
            spellings[answer] = answer.lower()
        scores[answer] = max(score, scores.get(answer, 0.0))
    return (
        {length: tuple(sorted(words)) for length, words in by_length.items()},
        scores,
        spellings,
    )


def load_central_candidates(minimum_zipf: float, excluded: set[str]):
    """Load only accessible, definition-backed answers from the central corpus."""
    import generate_grid_catalog as generator

    scores: dict[str, float] = {}
    spellings: dict[str, str] = {}
    by_length: dict[int, list[str]] = {length: [] for length in range(2, 10)}
    for entry in generator.load_entries():
        answer = str(entry.get("answer", "")).upper()
        score = float(entry.get("frequency", 0.0) or 0.0)
        length = len(answer)
        if (
            length not in by_length
            or answer in excluded
            or answer in scores
            or entry.get("difficulty") not in {"easy", "normal"}
            or score < minimum_zipf
        ):
            continue
        scores[answer] = score
        spellings[answer] = answer.lower()
        by_length[length].append(answer)
    return (
        {length: tuple(sorted(words)) for length, words in by_length.items()},
        scores,
        spellings,
    )


def editorial_quality_scores(scores: dict[str, float]) -> tuple[dict[str, float], int]:
    """Build an Ingrid-style scored list with a review-evidence bonus.

    Frequency remains useful, but a definition-backed answer that has already
    passed MotMan's editorial filters should outrank an equally common raw
    structural form.  The original Zipf score is kept separately for reports.
    """
    import generate_grid_catalog as generator

    reviewed = {
        str(entry.get("answer", "")).upper()
        for entry in generator.load_entries()
        if entry.get("difficulty") in {"easy", "normal"}
    }
    quality = {
        answer: float(score) + (0.75 if answer in reviewed else 0.0)
        for answer, score in scores.items()
    }
    return quality, len(set(scores).intersection(reviewed))


def load_constructor_quality_scores(
    path: Path | None,
    fallback: dict[str, float],
) -> tuple[dict[str, float], dict]:
    """Overlay professional-style constructor scores without importing clues."""
    if path is None or not path.exists():
        return fallback, {"loaded": False, "path": str(path) if path else None}
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        document = json.load(handle)
    wordlist_scores = {
        str(entry.get("answer", "")).upper(): float(entry["constructorScore"])
        for entry in document.get("entries", [])
        if entry.get("answer") and entry.get("constructorScore") is not None
    }
    quality = {
        answer: wordlist_scores.get(answer, fallback[answer] * 10.0)
        for answer in fallback
    }
    return quality, {
        "loaded": True,
        "path": str(path),
        "matchedCandidates": sum(answer in wordlist_scores for answer in fallback),
        "wordlistAnswers": len(wordlist_scores),
        "purpose": "placement ranking only",
    }


def load_large_constructor_candidates(
    path: Path,
    excluded: set[str],
    minimum_score: float,
):
    """Load the complete definition-free Morphalou placement reservoir."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        document = json.load(handle)
    if document.get("kind") != "motman-large-definition-free-constructor-wordlist":
        return None
    current_digest = hashlib.sha256(
        (ROOT / "src/data/editorial.blacklist.json").read_bytes()
    ).hexdigest()
    if document.get("policy", {}).get("blacklistSha256") != current_digest:
        raise RuntimeError(
            "Large constructor wordlist is stale; rebuild it after the blacklist."
        )
    by_length: dict[int, list[str]] = {length: [] for length in range(2, 10)}
    scores: dict[str, float] = {}
    spellings: dict[str, str] = {}
    lemmas: dict[str, str] = {}
    recorded_usage: dict[str, int] = {}
    for entry in document.get("entries", []):
        answer = str(entry.get("answer", "")).upper()
        score = float(entry.get("constructorScore", 0.0) or 0.0)
        length = len(answer)
        if (
            length not in by_length
            or answer in excluded
            or answer in scores
            or score < minimum_score
        ):
            continue
        by_length[length].append(answer)
        scores[answer] = score
        spellings[answer] = str(entry.get("spelling") or answer.lower())
        lemmas[answer] = str(entry.get("lemma") or answer).upper()
        recorded_usage[answer] = int(entry.get("activeUses", 0) or 0)
    return (
        {length: tuple(sorted(words)) for length, words in by_length.items()},
        scores,
        spellings,
        lemmas,
        recorded_usage,
        {
            "loaded": True,
            "path": str(path),
            "kind": document.get("kind"),
            "answers": len(scores),
            "minimumConstructorScore": minimum_score,
            "definitionsUsedForPlacement": False,
        },
    )


def active_usage() -> Counter:
    catalog = json.loads(
        (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
    )
    return Counter(
        word["answer"]
        for grid in catalog.get("grids", [])
        for word in grid.get("words", [])
    )


def catalog_shape_candidates(rng: random.Random):
    """Yield unique, already proven 9x10 masks with the required frame."""
    catalog = json.loads(
        (ROOT / "src/data/grid.catalog.json").read_text(encoding="utf-8")
    )
    candidates = []
    fingerprints = set()
    for grid in catalog.get("grids", []):
        if grid.get("columns") != COLUMNS or grid.get("rows") != ROWS:
            continue
        original_clues = {tuple(cell) for cell in grid.get("clueCells", [])}
        # The owner's new border rule takes precedence. Legacy clue cells in
        # the first two interior rows/columns are removed so every border clue
        # launches at least a two-letter path.
        clues = FRAME | {
            cell
            for cell in original_clues
            if cell[0] >= 3 and cell[1] >= 3
        }
        fingerprint = tuple(sorted(clues))
        if fingerprint in fingerprints:
            continue
        fingerprints.add(fingerprint)
        raw_slots = direct_slots(clues)
        audit = validate_geometry(
            f"common-flex-from-{grid['id']}", clues, raw_slots
        )
        lengths = [slot["length"] for slot in raw_slots]
        if (
            not audit["valid"]
            or any(length < 2 or length > 9 for length in lengths)
            or lengths.count(2) > MAX_TWO_LETTER
            or sum(length >= 5 for length in lengths) < 5
            or max(lengths) < 7
        ):
            continue
        slots = [
            Slot(
                index=index,
                slot_id=item["slotId"],
                direction=item["direction"],
                clue_cell=tuple(item["clueCell"]),
                cells=tuple(tuple(cell) for cell in item["cells"]),
            )
            for index, item in enumerate(raw_slots)
        ]
        candidates.append((grid["id"], clues, raw_slots, slots, audit))
    rng.shuffle(candidates)
    return candidates


def mutated_catalog_shape_candidate(rng: random.Random, bases, attempt: int):
    """Add spaced internal pivots to a proven mask and re-audit it."""
    source_id, base_clues, _raw, _slots, _audit = rng.choice(bases)
    clues = set(base_clues)
    possible = [
        (row, column)
        for row in range(3, ROWS)
        for column in range(3, COLUMNS)
        if (row, column) not in clues
    ]
    rng.shuffle(possible)
    added = set()
    target = rng.randint(7, 14)
    for cell in possible:
        if any(
            (cell[0] + dr, cell[1] + dc) in added
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
        ):
            continue
        added.add(cell)
        if len(added) == target:
            break
    if len(added) != target:
        return None
    clues.update(added)
    raw_slots = direct_slots(clues)
    audit = validate_geometry(f"common-flex-mutated-{attempt:05d}", clues, raw_slots)
    lengths = [slot["length"] for slot in raw_slots]
    if (
        not audit["valid"]
        or any(length < 2 or length > 9 for length in lengths)
        or lengths.count(2) > MAX_TWO_LETTER
        or sum(length >= 5 for length in lengths) < 2
        or max(lengths, default=0) < 5
    ):
        return None
    slots = [
        Slot(
            index=index,
            slot_id=item["slotId"],
            direction=item["direction"],
            clue_cell=tuple(item["clueCell"]),
            cells=tuple(tuple(cell) for cell in item["cells"]),
        )
        for index, item in enumerate(raw_slots)
    ]
    return source_id, clues, raw_slots, slots, audit, added


def no_single_runs(clues: set[tuple[int, int]]) -> bool:
    for direction in ("across", "down"):
        outer = range(ROWS) if direction == "across" else range(COLUMNS)
        limit = COLUMNS if direction == "across" else ROWS
        for fixed in outer:
            offset = 0
            while offset < limit:
                cell = (fixed, offset) if direction == "across" else (offset, fixed)
                if cell in clues:
                    offset += 1
                    continue
                start = offset
                while offset < limit:
                    cell = (fixed, offset) if direction == "across" else (offset, fixed)
                    if cell in clues:
                        break
                    offset += 1
                if offset - start == 1:
                    return False
    return True


def sample_internal_clues(rng: random.Random) -> set[tuple[int, int]] | None:
    # The relaxed owner rule permits adjacent definition cells.  Sampling them
    # freely creates clue walls and, crucially, smaller lexical components that
    # can close with ordinary words instead of relying on many two-letter slots.
    if MAX_TWO_LETTER == 0:
        # With a minimum answer length of three, seven random clue cells make
        # almost every 9x10 mask invalid.  Professional grids instead use a few
        # deliberate pivots in the central band (plus occasional trailing clue
        # cells) to preserve long entries while splitting the hardest stacks.
        target = rng.randint(1, 3)
        candidates = [
            (row, column)
            for row in (4, 5, 6)
            for column in (4, 5, 8)
        ]
        rng.shuffle(candidates)
        return set(candidates[:target])

    allow_adjacent = rng.random() < 0.45
    target = rng.randint(7, 16 if allow_adjacent else 12)
    candidates = [
        (row, column)
        for row in range(2, ROWS)
        for column in range(2, COLUMNS)
    ]
    rng.shuffle(candidates)
    if allow_adjacent:
        return set(candidates[:target])
    chosen: set[tuple[int, int]] = set()
    for cell in candidates:
        if any(
            (cell[0] + dr, cell[1] + dc) in chosen
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
        ):
            continue
        chosen.add(cell)
        if len(chosen) == target:
            return chosen
    return None


def shape_candidate(rng: random.Random, attempt: int):
    internal = sample_internal_clues(rng)
    if not internal:
        return None
    clues = FRAME | internal
    if not no_single_runs(clues):
        return None
    raw_slots = direct_slots(clues)
    audit = validate_geometry(f"common-flex-{attempt:04d}", clues, raw_slots)
    if not audit["valid"]:
        return None
    lengths = [slot["length"] for slot in raw_slots]
    if (
        any(length < 2 or length > 9 for length in lengths)
        or lengths.count(2) > MAX_TWO_LETTER
        or sum(length >= 5 for length in lengths) < 5
        or max(lengths) < 7
    ):
        return None
    slots = [
        Slot(
            index=index,
            slot_id=item["slotId"],
            direction=item["direction"],
            clue_cell=tuple(item["clueCell"]),
            cells=tuple(tuple(cell) for cell in item["cells"]),
        )
        for index, item in enumerate(raw_slots)
    ]
    return clues, raw_slots, slots, audit


def main() -> int:
    global MAX_TWO_LETTER
    args = parse_args()
    MAX_TWO_LETTER = args.maximum_two_letter
    rng = random.Random(args.seed)
    usage = active_usage()
    excluded, excluded_families = build_replacement_exclusions(
        {answer.upper() for answer in args.exclude_answer}, args.exclude_from,
        include_morphalou_forms=args.include_morphalou_forms,
    )
    if args.exclude_active:
        excluded.update(usage)
    large_wordlist = None
    if (
        not args.central_corpus_only
        and args.constructor_wordlist
        and args.constructor_wordlist.exists()
    ):
        large_wordlist = load_large_constructor_candidates(
            args.constructor_wordlist,
            excluded,
            args.minimum_constructor_score,
        )
    if large_wordlist is not None:
        (
            words_by_length,
            scores,
            spellings,
            large_lemma_map,
            _wordlist_usage,
            constructor_wordlist,
        ) = large_wordlist
        quality_scores = scores
        reviewed_candidate_count = 0
    elif args.central_corpus_only:
        words_by_length, scores, spellings = load_central_candidates(
            args.minimum_zipf, excluded
        )
        large_lemma_map = {}
        quality_scores, reviewed_candidate_count = editorial_quality_scores(scores)
        constructor_wordlist = {
            "loaded": False,
            "path": None,
            "purpose": "legacy central-corpus diagnostic only",
        }
    else:
        words_by_length, scores, spellings = load_candidates(
            args.minimum_zipf,
            excluded,
            args.include_child_forms,
            args.include_morphalou_forms,
            args.morphalou_lemmas_only,
        )
        large_lemma_map = {}
        fallback_quality, reviewed_candidate_count = editorial_quality_scores(scores)
        quality_scores, constructor_wordlist = load_constructor_quality_scores(
            args.constructor_wordlist, fallback_quality
        )
    image_document = json.loads(
        (ROOT / "src/data/crossword.images-reviewed.json").read_text(encoding="utf-8")
    )
    image_answers = {
        entry["answer"]
        for entry in image_document.get("entries", [])
        if entry.get("answer") in scores and isinstance(entry.get("image"), dict)
    }
    candidate_families = (
        large_lemma_map
        if large_wordlist is not None
        else load_lemma_families(args.include_morphalou_forms)
    )
    cooccurrence_conflicts = load_rejected_cooccurrence_map()
    indexes = (
        words_by_length,
        None,
        scores,
        {answer: candidate_families.get(answer, answer) for answer in scores},
        {
            answer: set(cooccurrence_conflicts.get(answer, set()))
            for answer in scores
        },
        {answer: "normal" for answer in scores},
        image_answers,
    )
    started = time.monotonic()
    attempts = 0
    valid_shapes = 0
    last_telemetry = {}
    solution = None
    selected = None
    source_shape_id = None
    if args.fixed_shape_report:
        previous = json.loads(args.fixed_shape_report.read_text(encoding="utf-8"))
        if isinstance(previous.get("grid"), dict):
            previous_grid = previous["grid"]
        elif isinstance(previous.get("grids"), list) and previous["grids"]:
            previous_grid = previous["grids"][0]
        elif isinstance(previous.get("shape"), dict):
            previous_grid = previous["shape"]
        elif isinstance(previous.get("shapes"), list) and previous["shapes"]:
            previous_grid = next(
                (
                    shape
                    for shape in previous["shapes"]
                    if shape.get("id") == args.fixed_shape_id
                ),
                previous["shapes"][0],
            )
        else:
            previous_grid = previous
        clues = {tuple(cell) for cell in previous_grid["clueCells"]}
        raw_slots = direct_slots(clues)
        audit = validate_geometry("common-flex-fixed-repair", clues, raw_slots)
        slots = [
            Slot(
                index=index,
                slot_id=item["slotId"],
                direction=item["direction"],
                clue_cell=tuple(item["clueCell"]),
                cells=tuple(tuple(cell) for cell in item["cells"]),
            )
            for index, item in enumerate(raw_slots)
        ]
        attempts += 1
        valid_shapes += 1
        telemetry = {}
        result = fill_bitset(
            slots,
            indexes,
            random.Random(args.seed),
            None,
            answer_usage=dict(usage),
            max_grammar_answers=99,
            grammar_answers=set(),
            max_seconds=args.seconds,
            node_limit=100_000_000,
            require_image=args.minimum_images > 0,
            minimum_images=args.minimum_images,
            prefer_constraint_support=True,
            constraint_support_bucket_size=2,
            branching_strategy=args.branching_strategy,
            quality_scores=quality_scores,
            solution_limit=args.solution_candidates,
            telemetry=telemetry,
        )
        last_telemetry = telemetry
        if result is not None:
            mapping = result if isinstance(result, dict) else dict(enumerate(result))
            if len(mapping) == len(slots):
                solution = mapping
                selected = clues, raw_slots, slots, audit
                source_shape_id = previous_grid.get("id", "fixed-shape-report")
    base_shapes = catalog_shape_candidates(rng)
    for source_id, clues, raw_slots, slots, audit in (
        [] if (
            args.fixed_shape_only or args.mutations_only or args.random_only
        ) else base_shapes
    ):
        if solution is not None:
            break
        if time.monotonic() - started >= args.seconds:
            break
        if any(not words_by_length.get(slot.length) for slot in slots):
            continue
        attempts += 1
        valid_shapes += 1
        telemetry: dict = {}
        result = fill_bitset(
            slots,
            indexes,
            random.Random(args.seed + attempts),
            None,
            answer_usage=dict(usage),
            max_grammar_answers=99,
            grammar_answers=set(),
            max_seconds=min(
                max(args.seconds_per_shape, 5.0),
                max(0.05, args.seconds - (time.monotonic() - started)),
            ),
            node_limit=20_000_000,
            require_image=args.minimum_images > 0,
            minimum_images=args.minimum_images,
            prefer_constraint_support=True,
            constraint_support_bucket_size=2,
            branching_strategy=args.branching_strategy,
            quality_scores=quality_scores,
            solution_limit=args.solution_candidates,
            telemetry=telemetry,
        )
        last_telemetry = telemetry
        if result is None:
            continue
        mapping = result if isinstance(result, dict) else dict(enumerate(result))
        if len(mapping) != len(slots):
            continue
        solution = mapping
        selected = clues, raw_slots, slots, audit
        source_shape_id = source_id
        break
    while (
        not args.random_only
        and not args.fixed_shape_only
        and solution is None
        and time.monotonic() - started < args.seconds
    ):
        attempts += 1
        candidate = mutated_catalog_shape_candidate(rng, base_shapes, attempts)
        if candidate is None:
            continue
        source_id, clues, raw_slots, slots, audit, added = candidate
        if any(not words_by_length.get(slot.length) for slot in slots):
            continue
        valid_shapes += 1
        telemetry = {}
        result = fill_bitset(
            slots,
            indexes,
            random.Random(args.seed + attempts),
            None,
            answer_usage=dict(usage),
            max_grammar_answers=99,
            grammar_answers=set(),
            max_seconds=min(
                args.seconds_per_shape,
                max(0.05, args.seconds - (time.monotonic() - started)),
            ),
            node_limit=8_000_000,
            require_image=args.minimum_images > 0,
            minimum_images=args.minimum_images,
            prefer_constraint_support=True,
            constraint_support_bucket_size=2,
            branching_strategy=args.branching_strategy,
            quality_scores=quality_scores,
            solution_limit=args.solution_candidates,
            telemetry=telemetry,
        )
        last_telemetry = telemetry
        if result is None:
            continue
        mapping = result if isinstance(result, dict) else dict(enumerate(result))
        if len(mapping) != len(slots):
            continue
        solution = mapping
        selected = clues, raw_slots, slots, audit
        source_shape_id = f"{source_id}+{len(added)}-pivots"
        break
    while not args.fixed_shape_only and time.monotonic() - started < args.seconds:
        if solution is not None:
            break
        attempts += 1
        candidate = shape_candidate(rng, attempts)
        if candidate is None:
            continue
        clues, raw_slots, slots, audit = candidate
        if any(not words_by_length.get(slot.length) for slot in slots):
            continue
        valid_shapes += 1
        telemetry: dict = {}
        result = fill_bitset(
            slots,
            indexes,
            random.Random(args.seed + attempts),
            None,
            answer_usage=dict(usage),
            max_grammar_answers=99,
            grammar_answers=set(),
            max_seconds=min(
                args.seconds_per_shape,
                max(0.05, args.seconds - (time.monotonic() - started)),
            ),
            node_limit=8_000_000,
            require_image=args.minimum_images > 0,
            minimum_images=args.minimum_images,
            prefer_constraint_support=True,
            constraint_support_bucket_size=2,
            branching_strategy=args.branching_strategy,
            quality_scores=quality_scores,
            solution_limit=args.solution_candidates,
            telemetry=telemetry,
        )
        last_telemetry = telemetry
        if result is None:
            continue
        mapping = result if isinstance(result, dict) else dict(enumerate(result))
        if len(mapping) != len(slots):
            continue
        solution = mapping
        selected = clues, raw_slots, slots, audit
        break

    payload = {
        "version": 1,
        "kind": "owner-directed-flexible-common-word-grid",
        "columns": COLUMNS,
        "rows": ROWS,
        "fixedRules": {
            "topRowAllClueCells": True,
            "leftColumnAllClueCells": True,
            "interiorFree": True,
            "maximumTwoLetterAnswers": args.maximum_two_letter,
        },
        "replacementExclusions": {
            "references": [str(path) for path in args.exclude_from],
            "answerCount": len(excluded),
            "familyCount": len(excluded_families),
        },
        "catalogModified": False,
        "publicationEligible": False,
        "minimumZipf": None if large_wordlist is not None else args.minimum_zipf,
        "minimumConstructorScore": (
            args.minimum_constructor_score if large_wordlist is not None else None
        ),
        "solutionCandidatesRequested": args.solution_candidates,
        "qualityModel": {
            "frequencyBase": (
                "Morphalou/Lexique lexical score"
                if large_wordlist is not None
                else "wordfreq Zipf or central-corpus frequency"
            ),
            "reviewedDefinitionBackedBonus": (
                0.0 if large_wordlist is not None else 0.75
            ),
            "reviewedCandidates": reviewed_candidate_count,
            "constructorWordlist": constructor_wordlist,
            "selectionOrder": [
                "fewest active-catalog answers",
                "lowest worst active-use count",
                "best weakest answer quality",
                "best total answer quality"
            ]
        },
        "candidateCounts": {
            str(length): len(words) for length, words in words_by_length.items()
        },
        "attempts": attempts,
        "validShapesTried": valid_shapes,
        "complete": solution is not None,
        "lastTelemetry": last_telemetry,
        "grid": None,
    }
    if solution is not None and selected is not None:
        clues, raw_slots, slots, audit = selected
        answers = [
            {
                "slotIndex": index,
                "slotId": slots[index].slot_id,
                "direction": slots[index].direction,
                "clueCell": list(slots[index].clue_cell),
                "cells": [list(cell) for cell in slots[index].cells],
                "answer": answer,
                "spelling": spellings[answer],
                "zipf": None if large_wordlist is not None else scores[answer],
                "constructorScore": (
                    scores[answer] if large_wordlist is not None else quality_scores[answer]
                ),
                "qualityScore": quality_scores[answer],
                "activeUses": usage[answer],
            }
            for index, answer in sorted(solution.items())
        ]
        payload["grid"] = {
            "id": f"common-flex-{args.seed}",
            "sourceShapeGridId": source_shape_id,
            "clueCells": [list(cell) for cell in sorted(clues)],
            "internalClueCells": [
                list(cell) for cell in sorted(clues - FRAME)
            ],
            "lengthDistribution": dict(
                sorted(Counter(len(item["answer"]) for item in answers).items())
            ),
            "geometryAudit": audit,
            "rawSlots": raw_slots,
            "answers": answers,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "complete": payload["complete"],
        "attempts": attempts,
        "validShapesTried": valid_shapes,
        "answers": (
            [item["answer"] for item in payload["grid"]["answers"]]
            if payload["grid"] else None
        ),
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if solution is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
