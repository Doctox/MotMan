import { randomUUID } from 'node:crypto'
import type { IncomingMessage, ServerResponse } from 'node:http'
import {
  canUseHint, canUseReroll, hasTurnStarted, hintCandidates, isTurnSubmissionExpired, shouldForfeitAfterInactivity,
} from '../../src/gameRules'
import {
  ASYNC_INVITATION_DURATION_MS, INVITATION_DURATION_MS, MAX_ASYNC_MATCHES,
  REALTIME_SEARCH_STALE_MS, TURN_SUBMIT_GRACE_MS,
} from './config'
import { gridSolution, hash, ruleGrid } from './gridCatalog'
import { readBody, sendJson, sendNoContent } from './http'
import type { BotProfile, CatalogGrid, MatchDatabase, MatchMode, MatchPace, StoredMatch, StoredTurn } from './types'

type PublicPlayer = { displayName: string; online: boolean }

export type MatchRequestContext = {
  database: MatchDatabase
  cleanPlayerId(value: unknown): string
  publicUser(playerId: string): PublicPlayer | null
  areFriends(left: string, right: string): boolean
  activeMatches(playerId: string, pace?: MatchPace): StoredMatch[]
  resolveExpired(): void
  lobbyState(playerId: string): unknown
  ensureFinalSprintRacks(match: StoredMatch): boolean
  publicMatch(match: StoredMatch): unknown
  saveDatabase(): void
  createMatch(hostId: string, guestId: string, mode: MatchMode, pace: MatchPace, sourceId: string, invitationId?: string | null, bot?: BotProfile | null): StoredMatch
  finishMatch(match: StoredMatch, winnerId: string | null, reason: StoredMatch['finishReason']): void
  gridForMatch(match: StoredMatch): CatalogGrid
  replenishRack(match: StoredMatch, playerId: string, current: string[], avoidLetters?: Iterable<string>): string[]
  sanitizePlacements(match: StoredMatch, playerId: string, placements: unknown[]): Array<{ cellIndex: number; letter: string }>
  startNextTurn(match: StoredMatch, completedAt: Date, turn: StoredTurn): void
  applyPlayedTurn(match: StoredMatch, playerId: string, placements: Array<{ cellIndex: number; letter: string }>): StoredTurn
}

export async function handleMatchRequest(request: IncomingMessage, response: ServerResponse, context: MatchRequestContext): Promise<void> {
  const {
    database, cleanPlayerId, publicUser, areFriends, activeMatches, resolveExpired, lobbyState,
    ensureFinalSprintRacks, publicMatch, saveDatabase, createMatch, finishMatch, gridForMatch,
    replenishRack, sanitizePlacements, startNextTurn, applyPlayedTurn,
  } = context
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
    if (ensureFinalSprintRacks(match)) {
      match.updatedAt = new Date().toISOString()
      saveDatabase()
    }
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
  if (ensureFinalSprintRacks(match)) {
    match.updatedAt = new Date().toISOString()
    saveDatabase()
  }
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
    } else ensureFinalSprintRacks(match)
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
    match.letterBag = [...(match.letterBag ?? []), ...currentRack]
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
