import { createClient } from '@supabase/supabase-js'
import { botThinkingDelayMs, createBotPersona, planBotMove, type BotSkill } from '../../../src/botOpponents.ts'
import {
  canUseHint, canUseReroll, drawRackFromBag, evaluateTurn, hintCandidates, keepRackLettersAfterTurn, REWARD_STEP_MS,
  shouldForfeitAfterInactivity, type GameRuleGrid, type GameRuleWord,
} from '../../../src/gameRules.ts'
import { calculateFeatherReward } from '../../../src/progressionRewards.ts'
import { selectGridForPlayers } from '../../../src/gridSelection.ts'

type Pace = 'realtime' | 'async'
type Mode = 'solo' | 'friend' | 'normal'
type CatalogWord = { wordId?: string; answer: string; clue?: string; image?: unknown; direction: 'across' | 'down'; arrow?: string; clueCell: number[]; cells: number[][] }
type CatalogGrid = { id: string; columns: number; rows: number; clueCells: number[][]; words: CatalogWord[] }
type Bot = { playerId: string; displayName: string; level: number; skill: BotSkill; avatarId: string; frameId: string }
type Turn = {
  id: string; kind: 'played' | 'timeout'; playerId: string; turnNumber: number; correct: number[]; wrong: number[];
  wrongPlacements: Array<{ cellIndex: number; letter: string }>; aidedCell: number | null; letterPoints: number;
  wordBonuses: Array<{ cells: number[]; points: number; direction: 'across' | 'down' }>;
  rackBonus: number; scoreGained: number; inactivityCount: number; createdAt: string
}
type State = {
  invitationId: string | null; difficulty: 'easy' | 'normal' | 'hard'; playerIds: [string, string]; bot: Bot | null;
  board: Record<string, { letter: string; playerId: string }>; racks: Record<string, string[]>; letterBag?: string[]; scores: Record<string, number>;
  productiveTurns: Record<string, number>; inactivity: Record<string, number>;
  rackCompletions: Record<string, number>;
  hint: { playerId: string; cellIndex: number; letter: string; turnNumber: number } | null;
  hintUsed: Record<string, boolean | number>; rerollUsed: Record<string, boolean | number>; lastTurn: Turn | null;
}
type MatchRow = {
  id: string; mode: Mode; pace: Pace; grid_id: string; state: State; status: 'active' | 'finished'; current_player_id: string;
  turn_number: number; turn_started_at: string; turn_ends_at: string; winner_id: string | null; finish_reason: 'completed' | 'timeout' | 'forfeit' | null;
  created_at: string; updated_at: string
}

const REALTIME_TURN_MS = 45_000
const ASYNC_TURN_MS = 24 * 60 * 60 * 1000
const READY_MS = 1_800
const GRACE_MS = 2_000
const BOT_SEARCH_MS = 30_000
const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'authorization, apikey, content-type, x-client-info', 'Access-Control-Allow-Methods': 'POST, OPTIONS' }
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } })
const nowIso = () => new Date().toISOString()

function hash(text: string): number {
  let value = 2166136261
  for (const character of text) value = Math.imul(value ^ character.charCodeAt(0), 16777619)
  return value >>> 0
}

function dimensions(grid: CatalogGrid) {
  const columns = grid.columns
  const rows = grid.rows
  if (!Number.isInteger(columns) || !Number.isInteger(rows) || columns <= 0 || rows <= 0) throw new Error(`Dimensions invalides pour ${grid.id}`)
  return { columns, rows }
}

function ruleGrid(grid: CatalogGrid): GameRuleGrid {
  const { columns, rows } = dimensions(grid)
  const cells: Array<{ kind: string; solution?: string }> = Array.from({ length: columns * rows }, () => ({ kind: 'clue' }))
  for (const word of grid.words) word.cells.forEach(([row, col], offset) => { cells[row * columns + col] = { kind: 'letter', solution: word.answer[offset] } })
  const words: GameRuleWord[] = grid.words.map((word, index) => ({ id: word.wordId ?? `${grid.id}:word:${index}`, answer: word.answer, direction: word.direction, cells: word.cells }))
  return { columns, rows, cells, words }
}

function publicGrid(grid: CatalogGrid) {
  const { columns, rows } = dimensions(grid)
  const cells: Array<Record<string, unknown>> = Array.from({ length: columns * rows }, () => ({ kind: 'clue', entries: [] }))
  const clueIndexes = new Set(grid.clueCells.map(([row, col]) => row * columns + col))
  for (let index = 0; index < cells.length; index += 1) if (!clueIndexes.has(index)) cells[index] = { kind: 'letter', solution: '', wordIds: [] }
  const words = grid.words.map((word, index) => {
    const id = word.wordId ?? `${grid.id}:word:${index}`
    const clueIndex = word.clueCell[0] * columns + word.clueCell[1]
    const clue = cells[clueIndex]
    const entries = Array.isArray(clue.entries) ? clue.entries as unknown[] : []
    entries.push({ text: word.clue ?? '', image: word.image, direction: word.direction, arrow: word.arrow ?? (word.direction === 'across' ? 'right' : 'down'), wordId: id })
    clue.entries = entries
    for (const [row, col] of word.cells) {
      const cell = cells[row * columns + col]
      const wordIds = Array.isArray(cell.wordIds) ? cell.wordIds as string[] : []
      wordIds.push(id); cell.wordIds = wordIds
    }
    const [row, col] = word.cells[0]
    return { id, answer: '•'.repeat(word.answer.length), clue: word.clue ?? '', image: word.image, difficulty: 1, theme: 'catalogue', row, col, direction: word.direction, length: word.answer.length }
  })
  return { id: grid.id, columns, rows, difficulty: 'normal', cells, words, seed: hash(grid.id), version: 'supabase-v1', validation: { valid: true, errors: [], score: 100 } }
}

function neededLetters(grid: GameRuleGrid, board: State['board']): string[] {
  return grid.cells.flatMap((cell, index) => cell.kind === 'letter' && !board[String(index)] && cell.solution ? [cell.solution] : [])
}

function ensureSharedLetterBag(grid: GameRuleGrid, state: State): boolean {
  if (Array.isArray(state.letterBag)) return false
  const available = neededLetters(grid, state.board)
  const normalizedRacks: Record<string, string[]> = { ...state.racks }

  for (const playerId of state.playerIds) {
    normalizedRacks[playerId] = (state.racks[playerId] ?? []).filter(letter => {
      const index = available.indexOf(letter)
      if (index < 0) return false
      available.splice(index, 1)
      return true
    })
  }

  state.racks = normalizedRacks
  state.letterBag = available
  for (const playerId of state.playerIds) state.racks[playerId] = refill(grid, state, playerId, state.racks[playerId] ?? [])
  return true
}

function refill(grid: GameRuleGrid, state: State, playerId: string, current: string[], avoid: Iterable<string> = []): string[] {
  ensureSharedLetterBag(grid, state)
  const drawn = drawRackFromBag({
    letterBag: state.letterBag ?? [], currentLetters: current, avoidLetters: avoid,
    chooseIndex: (pool, position) => hash(`${playerId}:${Object.keys(state.board).length}:${position}:${pool.join('')}`) % pool.length,
  })
  state.letterBag = drawn.letterBag
  return drawn.rack
}

async function profile(admin: ReturnType<typeof createClient>, id: string) {
  const { data } = await admin.from('profiles').select('id,display_name,friend_code,avatar_id,frame_id,animation_id,last_seen,activity').eq('id', id).single()
  return data ? { playerId: data.id, displayName: data.display_name, code: data.friend_code, online: Date.now() - new Date(data.last_seen).getTime() < 30_000, activity: data.activity, avatarId: data.avatar_id, frameId: data.frame_id, animationId: data.animation_id } : null
}

function botUser(bot: Bot) {
  return { playerId: bot.playerId, displayName: bot.displayName, code: `BOT${String(bot.level).padStart(2, '0')}`, online: true, activity: 'playing', avatarId: bot.avatarId, frameId: bot.frameId }
}

async function view(admin: ReturnType<typeof createClient>, row: MatchRow, viewerId: string, grid?: CatalogGrid) {
  const state = row.state
  const players = await Promise.all(state.playerIds.map(id => state.bot?.playerId === id ? botUser(state.bot) : profile(admin, id)))
  return {
    id: row.id, invitationId: state.invitationId, mode: row.mode, pace: row.pace, gridId: row.grid_id,
    difficulty: state.difficulty, playerIds: state.playerIds, bot: state.bot, players: players.filter(Boolean),
    currentPlayerId: row.current_player_id, turnNumber: row.turn_number, turnStartedAt: row.turn_started_at, turnEndsAt: row.turn_ends_at,
    board: state.board, racks: { [viewerId]: state.racks[viewerId] ?? [] }, scores: state.scores,
    productiveTurns: state.productiveTurns, inactivity: state.inactivity,
    hint: state.hint?.playerId === viewerId ? state.hint : null, hintUsed: state.hintUsed, rerollUsed: state.rerollUsed,
    lastTurn: state.lastTurn, status: row.status, winnerId: row.winner_id, finishReason: row.finish_reason,
    createdAt: row.created_at, updatedAt: row.updated_at, ...(grid ? { grid: publicGrid(grid) } : {}),
  }
}

async function getGrid(admin: ReturnType<typeof createClient>, gridId: string): Promise<CatalogGrid> {
  // `active` controls the pool used to create new matches. An already-created
  // match must remain resolvable after a catalogue rotation, otherwise one old
  // match can make the whole lobby fail and hide pending invitations.
  const { data, error } = await admin.from('server_grid_catalog').select('payload').eq('id', gridId).single()
  if (error || !data) throw new Error('Grille introuvable.')
  return data.payload as CatalogGrid
}

async function chooseGrid(admin: ReturnType<typeof createClient>, seed: string, playerIds: string[]): Promise<CatalogGrid> {
  const [{ data: catalogRows }, { data: popularityRows }, { data: cooldownRows }, histories] = await Promise.all([
    admin.from('server_grid_catalog').select('payload').eq('active', true).order('id'),
    admin.from('grid_popularity').select('grid_id,popularity_score,plays'),
    admin.from('server_grid_rotation_cooldowns').select('answer').eq('active', true),
    Promise.all(playerIds.map(async playerId => {
      const { data } = await admin.from('grid_player_history')
        .select('grid_id').eq('user_id', playerId)
        .order('completed_at', { ascending: false }).limit(12)
      return (data ?? []).map(item => item.grid_id as string)
    })),
  ])
  if (!catalogRows?.length) throw new Error('Le catalogue serveur est vide.')
  const grids = catalogRows.map(item => item.payload as CatalogGrid)
  return selectGridForPlayers({
    grids,
    recentGridIdsByPlayer: histories,
    globalCooldownAnswers: (cooldownRows ?? []).map(item => item.answer as string),
    popularity: (popularityRows ?? []).map(item => ({
      gridId: item.grid_id as string,
      score: Number(item.popularity_score) || 60,
      plays: Number(item.plays) || 0,
    })),
    seed,
  }).grid
}

function createBot(seed: string, preferredSkill?: BotSkill): Bot {
  const persona = createBotPersona(seed, preferredSkill)
  // server_matches.current_player_id is a UUID foreign-key shaped column.
  // Bot identities stay internal through state.bot, so a regular UUID is both
  // sufficient to distinguish them and safe to persist when their turn starts.
  return { playerId: crypto.randomUUID(), ...persona }
}

async function playersBlocked(admin: ReturnType<typeof createClient>, firstId: string, secondId: string): Promise<boolean> {
  const { data } = await admin.from('blocks').select('owner_id').or(`and(owner_id.eq.${firstId},blocked_id.eq.${secondId}),and(owner_id.eq.${secondId},blocked_id.eq.${firstId})`).limit(1)
  return Boolean(data?.length)
}

async function createMatch(admin: ReturnType<typeof createClient>, hostId: string, guestId: string, mode: Mode, pace: Pace, invitationId: string | null, bot: Bot | null) {
  const humanPlayerIds = [hostId, guestId].filter(id => id !== bot?.playerId)
  const grid = await chooseGrid(admin, `${hostId}:${guestId}:${Date.now()}`, humanPlayerIds)
  const rules = ruleGrid(grid)
  const startedAt = new Date(Date.now() + READY_MS)
  const endsAt = new Date(startedAt.getTime() + (pace === 'realtime' ? REALTIME_TURN_MS : ASYNC_TURN_MS))
  const state: State = {
    invitationId, difficulty: bot?.skill === 'beginner' ? 'easy' : bot?.skill === 'expert' ? 'hard' : 'normal',
    playerIds: [hostId, guestId], bot, board: {}, racks: {}, letterBag: neededLetters(rules, {}), scores: { [hostId]: 0, [guestId]: 0 },
    productiveTurns: { [hostId]: 0, [guestId]: 0 }, inactivity: { [hostId]: 0, [guestId]: 0 },
    rackCompletions: { [hostId]: 0, [guestId]: 0 },
    hint: null, hintUsed: {}, rerollUsed: {}, lastTurn: null,
  }
  state.racks[hostId] = refill(rules, state, hostId, [])
  state.racks[guestId] = refill(rules, state, guestId, [])
  const { data: row, error } = await admin.from('server_matches').insert({
    mode, pace, grid_id: grid.id, state, status: 'active', current_player_id: hostId,
    turn_number: 1, turn_started_at: startedAt.toISOString(), turn_ends_at: endsAt.toISOString(),
  }).select('*').single()
  if (error || !row) throw error ?? new Error('Création impossible.')
  const participants = [hostId, guestId].filter(id => id !== bot?.playerId).map(user_id => ({ match_id: row.id, user_id, opponent_id: bot ? null : (user_id === hostId ? guestId : hostId) }))
  if (participants.length) await admin.from('match_participants').insert(participants)
  return { row: row as MatchRow, grid }
}

function revealDuration(turn: Turn): number {
  return Math.max(700, (turn.wrongPlacements.length + turn.correct.length + turn.wordBonuses.length + (turn.rackBonus ? 1 : 0)) * REWARD_STEP_MS)
}

function finish(state: State, row: MatchRow, winnerId: string | null, reason: MatchRow['finish_reason']) {
  row.status = 'finished'; row.winner_id = winnerId; row.finish_reason = reason; row.current_player_id = ''
  row.turn_started_at = nowIso(); row.turn_ends_at = row.turn_started_at; state.hint = null
}

function sanitizePlacements(row: MatchRow, grid: CatalogGrid, playerId: string, placements: Array<{ cellIndex: number; letter: string }>) {
  const state = row.state
  const rules = ruleGrid(grid)
  const rack = [...(state.racks[playerId] ?? [])]
  const sanitized: Array<{ cellIndex: number; letter: string }> = []
  const used = new Set<number>()
  for (const placement of placements.slice(0, 5)) {
    const cellIndex = Math.floor(Number(placement.cellIndex))
    const letter = typeof placement.letter === 'string' ? placement.letter.toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').slice(0, 1) : ''
    const rackIndex = rack.indexOf(letter)
    if (!letter || rackIndex < 0 || used.has(cellIndex) || state.board[String(cellIndex)] || rules.cells[cellIndex]?.kind !== 'letter') continue
    rack.splice(rackIndex, 1); used.add(cellIndex); sanitized.push({ cellIndex, letter })
  }
  return { rack, sanitized }
}

function applyTurn(row: MatchRow, grid: CatalogGrid, playerId: string, placements: Array<{ cellIndex: number; letter: string }>): Turn {
  const state = row.state
  const rules = ruleGrid(grid)
  const { sanitized } = sanitizePlacements(row, grid, playerId, placements)
  const aidedCell = state.hint?.playerId === playerId && state.hint.turnNumber === row.turn_number ? state.hint.cellIndex : null
  const evaluated = evaluateTurn({ grid: rules, occupiedBefore: Object.keys(state.board).map(Number), placements: sanitized, aidedCell })
  for (const placement of evaluated.correctPlacements) state.board[String(placement.cellIndex)] = { letter: placement.letter, playerId }
  const correctLetters = new Set(evaluated.correctPlacements.map(item => item.letter))
  const current = keepRackLettersAfterTurn(state.racks[playerId] ?? [], evaluated.correctPlacements)
  state.racks[playerId] = refill(rules, state, playerId, current, correctLetters)
  state.scores[playerId] = (state.scores[playerId] ?? 0) + evaluated.scoreGained
  if (evaluated.productive) state.productiveTurns[playerId] = (state.productiveTurns[playerId] ?? 0) + 1
  if (evaluated.rackBonus) {
    state.rackCompletions ??= {}
    state.rackCompletions[playerId] = (state.rackCompletions[playerId] ?? 0) + 1
  }
  state.inactivity[playerId] = 0
  const turn: Turn = {
    id: crypto.randomUUID(), kind: 'played', playerId, turnNumber: row.turn_number,
    correct: evaluated.correctCells, wrong: evaluated.wrongCells, wrongPlacements: evaluated.wrongPlacements,
    aidedCell, letterPoints: evaluated.letterPoints,
    wordBonuses: evaluated.wordBonuses.map(word => ({ cells: word.cells, points: word.points, direction: word.direction })),
    rackBonus: evaluated.rackBonus, scoreGained: evaluated.scoreGained, inactivityCount: 0, createdAt: nowIso(),
  }
  state.lastTurn = turn; state.hint = null
  if (evaluated.completesGrid) {
    const [left, right] = state.playerIds
    const winner = state.scores[left] === state.scores[right] ? null : state.scores[left] > state.scores[right] ? left : right
    finish(state, row, winner, 'completed')
  } else {
    const opponent = state.playerIds.find(id => id !== playerId)!
    const nextStart = new Date(Date.now() + revealDuration(turn))
    row.current_player_id = opponent; row.turn_number += 1; row.turn_started_at = nextStart.toISOString()
    row.turn_ends_at = new Date(nextStart.getTime() + (row.pace === 'realtime' ? REALTIME_TURN_MS : ASYNC_TURN_MS)).toISOString()
  }
  return turn
}

function timeoutTurn(row: MatchRow) {
  const state = row.state
  const playerId = row.current_player_id
  const inactivity = (state.inactivity[playerId] ?? 0) + 1
  state.inactivity[playerId] = inactivity
  const turn: Turn = { id: crypto.randomUUID(), kind: 'timeout', playerId, turnNumber: row.turn_number, correct: [], wrong: [], wrongPlacements: [], aidedCell: null, letterPoints: 0, wordBonuses: [], rackBonus: 0, scoreGained: 0, inactivityCount: inactivity, createdAt: nowIso() }
  state.lastTurn = turn; state.hint = null
  if (shouldForfeitAfterInactivity(inactivity)) finish(state, row, state.playerIds.find(id => id !== playerId)!, 'timeout')
  else {
    const next = state.playerIds.find(id => id !== playerId)!
    const start = new Date(Date.now() + revealDuration(turn)); row.current_player_id = next; row.turn_number += 1; row.turn_started_at = start.toISOString()
    row.turn_ends_at = new Date(start.getTime() + (row.pace === 'realtime' ? REALTIME_TURN_MS : ASYNC_TURN_MS)).toISOString()
  }
}

function botPlacements(row: MatchRow, grid: CatalogGrid) {
  const state = row.state; const bot = state.bot!; const rules = ruleGrid(grid); const rack = state.racks[bot.playerId] ?? []
  const botScore = state.scores[bot.playerId] ?? 0
  const bestOpponentScore = Math.max(...state.playerIds.filter(id => id !== bot.playerId).map(id => state.scores[id] ?? 0), 0)
  return planBotMove({
    grid: rules,
    occupiedCells: Object.keys(state.board).map(Number),
    rackLetters: rack,
    persona: bot,
    seed: `${row.id}:${row.turn_number}:${rack.join('')}`,
    scoreGap: bestOpponentScore - botScore,
  }).attempts.map(attempt => ({ cellIndex: attempt.cellIndex, letter: attempt.letter }))
}

async function persist(admin: ReturnType<typeof createClient>, row: MatchRow) {
  const updatedAt = nowIso()
  const { data, error } = await admin.from('server_matches').update({
    state: row.state, status: row.status, current_player_id: row.current_player_id || null, turn_number: row.turn_number,
    turn_started_at: row.turn_started_at, turn_ends_at: row.turn_ends_at, winner_id: row.winner_id,
    finish_reason: row.finish_reason, updated_at: updatedAt,
  }).eq('id', row.id).eq('updated_at', row.updated_at).select('*').maybeSingle()
  if (error) throw error
  if (!data) throw new Error('La partie a changé sur un autre appareil. Actualisez-la.')
  return data as MatchRow
}

function playerOutcome(row: MatchRow, playerId: string) {
  const won = row.winner_id === playerId
  const interrupted = row.finish_reason === 'forfeit' || row.finish_reason === 'timeout'
  return interrupted ? won ? 'opponent-abandoned' : 'abandon' : row.winner_id === null ? 'draw' : won ? 'win' : 'loss'
}

async function recordMatchHistory(admin: ReturnType<typeof createClient>, row: MatchRow, playerId: string) {
  if (row.status !== 'finished' || playerId === row.state.bot?.playerId) return
  const opponentId = row.state.playerIds.find(id => id !== playerId) ?? ''
  const opponentName = row.state.bot?.playerId === opponentId
    ? row.state.bot.displayName
    : (await profile(admin, opponentId))?.displayName ?? null
  const { error } = await admin.from('grid_player_history').upsert({
    user_id: playerId,
    play_key: `match:${row.id}`,
    match_id: row.id,
    grid_id: row.grid_id,
    mode: row.mode === 'solo' ? 'solo' : 'multiplayer',
    pace: row.pace,
    outcome: playerOutcome(row, playerId),
    completed: row.finish_reason === 'completed',
    score: Math.max(0, row.state.scores[playerId] ?? 0),
    opponent_score: Math.max(0, row.state.scores[opponentId] ?? 0),
    opponent_name: opponentName,
    duration_seconds: Math.max(0, Math.round((new Date(row.updated_at).getTime() - new Date(row.created_at).getTime()) / 1000)),
    completed_at: row.updated_at,
    updated_at: nowIso(),
  }, { onConflict: 'user_id,play_key' })
  if (error) throw error
  await admin.from('match_participants').update({
    score: Math.max(0, row.state.scores[playerId] ?? 0),
    inactivity_count: Math.max(0, row.state.inactivity[playerId] ?? 0),
  }).eq('match_id', row.id).eq('user_id', playerId)
}

async function awardFinished(admin: ReturnType<typeof createClient>, row: MatchRow) {
  if (row.status !== 'finished') return
  for (const playerId of row.state.playerIds) {
    if (playerId === row.state.bot?.playerId) continue
    await recordMatchHistory(admin, row, playerId)
    const outcome = playerOutcome(row, playerId)
    const solo = row.mode === 'solo'
    const productiveTurns = row.state.productiveTurns[playerId] ?? 0
    const totalProductiveTurns = Object.entries(row.state.productiveTurns)
      .filter(([id]) => id !== row.state.bot?.playerId)
      .reduce((total, [, turns]) => total + Math.max(0, turns), 0)
    const feathers = calculateFeatherReward({
      mode: solo ? 'solo' : 'multiplayer', outcome, totalProductiveTurns,
      hintUsed: Boolean(row.state.hintUsed[playerId]),
      rerollUsed: Boolean(row.state.rerollUsed[playerId]),
      rackCompletions: row.state.rackCompletions?.[playerId] ?? 0,
    })
    await admin.rpc('server_award_progress', {
      p_user_id: playerId,
      p_idempotency_key: `match:${row.id}`,
      p_mode: solo ? 'solo' : 'multiplayer',
      p_outcome: outcome,
      p_productive_turns: productiveTurns,
      p_feather_amount: feathers.total,
      p_feather_breakdown: feathers,
    })
  }
}

Deno.serve(async request => {
  if (request.method === 'OPTIONS') return new Response('ok', { headers: cors })
  if (request.method !== 'POST') return json(405, { error: 'Méthode non autorisée.' })
  const authorization = request.headers.get('Authorization') ?? ''
  const url = Deno.env.get('SUPABASE_URL')!
  const authClient = createClient(url, Deno.env.get('SUPABASE_ANON_KEY')!, { global: { headers: { Authorization: authorization } }, auth: { persistSession: false } })
  const { data: { user } } = await authClient.auth.getUser(authorization.replace(/^Bearer\s+/i, ''))
  if (!user) return json(401, { error: 'Session invalide.' })
  const admin = createClient(url, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!, { auth: { persistSession: false, autoRefreshToken: false } })
  const { data: accessProfile } = await admin.from('profiles').select('status').eq('id', user.id).single()
  if (accessProfile?.status === 'banned') return json(403, { error: 'Ce compte a été banni.' })
  if (accessProfile?.status === 'suspended') return json(403, { error: 'Ce compte est temporairement suspendu.' })
  let body: Record<string, unknown>
  try { body = await request.json() } catch { return json(400, { error: 'Requête invalide.' }) }
  const action = typeof body.action === 'string' ? body.action : 'state'

  try {
    const activeRows = async () => {
      const { data: participants } = await admin.from('match_participants').select('match_id').eq('user_id', user.id)
      const ids = (participants ?? []).map(item => item.match_id)
      if (!ids.length) return [] as MatchRow[]
      const { data } = await admin.from('server_matches').select('*').in('id', ids).eq('status', 'active').order('updated_at', { ascending: false })
      return (data ?? []) as MatchRow[]
    }

    const resolveRow = async (row: MatchRow) => {
      if (row.status !== 'active') return row
      const grid = await getGrid(admin, row.grid_id)
      const initializedBag = ensureSharedLetterBag(ruleGrid(grid), row.state)
      if (row.state.bot?.playerId === row.current_player_id) {
        const delay = botThinkingDelayMs(`${row.id}:${row.turn_number}`)
        if (Date.now() >= new Date(row.turn_started_at).getTime() + delay) {
          applyTurn(row, grid, row.current_player_id, botPlacements(row, grid)); row = await persist(admin, row); await awardFinished(admin, row)
        }
      } else if (Date.now() >= new Date(row.turn_ends_at).getTime() + GRACE_MS) {
        timeoutTurn(row); row = await persist(admin, row); await awardFinished(admin, row)
      } else if (initializedBag) row = await persist(admin, row)
      return row
    }

    const lobby = async () => {
      let rows = await activeRows(); rows = await Promise.all(rows.map(resolveRow))
      const { data: incomingRows } = await admin.from('server_match_invitations').select('*').eq('guest_id', user.id).eq('status', 'pending').gt('expires_at', nowIso())
      const { data: outgoingRows } = await admin.from('server_match_invitations').select('*').eq('host_id', user.id).eq('status', 'pending').gt('expires_at', nowIso())
      const invitationView = async (item: Record<string, unknown>) => ({ id: item.id, hostId: item.host_id, guestId: item.guest_id, pace: item.pace, createdAt: item.created_at, expiresAt: item.expires_at, status: item.status, matchId: item.match_id, host: await profile(admin, String(item.host_id)), guest: await profile(admin, String(item.guest_id)) })
      const { data: searches } = await admin.from('server_match_searches').select('*').eq('user_id', user.id)
      const { data: recentRows, error: recentError } = await admin.from('grid_player_history')
        .select('id,mode,pace,outcome,score,opponent_score,opponent_name,completed_at')
        .eq('user_id', user.id).order('completed_at', { ascending: false }).limit(5)
      if (recentError) throw recentError
      const recent = (recentRows ?? []).map(item => ({
        id: item.id, mode: item.mode, pace: item.pace, outcome: item.outcome,
        score: item.score, opponentScore: item.opponent_score,
        opponentName: item.opponent_name, completedAt: item.completed_at,
      }))
      return { incoming: await Promise.all((incomingRows ?? []).map(invitationView)), outgoing: await Promise.all((outgoingRows ?? []).map(invitationView)), active: await Promise.all(rows.map(row => view(admin, row, user.id))), searches: (searches ?? []).map(item => ({ id: item.id, pace: item.pace, createdAt: item.created_at })), recent }
    }

    if (action === 'state') {
      const { data: searches } = await admin.from('server_match_searches').select('*').eq('user_id', user.id)
      for (const search of searches ?? []) if (Date.now() - new Date(search.created_at).getTime() >= BOT_SEARCH_MS) {
        const bot = createBot(`${user.id}:${search.id}`)
        await createMatch(admin, user.id, bot.playerId, 'normal', search.pace, null, bot)
        await admin.from('server_match_searches').delete().eq('id', search.id)
      }
      return json(200, await lobby())
    }

    if (action === 'solo') {
      const pace: Pace = body.pace === 'async' ? 'async' : 'realtime'
      const skill: BotSkill = body.difficulty === 'easy' ? 'beginner' : body.difficulty === 'hard' ? 'expert' : 'regular'
      const bot = createBot(`${user.id}:solo:${Date.now()}`, skill)
      const created = await createMatch(admin, user.id, bot.playerId, 'solo', pace, null, bot)
      return json(200, { match: await view(admin, created.row, user.id, created.grid) })
    }

    if (action === 'create') {
      const targetId = typeof body.targetId === 'string' ? body.targetId : ''
      const pace: Pace = body.pace === 'async' ? 'async' : 'realtime'
      const [left, right] = [user.id, targetId].sort()
      if (await playersBlocked(admin, user.id, targetId)) return json(409, { error: 'Cette invitation ne peut pas être envoyée.' })
      const { data: friendship } = await admin.from('friendships').select('left_user_id').eq('left_user_id', left).eq('right_user_id', right).maybeSingle()
      if (!friendship) return json(403, { error: 'Ce joueur n’est pas dans vos amis.' })
      await admin.from('server_match_invitations').insert({ host_id: user.id, guest_id: targetId, pace, expires_at: new Date(Date.now() + (pace === 'async' ? 7 * 86400000 : 120000)).toISOString() })
      return json(200, await lobby())
    }

    if (action === 'respond') {
      const invitationId = typeof body.invitationId === 'string' ? body.invitationId : ''
      const { data: invitation } = await admin.from('server_match_invitations').select('*').eq('id', invitationId).eq('guest_id', user.id).eq('status', 'pending').single()
      if (!invitation) return json(404, { error: 'Invitation expirée.' })
      if (body.decision === 'accept') {
        const created = await createMatch(admin, invitation.host_id, user.id, 'friend', invitation.pace, invitation.id, null)
        await admin.from('server_match_invitations').update({ status: 'accepted', match_id: created.row.id }).eq('id', invitation.id)
      } else await admin.from('server_match_invitations').update({ status: 'declined' }).eq('id', invitation.id)
      return json(200, await lobby())
    }

    if (action === 'cancel') {
      await admin.from('server_match_invitations').update({ status: 'cancelled' }).eq('id', String(body.invitationId ?? '')).eq('host_id', user.id).eq('status', 'pending')
      return json(200, await lobby())
    }

    if (action === 'search' || action === 'search-cancel') {
      const pace: Pace = body.pace === 'async' ? 'async' : 'realtime'
      if (action === 'search-cancel') {
        await admin.from('server_match_searches').delete().eq('user_id', user.id).eq('pace', pace)
        return json(200, { lobby: await lobby(), matchId: null })
      }
      const { data: candidates } = await admin.from('server_match_searches').select('*').eq('pace', pace).neq('user_id', user.id).order('created_at').limit(20)
      let other: Record<string, unknown> | null = null
      for (const candidate of candidates ?? []) {
        if (!await playersBlocked(admin, user.id, String(candidate.user_id))) { other = candidate; break }
      }
      let matchId: string | null = null
      if (other) {
        const created = await createMatch(admin, String(other.user_id), user.id, 'normal', pace, null, null); matchId = created.row.id
        await admin.from('server_match_searches').delete().in('id', [String(other.id)])
      } else await admin.from('server_match_searches').upsert({ user_id: user.id, pace, updated_at: nowIso() }, { onConflict: 'user_id,pace' })
      return json(200, { lobby: await lobby(), matchId })
    }

    const matchId = typeof body.matchId === 'string' ? body.matchId : ''
    const { data: participant } = await admin.from('match_participants').select('match_id').eq('match_id', matchId).eq('user_id', user.id).maybeSingle()
    if (!participant) return json(404, { error: 'Partie introuvable.' })
    const { data: found } = await admin.from('server_matches').select('*').eq('id', matchId).single()
    if (!found) return json(404, { error: 'Partie introuvable.' })
    let row = await resolveRow(found as MatchRow)
    const grid = await getGrid(admin, row.grid_id)
    if (action === 'feedback') {
      if (row.status !== 'finished') return json(409, { error: 'La partie doit être terminée avant de noter sa grille.' })
      const quality = body.quality === 'yes' ? 1 : body.quality === 'no' ? -1 : 0
      if (!quality) return json(400, { error: 'Avis invalide.' })
      const reason = typeof body.reason === 'string' ? body.reason.trim().slice(0, 120) : ''
      await recordMatchHistory(admin, row, user.id)
      const { error: feedbackError } = await admin.from('grid_player_history').update({
        feedback: quality,
        feedback_reason: reason || null,
        feedback_at: nowIso(),
        updated_at: nowIso(),
      }).eq('user_id', user.id).eq('play_key', `match:${row.id}`)
      if (feedbackError) throw feedbackError
      const { data: popularity } = await admin.from('grid_popularity')
        .select('plays,completions,positive_reviews,negative_reviews,popularity_score')
        .eq('grid_id', row.grid_id).maybeSingle()
      return json(200, { recorded: true, popularity })
    }
    if (action === 'match') {
      if (body.knownUpdatedAt === row.updated_at) return json(200, { unchanged: true })
      return json(200, { match: await view(admin, row, user.id, grid) })
    }
    if (action === 'turn' && row.state.lastTurn?.playerId === user.id && row.state.lastTurn.turnNumber === Number(body.turnNumber)) {
      return json(200, { match: await view(admin, row, user.id, grid), result: row.state.lastTurn })
    }
    if (row.status !== 'active') return json(200, { match: await view(admin, row, user.id, grid) })
    if (action === 'forfeit') {
      finish(row.state, row, row.state.playerIds.find(id => id !== user.id)!, 'forfeit')
      row = await persist(admin, row); await awardFinished(admin, row)
      return json(200, { match: await view(admin, row, user.id, grid) })
    }
    if (row.current_player_id !== user.id) return json(409, { error: 'Ce n’est pas votre tour.', match: await view(admin, row, user.id, grid) })
    if (Date.now() < new Date(row.turn_started_at).getTime()) return json(409, { error: 'Le tour n’a pas encore commencé.' })

    if (action === 'turn') {
      if (Number(body.turnNumber) !== row.turn_number) return json(409, { error: 'Ce tour est déjà terminé.', match: await view(admin, row, user.id, grid) })
      const placements = Array.isArray(body.placements) ? body.placements as Array<{ cellIndex: number; letter: string }> : []
      const valid = sanitizePlacements(row, grid, user.id, placements).sanitized
      const hasPlacedHint = row.state.hint?.playerId === user.id && row.state.hint.turnNumber === row.turn_number
      if (Date.now() >= new Date(row.turn_ends_at).getTime() + GRACE_MS || body.automatic === true && valid.length === 0 && !hasPlacedHint) timeoutTurn(row)
      else applyTurn(row, grid, user.id, valid)
    } else if (action === 'hint') {
      if (!canUseHint(Boolean(row.state.hintUsed[user.id]))) return json(409, { error: 'Votre indice a déjà été utilisé.' })
      const candidates = hintCandidates(ruleGrid(grid), row.state.racks[user.id] ?? [], Object.keys(row.state.board).map(Number))
      if (!candidates.length) return json(409, { error: 'Aucun indice disponible.' })
      const chosen = candidates[hash(`${row.id}:${row.turn_number}:hint`) % candidates.length]
      row.state.hint = { playerId: user.id, cellIndex: chosen.cellIndex, letter: chosen.letter, turnNumber: row.turn_number }
      row.state.hintUsed[user.id] = true
      row.state.board[String(chosen.cellIndex)] = { letter: chosen.letter, playerId: user.id }
      const rack = row.state.racks[user.id] ?? []
      const hintedLetterIndex = rack.indexOf(chosen.letter)
      row.state.racks[user.id] = hintedLetterIndex < 0 ? rack : rack.filter((_, index) => index !== hintedLetterIndex)
      if (neededLetters(ruleGrid(grid), row.state.board).length === 0) {
        const [left, right] = row.state.playerIds
        const winner = row.state.scores[left] === row.state.scores[right] ? null : row.state.scores[left] > row.state.scores[right] ? left : right
        finish(row.state, row, winner, 'completed')
      }
    } else if (action === 'reroll') {
      if (!canUseReroll({ alreadyUsed: Boolean(row.state.rerollUsed[user.id]), pendingPlacements: 0, hintActive: Boolean(row.state.hint) })) return json(409, { error: 'Le mélange n’est plus disponible.' })
      const currentRack = row.state.racks[user.id] ?? []
      row.state.letterBag = [...(row.state.letterBag ?? []), ...currentRack]
      row.state.rerollUsed[user.id] = true; row.state.racks[user.id] = refill(ruleGrid(grid), row.state, user.id, [], currentRack)
    } else return json(404, { error: 'Action inconnue.' })
    row = await persist(admin, row); await awardFinished(admin, row)
    const result = row.state.lastTurn
    return json(200, action === 'turn' ? { match: await view(admin, row, user.id, grid), result } : { match: await view(admin, row, user.id, grid) })
  } catch (error) {
    console.error(error)
    return json(500, { error: error instanceof Error ? error.message : 'Erreur de partie.' })
  }
})
