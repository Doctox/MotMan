import { describe, expect, it } from 'vitest'
import type { MatchState } from './matches'
import { matchPollDelay } from './matchSyncPolicy'

function match(overrides: Partial<MatchState> = {}): MatchState {
  return {
    id: 'match-1', invitationId: null, mode: 'friend', pace: 'realtime', gridId: 'grid-1', difficulty: 'normal',
    playerIds: ['player', 'opponent'], bot: null, players: [], currentPlayerId: 'opponent', turnNumber: 2,
    turnStartedAt: new Date(1_000).toISOString(), turnEndsAt: new Date(46_000).toISOString(), board: {}, racks: {},
    scores: {}, productiveTurns: {}, inactivity: {}, hint: null, hintUsed: {}, rerollUsed: {}, lastTurn: null,
    status: 'active', winnerId: null, finishReason: null, createdAt: new Date(0).toISOString(), updatedAt: new Date(1_000).toISOString(),
    ...overrides,
  }
}

describe('matchPollDelay', () => {
  it('suspend complètement le polling lorsque la partie est masquée', () => {
    expect(matchPollDelay({ match: match(), playerId: 'player', visibility: 'hidden', realtimeConnected: true, unchangedPolls: 0, failureCount: 0, now: 2_000 })).toBe(-1)
  })

  it('utilise Realtime avec un filet de sécurité lent', () => {
    expect(matchPollDelay({ match: match(), playerId: 'player', visibility: 'visible', realtimeConnected: true, unchangedPolls: 0, failureCount: 0, now: 2_000 })).toBe(8_000)
  })

  it('reste plus réactif sans websocket et pendant la réflexion du bot', () => {
    expect(matchPollDelay({ match: match(), playerId: 'player', visibility: 'visible', realtimeConnected: false, unchangedPolls: 0, failureCount: 0, now: 2_000 })).toBe(2_000)
    const botMatch = match({ bot: { playerId: 'opponent', displayName: 'Camille', level: 4, skill: 'regular', avatarId: 'plume', frameId: 'cadre-ivoire' } })
    expect(matchPollDelay({ match: botMatch, playerId: 'player', visibility: 'visible', realtimeConnected: true, unchangedPolls: 0, failureCount: 0, now: 2_000 })).toBe(1_250)
  })

  it('se réveille près de la fin du tour et ralentit après des erreurs', () => {
    expect(matchPollDelay({ match: match(), playerId: 'player', visibility: 'visible', realtimeConnected: true, unchangedPolls: 0, failureCount: 0, now: 45_900 })).toBe(350)
    expect(matchPollDelay({ match: match(), playerId: 'player', visibility: 'visible', realtimeConnected: true, unchangedPolls: 0, failureCount: 3, now: 2_000 })).toBe(10_000)
  })
})
