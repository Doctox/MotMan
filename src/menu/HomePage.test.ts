import { afterEach, describe, expect, it, vi } from 'vitest'
import type { MatchState } from '../matches'
import { asyncTimeLeft } from './HomePage'

function matchEndingAt(turnEndsAt: string): MatchState {
  return { turnEndsAt } as MatchState
}

describe('échéance des parties illimitées sur l’accueil', () => {
  afterEach(() => vi.useRealTimers())

  it('affiche les minutes sous une heure', () => {
    vi.useFakeTimers()
    vi.setSystemTime('2026-07-27T10:00:00.000Z')
    expect(asyncTimeLeft(matchEndingAt('2026-07-27T10:42:00.000Z'))).toBe('42 min')
  })

  it('arrondit les heures restantes au-dessus d’une heure', () => {
    vi.useFakeTimers()
    vi.setSystemTime('2026-07-27T10:00:00.000Z')
    expect(asyncTimeLeft(matchEndingAt('2026-07-27T11:20:00.000Z'))).toBe('2 h')
  })
})
