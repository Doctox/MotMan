"""Audit the 15k-word definition reservoir and render a human review page."""
from __future__ import annotations

import argparse
import gzip
import html
import json
import random
import re
import unicodedata
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/data"
DEFAULT_CORPUS = DATA / "crossword.dbnary-definitions.review.json.gz"
DEFAULT_JSON = ROOT / "output/quality/corpus-15000-audit.json"
DEFAULT_HTML = ROOT / "output/quality/corpus-15000-audit.html"


def fold(value: str) -> str:
    return re.sub(
        r"[^A-Z]",
        "",
        "".join(
            char
            for char in unicodedata.normalize("NFD", value.upper())
            if unicodedata.category(char) != "Mn"
        ),
    )


def frequency_tier(value: float) -> str:
    if value >= 15:
        return "tres-courant"
    if value >= 3:
        return "courant"
    if value >= 0.5:
        return "moins-courant"
    return "rare"


def definition_mentions_answer(entry: dict) -> bool:
    answer = entry["answer"]
    words = {fold(word) for word in re.findall(r"[A-Za-zÀ-ÿŒœ]+", entry["sourceDefinition"])}
    return answer in words


def load_generator_inventory() -> dict:
    # Mirror the current loader's explicit inputs without importing the grid
    # solver.  The production loader intentionally keeps only one entry per
    # answer, which is a separate limitation reported below.
    source_names = [
        "crossword.corpus.json",
        "crossword.curated.json",
        "crossword.images-reviewed.json",
        "crossword.reference-reviewed.json",
    ]
    raw_entries: list[dict] = []
    by_file = {}
    for name in source_names:
        document = json.loads((DATA / name).read_text(encoding="utf-8"))
        entries = document["entries"]
        raw_entries.extend(entries)
        by_file[name] = {
            "pairs": len(entries),
            "distinctAnswers": len({entry["answer"] for entry in entries}),
        }
    return {
        "explicitFiles": by_file,
        "rawPairsAcrossExplicitFiles": len(raw_entries),
        "distinctAnswersAcrossExplicitFiles": len({
            entry["answer"] for entry in raw_entries
        }),
        "loaderBehavior": "un seul couple conserve par reponse (dictionnaire by_answer)",
        "definitionReservoirAutomaticallyLoaded": False,
    }


def build_audit(document: dict) -> dict:
    entries = document["entries"]
    answers = Counter(entry["answer"] for entry in entries)
    answer_set = set(answers)
    source_senses = Counter(entry["sourceSenseId"] for entry in entries)
    blacklist = json.loads(
        (DATA / "editorial.blacklist.json").read_text(encoding="utf-8")
    )
    blocked = set(blacklist.get("rejectedAnswers", []))
    blocked.update(
        entry["answer"] for entry in blacklist.get("rotationCooldownAnswers", [])
    )
    inflection_families = sorted(
        (answer, f"{answer}S")
        for answer in answer_set
        if len(answer) >= 3 and f"{answer}S" in answer_set
    )
    by_tier = Counter(
        frequency_tier(float(entry["answerSourceFrequency"])) for entry in entries
    )
    unique_by_tier = {
        tier: len({
            entry["answer"]
            for entry in entries
            if frequency_tier(float(entry["answerSourceFrequency"])) == tier
        })
        for tier in ("tres-courant", "courant", "moins-courant", "rare")
    }
    flags = {
        "blacklistOrCooldownLeaks": sorted(answer_set & blocked),
        "duplicateSourceSenseIds": sorted(
            sense for sense, count in source_senses.items() if count > 1
        ),
        "entriesMarkedPlayableAsIs": sum(
            bool(entry.get("playableAsIs")) for entry in entries
        ),
        "definitionsMentioningAnswer": sum(
            definition_mentions_answer(entry) for entry in entries
        ),
        "definitionsOver120Characters": sum(
            len(entry["sourceDefinition"]) > 120 for entry in entries
        ),
        "visibleSingularPluralFamiliesInReservoir": len(inflection_families),
    }
    blocking = bool(
        flags["blacklistOrCooldownLeaks"]
        or flags["duplicateSourceSenseIds"]
        or flags["entriesMarkedPlayableAsIs"]
        or len(answer_set) < 15_000
    )
    randomizer = random.Random(20260715)
    samples = {}
    for tier in ("tres-courant", "courant", "moins-courant", "rare"):
        pool = [
            entry for entry in entries
            if frequency_tier(float(entry["answerSourceFrequency"])) == tier
        ]
        samples[tier] = randomizer.sample(pool, min(12, len(pool)))
    return {
        "version": 1,
        "verdict": {
            "validDefinitionReservoir": not blocking,
            "minimumDistinctAnswers": 15_000,
            "distinctAnswers": len(answer_set),
            "gridGenerationMayResume": False,
            "reason": (
                "Le reservoir de sens est suffisant, mais ses definitions longues "
                "ne sont pas des indices mobiles. Les couples courts doivent etre "
                "rediges et revus avant utilisation."
            ),
        },
        "corpus": {
            "sourceBackedDefinitionPairs": len(entries),
            "distinctAnswers": len(answer_set),
            "distinctAnswersByLength": document["metrics"]["distinctAnswersByLength"],
            "pairsByLength": document["metrics"]["pairsByLength"],
            "pairsByFrequencyTier": dict(by_tier),
            "distinctAnswersByFrequencyTier": unique_by_tier,
            "answersWithMultipleSenses": sum(count > 1 for count in answers.values()),
            "maximumSensesForOneAnswer": max(answers.values(), default=0),
            "source": document["source"],
            "eligibilityPolicy": document["eligibilityPolicy"],
        },
        "currentGenerator": load_generator_inventory(),
        "qualityFlags": flags,
        "inflectionFamilyExamples": inflection_families[:100],
        "samples": samples,
        "decisions": [
            "Le reservoir DBnary n'est pas branche automatiquement au generateur.",
            "Une definition source longue sert a verifier le sens, pas a remplir une case-definition.",
            "Les synonymes JeuxDeMots restent des suggestions et non des couples prets a jouer.",
            "Les familles singulier/pluriel seront interdites dans une meme grille et mesurees entre grilles.",
            "Les silhouettes doivent limiter leur dependance aux mots de trois lettres: seulement 263 reponses distinctes.",
        ],
    }


def render_html(audit: dict) -> str:
    corpus = audit["corpus"]
    verdict = audit["verdict"]
    flags = audit["qualityFlags"]
    cards = [
        ("Réponses distinctes", f"{corpus['distinctAnswers']:,}".replace(",", " ")),
        ("Définitions sourcées", f"{corpus['sourceBackedDefinitionPairs']:,}".replace(",", " ")),
        ("Mots de 3 lettres", corpus["distinctAnswersByLength"].get("3", 0)),
        ("Prêts à jouer sans revue", flags["entriesMarkedPlayableAsIs"]),
    ]
    card_html = "".join(
        f'<div class="card"><span>{html.escape(str(label))}</span><strong>{html.escape(str(value))}</strong></div>'
        for label, value in cards
    )
    length_rows = "".join(
        f"<tr><td>{length}</td><td>{count}</td><td>{corpus['pairsByLength'][length]}</td></tr>"
        for length, count in corpus["distinctAnswersByLength"].items()
    )
    tier_labels = {
        "tres-courant": "Très courant",
        "courant": "Courant",
        "moins-courant": "Moins courant",
        "rare": "Rare / réservoir difficile",
    }
    sample_sections = []
    for tier, entries in audit["samples"].items():
        rows = "".join(
            "<tr>"
            f"<td><strong>{html.escape(entry['answer'])}</strong></td>"
            f"<td>{entry['answerSourceFrequency']}</td>"
            f"<td>{html.escape(entry['sourceDefinition'])}</td>"
            "</tr>"
            for entry in entries
        )
        sample_sections.append(
            f"<h3>{html.escape(tier_labels[tier])}</h3>"
            "<table><thead><tr><th>Réponse</th><th>Fréquence</th><th>Définition source (pas l'indice final)</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    generator = audit["currentGenerator"]
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit du corpus 15 000 — MotMan</title>
<style>
:root{{--ink:#18342d;--muted:#5f716b;--paper:#fbfaf5;--line:#cad9d2;--good:#0f6b4f;--warn:#9b5b12}}
*{{box-sizing:border-box}} body{{margin:0;background:#eff4f0;color:var(--ink);font:15px/1.45 system-ui,sans-serif}}
main{{max-width:1180px;margin:auto;padding:28px}} h1{{font-size:30px;margin:0 0 8px}} h2{{margin-top:34px}} h3{{margin:26px 0 8px}}
.lead{{font-size:17px;color:var(--muted);max-width:900px}} .verdict{{padding:16px 18px;border-left:6px solid var(--good);background:#eaf7f0;border-radius:8px;margin:20px 0}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}} .card{{background:white;border:1px solid var(--line);border-radius:10px;padding:14px;display:flex;flex-direction:column}} .card span{{color:var(--muted)}} .card strong{{font-size:28px}}
table{{border-collapse:collapse;width:100%;background:white}} th,td{{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}} th{{background:#e7f0eb}} code{{background:#e6ece8;padding:2px 5px;border-radius:4px}} .warning{{color:var(--warn)}}
</style></head><body><main>
<h1>Audit du corpus français</h1>
<p class="lead">Le seuil est compté en <strong>réponses distinctes</strong>, pas en sens inversés ni en doublons. Toutes les définitions ci-dessous viennent du dump DBnary/Wiktionnaire et gardent leur identifiant de sens.</p>
<div class="verdict"><strong>Réservoir valide : {'OUI' if verdict['validDefinitionReservoir'] else 'NON'}.</strong> {html.escape(verdict['reason'])}</div>
<div class="cards">{card_html}</div>
<h2>Couverture par longueur</h2>
<table><thead><tr><th>Longueur</th><th>Réponses distinctes</th><th>Definitions/sens</th></tr></thead><tbody>{length_rows}</tbody></table>
<p class="warning"><strong>Point de vigilance :</strong> 263 mots de trois lettres seulement. Une silhouette qui exige trop de petites réponses recréera forcément FER, MER, SEL, ILE, ANS, etc.</p>
<h2>Ce que le générateur utilise aujourd'hui</h2>
<p>Les fichiers explicitement chargés contiennent {generator['rawPairsAcrossExplicitFiles']} couples pour {generator['distinctAnswersAcrossExplicitFiles']} réponses distinctes. Le chargeur conserve actuellement <strong>un seul couple par réponse</strong>. Le nouveau réservoir n'est pas branché automatiquement : c'est volontaire tant que les indices courts ne sont pas revus.</p>
<h2>Contrôles bloquants</h2>
<ul><li>Fuites blacklist/cooldown : {len(flags['blacklistOrCooldownLeaks'])}</li><li>Identifiants de sens dupliqués : {len(flags['duplicateSourceSenseIds'])}</li><li>Entrées marquées jouables sans revue : {flags['entriesMarkedPlayableAsIs']}</li><li>Définitions longues (&gt;120 caractères) : {flags['definitionsOver120Characters']} — conservées comme preuve du sens, jamais comme indice mobile</li><li>Familles singulier/pluriel présentes dans le réservoir : {flags['visibleSingularPluralFamiliesInReservoir']} — autorisées dans le stock, interdites ensemble dans une grille</li></ul>
<h2>Échantillon déterministe</h2>
{''.join(sample_sections)}
</main></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    args = parser.parse_args()
    with gzip.open(args.corpus, "rt", encoding="utf-8") as handle:
        document = json.load(handle)
    audit = build_audit(document)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    args.html.write_text(render_html(audit), encoding="utf-8")
    print(json.dumps({
        "json": str(args.json),
        "html": str(args.html),
        "validDefinitionReservoir": audit["verdict"]["validDefinitionReservoir"],
        "distinctAnswers": audit["corpus"]["distinctAnswers"],
        "sourceBackedDefinitionPairs": audit["corpus"]["sourceBackedDefinitionPairs"],
    }, ensure_ascii=False))
    if not audit["verdict"]["validDefinitionReservoir"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
