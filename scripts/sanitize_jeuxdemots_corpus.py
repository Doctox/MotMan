"""Split the JeuxDeMots reservoir into useless, reviewable and strict candidates.

This script never publishes a relation.  It creates a small high-precision pool
for editorial review and records why the rest was not allowed through.
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
DEFAULT_INPUT = DATA / "crossword.jeuxdemots.review.json.gz"
DEFAULT_CENTRAL = DATA / "crossword.central.json.gz"
DEFAULT_OUTPUT = DATA / "crossword.jeuxdemots.sanitized.json.gz"
DEFAULT_REPORT_JSON = ROOT / "output/quality/jeuxdemots-sanitization.json"
DEFAULT_REPORT_HTML = ROOT / "output/quality/jeuxdemots-sanitization.html"

STRICT_MUTUAL_WEIGHT = 200
STRICT_MINIMUM_FREQUENCY = 3.0
STRICT_MAXIMUM_RANK = 1
REVIEW_MUTUAL_WEIGHT = 100
REVIEW_MINIMUM_FREQUENCY = 1.0
REVIEW_MAXIMUM_RANK = 3
DOUBT_MUTUAL_WEIGHT = 150
DOUBT_MINIMUM_FREQUENCY = 2.0
DOUBT_MAXIMUM_RANK = 2
DOUBT_REPORT_LIMIT = 250

SENSITIVE_ANSWERS = {
    "BITE", "BITES", "COUILLE", "COUILLES", "CUL", "FOUTRE", "PHALLUS",
    "PENIS", "PUTE", "PUTES", "SEXE", "VAGIN", "VAGINS", "VERGE",
}


def normalize(value: str) -> str:
    folded = "".join(
        char
        for char in unicodedata.normalize("NFD", value.upper())
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"[^A-Z]", "", folded)


def levenshtein(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def is_morphological_near_duplicate(left: str, right: str) -> bool:
    left = normalize(left)
    right = normalize(right)
    shorter, longer = sorted((left, right), key=len)
    if shorter == longer:
        return True
    if len(shorter) >= 4 and longer.startswith(shorter) and len(longer) - len(shorter) <= 3:
        return True
    common_prefix = 0
    for left_char, right_char in zip(left, right):
        if left_char != right_char:
            break
        common_prefix += 1
    return (
        len(shorter) >= 5
        and common_prefix / len(shorter) >= 0.8
        and levenshtein(left, right) <= 2
    )


def load_gzip_json(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def relation_ranks(entries: list[dict]) -> dict[tuple[str, str], int]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        grouped[entry["answer"]].append(entry)
    ranks: dict[tuple[str, str], int] = {}
    for answer, relations in grouped.items():
        ordered = sorted(
            relations,
            key=lambda entry: (
                -int(entry["sourceRelationWeight"]),
                -float(entry["minimumSourceFrequency"]),
                normalize(entry["clue"]),
            ),
        )
        for rank, entry in enumerate(ordered, start=1):
            ranks[(answer, normalize(entry["clue"]))] = rank
    return ranks


def candidate_entry(
    entry: dict,
    reverse: dict,
    ranks: dict[tuple[str, str], int],
    *,
    status: str = "strict-editorial-review-candidate",
) -> dict:
    clue_answer = normalize(entry["clue"])
    mutual_weight = min(
        int(entry["sourceRelationWeight"]),
        int(reverse["sourceRelationWeight"]),
    )
    return {
        **entry,
        "reverseRelationWeight": int(reverse["sourceRelationWeight"]),
        "mutualRelationWeight": mutual_weight,
        "answerRelationRank": ranks[(entry["answer"], clue_answer)],
        "clueRelationRank": ranks[(clue_answer, entry["answer"])],
        "sanitationStatus": status,
        "sanitationPolicy": "mutual-top1-weight200-frequency3",
        "generatorEligible": False,
        "canonicalForGenerator": False,
        "playableAsIs": False,
        "reviewRequired": True,
    }


def sanitize(reservoir: dict, central: dict) -> tuple[dict, dict]:
    entries = reservoir["entries"]
    relation_map = {
        (entry["answer"], normalize(entry["clue"])): entry
        for entry in entries
    }
    ranks = relation_ranks(entries)
    existing_answers = {
        entry["answer"]
        for entry in central["entries"]
        if entry.get("canonicalForGenerator")
        and entry.get("sourceId") != "jeuxdemots-r_syn-sanitized"
    }

    stage_counts = Counter()
    rejection_counts = Counter()
    rejection_samples: dict[str, list[dict]] = defaultdict(list)
    strict_by_answer: dict[str, list[dict]] = defaultdict(list)
    doubt_by_answer: dict[str, list[dict]] = defaultdict(list)
    loose_review_answers: set[str] = set()
    corroborated_existing_answers: set[str] = set()

    def reject(reason: str, entry: dict) -> None:
        rejection_counts[reason] += 1
        if len(rejection_samples[reason]) < 12:
            rejection_samples[reason].append({
                "answer": entry["answer"],
                "clue": entry["clue"],
                "weight": entry["sourceRelationWeight"],
                "frequency": entry["minimumSourceFrequency"],
            })

    for entry in entries:
        answer = entry["answer"]
        clue_answer = normalize(entry["clue"])
        if answer in SENSITIVE_ANSWERS or clue_answer in SENSITIVE_ANSWERS:
            reject("sensitive-content", entry)
            continue
        if is_morphological_near_duplicate(answer, clue_answer):
            reject("morphological-near-duplicate", entry)
            continue
        reverse = relation_map.get((clue_answer, answer))
        if reverse is None:
            reject("not-reciprocal", entry)
            continue
        stage_counts["reciprocalRelations"] += 1
        mutual_weight = min(
            int(entry["sourceRelationWeight"]),
            int(reverse["sourceRelationWeight"]),
        )
        maximum_rank = max(
            ranks[(answer, clue_answer)],
            ranks[(clue_answer, answer)],
        )
        minimum_frequency = float(entry["minimumSourceFrequency"])

        if (
            mutual_weight >= REVIEW_MUTUAL_WEIGHT
            and minimum_frequency >= REVIEW_MINIMUM_FREQUENCY
            and maximum_rank <= REVIEW_MAXIMUM_RANK
        ):
            loose_review_answers.add(answer)

        strict_relation = (
            mutual_weight >= STRICT_MUTUAL_WEIGHT
            and minimum_frequency >= STRICT_MINIMUM_FREQUENCY
            and maximum_rank <= STRICT_MAXIMUM_RANK
        )
        doubt_relation = (
            not strict_relation
            and mutual_weight >= DOUBT_MUTUAL_WEIGHT
            and minimum_frequency >= DOUBT_MINIMUM_FREQUENCY
            and maximum_rank <= DOUBT_MAXIMUM_RANK
            and answer not in existing_answers
        )
        if doubt_relation:
            doubt = candidate_entry(
                entry,
                reverse,
                ranks,
                status="owner-doubt-review-candidate",
            )
            doubt["doubtReasons"] = [
                reason
                for condition, reason in (
                    (mutual_weight < STRICT_MUTUAL_WEIGHT, "poids mutuel inférieur à 200"),
                    (minimum_frequency < STRICT_MINIMUM_FREQUENCY, "fréquence Lexique inférieure à 3"),
                    (maximum_rank > STRICT_MAXIMUM_RANK, "pas le premier synonyme des deux côtés"),
                )
                if condition
            ]
            doubt_by_answer[answer].append(doubt)

        if mutual_weight < STRICT_MUTUAL_WEIGHT:
            reject("mutual-weight-below-200", entry)
            continue
        if minimum_frequency < STRICT_MINIMUM_FREQUENCY:
            reject("source-frequency-below-3", entry)
            continue
        if maximum_rank > STRICT_MAXIMUM_RANK:
            reject("not-mutual-first-choice", entry)
            continue
        stage_counts["strictDirectedRelations"] += 1
        if answer in existing_answers:
            corroborated_existing_answers.add(answer)
            continue
        strict_by_answer[answer].append(candidate_entry(entry, reverse, ranks))

    strict_entries = []
    for answer, candidates in strict_by_answer.items():
        strict_entries.append(max(
            candidates,
            key=lambda entry: (
                entry["mutualRelationWeight"],
                entry["minimumSourceFrequency"],
                -len(entry["clue"]),
                entry["clue"].casefold(),
            ),
        ))
    strict_entries.sort(key=lambda entry: (entry["length"], entry["answer"]))
    doubt_entries = [
        max(
            candidates,
            key=lambda entry: (
                entry["mutualRelationWeight"],
                entry["minimumSourceFrequency"],
                -max(entry["answerRelationRank"], entry["clueRelationRank"]),
                -len(entry["clue"]),
            ),
        )
        for candidates in doubt_by_answer.values()
    ]
    doubt_entries.sort(
        key=lambda entry: (
            -entry["mutualRelationWeight"],
            -entry["minimumSourceFrequency"],
            entry["answer"],
        )
    )
    doubt_report_entries = doubt_entries[:DOUBT_REPORT_LIMIT]

    output = {
        "version": 1,
        "kind": "jeuxdemots-sanitized-editorial-pool",
        "publicationPolicy": "Aucun couple n'est publiable avant une décision éditoriale explicite.",
        "strictPolicy": {
            "reciprocalRelationRequired": True,
            "minimumMutualWeight": STRICT_MUTUAL_WEIGHT,
            "minimumLexiqueFrequencyForBothTerms": STRICT_MINIMUM_FREQUENCY,
            "mutualRankRequired": 1,
            "morphologicalNearDuplicatesRejected": True,
            "sensitiveContentRejected": True,
        },
        "metrics": {
            "inputRelations": len(entries),
            "inputDistinctAnswers": len({entry["answer"] for entry in entries}),
            "reciprocalRelations": stage_counts["reciprocalRelations"],
            "looseReviewDistinctAnswers": len(loose_review_answers),
            "strictDirectedRelations": stage_counts["strictDirectedRelations"],
            "corroboratedExistingAnswers": len(corroborated_existing_answers),
            "strictNewDistinctAnswers": len(strict_entries),
            "doubtDistinctAnswers": len(doubt_entries),
            "doubtCandidatesShown": len(doubt_report_entries),
            "strictCandidatesPlayableWithoutReview": 0,
            "rejectedRelationsByPrimaryReason": dict(rejection_counts),
        },
        "entries": [*strict_entries, *doubt_entries],
    }
    report = {
        "valid": bool(strict_entries),
        "metrics": output["metrics"],
        "strictPolicy": output["strictPolicy"],
        "rejectionSamples": dict(rejection_samples),
        "strictCandidates": [
            {
                "answer": entry["answer"],
                "clue": entry["clue"],
                "partOfSpeech": entry["partOfSpeech"],
                "mutualWeight": entry["mutualRelationWeight"],
                "minimumFrequency": entry["minimumSourceFrequency"],
            }
            for entry in strict_entries
        ],
        "doubtCandidates": [
            {
                "answer": entry["answer"],
                "clue": entry["clue"],
                "partOfSpeech": entry["partOfSpeech"],
                "mutualWeight": entry["mutualRelationWeight"],
                "minimumFrequency": entry["minimumSourceFrequency"],
                "reasons": entry["doubtReasons"],
            }
            for entry in doubt_report_entries
        ],
    }
    return output, report


def render_html(report: dict) -> str:
    metrics = report["metrics"]
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['answer'])}</td>"
        f"<td>{html.escape(item['clue'])}</td>"
        f"<td>{html.escape(item['partOfSpeech'])}</td>"
        f"<td>{item['mutualWeight']}</td>"
        f"<td>{item['minimumFrequency']:.2f}</td>"
        "</tr>"
        for item in report["strictCandidates"]
    )
    rejection_rows = "".join(
        f"<tr><td>{html.escape(reason)}</td><td>{count:,}</td></tr>".replace(",", " ")
        for reason, count in sorted(metrics["rejectedRelationsByPrimaryReason"].items())
    )
    doubt_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['answer'])}</td>"
        f"<td>{html.escape(item['clue'])}</td>"
        f"<td>{html.escape(item['partOfSpeech'])}</td>"
        f"<td>{item['mutualWeight']}</td>"
        f"<td>{item['minimumFrequency']:.2f}</td>"
        f"<td>{html.escape('; '.join(item['reasons']))}</td>"
        "</tr>"
        for item in report["doubtCandidates"]
    )
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Tri JeuxDeMots — MotMan</title><style>
body{{font:15px system-ui;max-width:1100px;margin:32px auto;padding:0 18px;color:#17251f}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}}
.card{{border:1px solid #aec1b7;background:#f5faf7;padding:12px}}table{{width:100%;border-collapse:collapse;margin:20px 0}}
th,td{{border:1px solid #c4cec9;padding:7px;text-align:left}}th{{position:sticky;top:0;background:#e9f2ed}}
</style></head><body><h1>Gros tri du corpus JeuxDeMots</h1>
<div class="summary"><div class="card"><b>{metrics['inputRelations']:,}</b><br>relations reçues</div>
<div class="card"><b>{metrics['reciprocalRelations']:,}</b><br>relations réciproques</div>
<div class="card"><b>{metrics['looseReviewDistinctAnswers']:,}</b><br>réponses encore révisables</div>
<div class="card"><b>{metrics['strictNewDistinctAnswers']:,}</b><br>nouvelles réponses strictes à relire</div>
<div class="card"><b>{metrics['doubtDistinctAnswers']:,}</b><br>réponses classées « doute »</div></div>
<h2>Pourquoi les autres relations sortent</h2><table><tr><th>Motif principal</th><th>Relations</th></tr>{rejection_rows}</table>
<h2>Lot strict — toujours non publié</h2><p>Réciprocité, choix mutuel n°1, poids mutuel ≥ 200 et fréquence Lexique ≥ 3. Une revue éditoriale reste obligatoire.</p>
<table><tr><th>Réponse</th><th>Indice proposé</th><th>Classe</th><th>Poids mutuel</th><th>Fréquence min.</th></tr>{rows}</table>
<h2>Doute propriétaire</h2><p>{metrics['doubtCandidatesShown']} propositions affichées sur {metrics['doubtDistinctAnswers']}. Elles ne sont ni rejetées ni publiées en attendant ton avis.</p>
<table><tr><th>Réponse</th><th>Indice proposé</th><th>Classe</th><th>Poids mutuel</th><th>Fréquence min.</th><th>Pourquoi le doute</th></tr>{doubt_rows}</table>
</body></html>""".replace(",", " ")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--central", type=Path, default=DEFAULT_CENTRAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-html", type=Path, default=DEFAULT_REPORT_HTML)
    args = parser.parse_args()
    output, report = sanitize(load_gzip_json(args.input), load_gzip_json(args.central))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, separators=(",", ":"))
    args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report_html.write_text(render_html(report), encoding="utf-8")
    print(json.dumps(output["metrics"], ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
