"""Solver-only French lexicon, deliberately separate from publishable clues."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def build_placement_index(generator, difficulty: str):
    document = json.loads((ROOT / "src/data/lexique.lemmas.json").read_text(encoding="utf-8"))
    child_document = json.loads(
        (ROOT / "src/data/lexique.child-forms.json").read_text(encoding="utf-8")
    )
    editorial_entries = generator.load_entries()
    curated_short = {
        entry["answer"]: entry for entry in editorial_entries
        if entry["length"] == 2
        and entry.get("editorialStatus") == "human-reviewed"
        and (
            entry.get("sourceType") == "dictionary"
            or entry.get("shortAnswerApproved") is True
        )
    }
    image_answers = {
        entry["answer"] for entry in editorial_entries if entry.get("image")
    }
    by_length = defaultdict(list)
    frequency = {}
    concept_group = {}
    semantic_conflicts = {}
    word_difficulty = {}
    blocked = (
        generator.FORBIDDEN_ANSWERS
        | generator.REJECTED_ANSWERS
        | generator.ROTATION_COOLDOWN_ANSWERS
    )
    # The reviewed central corpus is the primary reservoir.  Lexique is only
    # a crossing rescue below.  Easy mode deliberately keeps its stricter
    # child-facing word list; the broad central pool is used for the standard
    # and culturally harder placement modes.
    if difficulty != "easy":
        central = generator.build_index(
            editorial_entries,
            min_frequency=0,
            difficulty=difficulty,
            allow_dictionary_derived=False,
        )
        for length, answers in central[0].items():
            by_length[length].extend(answers)
        # A large fixed bonus makes reviewed central entries win ordering ties
        # while still letting the solver use Lexique when crossings require it.
        frequency.update({answer: value + 1000 for answer, value in central[2].items()})
        concept_group.update(central[3])
        semantic_conflicts.update(central[4])
        word_difficulty.update(central[5])
    central_answers = {
        answer for answers in by_length.values() for answer in answers
    }
    placement_entries = child_document["entries"] if difficulty == "easy" else document["entries"]
    for entry in [*placement_entries, *curated_short.values()]:
        answer = entry["answer"]
        is_curated_short = (
            len(answer) == 2
            and entry.get("editorialStatus") == "human-reviewed"
        )
        if difficulty == "easy" and not is_curated_short:
            # A child-facing answer must be a form that can be clued naturally,
            # not merely a frequent token.  Conjugated verbs (TUEZ, HAIS),
            # gendered adjective fragments (BEL, MURE) and function words made
            # the former fills technically valid but editorially absurd.
            part_of_speech = entry.get("partOfSpeech")
            lemma = entry.get("lemma", answer)
            verb_info = entry.get("verbInfo") or ""
            if part_of_speech not in {"NOM", "ADJ", "ADV", "VER"}:
                continue
            if part_of_speech == "VER" and not verb_info.startswith("inf"):
                continue
            if part_of_speech == "ADJ" and answer != lemma:
                continue
        if answer in blocked or (difficulty == "easy" and answer in generator.REJECTED_EASY_ANSWERS):
            continue
        if difficulty == "normal" and answer in generator.REJECTED_NORMAL_ANSWERS:
            continue
        if answer in central_answers:
            continue
        by_length[len(answer)].append(answer)
        source_frequency = float(entry.get("sourceFrequency", entry.get("frequency", 1)))
        frequency[answer] = math.log1p(source_frequency) + 1
        concept_group[answer] = entry.get("conceptGroup", answer)
        semantic_conflicts[answer] = set(entry.get("semanticConflicts", []))
        word_difficulty[answer] = entry.get("difficulty", "hard")
    return (
        by_length, None, frequency, concept_group, semantic_conflicts,
        word_difficulty, image_answers | (central[6] if difficulty != "easy" else set()),
    )
