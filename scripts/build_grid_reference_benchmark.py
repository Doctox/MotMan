"""Build the internal six-product arrowword layout benchmark.

Screenshots are official store media kept under output/quality for structural
research only.  They are never bundled into the game or used as puzzle data.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "output/quality/reference-research/six-source-benchmark"

PRODUCTS = [
    {
        "name": "Mots Fléchés Français — Alpine Studio",
        "url": "https://play.google.com/store/apps/details?id=com.motsflechesfrancais&hl=fr",
        "image": "alpine-0.png",
        "layout": "Grand rectangle, définitions internes nombreuses, quelques voisines.",
        "takeaways": ["flèches directes", "longueurs très variées", "pas de cadre complet"],
    },
    {
        "name": "Mots Fléchés : Mots Croisés — MBEX",
        "url": "https://apps.apple.com/fr/app/mots-fl%C3%A9ch%C3%A9s-mots-crois%C3%A9s/id6470312336",
        "image": "mbex-1.jpg",
        "layout": "Définitions réparties, cases doubles ponctuelles, grille plus grande que 9×9.",
        "takeaways": ["départ immédiatement après la flèche", "pas de mur de définitions", "indices courts"],
    },
    {
        "name": "Mots Fléchés Sport Cérébral",
        "url": "https://apps.apple.com/fr/app/mots-fl%C3%A9ch%C3%A9s-sport-c%C3%A9r%C3%A9bral/id1233675690",
        "image": "sport-cerebral-1.png",
        "layout": "Silhouette ouverte, définitions internes espacées, plusieurs niveaux éditoriaux.",
        "takeaways": ["flèches directes", "mots longs dominants possibles", "densité adaptée au niveau"],
    },
    {
        "name": "Mots Fléchés — RCI Jeux",
        "url": "https://apps.apple.com/fr/app/mots-fl%C3%A9ch%C3%A9s/id364475194",
        "image": "rci-jeux-0.png",
        "layout": "Cases bleues internes, doubles définitions empilées, pointes vers droite ou bas.",
        "takeaways": ["double droite+bas lisible", "une flèche touche sa première lettre", "aucun coude"],
    },
    {
        "name": "Mots Fléchés & Mots Croisés — Digital Crosswords",
        "url": "https://apps.apple.com/fr/app/mots-fl%C3%A9ch%C3%A9s-mots-crois%C3%A9s/id688120018",
        "image": "digital-crosswords-0.png",
        "layout": "Cadre haut/gauche complet, complété par quelques définitions internes.",
        "takeaways": ["variante à cadre complet", "mots longs", "peu de blocs internes adjacents"],
    },
    {
        "name": "Arrow Crosswords — Havos",
        "url": "https://apps.apple.com/fr/app/mots-fl%C3%A9ch%C3%A9s/id1013462300",
        "image": "havos-1.png",
        "layout": "Grande grille très remplie, définitions grises distribuées, doubles fréquentes.",
        "takeaways": ["silhouettes irrégulières", "définitions parfois voisines mais sans murs", "longueurs libres"],
    },
]

COMMON_RULES = [
    "Flèche directe uniquement : droite ou bas, au contact de la première lettre.",
    "Toute case-lettre appartient à une entrée déclarée; aucun remplissage décoratif.",
    "Les définitions internes créent la silhouette; le cadre haut/gauche complet reste une variante.",
    "Une case peut porter une définition droite et une définition bas, sans minimum artificiel.",
    "Pas de quota par longueur : on contrôle seulement la variété et la domination d'une longueur.",
    "Les cellules de définition adjacentes sont tolérées ponctuellement, jamais en mur répétitif.",
]


def build(output_html: Path, output_json: Path) -> None:
    payload = {
        "version": 1,
        "purpose": "benchmark structurel interne; aucune grille ni définition copiée",
        "products": PRODUCTS,
        "commonRules": COMMON_RULES,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    cards = []
    for product in PRODUCTS:
        takeaways = "".join(f"<li>{html.escape(item)}</li>" for item in product["takeaways"])
        cards.append(f"""
        <article class="card">
          <h2>{html.escape(product['name'])}</h2>
          <a href="{html.escape(product['url'])}"><img src="six-source-benchmark/{product['image']}" alt="Capture officielle de {html.escape(product['name'])}"></a>
          <p>{html.escape(product['layout'])}</p><ul>{takeaways}</ul>
        </article>""")
    rules = "".join(f"<li>{html.escape(rule)}</li>" for rule in COMMON_RULES)
    output_html.write_text(f"""<!doctype html><html lang="fr"><meta charset="utf-8">
<title>Benchmark de six systèmes de mots fléchés</title>
<style>body{{font:16px system-ui;margin:28px;background:#f6f2e9;color:#17221f}}main{{max-width:1180px;margin:auto}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:20px}}.card,section{{background:white;border:1px solid #c8c2b6;border-radius:14px;padding:16px;box-shadow:0 5px 18px #0001}}img{{display:block;max-width:100%;max-height:620px;margin:auto;object-fit:contain}}h1,h2{{line-height:1.15}}h2{{font-size:18px}}li{{margin:.35em 0}}.warning{{color:#705126}}</style>
<main><h1>Six systèmes comparés avant de générer</h1>
<p class="warning">Captures officielles conservées pour recherche structurelle interne. Aucune grille, réponse ou définition n'est reprise.</p>
<section><h2>Règles communes retenues pour MotMan</h2><ol>{rules}</ol></section>
<div class="grid">{''.join(cards)}</div></main></html>""", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, default=ROOT / "output/quality/six-source-benchmark.html")
    parser.add_argument("--json", type=Path, default=ROOT / "output/quality/six-source-benchmark.json")
    args = parser.parse_args()
    build(args.html, args.json)
    print(args.html)


if __name__ == "__main__":
    main()
