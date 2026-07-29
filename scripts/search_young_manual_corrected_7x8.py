#!/usr/bin/env python3
"""Recherche bornée d'un remplissage actuel sur une silhouette 7x8 certifiée.

Ce chercheur ne modifie jamais la silhouette. Il remplit les colonnes de haut
en bas tout en maintenant sept préfixes de lignes, puis ne conserve que les
fermetures exactes. Les réponses déjà actives sont exclues de ce pilote afin de
mesurer la capacité à produire un contenu réellement neuf.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from wordfreq import zipf_frequency

from strict_ribbon_row_dfs import (
    PrefixTrie,
    WordDomain,
    WordRecord,
    _load_forbidden,
    load_records,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY = ROOT / "output/quality/corrected-7x8-shapes/corrected-shape-library.json"

CURRENT = {
    "BOT", "BOX", "BUG", "FAN", "FAQ", "GIF", "GPS", "JOB", "KIT",
    "LOL", "POP", "RAP", "TGV", "WEB", "ZEN", "BLOG", "CAFE", "CHAT",
    "CLIP", "CODE", "COOL", "DATA", "FILM", "FLOW", "FUNK", "GEEK",
    "JAZZ", "KPOP", "LIVE", "LOOK", "MAIL", "MEME", "MOTO", "QUIZ",
    "ROCK", "TAXI", "TEAM", "VELO", "WIFI", "YOGA", "BAGAGE", "BALLON",
    "BANANE", "BARBIE", "BASKET", "BATEAU", "BOULOT", "BRUNCH", "BURGER",
    "BUREAU", "CAMERA", "CASQUE", "CINEMA", "COOKIE", "DISNEY", "EMOJIS",
    "EMPLOI", "EQUIPE", "GAMING", "MOBILE", "PIMENT", "PROFIL", "REPLAY",
    "SERIES", "SELFIE", "STREAM", "STUDIO", "TWITCH", "VALISE", "VOYAGE",
    "ARTISTE", "AUBERGE", "BITCOIN", "CAMPING", "CLAVIER", "CONCERT",
    "CONSOLE", "COSPLAY", "CUISINE", "DANSEUR", "FITNESS", "FROMAGE",
    "GUITARE", "JOGGING", "KARAOKE", "MESSAGE", "MUSIQUE", "NETFLIX",
    "PISCINE", "PODCAST", "POKEMON", "RAPPEUR", "RECETTE", "RESEAUX",
    "SCOOTER", "SPOTIFY", "TRAMWAY", "VOITURE", "WEEKEND", "YOUTUBE",
}
STRONG = {
    "BOX", "BUG", "GIF", "RAP", "WEB", "BLOG", "CLIP", "LIVE", "MEME",
    "WIFI", "BARBIE", "BRUNCH", "BURGER", "CINEMA", "DISNEY", "SELFIE",
    "STREAM", "TWITCH", "CONCERT", "CONSOLE", "NETFLIX", "PODCAST",
    "POKEMON", "SPOTIFY", "YOUTUBE",
}
BRANDS = {
    "BARBIE", "DISNEY", "NETFLIX", "POKEMON", "SPOTIFY", "TWITCH",
    "YOUTUBE",
}


@dataclass(frozen=True)
class Selection:
    answers: frozenset[str] = frozenset()
    families: frozenset[str] = frozenset()
    current: int = 0
    strong: int = 0
    brands: int = 0
    unfamiliar: int = 0


class YoungSearch:
    def __init__(
        self,
        *,
        shape: dict,
        short: list[WordRecord],
        six: list[WordRecord],
        seven: list[WordRecord],
        middle: list[WordRecord],
        seconds: float,
        solution_limit: int,
        seed: int,
    ) -> None:
        self.shape = shape
        self.pivots = {column - 1 for row, column in shape["pivots"] if row == 4}
        self.middle_length = min(self.pivots) if self.pivots else 6
        self.deadline = time.monotonic() + seconds
        self.started = time.monotonic()
        self.solution_limit = solution_limit
        self.nodes = 0
        self.depth = Counter()
        self.rejections = Counter()
        self.timed_out = False
        self.solutions: list[dict] = []

        self.six_records = {record.answer: record for record in six}
        self.seven_records = {record.answer: record for record in seven}
        self.short_records = {record.answer: record for record in short}
        self.middle_records = {record.answer: record for record in middle}
        self.all_records = {
            **self.short_records, **self.six_records, **self.seven_records,
            **self.middle_records,
        }
        self.six_trie = PrefixTrie(self.six_records)
        self.middle_trie = PrefixTrie(self.middle_records)
        self.seven_domain = WordDomain(list(seven), seed)
        self.short_domain = WordDomain(list(short), seed + 1)

    def add(self, selection: Selection, records: tuple[WordRecord, ...]) -> Selection | None:
        answers = set(selection.answers)
        families = set(selection.families)
        current = selection.current
        strong = selection.strong
        brands = selection.brands
        unfamiliar = selection.unfamiliar
        for record in records:
            if record.grammar:
                self.rejections["grammar-or-conjugated-form"] += 1
                return None
            if record.answer in answers:
                self.rejections["duplicate-answer"] += 1
                return None
            if record.family in families:
                self.rejections["duplicate-family"] += 1
                return None
            answers.add(record.answer)
            families.add(record.family)
            current += record.answer in CURRENT
            strong += record.answer in STRONG
            brands += record.answer in BRANDS
            unfamiliar += record.answer not in CURRENT and record.zipf < 3.0
        if brands > 2:
            self.rejections["too-many-brands"] += 1
            return None
        if unfamiliar > 2:
            self.rejections["too-many-unfamiliar"] += 1
            return None
        return Selection(
            frozenset(answers), frozenset(families), current, strong, brands,
            unfamiliar,
        )

    def solve(self) -> list[dict]:
        # Etats des trois lignes hautes, de la ligne médiane et des trois basses.
        self._column(0, (0, 0, 0), 0, (0, 0, 0), Selection(), ())
        return self.solutions

    def _column(
        self,
        column: int,
        top_nodes: tuple[int, int, int],
        middle_node: int,
        bottom_nodes: tuple[int, int, int],
        selection: Selection,
        verticals: tuple[tuple[str, ...], ...],
    ) -> None:
        self.nodes += 1
        self.depth[column] += 1
        if time.monotonic() >= self.deadline:
            self.timed_out = True
            return
        if len(self.solutions) >= self.solution_limit:
            return
        if column == 6:
            self._finish(top_nodes, middle_node, bottom_nodes, selection, verticals)
            return

        if column in self.pivots:
            top_matches = tuple(self.short_domain.matching(
                (self.six_trie,) * 3, top_nodes
            ))
            bottom_matches = tuple(self.short_domain.matching(
                (self.six_trie,) * 3, bottom_nodes
            ))
            for top in top_matches:
                next_top = tuple(
                    self.six_trie.advance(node, top.answer[row])
                    for row, node in enumerate(top_nodes)
                )
                if any(node is None for node in next_top):
                    continue
                for bottom in bottom_matches:
                    selected = self.add(selection, (top, bottom))
                    if selected is None:
                        continue
                    next_bottom = tuple(
                        self.six_trie.advance(node, bottom.answer[row])
                        for row, node in enumerate(bottom_nodes)
                    )
                    if any(node is None for node in next_bottom):
                        continue
                    self._column(
                        column + 1,
                        tuple(int(node) for node in next_top),
                        middle_node,
                        tuple(int(node) for node in next_bottom),
                        selected,
                        verticals + ((top.answer, bottom.answer),),
                    )
                    if self.timed_out or len(self.solutions) >= self.solution_limit:
                        return
            return

        tries = [self.six_trie, self.six_trie, self.six_trie]
        nodes = [*top_nodes]
        constrained_middle = column < self.middle_length
        if constrained_middle:
            tries.append(self.middle_trie)
            nodes.append(middle_node)
        tries.extend((self.six_trie, self.six_trie, self.six_trie))
        nodes.extend(bottom_nodes)

        # WordDomain.matching exige sept positions. Pour un singleton médian,
        # la quatrième lettre est libre : filtrage direct, toujours borné.
        if constrained_middle:
            candidates = self.seven_domain.matching(tuple(tries), tuple(nodes))
        else:
            candidates = self.seven_domain.records
        for record in candidates:
            chars = record.answer
            next_top = tuple(
                self.six_trie.advance(node, chars[row])
                for row, node in enumerate(top_nodes)
            )
            next_bottom = tuple(
                self.six_trie.advance(node, chars[row + 4])
                for row, node in enumerate(bottom_nodes)
            )
            if any(node is None for node in (*next_top, *next_bottom)):
                continue
            next_middle = middle_node
            if constrained_middle:
                advanced = self.middle_trie.advance(middle_node, chars[3])
                if advanced is None:
                    continue
                next_middle = advanced
            selected = self.add(selection, (record,))
            if selected is None:
                continue
            self._column(
                column + 1,
                tuple(int(node) for node in next_top),
                int(next_middle),
                tuple(int(node) for node in next_bottom),
                selected,
                verticals + ((record.answer,),),
            )
            if self.timed_out or len(self.solutions) >= self.solution_limit:
                return

    def _finish(
        self,
        top_nodes: tuple[int, int, int],
        middle_node: int,
        bottom_nodes: tuple[int, int, int],
        selection: Selection,
        verticals: tuple[tuple[str, ...], ...],
    ) -> None:
        row_answers = [self.six_trie.terminal[node] for node in (*top_nodes, *bottom_nodes)]
        middle = self.middle_trie.terminal[middle_node]
        if any(answer is None for answer in row_answers) or middle is None:
            self.rejections["non-terminal-row"] += 1
            return
        records = tuple(self.all_records[str(answer)] for answer in (*row_answers[:3], middle, *row_answers[3:]))
        final = self.add(selection, records)
        if final is None:
            return
        if final.current < 1:
            self.rejections["not-enough-current"] += 1
            return
        if final.strong < 1:
            self.rejections["no-strong-current"] += 1
            return

        by_slot = {}
        vertical_queue = list(verticals)
        top_rows = list(row_answers[:3])
        bottom_rows = list(row_answers[3:])
        for slot in self.shape["slots"]:
            direction = slot["direction"]
            clue_row, clue_column = slot["clueCell"]
            if direction == "down":
                column = clue_column - 1
                item = vertical_queue[column]
                answer = item[0] if clue_row == 0 else item[1]
            elif clue_row < 4:
                answer = top_rows[clue_row - 1]
            elif clue_row == 4:
                answer = middle
            else:
                answer = bottom_rows[clue_row - 5]
            by_slot[str(slot["slotIndex"])] = answer

        ordered = [by_slot[str(slot["slotIndex"])] for slot in self.shape["slots"]]
        self.solutions.append({
            "candidateId": f"young-manual-{self.shape['shapeId']}-{len(self.solutions)+1:02d}",
            "shapeId": self.shape["shapeId"],
            "slotAnswers": by_slot,
            "answers": ordered,
            "matrix": [*top_rows, None, *bottom_rows],
            "currentAnswers": sorted(answer for answer in final.answers if answer in CURRENT),
            "strongAnswers": sorted(answer for answer in final.answers if answer in STRONG),
            "brandAnswers": sorted(answer for answer in final.answers if answer in BRANDS),
            "unfamiliarAnswers": sorted(
                answer for answer in final.answers
                if answer not in CURRENT and self.all_records[answer].zipf < 3.0
            ),
            "answerZipf": {
                answer: round(self.all_records[answer].zipf, 3)
                for answer in ordered
            },
        })

    def telemetry(self) -> dict:
        return {
            "status": "found" if self.solutions else "cutoff" if self.timed_out else "dead",
            "elapsedSeconds": round(time.monotonic() - self.started, 3),
            "nodes": self.nodes,
            "depthVisits": {str(key): value for key, value in sorted(self.depth.items())},
            "rejections": dict(sorted(self.rejections.items())),
            "candidateCount": len(self.solutions),
        }


def load_shape(path: Path, shape_id: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    shape = next((item for item in payload["shapes"] if item["shapeId"] == shape_id), None)
    if shape is None:
        raise SystemExit(f"Silhouette inconnue: {shape_id}")
    return shape


def prepare_records() -> tuple[dict[int, list[WordRecord]], Counter[str]]:
    six, seven, short, middle, _ = load_records(
        minimum_zipf=2.0,
        minimum_constructor_score=5.0,
        pilot_safe_short_only=True,
        short_minimum_zipf=2.0,
        short_minimum_constructor_score=5.0,
    )
    _, active = _load_forbidden()
    pools = {3: short, 4: middle[4], 5: middle[5], 6: six, 7: seven}
    for length, records in pools.items():
        by_answer = {record.answer: record for record in records if not active[record.answer]}
        for answer in CURRENT:
            if len(answer) != length or active[answer]:
                continue
            existing = by_answer.get(answer)
            by_answer[answer] = WordRecord(
                answer=answer,
                score=(existing.score if existing else 75.0) + (1500 if answer in STRONG else 900),
                zipf=existing.zipf if existing else float(zipf_frequency(answer.lower(), "fr")),
                family=existing.family if existing else "",
                image=existing.image if existing else False,
                grammar=False,
            )
        pools[length] = sorted(by_answer.values(), key=lambda item: (-item.score, item.answer))
    return pools, active


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shape-library", type=Path, default=DEFAULT_LIBRARY)
    parser.add_argument(
        "--shape-id",
        choices=tuple(f"corrected-7x8-{index:02d}" for index in (3, 5, 6, 7)),
        default="corrected-7x8-05",
    )
    parser.add_argument("--seconds", type=float, default=35.0)
    parser.add_argument("--solution-limit", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20260721)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    shape = load_shape(args.shape_library, args.shape_id)
    pools, active = prepare_records()
    middle_length = min(column - 1 for row, column in shape["pivots"] if row == 4)
    search = YoungSearch(
        shape=shape,
        short=pools[3],
        six=pools[6],
        seven=pools[7],
        middle=pools[middle_length],
        seconds=args.seconds,
        solution_limit=args.solution_limit,
        seed=args.seed,
    )
    candidates = search.solve()
    payload = {
        "version": 1,
        "kind": "motman-young-manual-corrected-7x8-search",
        "shapeId": args.shape_id,
        "catalogModified": False,
        "runtimeModified": False,
        "publicationEligible": False,
        "policy": {
            "activeAnswers": "hard-excluded-for-this-pilot",
            "minimumCurrentAnswers": 1,
            "minimumStrongCurrentAnswers": 1,
            "maximumBrandsOrFranchises": 2,
            "maximumUnfamiliarAnswers": 2,
            "grammarOrConjugatedForms": "hard-excluded",
        },
        "activeAnswerCount": len(active),
        "poolCounts": {str(length): len(records) for length, records in pools.items()},
        "telemetry": search.telemetry(),
        "candidates": candidates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **payload["telemetry"]}, ensure_ascii=False, indent=2))
    return 0 if candidates else 3 if search.timed_out else 2


if __name__ == "__main__":
    raise SystemExit(main())
