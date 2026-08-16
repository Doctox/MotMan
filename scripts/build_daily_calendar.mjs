// Génération du calendrier du défi du jour (src/data/runtime.daily.calendar.json).
//
// POURQUOI CE SCRIPT EXISTE : le calendrier était écrit à la main, s'arrêtait au
// 18/09/2026 et annonçait des thèmes (« Sport », « Animaux »…) que les grilles
// pointées n'ont pas — les 56 grilles publiées sont génériques. Deux problèmes :
//  1. une couverture qui expire en silence (le repli générique prend le relais) ;
//  2. une promesse fausse faite au joueur.
// Ce script règle les deux : il pioche de façon DÉTERMINISTE dans les grilles
// jouables du catalogue et écrit `theme: null` partout. Le champ `theme` reste au
// format gravé (contrat 3) : il sera renseigné le jour où de vraies grilles à
// thème existeront. Tant qu'il vaut null, l'UI n'affiche aucun libellé de thème.
//
// RÉPARTITION : sélection « moins récemment utilisée » avec fenêtre de choix
// déterministe (hachage FNV-1a de la date, cohérent avec seedFromDate). Sur 56
// grilles jouables et une fenêtre de 8, l'écart minimal entre deux passages d'une
// même grille est de 49 jours ; deux jours consécutifs ne peuvent jamais partager
// la même grille. Les entrées antérieures à la date de départ sont conservées
// telles quelles (on ne réécrit pas le passé), et servent d'amorce à la sélection.
//
// Usage :
//   node scripts/build_daily_calendar.mjs                    # depuis aujourd'hui, 240 jours
//   node scripts/build_daily_calendar.mjs --from=2026-09-01 --days=365
//   node scripts/build_daily_calendar.mjs --check            # n'écrit rien, affiche le plan

import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const DATA_DIR = path.resolve(process.cwd(), 'src', 'data')
const CALENDAR = path.join(DATA_DIR, 'runtime.daily.calendar.json')
const CATALOG = path.join(DATA_DIR, 'runtime.grid.catalog.json')
const POLICY = path.join(DATA_DIR, 'runtime.catalog-policy.json')

/** Fenêtre de tirage parmi les grilles les moins récemment utilisées. */
const PICK_WINDOW = 8
const DEFAULT_DAYS = 240

// Doit rester synchronisé avec BLOCKED_ANSWERS de src/gridCatalogPolicy.ts.
const BLOCKED_ANSWERS = new Set([
  'SS', 'TT', 'PCQ', 'FDP', 'IBN', 'KIL', 'NUD', 'GEN', 'INN', 'THE', 'GUEST', 'BOARD', 'CHAN',
  'BESEF', 'TUT', 'ATON', 'SPEED',
])
const NUL = String.fromCharCode(0)

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'))
}

function argument(name, fallback) {
  const found = process.argv.find(item => item.startsWith(`--${name}=`))
  return found ? found.slice(name.length + 3) : fallback
}

function parisToday() {
  return new Intl.DateTimeFormat('fr-CA', { timeZone: 'Europe/Paris', year: 'numeric', month: '2-digit', day: '2-digit' })
    .format(new Date())
}

function dayNumber(key) {
  const [year, month, day] = key.split('-').map(Number)
  return Math.floor(Date.UTC(year, month - 1, day) / 86_400_000)
}

function dateKeyFrom(number) {
  return new Date(number * 86_400_000).toISOString().slice(0, 10)
}

/** FNV-1a, identique à seedFromDate (src/dailyCalendar.ts). */
function seedFromDate(dateKey) {
  let hash = 2166136261
  for (const character of dateKey) {
    hash ^= character.charCodeAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

const catalog = readJson(CATALOG)
const policy = readJson(POLICY)
const quarantined = new Set(policy.quarantinedGridIds ?? [])
const rejectedAnswers = new Set(policy.rejectedAnswers ?? [])
const rejectedPairs = new Set(policy.rejectedPairs ?? [])

const playableIds = catalog.grids
  .filter(grid => !quarantined.has(grid.id) && grid.words.every(word =>
    !BLOCKED_ANSWERS.has(word.answer)
    && !rejectedAnswers.has(word.answer)
    && !rejectedPairs.has(`${word.answer}${NUL}${word.clue ?? ''}`)
    && Boolean((word.clue && word.clue.trim()) || word.image)))
  .map(grid => grid.id)
  .sort()

if (playableIds.length < 2) {
  console.error('\n✖ Moins de 2 grilles jouables au catalogue : calendrier impossible.\n')
  process.exit(1)
}

const from = argument('from', parisToday())
const days = Number(argument('days', String(DEFAULT_DAYS)))
const check = process.argv.includes('--check')
if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !Number.isInteger(days) || days <= 0) {
  console.error('\n✖ Paramètres invalides. Attendu : --from=YYYY-MM-DD --days=<entier positif>\n')
  process.exit(1)
}

const existing = fs.existsSync(CALENDAR) ? readJson(CALENDAR) : { days: [] }
const startNumber = dayNumber(from)
const preserved = (existing.days ?? [])
  .filter(entry => entry?.date && dayNumber(entry.date) < startNumber)
  .sort((first, second) => first.date.localeCompare(second.date))
  // Le passé garde sa grille mais perd ses thèmes factices : plus aucune
  // promesse de thème dans les données tant qu'aucune grille n'en porte.
  .map(entry => ({ date: entry.date, gridId: entry.gridId, theme: null, difficulty: entry.difficulty ?? 'normal' }))

// Amorce : « dernier usage » des grilles déjà programmées, en index négatifs.
const lastUsed = new Map()
preserved.forEach((entry, index) => {
  if (playableIds.includes(entry.gridId)) lastUsed.set(entry.gridId, index - preserved.length)
})

const generated = []
for (let offset = 0; offset < days; offset += 1) {
  const date = dateKeyFrom(startNumber + offset)
  const ranked = [...playableIds].sort((first, second) => {
    const firstUse = lastUsed.get(first)
    const secondUse = lastUsed.get(second)
    const firstRank = firstUse === undefined ? Number.NEGATIVE_INFINITY : firstUse
    const secondRank = secondUse === undefined ? Number.NEGATIVE_INFINITY : secondUse
    return firstRank === secondRank ? first.localeCompare(second) : firstRank - secondRank
  })
  const window = ranked.slice(0, Math.min(PICK_WINDOW, ranked.length))
  const gridId = window[seedFromDate(date) % window.length]
  lastUsed.set(gridId, offset)
  generated.push({ date, gridId, theme: null, difficulty: 'normal' })
}

// Contrôles de la répartition produite.
const all = [...preserved, ...generated]
const gaps = new Map()
let minimumGap = Number.POSITIVE_INFINITY
for (const [index, entry] of all.entries()) {
  const previous = gaps.get(entry.gridId)
  if (previous !== undefined) minimumGap = Math.min(minimumGap, index - previous)
  gaps.set(entry.gridId, index)
}
const consecutive = all.filter((entry, index) => index > 0 && all[index - 1].gridId === entry.gridId)
if (consecutive.length) {
  console.error(`\n✖ Répétition deux jours de suite : ${consecutive.map(entry => entry.date).join(', ')}\n`)
  process.exit(1)
}

const payload = {
  schema: existing.schema ?? 'motman-daily-theme-schedule',
  version: existing.version ?? 1,
  timezone: 'Europe/Paris',
  _comment: `Calendrier générique généré par scripts/build_daily_calendar.mjs (grilles jouables du catalogue v${catalog.version}). `
    + 'AUCUN thème n\'est annoncé (theme:null) : les grilles publiées sont génériques, et l\'UI n\'affiche un libellé de thème '
    + 'que si le champ est renseigné. À remplacer par le calendrier éditorialisé quand de vraies grilles à thème existeront (contrat 3). '
    + 'Le repli générique couvre les dates non listées.',
  days: all,
}

if (check) {
  console.log(`• Plan : ${all.length} jour(s) (${all[0]?.date} → ${all.at(-1)?.date}), ${playableIds.length} grilles jouables, écart minimal ${minimumGap} jour(s). Rien écrit (--check).`)
  process.exit(0)
}

fs.writeFileSync(CALENDAR, `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
console.log(`✓ Calendrier écrit : ${all.length} jour(s) (${all[0]?.date} → ${all.at(-1)?.date}), ${playableIds.length} grilles jouables, écart minimal ${minimumGap} jour(s).`)
