import { describe, expect, it } from 'vitest'
import { matchHistoryDateLabel, matchHistoryResultLabel, matchHistoryTone } from './matchHistory'

describe('présentation de l’historique des matchs', () => {
  it('classe les résultats interrompus du bon côté', () => {
    expect(matchHistoryTone('opponent-abandoned')).toBe('won')
    expect(matchHistoryResultLabel('opponent-abandoned')).toBe('Victoire')
    expect(matchHistoryTone('abandon')).toBe('lost')
    expect(matchHistoryResultLabel('abandon')).toBe('Défaite')
  })

  it('présente une ancienneté courte et lisible', () => {
    const now = new Date('2026-07-19T20:00:00.000Z').getTime()
    expect(matchHistoryDateLabel('2026-07-19T19:42:00.000Z', now)).toBe('Il y a 18 min')
    expect(matchHistoryDateLabel('2026-07-18T20:00:00.000Z', now)).toBe('Hier')
  })
})
