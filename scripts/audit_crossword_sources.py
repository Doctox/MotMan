"""Audit real French crossword sources and prepare a licensing request.

This script is deliberately offline. Web research is recorded in
``src/data/crossword.sources.json`` with an evidence URL and a rights status;
the audit never treats a public web page as permission to republish its grids.
"""
from __future__ import annotations

import argparse
import gzip
import html
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "src" / "data" / "crossword.sources.json"
DEFAULT_JSON = ROOT / "output" / "quality" / "real-crossword-source-audit.json"
DEFAULT_HTML = ROOT / "output" / "quality" / "real-crossword-source-audit.html"
DEFAULT_REQUEST = ROOT / "output" / "quality" / "source-license-request.md"

CORPUS_FILES = (
    "crossword.ouestfrance.json",
    "crossword.leparisien.json",
    "crossword.curated.json",
    "crossword.images-reviewed.json",
    "crossword.reference-reviewed.json",
    "crossword.dbnary.review.json",
    "crossword.dbnary.staging.json.gz",
)

RIGHTS_CLEARED = {
    "open-license",
    "commercial-license-obtained",
    "written-permission-obtained",
}


def read_json(path: Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def load_local_counts() -> tuple[Counter, Counter, list[dict]]:
    unique_by_source: dict[str, set[tuple[str, str]]] = {}
    unique_by_status: dict[str, set[tuple[str, str, str]]] = {}
    documents = []
    for name in CORPUS_FILES:
        path = ROOT / "src" / "data" / name
        if not path.exists():
            continue
        document = read_json(path)
        entries = document.get("entries", [])
        sources = Counter(entry.get("sourceId", "unknown") for entry in entries)
        statuses = Counter(entry.get("editorialStatus", "unknown") for entry in entries)
        for entry in entries:
            source_id = entry.get("sourceId", "unknown")
            status = entry.get("editorialStatus", "unknown")
            pair = (entry.get("answer", ""), entry.get("sourceClue", entry.get("clue", "")))
            unique_by_source.setdefault(source_id, set()).add(pair)
            unique_by_status.setdefault(status, set()).add((source_id, *pair))
        documents.append({
            "file": name,
            "entries": len(entries),
            "bySource": dict(sorted(sources.items())),
            "byEditorialStatus": dict(sorted(statuses.items())),
        })
    by_source = Counter({key: len(value) for key, value in unique_by_source.items()})
    by_status = Counter({key: len(value) for key, value in unique_by_status.items()})
    return by_source, by_status, documents


def build_audit(registry: dict) -> dict:
    sources = registry["sources"]
    source_by_id = {source["id"]: source for source in sources}
    local_by_source, local_by_status, documents = load_local_counts()
    local_by_family: Counter = Counter()
    rights_uncleared = Counter()
    for source_id, count in local_by_source.items():
        source = source_by_id.get(source_id, {})
        family = source.get("editorialFamily", source_id)
        local_by_family[family] += count
        if source.get("publicationRights") not in RIGHTS_CLEARED:
            rights_uncleared[source_id] += count

    acquisition = sorted(
        (
            {
                "id": source["id"],
                "priority": source["priority"],
                "family": source["editorialFamily"],
                "status": source["status"],
                "rights": source["publicationRights"],
                "url": source["url"],
                "role": source["role"],
                "delivery": source.get("delivery"),
            }
            for source in sources
            if "priority" in source
        ),
        key=lambda item: item["priority"],
    )
    active_real = [
        source for source in sources
        if source["type"] == "crossword-corpus"
        and source["status"].startswith("active-")
    ]
    independent_active = [
        source for source in active_real
        if source.get("editorialFamily") not in {"keesing-rci", "rci-likely"}
    ]
    return {
        "version": 1,
        "checkedOn": registry.get("checkedOn"),
        "decision": {
            "preferredAcquisition": "fortissimots",
            "pilot": "3 grilles 9x10 (une facile enfant, une normale, une difficile)",
            "reason": (
                "Le corpus local contient de vraies définitions publiées, mais aucune "
                "famille professionnelle indépendante avec droits de republication clarifiés."
            ),
            "dictionaryPolicy": (
                "DBnary reste un outil de validation/staging et ne remplace jamais une "
                "source de grilles relue par un verbicruciste."
            ),
        },
        "localCorpus": {
            "bySource": dict(sorted(local_by_source.items())),
            "byEditorialFamily": dict(sorted(local_by_family.items())),
            "byEditorialStatus": dict(sorted(local_by_status.items())),
            "entriesWithUnclearedPublicationRights": dict(sorted(rights_uncleared.items())),
            "activeRealGridSources": [source["id"] for source in active_real],
            "activeIndependentLicensedGridSources": [source["id"] for source in independent_active],
            "documents": documents,
        },
        "acquisitionCandidates": acquisition,
        "publicationGate": {
            "requiredRightsStatuses": sorted(RIGHTS_CLEARED),
            "rule": (
                "Une source candidate ou simplement visible en ligne ne peut jamais être "
                "chargée par le catalogue publié sans licence ouverte, contrat ou accord écrit."
            ),
        },
    }


def render_html(audit: dict) -> str:
    candidates = "".join(
        f"""
        <tr>
          <td><strong>{item['priority']}. {html.escape(item['id'])}</strong><br>
              <small>{html.escape(item['family'])}</small></td>
          <td>{html.escape(item['status'])}</td>
          <td>{html.escape(item['rights'])}</td>
          <td>{html.escape(item['role'])}</td>
          <td><a href="{html.escape(item['url'])}">source officielle</a></td>
        </tr>"""
        for item in audit["acquisitionCandidates"]
    )
    local_rows = "".join(
        f"<tr><td>{html.escape(source)}</td><td>{count}</td></tr>"
        for source, count in audit["localCorpus"]["bySource"].items()
    )
    return f"""<!doctype html>
<html lang="fr">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit des sources de mots fléchés</title>
<style>
  :root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
  body {{ margin: 0; background: #f3f0e8; color: #222; }}
  main {{ max-width: 1100px; margin: auto; padding: 32px 18px 64px; }}
  h1 {{ margin-bottom: 6px; }} h2 {{ margin-top: 32px; }}
  .lead {{ font-size: 1.08rem; max-width: 78ch; }}
  .verdict {{ background: #fff4c8; border-left: 6px solid #d89b00; padding: 16px; }}
  table {{ width: 100%; border-collapse: collapse; background: white; }}
  th,td {{ padding: 11px; border: 1px solid #d8d4ca; text-align: left; vertical-align: top; }}
  th {{ background: #222; color: white; }}
  code {{ background: #e9e5dc; padding: 2px 5px; }}
  .ok {{ color: #176b3a; font-weight: 700; }} .no {{ color: #9b2d20; font-weight: 700; }}
</style>
<main>
  <h1>Sources réelles de mots fléchés</h1>
  <p class="lead">Audit au {html.escape(str(audit['checkedOn']))}. Le but est d'obtenir des couples
  rédigés par des humains et des silhouettes professionnelles, sans confondre accès public et droit de republication.</p>
  <div class="verdict"><strong>Choix recommandé : Fortissimots.</strong>
  Demander d'abord 3 grilles pilotes 9×10 et un export structuré, puis commander le lot 30 si la revue humaine passe.
  Keesing/RCI reste une bonne voie de licence, mais ne diversifie pas vraiment Le Parisien et probablement Ouest-France.</div>

  <h2>État local</h2>
  <p class="no">0 source professionnelle indépendante avec droits de publication clarifiés.</p>
  <table><thead><tr><th>Source chargée</th><th>Couples uniques locaux</th></tr></thead><tbody>{local_rows}</tbody></table>

  <h2>Pistes qualifiées</h2>
  <table><thead><tr><th>Source / famille</th><th>Statut</th><th>Droits</th><th>Intérêt pour MotMan</th><th>Preuve</th></tr></thead>
  <tbody>{candidates}</tbody></table>

  <h2>Règle de publication</h2>
  <p>{html.escape(audit['publicationGate']['rule'])}</p>
  <p>DBnary reste du <code>staging</code> : utile pour vérifier une forme ou un sens, insuffisant pour inventer une définition jouable.</p>
</main>
</html>"""


def request_template() -> str:
    return """# Demande de lot pilote de mots fléchés pour MotMan

Objet : devis pour des grilles de mots fléchés françaises 9×10 destinées à une application

Bonjour,

Nous développons MotMan, un jeu mobile multijoueur de mots fléchés en français. Nous cherchons un partenariat avec un verbicruciste ou un fournisseur de contenu pour garantir une qualité éditoriale professionnelle.

Nous souhaiterions d'abord un lot pilote de 3 grilles, puis 30 grilles si le pilote est concluant :

- format exact : 9 colonnes × 10 lignes, cases de définition comprises ;
- une grille enfant 7–14 ans, une grand public accessible, une adulte cultivée ;
- flèches directes vers la première lettre, horizontalement à droite ou verticalement vers le bas ;
- aucune lettre ni suite de lettres orpheline ;
- définitions courtes, naturelles, non ambiguës et réponses françaises canoniques ;
- silhouettes variées, avec des cases à double définition lorsque cela aère la grille ;
- 1 à 6 indices-images simples lorsque les droits des illustrations le permettent ;
- pas de quota artificiel par longueur, mais une diversité naturelle des mots.

Pour l'intégration, pouvez-vous fournir un export UTF-8 JSON, CSV ou XML contenant pour chaque grille : dimensions, cases, définition, réponse, position de départ, direction, niveau et identifiant de provenance ? Si vous ne fournissez que du PDF/vectoriel, autorisez-vous contractuellement sa conversion vers ce format de données ?

Merci d'indiquer le tarif et les droits pour une utilisation commerciale dans une application web/mobile, l'adaptation technique au format MotMan, la conservation dans notre catalogue et la diffusion aux joueurs.

Cordialement,
L'équipe MotMan
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--request", type=Path, default=DEFAULT_REQUEST)
    args = parser.parse_args()
    registry = read_json(args.registry)
    audit = build_audit(registry)
    for path in (args.json, args.html, args.request):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    args.html.write_text(render_html(audit), encoding="utf-8")
    args.request.write_text(request_template(), encoding="utf-8")
    print(json.dumps({
        "status": "audited",
        "preferred": audit["decision"]["preferredAcquisition"],
        "candidates": len(audit["acquisitionCandidates"]),
        "activeIndependentLicensed": len(
            audit["localCorpus"]["activeIndependentLicensedGridSources"]
        ),
        "html": str(args.html),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
