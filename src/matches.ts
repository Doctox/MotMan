import type { SocialUser } from './social'
import type { GeneratedGrid } from './generator'
import { hasSupabaseSession } from './supabaseClient'
import { invokeSupabaseFunction } from './supabaseFunctions'
import type { MatchHistoryOutcome } from './matchHistory'

export type MatchPace = 'realtime' | 'async'
export type MatchMode = 'solo' | 'friend' | 'normal'
export type MatchSearch = { id: string; pace: MatchPace; createdAt: string }
export type MatchHistoryEntry = {
  id: string
  mode: 'solo' | 'multiplayer'
  pace: MatchPace
  outcome: MatchHistoryOutcome
  score: number
  opponentScore: number
  opponentName: string | null
  completedAt: string
}
export type MatchBot = { playerId: string; displayName: string; level: number; skill: 'beginner' | 'regular' | 'expert'; avatarId: string; frameId: string }

export type MatchInvitation = {
  id: string
  hostId: string
  guestId: string
  pace: MatchPace
  createdAt: string
  expiresAt: string
  status: 'pending' | 'accepted' | 'declined' | 'cancelled' | 'expired'
  matchId?: string
  host: SocialUser | null
  guest: SocialUser | null
}

export type MatchTurn = {
  id: string
  kind: 'played' | 'timeout'
  playerId: string
  turnNumber: number
  correct: number[]
  wrong: number[]
  wrongPlacements: Array<{ cellIndex: number; letter: string }>
  aidedCell: number | null
  letterPoints: number
  wordBonuses: Array<{ cells: number[]; points: number; direction: 'across' | 'down' }>
  rackBonus: number
  scoreGained: number
  inactivityCount: number
  createdAt: string
}

export type MatchState = {
  id: string
  invitationId: string | null
  mode: MatchMode
  pace: MatchPace
  gridId: string
  difficulty: 'easy' | 'normal' | 'hard'
  playerIds: [string, string]
  bot: MatchBot | null
  players: SocialUser[]
  currentPlayerId: string
  turnNumber: number
  turnStartedAt: string
  turnEndsAt: string
  board: Record<string, { letter: string; playerId: string }>
  racks: Record<string, string[]>
  scores: Record<string, number>
  productiveTurns: Record<string, number>
  inactivity: Record<string, number>
  hint: { playerId: string; cellIndex: number; letter: string; turnNumber: number } | null
  hintUsed: Record<string, boolean | number>
  rerollUsed: Record<string, boolean | number>
  lastTurn: MatchTurn | null
  status: 'active' | 'finished'
  winnerId: string | null
  finishReason: 'completed' | 'timeout' | 'forfeit' | null
  createdAt: string
  updatedAt: string
  grid?: GeneratedGrid
}

export type MatchLobbyState = { incoming: MatchInvitation[]; outgoing: MatchInvitation[]; active: MatchState[]; searches: MatchSearch[]; recent: MatchHistoryEntry[] }
export const EMPTY_MATCH_LOBBY: MatchLobbyState = { incoming: [], outgoing: [], active: [], searches: [], recent: [] }
const localTestServer = import.meta.env.VITE_MOTMAN_LOCAL_TEST_SERVER === 'true'

async function localMatch<T>(path: string, body?: Record<string, unknown>): Promise<T> {
  const response = await fetch(`/api/matches/${path}`, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  } : undefined)
  const payload = response.status === 204 ? null : await response.json()
  if (!response.ok) throw Object.assign(new Error(payload?.error ?? 'Serveur de test indisponible.'), { payload })
  return payload as T
}

async function supabaseMatch<T>(action: string, body: Record<string, unknown> = {}): Promise<T> {
  if (!await hasSupabaseSession()) throw new Error('Votre session MotMan a expiré. Reconnectez-vous.')
  return invokeSupabaseFunction<T>('match-api', { action, ...body })
}

export async function loadMatchLobby(playerId: string): Promise<MatchLobbyState> {
  if (localTestServer) return localMatch(`state?playerId=${encodeURIComponent(playerId)}`)
  void playerId
  return supabaseMatch<MatchLobbyState>('state')
}

export async function createInstantMatch(playerId: string, targetId: string, pace: MatchPace): Promise<MatchLobbyState> {
  if (localTestServer) return localMatch('create', { playerId, targetId, pace })
  void playerId
  return supabaseMatch<MatchLobbyState>('create', { targetId, pace })
}

export async function respondToMatchInvitation(playerId: string, invitationId: string, decision: 'accept' | 'decline'): Promise<MatchLobbyState> {
  if (localTestServer) return localMatch('respond', { playerId, invitationId, decision })
  void playerId
  return supabaseMatch<MatchLobbyState>('respond', { invitationId, decision })
}

export async function cancelMatchInvitation(playerId: string, invitationId: string): Promise<MatchLobbyState> {
  if (localTestServer) return localMatch('cancel', { playerId, invitationId })
  void playerId
  return supabaseMatch<MatchLobbyState>('cancel', { invitationId })
}

export async function searchNormalMatch(playerId: string, pace: MatchPace): Promise<{ lobby: MatchLobbyState; matchId: string | null }> {
  if (localTestServer) return localMatch('search', { playerId, pace })
  void playerId
  return supabaseMatch<{ lobby: MatchLobbyState; matchId: string | null }>('search', { pace })
}

export async function cancelNormalSearch(playerId: string, pace: MatchPace): Promise<MatchLobbyState> {
  if (localTestServer) return localMatch('search/cancel', { playerId, pace })
  void playerId
  return (await supabaseMatch<{ lobby: MatchLobbyState }>('search-cancel', { pace })).lobby
}

export async function createSoloMatch(difficulty: 'easy' | 'normal' | 'hard', pace: MatchPace): Promise<MatchState> {
  return (await supabaseMatch<{ match: MatchState }>('solo', { difficulty, pace })).match
}

export async function loadMatch(playerId: string, matchId: string, knownUpdatedAt?: string): Promise<MatchState | null> {
  if (localTestServer) {
    const query = new URLSearchParams({ playerId, ...(knownUpdatedAt ? { since: knownUpdatedAt } : {}) })
    return localMatch(`match/${encodeURIComponent(matchId)}?${query}`)
  }
  void playerId
  const remote = await supabaseMatch<{ match?: MatchState; unchanged?: boolean }>('match', { matchId, knownUpdatedAt })
  return remote.unchanged ? null : remote.match ?? null
}

export async function playMatchTurn(playerId: string, matchId: string, turnNumber: number, placements: Array<{ cellIndex: number; letter: string }>, automatic = false, knownUpdatedAt?: string): Promise<{ match: MatchState; result: MatchTurn }> {
  if (localTestServer) return localMatch('turn', { playerId, matchId, turnNumber, placements, automatic, knownUpdatedAt })
  void playerId
  return supabaseMatch<{ match: MatchState; result: MatchTurn }>('turn', { matchId, turnNumber, placements, automatic, knownUpdatedAt })
}

export async function requestMatchHint(playerId: string, matchId: string, knownUpdatedAt?: string): Promise<MatchState> {
  if (localTestServer) return localMatch('hint', { playerId, matchId, knownUpdatedAt })
  void playerId
  return (await supabaseMatch<{ match: MatchState }>('hint', { matchId, knownUpdatedAt })).match
}

export async function rerollMatchRack(playerId: string, matchId: string, knownUpdatedAt?: string): Promise<MatchState> {
  if (localTestServer) return localMatch('reroll', { playerId, matchId, knownUpdatedAt })
  void playerId
  return (await supabaseMatch<{ match: MatchState }>('reroll', { matchId, knownUpdatedAt })).match
}

export async function forfeitMatch(playerId: string, matchId: string, knownUpdatedAt?: string): Promise<MatchState> {
  if (localTestServer) return localMatch('forfeit', { playerId, matchId, knownUpdatedAt })
  void playerId
  return (await supabaseMatch<{ match: MatchState }>('forfeit', { matchId, knownUpdatedAt })).match
}

export async function submitMatchGridFeedback(playerId: string, matchId: string, quality: 'yes' | 'no', reason?: string): Promise<void> {
  if (localTestServer) {
    // The local priority-zero server deliberately has no persistent content
    // telemetry; keeping the UI responsive is enough in that isolated mode.
    void playerId
    return
  }
  void playerId
  await supabaseMatch<{ recorded: true }>('feedback', { matchId, quality, reason })
}
