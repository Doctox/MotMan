#!/usr/bin/env python3
"""Audit humain ciblé du catalogue actif: sensibilité et obscurité.

Ce rapport ne modifie jamais le catalogue. Les listes ci-dessous sont une
revue éditoriale explicite, pas une détection par mot-clé: un mot religieux
courant (IMAM, PAPE, ÉGLISE, etc.) est inventorié mais n'est pas rejeté.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "src/data/grid.catalog.json"
OUTPUT = ROOT / "output/quality/active-catalog-editorial-risk-audit.json"


# (grid id, answer) -> (classification, note)
SENSITIVE = {
    ("reference-normal-adult-02", "FOI"): ("acceptable-courant", "Notion religieuse courante, indice explicite."),
    ("reference-normal-adult-01", "RITES"): ("acceptable-courant", "Terme générique de cérémonie, pas une communauté ciblée."),
    ("reference-normal-adult-03", "BOUCLIER"): ("acceptable-culture", "Référence mythologique à Athéna."),
    ("reference-normal-adult-03", "EVE"): ("acceptable-culture", "Référence biblique connue."),
    ("reference-normal-adult-03", "KARMA"): ("acceptable-courant", "Notion religieuse devenue courante en français."),
    ("reference-normal-adult-03", "PECHE"): ("acceptable-culture", "Référence biblique connue mais plus détournée."),
    ("reference-normal-adult-03", "PLAIE"): ("acceptable-culture", "Référence biblique connue."),
    ("reference-normal-adult-03", "CHATS"): ("acceptable-culture", "Référence mythologique à Bastet."),
    ("calibration-normal-upper-01", "NEF"): ("acceptable-courant", "Vocabulaire d'église courant."),
    ("calibration-normal-upper-01", "EMIR"): ("acceptable-courant", "Titre historique courant; ne pas rejeter pour motif religieux."),
    ("calibration-normal-upper-01", "FROC"): ("a-revoir", "Référence monastique et terme vieillissant."),
    ("calibration-hard-02", "ICONE"): ("acceptable-culture", "Sens religieux orthodoxe clair."),
    ("calibration-hard-02", "GUI"): ("acceptable-culture", "Référence culturelle aux druides, mot courant."),
    ("reference-standard-12", "ATHEE"): ("acceptable-courant", "Mot français courant."),
    ("reference-standard-12", "DIEU"): ("acceptable-courant", "Mot français courant."),
    ("reference-standard-13", "NEF"): ("acceptable-courant", "Vocabulaire d'église courant."),
    ("reference-standard-15", "TOTEM"): ("a-revoir", "Notion culturelle autochtone simplifiée par 'emblème tribal'."),
    ("reference-standard-21", "NEF"): ("acceptable-courant", "Vocabulaire d'église courant."),
    ("reference-standard-21", "CURE"): ("acceptable-courant", "Fonction religieuse courante et indice clair."),
    ("reference-standard-22", "ENFER"): ("acceptable-courant", "Notion courante."),
    ("reference-standard-24", "EDEN"): ("acceptable-culture", "Référence biblique courante."),
    ("reference-standard-25", "CREDO"): ("acceptable-courant", "Expression courante et indice explicite."),
    ("corpus-aware-review-03", "LEVITES"): ("probleme-specialise", "Nom religieux spécialisé; trop peu courant pour le jeu généraliste."),
    ("corpus-aware-review-03", "MANITOU"): ("a-revoir", "Référence culturelle autochtone simplifiée; contexte à relire."),
    ("corpus-aware-review-05", "IFTAR"): ("acceptable-courant", "Mot désormais courant, définition directe."),
    ("central-priority-review-01", "ABBE"): ("acceptable-courant", "Fonction religieuse courante."),
    ("central-priority-review-03", "CREDO"): ("acceptable-courant", "Sens figuré courant."),
    ("central-priority-review-03", "ORIENTAL"): ("probleme-couple", "'Venu d'Asie' réduit oriental à une origine trop large et ambiguë."),
    ("central-priority-review-04", "MINARETS"): ("acceptable-courant", "Élément architectural connu et indice clair."),
    ("fresh-quality-pilot-01", "IMAM"): ("acceptable-courant", "Fonction religieuse courante et indice clair."),
    ("image-rich-review-02", "ARABE"): ("probleme-couple", "Bédouin n'est pas synonyme d'Arabe; couple réducteur et factuellement faux."),
    ("reference-standard-30", "CASTE"): ("acceptable-courant", "Notion sociale générique, indice clair."),
    ("reference-standard-22", "BEY"): ("a-revoir", "Titre ottoman peu courant."),
    ("review-20260715-01", "PAPES"): ("acceptable-courant", "Mot courant; le pluriel est correct pour 'Chefs du Vatican'."),
    ("review-20260715-01", "BEY"): ("a-revoir", "Titre ottoman peu courant."),
    ("review-20260715-02", "CADI"): ("probleme-specialise", "Titre juridique musulman trop spécialisé pour une grille grand public."),
    ("review-20260715-02", "CASTE"): ("acceptable-courant", "Notion sociale générique, indice clair."),
    ("dynamic-reference-c-02-refined", "RITE"): ("acceptable-courant", "Terme générique de cérémonie."),
}


OBSCURE = {
    ("reference-normal-adult-01", "AZIMUT"): "Terme technique de navigation.",
    ("reference-normal-adult-01", "EPURE"): "Terme technique de dessin.",
    ("reference-normal-adult-02", "AVISO"): "Type de navire peu connu.",
    ("reference-normal-adult-03", "RUE"): "Le sens botanique 'plante amère' est très peu connu.",
    ("reference-normal-adult-03", "PIE"): "Le détour par Rossini est artificiel.",
    ("calibration-normal-upper-01", "ERRE"): "Sens nautique peu courant.",
    ("calibration-normal-upper-01", "LEV"): "Monnaie bulgare peu familière.",
    ("reference-standard-18", "ALOI"): "Vocabulaire métallurgique peu courant.",
    ("repetition-renovation-09", "RIS"): "Sens culinaire peu connu et souvent répété.",
    ("reference-standard-21", "UT"): "Ancien nom de note, peu naturel.",
    ("reference-standard-23", "LACIS"): "Nom rare pour un enchevêtrement.",
    ("reference-standard-23", "ECU"): "Ancienne monnaie, réponse de remplissage typique.",
    ("repetition-renovation-26", "RIA"): "Terme géographique spécialisé.",
    ("reference-standard-27", "ALOI"): "Vocabulaire métallurgique peu courant.",
    ("reference-standard-30", "LICE"): "Sens 'arène' vieilli.",
    ("reference-standard-30", "GIRON"): "Sens figuré vieilli et difficile à deviner.",
    ("corpus-aware-review-03", "ESTER"): "Verbe juridique spécialisé.",
    ("corpus-aware-review-03", "ACROMION"): "Anatomie spécialisée.",
    ("corpus-aware-review-03", "TARSE"): "Anatomie spécialisée.",
    ("corpus-aware-review-03", "AVINES"): "Adjectif rare et formulation peu naturelle.",
    ("corpus-aware-review-03", "LEVITES"): "Nom historique/religieux spécialisé.",
    ("corpus-aware-review-03", "VELUM"): "Terme anatomique rare.",
    ("corpus-aware-review-05", "TRIDI"): "Calendrier républicain spécialisé.",
    ("central-priority-review-01", "ICIBAS"): "Adverbe littéraire vieillissant.",
    ("central-priority-review-02", "IVOIRINE"): "Adjectif rare.",
    ("central-priority-review-02", "ORESTE"): "Nom mythologique moins grand public.",
    ("central-priority-review-02", "EIDER"): "Canard peu connu.",
    ("central-priority-review-03", "CELERITE"): "Nom soutenu, difficile pour le public visé.",
    ("central-priority-review-03", "HALON"): "Gaz technique peu connu.",
    ("central-priority-review-04", "ENDOS"): "Nom technique peu courant.",
    ("central-priority-review-04", "MIES"): "Pluriel artificiel de remplissage.",
    ("central-priority-review-04", "LEST"): "Terme nautique moins courant.",
    ("central-priority-review-04", "COATI"): "Animal peu familier.",
    ("central-priority-review-05", "TREMAS"): "Pluriel typographique peu ludique.",
    ("central-priority-review-05", "ANISETTE"): "Liqueur datée.",
    ("central-priority-review-05", "SEMONCE"): "Nom vieilli pour une réprimande.",
    ("fresh-quality-pilot-01", "ISBAS"): "Habitation russe très peu connue.",
    ("fresh-quality-pilot-01", "UVEE"): "Anatomie oculaire spécialisée.",
    ("fresh-quality-pilot-01", "ISLE"): "Nom propre de rivière locale.",
    ("image-rich-review-02", "NIA"): "Passé simple isolé, forme artificielle.",
    ("image-rich-review-02", "ALESIA"): "Nom propre historique imposé par le croisement.",
    ("image-rich-review-02", "TUB"): "Ancien mot de baignoire, daté.",
    ("image-rich-review-03", "ALANGUIR"): "Verbe soutenu et peu spontané.",
    ("image-rich-review-03", "SAMPANS"): "Bateaux asiatiques peu connus.",
    ("image-rich-review-03", "GREGE"): "Nom de couleur peu courant.",
    ("image-rich-review-03", "CRUT"): "Passé simple isolé, forme artificielle.",
    ("dynamic-reference-c-02-refined", "AGACA"): "Passé simple isolé, forme artificielle.",
    ("dynamic-reference-c-02-refined", "PAT"): "Terme d'échecs peu familier.",
    ("review-20260715-02", "CADI"): "Titre juridique historique/spécialisé.",
    ("review-20260715-03", "RIS"): "Sens culinaire peu connu et souvent répété.",
}


def main() -> int:
    raw = CATALOG.read_bytes()
    catalog = json.loads(raw)
    words = {
        (grid["id"], word["answer"]): word
        for grid in catalog["grids"]
        for word in grid.get("words", [])
    }

    sensitive_rows = []
    missing_review_keys = []
    for key, (classification, note) in sorted(SENSITIVE.items()):
        word = words.get(key)
        if word is None:
            missing_review_keys.append({"gridId": key[0], "answer": key[1], "list": "sensitive"})
            continue
        sensitive_rows.append({
            "gridId": key[0],
            "answer": key[1],
            "clue": word.get("clue"),
            "classification": classification,
            "blocking": classification.startswith("probleme-"),
            "note": note,
        })

    obscure_rows = []
    for key, note in sorted(OBSCURE.items()):
        word = words.get(key)
        if word is None:
            missing_review_keys.append({"gridId": key[0], "answer": key[1], "list": "obscure"})
            continue
        obscure_rows.append({
            "gridId": key[0],
            "answer": key[1],
            "clue": word.get("clue"),
            "classification": "manifestement-obscur-ou-artificiel",
            "blocking": True,
            "note": note,
        })

    blocking_grids = sorted({
        row["gridId"]
        for row in [*sensitive_rows, *obscure_rows]
        if row["blocking"]
    })
    document = {
        "version": 1,
        "kind": "active-catalog-editorial-risk-audit",
        "catalogPath": "src/data/grid.catalog.json",
        "catalogSha256": hashlib.sha256(raw).hexdigest(),
        "catalogModified": False,
        "gridCount": len(catalog["grids"]),
        "policy": {
            "commonReligiousWordsAreNotProblems": True,
            "examplesAccepted": ["IMAM", "PAPE", "EGLISE", "MOSQUEE"],
            "blockingTargets": [
                "jargon ou translittération ultra-spécialisée",
                "couple factuellement faux ou réducteur",
                "mot manifestement obscur, archaïque ou forme de remplissage",
            ],
        },
        "summary": {
            "sensitiveReferencesInventoried": len(sensitive_rows),
            "sensitiveBlocking": sum(row["blocking"] for row in sensitive_rows),
            "obscureOrArtificialBlocking": len(obscure_rows),
            "blockingGridCount": len(blocking_grids),
            "blockingGridIds": blocking_grids,
            "missingReviewKeys": missing_review_keys,
        },
        "sensitiveReferences": sensitive_rows,
        "obscureOrArtificial": obscure_rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document["summary"], ensure_ascii=False, indent=2))
    return 0 if not missing_review_keys else 2


if __name__ == "__main__":
    raise SystemExit(main())
