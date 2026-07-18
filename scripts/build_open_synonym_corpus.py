"""Build a large, licensed French synonym suggestion pool for review.

This pool is not a grid catalog and is never published automatically.  It
combines JeuxDeMots (CC0), WOLF (CeCILL-C), DBnary/Wiktionary
(CC-BY-SA-3.0) and the existing Eduscol/WOLF school selection.  Every
retained pair is traceable, but a lexical relation is never treated as a
playable crossword clue without editorial review.
"""
from __future__ import annotations

import argparse
import bz2
import gzip
import hashlib
import html
import json
import math
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
DEFAULT_OUTPUT = DATA / "crossword.open-synonyms.review.json.gz"
JDM_FILENAME = "20260319-LEXICALNET-JEUXDEMOTS-R5.txt.zip"
JDM_URL = f"https://www.jeuxdemots.org/JDM-LEXICALNET-FR/{JDM_FILENAME}"
MINIMUM_ELIGIBLE_PAIRS = 15_000
MINIMUM_SOURCE_FREQUENCY = 3.0
MINIMUM_JDM_WEIGHT = 25
MAXIMUM_PAIRS_PER_ANSWER = 12
ANSWER_LENGTH = (3, 8)
CLUE_LENGTH = (3, 10)
WOLF_POS_TO_LEXIQUE = {
    "n": "NOM",
    "v": "VER",
    "a": "ADJ",
    "s": "ADJ",
    "r": "ADV",
}
GRAMMAR_WORDS = set(
    "ALORS APRES AVANT AVEC CAR CE CES COMME DANS DES DONC ELLE ELLES EN ET "
    "IL ILS JE LA LE LES MAIS NI NOUS ON OU PAR PAS POUR QUE QUI SA SES SI "
    "SUR TA TES TU UN UNE VOUS".split()
)
SINGLE_WORD = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿŒœ]+$")


def normalize_answer(value: str) -> str:
    value = value.replace("œ", "oe").replace("Œ", "OE")
    value = "".join(
        char
        for char in unicodedata.normalize("NFD", value)
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"[^A-Z]", "", value.upper())


def display_clue(value: str) -> str | None:
    value = re.sub(r"\s+", " ", value.strip().replace("_", " "))
    if not SINGLE_WORD.fullmatch(value):
        return None
    return value[:1].upper() + value[1:]


def is_visible_inflection(left: str, right: str) -> bool:
    shorter, longer = sorted((left, right), key=len)
    return len(shorter) >= 3 and longer == f"{shorter}S"


def load_context() -> tuple[dict[str, dict], set[str], set[tuple[str, str]]]:
    lexique = json.loads((DATA / "lexique.lemmas.json").read_text(encoding="utf-8"))
    metadata = {entry["answer"]: entry for entry in lexique["entries"]}
    blacklist = json.loads(
        (DATA / "editorial.blacklist.json").read_text(encoding="utf-8")
    )
    blocked_answers = set(blacklist.get("rejectedAnswers", []))
    blocked_answers.update(
        item["answer"]
        for item in blacklist.get("rotationCooldownAnswers", [])
    )
    # The source pools use accent-free canonical answers while editorial clues
    # keep their display accents. Compare both sides in the same canonical form
    # so a rejection such as EPONGE / "Réduit" also blocks EPONGE / REDUIT.
    blocked_pairs = {
        (normalize_answer(item["answer"]), normalize_answer(item["clue"]))
        for item in blacklist.get("rejectedPairs", [])
    }
    return metadata, blocked_answers, blocked_pairs


def pair_is_eligible(
    answer: str,
    clue_answer: str,
    metadata: dict[str, dict],
    blocked_answers: set[str],
    blocked_pairs: set[tuple[str, str]],
    *,
    required_pos: str | None = None,
) -> bool:
    answer_meta = metadata.get(answer)
    clue_meta = metadata.get(clue_answer)
    if not answer_meta or not clue_meta:
        return False
    if not ANSWER_LENGTH[0] <= len(answer) <= ANSWER_LENGTH[1]:
        return False
    if not CLUE_LENGTH[0] <= len(clue_answer) <= CLUE_LENGTH[1]:
        return False
    if min(
        float(answer_meta.get("sourceFrequency", 0)),
        float(clue_meta.get("sourceFrequency", 0)),
    ) < MINIMUM_SOURCE_FREQUENCY:
        return False
    if required_pos and (
        answer_meta.get("partOfSpeech") != required_pos
        or clue_meta.get("partOfSpeech") != required_pos
    ):
        return False
    if answer_meta.get("partOfSpeech") != clue_meta.get("partOfSpeech"):
        return False
    if answer == clue_answer or is_visible_inflection(answer, clue_answer):
        return False
    if answer in blocked_answers or clue_answer in blocked_answers:
        return False
    if answer in GRAMMAR_WORDS or clue_answer in GRAMMAR_WORDS:
        return False
    return (normalize_answer(answer), normalize_answer(clue_answer)) not in blocked_pairs


def score_candidate(entry: dict) -> tuple:
    source_priority = {
        "eduscol-wolf": 4,
        "wolf-fr-manual": 3,
        "jeuxdemots-r_syn": 3,
        "dbnary-fr-wiktionary": 2,
        "wolf-fr": 1,
    }.get(entry["sourceId"], 0)
    return (
        source_priority,
        float(entry["minimumSourceFrequency"]),
        float(entry["clueSourceFrequency"]),
        -len(entry["clue"]),
        entry["clue"].casefold(),
    )


def add_candidate(
    candidates: dict[str, dict[str, dict]],
    entry: dict,
) -> None:
    clue_key = normalize_answer(entry["clue"])
    previous = candidates[entry["answer"]].get(clue_key)
    evidence_sources = set(entry.get("evidenceSources", [entry["sourceId"]]))
    human_evidence = bool(entry.get("humanValidatedEvidence"))
    if previous is not None:
        evidence_sources.update(
            previous.get("evidenceSources", [previous["sourceId"]])
        )
        human_evidence = human_evidence or bool(
            previous.get("humanValidatedEvidence")
        )
    chosen = (
        entry
        if previous is None or score_candidate(entry) > score_candidate(previous)
        else previous
    )
    chosen["evidenceSources"] = sorted(evidence_sources)
    chosen["humanValidatedEvidence"] = human_evidence
    candidates[entry["answer"]][clue_key] = chosen


def common_fields(
    answer: str,
    clue: str,
    clue_answer: str,
    metadata: dict[str, dict],
) -> dict:
    answer_frequency = float(metadata[answer]["sourceFrequency"])
    clue_frequency = float(metadata[clue_answer]["sourceFrequency"])
    minimum_frequency = min(answer_frequency, clue_frequency)
    return {
        "answer": answer,
        "clue": clue,
        "sourceClue": clue,
        "length": len(answer),
        "frequency": round(math.log10(minimum_frequency + 1) + 2, 3),
        "answerSourceFrequency": answer_frequency,
        "clueSourceFrequency": clue_frequency,
        "minimumSourceFrequency": minimum_frequency,
        "partOfSpeech": metadata[answer]["partOfSpeech"],
        "commonnessTier": "frequent" if minimum_frequency >= 10 else "standard",
        "difficulty": "easy" if minimum_frequency >= 15 else "normal",
        "sourceDifficulty": 1 if minimum_frequency >= 15 else 2,
        "clueType": "direct-synonym",
        "sourceType": "dictionary",
        "editorialStatus": "automatic-eligible-review-required",
        "reviewRequired": True,
        "semanticConflicts": [clue_answer],
    }


def add_wolf_candidates(
    candidates: dict[str, dict[str, dict]],
    metadata: dict[str, dict],
    blocked_answers: set[str],
    blocked_pairs: set[tuple[str, str]],
    source: Path,
) -> Counter:
    metrics = Counter()
    with bz2.open(source, "rb") as stream:
        for _event, element in ET.iterparse(stream, events=("end",)):
            if element.tag != "SYNSET":
                continue
            required_pos = WOLF_POS_TO_LEXIQUE.get(
                (element.findtext("POS") or "").strip()
            )
            synonym = element.find("SYNONYM")
            literals: list[tuple[str, str, bool]] = []
            if required_pos and synonym is not None:
                for literal in synonym.findall("LITERAL"):
                    raw = (literal.text or "").strip()
                    clue = display_clue(raw)
                    normalized = normalize_answer(raw)
                    if clue and normalized:
                        literals.append((normalized, clue, "ManVal" in literal.get("lnote", "")))
            literals = list(dict.fromkeys(literals))
            if len(literals) >= 2:
                synset_id = element.findtext("ID") or ""
                for answer, _answer_display, answer_manual in literals:
                    for clue_answer, clue, clue_manual in literals:
                        metrics["rawDirectedPairs"] += 1
                        if not pair_is_eligible(
                            answer,
                            clue_answer,
                            metadata,
                            blocked_answers,
                            blocked_pairs,
                            required_pos=required_pos,
                        ):
                            metrics["rejectedPairs"] += 1
                            continue
                        manual = answer_manual or clue_manual
                        entry = {
                            **common_fields(answer, clue, clue_answer, metadata),
                            "sourceId": "wolf-fr-manual" if manual else "wolf-fr",
                            "sourceUrl": "https://almanach.inria.fr/software_and_resources/WOLF-fr.html",
                            "sourceSynsetId": synset_id,
                            "conceptGroup": f"wolf:{synset_id}",
                            "license": "CeCILL-C",
                            "wolfManualValidation": manual,
                            "evidenceSources": ["wolf-fr"],
                            "humanValidatedEvidence": manual,
                        }
                        add_candidate(candidates, entry)
                        metrics["eligibleRelations"] += 1
            element.clear()
    return metrics


def add_dbnary_candidates(
    candidates: dict[str, dict[str, dict]],
    metadata: dict[str, dict],
    blocked_answers: set[str],
    blocked_pairs: set[tuple[str, str]],
    source: Path,
) -> Counter:
    metrics = Counter()
    with gzip.open(source, "rt", encoding="utf-8") as handle:
        entries = json.load(handle)["entries"]
    for source_entry in entries:
        metrics["rawDirectedPairs"] += 1
        answer = source_entry["answer"]
        clue = display_clue(source_entry["clue"])
        clue_answer = normalize_answer(source_entry["clue"])
        if not clue or not pair_is_eligible(
            answer,
            clue_answer,
            metadata,
            blocked_answers,
            blocked_pairs,
        ):
            metrics["rejectedPairs"] += 1
            continue
        entry = {
            **common_fields(answer, clue, clue_answer, metadata),
            "sourceId": "dbnary-fr-wiktionary",
            "sourceUrl": source_entry["sourceUrl"],
            "sourceEntry": source_entry.get("sourceEntry"),
            "conceptGroup": f"dbnary:{answer}:{clue_answer}",
            "license": "CC-BY-SA-3.0",
            "evidenceSources": ["dbnary-fr-wiktionary"],
            "humanValidatedEvidence": False,
        }
        add_candidate(candidates, entry)
        metrics["eligibleRelations"] += 1
    return metrics


def download(url: str, path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 MotMan-corpus-audit"}
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        path.write_bytes(response.read())


def add_jeuxdemots_candidates(
    candidates: dict[str, dict[str, dict]],
    metadata: dict[str, dict],
    blocked_answers: set[str],
    blocked_pairs: set[tuple[str, str]],
    source: Path,
) -> Counter:
    """Read the official positive r_syn relation dump from JeuxDeMots."""
    download(JDM_URL, source)
    metrics = Counter()
    metrics["archiveBytes"] = source.stat().st_size
    metrics["archiveSha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    with zipfile.ZipFile(source) as archive:
        members = archive.namelist()
        if len(members) != 1:
            raise ValueError(f"archive JeuxDeMots inattendue: {members}")
        with archive.open(members[0]) as stream:
            for raw_line in stream:
                line = raw_line.decode("latin-1", "replace").strip()
                if not line or line.startswith("****"):
                    continue
                try:
                    relation, raw_weight = line.rsplit(" ; ", 1)
                    raw_answer, raw_clue = relation.split(" ; ", 1)
                    weight = int(raw_weight)
                except (ValueError, TypeError):
                    metrics["malformedLines"] += 1
                    continue
                metrics["rawDirectedPairs"] += 1
                if weight < MINIMUM_JDM_WEIGHT:
                    metrics["rejectedByWeight"] += 1
                    continue
                answer_display = html.unescape(raw_answer).strip()
                clue_display = html.unescape(raw_clue).strip()
                clue = display_clue(clue_display)
                answer = normalize_answer(answer_display)
                clue_answer = normalize_answer(clue_display)
                if not clue or not pair_is_eligible(
                    answer,
                    clue_answer,
                    metadata,
                    blocked_answers,
                    blocked_pairs,
                ):
                    metrics["rejectedPairs"] += 1
                    continue
                entry = {
                    **common_fields(answer, clue, clue_answer, metadata),
                    "sourceId": "jeuxdemots-r_syn",
                    "sourceUrl": JDM_URL,
                    "sourceRelationType": "r_syn (5)",
                    "sourceRelationWeight": weight,
                    "conceptGroup": f"jeuxdemots:{answer}:{clue_answer}",
                    "license": "CC0 / domaine public",
                    "evidenceSources": ["jeuxdemots-r_syn"],
                    "humanValidatedEvidence": True,
                    "communityValidatedEvidence": True,
                }
                add_candidate(candidates, entry)
                metrics["eligibleRelations"] += 1
    return metrics


def add_school_candidates(
    candidates: dict[str, dict[str, dict]],
    metadata: dict[str, dict],
    blocked_answers: set[str],
    blocked_pairs: set[tuple[str, str]],
    source: Path,
) -> Counter:
    metrics = Counter()
    entries = json.loads(source.read_text(encoding="utf-8"))["entries"]
    for source_entry in entries:
        metrics["rawDirectedPairs"] += 1
        answer = source_entry["answer"]
        clue = source_entry["clue"]
        clue_answer = normalize_answer(clue)
        if not pair_is_eligible(
            answer,
            clue_answer,
            metadata,
            blocked_answers,
            blocked_pairs,
        ):
            metrics["rejectedPairs"] += 1
            continue
        entry = {
            **common_fields(answer, clue, clue_answer, metadata),
            **{
                key: value
                for key, value in source_entry.items()
                if key.startswith("source") or key in {"license", "wolfManualValidation"}
            },
            "sourceId": "eduscol-wolf",
            "sourceClue": clue,
            "conceptGroup": source_entry.get("conceptGroup", f"school:{answer}:{clue_answer}"),
            "editorialStatus": "dictionary-derived-review-required",
            "reviewRequired": True,
            "semanticConflicts": [clue_answer],
            "evidenceSources": ["eduscol-wolf"],
            "humanValidatedEvidence": bool(
                source_entry.get("wolfManualValidation")
            ),
        }
        add_candidate(candidates, entry)
        metrics["eligibleRelations"] += 1
    return metrics


def select_entries(candidates: dict[str, dict[str, dict]]) -> tuple[list[dict], Counter]:
    selected = []
    metrics = Counter()
    for answer in sorted(candidates):
        choices = sorted(
            candidates[answer].values(), key=score_candidate, reverse=True
        )
        metrics["eligibleBeforeAnswerCap"] += len(choices)
        retained = choices[:MAXIMUM_PAIRS_PER_ANSWER]
        for entry in retained:
            corroborated = len(entry.get("evidenceSources", [])) >= 2
            entry["confidence"] = (
                "strong-source-suggestion"
                if entry.get("humanValidatedEvidence") or corroborated
                else "review-required"
            )
            entry["playableAsIs"] = False
        selected.extend(retained)
        metrics["removedByAnswerCap"] += max(0, len(choices) - MAXIMUM_PAIRS_PER_ANSWER)
    selected.sort(key=lambda item: (item["length"], item["answer"], item["clue"].casefold()))
    return selected, metrics


def build_document(
    entries: list[dict],
    source_metrics: dict[str, Counter],
    selection_metrics: Counter,
) -> dict:
    sources = Counter(entry["sourceId"] for entry in entries)
    answers = Counter(entry["answer"] for entry in entries)
    lengths = Counter(entry["length"] for entry in entries)
    source_validated = [
        entry
        for entry in entries
        if entry.get("confidence") == "strong-source-suggestion"
    ]
    return {
        "version": 1,
        "kind": "open-synonym-editorial-suggestion-pool",
        "publicationPolicy": "Aucune publication automatique; chaque couple reste soumis à la revue éditoriale MotMan.",
        "eligibilityPolicy": {
            "minimumEligiblePairs": MINIMUM_ELIGIBLE_PAIRS,
            "minimumLexiqueFrequencyForAnswerAndClue": MINIMUM_SOURCE_FREQUENCY,
            "minimumJeuxDeMotsRelationWeight": MINIMUM_JDM_WEIGHT,
            "maximumPairsPerAnswer": MAXIMUM_PAIRS_PER_ANSWER,
            "answerLength": list(ANSWER_LENGTH),
            "clueLength": list(CLUE_LENGTH),
            "requiredRelation": "direct synonym from the same licensed lexical relation",
            "samePartOfSpeech": True,
            "blacklistAndRotationCooldownApplied": True,
            "visibleInflectionPairsRejected": True,
        },
        "sources": [
            {
                "id": "jeuxdemots-r_syn",
                "url": JDM_URL,
                "license": "CC0 / domaine public",
            },
            {
                "id": "wolf-fr",
                "url": "https://almanach.inria.fr/software_and_resources/WOLF-fr.html",
                "license": "CeCILL-C",
            },
            {
                "id": "dbnary-fr-wiktionary",
                "url": "https://kaiko.getalp.org/about-dbnary/",
                "license": "CC-BY-SA-3.0",
            },
            {
                "id": "eduscol-wolf",
                "url": "https://eduscol.education.gouv.fr/6873/liste-de-frequence-lexicale",
                "license": "Eduscol Etalab-2.0; WOLF CeCILL-C",
            },
        ],
        "metrics": {
            "suggestionPoolThresholdReached": len(source_validated) >= MINIMUM_ELIGIBLE_PAIRS,
            "sourceBackedPairsPendingReview": len(entries),
            "sourceValidatedSuggestionPairs": len(source_validated),
            "suggestionsStillRequiringStrongerSourceEvidence": len(entries) - len(source_validated),
            "playablePairsWithoutEditorialReview": 0,
            "distinctAnswers": len(answers),
            "sourceValidatedDistinctAnswers": len({
                entry["answer"] for entry in source_validated
            }),
            "distinctClues": len({normalize_answer(entry["clue"]) for entry in entries}),
            "distinctAnswersByLength": {
                str(length): len({
                    entry["answer"] for entry in entries
                    if entry["length"] == length
                })
                for length in sorted(lengths)
            },
            "sourceValidatedBySource": dict(sorted(Counter(
                entry["sourceId"] for entry in source_validated
            ).items())),
            "bySource": dict(sorted(sources.items())),
            "byLength": {str(key): value for key, value in sorted(lengths.items())},
            "maximumPairsForOneAnswer": max(answers.values(), default=0),
            "answersAtMaximumCap": sum(
                count == MAXIMUM_PAIRS_PER_ANSWER for count in answers.values()
            ),
            "sourceProcessing": {
                key: dict(value) for key, value in source_metrics.items()
            },
            "selection": dict(selection_metrics),
        },
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wolf-source", type=Path, default=DATA / "sources/wolf-1.0b4.xml.bz2")
    parser.add_argument("--dbnary-source", type=Path, default=DATA / "crossword.dbnary.staging.json.gz")
    parser.add_argument("--school-source", type=Path, default=DATA / "crossword.school.json")
    parser.add_argument(
        "--jeuxdemots-source",
        type=Path,
        default=DATA / f"sources/{JDM_FILENAME}",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    metadata, blocked_answers, blocked_pairs = load_context()
    candidates: dict[str, dict[str, dict]] = defaultdict(dict)
    source_metrics = {
        "jeuxdemots": add_jeuxdemots_candidates(
            candidates,
            metadata,
            blocked_answers,
            blocked_pairs,
            args.jeuxdemots_source,
        ),
        "wolf": add_wolf_candidates(
            candidates, metadata, blocked_answers, blocked_pairs, args.wolf_source
        ),
        "dbnary": add_dbnary_candidates(
            candidates, metadata, blocked_answers, blocked_pairs, args.dbnary_source
        ),
        "school": add_school_candidates(
            candidates, metadata, blocked_answers, blocked_pairs, args.school_source
        ),
    }
    entries, selection_metrics = select_entries(candidates)
    document = build_document(entries, source_metrics, selection_metrics)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(document["metrics"], ensure_ascii=False, indent=2))
    if not document["metrics"]["suggestionPoolThresholdReached"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
