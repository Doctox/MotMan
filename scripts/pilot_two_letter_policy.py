"""Human-reviewed two-letter policy for unpublished 7x8 pilots.

Two-letter entries are a deliberately small topology relief valve.  The
general lexicons must never enlarge this set implicitly: every accepted form
is listed here because it can be clued as a complete, familiar answer.
"""
from __future__ import annotations


MINIMUM_TWO_LETTER_ANSWERS = 1
MAXIMUM_TWO_LETTER_ANSWERS = 2

# The values document the intended, non-fragmentary reading.  Individual grid
# clues may be worded differently, but still pass the usual semantic review.
PILOT_TWO_LETTER_WHITELIST = {
    "AN": "Année",
    "AS": "Champion",
    "BD": "Bande dessinée",
    "DJ": "Aux platines",
    "IA": "Intelligence artificielle",
    "IL": "Pronom masculin",
    "ON": "Pronom indéfini",
    "OR": "Métal précieux",
    "OS": "Pièce du squelette",
    "QR": "Code à scanner",
    "UN": "Premier nombre",
    "VR": "Réalité virtuelle",
    "XP": "Points d'expérience",
}

# Les réponses lexicales et les sigles actuels portent la grille. Les trois
# formes grammaticales restent une ultime soupape de fermeture, jamais un
# premier choix éditorial.
PREFERRED_TWO_LETTER_ANSWERS = {
    "AN", "AS", "BD", "DJ", "IA", "OR", "OS", "QR", "VR", "XP",
}
PENALIZED_TWO_LETTER_ANSWERS = {"IL", "ON", "UN"}

assert PREFERRED_TWO_LETTER_ANSWERS | PENALIZED_TWO_LETTER_ANSWERS == set(
    PILOT_TWO_LETTER_WHITELIST
)
assert not PREFERRED_TWO_LETTER_ANSWERS & PENALIZED_TWO_LETTER_ANSWERS


def is_reviewed_two_letter_answer(answer: str) -> bool:
    return answer.upper() in PILOT_TWO_LETTER_WHITELIST


def valid_two_letter_answer_count(count: int) -> bool:
    return MINIMUM_TWO_LETTER_ANSWERS <= count <= MAXIMUM_TWO_LETTER_ANSWERS
