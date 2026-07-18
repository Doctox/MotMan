import { expect, request as playwrightRequest, test, type APIRequestContext, type Browser, type BrowserContext, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

type Identity = {
  version: 1
  playerId: string
  displayName: string
  accountType: 'guest'
  createdAt: string
}

type CatalogGrid = {
  id: string
  size?: number
  columns?: number
  rows?: number
  words: Array<{ answer: string; cells: number[][] }>
}

type MatchState = {
  id: string
  gridId: string
  pace: 'realtime' | 'async'
  playerIds: [string, string]
  currentPlayerId: string
  turnNumber: number
  turnStartedAt: string
  turnEndsAt: string
  board: Record<string, { letter: string; playerId: string }>
  racks: Record<string, string[]>
  scores: Record<string, number>
  inactivity: Record<string, number>
  lastTurn: null | { id: string; playerId: string; turnNumber: number; correct: number[] }
  status: 'active' | 'finished'
  winnerId: string | null
  finishReason: 'completed' | 'timeout' | 'forfeit' | null
  updatedAt: string
}

const catalog = JSON.parse(readFileSync(resolve('src/data/runtime.grid.catalog.json'), 'utf8')) as { grids: CatalogGrid[] }
let identitySequence = 0

function newIdentity(label: string): Identity {
  identitySequence += 1
  return {
    version: 1,
    playerId: `guest_${randomUUID()}`,
    displayName: `${label} ${identitySequence}`,
    accountType: 'guest',
    createdAt: new Date().toISOString(),
  }
}

async function register(request: APIRequestContext, identity: Identity): Promise<void> {
  void request
  const isolated = await playwrightRequest.newContext({
    baseURL: 'http://127.0.0.1:4175',
    extraHTTPHeaders: { Origin: 'http://127.0.0.1:4175' },
  })
  const bootstrap = await isolated.post('/api/auth/bootstrap', { data: { identity } })
  expect(bootstrap.ok()).toBe(true)
  const response = await isolated.post('/api/social/register', {
    data: {
      displayName: identity.displayName,
      avatarId: 'plume-originelle',
      frameId: 'cadre-ivoire',
      animationId: 'aucune',
    },
  })
  expect(response.ok()).toBe(true)
  await isolated.dispose()
}

async function createNormalMatch(request: APIRequestContext, pace: 'realtime' | 'async', label: string) {
  const first = newIdentity(`${label} A`)
  await register(request, first)
  const second = newIdentity(`${label} B`)
  await register(request, second)

  const waiting = await request.post('/api/matches/search', { data: { playerId: first.playerId, pace } })
  if (!waiting.ok()) throw new Error(`Première recherche refusée (${waiting.status()}) : ${await waiting.text()}`)
  const paired = await request.post('/api/matches/search', { data: { playerId: second.playerId, pace } })
  if (!paired.ok()) throw new Error(`Seconde recherche refusée (${paired.status()}) : ${await paired.text()}`)
  const payload = await paired.json() as { matchId: string | null }
  expect(payload.matchId).toBeTruthy()
  return { first, second, matchId: String(payload.matchId) }
}

async function loadMatch(request: APIRequestContext, playerId: string, matchId: string): Promise<MatchState> {
  const url = `/api/matches/match/${encodeURIComponent(matchId)}?playerId=${encodeURIComponent(playerId)}`
  let lastError: unknown
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const response = await request.get(url)
      expect(response.ok()).toBe(true)
      return response.json() as Promise<MatchState>
    } catch (error) {
      lastError = error
      if (attempt < 2) await new Promise(resolvePromise => setTimeout(resolvePromise, 150 * (attempt + 1)))
    }
  }
  throw lastError
}

function solutionFor(gridId: string): Map<number, string> {
  const grid = catalog.grids.find(candidate => candidate.id === gridId)
  if (!grid) throw new Error(`Grille ${gridId} introuvable dans le catalogue de test`)
  const columns = grid.columns ?? grid.size
  if (!columns) throw new Error(`Dimensions absentes pour ${grid.id}`)
  const solution = new Map<number, string>()
  grid.words.forEach(word => word.cells.forEach(([row, column], offset) => solution.set(row * columns + column, word.answer[offset])))
  return solution
}

function playablePlacements(match: MatchState): Array<{ cellIndex: number; letter: string }> {
  const solution = solutionFor(match.gridId)
  const occupied = new Set(Object.keys(match.board).map(Number))
  const usedCells = new Set<number>()
  return (match.racks[match.currentPlayerId] ?? []).flatMap(letter => {
    const cellIndex = [...solution.entries()].find(([index, expected]) => expected === letter && !occupied.has(index) && !usedCells.has(index))?.[0]
    if (cellIndex === undefined) return []
    usedCells.add(cellIndex)
    return [{ cellIndex, letter }]
  })
}

async function submitTurn(request: APIRequestContext, match: MatchState, placements: Array<{ cellIndex: number; letter: string }>, automatic = false) {
  const waitForStart = new Date(match.turnStartedAt).getTime() + 10 - Date.now()
  if (waitForStart > 0) await new Promise(resolvePromise => setTimeout(resolvePromise, waitForStart))
  const response = await request.post('/api/matches/turn', {
    data: { playerId: match.currentPlayerId, matchId: match.id, turnNumber: match.turnNumber, placements, automatic },
  })
  expect(response.ok()).toBe(true)
  return response.json() as Promise<{ match: MatchState; result: NonNullable<MatchState['lastTurn']> }>
}

async function openGame(browser: Browser, identity: Identity, matchId: string, viewport: { width: number; height: number }, expectBoard = true): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport })
  await context.addInitScript(storedIdentity => {
    localStorage.setItem('motman-player-v1', JSON.stringify(storedIdentity))
  }, identity)
  const page = await context.newPage()
  await page.goto(`/#partie=${encodeURIComponent(matchId)}`)
  if (expectBoard) await expect(page.locator('.board')).toBeVisible()
  return { context, page }
}

test('un sondage inchangé ne renvoie pas à nouveau toute la partie', async ({ request, browserName }) => {
  test.skip(browserName === 'webkit', 'Le contrat HTTP est indépendant du moteur visuel.')
  const { first, matchId } = await createNormalMatch(request, 'async', 'Sondage')
  const initial = await loadMatch(request, first.playerId, matchId)
  const unchanged = await request.get(`/api/matches/match/${encodeURIComponent(matchId)}?playerId=${encodeURIComponent(first.playerId)}&since=${encodeURIComponent(initial.updatedAt)}`)

  expect(unchanged.status()).toBe(204)
  expect(await unchanged.body()).toHaveLength(0)
})

test('deux téléphones conservent la même lettre après validation', async ({ browser, request }) => {
  const { first, second, matchId } = await createNormalMatch(request, 'realtime', 'Synchro')
  const initial = await loadMatch(request, first.playerId, matchId)
  const placement = playablePlacements(initial)[0]
  expect(placement).toBeTruthy()

  const [playerOne, playerTwo] = await Promise.all([
    openGame(browser, first, matchId, { width: 390, height: 844 }),
    openGame(browser, second, matchId, { width: 393, height: 852 }),
  ])
  try {
    await expect(playerOne.page.locator('.turn-ready-flash')).toBeVisible()
    await expect(playerOne.page.locator('.turn-ready-flash')).toBeHidden()
    await playerOne.page.getByRole('button', { name: `Lettre ${placement.letter}` }).click({ force: true })
    await playerOne.page.locator(`[data-cell="${placement.cellIndex}"]`).click({ force: true })
    await playerOne.page.getByRole('button', { name: 'Valider' }).click({ force: true })

    const confirmedOne = playerOne.page.locator(`[data-cell="${placement.cellIndex}"][data-confirmed="true"]`)
    const confirmedTwo = playerTwo.page.locator(`[data-cell="${placement.cellIndex}"][data-confirmed="true"]`)
    await expect(confirmedOne).toBeVisible()
    await expect(confirmedTwo).toBeVisible()
    await expect(confirmedOne).toContainText(placement.letter)
    await expect(confirmedTwo).toContainText(placement.letter)

    const synchronized = await loadMatch(request, second.playerId, matchId)
    expect(synchronized.board[placement.cellIndex]?.letter).toBe(placement.letter)
    // On WebKit, the deliberately shortened test clock can already have moved
    // to the following timeout while both phones animate the confirmation.
    // The durable board cell is the synchronization contract under test.
  } finally {
    await playerOne.context.close()
    await playerTwo.context.close()
  }
})

test('les réponses à 2 s, 1 s et 0 s sont acceptées, sans double validation', async ({ request, browserName }) => {
  test.skip(browserName === 'webkit', 'La frontière temporelle est une règle serveur indépendante du moteur visuel.')
  const { first, matchId } = await createNormalMatch(request, 'realtime', 'Limite')
  let match = await loadMatch(request, first.playerId, matchId)

  for (const remainingSeconds of [2, 1, 0]) {
    const turn = match
    const placement = playablePlacements(turn)[0]
    expect(placement).toBeTruthy()
    const target = new Date(turn.turnEndsAt).getTime() - remainingSeconds * 1_000 + (remainingSeconds === 0 ? 250 : 0)
    const wait = target - Date.now()
    if (wait > 0) await new Promise(resolvePromise => setTimeout(resolvePromise, wait))

    const accepted = await submitTurn(request, turn, [placement])
    expect(accepted.result.correct).toContain(placement.cellIndex)
    match = accepted.match

    if (remainingSeconds === 0) {
      const duplicate = await request.post('/api/matches/turn', {
        data: { playerId: turn.currentPlayerId, matchId, turnNumber: turn.turnNumber, placements: [placement], automatic: false },
      })
      expect(duplicate.ok()).toBe(true)
      const duplicatePayload = await duplicate.json() as { match: MatchState; result: NonNullable<MatchState['lastTurn']> }
      expect(duplicatePayload.result.id).toBe(accepted.result.id)
      expect(duplicatePayload.match.scores).toEqual(accepted.match.scores)
    }
  }
})

test('temps limité et illimité demandent trois absences avant la défaite', async ({ request, browserName }) => {
  test.skip(browserName === 'webkit', 'La règle d’inactivité est couverte une fois au niveau serveur.')
  for (const pace of ['realtime', 'async'] as const) {
    const { first, matchId } = await createNormalMatch(request, pace, pace === 'realtime' ? 'Abs RT' : 'Abs IL')
    let match = await loadMatch(request, first.playerId, matchId)
    const inactivePlayer = match.currentPlayerId

    for (let miss = 1; miss <= 3; miss += 1) {
      const timeout = await submitTurn(request, match, [], true)
      match = timeout.match
      expect(match.inactivity[inactivePlayer]).toBe(miss)
      if (miss < 3) {
        expect(match.status).toBe('active')
        const opponentPass = await submitTurn(request, match, [], false)
        match = opponentPass.match
        expect(match.currentPlayerId).toBe(inactivePlayer)
      }
    }

    expect(match.status).toBe('finished')
    expect(match.finishReason).toBe('timeout')
    expect(match.winnerId).not.toBe(inactivePlayer)
  }
})

test('une grille complète atteint l’écran final', async ({ browser, request }) => {
  const { first, matchId } = await createNormalMatch(request, 'realtime', 'Complète')
  let match = await loadMatch(request, first.playerId, matchId)

  for (let turn = 0; turn < 40 && match.status === 'active'; turn += 1) {
    const placements = playablePlacements(match)
    expect(placements.length).toBeGreaterThan(0)
    match = (await submitTurn(request, match, placements)).match
  }

  expect(match.status).toBe('finished')
  expect(match.finishReason).toBe('completed')
  const result = await openGame(browser, first, matchId, { width: 390, height: 844 }, false)
  try {
    await expect(result.page.locator('.game-result-screen')).toBeVisible()
    await expect(result.page.getByRole('button', { name: 'Nouvelle partie' })).toBeVisible()
    await expect(result.page.getByRole('button', { name: /Retour à l’accueil/ })).toBeVisible()
  } finally {
    await result.context.close()
  }
})
