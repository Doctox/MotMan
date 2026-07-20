import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadMatch, playMatchTurn, type MatchState, type MatchTurn } from './matches'

const remote = vi.hoisted(() => ({
  invoke: vi.fn(),
  hasSession: vi.fn().mockResolvedValue(true),
}))

vi.mock('./supabaseClient', () => ({ hasSupabaseSession: remote.hasSession }))
vi.mock('./supabaseFunctions', () => ({ invokeSupabaseFunction: remote.invoke }))

describe('synchronisation légère des parties', () => {
  afterEach(() => remote.invoke.mockReset())

  it('retourne null quand le serveur annonce un état inchangé', async () => {
    remote.invoke.mockResolvedValue({ unchanged: true })

    await expect(loadMatch('guest_1234567890abcdef', 'match-1', '2026-07-17T10:00:00.000Z')).resolves.toBeNull()
    expect(remote.invoke).toHaveBeenCalledWith('match-api', {
      action: 'match', matchId: 'match-1', knownUpdatedAt: '2026-07-17T10:00:00.000Z',
    })
  })

  it('retourne le nouvel état quand la partie a changé', async () => {
    const state = { id: 'match-1', updatedAt: '2026-07-17T10:00:01.000Z' } as MatchState
    remote.invoke.mockResolvedValue({ match: state })

    await expect(loadMatch('guest_1234567890abcdef', 'match-1', '2026-07-17T10:00:00.000Z')).resolves.toBe(state)
  })

  it('envoie la version affichée avec une action de jeu', async () => {
    const state = { id: 'match-1', updatedAt: '2026-07-20T12:00:01.000Z' } as MatchState
    const result = { id: 'turn-1' } as MatchTurn
    remote.invoke.mockResolvedValue({ match: state, result })

    await playMatchTurn('guest_1234567890abcdef', 'match-1', 4, [{ cellIndex: 12, letter: 'A' }], false, '2026-07-20T12:00:00.000Z')

    expect(remote.invoke).toHaveBeenCalledWith('match-api', {
      action: 'turn', matchId: 'match-1', turnNumber: 4,
      placements: [{ cellIndex: 12, letter: 'A' }], automatic: false,
      knownUpdatedAt: '2026-07-20T12:00:00.000Z',
    })
  })
})
