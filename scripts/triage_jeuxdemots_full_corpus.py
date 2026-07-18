"""Assign a durable disposition to every retained JeuxDeMots relation.

This is an exhaustive triage ledger, not an automatic publication step.  It
separates reviewed decisions, hard rejections, insufficient evidence, doubts,
corroboration of existing answers and the best editorial candidate per answer.
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
from collections import Counter, defaultdict
from pathlib import Path

from sanitize_jeuxdemots_corpus import (
    SENSITIVE_ANSWERS,
    is_morphological_near_duplicate,
    normalize,
    relation_ranks,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
DEFAULT_INPUT = DATA / "crossword.jeuxdemots.review.json.gz"
DEFAULT_OPEN = DATA / "crossword.open-synonyms.review.json.gz"
DEFAULT_CENTRAL = DATA / "crossword.central.json.gz"
DEFAULT_APPROVED = DATA / "crossword.jeuxdemots.approved.json"
DEFAULT_BLACKLIST = DATA / "editorial.blacklist.json"
DEFAULT_OUTPUT = DATA / "crossword.jeuxdemots.full-triage.json.gz"
DEFAULT_CANDIDATES = DATA / "crossword.jeuxdemots.editorial-candidates.json"
DEFAULT_REPORT = ROOT / "output/quality/jeuxdemots-full-triage.html"

WOLF_EVIDENCE = {"wolf-fr", "wolf-fr-manual", "eduscol-wolf"}


def load(path: Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def pair(entry: dict) -> tuple[str, str]:
    return entry["answer"], normalize(entry.get("clue", ""))


def evidence_map(document: dict) -> dict[tuple[str, str], set[str]]:
    return {
        pair(entry): set(entry.get("evidenceSources", []))
        for entry in document["entries"]
    }


def candidate_score(entry: dict) -> tuple:
    return (
        bool(entry.get("wolfCorroborated")),
        bool(entry.get("reciprocal")),
        int(entry.get("mutualRelationWeight") or entry.get("sourceRelationWeight", 0)),
        -int(entry.get("maximumRelationRank") or entry.get("answerRelationRank", 99)),
        float(entry.get("minimumSourceFrequency", 0)),
        -len(entry.get("clue", "")),
        entry.get("clue", "").casefold(),
    )


def triage(
    reservoir: dict,
    open_synonyms: dict,
    central: dict,
    approved: dict,
    blacklist: dict,
) -> tuple[dict, dict, dict]:
    entries = reservoir["entries"]
    relation_map = {pair(entry): entry for entry in entries}
    ranks = relation_ranks(entries)
    evidence = evidence_map(open_synonyms)
    approved_pairs = {pair(entry) for entry in approved["entries"]}
    blocked_pairs = {
        (normalize(item["answer"]), normalize(item["clue"]))
        for item in blacklist.get("rejectedPairs", [])
    }
    blocked_answers = set(blacklist.get("rejectedAnswers", []))
    blocked_answers.update(blacklist.get("rejectedEasyAnswers", []))
    blocked_answers.update(blacklist.get("rejectedNormalAnswers", []))
    blocked_answers.update(
        item["answer"] for item in blacklist.get("rotationCooldownAnswers", [])
    )
    existing_answers = {
        entry["answer"] for entry in central["entries"]
        if entry.get("canonicalForGenerator")
    }

    classified = []
    provisional_candidates: dict[str, list[int]] = defaultdict(list)
    counts = Counter()
    reason_counts = Counter()

    for source in entries:
        answer = source["answer"]
        clue_answer = normalize(source["clue"])
        key = (answer, clue_answer)
        relation_evidence = evidence.get(key, set())
        wolf_corroborated = bool(relation_evidence & WOLF_EVIDENCE)
        reverse = relation_map.get((clue_answer, answer))
        reciprocal = reverse is not None
        mutual_weight = min(
            int(source["sourceRelationWeight"]),
            int(reverse["sourceRelationWeight"]) if reverse else 0,
        )
        maximum_rank = max(
            ranks[key],
            ranks[(clue_answer, answer)] if reverse else 99,
        )
        frequency = float(source["minimumSourceFrequency"])
        status = "doubt-insufficient-editorial-evidence"
        reasons = []

        if key in approved_pairs:
            status = "approved-human-reviewed"
            reasons = ["couple déjà relu et validé"]
        elif key in blocked_pairs:
            status = "rejected-editorial-blacklist"
            reasons = ["couple explicitement refusé"]
        elif answer in blocked_answers or clue_answer in blocked_answers:
            status = "rejected-answer-policy"
            reasons = ["réponse ou indice bloqué par la politique éditoriale"]
        elif answer in SENSITIVE_ANSWERS or clue_answer in SENSITIVE_ANSWERS:
            status = "rejected-sensitive-content"
            reasons = ["contenu sensible"]
        elif is_morphological_near_duplicate(answer, clue_answer):
            status = "rejected-morphological-duplicate"
            reasons = ["variante morphologique ou forme visuellement quasi identique"]
        else:
            strong_reciprocal = (
                reciprocal
                and mutual_weight >= 100
                and maximum_rank <= 3
                and frequency >= 3
                and (wolf_corroborated or mutual_weight >= 200)
            )
            strong_corroborated_one_way = (
                not reciprocal
                and wolf_corroborated
                and int(source["sourceRelationWeight"]) >= 300
                and ranks[key] <= 2
                and frequency >= 5
            )
            existing_corroboration = answer in existing_answers and (
                (
                    reciprocal
                    and mutual_weight >= 75
                    and maximum_rank <= 5
                    and frequency >= 1
                )
                or (wolf_corroborated and frequency >= 2)
            )
            if existing_corroboration:
                status = "existing-answer-corroboration"
                reasons = ["réponse déjà utilisable; relation conservée comme preuve ou alternative"]
            elif strong_reciprocal or strong_corroborated_one_way:
                status = "editorial-candidate"
                reasons = [
                    "relation réciproque et suffisamment forte"
                    if reciprocal else "relation forte recoupée par WOLF"
                ]
                if wolf_corroborated:
                    reasons.append("relation également présente dans WOLF/Eduscol")
            elif answer in existing_answers:
                status = "rejected-insufficient-evidence"
                reasons = ["réponse déjà couverte et relation alternative trop faible"]
            elif reciprocal and mutual_weight >= 75 and maximum_rank <= 5 and frequency >= 1:
                status = "doubt-reciprocal"
                reasons = ["relation plausible mais preuve ou rang insuffisant pour une promotion"]
            elif not reciprocal and wolf_corroborated and frequency >= 2:
                status = "doubt-cross-source-nonreciprocal"
                reasons = ["recoupée par WOLF mais non réciproque dans JeuxDeMots"]
            else:
                status = "rejected-insufficient-evidence"
                if not reciprocal:
                    reasons.append("relation non réciproque")
                if frequency < 1:
                    reasons.append("fréquence lexicale trop faible")
                if reciprocal and mutual_weight < 75:
                    reasons.append("poids mutuel trop faible")
                if reciprocal and maximum_rank > 5:
                    reasons.append("relation trop éloignée dans le classement sémantique")
                if not reasons:
                    reasons.append("preuves insuffisantes pour une définition de jeu")

        record = {
            **source,
            "triageStatus": status,
            "triageReasons": reasons,
            "reciprocal": reciprocal,
            "reverseRelationWeight": int(reverse["sourceRelationWeight"]) if reverse else None,
            "mutualRelationWeight": mutual_weight if reverse else None,
            "answerRelationRank": ranks[key],
            "clueRelationRank": ranks[(clue_answer, answer)] if reverse else None,
            "maximumRelationRank": maximum_rank if reverse else None,
            "wolfCorroborated": wolf_corroborated,
            "evidenceSources": sorted(relation_evidence or {"jeuxdemots-r_syn"}),
            "generatorEligible": status == "approved-human-reviewed" and source.get("generatorEligible", False),
            "canonicalForGenerator": False,
            "playableAsIs": status == "approved-human-reviewed",
        }
        classified.append(record)
        index = len(classified) - 1
        if status == "editorial-candidate":
            provisional_candidates[answer].append(index)
        counts[status] += 1
        for reason in reasons:
            reason_counts[reason] += 1

    selected = []
    for answer, indexes in provisional_candidates.items():
        winner = max(indexes, key=lambda index: candidate_score(classified[index]))
        for index in indexes:
            if index == winner:
                classified[index]["triageStatus"] = "selected-editorial-candidate"
                classified[index]["triageReasons"].append("meilleure proposition disponible pour cette réponse")
                selected.append(classified[index])
                counts["editorial-candidate"] -= 1
                counts["selected-editorial-candidate"] += 1
            else:
                classified[index]["triageStatus"] = "doubt-alternative-candidate"
                classified[index]["triageReasons"].append("une proposition mieux classée existe pour cette réponse")
                counts["editorial-candidate"] -= 1
                counts["doubt-alternative-candidate"] += 1

    classified.sort(key=lambda entry: (entry["length"], entry["answer"], entry["clue"].casefold()))
    selected.sort(key=lambda entry: (entry["length"], entry["answer"]))
    metrics = {
        "inputRelations": len(entries),
        "classifiedRelations": len(classified),
        "inputDistinctAnswers": len({entry["answer"] for entry in entries}),
        "selectedCandidateAnswers": len(selected),
        "statusCounts": dict(sorted(
            (status, count) for status, count in counts.items() if count
        )),
        "reasonCounts": dict(reason_counts.most_common()),
        "unclassifiedRelations": len(entries) - len(classified),
    }
    ledger = {
        "version": 1,
        "kind": "jeuxdemots-exhaustive-editorial-triage",
        "publicationPolicy": "Seuls les couples approved-human-reviewed peuvent être publiés; selected-editorial-candidate exige encore une relecture.",
        "metrics": metrics,
        "entries": classified,
    }
    candidates = {
        "version": 1,
        "kind": "jeuxdemots-best-candidate-per-answer",
        "publicationPolicy": "Lot à relire; aucune promotion automatique.",
        "metrics": {
            "candidateAnswers": len(selected),
            "wolfCorroborated": sum(entry["wolfCorroborated"] for entry in selected),
            "reciprocal": sum(entry["reciprocal"] for entry in selected),
        },
        "entries": selected,
    }
    report = {"metrics": metrics, "candidates": candidates["metrics"]}
    return ledger, candidates, report


def render(report: dict) -> str:
    status_rows = "".join(
        f"<tr><td>{html.escape(status)}</td><td>{count:,}</td></tr>"
        for status, count in report["metrics"]["statusCounts"].items()
    )
    reason_rows = "".join(
        f"<tr><td>{html.escape(reason)}</td><td>{count:,}</td></tr>"
        for reason, count in report["metrics"]["reasonCounts"].items()
    )
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Tri exhaustif JeuxDeMots</title>
<style>body{{font:16px system-ui;max-width:950px;margin:35px auto;padding:0 18px;color:#17251f}}table{{width:100%;border-collapse:collapse;margin:20px 0}}td,th{{border:1px solid #bdc9c3;padding:8px;text-align:left}}th{{background:#eef5f1}}.ok{{background:#e7f7ed;border:1px solid #83c59b;padding:14px}}</style></head><body>
<h1>Tri exhaustif du réservoir JeuxDeMots</h1><p class="ok"><b>{report['metrics']['classifiedRelations']:,} / {report['metrics']['inputRelations']:,}</b> relations classées. Relations sans statut : <b>{report['metrics']['unclassifiedRelations']}</b>. Meilleurs candidats restant à relire : <b>{report['metrics']['selectedCandidateAnswers']:,}</b>.</p>
<h2>Statuts</h2><table><tr><th>Statut</th><th>Relations</th></tr>{status_rows}</table>
<h2>Motifs</h2><table><tr><th>Motif</th><th>Relations</th></tr>{reason_rows}</table></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--open-synonyms", type=Path, default=DEFAULT_OPEN)
    parser.add_argument("--central", type=Path, default=DEFAULT_CENTRAL)
    parser.add_argument("--approved", type=Path, default=DEFAULT_APPROVED)
    parser.add_argument("--blacklist", type=Path, default=DEFAULT_BLACKLIST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    ledger, candidates, report = triage(
        load(args.input), load(args.open_synonyms), load(args.central),
        load(args.approved), load(args.blacklist),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt", encoding="utf-8") as handle:
        json.dump(ledger, handle, ensure_ascii=False, separators=(",", ":"))
    args.candidates.write_text(json.dumps(candidates, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render(report), encoding="utf-8")
    print(json.dumps({**report["metrics"], "candidates": report["candidates"]}, ensure_ascii=False, indent=2))
    return 0 if report["metrics"]["unclassifiedRelations"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
