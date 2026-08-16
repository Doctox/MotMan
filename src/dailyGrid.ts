import { calendarEntryFor, seedFromDate, type DailyCalendarDay } from './dailyCalendar'
import type { GeneratedGrid, GridDifficulty } from './generator'

// Résolution de la grille du jour (contrat 3) + fallback robuste.
// La lecture légère du calendrier vit dans dailyCalendar.ts ; ce module y ajoute
// la matérialisation via generator.ts.
//
// ⚠️ IMPORT DE TYPE UNIQUEMENT sur ./generator, et chargement DIFFÉRÉ des
// fonctions. generator.ts tire `data/runtime.grid.catalog.json` (320 Ko, AVEC les
// solutions de toutes les grilles) : un import en valeur suffirait à l'embarquer
// dans le bundle client dès qu'un composant importerait ce module, et ferait
// échouer `npm run audit:security` (scripts/check_production_secrets.mjs).
// Le catalogue reste donc derrière un `await import(...)`, exactement comme dans
// generator.ts lui-même.

export type { DailyCalendarDay } from './dailyCalendar'
export { calendarEntryFor, seedFromDate } from './dailyCalendar'

export type DailyGridSource = 'calendar' | 'fallback'

export type DailyGrid = {
  grid: GeneratedGrid
  gridId: string
  theme: string | null
  difficulty: GridDifficulty
  source: DailyGridSource
}

type ResolveDeps = {
  entryFor?: (dateKey: string) => DailyCalendarDay | null
  byId?: (gridId: string, difficulty: GridDifficulty) => Promise<GeneratedGrid>
  generic?: (seed: number, difficulty: GridDifficulty) => Promise<GeneratedGrid>
  onIncident?: (dateKey: string, gridId: string, reason: unknown) => void
}

/**
 * Résout la grille du jour pour `dateKey`.
 *  - Entrée de calendrier + grille existante/jouable → source `calendar`, thème affiché.
 *  - Sinon (pas d'entrée, ou gridId introuvable/injouable) → DÉGRADATION
 *    SILENCIEUSE en sélection déterministe par date sur le catalogue générique,
 *    sans thème, incident loggé. Le joueur a TOUJOURS une grille.
 *
 * `deps` est injectable pour tester les deux branches sans charger le catalogue.
 */
export async function resolveDailyGrid(dateKey: string, deps: ResolveDeps = {}): Promise<DailyGrid> {
  const entryFor = deps.entryFor ?? ((key: string) => calendarEntryFor(key))
  const byId = deps.byId ?? (async (gridId: string, level: GridDifficulty) => (await import('./generator')).generateGridById(gridId, level))
  const generic = deps.generic ?? (async (seed: number, level: GridDifficulty) => (await import('./generator')).generateGrid(seed, level))
  const onIncident = deps.onIncident ?? defaultIncidentLog

  const entry = entryFor(dateKey)
  const difficulty: GridDifficulty = entry?.difficulty ?? 'normal'

  if (entry) {
    try {
      const grid = await byId(entry.gridId, difficulty)
      return { grid, gridId: entry.gridId, theme: entry.theme ?? null, difficulty, source: 'calendar' }
    } catch (reason) {
      onIncident(dateKey, entry.gridId, reason)
    }
  }

  const grid = await generic(seedFromDate(dateKey), difficulty)
  return { grid, gridId: grid.id, theme: null, difficulty, source: 'fallback' }
}

function defaultIncidentLog(dateKey: string, gridId: string, reason: unknown): void {
  const message = reason instanceof Error ? reason.message : String(reason)
  // Incident volontairement non bloquant : le fallback prend le relais.
  console.warn(`[MotMan] Défi du jour ${dateKey} : grille « ${gridId} » indisponible (${message}). Repli sur le catalogue générique.`)
}
