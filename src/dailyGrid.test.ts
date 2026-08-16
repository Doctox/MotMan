import { describe, expect, it, vi } from 'vitest'
import type { GeneratedGrid, GridDifficulty } from './generator'
import { calendarEntryFor, resolveDailyGrid, seedFromDate, type DailyCalendarDay } from './dailyGrid'

function fakeGrid(id: string): GeneratedGrid {
  return {
    id, columns: 7, rows: 8, difficulty: 'normal',
    cells: [], words: [], seed: 0, version: 'test',
    validation: { valid: true, errors: [], score: 100 },
  } as unknown as GeneratedGrid
}

const CALENDAR: DailyCalendarDay[] = [
  { date: '2026-09-01', gridId: 'animaux-7x8-abc123', theme: 'Animaux', difficulty: 'hard' },
]

describe('seedFromDate', () => {
  it('est déterministe et varie selon la date', () => {
    expect(seedFromDate('2026-09-01')).toBe(seedFromDate('2026-09-01'))
    expect(seedFromDate('2026-09-01')).not.toBe(seedFromDate('2026-09-02'))
  })
})

describe('calendarEntryFor', () => {
  it('retourne l’entrée du jour ou null', () => {
    expect(calendarEntryFor('2026-09-01', CALENDAR)?.gridId).toBe('animaux-7x8-abc123')
    expect(calendarEntryFor('2026-09-02', CALENDAR)).toBeNull()
  })
})

describe('resolveDailyGrid', () => {
  it('sert la grille du calendrier (source=calendar) avec thème et difficulté', async () => {
    const byId = vi.fn(async (gridId: string) => fakeGrid(gridId))
    const generic = vi.fn(async () => fakeGrid('generic'))
    const result = await resolveDailyGrid('2026-09-01', {
      entryFor: key => calendarEntryFor(key, CALENDAR),
      byId,
      generic,
    })
    expect(result.source).toBe('calendar')
    expect(result.gridId).toBe('animaux-7x8-abc123')
    expect(result.theme).toBe('Animaux')
    expect(result.difficulty).toBe('hard')
    expect(byId).toHaveBeenCalledWith('animaux-7x8-abc123', 'hard')
    expect(generic).not.toHaveBeenCalled()
  })

  it('bascule en fallback déterministe quand aucune entrée (sans thème)', async () => {
    const generic = vi.fn(async (seed: number) => fakeGrid(`generic-${seed}`))
    const result = await resolveDailyGrid('2026-09-02', {
      entryFor: key => calendarEntryFor(key, CALENDAR),
      byId: async () => { throw new Error('ne doit pas être appelé') },
      generic,
    })
    expect(result.source).toBe('fallback')
    expect(result.theme).toBeNull()
    expect(generic).toHaveBeenCalledWith(seedFromDate('2026-09-02'), 'normal')
  })

  it('bascule en fallback (et loggue) si la grille du calendrier est introuvable/injouable', async () => {
    const incidents: string[] = []
    const result = await resolveDailyGrid('2026-09-01', {
      entryFor: key => calendarEntryFor(key, CALENDAR),
      byId: async () => { throw new Error('La grille animaux-7x8-abc123 est introuvable') },
      generic: async (seed: number) => fakeGrid(`generic-${seed}`),
      onIncident: (_date, gridId) => incidents.push(gridId),
    })
    expect(result.source).toBe('fallback')
    expect(result.theme).toBeNull()
    expect(incidents).toContain('animaux-7x8-abc123')
  })
})
