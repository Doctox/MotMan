#!/usr/bin/env python3
"""Assemble the first corrected-contract 7x8 pilot for owner review only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = (
    ROOT
    / "output/quality/pilot-agent-c-corrected7x8/corrected-03-large-seed-814300.json"
)

EDITORIAL = {
    "ESTOMAC": {"definition": "Organe digestif", "partOfSpeech": "nom"},
    "FERRARI": {
        "definition": "Bolide italien",
        "partOfSpeech": "nom propre",
        "culturalStatus": "marque mondialement connue",
    },
    "FRIANDE": {
        "definition": "Gourmande",
        "partOfSpeech": "adjectif féminin",
        "editorialReview": "Le genre de la définition indique naturellement la forme féminine.",
    },
    "REPLIER": {"definition": "Plier encore", "partOfSpeech": "infinitif"},
    "OIE": {"definition": "Oie", "partOfSpeech": "nom"},
    "INSECTE": {"definition": "Insecte", "partOfSpeech": "nom"},
    "EFFROI": {"definition": "Effroi", "partOfSpeech": "nom"},
    "SEREIN": {"definition": "Serein", "partOfSpeech": "adjectif"},
    "TRIPES": {"definition": "Boyaux", "partOfSpeech": "nom pluriel"},
    "ORAL": {"definition": "Examen parlé", "partOfSpeech": "nom"},
    "ONG": {
        "definition": "Organisation humanitaire",
        "partOfSpeech": "sigle",
        "editorialReview": "Le libellé signale explicitement qu'une abréviation est attendue.",
    },
    "MANIOC": {"definition": "Tubercule tropical", "partOfSpeech": "nom"},
    "ARDENT": {"definition": "Très passionné", "partOfSpeech": "adjectif"},
    "CIERGE": {"definition": "Lueur d'église", "partOfSpeech": "nom"},
}

IMAGE_META = {
    "OIE": {
        "asset": "/assets/clues/twemoji/oie.svg",
        "alt": "Oiseau palmipède",
        "concept": "Oie",
        "sourceId": "twemoji-1fabf",
        "sourceUrl": "https://github.com/jdecked/twemoji/blob/master/assets/svg/1fabf.svg",
    },
    "INSECTE": {
        "asset": "/assets/clues/twemoji/insecte.svg",
        "alt": "Petit coléoptère",
        "concept": "Insecte",
        "sourceId": "twemoji-1fab2",
        "sourceUrl": "https://github.com/jdecked/twemoji/blob/master/assets/svg/1fab2.svg",
    },
    "EFFROI": {
        "asset": "/assets/clues/twemoji/effroi.svg",
        "alt": "Visage terrifié",
        "concept": "Effroi",
        "sourceId": "twemoji-1f631",
        "sourceUrl": "https://github.com/jdecked/twemoji/blob/master/assets/svg/1f631.svg",
    },
    "SEREIN": {
        "asset": "/assets/clues/twemoji/serein.svg",
        "alt": "Visage apaisé",
        "concept": "Serein",
        "sourceId": "twemoji-1f60c",
        "sourceUrl": "https://github.com/jdecked/twemoji/blob/master/assets/svg/1f60c.svg",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def build(candidate: dict) -> dict:
    answers = []
    for item in candidate["answers"]:
        answer = item["answer"]
        review = EDITORIAL[answer]
        image = IMAGE_META.get(answer)
        source_type = "image-concept" if image else "editorial-original"
        thoughtful = answer in {"FRIANDE", "EFFROI", "CIERGE"}
        clever = answer in {"FERRARI", "CIERGE"}
        cultural_status = (
            "current-pop" if answer == "FERRARI"
            else "general-culture" if answer in {"MANIOC", "CIERGE"}
            else "everyday"
        )
        language_status = "known-proper-name" if answer == "FERRARI" else "french"
        editorial_review = {
            "semanticFit": True,
            "grammaticalFit": True,
            "unambiguous": True,
            "answerNotRevealed": True,
            "languageAcceptable": True,
            "allAudience": True,
        }
        if image:
            editorial_review["imageRecognizable"] = True
        answers.append(
            {
                "slotIndex": item["slotIndex"],
                "answer": answer,
                "definition": review["definition"],
                "definitionStatus": "image-review" if image else "manually-reviewed",
                "editorialStatus": "owner-review-required",
                "sourceType": source_type,
                "sourceId": image["sourceId"] if image else "motman-editorial-pilot-20260721",
                "sourceUrl": image["sourceUrl"] if image else "internal://motman/editorial/pilot-20260721",
                "license": "CC BY 4.0" if image else "MotMan original",
                "familiarityScore": item.get("wordfreqZipf"),
                "familiarityBand": "thoughtful" if thoughtful else "common",
                "partOfSpeech": review["partOfSpeech"],
                "languageStatus": language_status,
                "culturalStatus": cultural_status,
                "clueStyle": "image" if image else "clever" if clever else "direct",
                "imageStatus": "reviewed-recognizable-licensed" if image else "not-applicable",
                "editorialReview": editorial_review,
            }
        )

    return {
        "version": 1,
        "kind": "motman-corrected-7x8-owner-pilot-source",
        "catalogModified": False,
        "runtimeModified": False,
        "grids": [
            {
                "id": "pilot-corrected-7x8-01",
                "sourceShapeId": candidate["sourceShapeId"],
                "columns": 7,
                "rows": 8,
                "clueCells": candidate["clueCells"],
                "rawSlots": candidate["rawSlots"],
                "answers": answers,
                "imageAnswers": [
                    {
                        "answer": answer,
                        "asset": meta["asset"],
                        "alt": meta["alt"],
                        "concept": meta["concept"],
                        "source": "Twemoji",
                        "license": "CC BY 4.0",
                    }
                    for answer, meta in IMAGE_META.items()
                ],
                "minimumImages": 4,
                "publicationStatus": "owner-review-required",
            }
        ],
    }


def main() -> None:
    args = parse_args()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    payload = build(candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(args.output), "grids": 1, "images": 4}))


if __name__ == "__main__":
    main()
