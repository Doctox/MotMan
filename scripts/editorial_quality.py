"""Deterministic editorial gates shared by corpus indexing and catalog audit."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path


# These forms are grammatical only in a context that the answer cannot carry
# (for example BEL must precede a masculine noun beginning with a vowel).
FORBIDDEN_STANDALONE_FORMS = {"BEL"}
FORBIDDEN_CLUE_PUNCTUATION = re.compile(r"(?:\.{2,}|/|[()])")
ROMAN_LETTERS = set("IVXLCDM")
FRENCH_NUMBERS = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
    "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
    "dix sept": 17, "dix huit": 18, "dix neuf": 19, "vingt": 20,
}
PILOT_REVIEW_FLAGS = (
    "semanticFit",
    "grammaticalFit",
    "unambiguous",
    "answerNotRevealed",
    "languageAcceptable",
    "allAudience",
)
PILOT_LANGUAGE_STATUSES = {"french", "common-anglicism", "known-proper-name"}
PILOT_CULTURAL_STATUSES = {"everyday", "current-pop", "general-culture", "none"}
PILOT_CLUE_STYLES = {"direct", "clever", "image"}


def normalize_text(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def _inflection_signature(clue: str) -> tuple[str, ...]:
    """Reduce a short clue to a cautious singular/plural comparison key."""
    words = re.findall(r"[a-z]+", fold(clue))
    return tuple(
        word[:-1] if len(word) > 3 and word.endswith("s") else word
        for word in words
    )


def roman_to_int(value: str) -> int | None:
    if not value or any(letter not in ROMAN_LETTERS for letter in value):
        return None
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    previous = 0
    for letter in reversed(value):
        current = values[letter]
        total += -current if current < previous else current
        previous = max(previous, current)
    return total


def int_to_roman(value: int) -> str:
    if not 1 <= value <= 3999:
        return ""
    result = []
    for number, numeral in (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ):
        while value >= number:
            result.append(numeral)
            value -= number
    return "".join(result)


def _clue_number(clue: str) -> int | None:
    digit = re.search(r"(?<!\d)([1-9]\d{0,3})(?!\d)", clue)
    if digit:
        return int(digit.group(1))
    folded = re.sub(r"[^a-z]+", " ", fold(clue)).strip()
    for phrase, value in sorted(FRENCH_NUMBERS.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b{re.escape(phrase)}\b", folded):
            return value
    return None


def valid_image(image: object, root: Path | None = None) -> bool:
    if not isinstance(image, dict):
        return False
    if not all(normalize_text(image.get(field)) for field in ("asset", "alt", "source", "license")):
        return False
    asset = image["asset"]
    if root is not None and isinstance(asset, str) and asset.startswith("/"):
        return (root / "public" / asset.lstrip("/")).is_file()
    return True


def editorial_errors(item: dict, *, root: Path | None = None) -> list[dict]:
    """Validate one answer/clue item without making probabilistic judgements."""
    errors = []
    answer = normalize_text(item.get("answer")).upper()
    clue = normalize_text(item.get("clue"))
    if not clue and not valid_image(item.get("image"), root):
        errors.append({"code": "empty_clue", "message": "définition vide sans image valide"})
    if answer in FORBIDDEN_STANDALONE_FORMS:
        errors.append({
            "code": "morphological_fragment",
            "message": f"{answer} est une forme contextuelle, pas une réponse autonome",
        })
    if clue and FORBIDDEN_CLUE_PUNCTUATION.search(clue):
        errors.append({
            "code": "clue_fragment_punctuation",
            "message": "ponctuation de fragment, trou ou aparté interdite dans une définition courte",
        })
    word_count = len(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]+", clue))
    if word_count > 3:
        errors.append({
            "code": "clue_too_long",
            "message": "la définition dépasse exceptionnellement trois mots",
            "wordCount": word_count,
        })

    folded_clue = fold(clue)
    roman_context = "romain" in folded_clue or re.search(r"\ba rome\b", folded_clue)
    if roman_context and answer and all(letter in ROMAN_LETTERS for letter in answer):
        parsed = roman_to_int(answer)
        value = _clue_number(clue)
        if value is None:
            errors.append({
                "code": "roman_value_missing",
                "message": "la définition ne précise pas la valeur du chiffre romain",
            })
        elif parsed != value or int_to_roman(value) != answer:
            errors.append({
                "code": "roman_value_mismatch",
                "message": "la réponse n’est pas l’écriture romaine canonique de la valeur annoncée",
                "expected": int_to_roman(value),
                "value": value,
            })
        natural = bool(re.search(r"(?<!\d)[1-9]\d{0,3}\s+romain\b", folded_clue)) or "a rome" in folded_clue
        if value is not None and not natural:
            errors.append({
                "code": "roman_clue_unnatural",
                "message": "formulation attendue : « 12 romain » ou « Douze, à Rome »",
            })
    return errors


def pilot_editorial_errors(item: dict, *, root: Path | None = None) -> list[dict]:
    """Strict, auditable editorial contract for an unpublished 7×8 pilot."""
    errors = list(editorial_errors(item, root=root))
    answer = normalize_text(item.get("answer")).upper()
    clue = normalize_text(item.get("clue"))

    def reject(code: str, message: str, **details: object) -> None:
        errors.append({"code": code, "message": message, **details})

    if len(answer) < 3:
        reject("pilot_answer_too_short", "le pilote interdit toute réponse de moins de trois lettres")
    missing_sources = [
        field for field in ("sourceId", "sourceUrl", "sourceType")
        if not normalize_text(item.get(field))
    ]
    if missing_sources:
        reject(
            "pilot_missing_provenance",
            "provenance éditoriale incomplète",
            fields=missing_sources,
        )
    familiarity = item.get("familiarityScore")
    if not isinstance(familiarity, (int, float)) or isinstance(familiarity, bool) or not 0 <= familiarity <= 100:
        reject("pilot_invalid_familiarity", "familiarityScore doit être compris entre 0 et 100")
    if item.get("familiarityBand") not in {"common", "thoughtful"}:
        reject("pilot_missing_familiarity_band", "familiarityBand doit valoir common ou thoughtful")
    if not normalize_text(item.get("partOfSpeech")):
        reject("pilot_missing_part_of_speech", "nature grammaticale absente")
    if item.get("languageStatus") not in PILOT_LANGUAGE_STATUSES:
        reject("pilot_invalid_language_status", "statut de langue absent ou non autorisé")
    if item.get("culturalStatus") not in PILOT_CULTURAL_STATUSES:
        reject("pilot_invalid_cultural_status", "statut culturel absent ou non autorisé")
    if item.get("clueStyle") not in PILOT_CLUE_STYLES:
        reject("pilot_invalid_clue_style", "clueStyle doit valoir direct, clever ou image")

    review = item.get("editorialReview")
    if not isinstance(review, dict):
        reject("pilot_missing_editorial_review", "revue éditoriale structurée absente")
    else:
        failed = [flag for flag in PILOT_REVIEW_FLAGS if review.get(flag) is not True]
        if failed:
            reject(
                "pilot_editorial_review_failed",
                "un contrôle éditorial bloquant manque ou a échoué",
                flags=failed,
            )

    folded_answer = fold(answer)
    if clue and len(folded_answer) >= 4 and re.search(
        rf"\b{re.escape(folded_answer)}\b", fold(clue)
    ):
        reject("pilot_answer_revealed", "la définition révèle directement la réponse")

    if item.get("image"):
        if item.get("imageStatus") != "reviewed-recognizable-licensed":
            reject(
                "pilot_image_not_reviewed",
                "l’image doit être reconnaissable sur mobile et sa licence vérifiée",
            )
        if isinstance(review, dict) and review.get("imageRecognizable") is not True:
            reject(
                "pilot_image_not_recognizable",
                "la reconnaissabilité mobile de l’image n’est pas validée",
            )
    return errors


def grid_semantic_errors(words: list[dict]) -> list[dict]:
    """Reject duplicate concepts, without rejecting merely related vocabulary.

    ``conceptGroup`` is deliberately narrow: RAT and RATS may share ``RAT``;
    ROSE and FLEUR must keep distinct groups. ``semanticConflicts`` handles
    explicit equivalences such as AUTO/VOITURE or text/image duplicates.
    """
    errors: list[dict] = []
    by_group: dict[str, dict] = {}
    by_answer: dict[str, dict] = {}
    by_clue: dict[str, dict] = {}
    duplicate_pairs: set[tuple[str, str]] = set()

    for word in words:
        if not isinstance(word, dict):
            continue
        answer = normalize_text(word.get("answer")).upper()
        if answer:
            by_answer[answer] = word
        clue = normalize_text(word.get("clue"))
        if clue:
            clue_key = fold(clue)
            previous_clue = by_clue.get(clue_key)
            previous_answer = (
                normalize_text(previous_clue.get("answer")).upper()
                if previous_clue is not None else ""
            )
            if previous_clue is not None and previous_answer != answer:
                errors.append({
                    "code": "ambiguous_duplicate_clue",
                    "message": "la même définition ne peut pas désigner deux réponses différentes",
                    "clue": clue,
                    "answers": [previous_answer, answer],
                })
            else:
                by_clue[clue_key] = word
        group = normalize_text(word.get("conceptGroup")).upper()
        if not group:
            continue
        previous = by_group.get(group)
        if previous is not None:
            pair = tuple(sorted((
                normalize_text(previous.get("answer")).upper(), answer,
            )))
            duplicate_pairs.add(pair)
            errors.append({
                "code": "duplicate_concept",
                "message": "deux réponses représentent le même concept dans la grille",
                "conceptGroup": group,
                "answers": [
                    normalize_text(previous.get("answer")).upper(), answer,
                ],
            })
        else:
            by_group[group] = word

    # The owner treats a singular and its visible ``S`` plural as a repeated
    # answer even when a homograph could technically justify another sense.
    # Keep two-letter forms out of this mechanical rule (DO/DOS is not an
    # inflection), then reject every longer A/AS family by default.
    for singular, singular_word in by_answer.items():
        if len(singular) < 3:
            continue
        plural = f"{singular}S"
        plural_word = by_answer.get(plural)
        if plural_word is None:
            continue
        pair = tuple(sorted((singular, plural)))
        if pair in duplicate_pairs:
            continue
        duplicate_pairs.add(pair)
        errors.append({
            "code": "duplicate_inflection",
            "message": "une réponse et sa forme en S se répètent visuellement dans la grille",
            "answers": list(pair),
        })

    reported_pairs: set[tuple[str, str]] = set()
    for answer, word in by_answer.items():
        conflicts = word.get("semanticConflicts", [])
        if not isinstance(conflicts, list):
            continue
        for raw_conflict in conflicts:
            conflict = normalize_text(raw_conflict).upper()
            pair = tuple(sorted((answer, conflict)))
            if conflict in by_answer and pair not in reported_pairs:
                reported_pairs.add(pair)
                errors.append({
                    "code": "semantic_conflict",
                    "message": "deux indices donnent des réponses sémantiquement équivalentes",
                    "answers": list(pair),
                })
    return errors
