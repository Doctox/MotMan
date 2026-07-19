import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { IncomingMessage, ServerResponse } from 'node:http'
import type { Plugin } from 'vite'
import catalog from '../src/data/runtime.grid.catalog.json'
import { isCatalogGridPlayable } from '../src/gridCatalogPolicy'
import { botThinkingDelayMs, createBotPersona, planBotMove, type BotSkill } from '../src/botOpponents'
import { gridCellIndex, resolveGridDimensions, type GridDimensionsSource } from '../src/gridDimensions'
import {
  canUseHint,
  canUseReroll,
  evaluateTurn,
  gameWordCellIndexes,
  hasTurnStarted,
  hintCandidates,
  isTurnSubmissionExpired,
  keepRackLettersAfterTurn,
  replenishUniqueRack,
  REWARD_STEP_MS,
  shouldForfeitAfterInactivity,
  type GameRuleGrid,
  type GameRuleWord,
} from '../src/gameRules'
import { database as accountDatabase, type DatabaseUser } from './motmanDatabase'

type CatalogWord = {
  wordId?: string
  answer: string
  clue?: string
  image?: unknown
  direction: 'across' | 'down'
  arrow?: string
  clueCell: number[]
  cells: number[][]
}
type CatalogGrid = GridDimensionsSource & { id: string; clueCells?: number[][]; words: CatalogWord[] }
type MatchInvitation = {
  id: string
  hostId: string
  guestId: string
  pace: MatchPace
  createdAt: string
  expiresAt: string
  status: 'pending' | 'accepted' | 'declined' | 'cancelled' | 'expired'
  matchId?: string
}
type MatchPace = 'realtime' | 'async'
type MatchMode = 'friend' | 'normal'
type MatchSearch = { id: string; playerId: string; pace: MatchPace; createdAt: string; updatedAt: string }
type BotProfile = { playerId: string; displayName: string; level: number; skill: BotSkill; avatarId: string; frameId: string }
type StoredTurn = {
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
type StoredMatch = {
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
type MatchDatabase = { version: 4; invitations: MatchInvitation[]; matches: StoredMatch[]; searches: MatchSearch[] }

function numericEnvironment(name: string, fallback: number, minimum: number): number {
  const parsed = Number(process.env[name])
  return Number.isFinite(parsed) ? Math.max(minimum, parsed) : fallback
}

const MATCH_DATABASE_PATH = resolve(process.env.MOTMAN_MATCH_DATABASE_PATH ?? '.motman-matches.json')
const REALTIME_TURN_DURATION_MS = numericEnvironment('MOTMAN_TURN_DURATION_MS', 45_000, 250)
const ASYNC_TURN_DURATION_MS = numericEnvironment('MOTMAN_ASYNC_TURN_DURATION_MS', 24 * 60 * 60 * 1_000, 1_000)
const TURN_READY_DURATION_MS = numericEnvironment('MOTMAN_TURN_READY_DURATION_MS', 1_800, 0)
// A short server grace period lets a phone submit the move displayed at 00:00
// without a simultaneous polling request turning it into a timeout first.
const TURN_SUBMIT_GRACE_MS = numericEnvironment('MOTMAN_TURN_GRACE_MS', 2_000, 0)
const REVEAL_STEP_MS = numericEnvironment('MOTMAN_REVEAL_STEP_MS', REWARD_STEP_MS, 0)
const MIN_REVEAL_DURATION_MS = numericEnvironment('MOTMAN_MIN_REVEAL_DURATION_MS', 700, 0)
const INVITATION_DURATION_MS = 120_000
const ASYNC_INVITATION_DURATION_MS = 7 * 24 * 60 * 60 * 1_000
const REALTIME_SEARCH_STALE_MS = 45_000
const ASYNC_SEARCH_DURATION_MS = 7 * 24 * 60 * 60 * 1_000
const REALTIME_BOT_MATCH_DELAY_MS = Math.max(1_000, Number(process.env.MOTMAN_REALTIME_BOT_DELAY_MS) || 30_000)
const ASYNC_BOT_MATCH_DELAY_MS = Math.max(1_000, Number(process.env.MOTMAN_ASYNC_BOT_DELAY_MS) || 30_000)
const MAX_ASYNC_MATCHES = 3
const RECENT_GRID_HISTORY_LIMIT = 12
const EMPTY_DATABASE: MatchDatabase = { version: 4, invitations: [], matches: [], searches: [] }
const grids = (catalog.grids as CatalogGrid[]).filter(isCatalogGridPlayable)
const gridIds = new Set(grids.map(grid => grid.id))
if (!grids.length) throw new Error('Le catalogue actif ne contient aucune grille jouable.')

function loadMatchDatabase(): MatchDatabase {
  try {
    if (!existsSync(MATCH_DATABASE_PATH)) return structuredClone(EMPTY_DATABASE)
    const parsed = JSON.parse(readFileSync(MATCH_DATABASE_PATH, 'utf8')) as Partial<MatchDatabase> & { version?: number }
    if (![1, 2, 3, 4].includes(parsed.version ?? 0) || !Array.isArray(parsed.invitations) || !Array.isArray(parsed.matches)) return structuredClone(EMPTY_DATABASE)
    const loaded: MatchDatabase = {
      version: 4,
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
      match.hintUsed ??= {}
      match.rerollUsed ??= {}
      if (match.lastTurn) {
        match.lastTurn.kind ??= 'played'
        match.lastTurn.inactivityCount ??= 0
        match.lastTurn.wrongPlacements ??= []
      }
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

function sendJson(response: ServerResponse, status: number, payload: unknown): void {
  response.statusCode = status
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store')
  response.end(JSON.stringify(payload))
}

function sendNoContent(response: ServerResponse): void {
  response.statusCode = 204
  response.setHeader('Cache-Control', 'no-store')
  response.end()
}

async function readBody(request: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Uint8Array[] = []
  for await (const chunk of request) chunks.push(typeof chunk === 'string' ? Buffer.from(chunk) : chunk)
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) as Record<string, unknown> : {}
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
  const grid = grids.find(candidate => candidate.id === match.gridId)
  if (!grid) throw new Error('La grille de cette partie est introuvable.')
  return grid
}

const ruleGridCache = new Map<string, GameRuleGrid>()

function ruleWord(word: CatalogWord): GameRuleWord {
  return {
    ...word,
    cells: word.cells.map(([row, column]) => [row, column] as const),
  }
}

function ruleGrid(grid: CatalogGrid): GameRuleGrid {
  const cached = ruleGridCache.get(grid.id)
  if (cached) return cached
  const dimensions = resolveGridDimensions(grid)
  const cells: GameRuleGrid['cells'][number][] = Array.from(
    { length: dimensions.columns * dimensions.rows },
    () => ({ kind: 'clue' }),
  )
  grid.words.forEach(word => word.cells.forEach(([row, column], offset) => {
    cells[gridCellIndex(dimensions, row, column)] = { kind: 'letter', solution: word.answer[offset] }
  }))
  const created: GameRuleGrid = { ...dimensions, cells, words: grid.words.map(ruleWord) }
  ruleGridCache.set(grid.id, created)
  return created
}

function gridSolution(grid: CatalogGrid): Map<number, string> {
  const dimensions = resolveGridDimensions(grid)
  const solution = new Map<number, string>()
  grid.words.forEach(word => word.cells.forEach(([row, col], offset) => solution.set(gridCellIndex(dimensions, row, col), word.answer[offset])))
  return solution
}

function wordIndexes(grid: CatalogGrid, word: CatalogWord): number[] {
  return gameWordCellIndexes(ruleGrid(grid), ruleWord(word))
}

function hash(text: string): number {
  let value = 2166136261
  for (const character of text) value = Math.imul(value ^ character.charCodeAt(0), 16777619)
  return value >>> 0
}

function replenishRack(match: StoredMatch, playerId: string, current: string[], avoidLetters: Iterable<string> = []): string[] {
  const solution = gridSolution(gridForMatch(match))
  const needed = [...solution.entries()].flatMap(([index, letter]) => match.board[index] ? [] : [letter])
  return replenishUniqueRack({
    neededLetters: needed,
    currentLetters: current,
    avoidLetters,
    chooseIndex: (pool, position) => hash(`${match.id}:${playerId}:${match.turnNumber}:${position}`) % pool.length,
  })
}

function publicGrid(grid: CatalogGrid) {
  const { columns, rows } = resolveGridDimensions(grid)
  const cells: Array<Record<string, unknown>> = Array.from(
    { length: columns * rows },
    () => ({ kind: 'clue', entries: [] }),
  )
  const clueIndexes = new Set((grid.clueCells ?? grid.words.map(word => word.clueCell))
    .map(([row, column]) => gridCellIndex({ columns, rows }, row, column)))
  for (let index = 0; index < cells.length; index += 1) {
    if (!clueIndexes.has(index)) cells[index] = { kind: 'letter', solution: '', wordIds: [] }
  }
  const words = grid.words.map((word, index) => {
    const id = word.wordId ?? `${grid.id}:word:${index}`
    const clueIndex = gridCellIndex({ columns, rows }, word.clueCell[0], word.clueCell[1])
    const clueCell = cells[clueIndex]
    const entries = Array.isArray(clueCell.entries) ? clueCell.entries as unknown[] : []
    entries.push({
      text: word.clue ?? '', image: word.image, direction: word.direction,
      arrow: word.arrow ?? (word.direction === 'across' ? 'right' : 'down'), wordId: id,
    })
    clueCell.entries = entries
    for (const [row, column] of word.cells) {
      const cell = cells[gridCellIndex({ columns, rows }, row, column)]
      const wordIds = Array.isArray(cell.wordIds) ? cell.wordIds as string[] : []
      wordIds.push(id)
      cell.wordIds = wordIds
    }
    const [row, col] = word.cells[0]
    return {
      id, answer: '•'.repeat(word.answer.length), clue: word.clue ?? '', image: word.image,
      difficulty: 1, theme: 'catalogue', row, col, direction: word.direction, length: word.answer.length,
    }
  })
  return {
    id: grid.id, columns, rows, difficulty: 'normal', cells, words,
    seed: hash(grid.id), version: 'local-test-v1', validation: { valid: true, errors: [], score: 100 },
  }
}

function publicMatch(match: StoredMatch) {
  const players = match.playerIds.map(playerId => playerId === match.bot?.playerId ? botUser(match.bot) : publicUser(playerId)).filter(Boolean)
  return { ...match, players, grid: publicGrid(gridForMatch(match)) }
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
  const rack = match.racks[playerId] ?? []
  const usedLetters = new Set<string>()
  const usedCells = new Set<number>()
  const sanitized: Array<{ cellIndex: number; letter: string }> = []
  for (const raw of placements) {
    if (!raw || typeof raw !== 'object') continue
    const cellIndex = Number((raw as Record<string, unknown>).cellIndex)
    const letter = typeof (raw as Record<string, unknown>).letter === 'string' ? String((raw as Record<string, unknown>).letter).toUpperCase().slice(0, 1) : ''
    if (!Number.isInteger(cellIndex) || !solution.has(cellIndex) || match.board[cellIndex] || usedCells.has(cellIndex) || usedLetters.has(letter) || !rack.includes(letter)) continue
    sanitized.push({ cellIndex, letter })
    usedCells.add(cellIndex)
    usedLetters.add(letter)
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
  return { incoming, outgoing, active, searches }
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
    board: {}, racks: {}, scores: { [hostId]: 0, [guestId]: 0 },
    productiveTurns: { [hostId]: 0, [guestId]: 0 },
    inactivity: { [hostId]: 0, [guestId]: 0 }, hint: null,
    hintUsed: {}, rerollUsed: {}, lastTurn: null, status: 'active', winnerId: null, finishReason: null,
    createdAt: now.toISOString(), updatedAt: now.toISOString(),
  }
  match.racks[hostId] = replenishRack(match, hostId, [])
  match.racks[guestId] = replenishRack(match, guestId, [])
  return match
}

async function handleMatchRequest(request: IncomingMessage, response: ServerResponse): Promise<void> {
  const url = new URL(request.url ?? '/', 'http://motman.local')
  const route = url.pathname.replace(/^\/api\/matches\/?/, '').replace(/^\/+/, '')

  if (request.method === 'GET' && route === 'state') {
    const playerId = cleanPlayerId(url.searchParams.get('playerId'))
    if (!playerId) return sendJson(response, 400, { error: 'Identité invalide.' })
    const liveSearch = database.searches.find(search => search.playerId === playerId && search.pace === 'realtime')
    if (liveSearch) liveSearch.updatedAt = new Date().toISOString()
    return sendJson(response, 200, lobbyState(playerId))
  }

  if (request.method === 'GET' && route.startsWith('match/')) {
    resolveExpired()
    const playerId = cleanPlayerId(url.searchParams.get('playerId'))
    const matchId = route.slice('match/'.length)
    const match = database.matches.find(candidate => candidate.id === matchId && candidate.playerIds.includes(playerId))
    if (!match) return sendJson(response, 404, { error: 'Partie introuvable.' })
    if (url.searchParams.get('since') === match.updatedAt) return sendNoContent(response)
    return sendJson(response, 200, publicMatch(match))
  }

  if (request.method !== 'POST') return sendJson(response, 405, { error: 'Méthode non autorisée.' })
  let body: Record<string, unknown>
  try { body = await readBody(request) } catch { return sendJson(response, 400, { error: 'Requête invalide.' }) }
  const playerId = cleanPlayerId(body.playerId)
  if (!playerId || !publicUser(playerId)) return sendJson(response, 400, { error: 'Profil joueur invalide.' })

  if (route === 'unregister') {
    database.invitations = database.invitations.filter(invitation => invitation.hostId !== playerId && invitation.guestId !== playerId)
    database.matches = database.matches.filter(match => !match.playerIds.includes(playerId))
    database.searches = database.searches.filter(search => search.playerId !== playerId)
    saveDatabase()
    return sendJson(response, 200, { ok: true })
  }

  if (route === 'create') {
    resolveExpired()
    const targetId = cleanPlayerId(body.targetId)
    const pace: MatchPace | '' = body.pace === 'realtime' ? 'realtime' : body.pace === 'async' ? 'async' : ''
    if (!pace) return sendJson(response, 400, { error: 'Rythme de partie invalide.' })
    const target = publicUser(targetId)
    if (!target || !areFriends(playerId, targetId)) return sendJson(response, 404, { error: 'Cet ami est introuvable.' })
    if (pace === 'realtime' && !target.online) return sendJson(response, 409, { error: `${target.displayName} est hors ligne.` })
    if (pace === 'realtime' && (activeMatches(playerId, 'realtime').length || activeMatches(targetId, 'realtime').length))
      return sendJson(response, 409, { error: 'Un des joueurs est déjà en partie.' })
    const existing = database.invitations.find(invitation => invitation.status === 'pending' &&
      ((invitation.hostId === playerId && invitation.guestId === targetId) || (invitation.hostId === targetId && invitation.guestId === playerId)))
    if (!existing) {
      const createdAt = new Date()
      const invitationDuration = pace === 'async' ? ASYNC_INVITATION_DURATION_MS : INVITATION_DURATION_MS
      database.invitations.push({ id: randomUUID(), hostId: playerId, guestId: targetId, pace, createdAt: createdAt.toISOString(), expiresAt: new Date(createdAt.getTime() + invitationDuration).toISOString(), status: 'pending' })
      saveDatabase()
    }
    return sendJson(response, 200, lobbyState(playerId))
  }

  if (route === 'respond') {
    resolveExpired()
    const invitationId = typeof body.invitationId === 'string' ? body.invitationId : ''
    const decision = body.decision === 'accept' ? 'accept' : body.decision === 'decline' ? 'decline' : ''
    const invitation = database.invitations.find(candidate => candidate.id === invitationId && candidate.guestId === playerId && candidate.status === 'pending')
    if (!invitation || !decision) return sendJson(response, 404, { error: 'Cette invitation n’est plus disponible.' })
    if (decision === 'decline') invitation.status = 'declined'
    else {
      if (invitation.pace === 'realtime' && (activeMatches(invitation.hostId, 'realtime').length || activeMatches(invitation.guestId, 'realtime').length))
        return sendJson(response, 409, { error: 'Un des joueurs est déjà en partie.' })
      const match = createMatch(invitation.hostId, invitation.guestId, 'friend', invitation.pace, invitation.id, invitation.id)
      database.matches.push(match)
      invitation.status = 'accepted'
      invitation.matchId = match.id
    }
    saveDatabase()
    return sendJson(response, 200, lobbyState(playerId))
  }

  if (route === 'cancel') {
    const invitationId = typeof body.invitationId === 'string' ? body.invitationId : ''
    const invitation = database.invitations.find(candidate => candidate.id === invitationId && candidate.hostId === playerId && candidate.status === 'pending')
    if (!invitation) return sendJson(response, 404, { error: 'Cette invitation n’existe plus.' })
    invitation.status = 'cancelled'
    saveDatabase()
    return sendJson(response, 200, lobbyState(playerId))
  }

  if (route === 'search' || route === 'search/cancel') {
    resolveExpired()
    const pace: MatchPace | '' = body.pace === 'realtime' ? 'realtime' : body.pace === 'async' ? 'async' : ''
    if (!pace) return sendJson(response, 400, { error: 'Rythme de partie invalide.' })
    if (route === 'search/cancel') {
      database.searches = database.searches.filter(search => search.playerId !== playerId || search.pace !== pace)
      saveDatabase()
      return sendJson(response, 200, lobbyState(playerId))
    }
    if (pace === 'realtime' && activeMatches(playerId, 'realtime').length)
      return sendJson(response, 409, { error: 'Vous avez déjà une partie en temps réel.' })
    if (pace === 'async' && activeMatches(playerId, 'async').length >= MAX_ASYNC_MATCHES)
      return sendJson(response, 409, { error: 'Vous avez déjà trois parties asynchrones.' })
    const candidate = [...database.searches]
      .filter(search => search.playerId !== playerId && search.pace === pace)
      .filter(search => pace === 'realtime'
        ? Date.now() - new Date(search.updatedAt).getTime() < REALTIME_SEARCH_STALE_MS && activeMatches(search.playerId, 'realtime').length === 0
        : activeMatches(search.playerId, 'async').length < MAX_ASYNC_MATCHES)
      .sort((left, right) => new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime())[0]
    if (candidate) {
      const match = createMatch(candidate.playerId, playerId, 'normal', pace, candidate.id)
      database.matches.push(match)
      database.searches = database.searches.filter(search => search.id !== candidate.id && !(search.playerId === playerId && search.pace === pace))
      saveDatabase()
      return sendJson(response, 200, { lobby: lobbyState(playerId), matchId: match.id })
    }
    const existing = database.searches.find(search => search.playerId === playerId && search.pace === pace)
    if (!existing) {
      const createdAt = new Date().toISOString()
      database.searches.push({ id: randomUUID(), playerId, pace, createdAt, updatedAt: createdAt })
    } else existing.updatedAt = new Date().toISOString()
    saveDatabase()
    return sendJson(response, 200, { lobby: lobbyState(playerId), matchId: null })
  }

  const matchId = typeof body.matchId === 'string' ? body.matchId : ''
  // A turn submission is resolved before expiry. Other actions may safely
  // advance every expired match first.
  if (route !== 'turn') resolveExpired()
  let match = database.matches.find(candidate => candidate.id === matchId && candidate.playerIds.includes(playerId))
  if (!match) return sendJson(response, 404, { error: 'Partie introuvable.' })
  if (route === 'turn' && match.status === 'active' && isTurnSubmissionExpired(Date.now(), new Date(match.turnEndsAt).getTime(), TURN_SUBMIT_GRACE_MS)) {
    resolveExpired()
    match = database.matches.find(candidate => candidate.id === matchId && candidate.playerIds.includes(playerId))
    if (!match) return sendJson(response, 404, { error: 'Partie introuvable.' })
  }

  const requestedTurnNumber = Number(body.turnNumber)
  if (route === 'turn' && Number.isInteger(requestedTurnNumber) && match.lastTurn?.playerId === playerId && match.lastTurn.turnNumber === requestedTurnNumber) {
    return sendJson(response, 200, { match: publicMatch(match), result: match.lastTurn })
  }
  if (match.status !== 'active') return sendJson(response, 409, { error: 'Cette partie est terminée.', match: publicMatch(match) })

  if (route === 'forfeit') {
    const winner = match.playerIds.find(id => id !== playerId) ?? null
    finishMatch(match, winner, 'forfeit')
    saveDatabase()
    return sendJson(response, 200, publicMatch(match))
  }

  if (match.currentPlayerId !== playerId) return sendJson(response, 409, { error: 'Ce n’est pas votre tour.', match: publicMatch(match) })
  if (!hasTurnStarted(Date.now(), new Date(match.turnStartedAt).getTime())) {
    return sendJson(response, 409, { error: 'Le prochain tour commence après les résultats.', match: publicMatch(match) })
  }

  if (route === 'hint') {
    if (!canUseHint(Boolean(match.hintUsed[playerId]))) return sendJson(response, 409, { error: 'Indice déjà utilisé pendant cette partie.' })
    const currentGrid = gridForMatch(match)
    const solution = gridSolution(currentGrid)
    const rack = match.racks[playerId] ?? []
    const candidates = hintCandidates(ruleGrid(currentGrid), rack, Object.keys(match.board).map(Number))
    if (!candidates.length) return sendJson(response, 409, { error: 'Aucun indice disponible.' })
    const selected = candidates[hash(`${match.id}:${playerId}:${match.turnNumber}:hint`) % candidates.length]
    match.hint = { playerId, cellIndex: selected.cellIndex, letter: selected.letter, turnNumber: match.turnNumber }
    match.hintUsed[playerId] = true
    match.board[selected.cellIndex] = { letter: selected.letter, playerId }
    const hintedLetterIndex = rack.indexOf(selected.letter)
    match.racks[playerId] = rack.filter((_, index) => index !== hintedLetterIndex)
    match.updatedAt = new Date().toISOString()
    if ([...solution.keys()].every(index => match.board[index])) {
      const [left, right] = match.playerIds
      const winner = match.scores[left] === match.scores[right] ? null : match.scores[left] > match.scores[right] ? left : right
      finishMatch(match, winner, 'completed')
    }
    saveDatabase()
    return sendJson(response, 200, publicMatch(match))
  }

  if (route === 'reroll') {
    const rerollAllowed = canUseReroll({
      alreadyUsed: Boolean(match.rerollUsed[playerId]),
      pendingPlacements: 0,
      hintActive: match.hint?.playerId === playerId && match.hint.turnNumber === match.turnNumber,
    })
    if (!rerollAllowed) return sendJson(response, 409, { error: 'Relance déjà utilisée ou indisponible pendant ce tour.' })
    const currentRack = match.racks[playerId] ?? []
    match.racks[playerId] = replenishRack(match, playerId, [], currentRack)
    match.rerollUsed[playerId] = true
    match.updatedAt = new Date().toISOString()
    saveDatabase()
    return sendJson(response, 200, publicMatch(match))
  }

  if (route !== 'turn') return sendJson(response, 404, { error: 'Action inconnue.' })
  if (Number.isInteger(requestedTurnNumber) && requestedTurnNumber !== match.turnNumber) {
    return sendJson(response, 409, { error: 'Ce tour est déjà terminé.', match: publicMatch(match) })
  }
  const placements = Array.isArray(body.placements) ? body.placements : []
  const sanitized = sanitizePlacements(match, playerId, placements)

  // Reaching zero with placed letters validates them exactly like the button.
  // Reaching zero without a placement remains a genuine inactivity timeout.
  if (body.automatic === true && sanitized.length === 0) {
    const inactivityCount = (match.inactivity[playerId] ?? 0) + 1
    match.inactivity[playerId] = inactivityCount
    const occurredAt = new Date()
    match.lastTurn = {
      id: randomUUID(), kind: 'timeout', playerId, turnNumber: match.turnNumber,
      correct: [], wrong: [], wrongPlacements: [], aidedCell: null, letterPoints: 0,
      wordBonuses: [], rackBonus: 0, scoreGained: 0, inactivityCount,
      createdAt: occurredAt.toISOString(),
    }
    match.hint = null
    match.updatedAt = occurredAt.toISOString()
    const opponentId = match.playerIds.find(id => id !== playerId) ?? null
    if (shouldForfeitAfterInactivity(inactivityCount)) finishMatch(match, opponentId, 'timeout')
    else startNextTurn(match, occurredAt, match.lastTurn)
    saveDatabase()
    return sendJson(response, 200, { match: publicMatch(match), result: match.lastTurn })
  }
  const result = applyPlayedTurn(match, playerId, sanitized)
  saveDatabase()
  return sendJson(response, 200, { match: publicMatch(match), result })
}

function attachMatchApi(middlewares: { use: (route: string, handler: (request: IncomingMessage, response: ServerResponse) => void) => void }): void {
  middlewares.use('/api/matches', (request, response) => {
    void handleMatchRequest(request, response).catch(error => sendJson(response, 500, { error: error instanceof Error ? error.message : 'Le service de partie a rencontré une erreur.' }))
  })
}

export function motmanMatchPlugin(): Plugin {
  return {
    name: 'motman-match-api',
    configureServer(server) { attachMatchApi(server.middlewares) },
    configurePreviewServer(server) { attachMatchApi(server.middlewares) },
  }
}
