#!/usr/bin/env python3
"""Search varied 7x8 fills from the reviewed central corpus, with bounded telemetry."""

from __future__ import annotations

import argparse
import gzip
import itertools
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

from wordfreq import iter_wordlist, zipf_frequency

from bitset_grid_filler import fill_bitset
from build_compact_7x8_review import family_key_from_parts
from editorial_fill_quality import (
    DEFAULT_MINIMUM_ENTRY_SCORE,
    DEFAULT_PRESENTATION_ENTRY_SCORE,
    answer_usage,
    grid_interest_metrics,
    rescore_entries,
)
from search_compact_grid_pilot import OWNER_SHORT, build_slots, normalized


ROOT = Path(__file__).resolve().parents[1]
POP_CLUES = {
    "ALICE": "Au pays des merveilles",
    "ARIEL": "Petite sirène",
    "ANNA": "Sœur d'Elsa",
    "AVATAR": "Image de profil",
    "BATMAN": "Héros de Gotham",
    "BLOC": "Brique de Minecraft",
    "BOWSER": "Ennemi de Mario",
    "CLAN": "Équipe de joueurs",
    "DOBBY": "Elfe de Harry Potter",
    "ELSA": "Reine des neiges",
    "EMOJI": "Petit pictogramme",
    "GROGU": "Compagnon du Mandalorien",
    "GOTHAM": "Ville de Batman",
    "GAMER": "Joueur passionné",
    "MARIO": "Plombier de Nintendo",
    "HARRY": "Prénom de Potter",
    "KIRBY": "Boule rose",
    "KPOP": "Pop coréenne",
    "LEGO": "Briques à assembler",
    "LILO": "Amie de Stitch",
    "LINK": "Héros de Zelda",
    "LUIGI": "Frère de Mario",
    "LUFFY": "Pirate au chapeau",
    "MANGA": "BD japonaise",
    "MARVEL": "Maison des Avengers",
    "NARUTO": "Ninja de Konoha",
    "NINJA": "Combattant de Naruto",
    "OLAF": "Bonhomme de neige",
    "ROBLOX": "Plateforme de jeux",
    "SIMBA": "Lion de Disney",
    "SONIC": "Hérisson bleu",
    "STITCH": "Alien bleu de Disney",
    "VAIANA": "Héroïne du Pacifique",
    "VENOM": "Ennemi de Spider-Man",
    "ZELDA": "Princesse de Nintendo",
    "MICKEY": "Souris de Disney",
    "MINNIE": "Amie de Mickey",
    "TINTIN": "Ami de Milou",
    "POTTER": "Sorcier à lunettes",
    "POPPINS": "Nounou nommée Mary",
    "PIKACHU": "Pokémon jaune",
    "PEACH": "Princesse de Mario",
    "PIECE": "Monnaie de Mario",
    "SACHA": "Dresseur de Pikachu",
    "SKIN": "Apparence dans un jeu",
    "STEVE": "Héros de Minecraft",
    "STICKER": "Autocollant numérique",
    "STREAM": "Diffusion en direct",
    "TAILS": "Ami de Sonic",
    "TIKTOK": "Réseau de vidéos",
    "MUFASA": "Père de Simba",
    "BARBIE": "Poupée de Mattel",
    "CREEPER": "Monstre de Minecraft",
    "GROOT": "Arbre des Gardiens",
    "INOXTAG": "Youtubeur de Kaizen",
    "MATRIX": "Film à pilule rouge",
    "NEVILLE": "Ami de Harry Potter",
    "NEMO": "Poisson-clown de Pixar",
    "NETFLIX": "Plateforme au N rouge",
    "PIXAR": "Studio de Toy Story",
    "SHREK": "Ogre vert",
    "SPOTIFY": "Appli de musique",
    "SQUEEZIE": "Créateur du GP Explorer",
    "TWITCH": "Plateforme de streams",
    "VADOR": "Seigneur Sith",
    "YODA": "Maître Jedi",
    "YOUTUBE": "Site de vidéos",
    "LIVE": "Direct en ligne",
    "MEME": "Image virale",
    "PODCAST": "Émission à écouter",
    "SELFIE": "Photo de soi",
    "VLOG": "Journal en vidéo",
    "LOL": "Jeu de Riot",
    "MAP": "Carte de jeu",
}
GRAMMAR_ANSWERS = {
    "AU", "CA", "CE", "CES", "CET", "DE", "DU", "ELLE", "EN", "ES",
    "ET", "EU", "EUX", "IL", "ILS", "JE", "LA", "LE", "LES", "LUI",
    "MA", "ME", "MOI", "NE", "NI", "ON", "OU", "QUE", "QUI", "SA",
    "SE", "SI", "SOI", "SON", "TA", "TE", "TOI", "TON", "TU", "UN",
    "UNE", "VOS",
}
AVOID = {
    "SARCLE", "NIERA",
    "AN", "ANS", "AME", "AMES", "AMAS", "BOL", "FER", "ILE", "ILES", "MER", "MUR", "SEL",
    "SET", "SEC", "NETS", "MIG", "TIG", "UT", "PI", "RU", "LU", "PS", "GI",
    "ALLAH", "ALLAHU", "CORAN", "DJIHAD", "HARAM", "HITLER", "IMAM", "ISLAM", "LENNON", "NAZI", "NAZIS",
    "AXELLE", "EAGLES", "ELAVES", "ETERNAL", "ISLE", "LIEUS", "ODON", "PEEL",
    "AGAINST", "ALONE", "CERE", "COLD", "ISABEAU", "NAEVUS", "NAIL", "PARMIS",
    "ANGRY", "AVALAI", "EPOUSA", "FRAPPA", "MAIE", "PENN", "PIETRO", "PLON", "PU",
    "ASSURA", "ECARTA", "EMMENA", "EVENTAS", "ILIENNE", "RESISTA", "SALOPE", "SERINEE",
    "ECUMAI", "EGEENS", "FIT", "HERE", "MONTRA", "MU", "NINE", "OLEINES",
    "ACHETA", "ADAMA", "ALISE", "DIAPRER", "EIDERS", "ELAINE", "HUNGER",
    "ESSART", "ETEULES", "EVEN", "LARRON", "LEAD", "OULD", "SELLER", "STEAMER",
    "STREET", "TAPETTE", "TERGAL", "TERM", "TINT", "TINTO", "TRAORE", "TRIERE",
    "USUS", "VIET", "VS", "WEBSITE", "XL",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", type=int, default=20)
    parser.add_argument("--attempts", type=int, default=240)
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--shape-seconds", type=float, default=1.2)
    parser.add_argument("--seed", type=int, default=719900)
    parser.add_argument("--exclude-catalog", type=Path, action="append", default=[])
    parser.add_argument(
        "--allow-repeat-answer",
        action="append",
        default=[],
        help=(
            "Réponse courte explicitement réutilisable malgré le catalogue exclu. "
            "La blacklist et la liste AVOID restent toujours prioritaires."
        ),
    )
    parser.add_argument(
        "--allow-active-answer-max-length",
        type=int,
        default=0,
        help=(
            "Option retirée : les répétitions automatiques du catalogue actif "
            "sont désormais interdites."
        ),
    )
    parser.add_argument("--pop-target", type=int, default=4)
    parser.add_argument("--pop-answer", action="append", default=[])
    parser.add_argument("--require-pop", action="store_true")
    parser.add_argument("--wordfreq-minimum", type=float, default=2.4)
    parser.add_argument(
        "--lexicon-scope",
        choices=("central", "central-large", "central-hybrid", "lexical-full", "full"),
        default="lexical-full",
        help=(
            "central: couples relus seulement; central-large: ajoute les lemmes "
            "attestés; central-hybrid: ajoute les flexions françaises fréquentes; "
            "full: ajoute aussi wordfreq pour le placement."
        ),
    )
    parser.add_argument("--minimum-answers", type=int, default=13)
    parser.add_argument("--maximum-answers", type=int, default=22)
    parser.add_argument("--maximum-short-slots", type=int, default=6)
    parser.add_argument("--maximum-two-letter-slots", type=int, default=2)
    parser.add_argument("--maximum-grammar-answers", type=int, default=2)
    parser.add_argument("--maximum-undesirable-answers", type=int, default=0)
    parser.add_argument("--shape-pool-size", type=int, default=200)
    parser.add_argument("--shape-sampling-attempts", type=int, default=5_000)
    parser.add_argument(
        "--branching-strategy",
        choices=("slot", "cell"),
        default="slot",
        help="Stratégie CSP; slot/MRV est la voie stable, cell reste expérimentale.",
    )
    parser.add_argument(
        "--minimum-entry-score",
        type=float,
        default=DEFAULT_MINIMUM_ENTRY_SCORE,
        help="Score éditorial minimal (0-100) avant admission dans le solveur.",
    )
    parser.add_argument(
        "--minimum-engaging-answers",
        type=int,
        default=3,
        help="Nombre minimal de réponses longues, fortes ou pop par grille.",
    )
    parser.add_argument(
        "--minimum-presentation-entry-score",
        type=float,
        default=DEFAULT_PRESENTATION_ENTRY_SCORE,
        help="Score minimal réellement autorisé dans une grille présentée.",
    )
    parser.add_argument(
        "--maximum-adjacent-clue-pairs",
        type=int,
        default=3,
        help="Nombre maximal de voisinages directs entre cases-définition internes.",
    )
    parser.add_argument(
        "--solution-limit",
        type=int,
        default=256,
        help="Nombre maximal de fermetures propres comparÃ©es par silhouette.",
    )
    return parser.parse_args()


def excluded_answers(paths: list[Path]) -> set[str]:
    result = set(AVOID)
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        grids = document.get("grids")
        if not isinstance(grids, list):
            grids = [document.get("grid") or document]
        for grid in grids:
            for item in grid.get("words") or grid.get("answers") or []:
                answer = normalized(str(item.get("answer", "")))
                if answer:
                    result.add(answer)
    return result


def central_index(
    excluded: set[str], wordfreq_minimum: float, lexicon_scope: str,
    minimum_entry_score: float = DEFAULT_MINIMUM_ENTRY_SCORE,
) -> tuple[tuple, dict[str, dict], dict[str, set[str]], dict[str, str]]:
    with gzip.open(ROOT / "src/data/fill.wordlist.large.json.gz", "rt", encoding="utf-8") as stream:
        lexical_entries = json.load(stream).get("entries", [])
    lexical = {}
    lexical_family_lookup: dict[str, tuple[str, str]] = {}
    all_families: dict[str, str] = {}
    for item in lexical_entries:
        answer = normalized(str(item.get("answer", "")))
        if answer and answer not in lexical:
            lexical[answer] = item
            lexical_family_lookup[answer] = (
                normalized(str(item.get("lemma") or answer)),
                str(item.get("partOfSpeech") or ""),
            )
    for answer, item in lexical.items():
        lemma, part_of_speech = lexical_family_lookup[answer]
        all_families[answer] = family_key_from_parts(
            answer, lemma, part_of_speech, lexical_family_lookup
        )

    with gzip.open(ROOT / "src/data/crossword.central.json.gz", "rt", encoding="utf-8") as stream:
        entries = json.load(stream).get("entries", [])
    by_length: dict[int, list[str]] = defaultdict(list)
    scores: dict[str, float] = {}
    families: dict[str, str] = {}
    metadata: dict[str, dict] = {}
    image_document = json.loads(
        (ROOT / "src/data/crossword.images-reviewed.json").read_text(encoding="utf-8")
    )
    images = {normalized(str(item.get("answer", ""))) for item in image_document.get("entries", [])}
    for item in entries:
        answer = normalized(str(item.get("answer", "")))
        if (
            not 2 <= len(answer) <= 7
            or answer in excluded
            or answer in scores
            or item.get("generatorEligible") is not True
            or item.get("canonicalForGenerator") is not True
        ):
            continue
        lexical_item = lexical.get(answer, {})
        spelling = str(lexical_item.get("spelling") or answer.lower())
        lemma = normalized(str(lexical_item.get("lemma") or answer))
        zipf = float(zipf_frequency(spelling, "fr"))
        editorial_frequency = float(item.get("frequency", 0.0))
        scores[answer] = 20.0 + editorial_frequency + min(6.0, zipf)
        families[answer] = family_key_from_parts(
            answer,
            lemma,
            str(lexical_item.get("partOfSpeech") or ""),
            lexical_family_lookup,
        )
        all_families.setdefault(answer, families[answer])
        by_length[len(answer)].append(answer)
        metadata[answer] = {
            "spelling": spelling,
            "lemma": lemma,
            "wordfreqZipf": zipf,
            "centralClue": item.get("clue", ""),
            "sourceClue": item.get("sourceClue", ""),
            "sourceId": item.get("sourceId", ""),
            "sourceUrl": item.get("sourceUrl", ""),
            "editorialStatus": item.get("editorialStatus", ""),
        }

    # Geometry may require an inflected form that has no approved definition
    # yet. Admit only attested, frequent French forms from the construction
    # lexicon; they remain explicitly owner-review-required downstream.
    for item in lexical_entries if lexicon_scope != "central" else []:
        answer = normalized(str(item.get("answer", "")))
        spelling = str(item.get("spelling") or answer.lower())
        zipf = float(zipf_frequency(spelling, "fr"))
        constructor_score = float(item.get("constructorScore", 0.0))
        source_frequency = float(item.get("sourceFrequency", 0.0))
        school_frequency = float(item.get("schoolFrequency", 0.0))
        quality_signal = (
            source_frequency >= 0.4
            or school_frequency > 0.0
            or constructor_score >= 17.0
        )
        attested_lemma = (
            item.get("attestedCommonForm") is True
            and str(item.get("partOfSpeech") or "") != "proper-noun"
            and constructor_score >= 15.0
            and quality_signal
            and zipf >= 2.4
        )
        frequent_flexion = (
            lexicon_scope in {"central-hybrid", "lexical-full", "full"}
            and zipf >= wordfreq_minimum
            and str(item.get("partOfSpeech") or "") != "proper-noun"
            and (quality_signal or lexicon_scope == "lexical-full")
        )
        if (
            not 2 <= len(answer) <= 7
            or answer in excluded
            or answer in scores
            or not (attested_lemma or frequent_flexion)
        ):
            continue
        lemma = normalized(str(item.get("lemma") or answer))
        scores[answer] = (15.0 if attested_lemma else 13.0) + min(6.0, zipf)
        families[answer] = family_key_from_parts(
            answer,
            lemma,
            str(item.get("partOfSpeech") or ""),
            lexical_family_lookup,
        )
        all_families.setdefault(answer, families[answer])
        by_length[len(answer)].append(answer)
        metadata[answer] = {
            "spelling": spelling,
            "lemma": lemma,
            "wordfreqZipf": zipf,
            "centralClue": "",
            "sourceClue": "",
            "sourceId": "motman-large-lexical-review-20260719",
            "sourceUrl": "internal://motman/lexicon/fill-wordlist-large",
            "editorialStatus": "lexical-form-owner-review-required",
        }

    for spelling in iter_wordlist("fr") if lexicon_scope == "full" else []:
        zipf = float(zipf_frequency(spelling, "fr"))
        if zipf < wordfreq_minimum:
            break
        if not spelling.isalpha():
            continue
        answer = normalized(spelling)
        if not 2 <= len(answer) <= 7 or answer in excluded or answer in scores:
            continue
        scores[answer] = 10.0 + min(6.0, zipf)
        families[answer] = family_key_from_parts(
            answer, answer, "", lexical_family_lookup
        )
        all_families.setdefault(answer, families[answer])
        by_length[len(answer)].append(answer)
        metadata[answer] = {
            "spelling": spelling,
            "lemma": answer,
            "wordfreqZipf": zipf,
            "centralClue": "",
            "sourceClue": "",
            "sourceId": "wordfreq-french-owner-review-20260719",
            "sourceUrl": "https://github.com/rspeer/wordfreq",
            "editorialStatus": "wordfreq-owner-review-required",
        }

    # The owner's short-answer vocabulary is a deliberately closed editorial
    # list.  Some canonical abbreviations (QR, WC, XL...) have no ordinary
    # dictionary POS record, so filtering the lexical source must not silently
    # remove them from the construction domain.
    for answer in OWNER_SHORT:
        if not 2 <= len(answer) <= 3 or answer in excluded:
            continue
        spelling = answer.lower()
        zipf = float(zipf_frequency(spelling, "fr"))
        by_length[len(answer)].append(answer)
        existing_status = str(metadata.get(answer, {}).get("editorialStatus") or "")
        if existing_status not in {
            "source-backed", "human-reviewed", "image-reviewed", "owner-approved",
        }:
            scores[answer] = 18.0 + min(6.0, zipf)
            families[answer] = family_key_from_parts(
                answer, answer, "", lexical_family_lookup
            )
            all_families.setdefault(answer, families[answer])
            metadata[answer] = {
                "spelling": spelling,
                "lemma": answer,
                "wordfreqZipf": zipf,
                "centralClue": "",
                "sourceClue": "",
                "sourceId": "motman-owner-short-vocabulary-20260719",
                "sourceUrl": "internal://motman/editorial/owner-short-vocabulary",
                "editorialStatus": "owner-short-review-required",
            }

    for answer, clue in POP_CLUES.items():
        if answer in excluded:
            continue
        by_length[len(answer)].append(answer)
        scores[answer] = 40.0
        families[answer] = family_key_from_parts(
            answer, answer, "", lexical_family_lookup
        )
        all_families.setdefault(answer, families[answer])
        metadata[answer] = {
            "spelling": answer.title(),
            "lemma": answer,
            "wordfreqZipf": float(zipf_frequency(answer.lower(), "fr")),
            "centralClue": clue,
            "sourceClue": clue,
            "sourceId": "motman-pop-culture-owner-policy-20260719",
            "sourceUrl": "internal://motman/editorial/pop-culture",
            "editorialStatus": "owner-policy-review-required",
        }
    scores = rescore_entries(
        scores,
        metadata,
        grammar_answers=GRAMMAR_ANSWERS,
        pop_answers=set(POP_CLUES),
    )
    admitted = {
        answer for answer, score in scores.items()
        if score >= minimum_entry_score
    }
    scores = {answer: score for answer, score in scores.items() if answer in admitted}
    metadata = {
        answer: {**item, "editorialFillScore": scores[answer]}
        for answer, item in metadata.items()
        if answer in admitted
    }
    families = {answer: family for answer, family in families.items() if answer in admitted}
    # Keep only the owner's closed short-answer vocabulary even if a central
    # source contains a less playable crossword abbreviation.
    for length in (2, 3):
        by_length[length] = [
            answer for answer in by_length[length]
            if answer in OWNER_SHORT and answer in admitted
        ]
    by_length = {
        length: sorted(set(answers) & admitted)
        for length, answers in by_length.items()
    }
    indexes = (
        by_length,
        None,
        scores,
        families,
        {answer: set() for answer in scores},
        {answer: "normal" for answer in scores},
        images & set(scores),
    )
    family_answers: dict[str, set[str]] = defaultdict(set)
    for answer, family in families.items():
        family_answers[family].add(answer)
    return indexes, metadata, family_answers, all_families


def candidate_pivots(rng: random.Random) -> list[tuple[int, int]]:
    cells = [(row, column) for row in range(2, 7) for column in range(2, 6)]
    rng.shuffle(cells)
    count = rng.choices((1, 2, 3, 4), weights=(1, 5, 5, 2), k=1)[0]
    chosen: list[tuple[int, int]] = []
    for cell in cells:
        # At most one direct adjacency keeps definition clusters readable.
        adjacent = sum(abs(cell[0] - other[0]) + abs(cell[1] - other[1]) == 1 for other in chosen)
        if adjacent and any(
            abs(other[0] - previous[0]) + abs(other[1] - previous[1]) == 1
            for other, previous in itertools.combinations(chosen, 2)
        ):
            continue
        chosen.append(cell)
        if len(chosen) == count:
            break
    return sorted(chosen)


def expand_unavailable_by_family(
    unavailable: set[str],
    all_families: dict[str, str],
    family_answers: dict[str, set[str]],
) -> set[str]:
    """Block every available form sharing a known lemma with an old answer."""
    expanded = set(unavailable)
    for answer in tuple(unavailable):
        family = all_families.get(answer, answer)
        expanded.update(family_answers.get(family, set()))
    return expanded


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    rng = random.Random(args.seed)
    if args.allow_active_answer_max_length:
        raise ValueError(
            "--allow-active-answer-max-length a été retiré : une réponse active "
            "ne peut plus être réautorisée automatiquement."
        )
    active_usage = answer_usage(args.exclude_catalog)
    unavailable = excluded_answers(args.exclude_catalog)
    blacklist = json.loads((ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8"))
    unavailable.update(blacklist.get("rejectedAnswers", []))
    unavailable.update(
        item.get("answer", "") if isinstance(item, dict) else str(item)
        for item in blacklist.get("rotationCooldownAnswers", [])
    )
    blocked_by_policy = set(AVOID)
    blocked_by_policy.update(blacklist.get("rejectedAnswers", []))
    blocked_by_policy.update(
        item.get("answer", "") if isinstance(item, dict) else str(item)
        for item in blacklist.get("rotationCooldownAnswers", [])
    )
    allowed_repeats = {
        normalized(answer)
        for answer in args.allow_repeat_answer
        if normalized(answer) and normalized(answer) not in blocked_by_policy
    }
    unavailable.difference_update(allowed_repeats)
    unavailable.discard("")
    indexes, metadata, family_answers, all_families = central_index(
        unavailable,
        args.wordfreq_minimum,
        args.lexicon_scope,
        args.minimum_entry_score,
    )
    index_ready_at = time.monotonic()
    families = indexes[3]
    unavailable = expand_unavailable_by_family(
        unavailable,
        {**families, **all_families},
        family_answers,
    )
    unavailable_family_keys = {
        families.get(answer, all_families.get(answer, answer))
        for answer in unavailable
    }

    current_document = json.loads(args.exclude_catalog[0].read_text(encoding="utf-8")) if args.exclude_catalog else {}
    # A validated geometry may be reused once with an entirely new fill. The
    # batch still forbids duplicate shapes among its own new grids.
    seen_shapes: set[tuple[tuple[int, int], ...]] = set()
    accepted = []
    rejection_counts: dict[str, int] = defaultdict(int)
    pop_cycle = [normalized(answer) for answer in args.pop_answer] or list(POP_CLUES)
    unknown_pop = sorted(set(pop_cycle) - set(POP_CLUES))
    if unknown_pop:
        raise ValueError(f"Références pop inconnues: {unknown_pop}")
    rng.shuffle(pop_cycle)
    pop_count = 0

    pivot_cells = [(row, column) for row in range(1, 8) for column in range(1, 7)]
    valid_shapes: list[tuple[list[tuple[int, int]], list[list[int]], list[dict], list]] = []
    valid_shape_fingerprints: set[tuple[tuple[int, int], ...]] = set()

    def admit_shape(combination: list[tuple[int, int]]) -> None:
        try:
            clue_cells, raw_slots, slots = build_slots(7, 8, set(combination))
        except ValueError:
            return
        lengths = [len(slot.cells) for slot in slots]
        fingerprint = tuple(sorted(tuple(cell) for cell in clue_cells))
        if (
            fingerprint in valid_shape_fingerprints
            or lengths.count(2) > args.maximum_two_letter_slots
            or sum(length <= 3 for length in lengths) > args.maximum_short_slots
            or len(slots) < args.minimum_answers
            or len(slots) > args.maximum_answers
            or any(length not in indexes[0] or not indexes[0][length] for length in lengths)
        ):
            return
        valid_shape_fingerprints.add(fingerprint)
        valid_shapes.append((list(combination), clue_cells, raw_slots, slots))

    # Professional constructor software works from reusable pattern libraries.
    # Start with MotMan's owner-approved 7x8 silhouettes, but give them entirely
    # fresh answers; random geometry remains a secondary source of variety.
    template_pivots = [
        sorted(
            (int(row), int(column))
            for row, column in grid.get("clueCells", [])
            if int(row) > 0 and int(column) > 0
        )
        for grid in current_document.get("grids", [])
        if grid.get("columns") == 7 and grid.get("rows") == 8
    ]
    rng.shuffle(template_pivots)
    for combination in template_pivots:
        admit_shape(combination)

    shape_sampling_started_at = time.monotonic()
    for _shape_attempt in range(args.shape_sampling_attempts):
        # The owner-approved compact grids mostly use one to three internal
        # double-clue cells.  More pivots create a thicket of 2/3-letter glue.
        count = rng.choices((1, 2, 3, 4), weights=(2, 7, 6, 2), k=1)[0]
        combination = sorted(rng.sample(pivot_cells, count))
        adjacent_pairs = sum(
            abs(first[0] - second[0]) + abs(first[1] - second[1]) == 1
            for first, second in itertools.combinations(combination, 2)
        )
        if adjacent_pairs > args.maximum_adjacent_clue_pairs:
            continue
        admit_shape(combination)
        if len(valid_shapes) >= args.shape_pool_size:
            break
    rng.shuffle(valid_shapes)
    valid_shapes.sort(key=lambda item: (
        sum(len(slot.cells) == 2 for slot in item[3]),
        sum(len(slot.cells) <= 3 for slot in item[3]),
        -sum(len(slot.cells) >= 5 for slot in item[3]),
    ))
    fill_started_at = time.monotonic()

    for attempt in range(args.attempts):
        if len(accepted) >= args.target or time.monotonic() - started >= args.seconds:
            break
        if attempt >= len(valid_shapes):
            rejection_counts["shape-pool-exhausted"] += 1
            break
        pivots, clue_cells, raw_slots, slots = valid_shapes[attempt]
        fingerprint = tuple(sorted(tuple(cell) for cell in clue_cells))
        if fingerprint in seen_shapes:
            rejection_counts["duplicate-shape"] += 1
            continue

        fixed_variants: list[dict[int, str]] = [{}]
        if pop_count < args.pop_target:
            # Do not retry the same impossible anchor on every silhouette.
            # Cycling by attempt lets each well-known reference meet several
            # different slot patterns while keeping the requested batch quota.
            pop_answer = pop_cycle[attempt % len(pop_cycle)]
            matching = [index for index, slot in enumerate(slots) if len(slot.cells) == len(pop_answer)]
            rng.shuffle(matching)
            fixed_variants = [{index: pop_answer} for index in matching[:12]]
            if not args.require_pop:
                fixed_variants.append({})

        solution = None
        telemetry = {}
        fixed_used: dict[int, str] = {}
        for fixed in fixed_variants:
            telemetry = {}
            solution = fill_bitset(
                slots,
                indexes,
                rng,
                None,
                unavailable_answers=unavailable,
                answer_usage=active_usage,
                max_grammar_answers=args.maximum_grammar_answers,
                grammar_answers=GRAMMAR_ANSWERS,
                max_seconds=args.shape_seconds,
                node_limit=3_000_000,
                require_image=False,
                fixed_answers=fixed,
                prefer_constraint_support=True,
                constraint_support_bucket_size=3,
                branching_strategy=args.branching_strategy,
                quality_scores=indexes[2],
                answer_families=families,
                undesirable_answers={
                    answer for answer, item in metadata.items()
                    if (
                        item.get("wordfreqZipf", 0.0) < 2.2
                        or indexes[2].get(answer, 0.0) < args.minimum_presentation_entry_score
                    )
                    and answer not in POP_CLUES
                },
                max_undesirable_answers=args.maximum_undesirable_answers,
                solution_limit=args.solution_limit,
                explore_randomly=True,
                telemetry=telemetry,
            )
            if solution is not None:
                fixed_used = fixed
                break
        if solution is None:
            rejection_counts[f"fill-{telemetry.get('reason', 'failed')}"] += 1
            continue

        answers = []
        answer_values = []
        for index in sorted(solution):
            answer = solution[index]
            answer_values.append(answer)
            answers.append({"slotIndex": index, "answer": answer, **metadata[answer]})
        solution_family_keys = [families.get(answer, answer) for answer in answer_values]
        if len(set(solution_family_keys)) != len(answer_values):
            rejection_counts["family-repeat"] += 1
            continue
        if set(solution_family_keys) & unavailable_family_keys:
            rejection_counts["family-repeat-external"] += 1
            continue
        interest = grid_interest_metrics(
            answer_values,
            indexes[2],
            grammar_answers=GRAMMAR_ANSWERS,
            pop_answers=set(POP_CLUES),
        )
        if interest["weakestEntryScore"] < args.minimum_presentation_entry_score:
            rejection_counts["entry-below-presentation-score"] += 1
            continue
        if interest["engagingAnswerCount"] < args.minimum_engaging_answers:
            rejection_counts["not-enough-engaging-answers"] += 1
            continue
        accepted.append({
            "id": f"compact-7x8-batch-raw-{len(accepted) + 1:02d}",
            "columns": 7,
            "rows": 8,
            "sourceShapeId": "compact-7x8-" + "-".join(f"pivot-{r}-{c}" for r, c in pivots),
            "clueCells": clue_cells,
            "rawSlots": raw_slots,
            "answers": answers,
            "fixedPopAnswer": next(iter(fixed_used.values()), None),
            "editorialQuality": interest,
            "solverTelemetry": telemetry,
        })
        seen_shapes.add(fingerprint)
        if fixed_used:
            pop_count += 1
        for answer in answer_values:
            unavailable.update(family_answers.get(families.get(answer, answer), {answer}))
        unavailable_family_keys.update(solution_family_keys)

    payload = {
        "version": 1,
        "kind": "compact-7x8-central-batch-search",
        "complete": len(accepted) >= args.target,
        "catalogModified": False,
        "publicationEligible": False,
        "attempts": args.attempts,
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "phaseSeconds": {
            "index": round(index_ready_at - started, 3),
            "shapeSampling": round(fill_started_at - shape_sampling_started_at, 3),
            "fill": round(time.monotonic() - fill_started_at, 3),
        },
        "shapePoolCount": len(valid_shapes),
        "acceptedCount": len(accepted),
        "popCultureCount": pop_count,
        "allowedRepeatAnswers": sorted(allowed_repeats),
        "lexiconScope": args.lexicon_scope,
        "editorialQualityPolicy": {
            "minimumEntryScore": args.minimum_entry_score,
            "minimumPresentationEntryScore": args.minimum_presentation_entry_score,
            "minimumEngagingAnswers": args.minimum_engaging_answers,
            "automaticActiveRepeatsAllowed": False,
        },
        "shapePolicy": {
            "minimumAnswers": args.minimum_answers,
            "maximumAnswers": args.maximum_answers,
            "maximumShortSlots": args.maximum_short_slots,
            "maximumTwoLetterSlots": args.maximum_two_letter_slots,
        },
        "rejectionCounts": dict(sorted(rejection_counts.items())),
        "grids": accepted,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "complete": payload["complete"],
        "acceptedCount": len(accepted),
        "popCultureCount": pop_count,
        "elapsedSeconds": payload["elapsedSeconds"],
        "rejectionCounts": payload["rejectionCounts"],
        "answers": [[item["answer"] for item in grid["answers"]] for grid in accepted],
    }, ensure_ascii=False, indent=2))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
