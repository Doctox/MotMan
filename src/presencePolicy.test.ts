import { describe, expect, it } from 'vitest'
import {
  isPresenceOnline,
  PRESENCE_HEARTBEAT_HIDDEN_MS,
  PRESENCE_HEARTBEAT_VISIBLE_MS,
  PRESENCE_ONLINE_TTL_MS,
  presenceHeartbeatDelay,
} from './presencePolicy'

describe('presence heartbeat policy', () => {
  it('utilise un heartbeat léger et moins fréquent quand l’application est cachée', () => {
    expect(presenceHeartbeatDelay('visible')).toBe(PRESENCE_HEARTBEAT_VISIBLE_MS)
    expect(presenceHeartbeatDelay('hidden')).toBe(PRESENCE_HEARTBEAT_HIDDEN_MS)
    expect(PRESENCE_HEARTBEAT_VISIBLE_MS).toBe(25_000)
    expect(PRESENCE_HEARTBEAT_HIDDEN_MS).toBe(60_000)
  })

  it('garde une marge entre le heartbeat caché et le passage hors ligne', () => {
    expect(PRESENCE_ONLINE_TTL_MS).toBeGreaterThan(PRESENCE_HEARTBEAT_HIDDEN_MS)
    expect(PRESENCE_ONLINE_TTL_MS - PRESENCE_HEARTBEAT_HIDDEN_MS).toBeGreaterThanOrEqual(15_000)
  })

  it('classe correctement une présence récente, expirée ou invalide', () => {
    const now = Date.parse('2026-07-29T12:00:00.000Z')
    expect(isPresenceOnline('2026-07-29T11:58:46.000Z', now)).toBe(true)
    expect(isPresenceOnline('2026-07-29T11:58:45.000Z', now)).toBe(false)
    expect(isPresenceOnline('invalide', now)).toBe(false)
  })
})
