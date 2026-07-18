"""Build the complete owner review page for unresolved JeuxDeMots pairs.

The exhaustive triage ledger remains the source of truth. This report only
exposes statuses that still require an editorial decision; it never promotes
a pair by itself.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
SOURCE = DATA / "crossword.jeuxdemots.full-triage.json.gz"
OUTPUT_JSON = ROOT / "output/quality/jeuxdemots-owner-full-doubt.json"
OUTPUT_HTML = ROOT / "output/quality/jeuxdemots-owner-doubt.html"
OWNER_DECISIONS = DATA / "jeuxdemots.owner-full-decisions.json"

REVIEW_STATUSES = {
    "selected-editorial-candidate",
    "doubt-alternative-candidate",
    "doubt-reciprocal",
    "doubt-cross-source-nonreciprocal",
}

STATUS_LABELS = {
    "selected-editorial-candidate": "Candidat prioritaire",
    "doubt-alternative-candidate": "Alternative",
    "doubt-reciprocal": "Relation réciproque à confirmer",
    "doubt-cross-source-nonreciprocal": "Recoupé par une autre source",
}

STATUS_PRIORITY = {
    "selected-editorial-candidate": 0,
    "doubt-alternative-candidate": 1,
    "doubt-cross-source-nonreciprocal": 2,
    "doubt-reciprocal": 3,
}


def stable_id(entry: dict) -> str:
    payload = json.dumps(
        [entry["answer"], entry["clue"], entry["triageStatus"]],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"JDM-{hashlib.sha256(payload).hexdigest()[:16]}"


def source_digest(entries: list[dict]) -> str:
    payload = json.dumps(
        sorted(
            (entry["answer"], entry["clue"], entry["status"])
            for entry in entries
        ),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def review_entry(entry: dict) -> dict:
    return {
        "id": stable_id(entry),
        "answer": entry["answer"],
        "clue": entry["clue"],
        "length": entry.get("length"),
        "status": entry["triageStatus"],
        "statusLabel": STATUS_LABELS[entry["triageStatus"]],
        "reasons": entry.get("triageReasons", []),
        "reciprocal": bool(entry.get("reciprocal")),
        "wolfCorroborated": bool(entry.get("wolfCorroborated")),
        "relationWeight": entry.get("mutualRelationWeight")
        or entry.get("sourceRelationWeight"),
        "relationRank": entry.get("maximumRelationRank")
        or entry.get("answerRelationRank"),
        "frequency": entry.get("minimumSourceFrequency"),
    }


def build_document(source: dict) -> dict:
    entries = [
        review_entry(entry)
        for entry in source["entries"]
        if entry.get("triageStatus") in REVIEW_STATUSES
    ]
    entries.sort(
        key=lambda entry: (
            STATUS_PRIORITY[entry["status"]],
            -(entry.get("relationWeight") or 0),
            entry.get("relationRank") or 99,
            -(entry.get("frequency") or 0),
            entry["answer"],
            entry["clue"].casefold(),
        )
    )
    digest = source_digest(entries)
    status_counts = Counter(entry["status"] for entry in entries)
    return {
        "version": 2,
        "kind": "jeuxdemots-owner-full-doubt-review",
        "sourceDigest": digest,
        "publicationPolicy": (
            "Aucun couple de cette feuille n'est publiable sans une décision "
            "explicite. Les choix restent locaux jusqu'à l'export JSON."
        ),
        "metrics": {
            "totalReviewablePairs": len(entries),
            "statusCounts": dict(sorted(status_counts.items())),
        },
        "entries": entries,
    }


def load_owner_seed(source_digest: str, path: Path = OWNER_DECISIONS) -> dict[str, str]:
    """Restore already applied choices when the browser storage is unavailable."""
    if not path.exists():
        return {}
    owner = json.loads(path.read_text(encoding="utf-8"))
    if owner.get("sourceDigest") != source_digest:
        raise ValueError(
            "les décisions propriétaire enregistrées ne correspondent plus à la page"
        )
    allowed = {"accept", "reject", "doubt"}
    return {
        item["id"]: item["decision"]
        for item in owner.get("decisions", [])
        if item.get("decision") in allowed
    }


def render(document: dict, initial_decisions: dict[str, str] | None = None) -> str:
    entries_json = json.dumps(
        document["entries"], ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")
    labels_json = json.dumps(STATUS_LABELS, ensure_ascii=False)
    total = document["metrics"]["totalReviewablePairs"]
    digest = document["sourceDigest"]
    initial_decisions = initial_decisions or {}
    initial_decisions_json = json.dumps(
        initial_decisions, ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")
    restored = len(initial_decisions)
    template = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Décisions JeuxDeMots complètes — MotMan</title>
<style>
:root{color-scheme:light;--ink:#17251f;--line:#bdc9c3;--green:#08723d;--red:#b32222;--amber:#8a6300}
*{box-sizing:border-box}body{font:15px system-ui;margin:0;color:var(--ink);background:#f6f8f7}
main{max-width:1320px;margin:auto;padding:24px 18px 60px}h1{margin:.2rem 0}.note{background:#fff5cc;border:1px solid #d8ba4a;padding:12px;border-radius:8px}
.toolbar{position:sticky;top:0;z-index:5;background:#fff;border:1px solid #aebdb5;box-shadow:0 3px 12px #0002;padding:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;border-radius:8px}
.stats{width:100%;display:flex;gap:14px;flex-wrap:wrap}.stats strong{font-size:1.05rem}input,button,select{font:inherit;padding:8px 10px;border:1px solid #8fa198;border-radius:6px;background:white}input[type=search]{min-width:240px;flex:1}button{cursor:pointer}
.pager{display:flex;gap:8px;align-items:center;margin:14px 0;justify-content:flex-end}.pager button:disabled{opacity:.4;cursor:not-allowed}
.table-wrap{overflow:auto;background:white;border:1px solid var(--line);border-radius:8px}table{border-collapse:collapse;width:100%;min-width:930px}th,td{border-bottom:1px solid var(--line);padding:8px;text-align:left;vertical-align:middle}th{position:sticky;top:0;background:#eef5f1;z-index:2}td.answer{font-weight:750;font-size:1.05rem}.muted{color:#607068;font-size:.88rem}.choices{white-space:nowrap}.choices button{font-size:18px;min-width:42px;margin:2px}.choices [data-decision=accept]{color:var(--green)}.choices [data-decision=reject]{color:var(--red)}.choices [data-decision=doubt]{color:var(--amber)}
tr.decision-accept{background:#e5f8ec}tr.decision-reject{background:#fde8e8}tr.decision-doubt{background:#fff4ce}.choices button.selected{color:white}.choices [data-decision=accept].selected{background:var(--green)}.choices [data-decision=reject].selected{background:var(--red)}.choices [data-decision=doubt].selected{background:#9b7100}.saved{color:var(--green);font-weight:700}.empty{text-align:center;padding:28px}.priority{font-weight:700;color:#185d42}
@media(max-width:700px){main{padding:12px 8px 40px}.toolbar{position:static}.stats{gap:8px}.secondary{display:none}.pager{justify-content:space-between}}
</style></head><body><main>
<h1>JeuxDeMots — tous les couples encore à arbitrer</h1>
<p class="note"><b>__TOTAL__ couples sont bien présents.</b> <b>__RESTORED__ décisions déjà remises sont restaurées depuis le corpus.</b> Clique sur <b>✓</b> pour valider, <b>✕</b> pour refuser ou <b>?</b> pour conserver le doute. Tes nouveaux choix sont sauvegardés automatiquement dans ce navigateur. Télécharge le JSON lorsque tu veux me les remettre.</p>
<section class="toolbar" aria-label="Outils de revue">
  <div class="stats"><span>Total <strong id="total">__TOTAL__</strong></span><span>Traités <strong id="done">0</strong></span><span>✓ <strong id="accepted">0</strong></span><span>✕ <strong id="rejected">0</strong></span><span>? <strong id="doubted">0</strong></span><span>Restants <strong id="pending">__TOTAL__</strong></span></div>
  <input id="search" type="search" placeholder="Chercher un mot ou un indice…" aria-label="Chercher">
  <select id="decisionFilter" aria-label="Filtrer par décision"><option value="all">Toutes les décisions</option><option value="pending" selected>Seulement à traiter</option><option value="accept">Validés</option><option value="reject">Refusés</option><option value="doubt">Conservés en doute</option></select>
  <select id="statusFilter" aria-label="Filtrer par origine"><option value="all">Toutes les catégories</option></select>
  <select id="pageSize" aria-label="Nombre par page"><option>50</option><option selected>100</option><option>200</option></select>
  <button type="button" id="copy">Copier le bilan</button><button type="button" id="download">Télécharger le JSON</button><span class="saved" id="saved"></span>
</section>
<div class="pager"><span id="visibleCount"></span><button type="button" id="previous">← Précédente</button><strong id="pageInfo"></strong><button type="button" id="next">Suivante →</button></div>
<div class="table-wrap"><table><thead><tr><th>Réponse</th><th>Indice proposé</th><th>Catégorie</th><th class="secondary">Preuves</th><th class="secondary">Pourquoi en doute</th><th>Décision</th></tr></thead><tbody id="rows"></tbody></table></div>
<div class="pager"><button type="button" id="previousBottom">← Précédente</button><strong id="pageInfoBottom"></strong><button type="button" id="nextBottom">Suivante →</button></div>
</main><script>
const entries=__ENTRIES__;
const statusLabels=__STATUS_LABELS__;
const sourceDigest='__DIGEST__';
const storageKey=`motman-jdm-full-doubt-decisions-${sourceDigest}`;
const restoredDecisions=__INITIAL_DECISIONS__;
const browserDecisions=JSON.parse(localStorage.getItem(storageKey)||'{}');
let decisions={...restoredDecisions,...browserDecisions};
let page=1;
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const decisionOf=item=>decisions[item.id]||'pending';
for(const [value,label] of Object.entries(statusLabels)){const option=document.createElement('option');option.value=value;option.textContent=label;$('statusFilter').append(option)}
function save(){localStorage.setItem(storageKey,JSON.stringify(decisions));$('saved').textContent='Enregistré';setTimeout(()=>$('saved').textContent='',900)}
function matching(){const query=$('search').value.trim().toLocaleLowerCase('fr');const decision=$('decisionFilter').value;const status=$('statusFilter').value;return entries.filter(item=>(!query||`${item.answer} ${item.clue}`.toLocaleLowerCase('fr').includes(query))&&(decision==='all'||decisionOf(item)===decision)&&(status==='all'||item.status===status))}
function renderStats(){const counts={accept:0,reject:0,doubt:0,pending:0};for(const item of entries)counts[decisionOf(item)]++;$('accepted').textContent=counts.accept;$('rejected').textContent=counts.reject;$('doubted').textContent=counts.doubt;$('pending').textContent=counts.pending;$('done').textContent=counts.accept+counts.reject+counts.doubt}
function evidence(item){const bits=[];if(item.reciprocal)bits.push('réciproque');if(item.wolfCorroborated)bits.push('WOLF/Eduscol');if(item.relationWeight)bits.push(`poids ${item.relationWeight}`);if(item.relationRank)bits.push(`rang ${item.relationRank}`);if(item.frequency!=null)bits.push(`fréq. ${Number(item.frequency).toFixed(1)}`);return bits.join(' · ')}
function render(){renderStats();const items=matching();const size=Number($('pageSize').value);const pages=Math.max(1,Math.ceil(items.length/size));page=Math.min(page,pages);const shown=items.slice((page-1)*size,page*size);$('rows').innerHTML=shown.length?shown.map(item=>{const decision=decisionOf(item);return `<tr data-id="${esc(item.id)}" class="${decision==='pending'?'':`decision-${decision}`}"><td class="answer">${esc(item.answer)} <span class="muted">${item.length||''}</span></td><td>${esc(item.clue)}</td><td class="${item.status==='selected-editorial-candidate'?'priority':''}">${esc(item.statusLabel)}</td><td class="secondary muted">${esc(evidence(item))}</td><td class="secondary muted">${esc(item.reasons.join(' ; '))}</td><td class="choices"><button type="button" data-decision="accept" class="${decision==='accept'?'selected':''}" title="Valider" aria-label="Valider ${esc(item.answer)}">✓</button><button type="button" data-decision="reject" class="${decision==='reject'?'selected':''}" title="Refuser" aria-label="Refuser ${esc(item.answer)}">✕</button><button type="button" data-decision="doubt" class="${decision==='doubt'?'selected':''}" title="Garder en doute" aria-label="Garder ${esc(item.answer)} en doute">?</button></td></tr>`}).join(''):'<tr><td colspan="6" class="empty">Aucun couple ne correspond à ce filtre.</td></tr>';$('visibleCount').textContent=`${items.length} couple${items.length>1?'s':''} affichable${items.length>1?'s':''}`;for(const id of ['pageInfo','pageInfoBottom'])$(id).textContent=`Page ${page} / ${pages}`;for(const id of ['previous','previousBottom'])$(id).disabled=page<=1;for(const id of ['next','nextBottom'])$(id).disabled=page>=pages}
$('rows').addEventListener('click',event=>{const button=event.target.closest('button[data-decision]');if(!button)return;const row=button.closest('tr[data-id]');decisions[row.dataset.id]=button.dataset.decision;save();render()});
for(const id of ['search','decisionFilter','statusFilter','pageSize'])$(id).addEventListener(id==='search'?'input':'change',()=>{page=1;render()});
for(const id of ['previous','previousBottom'])$(id).addEventListener('click',()=>{page--;render();scrollTo({top:0,behavior:'smooth'})});for(const id of ['next','nextBottom'])$(id).addEventListener('click',()=>{page++;render();scrollTo({top:0,behavior:'smooth'})});
function exportData(){return {version:2,sourceDigest,exportedAt:new Date().toISOString(),counts:{total:entries.length,decided:Object.keys(decisions).length},decisions:entries.map(item=>({id:item.id,answer:item.answer,clue:item.clue,category:item.status,decision:decisionOf(item)}))}}
$('copy').addEventListener('click',async()=>{const text=JSON.stringify(exportData(),null,2);try{await navigator.clipboard.writeText(text)}catch{const area=document.createElement('textarea');area.value=text;document.body.append(area);area.select();document.execCommand('copy');area.remove()}$('copy').textContent='Bilan copié ✓'});
$('download').addEventListener('click',()=>{const link=document.createElement('a');link.href=URL.createObjectURL(new Blob([JSON.stringify(exportData(),null,2)],{type:'application/json'}));link.download='jeuxdemots-full-decisions.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000)});
render();
</script></body></html>"""
    return (
        template.replace("__TOTAL__", f"{total:,}".replace(",", " "))
        .replace("__RESTORED__", f"{restored:,}".replace(",", " "))
        .replace("__ENTRIES__", entries_json)
        .replace("__STATUS_LABELS__", labels_json)
        .replace("__DIGEST__", digest)
        .replace("__INITIAL_DECISIONS__", initial_decisions_json)
    )


def main() -> int:
    with gzip.open(SOURCE, "rt", encoding="utf-8") as handle:
        source = json.load(handle)
    document = build_document(source)
    initial_decisions = load_owner_seed(document["sourceDigest"])
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    OUTPUT_HTML.write_text(
        render(document, initial_decisions=initial_decisions), encoding="utf-8"
    )
    print(json.dumps({
        **document["metrics"],
        "restoredOwnerDecisions": len(initial_decisions),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
