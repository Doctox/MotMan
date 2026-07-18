"""Build the small, human-edited MotMan reference set.

The solver may propose a crossing fill, but every answer and every clue below is
explicitly accepted by an editor.  This file is therefore the reproducible
source of truth for the pilot, not a generated corpus or a scraped grid.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from grid_topology import audit_grid_topology, render_topology_html


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "src/data/grid-generation-handcrafted/reference.pilot.json"
DEFAULT_AUDIT = ROOT / "output/quality/handcrafted-reference-pilot-audit.json"
DEFAULT_HTML = ROOT / "output/quality/handcrafted-reference-pilot.html"

DIRECTIONS = {"across": (0, 1), "down": (1, 0)}

# # = case définition, . = case lettre.  The top-left # is neutral.
EASY_01_PATTERN = (
    "####..###",
    "#...##...",
    "#..#.....",
    "#.#......",
    ".#.....#.",
    ".#....#.#",
    "#..#.#...",
    "#...#....",
    "#.....#..",
    "#...#....",
)

EASY_01_ANSWERS = (
    "IL", "BAS", "PIC", "ON", "BALLE", "REMUER", "COTES", "HIER",
    "FA", "DOS", "ARC", "BOUE", "IMAGE", "LU", "MER", "CIEL",
    "BOL", "AN", "PLUS", "ILE", "CERF", "BETES", "AMER", "ROI",
    "OR", "CHARME", "POULE", "FAIM", "DO", "SEUL", "CAR", "BEC",
)

EASY_01_CLUES = {
    "IL": "Pronom masculin",
    "BAS": "En dessous",
    "PIC": "Sommet pointu",
    "ON": "Pronom indéfini",
    "BALLE": "Petite sphère",
    "REMUER": "Bouger vivement",
    "COTES": "Bords marins",
    "HIER": "Jour précédent",
    "FA": "Après mi",
    "DOS": "Arrière du corps",
    "ARC": "Arme courbée",
    "BOUE": "Terre mouillée",
    "IMAGE": "Dessin ou photo",
    "LU": "Parcouru des yeux",
    "MER": "Grande eau salée",
    "CIEL": "Voûte bleue",
    "BOL": "",
    "AN": "Douze mois",
    "PLUS": "Davantage",
    "ILE": "Entourée d'eau",
    "CERF": "Porte des bois",
    "BETES": "Animaux",
    "AMER": "Goût du pamplemousse",
    "ROI": "",
    "OR": "Métal précieux",
    "CHARME": "Pouvoir de plaire",
    "POULE": "",
    "FAIM": "Besoin de manger",
    "DO": "Avant ré",
    "SEUL": "Sans compagnie",
    "CAR": "Autocar",
    "BEC": "Bouche d'oiseau",
}

EASY_01_IMAGES = {
    answer: {
        "asset": f"/assets/clues/twemoji/{answer.lower()}.svg",
        "alt": answer.capitalize(),
        "source": "Twemoji",
        "license": "CC BY 4.0",
    }
    for answer in ("BOL", "ROI", "POULE")
}

NORMAL_01_PATTERN = (
    "###..####",
    "#..##....",
    "#........",
    "#......#.",
    "#.#...#.#",
    ".#..#....",
    ".#.#.#...",
    "#........",
    "#.....#..",
    "#........",
)

NORMAL_01_ANSWERS = (
    "SI", "AN", "EPIS", "MEGAPOLE", "AZIMUT", "TIR", "RE", "ETAT",
    "AGE", "ATTENUER", "NEIGE", "OR", "ESCOMPTE", "AMAS", "NEZ",
    "EPURE", "POT", "IL", "SEC", "GITE", "AMI", "CAGEOT", "ON",
    "RITES", "TAU", "TERRE", "LEGO", "ANE", "TIC", "NEM",
)

NORMAL_01_CLUES = {
    "SI": "Note après la",
    "AN": "Tour du calendrier",
    "EPIS": "Têtes de blé",
    "MEGAPOLE": "Ville géante",
    "AZIMUT": "Angle de direction",
    "TIR": "Action de viser",
    "RE": "Note après do",
    "ETAT": "Nation organisée",
    "AGE": "Nombre d'années",
    "ATTENUER": "Rendre moins fort",
    "NEIGE": "",
    "OR": "Métal des médailles",
    "ESCOMPTE": "Réduction commerciale",
    "AMAS": "Tas compact",
    "NEZ": "",
    "EPURE": "Dessin technique",
    "POT": "Récipient en terre",
    "IL": "Pronom masculin",
    "SEC": "Sans humidité",
    "GITE": "Logement de passage",
    "AMI": "Proche choisi",
    "CAGEOT": "Caisse à légumes",
    "ON": "Pronom indéfini",
    "RITES": "Gestes cérémoniels",
    "TAU": "T grec",
    "TERRE": "Notre planète",
    "LEGO": "Marque de briques",
    "ANE": "Cousin du cheval",
    "TIC": "Geste involontaire",
    "NEM": "Rouleau vietnamien",
}

NORMAL_01_IMAGES = {
    answer: {
        "asset": f"/assets/clues/twemoji/{answer.lower()}.svg",
        "alt": answer.capitalize(),
        "source": "Twemoji",
        "license": "CC BY 4.0",
    }
    for answer in ("NEIGE", "NEZ")
}

NORMAL_01_DIFFICULTIES = {
    **{answer: "easy" for answer in (
        "SI", "RE", "NEIGE", "OR", "NEZ", "IL", "ON", "TERRE", "ANE",
    )},
    **{answer: "hard" for answer in ("AZIMUT", "EPURE", "TAU")},
}

NORMAL_02_PATTERN = (
    "####..###",
    "#...##...",
    "#........",
    "#.....#..",
    "#..#...#.",
    "#....#...",
    "#.#.#...#",
    ".#...#...",
    ".#..#....",
    "#....#...",
)

NORMAL_02_ANSWERS = (
    "SI", "BAL", "AIR", "EVIDENCE", "SITOT", "IV", "AS", "SEL",
    "COTE", "AME", "CRI", "FIN", "BLE", "OR", "FILS", "PIED", "NET",
    "BESACE", "AVISO", "LIT", "AN", "ICI", "REVUE", "DOSE", "ETE",
    "LARBIN", "TAIRE", "MILLE", "IA", "FOI", "EST",
)

NORMAL_02_CLUES = {
    "SI": "Introduit une condition",
    "BAL": "Soirée des débutantes",
    "AIR": "Morceau à fredonner",
    "EVIDENCE": "S'impose naturellement",
    "SITOT": "Sans aucun délai",
    "IV": "Quatre, à Rome",
    "AS": "Carte ou champion",
    "SEL": "Fleur de Guérande",
    "COTE": "Valeur boursière",
    "AME": "Principe vital",
    "CRI": "Voix de détresse",
    "FIN": "Dernier acte",
    "BLE": "Or des moissons",
    "OR": "But des alchimistes",
    "FILS": "Descendant masculin",
    "PIED": "",
    "NET": "Sans bavure",
    "BESACE": "Sac de pèlerin",
    "AVISO": "Navire d'escorte",
    "LIT": "Meuble horizontal",
    "AN": "Révolution terrestre",
    "ICI": "En ce lieu",
    "REVUE": "Publication périodique",
    "DOSE": "Partie prescrite",
    "ETE": "Temps des moissons",
    "LARBIN": "Domestique servile",
    "TAIRE": "Garder sous silence",
    "MILLE": "Dix centaines",
    "IA": "Esprit artificiel",
    "FOI": "Vertu théologale",
    "EST": "Levant cardinal",
}

NORMAL_02_IMAGES = {
    "PIED": {
        "asset": "/assets/clues/twemoji/pied.svg",
        "alt": "Pied",
        "source": "Twemoji",
        "license": "CC BY 4.0",
    }
}

NORMAL_02_EASY = {"SI", "AIR", "AS", "FIN", "OR", "PIED", "ICI"}
NORMAL_02_HARD = {"SITOT", "BESACE", "AVISO", "LARBIN", "FOI"}

NORMAL_03_PATTERN = (
    "####..###",
    "#...##...",
    "#........",
    "#....#...",
    "#.#...#.#",
    ".#.....#.",
    ".#.#.....",
    "#...#....",
    "#...#....",
    "#....#...",
)

NORMAL_03_ANSWERS = (
    "OS", "ANS", "PRE", "BOUCLIER", "UNIR", "EVE", "TAC", "PECHE",
    "KARMA", "CAP", "TRES", "AIL", "SENS", "SEIN", "RUE", "ABUS",
    "NON", "SUITE", "PIE", "REVE", "ERE", "CRACK", "CHATS", "LA",
    "PLAIE", "ERRER", "TASSE", "MENU", "CAS", "PLI",
)

NORMAL_03_CLUES = {
    "OS": "Pièce du squelette",
    "ANS": "Tours du Soleil",
    "PRE": "Domaine de Pan",
    "BOUCLIER": "Attribut d'Athéna",
    "UNIR": "Faire alliance",
    "EVE": "Première exilée",
    "TAC": "Réponse du tic",
    "PECHE": "Faute originelle",
    "KARMA": "Poids des actes",
    "CAP": "Pointe marine",
    "TRES": "Fortement",
    "AIL": "Chasse-vampires",
    "SENS": "Facultés corporelles",
    "SEIN": "Giron maternel",
    "RUE": "Plante amère",
    "ABUS": "Excès de pouvoir",
    "NON": "Mot du refus",
    "SUITE": "Danses baroques",
    "PIE": "Oiseau de Rossini",
    "REVE": "Songe nocturne",
    "ERE": "Temps géologique",
    "CRACK": "Champion hippique",
    "CHATS": "Félins de Bastet",
    "LA": "Note du diapason",
    "PLAIE": "Fléau d'Égypte",
    "ERRER": "Marcher sans but",
    "TASSE": "",
    "MENU": "Carte du repas",
    "CAS": "Sujet clinique",
    "PLI": "Secret d'origami",
}

NORMAL_03_IMAGES = {
    "TASSE": {
        "asset": "/assets/clues/twemoji/tasse.svg",
        "alt": "Tasse",
        "source": "Twemoji",
        "license": "CC BY 4.0",
    }
}

NORMAL_03_EASY = {"OS", "ANS", "UNIR", "CAP", "NON", "TASSE", "MENU"}
NORMAL_03_HARD = {"PRE", "KARMA", "RUE", "PIE", "CRACK"}


def clue_cells(pattern: tuple[str, ...]) -> set[tuple[int, int]]:
    return {
        (row, col)
        for row, line in enumerate(pattern)
        for col, value in enumerate(line)
        if value == "#"
    }


def direct_slots(pattern: tuple[str, ...]) -> list[dict]:
    rows, columns = len(pattern), len(pattern[0])
    clues = clue_cells(pattern)
    slots = []
    for direction, (dr, dc) in DIRECTIONS.items():
        arrow = "right" if direction == "across" else "down"
        for clue in sorted(clues):
            if clue == (0, 0):
                continue
            current = (clue[0] + dr, clue[1] + dc)
            cells = []
            while 0 <= current[0] < rows and 0 <= current[1] < columns and current not in clues:
                cells.append(current)
                current = (current[0] + dr, current[1] + dc)
            if len(cells) >= 2:
                slots.append({
                    "direction": direction,
                    "arrow": arrow,
                    "clueCell": list(clue),
                    "cells": [list(cell) for cell in cells],
                })
    return slots


def build_easy_01() -> dict:
    slots = direct_slots(EASY_01_PATTERN)
    if len(slots) != len(EASY_01_ANSWERS):
        raise ValueError(f"silhouette: {len(slots)} chemins pour {len(EASY_01_ANSWERS)} réponses")
    words = []
    grid_id = "reference-easy-child-01"
    for index, (slot, answer) in enumerate(zip(slots, EASY_01_ANSWERS)):
        if len(slot["cells"]) != len(answer):
            raise ValueError(f"{answer}: longueur {len(answer)} != chemin {len(slot['cells'])}")
        image = EASY_01_IMAGES.get(answer)
        clue = EASY_01_CLUES[answer]
        words.append({
            "wordId": f"{grid_id}:word:{index + 1:02d}",
            "answer": answer,
            "clue": clue,
            "sourceClue": clue or f"Indice illustré : {image['alt'].casefold()}",
            "definitionStatus": "reviewed",
            "editorialStatus": "human-reviewed" if not image else "image-reviewed",
            "sourceType": "editorial-original" if not image else "image",
            "sourceId": "motman-original-child-pilot" if not image else f"twemoji-{answer.lower()}",
            "sourceUrl": "https://www.lexique.org/" if not image else (
                f"https://github.com/jdecked/twemoji/blob/master/assets/svg/{answer.lower()}.svg"
            ),
            "difficulty": "normal" if answer == "CHARME" else "easy",
            "audienceEvidence": "human-reviewed-child-7-14",
            "conceptGroup": {"COTES": "COTE", "BETES": "BETE"}.get(answer, answer),
            "semanticConflicts": [],
            **slot,
            **({"image": image} if image else {}),
        })
    grid = {
        "id": grid_id,
        "columns": 9,
        "rows": 10,
        "difficulty": "easy",
        "audience": "enfants de 7 à 14 ans",
        "clueCells": [list(cell) for cell in sorted(clue_cells(EASY_01_PATTERN))],
        "words": words,
        "difficultyMix": dict(Counter(word["difficulty"] for word in words)),
        "imageCount": len(EASY_01_IMAGES),
        "publicationStatus": "owner-approved-staging",
        "humanReview": {
            "status": "approved",
            "reviewedAt": "2026-07-14",
            "note": "Grille approuvée visuellement par le propriétaire comme grille étalon.",
        },
        "provenance": {
            "answers": "Lexique 3.83 et liste scolaire Éduscol",
            "clues": "Formulations originales MotMan, revue manuelle du 2026-07-14",
            "geometry": "Remplissage sous contraintes puis acceptation mot par mot",
        },
    }
    report = audit_grid_topology(grid)
    if not report["valid"]:
        raise ValueError(f"grille enfant invalide: {report['errorCounts']}")
    grid["reviewSummary"] = {
        "topologyValid": True,
        "images": len(EASY_01_IMAGES),
        "errors": 0,
        "layoutMetrics": report["layoutMetrics"],
    }
    return grid


def build_normal_01() -> dict:
    slots = direct_slots(NORMAL_01_PATTERN)
    if len(slots) != len(NORMAL_01_ANSWERS):
        raise ValueError(
            f"silhouette normale: {len(slots)} chemins pour "
            f"{len(NORMAL_01_ANSWERS)} réponses"
        )
    words = []
    grid_id = "reference-normal-adult-01"
    for index, (slot, answer) in enumerate(zip(slots, NORMAL_01_ANSWERS)):
        if len(slot["cells"]) != len(answer):
            raise ValueError(
                f"{answer}: longueur {len(answer)} != chemin {len(slot['cells'])}"
            )
        image = NORMAL_01_IMAGES.get(answer)
        clue = NORMAL_01_CLUES[answer]
        difficulty = NORMAL_01_DIFFICULTIES.get(answer, "normal")
        words.append({
            "wordId": f"{grid_id}:word:{index + 1:02d}",
            "answer": answer,
            "clue": clue,
            "sourceClue": clue or f"Indice illustré : {image['alt'].casefold()}",
            "definitionStatus": "reviewed",
            "editorialStatus": "human-reviewed" if not image else "image-reviewed",
            "sourceType": "editorial-original" if not image else "image",
            "sourceId": "motman-original-normal-pilot" if not image else f"twemoji-{answer.lower()}",
            "sourceUrl": "https://www.lexique.org/" if not image else (
                f"https://github.com/jdecked/twemoji/blob/master/assets/svg/{answer.lower()}.svg"
            ),
            "difficulty": difficulty,
            "audienceEvidence": "human-reviewed-general-adult",
            "conceptGroup": answer,
            "semanticConflicts": [],
            **slot,
            **({"image": image} if image else {}),
        })
    grid = {
        "id": grid_id,
        "columns": 9,
        "rows": 10,
        "difficulty": "normal",
        "audience": "adultes grand public",
        "clueCells": [list(cell) for cell in sorted(clue_cells(NORMAL_01_PATTERN))],
        "words": words,
        "difficultyMix": dict(Counter(word["difficulty"] for word in words)),
        "imageCount": len(NORMAL_01_IMAGES),
        "publicationStatus": "owner-approved-staging",
        "humanReview": {
            "status": "approved",
            "reviewedAt": "2026-07-14",
            "note": "Grille normale approuvée par le propriétaire.",
        },
        "provenance": {
            "answers": "Lexique 3.83, filtrage de fréquence et revue mot par mot",
            "clues": "Formulations originales MotMan, revue manuelle du 2026-07-14",
            "geometry": "Silhouette directe distincte puis remplissage sous contraintes",
        },
    }
    report = audit_grid_topology(grid)
    if not report["valid"]:
        raise ValueError(f"grille normale invalide: {report['errorCounts']}")
    grid["reviewSummary"] = {
        "topologyValid": True,
        "images": len(NORMAL_01_IMAGES),
        "errors": 0,
        "layoutMetrics": report["layoutMetrics"],
    }
    return grid


def build_normal_02() -> dict:
    slots = direct_slots(NORMAL_02_PATTERN)
    if len(slots) != len(NORMAL_02_ANSWERS):
        raise ValueError(
            f"seconde silhouette normale: {len(slots)} chemins pour "
            f"{len(NORMAL_02_ANSWERS)} réponses"
        )
    words = []
    grid_id = "reference-normal-adult-02"
    for index, (slot, answer) in enumerate(zip(slots, NORMAL_02_ANSWERS)):
        if len(slot["cells"]) != len(answer):
            raise ValueError(
                f"{answer}: longueur {len(answer)} != chemin {len(slot['cells'])}"
            )
        image = NORMAL_02_IMAGES.get(answer)
        clue = NORMAL_02_CLUES[answer]
        difficulty = (
            "easy" if answer in NORMAL_02_EASY
            else "hard" if answer in NORMAL_02_HARD
            else "normal"
        )
        words.append({
            "wordId": f"{grid_id}:word:{index + 1:02d}",
            "answer": answer,
            "clue": clue,
            "sourceClue": clue or f"Indice illustré : {image['alt'].casefold()}",
            "definitionStatus": "reviewed",
            "editorialStatus": "human-reviewed" if not image else "image-reviewed",
            "sourceType": "editorial-original" if not image else "image",
            "sourceId": "motman-original-normal-pilot-02" if not image else f"twemoji-{answer.lower()}",
            "sourceUrl": "https://www.lexique.org/" if not image else (
                f"https://github.com/jdecked/twemoji/blob/master/assets/svg/{answer.lower()}.svg"
            ),
            "difficulty": difficulty,
            "audienceEvidence": "human-reviewed-general-adult",
            "conceptGroup": answer,
            "semanticConflicts": [],
            **slot,
            **({"image": image} if image else {}),
        })
    grid = {
        "id": grid_id,
        "columns": 9,
        "rows": 10,
        "difficulty": "normal",
        "audience": "adultes, niveau grand public intermédiaire",
        "clueCells": [list(cell) for cell in sorted(clue_cells(NORMAL_02_PATTERN))],
        "words": words,
        "difficultyMix": dict(Counter(word["difficulty"] for word in words)),
        "imageCount": len(NORMAL_02_IMAGES),
        "publicationStatus": "owner-approved-staging",
        "humanReview": {
            "status": "approved",
            "reviewedAt": "2026-07-14",
            "note": "Grille approuvée puis reclassée en normal par le propriétaire.",
        },
        "provenance": {
            "answers": "Lexique 3.83, fréquence renforcée sur les croisements courts",
            "clues": "Formulations originales MotMan, revue manuelle du 2026-07-14",
            "geometry": "Silhouette directe distincte puis remplissage sous contraintes",
        },
    }
    report = audit_grid_topology(grid)
    if not report["valid"]:
        raise ValueError(f"seconde grille normale invalide: {report['errorCounts']}")
    grid["reviewSummary"] = {
        "topologyValid": True,
        "images": len(NORMAL_02_IMAGES),
        "errors": 0,
        "layoutMetrics": report["layoutMetrics"],
    }
    return grid


def build_normal_03() -> dict:
    slots = direct_slots(NORMAL_03_PATTERN)
    if len(slots) != len(NORMAL_03_ANSWERS):
        raise ValueError(
            f"troisième silhouette normale: {len(slots)} chemins pour "
            f"{len(NORMAL_03_ANSWERS)} réponses"
        )
    words = []
    grid_id = "reference-normal-adult-03"
    for index, (slot, answer) in enumerate(zip(slots, NORMAL_03_ANSWERS)):
        if len(slot["cells"]) != len(answer):
            raise ValueError(
                f"{answer}: longueur {len(answer)} != chemin {len(slot['cells'])}"
            )
        image = NORMAL_03_IMAGES.get(answer)
        clue = NORMAL_03_CLUES[answer]
        difficulty = (
            "easy" if answer in NORMAL_03_EASY
            else "hard" if answer in NORMAL_03_HARD
            else "normal"
        )
        words.append({
            "wordId": f"{grid_id}:word:{index + 1:02d}",
            "answer": answer,
            "clue": clue,
            "sourceClue": clue or f"Indice illustré : {image['alt'].casefold()}",
            "definitionStatus": "reviewed",
            "editorialStatus": "human-reviewed" if not image else "image-reviewed",
            "sourceType": "editorial-original" if not image else "image",
            "sourceId": "motman-original-normal-pilot-03" if not image else f"twemoji-{answer.lower()}",
            "sourceUrl": "https://www.lexique.org/" if not image else (
                f"https://github.com/jdecked/twemoji/blob/master/assets/svg/{answer.lower()}.svg"
            ),
            "difficulty": difficulty,
            "audienceEvidence": "owner-classified-general-adult",
            "conceptGroup": answer,
            "semanticConflicts": [],
            **slot,
            **({"image": image} if image else {}),
        })
    grid = {
        "id": grid_id,
        "columns": 9,
        "rows": 10,
        "difficulty": "normal",
        "audience": "adultes, niveau grand public intermédiaire",
        "clueCells": [list(cell) for cell in sorted(clue_cells(NORMAL_03_PATTERN))],
        "words": words,
        "difficultyMix": dict(Counter(word["difficulty"] for word in words)),
        "imageCount": len(NORMAL_03_IMAGES),
        "publicationStatus": "owner-approved-staging",
        "humanReview": {
            "status": "approved",
            "reviewedAt": "2026-07-14",
            "note": "Silhouette approuvée et contenu classé normal par le propriétaire.",
        },
        "provenance": {
            "answers": "Lexique 3.83, formes canoniques et fréquence minimale contrôlée",
            "clues": "Formulations originales MotMan, classées normales par le propriétaire",
            "geometry": "Recherche conjointe silhouette-remplissage, flèches directes uniquement",
        },
    }
    report = audit_grid_topology(grid)
    if not report["valid"]:
        raise ValueError(f"troisième grille normale invalide: {report['errorCounts']}")
    grid["reviewSummary"] = {
        "topologyValid": True,
        "images": len(NORMAL_03_IMAGES),
        "errors": 0,
        "layoutMetrics": report["layoutMetrics"],
    }
    return grid


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    args = parser.parse_args()
    grids = [build_easy_01(), build_normal_01(), build_normal_02(), build_normal_03()]
    reports = [audit_grid_topology(grid) for grid in grids]
    document = {
        "version": 1,
        "kind": "handcrafted-reference-pilot",
        "publicationPolicy": "Staging only until explicit visual and human play review.",
        "grids": grids,
    }
    for path in (args.output, args.audit, args.html):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    args.audit.write_text(json.dumps({
        "version": 1,
        "valid": all(report["valid"] for report in reports),
        "grids": reports,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    args.html.write_text(
        render_topology_html(reports, title="Pilotes MotMan édités manuellement"),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "built",
        "grids": [grid["id"] for grid in grids],
        "valid": all(report["valid"] for report in reports),
        "html": str(args.html),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
