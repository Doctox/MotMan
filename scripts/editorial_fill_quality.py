#!/usr/bin/env python3
"""Editorial scoring and freshness gates for compact MotMan fills.

The constraint solver answers one question: *does the fill fit?*  This module
answers the separate product question: *is the fill worth showing to a human?*
It deliberately mirrors professional constructor tools: a scored word list,
a minimum entry score, recently-used exclusions, and whole-batch review.
"""

from __future__ import annotations

import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from editorial_quality import editorial_errors


DEFAULT_MINIMUM_ENTRY_SCORE = 18.0
DEFAULT_PRESENTATION_ENTRY_SCORE = 30.0
REJECTED_PAIR_STATUSES = {"rejected", "invalid", "blocked", "false"}


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.upper())
    return "".join(character for character in folded if "A" <= character <= "Z")


def answer_usage(paths: Iterable[Path]) -> Counter[str]:
    """Count exact answers in one or more catalog/staging documents."""
    usage: Counter[str] = Counter()
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        grids = document.get("grids")
        if not isinstance(grids, list):
            grids = [document.get("grid") or document]
        for grid in grids:
            for item in grid.get("words") or grid.get("answers") or []:
                answer = normalize(str(item.get("answer", "")))
                if answer:
                    usage[answer] += 1
    return usage


def blacklist_sets(document: dict) -> tuple[set[str], set[str]]:
    rejected = {normalize(str(answer)) for answer in document.get("rejectedAnswers", [])}
    cooldown = {
        normalize(str(item.get("answer", "") if isinstance(item, dict) else item))
        for item in document.get("rotationCooldownAnswers", [])
    }
    return rejected - {""}, cooldown - {""}


def blocking_pair_reasons(answer: str, metadata: dict) -> list[str]:
    """Return deterministic reasons that make a pair unscorable.

    A review label is evidence of a workflow, never a waiver for a known
    semantic, grammatical or safety error.
    """
    clue = str(metadata.get("centralClue") or metadata.get("sourceClue") or "")
    reasons = [error["code"] for error in editorial_errors({
        "answer": answer,
        "clue": clue,
        "image": metadata.get("image"),
    })]
    statuses = (
        metadata.get("pairReviewStatus"),
        metadata.get("semanticStatus"),
        metadata.get("editorialDecision"),
    )
    if any(str(status).strip().casefold() in REJECTED_PAIR_STATUSES for status in statuses):
        reasons.append("rejected-pair-status")
    declared_errors = metadata.get("editorialErrors") or metadata.get("semanticErrors") or []
    if isinstance(declared_errors, list) and declared_errors:
        reasons.append("declared-editorial-error")
    return sorted(set(reasons))


def editorial_entry_score(
    answer: str,
    metadata: dict,
    *,
    grammar_answers: set[str] | None = None,
    pop_answers: set[str] | None = None,
    active_uses: int = 0,
) -> float:
    """Return a 0..100 constructor score focused on playability.

    Frequency remains useful, but it no longer dominates.  Human-reviewed and
    source-backed roots outrank raw lexical forms; obscure inflections, short
    grammar glue and active-catalog reuse are penalized.
    """
    answer = normalize(answer)
    grammar_answers = grammar_answers or set()
    pop_answers = pop_answers or set()
    status = str(metadata.get("editorialStatus") or "")
    source_id = str(metadata.get("sourceId") or "")
    lemma = normalize(str(metadata.get("lemma") or answer)) or answer
    zipf = float(metadata.get("wordfreqZipf") or 0.0)

    if blocking_pair_reasons(answer, metadata):
        return 0.0

    future_or_conditional = (
        answer != lemma
        and answer.endswith((
            "RAI", "RAS", "RA", "RAIT", "RIONS", "RIEZ", "RAIENT",
            "RONS", "REZ", "RONT",
        ))
    )
    first_group_past_simple = (
        answer != lemma
        and lemma.endswith("ER")
        and answer in {
            lemma[:-2] + ending
            for ending in ("AI", "AS", "A", "AMES", "ATES", "ERENT")
        }
    )
    if future_or_conditional or first_group_past_simple:
        return 0.0

    if answer in pop_answers:
        score = 92.0
    elif status in {
        "human-reviewed", "owner-approved", "manually-reviewed", "image-reviewed",
    }:
        score = 82.0
    elif status in {"source-backed", "editorial-reviewed", "reviewed"}:
        score = 70.0
    elif source_id == "motman-owner-short-vocabulary-20260719":
        score = 52.0
    elif status == "lexical-form-owner-review-required":
        score = 43.0
    elif status == "wordfreq-owner-review-required":
        # wordfreq is evidence of usage, not evidence that a token is a clean
        # French crossword entry (it contains names, English and truncations).
        score = 24.0
    else:
        score = 38.0

    score += max(-6.0, min(12.0, (zipf - 2.5) * 3.0))
    if len(answer) == 2:
        score -= 18.0
    elif len(answer) == 3:
        score -= 8.0
    if answer in grammar_answers:
        score -= 18.0
    if answer != lemma:
        score -= 12.0
        # Rare finite forms are the typical "NIERA / ECRASA" mechanical fill.
        if zipf < 2.8:
            score -= 20.0
    if not str(metadata.get("centralClue") or metadata.get("sourceClue") or "").strip():
        score -= 5.0
    score -= min(30.0, 12.0 * active_uses)
    return round(max(0.0, min(100.0, score)), 3)


def rescore_entries(
    raw_scores: dict[str, float],
    metadata: dict[str, dict],
    *,
    grammar_answers: set[str],
    pop_answers: set[str],
    active_usage_counts: Counter[str] | None = None,
) -> dict[str, float]:
    """Build the score table consumed by the constraint solver."""
    usage = active_usage_counts or Counter()
    return {
        answer: editorial_entry_score(
            answer,
            metadata[answer],
            grammar_answers=grammar_answers,
            pop_answers=pop_answers,
            active_uses=usage.get(answer, 0),
        )
        for answer in raw_scores
        if answer in metadata
    }


def grid_interest_metrics(
    answers: Iterable[str],
    quality_scores: dict[str, float],
    *,
    grammar_answers: set[str],
    pop_answers: set[str],
) -> dict:
    values = [normalize(answer) for answer in answers]
    engaging = [
        answer for answer in values
        if answer in pop_answers
        or (
            len(answer) >= 5
            and answer not in grammar_answers
            and quality_scores.get(answer, 0.0) >= 50.0
        )
    ]
    return {
        "answerCount": len(values),
        "twoLetterCount": sum(len(answer) == 2 for answer in values),
        "shortAnswerCount": sum(len(answer) <= 3 for answer in values),
        "grammarAnswerCount": sum(answer in grammar_answers for answer in values),
        "engagingAnswerCount": len(engaging),
        "engagingAnswers": engaging,
        "weakestEntryScore": min(
            (quality_scores.get(answer, 0.0) for answer in values),
            default=0.0,
        ),
        "meanEntryScore": round(
            sum(quality_scores.get(answer, 0.0) for answer in values) / max(1, len(values)),
            3,
        ),
    }


def audit_candidate_batch(
    grids: Iterable[dict],
    *,
    blacklist_document: dict,
    reference_paths: Iterable[Path] = (),
) -> dict:
    """Reject hard blacklist hits and repetition inside the new lot.

    Cooldowns and active-catalog reuse are reported and scored as fatigue, not
    globally forbidden: the runtime already protects each player's recent
    rotation.
    """
    rejected, cooldown = blacklist_sets(blacklist_document)
    reference = answer_usage(reference_paths)
    occurrences: dict[str, list[str]] = defaultdict(list)
    grid_reports = []
    for sequence, grid in enumerate(grids, 1):
        grid_id = str(grid.get("id") or f"grid-{sequence:02d}")
        answers = [
            normalize(str(item.get("answer", "")))
            for item in (grid.get("words") or grid.get("answers") or [])
        ]
        answers = [answer for answer in answers if answer]
        for answer in answers:
            occurrences[answer].append(grid_id)
        grid_reports.append({
            "gridId": grid_id,
            "blacklistedAnswers": sorted(set(answers) & rejected),
            "cooldownAnswers": sorted(set(answers) & cooldown),
            "activeCatalogRepeats": sorted(set(answers) & set(reference)),
        })

    internal_repeats = {
        answer: grid_ids
        for answer, grid_ids in sorted(occurrences.items())
        if len(grid_ids) > 1
    }
    errors = []
    warnings = []
    for report in grid_reports:
        if report["blacklistedAnswers"]:
            errors.append({
                "gridId": report["gridId"],
                "reason": "blacklistedAnswers",
                "answers": report["blacklistedAnswers"],
            })
        if report["cooldownAnswers"]:
            warnings.append({
                "gridId": report["gridId"],
                "reason": "cooldownAnswers",
                "answers": report["cooldownAnswers"],
            })
        if report["activeCatalogRepeats"]:
            warnings.append({
                "gridId": report["gridId"],
                "reason": "activeCatalogRepeats",
                "answers": report["activeCatalogRepeats"],
            })
    if internal_repeats:
        errors.append({"reason": "internalRepeats", "answers": internal_repeats})
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "internalRepeats": internal_repeats,
        "gridReports": grid_reports,
    }
