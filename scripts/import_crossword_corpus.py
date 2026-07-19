"""Build MotMan's clue corpus from real French crossword clue-answer pairs.

This importer never writes or rewrites a clue. It only normalizes answer spelling,
filters unsafe/weak pairs, selects one source clue per answer and records provenance.
The output schema intentionally mirrors the clue database (CWDB) used by WebCrow.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from wordfreq import zipf_frequency

from editorial_quality import editorial_errors


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "src" / "data" / "crossword.ouestfrance.json"
DEFAULT_SOURCE = (
    "https://raw.githubusercontent.com/ychalier-rlv/mots-croises/"
    "main/data/ouestfrance.tsv"
)
SOURCE_PAGE = "https://github.com/ychalier-rlv/mots-croises/tree/main/data"
SOURCE_ORIGIN = "https://jeux.ouest-france.fr/jeux-de-lettres/mots-fleches/"

WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]+(?:[-’'][A-Za-zÀ-ÖØ-öø-ÿŒœ]+)*")
WORDPLAY_RE = re.compile(
    r"\b(?:INITIALES?|ABR[ÉE]VI[ÉE]E?|SIGLE|SYMBOLIS[ÉE]|RACCOURCI|"
    r"MORCEAU|D[ÉE]BUT DE|FIN DE|BOUT DE|MOITI[ÉE] DE|LETTRE)\b",
    re.IGNORECASE,
)
PRONOUN_START_RE = re.compile(
    r"^(?:IL|ELLE|ON|QUI|CELUI|CELLE|CEUX|CELLES|SON|SA|SES)\b",
    re.IGNORECASE,
)
KNOWLEDGE_RE = re.compile(
    r"\b(?:VILLE|CIT[ÉE]|CAPITALE|D[ÉE]PARTEMENT|PR[ÉE]NOM|ROI|REINE|[ÉE]CRIVAIN|"
    r"ACTEUR|CHANTEUR|PEINTRE|DIEU|D[ÉE]ESSE|H[ÉE]ROS|MYTHOLOGIE|CHA[ÎI]NE|"
    r"DROGUE|AUXILIAIRE)\b",
    re.IGNORECASE,
)
VULGAR_OR_SENSITIVE = {
    "BIT", "BITE", "CON", "CUL", "FDP", "HOMO", "NUD", "PENIS",
    "PUTE", "SEXE", "SS", "TG",
}
WEAK_ANSWERS = {
    "ATT", "BAT", "CH", "COLLAB", "CRA", "CT", "HE", "LT", "MTN",
    "PB", "PK", "PQ", "SR", "VE",
}

# Two-letter answers are a special crossword convention. Only transparent,
# source-attested pairs are allowed; cryptic initials and chemical symbols are not.
SHORT_PAIR_WHITELIST = {
    "AN": {"DOUZE MOIS", "DURÉE"},
    "AS": {"CARTE GAGNANTE", "CRACK"},
    "CA": {"DÉMONSTRATIF"},
    "DO": {"NOTE"},
    "ET": {"CONJONCTION", "PUIS"},
    "EU": {"OBTENU"},
    "EX": {"ANCIEN ÉPOUX"},
    "IN": {"TENDANCE", "BRANCHÉ"},
    "LA": {"NOTE"},
    "LU": {"CONSULTÉ"},
    "NE": {"ÉCLOS"},
    "NI": {"CONJONCTION"},
    "OR": {"JAUNE BRILLANT"},
    "OS": {"CHARPENTE", "CUBITUS"},
    "OU": {"CONJONCTION"},
    "RE": {"NOTE"},
    "SI": {"NOTE"},
    "SU": {"MAÎTRISÉ"},
    "TV": {"MÉDIA"},
    "UN": {"CHIFFRE"},
    "US": {"USAGES"},
    "VA": {"CONVIENT"},
    "VU": {"REGARDÉ"},
}


def fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.upper())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def normalize_answer(value: str) -> str:
    return re.sub(r"[^A-Z]", "", fold(value))


def normalize_clue_key(value: str) -> str:
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", fold(value)).split())


def display_clue(value: str) -> str:
    # Capitalization is typographic only; no word is added, removed or rewritten.
    value = " ".join(value.strip().split())
    return value[:1].upper() + value[1:].lower()


def clue_tokens(value: str) -> list[str]:
    return WORD_RE.findall(value)


def token_frequency(token: str) -> float:
    clean = token.replace("’", "'").split("-")[0]
    return zipf_frequency(clean.lower(), "fr")


def pair_score(answer: str, clue: str) -> float:
    tokens = clue_tokens(clue)
    frequencies = [token_frequency(token) for token in tokens]
    score = min(frequencies, default=0) * 4 + zipf_frequency(answer.lower(), "fr") * 2
    if len(tokens) == 1:
        score += 4  # prefer the direct synonym style requested for MotMan
    elif len(tokens) == 2:
        score += 1
    if KNOWLEDGE_RE.search(clue):
        score -= 5
    return score


def pair_is_eligible(answer: str, clue: str, rejected_pairs: set[tuple[str, str]]) -> bool:
    tokens = clue_tokens(clue)
    clue_key = normalize_clue_key(clue)
    # The active compact board never needs answers longer than seven letters.
    if not 2 <= len(answer) <= 7 or not 1 <= len(tokens) <= 2:
        return False
    if answer in WEAK_ANSWERS or answer in VULGAR_OR_SENSITIVE:
        return False
    if any(term in VULGAR_OR_SENSITIVE for term in clue_key.split()):
        return False
    if (answer, clue.casefold()) in rejected_pairs:
        return False
    if editorial_errors({"answer": answer, "clue": clue}):
        return False
    if not clue_key or clue_key == answer or "_" in clue or "…" in clue:
        return False
    if WORDPLAY_RE.search(clue) or PRONOUN_START_RE.search(clue):
        return False
    if len(answer) == 2 and clue.upper() not in SHORT_PAIR_WHITELIST.get(answer, set()):
        return False
    return True


def difficulty_for(answer: str, clue: str) -> str:
    answer_frequency = zipf_frequency(answer.lower(), "fr")
    clue_frequency = min((token_frequency(token) for token in clue_tokens(clue)), default=0)
    if KNOWLEDGE_RE.search(clue) or answer_frequency < 3.25 or clue_frequency < 3.15:
        return "hard"
    if len(answer) >= 3 and answer_frequency >= 4.25 and clue_frequency >= 3.85:
        return "easy"
    return "normal"


def image_for(answer: str) -> dict | None:
    name = answer.lower()
    path = ROOT / "public" / "assets" / "clues" / "twemoji" / f"{name}.svg"
    if not path.exists():
        return None
    return {
        "asset": f"/assets/clues/twemoji/{name}.svg",
        "alt": "Indice illustré",
        "source": "Twemoji",
        "license": "CC BY 4.0",
    }


def fetch_source(url: str) -> tuple[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "MotMan-corpus-importer/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    return raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    editorial = json.loads(
        (ROOT / "src" / "data" / "editorial.blacklist.json").read_text(encoding="utf-8")
    )
    rejected_pairs = {
        (item["answer"], item["clue"].casefold()) for item in editorial["rejectedPairs"]
    }
    source_text, source_sha256 = fetch_source(args.source)

    candidates: dict[str, list[str]] = defaultdict(list)
    raw_rows = 0
    for row in csv.reader(io.StringIO(source_text), delimiter="\t"):
        if not row:
            continue
        raw_rows += 1
        answer = normalize_answer(row[0])
        for clue in row[1:]:
            clue = " ".join(clue.strip().split())
            if pair_is_eligible(answer, clue, rejected_pairs) and clue not in candidates[answer]:
                candidates[answer].append(clue)

    # A clue of a given length must not lead to two different answers. Keeping
    # the most frequent answer removes avoidable ambiguity before generation.
    clue_answers: dict[tuple[int, str], list[str]] = defaultdict(list)
    for answer, clues in candidates.items():
        for clue in clues:
            clue_answers[(len(answer), normalize_clue_key(clue))].append(answer)

    selected: dict[str, str] = {}
    for answer, clues in candidates.items():
        unambiguous = [
            clue for clue in clues
            if len(set(clue_answers[(len(answer), normalize_clue_key(clue))])) == 1
        ]
        if not unambiguous:
            continue
        selected[answer] = max(unambiguous, key=lambda clue: pair_score(answer, clue))

    entries = []
    for answer, clue in sorted(selected.items()):
        difficulty = difficulty_for(answer, clue)
        image = image_for(answer)
        entry = {
            "answer": answer,
            "clue": display_clue(clue),
            "sourceClue": clue,
            "length": len(answer),
            "frequency": round(zipf_frequency(answer.lower(), "fr"), 3),
            "difficulty": difficulty,
            "clueType": "crossword-source",
            "sourceType": "crossword",
            "sourceId": "ouestfrance-via-ychalier",
            "sourceUrl": SOURCE_PAGE,
            "editorialStatus": "source-backed",
            "conceptGroup": answer,
            "semanticConflicts": [],
        }
        if image:
            entry["image"] = image
        entries.append(entry)

    counts = Counter(entry["difficulty"] for entry in entries)
    lengths = Counter(entry["length"] for entry in entries)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 1,
        "format": "webcrow-cwdb-compatible",
        "publicationPolicy": "Exact source clue only; no generated or rewritten clue.",
        "source": {
            "id": "ouestfrance-via-ychalier",
            "url": SOURCE_PAGE,
            "downloadUrl": args.source,
            "originalPublisher": SOURCE_ORIGIN,
            "sha256": source_sha256,
            "rawAnswers": raw_rows,
        },
        "counts": {
            "entries": len(entries),
            "byDifficulty": dict(sorted(counts.items())),
            "byLength": {str(length): count for length, count in sorted(lengths.items())},
            "withImage": sum("image" in entry for entry in entries),
        },
        "entries": entries,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "imported",
        "sourceAnswers": raw_rows,
        "entries": len(entries),
        "byDifficulty": dict(counts),
        "byLength": dict(sorted(lengths.items())),
        "withImage": sum("image" in entry for entry in entries),
        "output": str(output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
