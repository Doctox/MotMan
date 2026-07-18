"""Build validated Entrelignes grids offline; the app only consumes accepted grids."""
from __future__ import annotations
import argparse, gzip, json, math, random, time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from editorial_quality import editorial_errors
from bitset_grid_filler import fill_bitset
from cp_sat_grid_filler import fill_cp_sat
from grid_topology import audit_grid_topology

ROOT = Path(__file__).resolve().parents[1]
LEXICON = ROOT / "src" / "data" / "crossword.corpus.json"
CENTRAL_LEXICON = ROOT / "src" / "data" / "crossword.central.json.gz"
CURATED_LEXICON = ROOT / "src" / "data" / "crossword.curated.json"
IMAGE_LEXICON = ROOT / "src" / "data" / "crossword.images-reviewed.json"
REVIEWED_LEXICON = ROOT / "src" / "data" / "crossword.reference-reviewed.json"
CATALOG = ROOT / "src" / "data" / "grid.catalog.json"
EDITORIAL_BLACKLIST = json.loads((ROOT / "src" / "data" / "editorial.blacklist.json").read_text(encoding="utf-8"))
LEXIQUE_LEMMAS = set(json.loads(
    (ROOT / "src" / "data" / "lexique.lemmas.json").read_text(encoding="utf-8")
)["lemmas"])
REJECTED_EASY_ANSWERS = set(EDITORIAL_BLACKLIST["rejectedEasyAnswers"])
REJECTED_NORMAL_ANSWERS = set(EDITORIAL_BLACKLIST.get("rejectedNormalAnswers", []))
REJECTED_ANSWERS = set(EDITORIAL_BLACKLIST.get("rejectedAnswers", []))
ROTATION_COOLDOWN_ANSWERS = {
    item["answer"]
    for item in EDITORIAL_BLACKLIST.get("rotationCooldownAnswers", [])
}
REJECTED_PAIRS = {(item["answer"], item["clue"].casefold()) for item in EDITORIAL_BLACKLIST["rejectedPairs"]}
SIZE = 9


def load_entries(*, include_review_staging: bool = False) -> list[dict]:
    if CENTRAL_LEXICON.exists():
        with gzip.open(CENTRAL_LEXICON, "rt", encoding="utf-8") as handle:
            central = json.load(handle)
        entries = [
            entry for entry in central["entries"]
            if entry.get("canonicalForGenerator")
        ]
        if len(entries) != len({entry["answer"] for entry in entries}):
            raise ValueError("corpus central ambigu: plusieurs couples canoniques")
        return entries

    entries = json.loads(LEXICON.read_text(encoding="utf-8"))["entries"]
    curated = json.loads(CURATED_LEXICON.read_text(encoding="utf-8"))["entries"]
    image_curated = json.loads(IMAGE_LEXICON.read_text(encoding="utf-8"))["entries"]
    reviewed_document = json.loads(REVIEWED_LEXICON.read_text(encoding="utf-8"))
    defaults = reviewed_document.get("defaults", {})
    reviewed = [
        {
            **defaults,
            **entry,
            "sourceClue": entry["clue"],
            "conceptGroup": entry.get("conceptGroup", entry["answer"]),
        }
        for entry in reviewed_document["entries"]
    ]
    by_answer = {}
    by_answer.update({entry["answer"]: entry for entry in entries})
    by_answer.update({entry["answer"]: entry for entry in curated})
    by_answer.update({entry["answer"]: entry for entry in image_curated})
    for entry in reviewed:
        by_answer[entry["answer"]] = {**by_answer.get(entry["answer"], {}), **entry}
    normalized = []
    for entry in by_answer.values():
        if entry.get("image"):
            entry = {
                **entry,
                "image": {**entry["image"], "alt": entry["answer"].title()},
            }
        normalized.append(entry)
    return normalized


def audience_difficulty(entry: dict) -> str:
    """Map source force labels to MotMan's intended player audiences.

    Newspaper force levels are not vocabulary ages: many common words coming
    from force 3/4 were mechanically marked hard.  Frequency can lower a pair
    by one or two tiers, while manually reviewed dictionary additions retain
    their explicit editorial tier.
    """
    declared = entry.get("difficulty", "hard")
    if entry.get("sourceType") == "dictionary":
        return declared
    frequency = float(entry.get("frequency", 0))
    if declared == "easy" or frequency >= 4:
        return "easy"
    if declared == "normal" or frequency >= 3:
        return "normal"
    return "hard"
DIFFICULTY_RANGES = {
    # A grid keeps a clear identity while allowing nearby variations. The
    # ranges also keep the backtracker from failing on a needlessly exact %.
    "easy": {
        # "easy" means present in the Eduscol school list; "normal" here is
        # still a high-frequency Lexique word. Both pools are child-safe,
        # while the hard/rare pool remains completely forbidden.
        "easy": (.45, .60), "normal": (.40, .55), "hard": (0, 0),
    },
    "normal": {
        "easy": (.20, .35), "normal": (.50, .65), "hard": (.10, .25),
    },
    "hard": {
        "easy": (.05, .15), "normal": (.20, .35), "hard": (.55, .75),
    },
}
FORBIDDEN_ANSWERS = {
    "BORIS", "MALO", "COP", "CONDO", "CADILLAC", "IBN", "TT", "PCQ", "SS",
    "FDP", "KIL", "NUD", "GEN", "INN", "THE", "GUEST", "BOARD", "CHAN",
    "BALZAC", "BAPTISTE", "ALICE", "BENIN", "CANADA", "COLETTE",
    "RON", "LAST", "ACE", "DAKOTA", "AFTER", "ABC", "SU", "VAN", "LEU",
    "CORNER", "NU", "PAL", "DOUALA", "LOS", "DIA", "BIT",
    "STP", "OSEF", "PET", "TAIN", "ION", "ZOE", "DER", "DSL", "TEAM",
    "FOR", "OUT", "OST", "PUTE", "BENOIT", "JOB", "MAJ", "CHRIST", "BLED",
    "BOBBY", "IVE", "SVP", "ASSO", "PARA", "ALIEN", "REZ", "STEP", "FUT",
    "HON", "MT", "SAM", "AVE", "ALAN", "CHINA", "REN", "MOD", "CES", "MIL",
    "COM", "ENVI", "SAL", "TELL", "REX", "CHEAP", "CHUR", "LAPS", "VAR",
    "REM", "ISO", "GROUP", "INT", "ARS", "LEA", "FIGHT", "GUS", "LIN", "TEE",
    "JOJO", "TARA", "TAO",
    "BABY", "COLMAR", "RIO", "MAMA", "ANA", "LIV", "NAZE", "KID", "ALMA",
    "BABA", "HUE", "BREAK", "MAG", "COCA", "AKA", "AIS", "ORES", "GREEN",
    "BCP", "PITT", "CALAIS", "ADELE", "BAD", "DJIHAD",
    "BODY", "DAR", "SNOW", "QU", "AVA", "CACA", "API", "RICH", "CHO",
    "HARAM", "JEAN", "AIN", "META", "NANA", "CLOPE", "COHEN", "ARNAUD",
    "CAN", "TAF", "CONDE", "ANJOU", "DUO", "RDV", "CASH", "RAM", "CLASS",
    "CONSO", "NEO", "HAN", "ROM", "ADMIN", "GAMMA", "NORA", "SAQ", "NOVA",
    "BRO", "ARCHI", "CLASH", "AVR", "GAGA", "CREA", "ITEM",
    "LIVE", "HOC", "TRAD", "HUI", "CHI", "MAO", "MINA", "ONCE", "ETC",
    "LAI", "BLADE", "MARC", "DRIVER", "JURA", "PRO", "MARA", "DREAM",
    "ANGLO", "BARBARA", "REAL", "SAFE", "POST", "BOMBAY", "TATA", "CHANG",
    "SET", "RAS", "NES", "CHIPS", "DONG", "BEACH", "DECA", "GAME", "BING",
    "SIL", "COCKPIT", "CIE",
    "MILE", "HTTP", "ROB", "GAP", "BUF", "MEL", "SAMI", "DEF", "ALFRED",
    "CAF", "WAT", "NAT", "MRC", "NOAH", "BLOCK", "GALLO", "LEAD", "USER",
    "HERO", "HIT", "ALBIN", "CLEAN", "LORD", "POLO", "BOT", "BIP", "AUBERT",
    "OPEN", "CUP", "CAME", "INDE", "MAN", "CONF", "FAC",
    "CUR", "DOC", "CHEN", "EUH", "PAU", "SUB", "ROY", "BALI", "CHAD",
    "CHECK", "BILL", "GUN", "AUBIN", "KHAN", "BOWL", "RAZ", "BEN", "BOB",
    "TWIN", "WOW", "ACTU", "FIAT", "CAROLE", "DEL", "ALABAMA", "BUFFALO",
    "CHARIA", "TER", "BRACELET", "IN", "PU", "AL", "VIT", "CON", "KIM", "CUL",
    "DS", "DR", "GG", "EF", "OT", "AMA", "TAN", "HOMO", "TG", "DT",
}
GRAMMAR_ANSWERS = {
    "JE", "TU", "IL", "ELLE", "ON", "NOUS", "VOUS", "ILS", "ELLES",
    "MOI", "TOI", "LUI", "EUX", "ME", "TE", "SE", "LE", "LA", "LES",
    "UN", "UNE", "DU", "DE", "DES", "EN", "Y", "CE", "CET", "CES",
    "CA", "CELA", "QUI", "QUE", "QUOI", "DONT", "OU", "MON", "TON",
    "SON", "MA", "TA", "SA", "MES", "TES", "SES", "NOTRE", "VOTRE",
    "LEUR", "NOS", "VOS", "LEURS",
    "AUX", "ET", "PAR", "EST", "VA", "PUIS", "DONC", "AFIN",
}
CURATED = {
    "IA": "Intelligence artificielle", "DJ": "Aux platines", "QR": "Code carré",
    "RAP": "Musique urbaine", "WEB": "Internet", "POP": "Musique populaire",
    "APP": "Appli mobile", "GIF": "Image animée", "GEEK": "Fan de tech",
    "WIFI": "Réseau sans fil", "BLOG": "Journal en ligne", "MEME": "Blague virale",
    "CLIP": "Vidéo musicale", "LIKE": "J’aime", "MODE": "Tendance",
    "JEU": "Pour s’amuser", "PHOTO": "Prise de vue", "VIDEO": "Images animées",
    "PIXEL": "Point d’écran", "EMOJI": "Petit pictogramme", "SERIE": "Épisodes télé",
    "MANGA": "BD japonaise", "ANIME": "Dessin japonais", "ROBOT": "Machine autonome",
    "GAMER": "Joueur passionné", "VIRAL": "Très partagé", "MATCH": "Rencontre sportive",
    "SELFIE": "Autoportrait mobile", "MOBILE": "Téléphone portable", "RESEAU": "Liens connectés",
    "STREAM": "Diffusion en direct", "PODCAST": "Émission audio", "INFLUENCE": "Pouvoir d’agir",
}

@dataclass(frozen=True)
class Slot:
    direction: str
    clue: tuple[int, int]
    cells: tuple[tuple[int, int], ...]
    arrow: str = "right"

SHAPES = [
 ((0,0),(0,1),(0,2),(0,3),(0,4),(0,5),(0,6),(0,7),(0,8),(1,0),(2,0),
  (3,0),(4,0),(4,5),(5,0),(5,6),(6,0),(6,4),(7,0),(8,0),(8,3)),
 ((0,0),(0,1),(0,2),(0,3),(0,4),(0,5),(0,6),(0,7),(0,8),(1,0),(2,0),
  (3,0),(3,5),(4,0),(4,4),(5,0),(5,3),(5,6),(6,0),(6,8),(7,0),(8,0)),
 ((0,0),(0,1),(0,2),(0,3),(0,4),(0,5),(0,6),(0,7),(0,8),(1,0),(2,0),
  (3,0),(3,3),(3,6),(4,0),(4,4),(5,0),(5,5),(6,0),(6,8),(7,0),(7,4),(8,0)),
 ((0,0),(0,1),(0,2),(0,3),(0,4),(0,5),(0,6),(0,7),(0,8),(1,0),(2,0),
  (3,0),(3,3),(3,6),(4,0),(4,5),(5,0),(5,4),(6,0),(6,8),(7,0),(7,3),
  (8,0),(8,5)),
 ((0,0),(0,1),(0,2),(0,3),(0,4),(0,5),(0,6),(0,7),(0,8),(1,0),(2,0),
  (3,0),(3,8),(4,0),(4,3),(4,6),(5,0),(5,4),(5,7),(6,0),(6,5),(7,0),
  (8,0),(8,3),(8,6)),
 ((0,0),(0,1),(0,2),(0,3),(0,4),(0,5),(0,6),(0,7),(0,8),(1,0),(2,0),
  (3,0),(3,3),(3,5),(4,0),(4,4),(4,7),(5,0),(5,8),(6,0),(6,3),(6,6),
  (7,0),(7,5),(8,0),(8,5)),
]

def make_shape(rng: random.Random) -> set[tuple[int, int]]:
    clues = set(rng.choice(SHAPES))
    if rng.random() < .5:
        clues = {(col, row) for row, col in clues}
    return clues

def slots_for(clues: set[tuple[int, int]]) -> list[Slot]:
    """Declare every visible run with an immediately adjacent straight arrow."""
    letters = {(row, col) for row in range(SIZE) for col in range(SIZE)} - clues
    runs: list[tuple[str, tuple[tuple[int, int], ...], list[tuple[tuple[int, int], str]]]] = []
    for direction, dr, dc in (("across", 0, 1), ("down", 1, 0)):
        for start in sorted(letters):
            if (start[0] - dr, start[1] - dc) in letters:
                continue
            cells = []
            current = start
            while current in letters:
                cells.append(current)
                current = (current[0] + dr, current[1] + dc)
            if len(cells) < 2:
                continue
            row, col = start
            candidates = []
            if direction == "across":
                candidates = [((row, col - 1), "right")]
            else:
                candidates = [((row - 1, col), "down")]
            candidates = [(clue, arrow) for clue, arrow in candidates
                          if clue in clues and clue != (0, 0)]
            if not candidates:
                return []
            runs.append((direction, tuple(cells), candidates))

    # Assign exactly one unambiguous arrow to each run. One clue cell may hold
    # at most one horizontal and one vertical definition.
    ordered = sorted(enumerate(runs), key=lambda item: (len(item[1][2]), -len(item[1][1])))
    assigned: dict[int, tuple[tuple[int, int], str]] = {}
    used: set[tuple[tuple[int, int], str]] = set()

    def place(offset: int) -> bool:
        if offset == len(ordered):
            return True
        run_index, (direction, _cells, candidates) = ordered[offset]
        for clue, arrow in candidates:
            key = (clue, direction)
            if key in used:
                continue
            used.add(key); assigned[run_index] = (clue, arrow)
            if place(offset + 1):
                return True
            used.remove(key); assigned.pop(run_index)
        return False

    if not place(0):
        return []
    return [
        Slot(direction, assigned[index][0], cells, assigned[index][1])
        for index, (direction, cells, _candidates) in enumerate(runs)
    ]

def shape_errors(clues: set[tuple[int, int]], slots: list[Slot]) -> list[str]:
    errors = []
    if (0, 0) not in clues: errors.append("angle neutre absent")
    expected_frame = ({(0, col) for col in range(SIZE)}
                      | {(row, 0) for row in range(SIZE)})
    if not expected_frame <= clues:
        errors.append("cadre de définitions incomplet")
    if any(slot.clue == (0, 0) for slot in slots): errors.append("flèche depuis l’angle neutre")
    active_clues = {slot.clue for slot in slots}
    if not any(row == 0 for row, _col in active_clues):
        errors.append("première ligne sans définition")
    if not any(col == 0 for _row, col in active_clues):
        errors.append("première colonne sans définition")
    counts = Counter(len(s.cells) for s in slots); total = sum(counts.values())
    if len(counts) < 4: errors.append("diversité insuffisante")
    if total and max(counts.values()) / total > .35: errors.append("longueur trop dominante")
    if not any(counts[n] for n in (2, 3)): errors.append("aucun mot court")
    if not any(counts[n] for n in (4, 5)): errors.append("aucun mot moyen")
    if not any(counts[n] for n in (6, 7, 8)): errors.append("aucun mot long")
    used = {cell for slot in slots for cell in slot.cells}
    if any((r, c) not in clues | used for r in range(SIZE) for c in range(SIZE)): errors.append("case sans fonction")
    if any(cell != (0, 0) and cell not in active_clues for cell in clues): errors.append("définition sans mot")
    double_clues = sum(sum(slot.clue == clue for slot in slots) == 2 for clue in active_clues)
    if double_clues < 3: errors.append("moins de trois cases à double définition")
    declared_paths = {(slot.direction, slot.cells) for slot in slots}
    letters = {(row, col) for row in range(SIZE) for col in range(SIZE)} - clues
    for direction, dr, dc in (("across", 0, 1), ("down", 1, 0)):
        for cell in sorted(letters):
            if (cell[0] - dr, cell[1] - dc) in letters:
                continue
            run = []
            current = cell
            while current in letters:
                run.append(current)
                current = (current[0] + dr, current[1] + dc)
            if len(run) >= 2 and (direction, tuple(run)) not in declared_paths:
                errors.append(f"segment orphelin {direction} {run}")
    visible_clues = clues - {(0, 0)}
    adjacent_pairs = 0
    for row in range(SIZE):
        line = [(row, col) in visible_clues for col in range(SIZE)]
        if row > 0:
            adjacent_pairs += sum(left and right for left, right in zip(line, line[1:]))
            if sum(line) > 4: errors.append("trop de définitions sur une ligne intérieure")
            if "111" in "".join("1" if value else "0" for value in line): errors.append("mur horizontal intérieur")
    for col in range(SIZE):
        line = [(row, col) in visible_clues for row in range(SIZE)]
        if col > 0:
            adjacent_pairs += sum(top and bottom for top, bottom in zip(line, line[1:]))
            if sum(line) > 4: errors.append("trop de définitions dans une colonne intérieure")
            if "111" in "".join("1" if value else "0" for value in line): errors.append("mur vertical intérieur")
    if adjacent_pairs > 2: errors.append("plus de deux paires intérieures de définitions adjacentes")
    if any(all((row + dr, col + dc) in clues for dr in (0, 1) for dc in (0, 1))
           for row in range(SIZE - 1) for col in range(SIZE - 1)):
        errors.append("bloc 2x2 de définitions")
    return errors

def build_index(entries: list[dict], excluded_answers: set[str] | None = None,
                min_frequency: float = 0, difficulty: str = "normal",
                allow_dictionary_derived: bool = False,
                strict_declared_difficulty: bool = False):
    by_length = defaultdict(list)
    frequency = {}
    concept_group = {}
    semantic_conflicts = {}
    word_difficulty = {}
    image_answers = set()
    excluded_answers = excluded_answers or set()
    allowed_difficulties = {"easy", "normal", "hard"}
    for entry in entries:
        clue = entry["clue"].lower()
        forbidden = ("abréviation", "sigle", "code iso", "symbole", "lettre de l’alphabet", "nom propre")
        if (1 <= entry["length"] <= 9 and (entry["length"] == 1 or
                (entry.get("difficulty", "normal") in allowed_difficulties and entry["frequency"] >= min_frequency)) and
                entry.get("sourceType") in {
                    "crossword", "image", "dictionary", "lexical-relation",
                    "editorial-original",
                } and
                # A central entry explicitly approved for generation no
                # longer needs a second Lexique attestation.  Requiring both
                # silently removed JeuxDeMots relations and thousands of
                # reviewed crossword answers from the placement reservoir.
                (
                    entry.get("canonicalForGenerator") is True
                    or entry["answer"] in LEXIQUE_LEMMAS
                    or entry.get("sourceType") in {
                        "image", "dictionary", "editorial-original",
                    }
                ) and
                entry.get("editorialStatus") in ({"source-backed", "image-reviewed", "human-reviewed"}
                    | ({"dictionary-derived"} if allow_dictionary_derived else set())) and
                entry.get("sourceClue") and
                (entry["length"] != 2 or entry.get("shortAnswerApproved") is True or (
                    entry.get("sourceType") == "dictionary" and
                    entry.get("editorialStatus") == "human-reviewed"
                )) and
                not (difficulty == "easy" and entry.get("difficulty") == "hard"
                     and float(entry.get("frequency", 0)) < 3) and
                not (difficulty == "easy" and entry["answer"] in REJECTED_EASY_ANSWERS) and
                not (difficulty == "normal" and entry["answer"] in REJECTED_NORMAL_ANSWERS) and
                entry["answer"] not in REJECTED_ANSWERS | ROTATION_COOLDOWN_ANSWERS and
                (entry["answer"], entry["clue"].casefold()) not in REJECTED_PAIRS and
                not editorial_errors(entry, root=ROOT) and
                not any(marker in clue for marker in forbidden) and
                entry["answer"] not in FORBIDDEN_ANSWERS and
                entry["answer"] not in excluded_answers and
                entry["answer"] not in by_length[entry["length"]]):
            by_length[entry["length"]].append(entry["answer"])
            frequency[entry["answer"]] = entry["frequency"]
            concept_group[entry["answer"]] = entry.get("conceptGroup", entry["answer"])
            semantic_conflicts[entry["answer"]] = set(entry.get("semanticConflicts", []))
            word_difficulty[entry["answer"]] = (
                entry.get("difficulty", "hard") if strict_declared_difficulty
                else audience_difficulty(entry)
            )
            if entry.get("image"): image_answers.add(entry["answer"])
    position_index = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    for length, words in by_length.items():
        for word in words:
            for position, letter in enumerate(word): position_index[length][position][letter].add(word)
    return by_length, position_index, frequency, concept_group, semantic_conflicts, word_difficulty, image_answers

def choose_difficulty_mix(total: int, difficulty: str, rng: random.Random) -> dict[str, int]:
    """Choose one varied, valid mix inside the level's editorial ranges."""
    ranges = DIFFICULTY_RANGES[difficulty]
    levels = ("easy", "normal", "hard")
    possibilities = []
    for easy in range(total + 1):
        for normal in range(total - easy + 1):
            counts = {"easy": easy, "normal": normal, "hard": total - easy - normal}
            if all(ranges[level][0] <= counts[level] / total <= ranges[level][1]
                   for level in levels):
                possibilities.append(counts)
    if not possibilities:
        raise ValueError(f"Aucun mélange de difficulté possible pour {total} mots")
    # Prefer the centre of each range, but keep enough randomness for grids of
    # the same level to feel a little easier or harder than one another.
    centres = {level: sum(ranges[level]) / 2 for level in levels}
    possibilities.sort(key=lambda counts: sum(
        abs(counts[level] / total - centres[level]) for level in levels
    ))
    return rng.choice(possibilities[:max(1, len(possibilities) * 2 // 3)])

def fill(slots: list[Slot], indexes, limit: int, rng: random.Random,
         unavailable_answers: set[str] | None = None, target_difficulty: str = "normal",
         discouraged_answers: set[str] | None = None,
         answer_usage: dict[str, int] | None = None) -> dict[int, str] | None:
    by_length, position_index, frequency, concept_group, semantic_conflicts, word_difficulty, image_answers = indexes
    unavailable_answers = unavailable_answers or set()
    discouraged_answers = discouraged_answers or set()
    answer_usage = answer_usage or {}
    active = [(i, s) for i, s in enumerate(slots) if len(s.cells) >= 1]
    target_mix = choose_difficulty_mix(len(active), target_difficulty, rng)
    cell_links = defaultdict(list)
    for slot_index, active_slot in active:
        for position, cell in enumerate(active_slot.cells):
            cell_links[cell].append((slot_index, position))
    crossing_links = defaultdict(list)
    for slot_index, active_slot in active:
        for position, cell in enumerate(active_slot.cells):
            for other_index, other_position in cell_links[cell]:
                if other_index != slot_index:
                    crossing_links[slot_index].append(
                        (position, len(slots[other_index].cells), other_position)
                    )
    assigned, letters, used_words, used_concepts = {}, {}, set(), set(); nodes = 0
    assigned_mix: Counter[str] = Counter()
    def matching(slot_index: int, slot: Slot) -> list[str]:
        fixed = [(p, letters[cell]) for p, cell in enumerate(slot.cells) if cell in letters]
        if fixed:
            pools = [position_index[len(slot.cells)][position][letter] for position, letter in fixed]
            if not pools: return []
            candidates = set(min(pools, key=len))
            for pool in pools: candidates.intersection_update(pool)
            result = [word for word in candidates if word not in used_words and word not in unavailable_answers
                      and concept_group[word] not in used_concepts
                      and not semantic_conflicts[word].intersection(used_words)]
        else:
            result = [word for word in by_length[len(slot.cells)] if word not in used_words and word not in unavailable_answers
                      and concept_group[word] not in used_concepts
                      and not semantic_conflicts[word].intersection(used_words)]
        if result:
            # Shuffle before the stable priority sort so two seeds do not keep
            # selecting the same high-ranked answer for every open slot.
            rng.shuffle(result)
            has_image = any(word in image_answers for word in assigned.values())
            def tier_priority(word: str) -> tuple[int, int, float, float]:
                tier = word_difficulty[word]
                remaining_ratio = (target_mix[tier] - assigned_mix[tier]) / max(1, target_mix[tier])
                image_priority = 0 if not has_image and word in image_answers else 1
                reuse_priority = answer_usage.get(word, 1 if word in discouraged_answers else 0)
                support = sum(math.log1p(len(position_index[other_length][other_position][word[position]]))
                              for position, other_length, other_position in crossing_links[slot_index])
                return (reuse_priority, image_priority, -remaining_ratio, -support)
            result.sort(key=tier_priority)
        return result
    def search() -> bool:
        nonlocal nodes
        nodes += 1
        if nodes > limit: return False
        if len(assigned) == len(active):
            image_count = sum(word in image_answers for word in assigned.values())
            if not 1 <= image_count <= 6:
                return False
            return True
        choice = None
        for index, slot in active:
            if index in assigned: continue
            candidates = matching(index, slot)
            if not candidates: return False
            if choice is None or len(candidates) < len(choice[1]): choice = index, candidates, slot
        index, candidates, slot = choice
        for word in candidates:
            added = []
            for p, cell in enumerate(slot.cells):
                if cell not in letters: letters[cell] = word[p]; added.append(cell)
            assigned[index] = word; used_words.add(word); used_concepts.add(concept_group[word])
            assigned_mix[word_difficulty[word]] += 1
            if search(): return True
            del assigned[index]; used_words.remove(word); used_concepts.remove(concept_group[word])
            assigned_mix[word_difficulty[word]] -= 1
            for cell in added:
                if not any(i in assigned and cell in slots[i].cells for i, _ in active): letters.pop(cell, None)
        return False
    return assigned if search() else None

def fill_csp(slots: list[Slot], indexes, limit: int, rng: random.Random,
             unavailable_answers: set[str] | None = None,
             target_difficulty: str = "normal",
             answer_usage: dict[str, int] | None = None,
             max_seconds: float | None = None,
             telemetry: dict | None = None) -> dict[int, str] | None:
    """Fill a template with arc consistency and global difficulty quotas."""
    by_length, _, frequency, concept_group, semantic_conflicts, word_difficulty, image_answers = indexes
    unavailable_answers = unavailable_answers or set()
    answer_usage = answer_usage or {}
    telemetry = telemetry if telemetry is not None else {}
    started = time.monotonic()
    deadline = started + max_seconds if max_seconds else None

    def timed_out() -> bool:
        return deadline is not None and time.monotonic() >= deadline
    variables = [index for index, slot in enumerate(slots) if slot.cells]
    target_mix = choose_difficulty_mix(len(variables), target_difficulty, rng)
    domains = {
        index: {word for word in by_length[len(slots[index].cells)]
                if word not in unavailable_answers}
        for index in variables
    }

    cell_links = defaultdict(list)
    for index in variables:
        for position, cell in enumerate(slots[index].cells):
            cell_links[cell].append((index, position))
    intersections = {}
    neighbors = defaultdict(set)
    for links in cell_links.values():
        for left, left_position in links:
            for right, right_position in links:
                if left != right:
                    intersections[left, right] = (left_position, right_position)
                    neighbors[left].add(right)

    def enforce_arc_consistency(current_domains: dict[int, set[str]]) -> bool:
        queue = [(left, right) for left in variables for right in neighbors[left]]
        revisions = 0
        while queue:
            revisions += 1
            if revisions % 32 == 0 and timed_out():
                telemetry["reason"] = "timeout"
                return False
            left, right = queue.pop()
            left_position, right_position = intersections[left, right]
            supported_letters = {word[right_position] for word in current_domains[right]}
            revised = {word for word in current_domains[left]
                       if word[left_position] in supported_letters}
            if not revised:
                return False
            if len(revised) != len(current_domains[left]):
                current_domains[left] = revised
                queue.extend((other, left) for other in neighbors[left] if other != right)
        return True

    if any(not domain for domain in domains.values()) or not enforce_arc_consistency(domains):
        telemetry.setdefault("reason", "empty_or_inconsistent_domain")
        telemetry["elapsedSeconds"] = round(time.monotonic() - started, 3)
        return None

    assigned: dict[int, str] = {}
    used_words: set[str] = set()
    used_concepts: set[str] = set()
    assigned_mix: Counter[str] = Counter()
    nodes = 0

    def feasible_global_counts(current_domains: dict[int, set[str]]) -> bool:
        remaining = [index for index in variables if index not in assigned]
        for tier, target in target_mix.items():
            need = target - assigned_mix[tier]
            if need < 0:
                return False
            possible = sum(any(word_difficulty[word] == tier for word in current_domains[index])
                           for index in remaining)
            if possible < need:
                return False
        if not any(word in image_answers for word in assigned.values()):
            if not any(any(word in image_answers for word in current_domains[index]) for index in remaining):
                return False
        return True

    def search(current_domains: dict[int, set[str]]) -> bool:
        nonlocal nodes
        nodes += 1
        if timed_out():
            telemetry["reason"] = "timeout"
            return False
        if nodes > limit:
            telemetry["reason"] = "node_budget"
            return False
        if len(assigned) == len(variables):
            return (assigned_mix == Counter(target_mix)
                    and 1 <= sum(word in image_answers for word in assigned.values()) <= 6)

        index = min((item for item in variables if item not in assigned),
                    key=lambda item: len(current_domains[item]))
        candidates = list(current_domains[index])
        rng.shuffle(candidates)
        has_image = any(word in image_answers for word in assigned.values())

        def priority(word: str) -> tuple[int, int, float]:
            tier = word_difficulty[word]
            deficit = (target_mix[tier] - assigned_mix[tier]) / max(1, target_mix[tier])
            return (answer_usage.get(word, 0),
                    0 if not has_image and word in image_answers else 1,
                    -deficit)

        candidates.sort(key=priority)
        for word in candidates:
            if timed_out():
                telemetry["reason"] = "timeout"
                return False
            tier = word_difficulty[word]
            if assigned_mix[tier] >= target_mix[tier]:
                continue
            if word in used_words or concept_group[word] in used_concepts:
                continue
            if semantic_conflicts[word].intersection(used_words):
                continue

            next_domains = {item: set(domain) for item, domain in current_domains.items()}
            next_domains[index] = {word}
            assigned[index] = word
            used_words.add(word)
            used_concepts.add(concept_group[word])
            assigned_mix[tier] += 1

            valid = True
            for other in variables:
                if other in assigned:
                    continue
                filtered = {
                    candidate for candidate in next_domains[other]
                    if candidate not in used_words
                    and concept_group[candidate] not in used_concepts
                    and not semantic_conflicts[candidate].intersection(used_words)
                    and assigned_mix[word_difficulty[candidate]] < target_mix[word_difficulty[candidate]]
                }
                if not filtered:
                    valid = False
                    break
                next_domains[other] = filtered

            if (valid and feasible_global_counts(next_domains)
                    and enforce_arc_consistency(next_domains)
                    and search(next_domains)):
                return True

            assigned_mix[tier] -= 1
            used_concepts.remove(concept_group[word])
            used_words.remove(word)
            del assigned[index]
        return False

    solved = search(domains)
    telemetry["nodes"] = nodes
    telemetry["elapsedSeconds"] = round(time.monotonic() - started, 3)
    telemetry.setdefault("reason", "solved" if solved else "no_solution")
    return assigned if solved else None

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10); parser.add_argument("--attempts", type=int, default=2000)
    parser.add_argument("--nodes", type=int, default=150000); parser.add_argument("--seed", type=int, default=20260712)
    parser.add_argument("--fill-timeout", type=float, default=5.0,
                        help="secondes maximales par tentative de remplissage")
    parser.add_argument("--solver", choices=("bitset", "cp-sat", "legacy"), default="bitset")
    parser.add_argument("--difficulty", choices=("easy", "normal", "hard"), default="normal")
    parser.add_argument("--min-frequency", type=float)
    parser.add_argument("--max-answer-uses", type=int, default=2)
    parser.add_argument("--max-grammar-answers", type=int, default=1)
    parser.add_argument("--output", type=Path, default=CATALOG)
    parser.add_argument("--exclude-catalog", type=Path)
    parser.add_argument("--dry-run", action="store_true"); args = parser.parse_args()
    entries = load_entries(); clue_for = {e["answer"]: e["clue"] for e in entries}
    image_for = {e["answer"]: e.get("image") for e in entries if e.get("image")}
    excluded_answers = set()
    if args.exclude_catalog:
        exclusion_path = args.exclude_catalog if args.exclude_catalog.is_absolute() else ROOT / args.exclude_catalog
        exclusion_data = json.loads(exclusion_path.read_text(encoding="utf-8"))
        excluded_answers = {word["answer"] for grid in exclusion_data["grids"] for word in grid["words"]}
    default_frequency = {"easy": 0, "normal": 0, "hard": 0}[args.difficulty]
    min_frequency = args.min_frequency if args.min_frequency is not None else default_frequency
    indexes = build_index(entries, excluded_answers, min_frequency, args.difficulty)
    print(json.dumps({"status": "indexed", "words": sum(len(words) for words in indexes[0].values()),
                      "byLength": {str(length): len(words) for length, words in sorted(indexes[0].items())},
                      "difficulty": args.difficulty, "minFrequency": min_frequency}), flush=True)
    rng = random.Random(args.seed); grids = []; valid_shapes = 0; accepted_shapes = Counter(); accepted_answers = set()
    accepted_answer_usage: Counter[str] = Counter()
    rejection_reasons: Counter[str] = Counter()
    print(json.dumps({"status": "started", "target": args.count, "attempts": args.attempts, "seed": args.seed}), flush=True)
    for attempt in range(args.attempts):
        clues = make_shape(rng); slots = slots_for(clues)
        geometry_errors = shape_errors(clues, slots)
        if geometry_errors:
            rejection_reasons.update(f"shape:{error}" for error in set(geometry_errors))
            if (attempt + 1) % 25 == 0:
                print(json.dumps({"status": "running", "attempted": attempt + 1, "validShapes": valid_shapes, "accepted": len(grids)}), flush=True)
            continue
        fingerprint = tuple(sorted(clues))
        if accepted_shapes[fingerprint] >= 2: continue
        valid_shapes += 1
        print(json.dumps({"status": "filling", "attempted": attempt + 1, "validShapes": valid_shapes,
                          "accepted": len(grids), "nodeBudget": args.nodes}), flush=True)
        unavailable_answers = {answer for answer, uses in accepted_answer_usage.items() if uses >= args.max_answer_uses}
        fill_stats = {}
        if args.solver == "bitset":
            target_mix = choose_difficulty_mix(len(slots), args.difficulty, rng)
            answers = fill_bitset(
                slots, indexes, rng, target_mix,
                unavailable_answers=unavailable_answers,
                answer_usage=dict(accepted_answer_usage),
                grammar_answers=GRAMMAR_ANSWERS,
                max_grammar_answers=args.max_grammar_answers,
                max_seconds=args.fill_timeout,
                node_limit=args.nodes,
                minimum_images={"easy": 2, "normal": 2, "hard": 1}[args.difficulty],
                telemetry=fill_stats,
            )
        elif args.solver == "cp-sat":
            target_mix = choose_difficulty_mix(len(slots), args.difficulty, rng)
            answers = fill_cp_sat(
                slots, indexes, rng, target_mix,
                unavailable_answers=unavailable_answers,
                answer_usage=dict(accepted_answer_usage),
                grammar_answers=GRAMMAR_ANSWERS,
                max_grammar_answers=args.max_grammar_answers,
                max_seconds=args.fill_timeout,
                minimum_images={"easy": 2, "normal": 2, "hard": 1}[args.difficulty],
                telemetry=fill_stats,
            )
        else:
            answers = fill_csp(slots, indexes, args.nodes, rng, unavailable_answers, args.difficulty,
                               dict(accepted_answer_usage), args.fill_timeout, fill_stats)
        if answers is None:
            rejection_reasons[f"fill:{fill_stats.get('reason', 'no_solution')}"] += 1
            if (attempt + 1) % 25 == 0:
                print(json.dumps({"status": "running", "attempted": attempt + 1, "validShapes": valid_shapes, "accepted": len(grids)}), flush=True)
            continue
        if sum(answer in GRAMMAR_ANSWERS for answer in answers.values()) > args.max_grammar_answers:
            rejection_reasons["editorial:too_many_grammar_answers"] += 1
            continue
        answer_fingerprint = tuple(sorted(answers.values()))
        if answer_fingerprint in accepted_answers:
            rejection_reasons["diversity:duplicate_answer_set"] += 1
            continue
        image_limit = {"easy": 6, "normal": 4, "hard": 2}[args.difficulty]
        image_words = set(answer for answer in answers.values() if answer in image_for)
        image_words = set(sorted(image_words)[:image_limit])
        grid_id = f"offline-{args.seed}-{attempt}"
        words = [{"wordId": f"{grid_id}:word:{i}", "answer": answer, "clue": clue_for[answer], "direction": slots[i].direction,
                  "arrow": slots[i].arrow,
                  "clueCell": list(slots[i].clue), "cells": [list(c) for c in slots[i].cells],
                  **({"image": image_for[answer]} if answer in image_words else {})} for i, answer in answers.items()]
        difficulty_mix = Counter(indexes[5][answer] for answer in answers.values())
        ranges = DIFFICULTY_RANGES[args.difficulty]
        word_count = len(answers)
        if not all(ranges[level][0] <= difficulty_mix[level] / word_count <= ranges[level][1]
                   for level in ranges):
            rejection_reasons["difficulty:mix_out_of_range"] += 1
            continue
        candidate = {"id": grid_id, "size": SIZE, "difficulty": args.difficulty,
                     "difficultyMix": {level: difficulty_mix[level] for level in ("easy", "normal", "hard")},
                     "clueCells": [list(c) for c in sorted(clues)], "words": words,
                     "generationMetrics": fill_stats}
        topology = audit_grid_topology(candidate)
        if not topology["valid"]:
            rejection_reasons.update(f"topology:{code}" for code in topology["errorCounts"])
            continue
        grids.append(candidate)
        accepted_shapes[fingerprint] += 1
        accepted_answers.add(answer_fingerprint)
        accepted_answer_usage.update(answers.values())
        print(json.dumps({"status": "gridAccepted", "attempted": attempt + 1, "validShapes": valid_shapes, "accepted": len(grids), "gridId": grids[-1]["id"]}), flush=True)
        if len(grids) >= args.count: break
    print(json.dumps({"status": "finished", "attempted": attempt + 1, "validShapes": valid_shapes,
                      "accepted": len(grids), "rejectionReasons": dict(rejection_reasons.most_common())},
                     ensure_ascii=False), flush=True)
    if not args.dry_run:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.write_text(json.dumps({
            "version": 1,
            "generatorSeed": args.seed,
            "difficulty": args.difficulty,
            "minFrequency": min_frequency,
            "difficultyRanges": DIFFICULTY_RANGES,
            "maximumAnswerUsesPerLevel": args.max_answer_uses,
            "maximumShortAnswerUsesPerLevel": args.max_answer_uses,
            "grids": grids,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    if len(grids) < args.count: raise SystemExit("Catalogue incomplet : lexique insuffisant ou recherche à prolonger")

if __name__ == "__main__": main()
