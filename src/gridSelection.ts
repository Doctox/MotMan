export type SelectionGrid = {
  id: string
  words: Array<{ answer: string }>
}

export type GridPopularity = {
  gridId: string
  score: number
  plays?: number
}

export type GridSelectionResult<T extends SelectionGrid> = {
  grid: T
  recentGridIds: string[]
  repeatedAnswersOnCooldown: string[]
  overlapCount: number
}

export type ActiveGridClaim = { id: string; createdAt: string }

export const RECENT_GRID_AVOIDANCE_LIMIT = 5

export function shouldYieldActiveGridClaim(current: ActiveGridClaim, competing: readonly ActiveGridClaim[]): boolean {
  const currentTime = Date.parse(current.createdAt)
  return competing.some(other => {
    const otherTime = Date.parse(other.createdAt)
    if (Number.isFinite(currentTime) && Number.isFinite(otherTime) && currentTime !== otherTime) return otherTime < currentTime
    return `${other.createdAt}:${other.id}` < `${current.createdAt}:${current.id}`
  })
}

function normalizeAnswer(answer: string): string {
  return answer.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().trim()
}

function stableHash(value: string): number {
  let hash = 2166136261
  for (const character of value) {
    hash ^= character.charCodeAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function answerSet(grid: SelectionGrid): Set<string> {
  return new Set(grid.words.map(word => normalizeAnswer(word.answer)).filter(Boolean))
}

/**
 * Selects a random grid while avoiding each human player's latest five plays.
 *
 * Editorial validation happens before publication. Runtime answer cooldowns,
 * popularity and feedback must therefore never remove a published grid from
 * the playable pool.
 */
export function selectGridForPlayers<T extends SelectionGrid>({
  grids,
  recentGridIdsByPlayer,
  activeGridIds = [],
  seed,
}: {
  grids: readonly T[]
  recentGridIdsByPlayer: readonly (readonly string[])[]
  activeGridIds?: readonly string[]
  globalCooldownAnswers?: Iterable<string>
  popularity?: readonly GridPopularity[]
  seed: string
}): GridSelectionResult<T> {
  if (!grids.length) throw new Error('Le catalogue de grilles est vide.')

  const byId = new Map(grids.map(grid => [grid.id, grid]))
  const recentGroups = recentGridIdsByPlayer.map(ids => [...ids].slice(0, RECENT_GRID_AVOIDANCE_LIMIT))
  const recentGridIds = [...new Set(recentGroups.flat())]
  const recentIdSet = new Set(recentGridIds)
  const recentAnswerFrequency = new Map<string, number>()

  for (const ids of recentGroups) {
    for (const gridId of ids) {
      const grid = byId.get(gridId)
      if (!grid) continue
      for (const answer of answerSet(grid)) {
        recentAnswerFrequency.set(answer, (recentAnswerFrequency.get(answer) ?? 0) + 1)
      }
    }
  }

  const repeatedAnswersOnCooldown = [...recentAnswerFrequency]
    .filter(([, uses]) => uses >= 2)
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([answer]) => answer)
  // Do not expose the same board in concurrent matches involving either
  // player. Falling back to an occupied grid is allowed only when every grid
  // in the catalogue is already occupied for the participants.
  const activeIdSet = new Set(activeGridIds)
  const unoccupied = grids.filter(grid => !activeIdSet.has(grid.id))
  const occupancyPool = unoccupied.length ? unoccupied : [...grids]
  const fresh = occupancyPool.filter(grid => !recentIdSet.has(grid.id))
  const pool = fresh.length ? fresh : occupancyPool
  const grid = pool[stableHash(seed) % pool.length]
  let overlapCount = 0
  for (const answer of answerSet(grid)) {
    if ((recentAnswerFrequency.get(answer) ?? 0) > 0) overlapCount += 1
  }

  return {
    grid,
    recentGridIds,
    repeatedAnswersOnCooldown,
    overlapCount,
  }
}
