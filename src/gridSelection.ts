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
 * Selects a grid against each human player's latest twelve plays.
 *
 * A response seen at least twice enters a personal cooldown. A candidate
 * containing one of those responses is excluded while a clean alternative
 * exists. Global editorial cooldowns follow the same temporary rule: they
 * are blocked while at least one fresh clean grid remains, then become a
 * strong penalty so a small catalogue can never deadlock.
 */
export function selectGridForPlayers<T extends SelectionGrid>({
  grids,
  recentGridIdsByPlayer,
  globalCooldownAnswers = [],
  popularity = [],
  seed,
}: {
  grids: readonly T[]
  recentGridIdsByPlayer: readonly (readonly string[])[]
  globalCooldownAnswers?: Iterable<string>
  popularity?: readonly GridPopularity[]
  seed: string
}): GridSelectionResult<T> {
  if (!grids.length) throw new Error('Le catalogue de grilles est vide.')

  const byId = new Map(grids.map(grid => [grid.id, grid]))
  const recentGroups = recentGridIdsByPlayer.map(ids => [...ids].slice(0, 12))
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
  const repeatedSet = new Set(repeatedAnswersOnCooldown)
  const globalSet = new Set([...globalCooldownAnswers].map(normalizeAnswer))
  const popularityById = new Map(popularity.map(item => [item.gridId, item.score]))

  const fresh = grids.filter(grid => !recentIdSet.has(grid.id))
  const freshPool = fresh.length ? fresh : [...grids]
  const personalCooldownClean = freshPool.filter(grid => {
    for (const answer of answerSet(grid)) if (repeatedSet.has(answer)) return false
    return true
  })
  const personalPool = personalCooldownClean.length ? personalCooldownClean : freshPool
  const globalCooldownClean = personalPool.filter(grid => {
    for (const answer of answerSet(grid)) if (globalSet.has(answer)) return false
    return true
  })
  const pool = globalCooldownClean.length ? globalCooldownClean : personalPool

  const ranked = pool.map(grid => {
    let overlapCount = 0
    let repeatWeight = 0
    let globalCooldownHits = 0
    for (const answer of answerSet(grid)) {
      const uses = recentAnswerFrequency.get(answer) ?? 0
      if (uses > 0) overlapCount += 1
      repeatWeight += uses
      if (globalSet.has(answer)) globalCooldownHits += 1
    }
    const popularityScore = popularityById.get(grid.id) ?? 60
    const penalty = repeatWeight * 8 + overlapCount * 3 + globalCooldownHits * 2 - (popularityScore - 60) * 0.22
    return { grid, overlapCount, penalty }
  }).sort((left, right) => left.penalty - right.penalty || left.grid.id.localeCompare(right.grid.id))

  const bestPenalty = ranked[0].penalty
  const shortlist = ranked.filter(item => item.penalty <= bestPenalty + 2.5).slice(0, 5)
  const chosen = shortlist[stableHash(seed) % shortlist.length]
  return {
    grid: chosen.grid,
    recentGridIds,
    repeatedAnswersOnCooldown,
    overlapCount: chosen.overlapCount,
  }
}
