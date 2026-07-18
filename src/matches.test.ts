import { afterEach, describe, expect, it, vi } from 'vitest'
import { loadMatch, type MatchState } from './matches'

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
})
