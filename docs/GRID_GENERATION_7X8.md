# Pilotes de mots fléchés 7×8

La commande canonique est `scripts/run_compact_7x8_pilots.py`. Elle ne modifie
jamais le catalogue actif et ne publie rien.

## Smoke test reproductible

```powershell
python scripts/run_compact_7x8_pilots.py `
  --shape pilot-7x8-strict-04 `
  --lexicon hybrid `
  --attempts-per-shape 3 `
  --seconds-per-attempt 20 `
  --solution-limit 128 `
  --minimum-images 4 `
  --output-dir output/quality/pilot-7x8-smoke
```

Pour chercher une famille réellement différente d'un pilote existant :

```powershell
python scripts/run_compact_7x8_pilots.py `
  --shape pilot-7x8-strict-04 `
  --avoid-fill output/quality/pilot7x8-candidate1-reference.json `
  --minimum-solution-distance 8 `
  --attempts-per-shape 3 `
  --seconds-per-attempt 90 `
  --output-dir output/quality/pilot-7x8-diversity
```

## Reprise et cache

Chaque tentative reçoit une signature calculée à partir de la silhouette, de
la graine, du domaine lexical (`large`, `hybrid`, `wordfreq` ou `central`),
des contraintes et des fichiers de lexique, blacklist, solveur et
catalogue. `attempt-cache.json` conserve trois états distincts :

- `solved` : au moins une fermeture exacte ;
- `dead` : impasse mathématiquement prouvée ;
- `cutoff` : budget de temps atteint sans preuve d'impossibilité.

La même signature n'est jamais recalculée, y compris pour un `cutoff` : une
durée, une graine, une règle ou un fichier modifié produit une nouvelle
signature. `--force` est réservé au diagnostic volontaire.

`--deterministic` permet de parcourir exactement le même arbre et d'établir
une impasse. Sans cette option, la graine change l'ordre d'exploration. Les
choix `--branching-strategy` et `--cell-letter-order` font partie de la
signature et peuvent donc être comparés sans écraser les essais précédents.

### Solveur ruban et ancres éditoriales

Les silhouettes strictes 02, 03 et 04 disposent aussi d'un parcours ligne par
ligne avec cache persistant des seuls états mathématiquement morts. Une limite
de temps reste un `cutoff` et n'est jamais enregistrée comme une impossibilité.
Les mots intéressants choisis avant la fermeture peuvent être imposés par leur
indice de slot stable :

```powershell
python scripts/strict_ribbon_row_dfs.py `
  --shape-id pilot-7x8-strict-02 `
  --fixed-answer 0:NETFLIX `
  --fixed-answer 1:YOUTUBE `
  --seconds 60 `
  --cache output/quality/cache/strict-ribbon.sqlite3 `
  --checkpoint output/quality/strict-ribbon-checkpoint.json `
  --output output/quality/strict-ribbon-result.json
```

La signature du cache comprend la géométrie, le domaine réel, les seuils,
les remplissages à éviter et toutes les réponses imposées. Modifier une ancre
crée donc un contexte distinct sans invalider les preuves des essais précédents.

## Revue et playtest

`scripts/build_compact_7x8_review.py` écrit deux vues séparées lorsque
`--playtest-html` est fourni. La page éditoriale contient réponses,
provenances et décisions. La page de playtest retire les réponses de son HTML
et laisse saisir les lettres :

```powershell
python scripts/build_compact_7x8_review.py `
  --input output/quality/pilot-7x8-reviewed-source.json `
  --limit 3 `
  --staging output/quality/pilot-7x8-staging.json `
  --audit output/quality/pilot-7x8-audit.json `
  --html output/quality/pilot-7x8-editorial-review.html `
  --playtest-html output/quality/pilot-7x8-playtest.html
```

## Contrat bloquant

- plateau de 7 colonnes × 8 lignes ;
- première ligne et première colonne intégralement réservées aux définitions ;
- aucune réponse de moins de 3 lettres ;
- chaque case-lettre couverte exactement par une réponse horizontale et une
  réponse verticale ;
- blacklist dure respectée ;
- cooldown et présence dans le catalogue traités comme pénalités, pas comme
  interdictions définitives ;
- aucune publication automatique : les meilleurs remplissages passent encore
  par la revue sémantique, grammaticale, culturelle et visuelle.

Les résultats détaillés sont dans le dossier demandé : une sortie JSON par
tentative, `attempt-cache.json`, puis `candidate-pool.json` classé.
