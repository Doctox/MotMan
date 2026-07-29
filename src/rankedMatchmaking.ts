import { hasSupabaseSession } from './supabaseClient'
import { invokeSupabaseFunction } from './supabaseFunctions'
import type { SocialUser } from './social'

export type RankedProgressSnapshot = {
  points: number
  matches: number
  placements: number
  wins: number
  losses: number
  draws: number
}

export type RankedReadyCheck = {
  id: string
  matchId: string
  opponent: SocialUser | null
  expiresAt: string
  acceptedByMe: boolean
  acceptedByOpponent: boolean
  pausedMatchId: string | null
}

export type RankedMatchmakingState = {
  status: 'idle' | 'searching' | 'ready' | 'accepted' | 'started'
  queuedAt: string | null
  matchId: string | null
  ready: RankedReadyCheck | null
  progress: RankedProgressSnapshot
}

export type RankedLeaderboardEntry = {
  position: number
  user: SocialUser
  points: number
  matches: number
  wins: number
}

export type RankedLeaderboard = {
  general: RankedLeaderboardEntry[]
  friends: RankedLeaderboardEntry[]
}

export const EMPTY_RANKED_MATCHMAKING: RankedMatchmakingState = {
  status: 'idle',
  queuedAt: null,
  matchId: null,
  ready: null,
  progress: { points: 0, matches: 0, placements: 0, wins: 0, losses: 0, draws: 0 },
}

async function rankedAction(
  action: 'ranked-state' | 'ranked-search' | 'ranked-cancel' | 'ranked-ready-response',
  body: Record<string, unknown> = {},
): Promise<RankedMatchmakingState> {
  if (!await hasSupabaseSession()) throw new Error('Votre session MotMan a expiré. Reconnectez-vous.')
  return invokeSupabaseFunction<RankedMatchmakingState>('match-api', { action, ...body })
}

export function loadRankedMatchmaking(): Promise<RankedMatchmakingState> {
  return rankedAction('ranked-state')
}

export function startRankedSearch(): Promise<RankedMatchmakingState> {
  return rankedAction('ranked-search')
}

export function cancelRankedSearch(): Promise<RankedMatchmakingState> {
  return rankedAction('ranked-cancel')
}

export function respondToRankedReady(
  readySessionId: string,
  decision: 'accept' | 'decline',
): Promise<RankedMatchmakingState> {
  return rankedAction('ranked-ready-response', { readySessionId, decision })
}

export async function loadRankedLeaderboard(): Promise<RankedLeaderboard> {
  if (!await hasSupabaseSession()) return { general: [], friends: [] }
  return invokeSupabaseFunction<RankedLeaderboard>('match-api', { action: 'ranked-leaderboard' })
}
