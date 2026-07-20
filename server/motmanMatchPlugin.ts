import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import type { IncomingMessage, ServerResponse } from 'node:http'
import type { Plugin } from 'vite'
import { botThinkingDelayMs, createBotPersona, planBotMove } from '../src/botOpponents'
import {
  canUseHint,
  canUseReroll,
  drawRackFromBag,
  evaluateTurn,
  hasTurnStarted,
  hintCandidates,
  isTurnSubmissionExpired,
  keepRackLettersAfterTurn,
  prepareFinalSprintRacks,
  RACK_SIZE,
  shouldForfeitAfterInactivity,
} from '../src/gameRules'
import { database as accountDatabase, type DatabaseUser } from './motmanDatabase'
import {
  ASYNC_BOT_MATCH_DELAY_MS,
  ASYNC_SEARCH_DURATION_MS,
  ASYNC_TURN_DURATION_MS,
  MATCH_DATABASE_PATH,
  MAX_ASYNC_MATCHES,
  MIN_REVEAL_DURATION_MS,
  REALTIME_BOT_MATCH_DELAY_MS,
  REALTIME_SEARCH_STALE_MS,
  REALTIME_TURN_DURATION_MS,
  RECENT_GRID_HISTORY_LIMIT,
  REVEAL_STEP_MS,
  TURN_READY_DURATION_MS,
  TURN_SUBMIT_GRACE_MS,
} from './match/config'
import { gridById, gridIds, gridSolution, grids, hash, publicGrid, ruleGrid, wordIndexes } from './match/gridCatalog'
import { sendJson } from './match/http'
import { handleMatchRequest } from './match/requestHandler'
import type { BotProfile, CatalogGrid, MatchDatabase, MatchInvitation, MatchMode, MatchPace, StoredMatch, StoredTurn } from './match/types'

const EMPTY_DATABASE: MatchDatabase = { version: 5, invitations: [], matches: [], searches: [] }

function loadMatchDatabase(): MatchDatabase {
  try {
    if (!existsSync(MATCH_DATABASE_PATH)) return structuredClone(EMPTY_DATABASE)
    const parsed = JSON.parse(readFileSync(MATCH_DATABASE_PATH, 'utf8')) as Partial<MatchDatabase> & { version?: number }
    if (![1, 2, 3, 4, 5].includes(parsed.version ?? 0) || !Array.isArray(parsed.invitations) || !Array.isArray(parsed.matches)) return structuredClone(EMPTY_DATABASE)
    const loaded: MatchDatabase = {
      version: 5,
      invitations: parsed.invitations,
      matches: parsed.matches.filter(match => gridIds.has(match.gridId)),
      searches: Array.isArray(parsed.searches) ? parsed.searches : [],
    }
    loaded.searches.forEach(search => { search.updatedAt ??= search.createdAt })
    loaded.invitations.forEach(invitation => { invitation.pace ??= 'realtime' })
    loaded.matches.forEach(match => {
      match.invitationId ??= null
      match.mode ??= match.invitationId ? 'friend' : 'normal'
      match.pace ??= 'realtime'
      match.bot ??= null
      if (match.bot) {
        const fallbackPersona = createBotPersona(match.bot.playerId, match.bot.skill)
        match.bot.avatarId ??= fallbackPersona.avatarId
        match.bot.frameId ??= fallbackPersona.frameId
      }
      match.inactivity ??= Object.fromEntries(match.playerIds.map(playerId => [playerId, 0]))
      match.productiveTurns ??= Object.fromEntries(match.playerIds.map(playerId => [playerId, 0]))
      match.racks ??= {}
      match.hintUsed ??= {}
      match.rerollUsed ??= {}
      if (match.lastTurn) {
        match.lastTurn.kind ??= 'played'
        match.lastTurn.inactivityCount ??= 0
        match.lastTurn.wrongPlacements ??= []
      }
      ensureSharedLetterBag(match)
    })
    return loaded
  } catch {
    return structuredClone(EMPTY_DATABASE)
  }
}

let database = loadMatchDatabase()

function saveDatabase(): void {
  writeFileSync(MATCH_DATABASE_PATH, `${JSON.stringify(database, null, 2)}\n`, 'utf8')
}

function cleanPlayerId(value: unknown): string {
  return typeof value === 'string' && /^guest_[0-9a-f-]{16,}$/i.test(value) ? value : ''
}

function publicUser(playerId: string) {
  const user = accountDatabase.prepare('SELECT * FROM users WHERE id = ?').get(playerId) as DatabaseUser | undefined
  return user ? {
    playerId: user.id,
    displayName: user.display_name,
    code: user.friend_code,
    online: Date.now() - new Date(user.last_seen).getTime() < 30_000,
    avatarId: user.equipped_avatar_id,
    frameId: user.equipped_frame_id,
    animationId: user.equipped_animation_id,
  } : null
}

function botUser(bot: BotProfile) {
  return { playerId: bot.playerId, displayName: bot.displayName, code: `BOT${String(bot.level).padStart(2, '0')}`, online: true, activity: 'playing' as const, avatarId: bot.avatarId, frameId: bot.frameId }
}

function areFriends(left: string, right: string): boolean {
  const [first, second] = left < right ? [left, right] : [right, left]
  return Boolean(accountDatabase.prepare('SELECT 1 FROM friendships WHERE left_user_id = ? AND right_user_id = ?').get(first, second))
}

function gridForMatch(match: StoredMatch): CatalogGrid {
  return gridById(match.gridId)
}

function ensureSharedLetterBag(match: StoredMatch): void {
  if (Array.isArray(match.letterBag)) return
  const solution = gridSolution(gridForMatch(match))
  const available = [...solution.entries()].flatMap(([index, letter]) => match.board[index] ? [] : [letter])
  const normalizedRacks: Record<string, string[]> = { ...match.racks }

  for (const playerId of match.playerIds) {
    normalizedRacks[playerId] = (match.racks[playerId] ?? []).filter(letter => {
      const index = available.indexOf(letter)
      if (index < 0) return false
      available.splice(index, 1)
      return true
    })
  }

  match.racks = normalizedRacks
  match.letterBag = available
  for (const playerId of match.playerIds) match.racks[playerId] = replenishRack(match, playerId, match.racks[playerId] ?? [])
}

function ensureFinalSprintRacks(match: StoredMatch): boolean {
  if (match.status !== 'active') return false
  const remainingLetters = [...gridSolution(gridForMatch(match)).entries()]
    .flatMap(([index, letter]) => match.board[index] ? [] : [letter])
  const finale = prepareFinalSprintRacks({
    remainingLetters,
    playerIds: match.playerIds,
    racks: match.racks,
  })
  if (!finale.active) return false
  const bagChanged = (match.letterBag?.length ?? 0) > 0
  match.racks = finale.racks
  match.letterBag = []
  return finale.changed || bagChanged
}

function replenishRack(match: StoredMatch, playerId: string, current: string[], avoidLetters: Iterable<string> = []): string[] {
  ensureSharedLetterBag(match)
  const drawn = drawRackFromBag({
    letterBag: match.letterBag ?? [],
    currentLetters: current,
    avoidLetters,
    chooseIndex: (pool, position) => hash(`${match.id}:${playerId}:${match.turnNumber}:${position}`) % pool.length,
  })
  match.letterBag = drawn.letterBag
  return drawn.rack
}

function publicMatch(match: StoredMatch) {
  const { letterBag: _privateLetterBag, ...safeMatch } = match
  const players = match.playerIds.map(playerId => playerId === match.bot?.playerId ? botUser(match.bot) : publicUser(playerId)).filter(Boolean)
  return { ...safeMatch, players, grid: publicGrid(gridForMatch(match)) }
}

function finishMatch(match: StoredMatch, winnerId: string | null, reason: StoredMatch['finishReason']): void {
  match.status = 'finished'
  match.winnerId = winnerId
  match.finishReason = reason
  match.updatedAt = new Date().toISOString()
  match.turnEndsAt = match.updatedAt
}

function turnDuration(match: Pick<StoredMatch, 'pace'>): number {
  return match.pace === 'async' ? ASYNC_TURN_DURATION_MS : REALTIME_TURN_DURATION_MS
}

function activeMatches(playerId: string, pace?: MatchPace): StoredMatch[] {
  return database.matches.filter(match => match.status === 'active' && match.playerIds.includes(playerId) && (!pace || match.pace === pace))
}

function revealDuration(turn: StoredTurn): number {
  const steps = turn.wrong.length + turn.correct.length + turn.wordBonuses.length + Number(Boolean(turn.rackBonus))
  return Math.max(MIN_REVEAL_DURATION_MS, steps * REVEAL_STEP_MS + 350)
}

function startNextTurn(match: StoredMatch, completedAt: Date, turn: StoredTurn): void {
  const opponentId = match.playerIds.find(playerId => playerId !== turn.playerId) ?? turn.playerId
  const startsAt = new Date(completedAt.getTime() + revealDuration(turn))
  match.currentPlayerId = opponentId
  match.turnNumber += 1
  match.turnStartedAt = startsAt.toISOString()
  match.turnEndsAt = new Date(startsAt.getTime() + TURN_READY_DURATION_MS + turnDuration(match)).toISOString()
}

function sanitizePlacements(match: StoredMatch, playerId: string, placements: unknown[]): Array<{ cellIndex: number; letter: string }> {
  const solution = gridSolution(gridForMatch(match))
  const rack = [...(match.racks[playerId] ?? [])]
  const usedCells = new Set<number>()
  const sanitized: Array<{ cellIndex: number; letter: string }> = []
  for (const raw of placements.slice(0, RACK_SIZE)) {
    if (!raw || typeof raw !== 'object') continue
    const cellIndex = Number((raw as Record<string, unknown>).cellIndex)
    const letter = typeof (raw as Record<string, unknown>).letter === 'string' ? String((raw as Record<string, unknown>).letter).toUpperCase().slice(0, 1) : ''
    const rackIndex = rack.indexOf(letter)
    if (!Number.isInteger(cellIndex) || !solution.has(cellIndex) || match.board[cellIndex] || usedCells.has(cellIndex) || rackIndex < 0) continue
    sanitized.push({ cellIndex, letter })
    rack.splice(rackIndex, 1)
    usedCells.add(cellIndex)
  }
  return sanitized
}

function applyPlayedTurn(match: StoredMatch, playerId: string, sanitized: Array<{ cellIndex: number; letter: string }>): StoredTurn {
  const grid = gridForMatch(match)
  const rack = match.racks[playerId] ?? []
  const before = new Set(Object.keys(match.board).map(Number))
  const aidedCell = match.hint?.playerId === playerId && match.hint.turnNumber === match.turnNumber ? match.hint.cellIndex : null
  const evaluation = evaluateTurn({ grid: ruleGrid(grid), occupiedBefore: before, placements: sanitized, aidedCell })
  evaluation.correctPlacements.forEach(item => { match.board[item.cellIndex] = { letter: item.letter, playerId } })
  match.scores[playerId] = (match.scores[playerId] ?? 0) + evaluation.scoreGained
  if (evaluation.productive) match.productiveTurns[playerId] = (match.productiveTurns[playerId] ?? 0) + 1
  match.inactivity[playerId] = 0
  const usedCorrectLetters = new Set(evaluation.correctPlacements.map(item => item.letter))
  const retainedRack = keepRackLettersAfterTurn(rack, evaluation.correctPlacements)
  match.racks[playerId] = replenishRack(match, playerId, retainedRack, usedCorrectLetters)
  ensureFinalSprintRacks(match)
  const turn: StoredTurn = {
    id: randomUUID(), kind: 'played', playerId, turnNumber: match.turnNumber,
    correct: evaluation.correctCells, wrong: evaluation.wrongCells, wrongPlacements: evaluation.wrongPlacements,
    aidedCell, letterPoints: evaluation.letterPoints, wordBonuses: evaluation.wordBonuses,
    rackBonus: evaluation.rackBonus, scoreGained: evaluation.scoreGained, inactivityCount: 0, createdAt: new Date().toISOString(),
  }
  match.lastTurn = turn
  match.hint = null
  match.updatedAt = turn.createdAt
  if (evaluation.completesGrid) {
    const [left, right] = match.playerIds
    const winner = match.scores[left] === match.scores[right] ? null : match.scores[left] > match.scores[right] ? left : right
    finishMatch(match, winner, 'completed')
  } else startNextTurn(match, new Date(match.updatedAt), turn)
  return turn
}

function createBotProfile(sourceId: string): BotProfile {
  return { playerId: `bot_${randomUUID()}`, ...createBotPersona(sourceId) }
}

function botPlacements(match: StoredMatch): Array<{ cellIndex: number; letter: string }> {
  const bot = match.bot
  if (!bot) return []
  const grid = gridForMatch(match)
  const rack = match.racks[bot.playerId] ?? []
  const botScore = match.scores[bot.playerId] ?? 0
  const bestOpponentScore = Math.max(...match.playerIds
    .filter(playerId => playerId !== bot.playerId)
    .map(playerId => match.scores[playerId] ?? 0), 0)
  return planBotMove({
    grid: ruleGrid(grid),
    occupiedCells: Object.keys(match.board).map(Number),
    rackLetters: rack,
    persona: bot,
    seed: `${match.id}:${match.turnNumber}:${rack.join('')}`,
    scoreGap: bestOpponentScore - botScore,
  }).attempts.map(attempt => ({ cellIndex: attempt.cellIndex, letter: attempt.letter }))
}

function resolveReadyBots(now = Date.now()): boolean {
  let changed = false
  for (const match of database.matches) {
    if (match.status !== 'active' || !match.bot || match.currentPlayerId !== match.bot.playerId) continue
    const thinkingDelay = botThinkingDelayMs(`${match.id}:${match.turnNumber}`)
    if (now < new Date(match.turnStartedAt).getTime() + TURN_READY_DURATION_MS + thinkingDelay) continue
    applyPlayedTurn(match, match.bot.playerId, sanitizePlacements(match, match.bot.playerId, botPlacements(match)))
    changed = true
  }
  return changed
}

function resolveExpired(): void {
  const now = Date.now()
  // Bots live in the authoritative simulation too. Resolve their move before
  // timeout handling so a sleeping development server never makes them forfeit.
  let changed = resolveReadyBots(now)
  database.invitations.forEach(invitation => {
    if (invitation.status === 'pending' && new Date(invitation.expiresAt).getTime() <= now) { invitation.status = 'expired'; changed = true }
  })
  const validSearches = database.searches.filter(search => {
    const user = publicUser(search.playerId)
    if (!user) return false
    if (search.pace === 'realtime') return now - new Date(search.updatedAt).getTime() < REALTIME_SEARCH_STALE_MS && activeMatches(search.playerId, 'realtime').length === 0
    return now - new Date(search.createdAt).getTime() < ASYNC_SEARCH_DURATION_MS && activeMatches(search.playerId, 'async').length < MAX_ASYNC_MATCHES
  })
  if (validSearches.length !== database.searches.length) { database.searches = validSearches; changed = true }
  database.matches.forEach(match => {
    if (match.status !== 'active' || !isTurnSubmissionExpired(now, new Date(match.turnEndsAt).getTime(), TURN_SUBMIT_GRACE_MS)) return
    const inactivePlayerId = match.currentPlayerId
    const inactivityCount = (match.inactivity[inactivePlayerId] ?? 0) + 1
    match.inactivity[inactivePlayerId] = inactivityCount
    const occurredAt = new Date()
    match.lastTurn = {
      id: randomUUID(), kind: 'timeout', playerId: inactivePlayerId, turnNumber: match.turnNumber,
      correct: [], wrong: [], wrongPlacements: [], aidedCell: null, letterPoints: 0, wordBonuses: [], rackBonus: 0,
      scoreGained: 0, inactivityCount, createdAt: occurredAt.toISOString(),
    }
    match.hint = null
    match.updatedAt = occurredAt.toISOString()
    const opponentId = match.playerIds.find(playerId => playerId !== inactivePlayerId) ?? null
    if (shouldForfeitAfterInactivity(inactivityCount)) finishMatch(match, opponentId, 'timeout')
    else {
      startNextTurn(match, occurredAt, match.lastTurn)
    }
    changed = true
  })
  if (changed) saveDatabase()
}

function resolveBotFallback(playerId: string): void {
  const search = database.searches.find(candidate => candidate.playerId === playerId)
  if (!search) return
  const delay = search.pace === 'realtime' ? REALTIME_BOT_MATCH_DELAY_MS : ASYNC_BOT_MATCH_DELAY_MS
  if (Date.now() - new Date(search.createdAt).getTime() < delay) return
  const humanCandidate = database.searches.some(candidate => candidate.id !== search.id && candidate.pace === search.pace)
  if (humanCandidate) return
  if (search.pace === 'realtime' && activeMatches(playerId, 'realtime').length) return
  if (search.pace === 'async' && activeMatches(playerId, 'async').length >= MAX_ASYNC_MATCHES) return
  const bot = createBotProfile(search.id)
  const match = createMatch(playerId, bot.playerId, 'normal', search.pace, search.id, null, bot)
  database.matches.push(match)
  database.searches = database.searches.filter(candidate => candidate.id !== search.id)
  saveDatabase()
}

function lobbyState(playerId: string) {
  resolveExpired()
  resolveBotFallback(playerId)
  const invitationView = (invitation: MatchInvitation) => ({
    ...invitation,
    host: publicUser(invitation.hostId),
    guest: publicUser(invitation.guestId),
  })
  const incoming = database.invitations.filter(invitation => invitation.guestId === playerId && invitation.status === 'pending').map(invitationView)
  const outgoing = database.invitations.filter(invitation => invitation.hostId === playerId && invitation.status === 'pending').map(invitationView)
  const active = database.matches.filter(match => match.status === 'active' && match.playerIds.includes(playerId)).map(publicMatch)
  const searches = database.searches.filter(search => search.playerId === playerId).map(({ id, pace, createdAt }) => ({ id, pace, createdAt }))
  const recent = database.matches
    .filter(match => match.status === 'finished' && match.playerIds.includes(playerId))
    .sort((left, right) => new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime())
    .slice(0, 5)
    .map(match => {
      const opponentId = match.playerIds.find(id => id !== playerId) ?? ''
      const interrupted = match.finishReason === 'forfeit' || match.finishReason === 'timeout'
      const won = match.winnerId === playerId
      return {
        id: match.id,
        mode: 'multiplayer' as const,
        pace: match.pace,
        outcome: interrupted ? won ? 'opponent-abandoned' : 'abandon' : match.winnerId === null ? 'draw' : won ? 'win' : 'loss',
        score: Math.max(0, match.scores[playerId] ?? 0),
        opponentScore: Math.max(0, match.scores[opponentId] ?? 0),
        opponentName: match.bot?.playerId === opponentId ? match.bot.displayName : publicUser(opponentId)?.displayName ?? null,
        completedAt: match.updatedAt,
      }
    })
  return { incoming, outgoing, active, searches, recent }
}

function selectGridForPlayers(hostId: string, guestId: string, sourceId: string, now: Date): CatalogGrid {
  const players = new Set([hostId, guestId])
  const recentIds = new Set<string>()
  const recentMatches = database.matches
    .filter(match => match.playerIds.some(playerId => players.has(playerId)))
    .sort((left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime())

  for (const match of recentMatches) {
    recentIds.add(match.gridId)
    if (recentIds.size >= RECENT_GRID_HISTORY_LIMIT) break
  }

  const available = grids.filter(grid => !recentIds.has(grid.id))
  const pool = available.length ? available : grids
  return pool[hash(`${sourceId}:${now.toISOString()}:grid`) % pool.length]
}

function createMatch(hostId: string, guestId: string, mode: MatchMode, pace: MatchPace, sourceId: string, invitationId: string | null = null, bot: BotProfile | null = null): StoredMatch {
  const now = new Date()
  const grid = selectGridForPlayers(hostId, guestId, sourceId, now)
  const difficulty: StoredMatch['difficulty'] = bot?.skill === 'beginner' ? 'easy' : bot?.skill === 'expert' ? 'hard' : 'normal'
  const match: StoredMatch = {
    id: randomUUID(), invitationId, mode, pace, gridId: grid.id, difficulty,
    playerIds: [hostId, guestId], bot, currentPlayerId: hostId, turnNumber: 1,
    turnStartedAt: now.toISOString(), turnEndsAt: new Date(now.getTime() + TURN_READY_DURATION_MS + (pace === 'async' ? ASYNC_TURN_DURATION_MS : REALTIME_TURN_DURATION_MS)).toISOString(),
    board: {}, racks: {}, letterBag: [...gridSolution(grid).values()], scores: { [hostId]: 0, [guestId]: 0 },
    productiveTurns: { [hostId]: 0, [guestId]: 0 },
    inactivity: { [hostId]: 0, [guestId]: 0 }, hint: null,
    hintUsed: {}, rerollUsed: {}, lastTurn: null, status: 'active', winnerId: null, finishReason: null,
    createdAt: now.toISOString(), updatedAt: now.toISOString(),
  }
  match.racks[hostId] = replenishRack(match, hostId, [])
  match.racks[guestId] = replenishRack(match, guestId, [])
  return match
}

const requestContext = {
  database, cleanPlayerId, publicUser, areFriends, activeMatches, resolveExpired, lobbyState,
  ensureFinalSprintRacks, publicMatch, saveDatabase, createMatch, finishMatch, gridForMatch,
  replenishRack, sanitizePlacements, startNextTurn, applyPlayedTurn,
}

function attachMatchApi(middlewares: { use: (route: string, handler: (request: IncomingMessage, response: ServerResponse) => void) => void }): void {
  middlewares.use('/api/matches', (request, response) => {
    void handleMatchRequest(request, response, requestContext).catch(error => sendJson(response, 500, { error: error instanceof Error ? error.message : 'Le service de partie a rencontré une erreur.' }))
  })
}

export function motmanMatchPlugin(): Plugin {
  return {
    name: 'motman-match-api',
    configureServer(server) { attachMatchApi(server.middlewares) },
    configurePreviewServer(server) { attachMatchApi(server.middlewares) },
  }
}
