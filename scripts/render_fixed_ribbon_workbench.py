"""Render a factual owner checkpoint for the immutable A01 fill work."""
from __future__ import annotations

import gzip
import html
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUALITY = ROOT / "output/quality"
OUTPUT = QUALITY / "reference-ribbon-a01-workbench.html"
sys.path.insert(0, str(ROOT / "scripts"))

from diagnose_fixed_shape_corpus_gaps import load_expansion_words, load_words

REPORTS = (
    ("Central relu, preuve exhaustive", "reference-ribbon-a01-corpus-gaps.json"),
    ("Exact ligne par ligne", "reference-ribbon-a01-row-mixed-717215.json"),
    ("Rotation locale", "reference-ribbon-a01-inflected-local-717208.json"),
    ("Exact haut/bas + continuations", "reference-ribbon-a01-band-lcv-717219.json"),
)


def load(path: Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def render_grid(shape: dict) -> str:
    clue_cells = {tuple(cell) for cell in shape["clueCells"]}
    neutral = {(0, 0)}
    cells = []
    for row in range(shape["rows"]):
        for column in range(shape["columns"]):
            coordinate = (row, column)
            if coordinate in neutral:
                cells.append('<div class="cell neutral">∅</div>')
            elif coordinate in clue_cells:
                arrows = []
                for slot in shape["slots"]:
                    if tuple(slot["clueCell"]) == coordinate:
                        arrows.append("→" if slot["direction"] == "across" else "↓")
                cells.append(
                    '<div class="cell clue"><span>indice</span><b>'
                    + " ".join(arrows)
                    + "</b></div>"
                )
            else:
                cells.append('<div class="cell letter"></div>')
    return "".join(cells)


def attempt_row(label: str, path: Path) -> str:
    if not path.exists():
        return ""
    document = load(path)
    telemetry = document.get("solverTelemetry", {})
    progress = (
        telemetry.get("bestAcrossSlots")
        or telemetry.get("bestFilledAcrossSlots")
        or telemetry.get("bestCrossingConflicts")
        or telemetry.get("bestProgress")
        or "—"
    )
    if "bestCrossingConflicts" in telemetry:
        progress = f"{telemetry['bestCrossingConflicts']} conflits / 69"
    elif "bestAcrossSlots" in telemetry or "bestFilledAcrossSlots" in telemetry:
        progress = f"{progress} horizontales / 11"
    elif "bestProgress" in telemetry:
        progress = f"{progress} slots figés / 22"
    return (
        "<tr>"
        f"<td>{html.escape(label)}</td>"
        f"<td>{'oui' if document.get('complete') else 'non'}</td>"
        f"<td>{html.escape(str(progress))}</td>"
        f"<td>{html.escape(str(telemetry.get('reason', '—')))}</td>"
        f"<td>{html.escape(path.name)}</td>"
        "</tr>"
    )


def main() -> None:
    shapes = load(QUALITY / "reference-style-shapes-a.json")
    shape = next(
        item for item in shapes["shapes"]
        if item["id"] == "reference-ribbon-a-01"
    )
    morphalou = load(ROOT / "src/data/crossword.morphalou.staging.json.gz")
    owner_small = load(ROOT / "src/data/jeuxdemots.owner-decisions.json")
    owner_full = load(ROOT / "src/data/jeuxdemots.owner-full-decisions.json")
    latest = load(QUALITY / "reference-ribbon-a01-band-lcv-717219.json")
    _words, canonical = load_words()
    _expanded, _metadata, corpus = load_expansion_words(
        canonical, include_morphalou=True
    )
    attempts = "".join(
        attempt_row(label, QUALITY / filename) for label, filename in REPORTS
    )
    metrics = morphalou["metrics"]
    accepted = int(owner_small["counts"].get("accept", 0)) + int(
        owner_full["counts"].get("accept", 0)
    )
    rejected = int(owner_small["counts"].get("reject", 0)) + int(
        owner_full["counts"].get("reject", 0)
    )
    document = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>A01 — atelier de fermeture fixe</title><style>
body{{font:15px system-ui;max-width:1180px;margin:28px auto;padding:0 18px;color:#183029;background:#f7faf8}}
h1,h2{{margin:.4em 0}}.lead{{font-size:18px;max-width:850px}}.warn{{background:#fff1d9;border:1px solid #e3a54d;padding:14px;border-radius:10px}}
.ok{{background:#e7f6ed;border:1px solid #78b78d;padding:14px;border-radius:10px}}.layout{{display:grid;grid-template-columns:420px 1fr;gap:24px;align-items:start}}
.grid{{display:grid;grid-template-columns:repeat(9,1fr);width:405px;background:#526b61;border:2px solid #526b61;gap:1px}}
.cell{{aspect-ratio:1;background:#fff;display:flex;align-items:center;justify-content:center}}.clue{{background:#dcefe9;flex-direction:column;font-size:9px}}.clue b{{font-size:16px}}.neutral{{background:#23342e;color:white}}
.cards{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}.card{{background:white;border:1px solid #cbd8d2;padding:13px;border-radius:10px}}.big{{font-size:25px;font-weight:750}}
table{{width:100%;border-collapse:collapse;background:white}}td,th{{border:1px solid #cbd8d2;padding:8px;text-align:left}}th{{background:#e9f3ef}}code{{font-size:12px}}@media(max-width:850px){{.layout{{grid-template-columns:1fr}}.cards{{grid-template-columns:1fr 1fr}}}}
</style></head><body><h1>Atelier A01 — silhouette immuable</h1>
<p class="lead">La géométrie ne bouge plus. Le travail en cours consiste uniquement à faire tourner des réponses entières du corpus jusqu'à obtenir 69 croisements cohérents, puis à relire les 22 couples.</p>
<p class="warn"><b>État publication :</b> aucune nouvelle grille publiée. Meilleur résultat exact : {latest['solverTelemetry']['bestAcrossSlots']} horizontales sur 11. Meilleur résultat local : 4 croisements faux sur 69. Une fermeture incomplète est rejetée.</p>
<div class="layout"><section><h2>Silhouette contrôlée</h2><div class="grid">{render_grid(shape)}</div>
<p><b>9×10</b> · 69 lettres · 20 cases-indices · 1 case neutre · 22 réponses · aucun segment orphelin.</p></section>
<section><h2>Réservoir réellement utilisé</h2><div class="cards">
<div class="card"><div class="big">{corpus['combinedAnswers']:,}</div>réponses structurelles après filtres</div>
<div class="card"><div class="big">{corpus['centralAnswers']:,}</div>réponses centrales canoniques</div>
<div class="card"><div class="big">{corpus['lexiqueNewAnswersBeyondCentral']:,}</div>nouveaux Lexique au-delà du central</div>
<div class="card"><div class="big">{corpus['morphalouNewAnswersBeyondCentralAndLexique']:,}</div>nouveaux Morphalou au-delà des deux autres</div>
<div class="card"><div class="big">{metrics['retainedInflectedForms']:,}</div>flexions en staging avant filtre de lemme</div>
<div class="card"><div class="big">{corpus['morphalouRejectedByRule'].get('inflected-lemma-not-common', 0):,}</div>flexions rares écartées</div>
</div><p class="ok"><b>Décisions propriétaire intégrées :</b> {accepted:,} acceptations et {rejected:,} refus servent aux priorités et exclusions. Une forme Morphalou reste non publiable sans indice court sourcé et relu.</p></section></div>
<h2>Essais comparables</h2><table><tr><th>Méthode</th><th>Fermeture</th><th>Meilleur état</th><th>Arrêt</th><th>Preuve</th></tr>{attempts}</table>
<h2>Prochaine passe</h2><ol><li>Reprendre la recherche exacte haut/bas avec le classement par continuations.</li><li>Sur fermeture 0 défaut, rejeter automatiquement les formes non naturelles selon les décisions propriétaire.</li><li>Créer ou sélectionner seulement les indices sourcés manquants.</li><li>Rendre la grille pour revue humaine; aucune publication automatique.</li></ol>
</body></html>"""
    OUTPUT.write_text(document, encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "complete": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
