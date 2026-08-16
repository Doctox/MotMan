// Contrôle de build du calendrier du défi du jour (contrat 3, §4 — invariant dur).
//
// POURQUOI CE SCRIPT EXISTE : `npm run policy:runtime` NE FILTRE RIEN. Le filtrage
// par isCatalogGridPlayable a lieu à l'exécution dans generator.ts
// (`catalog.grids.filter(isCatalogGridPlayable)`). Sans ce contrôle, un calendrier
// qui pointe vers une grille absente ou injouable passe inaperçu au build et la
// grille du jour disparaît SILENCIEUSEMENT en production. Ce script fait ÉCHOUER le
// build dans ce cas (exit 1), au lieu de dégrader en silence.
//
// Il rejoue exactement la logique de isCatalogGridPlayable (gridCatalogPolicy.ts).

import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const DATA_DIR = path.resolve(process.cwd(), 'src', 'data')
const CALENDAR = path.join(DATA_DIR, 'runtime.daily.calendar.json')
const CATALOG = path.join(DATA_DIR, 'runtime.grid.catalog.json')
const POLICY = path.join(DATA_DIR, 'runtime.catalog-policy.json')

// Doit rester synchronisé avec BLOCKED_ANSWERS de src/gridCatalogPolicy.ts.
const BLOCKED_ANSWERS = new Set([
  'SS', 'TT', 'PCQ', 'FDP', 'IBN', 'KIL', 'NUD', 'GEN', 'INN', 'THE', 'GUEST', 'BOARD', 'CHAN',
  'BESEF', 'TUT', 'ATON', 'SPEED',
])
const NUL = String.fromCharCode(0)

function fail(message) {
  console.error(`\n✖ Calendrier du défi du jour invalide — build interrompu.\n  ${message}\n`)
  process.exit(1)
}

function readJson(file, label) {
  if (!fs.existsSync(file)) fail(`${label} introuvable : ${file}`)
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch (reason) {
    fail(`${label} illisible (${reason instanceof Error ? reason.message : reason}) : ${file}`)
  }
}

// Le calendrier est optionnel tant que la feature n'est pas lancée : son absence
// n'échoue pas le build (le fallback couvre tout). S'il existe, il doit être valide.
if (!fs.existsSync(CALENDAR)) {
  console.log('• Pas de runtime.daily.calendar.json — rien à vérifier (fallback catalogue générique).')
  process.exit(0)
}

const calendar = readJson(CALENDAR, 'runtime.daily.calendar.json')
const catalog = readJson(CATALOG, 'runtime.grid.catalog.json')
const policy = readJson(POLICY, 'runtime.catalog-policy.json')

if (!Array.isArray(calendar.days)) fail('Le calendrier doit contenir un tableau `days`.')

const quarantined = new Set(policy.quarantinedGridIds ?? [])
const rejectedAnswers = new Set(policy.rejectedAnswers ?? [])
const rejectedPairs = new Set(policy.rejectedPairs ?? [])

function isCatalogGridPlayable(grid) {
  if (!grid) return false
  if (quarantined.has(grid.id)) return false
  return grid.words.every(word =>
    !BLOCKED_ANSWERS.has(word.answer)
    && !rejectedAnswers.has(word.answer)
    && !rejectedPairs.has(`${word.answer}${NUL}${word.clue ?? ''}`)
    && Boolean((word.clue && word.clue.trim()) || word.image))
}

const byId = new Map(catalog.grids.map(grid => [grid.id, grid]))
const errors = []
const seenDates = new Set()
const dateFormat = /^\d{4}-\d{2}-\d{2}$/

for (const [index, entry] of calendar.days.entries()) {
  const where = `days[${index}] (${entry?.date ?? '??'})`
  if (!entry || typeof entry !== 'object') { errors.push(`${where} : entrée invalide`); continue }
  if (!dateFormat.test(entry.date ?? '')) errors.push(`${where} : date non conforme à YYYY-MM-DD`)
  if (seenDates.has(entry.date)) errors.push(`${where} : date en double`)
  seenDates.add(entry.date)
  if (typeof entry.gridId !== 'string' || !entry.gridId) { errors.push(`${where} : gridId manquant`); continue }
  const grid = byId.get(entry.gridId)
  if (!grid) errors.push(`${where} : gridId « ${entry.gridId} » absent de runtime.grid.catalog.json`)
  else if (!isCatalogGridPlayable(grid)) errors.push(`${where} : gridId « ${entry.gridId} » présent mais NON jouable (isCatalogGridPlayable=false)`)
}

if (errors.length) {
  fail(`${errors.length} problème(s) :\n  - ${errors.join('\n  - ')}`)
}

// ── Couverture future ────────────────────────────────────────────────────────
// Le calendrier expirait au 18/09/2026 sans que rien ne le signale : passé cette
// date, la grille « du jour » n'aurait plus rien de partagé, le repli générique
// aurait pris le relais EN SILENCE. On mesure donc la couverture CONTIGUË à
// partir d'aujourd'hui (Europe/Paris, comme la bascule de minuit du défi) :
// moins de 30 jours devant → avertissement, moins de 7 → échec du build.
const COVERAGE_WARNING_DAYS = 30
const COVERAGE_ERROR_DAYS = 7

function dayNumber(key) {
  const [year, month, day] = key.split('-').map(Number)
  return Math.floor(Date.UTC(year, month - 1, day) / 86_400_000)
}

const today = new Intl.DateTimeFormat('fr-CA', { timeZone: 'Europe/Paris', year: 'numeric', month: '2-digit', day: '2-digit' })
  .format(new Date())
const covered = new Set([...seenDates].map(dayNumber))
let remaining = 0
while (covered.has(dayNumber(today) + remaining)) remaining += 1

const regenerate = 'Régénérez-le : `node scripts/build_daily_calendar.mjs --days=240`.'
if (remaining < COVERAGE_ERROR_DAYS) {
  fail(`Couverture future insuffisante : ${remaining} jour(s) programmé(s) à partir du ${today} (seuil bloquant : ${COVERAGE_ERROR_DAYS}).\n  ${regenerate}`)
}
if (remaining < COVERAGE_WARNING_DAYS) {
  console.warn(`⚠ Calendrier du défi du jour : plus que ${remaining} jour(s) programmé(s) à partir du ${today}. ${regenerate}`)
}

console.log(`✓ Calendrier du défi du jour valide : ${calendar.days.length} jour(s), tous les gridId existent et sont jouables (catalogue v${catalog.version}). Couverture : ${remaining} jour(s) à partir du ${today}.`)
