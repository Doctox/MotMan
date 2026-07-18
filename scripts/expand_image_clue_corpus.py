"""Expand the reviewed image-clue pool with unambiguous Twemoji pictograms.

Only answers already present in MotMan's canonical central corpus are eligible.
The script downloads the corresponding CC BY 4.0 SVG, writes a reviewed image
entry, and leaves the textual source pair available as provenance evidence.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_grid_catalog as generator  # noqa: E402


DATA = ROOT / "src/data/crossword.images-reviewed.json"
ASSETS = ROOT / "public/assets/clues/twemoji"
TWEMOJI_RAW = "https://raw.githubusercontent.com/jdecked/twemoji/master/assets/svg/{code}.svg"
TWEMOJI_PAGE = "https://github.com/jdecked/twemoji/blob/master/assets/svg/{code}.svg"

# Deliberately concrete, single-concept images. Abstract notions and icons that
# could naturally name two answers in the same grid are kept out of this list.
PICTOGRAMS = {
    "ABRI": "1f6d6",
    "AIL": "1f9c4",
    "ANGE": "1f47c",
    "ARA": "1f99c",
    "ARGENT": "1f4b0",
    "AUTO": "1f697",
    "BAIN": "1f6c1",
    "BD": "1f4ac",
    "BARBE": "1f9d4",
    "BOIS": "1fab5",
    "BRAS": "1f4aa",
    "BROCOLI": "1f966",
    "CAFE": "2615",
    "CD": "1f4bf",
    "CAMION": "1f69a",
    "CARTE": "1f5fa",
    "CERVEAU": "1f9e0",
    "CHAISE": "1fa91",
    "CHAMEAU": "1f42b",
    "CHAPEAU": "1f3a9",
    "CHATEAU": "1f3f0",
    "CHEVAL": "1f40e",
    "CLIP": "1f4ce",
    "COQ": "1f413",
    "COR": "1f4ef",
    "CRABE": "1f980",
    "CRANE": "1f480",
    "CUILLERE": "1f944",
    "CUISINE": "1f373",
    "DOUCHE": "1f6bf",
    "DUEL": "2694",
    "DENT": "1f9b7",
    "EPEE": "2694",
    "EGLISE": "26ea",
    "ELEPHANT": "1f418",
    "FEMME": "1f469",
    "FENETRE": "1fa9f",
    "FILLE": "1f467",
    "FILM": "1f39e",
    "FIL": "1f9f5",
    "FORET": "1f332",
    "FUMEE": "1f4a8",
    "GARCON": "1f466",
    "GIRAFE": "1f992",
    "HERBE": "1f33f",
    "HOMME": "1f468",
    "JET": "1f6e9",
    "KIWI": "1f95d",
    "LIT": "1f6cf",
    "LAIT": "1f95b",
    "LOUP": "1f43a",
    "LUMIERE": "1f4a1",
    "MAGASIN": "1f3ea",
    "MAIS": "1f33d",
    "MIROIR": "1fa9e",
    "MONTAGNE": "26f0",
    "MOTO": "1f3cd",
    "MOUTON": "1f411",
    "MUR": "1f9f1",
    "NID": "1fab9",
    "OIGNON": "1f9c5",
    "ORANGE": "1f34a",
    "OVNI": "1f6f8",
    "PAPIER": "1f4c4",
    "PC": "1f4bb",
    "PAQUET": "1f4e6",
    "PARFUM": "1f9f4",
    "PASTEQUE": "1f349",
    "PANTALON": "1f456",
    "PIC": "26cf",
    "PILE": "1f50b",
    "PECHE": "1f351",
    "PEINTURE": "1f3a8",
    "PHOTO": "1f4f7",
    "PLAGE": "1f3d6",
    "PLANETE": "1fa90",
    "PONT": "1f309",
    "POT": "1fad9",
    "PORTE": "1f6aa",
    "PORT": "2693",
    "PUB": "1f4e3",
    "RADIO": "1f4fb",
    "RAIL": "1f6e4",
    "RENARD": "1f98a",
    "REPAS": "1f37d",
    "REQUIN": "1f988",
    "ROUTE": "1f6e3",
    "ROC": "1faa8",
    "ROUE": "1f6de",
    "SAC": "1f392",
    "SEAU": "1faa3",
    "SERPENT": "1f40d",
    "SINGE": "1f412",
    "SKI": "1f3bf",
    "SMS": "1f4f2",
    "STOP": "1f6d1",
    "TABLEAU": "1f5bc",
    "TELE": "1f4fa",
    "THE": "1fad6",
    "TGV": "1f684",
    "TOILETTE": "1f6bd",
    "TORTUE": "1f422",
    "TOUR": "1f5fc",
    "TRAM": "1f68a",
    "TV": "1f4fa",
    "VALISE": "1f9f3",
    "VER": "1fab1",
    "VERRE": "1f943",
    "VESTE": "1f9e5",
    "VILLE": "1f3d9",
    "VIN": "1f377",
    "VISAGE": "1f642",
    "ZEBRE": "1f993",
}


def main() -> None:
    central = {entry["answer"]: entry for entry in generator.load_entries()}
    blacklist = json.loads(
        (ROOT / "src/data/editorial.blacklist.json").read_text(encoding="utf-8")
    )
    blocked = set(blacklist.get("rejectedAnswers", []))
    blocked.update(item["answer"] for item in blacklist.get("rotationCooldownAnswers", []))
    document = json.loads(DATA.read_text(encoding="utf-8"))
    existing = {entry["answer"]: entry for entry in document["entries"]}
    ASSETS.mkdir(parents=True, exist_ok=True)
    added = []
    skipped = {}

    for answer, code in sorted(PICTOGRAMS.items()):
        if answer in existing:
            continue
        if answer in blocked:
            skipped[answer] = "blacklist-or-rotation-cooldown"
            continue
        source = central.get(answer)
        if source is None:
            skipped[answer] = "not-in-canonical-central-corpus"
            continue
        if not 2 <= len(answer) <= 8:
            skipped[answer] = "outside-current-grid-slot-lengths"
            continue
        asset = ASSETS / f"{answer.lower()}.svg"
        if not asset.exists():
            request = urllib.request.Request(
                TWEMOJI_RAW.format(code=code),
                headers={"User-Agent": "MotMan-image-corpus/1.0"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read()
            if b"<svg" not in payload[:500]:
                raise ValueError(f"Twemoji invalide pour {answer}: {code}")
            asset.write_bytes(payload)
        entry = {
            "answer": answer,
            "clue": "",
            "sourceClue": f"Indice illustré : {answer.lower()}",
            "length": len(answer),
            "frequency": max(5.0, float(source.get("frequency", 0))),
            "difficulty": "easy",
            "sourceType": "image",
            "sourceId": f"twemoji-{code}",
            "sourceUrl": TWEMOJI_PAGE.format(code=code),
            "editorialStatus": "image-reviewed",
            "manualReview": "motman-small-screen-pictogram-review-20260716",
            "conceptGroup": source.get("conceptGroup", answer),
            "semanticConflicts": source.get("semanticConflicts", []),
            "license": "CC BY 4.0",
            "image": {
                "asset": f"/assets/clues/twemoji/{answer.lower()}.svg",
                "alt": answer.title(),
                "source": "Twemoji",
                "license": "CC BY 4.0",
            },
        }
        existing[answer] = entry
        added.append(answer)

    document.update({
        "version": 2,
        "policy": (
            "Images simples, concrètes et immédiatement reconnaissables à petite taille; "
            "chaque réponse reste présente dans le corpus central sourcé."
        ),
        "entries": sorted(existing.values(), key=lambda entry: entry["answer"]),
        "metrics": {
            "reviewedImageAnswers": len(existing),
            "addedByExpansion": len(added),
            "skipped": skipped,
        },
    })
    DATA.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "reviewedImageAnswers": len(existing),
        "added": len(added),
        "addedAnswers": added,
        "skipped": skipped,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
