import type { BotSkill } from '../../src/botOpponents'
import type { GridDimensionsSource } from '../../src/gridDimensions'

export type CatalogWord = {
  wordId?: string
  answer: string
  clue?: string
  image?: unknown
  direction: 'across' | 'down'
  arrow?: string
  clueCell: number[]
  cells: number[][]
}

export type CatalogGrid = GridDimensionsSource & {
  id: string
  clueCells?: number[][]
  words: CatalogWord[]
}

export type MatchPace = 'realtime' | 'async'
export type MatchMode = 'friend' | 'normal'

export type MatchInvitation = {
  id: string
  hostId: string
  guestId: string
  pace: MatchPace
  createdAt: string
  expiresAt: string
  status: 'pending' | 'accepted' | 'declined' | 'cancelled' | 'expired'
  matchId?: string
}

export type MatchSearch = {
  id: string
  playerId: string
  pace: MatchPace
  createdAt: string
  updatedAt: string
}

export type BotProfile = {
  playerId: string
  displayName: string
  level: number
  skill: BotSkill
  avatarId: string
  frameId: string
}

export type StoredTurn = {
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

export type StoredMatch = {
  id: string
  invitationId: string | null
  mode: MatchMode
  pace: MatchPace
  gridId: string
  difficulty: 'easy' | 'normal' | 'hard'
  playerIds: [string, string]
  bot: BotProfile | null
  currentPlayerId: string
  turnNumber: number
  turnStartedAt: string
  turnEndsAt: string
  board: Record<string, { letter: string; playerId: string }>
  racks: Record<string, string[]>
  letterBag?: string[]
  scores: Record<string, number>
  productiveTurns: Record<string, number>
  inactivity: Record<string, number>
  hint: { playerId: string; cellIndex: number; letter: string; turnNumber: number } | null
  hintUsed: Record<string, boolean | number>
  rerollUsed: Record<string, boolean | number>
  lastTurn: StoredTurn | null
  status: 'active' | 'finished'
  winnerId: string | null
  finishReason: 'completed' | 'timeout' | 'forfeit' | null
  createdAt: string
  updatedAt: string
}

export type MatchDatabase = {
  version: 5
  invitations: MatchInvitation[]
  matches: StoredMatch[]
  searches: MatchSearch[]
}
