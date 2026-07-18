"""Apply the 2026-07-15 editorial review to the pinned strict JDM batch."""
from __future__ import annotations

import gzip
import hashlib
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
SOURCE = DATA / "crossword.jeuxdemots.sanitized.json.gz"
APPROVED = DATA / "crossword.jeuxdemots.approved.json"
DECISIONS = DATA / "jeuxdemots.editorial-decisions.json"
DOUBT_JSON = ROOT / "output/quality/jeuxdemots-owner-doubt.json"
DOUBT_HTML = ROOT / "output/quality/jeuxdemots-owner-doubt.html"
EXPECTED_COUNT = 242
EXPECTED_DIGEST = "ac56495da8d3ba81db3b1e6ce3b711609dac68056fbaeeb10e16f398282afcc3"

DOUBT_PAIRS = {
    ("AIDER", "Servir"),
    ("ARGENT", "Monnaie"),
    ("AUTORITE", "Empire"),
    ("BAGUETTE", "Bâton"),
    ("BARBARE", "Sauvage"),
    ("BARQUE", "Bateau"),
    ("BATON", "Baguette"),
    ("CABARET", "Café"),
    ("CAFE", "Cabaret"),
    ("CHUTE", "Ruine"),
    ("CONCLURE", "Régler"),
    ("CORDE", "Fil"),
    ("DEBUT", "Seuil"),
    ("DEFENSE", "Rempart"),
    ("EMPIRE", "Autorité"),
    ("FAIBLE", "Petit"),
    ("FLATTER", "Caresser"),
    ("FUGACE", "Fugitif"),
    ("FUGITIF", "Fugace"),
    ("HABITER", "Vivre"),
    ("HAUTEUR", "Éminence"),
    ("HISTOIRE", "Conte"),
    ("IMAGINER", "Penser"),
    ("LANGAGE", "Langue"),
    ("LANGUE", "Langage"),
    ("MAIGRE", "Pauvre"),
    ("NEGLIGER", "Oublier"),
    ("ORIGINE", "Principe"),
    ("PARAITRE", "Surgir"),
    ("PAUVRE", "Maigre"),
    ("PAYS", "Région"),
    ("PEINTURE", "Tableau"),
    ("PORTRAIT", "Image"),
    ("PRETRE", "Abbé"),
    ("PROCHAIN", "Proche"),
    ("PROCHE", "Prochain"),
    ("PRODUIT", "Fruit"),
    ("RAISON", "Esprit"),
    ("REGLER", "Conclure"),
    ("REPLI", "Pli"),
    ("SERVIR", "Aider"),
    ("SOLDAT", "Guerrier"),
    ("SURGIR", "Paraître"),
    ("TEMPETE", "Ouragan"),
    ("TRAINER", "Flâner"),
    ("TRAJET", "Voyage"),
    ("TRIPOTER", "Manier"),
    ("VIVRE", "Habiter"),
    ("VOYAGE", "Trajet"),
}


def digest(entries: list[dict]) -> str:
    pairs = sorted((entry["answer"], entry["clue"]) for entry in entries)
    payload = json.dumps(pairs, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def approved_entry(entry: dict) -> dict:
    return {
        **entry,
        "sourceClue": entry["clue"],
        "sourceId": "jeuxdemots-r_syn-sanitized",
        "sourceUrl": "https://www.jeuxdemots.org/jdm-about.php",
        "sourceType": "lexical-relation",
        "editorialStatus": "human-reviewed",
        "manualReview": "approved",
        "definitionStatus": "reviewed",
        "reviewedAt": "2026-07-15",
        "reviewedBy": "motman-editorial",
        "license": "CC0 relation; couple relu pour MotMan",
        "corpusStage": "production-reviewed",
        "generatorEligible": True,
        "canonicalForGenerator": True,
        "playableAsIs": True,
        "reviewRequired": False,
    }


def render_doubts(manual_doubts: list[dict], borderline: list[dict]) -> str:
    def rows(entries: list[dict], prefix: str) -> str:
        return "".join(
            f"<tr data-id=\"{prefix}-{index:03d}\" "
            f"data-answer=\"{html.escape(entry['answer'], quote=True)}\" "
            f"data-clue=\"{html.escape(entry['clue'], quote=True)}\" "
            f"data-category=\"{'strict-doubt' if prefix == 'S' else 'borderline-doubt'}\">"
            f"<td><b>{prefix}-{index:03d}</b></td>"
            f"<td>{html.escape(entry['answer'])}</td>"
            f"<td>{html.escape(entry['clue'])}</td>"
            f"<td>{entry['mutualRelationWeight']}</td>"
            f"<td>{entry['minimumSourceFrequency']:.2f}</td>"
            f"<td>{html.escape('; '.join(entry.get('doubtReasons', ['sens trop large ou contextuel'])))}</td>"
            "<td class=\"choices\">"
            "<button type=\"button\" data-decision=\"accept\" title=\"Valider ce couple\">✓</button>"
            "<button type=\"button\" data-decision=\"reject\" title=\"Refuser ce couple\">✕</button>"
            "<button type=\"button\" data-decision=\"doubt\" title=\"Laisser en doute\">?</button>"
            "</td>"
            "</tr>"
            for index, entry in enumerate(entries, start=1)
        )

    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Doutes JeuxDeMots — MotMan</title>
<style>
body{{font:15px system-ui;max-width:1180px;margin:30px auto;padding:0 18px;color:#17251f}}
table{{border-collapse:collapse;width:100%;margin:18px 0}}th,td{{border:1px solid #bdc9c3;padding:8px;text-align:left}}
th{{position:sticky;top:76px;background:#eef5f1;z-index:2}}.note{{background:#fff5cc;border:1px solid #d8ba4a;padding:12px}}
.toolbar{{position:sticky;top:0;z-index:3;background:#fff;border:1px solid #aebdb5;box-shadow:0 3px 10px #0002;padding:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
.toolbar b{{margin-right:auto}}button,select{{font:inherit;padding:7px 10px;border:1px solid #8fa198;border-radius:6px;background:white;cursor:pointer}}
.choices{{white-space:nowrap}}.choices button{{font-size:18px;min-width:39px;margin:2px}}
.choices button[data-decision=accept]{{color:#08723d}}.choices button[data-decision=reject]{{color:#b32222}}.choices button[data-decision=doubt]{{color:#8a6300}}
tr.decision-accept{{background:#e5f8ec}}tr.decision-reject{{background:#fde8e8}}tr.decision-doubt{{background:#fff4ce}}
tr button.selected{{color:white!important}}tr button[data-decision=accept].selected{{background:#08723d}}tr button[data-decision=reject].selected{{background:#b32222}}tr button[data-decision=doubt].selected{{background:#9b7100}}
.saved{{color:#08723d;font-weight:700}}@media(max-width:700px){{th:nth-child(4),td:nth-child(4),th:nth-child(5),td:nth-child(5),th:nth-child(6),td:nth-child(6){{display:none}}}}
</style></head>
<body><h1>JeuxDeMots — catégorie « doute »</h1><p class="note">Clique simplement sur <b>✓</b> pour valider, <b>✕</b> pour refuser ou <b>?</b> pour conserver le doute. Les choix sont sauvegardés automatiquement dans ce navigateur.</p>
<div class="toolbar"><b><span id="done">0</span> / <span id="total">0</span> traités — ✓ <span id="accepted">0</span> · ✕ <span id="rejected">0</span> · ? <span id="doubted">0</span></b>
<select id="filter"><option value="all">Tout afficher</option><option value="pending">Seulement à traiter</option><option value="accept">Validés</option><option value="reject">Refusés</option><option value="doubt">Encore en doute</option></select>
<button type="button" id="copy">Copier le bilan</button><button type="button" id="download">Télécharger le JSON</button><span class="saved" id="saved"></span></div>
<h2>Doutes issus de ma relecture du lot strict ({len(manual_doubts)})</h2><table><tr><th>ID</th><th>Réponse</th><th>Indice</th><th>Poids</th><th>Fréquence</th><th>Pourquoi</th><th>Décision</th></tr>{rows(manual_doubts, 'S')}</table>
<h2>Proches du seuil automatique ({len(borderline)} affichés)</h2><table><tr><th>ID</th><th>Réponse</th><th>Indice</th><th>Poids</th><th>Fréquence</th><th>Pourquoi</th><th>Décision</th></tr>{rows(borderline, 'D')}</table>
<script>
const storageKey = 'motman-jdm-doubt-decisions-{EXPECTED_DIGEST}';
const tableRows = [...document.querySelectorAll('tr[data-id]')];
let decisions = JSON.parse(localStorage.getItem(storageKey) || '{{}}');
const save = () => {{ localStorage.setItem(storageKey, JSON.stringify(decisions)); document.getElementById('saved').textContent='Enregistré'; setTimeout(()=>document.getElementById('saved').textContent='',900); }};
function render() {{
  const filter = document.getElementById('filter').value;
  const counts = {{accept:0,reject:0,doubt:0}};
  tableRows.forEach(row => {{
    const decision = decisions[row.dataset.id] || 'pending';
    row.className = decision === 'pending' ? '' : `decision-${{decision}}`;
    row.querySelectorAll('button[data-decision]').forEach(button => button.classList.toggle('selected', button.dataset.decision === decision));
    row.hidden = filter !== 'all' && decision !== filter;
    if (counts[decision] !== undefined) counts[decision]++;
  }});
  document.getElementById('total').textContent=tableRows.length;
  document.getElementById('accepted').textContent=counts.accept;
  document.getElementById('rejected').textContent=counts.reject;
  document.getElementById('doubted').textContent=counts.doubt;
  document.getElementById('done').textContent=counts.accept+counts.reject+counts.doubt;
}}
tableRows.forEach(row => row.querySelectorAll('button[data-decision]').forEach(button => button.addEventListener('click', () => {{ decisions[row.dataset.id]=button.dataset.decision; save(); render(); }})));
document.getElementById('filter').addEventListener('change', render);
function exportData() {{ return {{version:1, sourceDigest:'{EXPECTED_DIGEST}', decisions:tableRows.map(row => ({{id:row.dataset.id,answer:row.dataset.answer,clue:row.dataset.clue,category:row.dataset.category,decision:decisions[row.dataset.id]||'pending'}}))}}; }}
document.getElementById('copy').addEventListener('click', async () => {{ const text=JSON.stringify(exportData(),null,2); try {{ await navigator.clipboard.writeText(text); }} catch {{ const area=document.createElement('textarea');area.value=text;document.body.appendChild(area);area.select();document.execCommand('copy');area.remove(); }} document.getElementById('copy').textContent='Bilan copié ✓'; }});
document.getElementById('download').addEventListener('click', () => {{ const blob=new Blob([JSON.stringify(exportData(),null,2)],{{type:'application/json'}}); const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='jeuxdemots-decisions.json';link.click();URL.revokeObjectURL(link.href); }});
render();
</script></body></html>"""


def main() -> int:
    owner_decisions = DATA / "jeuxdemots.owner-decisions.json"
    if owner_decisions.exists():
        raise ValueError(
            "la revue propriétaire est déjà appliquée; ne pas l'écraser avec une nouvelle feuille"
        )
    with gzip.open(SOURCE, "rt", encoding="utf-8") as handle:
        source = json.load(handle)
    strict = [
        entry for entry in source["entries"]
        if entry["sanitationStatus"] == "strict-editorial-review-candidate"
    ]
    if len(strict) != EXPECTED_COUNT or digest(strict) != EXPECTED_DIGEST:
        raise ValueError("le lot strict a changé; une nouvelle relecture est obligatoire")
    by_pair = {(entry["answer"], entry["clue"]): entry for entry in strict}
    missing = sorted(DOUBT_PAIRS - set(by_pair))
    if missing:
        raise ValueError(f"doutes absents du lot strict: {missing}")

    manual_doubts = [by_pair[pair] for pair in sorted(DOUBT_PAIRS)]
    accepted = [
        approved_entry(entry)
        for pair, entry in sorted(by_pair.items())
        if pair not in DOUBT_PAIRS
    ]
    borderline = [
        entry for entry in source["entries"]
        if entry["sanitationStatus"] == "owner-doubt-review-candidate"
    ][:250]

    approved_document = {
        "version": 1,
        "kind": "jeuxdemots-human-reviewed-crossword-pairs",
        "publicationPolicy": "Couples relus individuellement; les doutes restent exclus.",
        "reviewedCandidateDigest": EXPECTED_DIGEST,
        "entries": accepted,
    }
    decisions = {
        "version": 1,
        "reviewedAt": "2026-07-15",
        "sourceCandidateDigest": EXPECTED_DIGEST,
        "sourceCandidateCount": len(strict),
        "acceptedCount": len(accepted),
        "doubtCount": len(manual_doubts),
        "rejectedBeforeReviewCount": 28,
        "acceptedPairs": [[entry["answer"], entry["clue"]] for entry in accepted],
        "doubtPairs": [[entry["answer"], entry["clue"]] for entry in manual_doubts],
        "policy": "Toute modification du lot source invalide le digest et force une nouvelle relecture.",
    }
    doubt_report = {
        "strictReviewDoubts": manual_doubts,
        "borderlineDoubts": borderline,
    }
    APPROVED.write_text(json.dumps(approved_document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DECISIONS.write_text(json.dumps(decisions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DOUBT_JSON.parent.mkdir(parents=True, exist_ok=True)
    DOUBT_JSON.write_text(json.dumps(doubt_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DOUBT_HTML.write_text(render_doubts(manual_doubts, borderline), encoding="utf-8")
    print(json.dumps({
        "strictReviewed": len(strict),
        "accepted": len(accepted),
        "ownerDoubt": len(manual_doubts),
        "borderlineDoubtShown": len(borderline),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
