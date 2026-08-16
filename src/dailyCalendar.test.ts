import { describe, expect, it } from 'vitest'
import calendarData from './data/runtime.daily.calendar.json'
import { calendarEntryFor, seedFromDate, type DailyCalendarDay } from './dailyCalendar'

// Le calendrier réel est un livrable : il doit rester lisible ET honnête.
// Ces contrôles protègent trois régressions déjà rencontrées :
//  - des thèmes annoncés que les grilles n'ont pas ;
//  - la même grille deux jours de suite ;
//  - des trous de date qui renvoient silencieusement au repli générique.
const days = (calendarData as { days: DailyCalendarDay[] }).days

function dayNumber(key: string): number {
  const [year, month, day] = key.split('-').map(Number)
  return Math.floor(Date.UTC(year, month - 1, day) / 86_400_000)
}

describe('calendrier du défi du jour (fichier réel)', () => {
  it('n’annonce aucun thème tant que les grilles publiées sont génériques', () => {
    expect(days.filter(day => day.theme !== null)).toEqual([])
  })

  it('couvre des jours consécutifs, sans trou ni doublon', () => {
    const numbers = days.map(day => dayNumber(day.date))
    expect(new Set(numbers).size).toBe(numbers.length)
    for (let index = 1; index < numbers.length; index += 1) {
      expect(numbers[index] - numbers[index - 1]).toBe(1)
    }
  })

  it('ne rejoue jamais la même grille deux jours de suite', () => {
    const repeated = days.filter((day, index) => index > 0 && days[index - 1].gridId === day.gridId)
    expect(repeated.map(day => day.date)).toEqual([])
  })

  it('espace largement les répétitions d’une même grille', () => {
    const lastSeen = new Map<string, number>()
    let minimumGap = Number.POSITIVE_INFINITY
    days.forEach((day, index) => {
      const previous = lastSeen.get(day.gridId)
      if (previous !== undefined) minimumGap = Math.min(minimumGap, index - previous)
      lastSeen.set(day.gridId, index)
    })
    expect(minimumGap).toBeGreaterThanOrEqual(30)
  })

  it('programme au moins six mois de défis', () => {
    expect(days.length).toBeGreaterThanOrEqual(180)
  })
})

describe('lecture du calendrier', () => {
  it('retrouve l’entrée d’un jour couvert et rend null ailleurs', () => {
    const first = days[0]
    expect(calendarEntryFor(first.date)?.gridId).toBe(first.gridId)
    expect(calendarEntryFor('1999-01-01')).toBeNull()
  })

  it('dérive une graine stable par date', () => {
    expect(seedFromDate('2026-08-16')).toBe(seedFromDate('2026-08-16'))
    expect(seedFromDate('2026-08-16')).not.toBe(seedFromDate('2026-08-17'))
  })
})
