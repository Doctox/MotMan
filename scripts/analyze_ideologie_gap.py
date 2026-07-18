"""Find the least structural closure of immutable ribbon A01 with IDEOLOGIE.

This diagnostic keeps every path of ``reference-ribbon-a-01`` immutable.  It
separates locally human lexical forms (reviewed/source-backed pairs, Lexique
lemmas and common child forms) from Morphalou-only structural forms, then
searches exact closures with a hard cap on the latter.  It is intentionally a
staging diagnostic: a lexical form without a reviewed clue is never promoted
to the published catalogue by this script.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import random
import sys
import time
from collections import defaultdict, deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from agent_a_exact_ribbon_a01 import (  # noqa: E402
    load_domains,
    load_shape as load_shape_document,
    mechanical_audit,
)
from diagnose_fixed_shape_corpus_gaps import (  # noqa: E402
    DEFAULT_SHAPES,
    load_shape,
)
from fill_fixed_ribbon_a01 import FixedRibbonArcSolver  # noqa: E402


LEXIQUE = ROOT / "src/data/lexique.lemmas.json"
CHILD_FORMS = ROOT / "src/data/lexique.child-forms.json"
BLACKLIST = ROOT / "src/data/editorial.blacklist.json"
OUTPUT = ROOT / "output/quality/reference-ribbon-a01-ideologie-gap.json"

# The 15 editorially defensible answers of closure 815203.  The three entries
# identified as the shared bottleneck can be released while every other one
# remains a hard whole-answer anchor.
CORE_815203 = {
    0: "IDEOLOGIE",
    1: "DESSINENT",
    3: "ETE",
    4: "REIN",
    6: "ELEVERENT",
    7: "ZEE",
    9: "DENTELLE",
    11: "OSE",
    14: "ZESTE",
    15: "LIMA",
    16: "NEZ",
    17: "ANTI",
    19: "GENANTES",
    20: "INCITENT",
    21: "ETATISTE",
}
RELEASE_PRIORITY = {1, 4, 6}


def load_human_lexical_answers(morphalou: dict[str, dict]) -> tuple[set[str], dict[str, str]]:
    """Return valid human forms and their strongest local evidence tier."""
    lemmas_document = json.loads(LEXIQUE.read_text(encoding="utf-8"))
    child_document = json.loads(CHILD_FORMS.read_text(encoding="utf-8"))
    lemmas = {entry["answer"] for entry in lemmas_document.get("entries", [])}
    child_forms = {entry["answer"] for entry in child_document.get("entries", [])}
    human = set(lemmas) | set(child_forms)
    evidence = {answer: "lexique-lemma" for answer in lemmas}
    evidence.update({answer: "lexique-common-child-form" for answer in child_forms})

    # Only highly predictable inflections of a Lexique lemma are admitted as
    # human lexical forms.  Literary simple past, subjunctive imperfect and
    # arbitrary second-person futures remain structural exceptions.
    for answer, entry in morphalou.items():
        lemma = str(entry.get("lemmaAnswer") or "").upper()
        if not lemma or lemma not in lemmas or entry.get("formType") != "inflected":
            continue
        part = entry.get("partOfSpeech")
        inflection = entry.get("inflection") or {}
        if part in {"common-noun", "adjective"}:
            human.add(answer)
            evidence.setdefault(answer, "morphalou-predictable-number-or-gender")
            continue
        if (
            part == "verb"
            and inflection.get("mode") == "indicative"
            and inflection.get("person") == "thirdPerson"
            and inflection.get("tense") in {"present", "future", "imperfect"}
        ):
            human.add(answer)
            evidence.setdefault(answer, "morphalou-common-indicative-form")
    return human, evidence


class CappedStructuralArcSolver(FixedRibbonArcSolver):
    """AC-3 solver with a hard bound on Morphalou-only selected answers."""

    def __init__(self, *args, human_answers: set[str], max_structural: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.human_answers = human_answers
        self.max_structural = max_structural
        self.human_masks = {}
        for length, words in self.words_by_length.items():
            mask = 0
            for index, word in enumerate(words):
                if word in human_answers:
                    mask |= 1 << index
                    self.priority[word] -= 20.0
            self.human_masks[length] = mask
        self.minimum_structural_seen = len(self.slots) + 1

    def unavoidable_structural(self, domains: tuple[int, ...] | list[int]) -> int:
        count = 0
        for index, domain in enumerate(domains):
            length = self.slots[index].length
            if not domain & self.human_masks[length]:
                count += 1
        self.minimum_structural_seen = min(self.minimum_structural_seen, count)
        return count

    def propagate(self, domains, initial_arcs=None):
        propagated = super().propagate(domains, initial_arcs)
        if propagated is None:
            return None
        if self.unavoidable_structural(propagated) > self.max_structural:
            self.wipeouts += 1
            return None
        return propagated

    def candidate_order(self, slot_index: int, domains: tuple[int, ...]) -> list[int]:
        ordered = super().candidate_order(slot_index, domains)
        words = self.words_by_length[self.slots[slot_index].length]
        ordered.sort(key=lambda index: (words[index] not in self.human_answers, self.priority[words[index]]))
        return ordered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cap", type=int, default=7)
    parser.add_argument("--seconds", type=float, default=180.0)
    parser.add_argument("--seed", type=int, default=823001)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument(
        "--fix-core-minus-priority",
        action="store_true",
        help=(
            "Fixe les 12 réponses défendables de 815203 autres que "
            "DESSINENT, REIN et ELEVERENT."
        ),
    )
    args = parser.parse_args()

    blacklist = json.loads(BLACKLIST.read_text(encoding="utf-8"))
    rejected = set(blacklist.get("rejectedAnswers", []))
    rejected.update(blacklist.get("rejectedEasyAnswers", []))
    rejected.update(blacklist.get("rejectedNormalAnswers", []))
    indexes, central_pairs, morphalou, _source = load_domains(rejected, True)
    by_length, _unused, frequency, _concept, _conflicts, _difficulty, _images = indexes
    human_answers, human_evidence = load_human_lexical_answers(morphalou)
    human_answers.update(central_pairs)
    for answer in central_pairs:
        human_evidence[answer] = "local-reviewed-or-source-backed-pair"
    human_answers.add("IDEOLOGIE")
    human_evidence["IDEOLOGIE"] = "owner-anchor-lexique-lemma"

    shape, slots = load_shape(DEFAULT_SHAPES, "reference-ribbon-a-01")
    metadata = {}
    for length, answers in by_length.items():
        for answer in answers:
            entry = morphalou.get(answer) or central_pairs.get(answer) or {}
            metadata[answer] = {
                **entry,
                "sourceFrequency": float(frequency.get(answer, 0) or 0),
                "schoolFrequency": 0,
            }
    fixed_answers = (
        {index: answer for index, answer in CORE_815203.items() if index not in RELEASE_PRIORITY}
        if args.fix_core_minus_priority
        else {0: "IDEOLOGIE"}
    )
    solver = CappedStructuralArcSolver(
        slots=slots,
        words_by_length={length: tuple(words) for length, words in by_length.items()},
        metadata=metadata,
        canonical=central_pairs,
        owner_accepts={},
        seed=args.seed,
        seconds=args.seconds,
        strategy="information",
        preferred_answers={0: "IDEOLOGIE"},
        human_answers=human_answers,
        max_structural=args.cap,
    )
    solution, telemetry = solver.solve(fixed_answers=fixed_answers)
    payload = {
        "version": 1,
        "kind": "reference-ribbon-a01-ideologie-minimum-structural-search",
        "shapeId": "reference-ribbon-a-01",
        "shapeModified": False,
        "catalogModified": False,
        "anchor": {"slotIndex": 0, "answer": "IDEOLOGIE"},
        "fixedAnswers": [
            {"slotIndex": index, "answer": answer}
            for index, answer in sorted(fixed_answers.items())
        ],
        "releasedPriorityCore": [
            {"slotIndex": index, "answer": CORE_815203[index]}
            for index in sorted(RELEASE_PRIORITY)
        ] if args.fix_core_minus_priority else [],
        "maximumMorphalouOnlyAnswers": args.cap,
        "corpusCounts": {str(length): len(by_length[length]) for length in (3, 4, 5, 8, 9)},
        "humanLexicalAnswerCount": len(human_answers),
        "telemetry": {**telemetry, "minimumUnavoidableStructuralSeen": solver.minimum_structural_seen},
        "complete": solution is not None,
        "publicationEligible": False,
        "solution": None,
    }
    if solution is not None:
        payload["solution"] = {
            "structuralOnlyCount": sum(answer not in human_answers for answer in solution.values()),
            "answers": [
                {
                    "slotIndex": index,
                    "slotId": shape["slots"][index]["slotId"],
                    "answer": answer,
                    "humanLexical": answer in human_answers,
                    "evidence": human_evidence.get(answer, "morphalou-only-structural"),
                    "clue": central_pairs.get(answer, {}).get("clue", ""),
                    "morphology": morphalou.get(answer),
                }
                for index, answer in sorted(solution.items())
            ],
            "mechanicalAudit": mechanical_audit(shape, solution),
        }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "complete": payload["complete"],
        "cap": args.cap,
        "telemetry": payload["telemetry"],
        "structuralOnly": payload.get("solution", {}).get("structuralOnlyCount") if payload.get("solution") else None,
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
    return 0 if solution is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
