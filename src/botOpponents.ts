import {
  evaluateTurn,
  keepRackLettersAfterTurn,
  replenishRackFromNeeds,
  type GamePlacement,
  type GameRuleGrid,
} from './gameRules.ts'

export type BotSkill = 'beginner' | 'regular' | 'expert'

export type BotPersona = {
  displayName: string
  level: number
  skill: BotSkill
  avatarId: string
  frameId: string
}

export type BotTuning = {
  accuracy: number
  minLetters: number
  maxLetters: number
  wordBonusWeight: number
  pressureGap: number
}

export type BotMoveAttempt = GamePlacement & { correct: boolean }

export type BotMovePlan = {
  attempts: BotMoveAttempt[]
  rackAfter: string[]
}

export const BOT_THINKING_MIN_MS = 4_000
export const BOT_THINKING_MAX_MS = 8_000

export const BOT_NAMES = ['Léa', 'Hugo', 'Inès', 'Nathan', 'Zoé', 'Lucas', 'Manon', 'Adam', 'Jade', 'Théo', 'Clara', 'Noé', 'Lina', 'Gabriel'] as const
export const BOT_AVATAR_IDS = ['amina', 'malik', 'mei', 'kenji', 'ines', 'nael', 'camille', 'alex'] as const
export const BOT_FRAME_IDS = ['cadre-ivoire', 'cadre-sauge', 'cadre-terracotta', 'cadre-encre', 'cadre-laiton'] as const

function hash(text: string): number {
  let value = 2166136261
  for (const character of text) value = Math.imul(value ^ character.charCodeAt(0), 16777619)
  return value >>> 0
}

export function botThinkingDelayMs(seed: string): number {
  return BOT_THINKING_MIN_MS + hash(`${seed}:thinking`) % (BOT_THINKING_MAX_MS - BOT_THINKING_MIN_MS + 1)
}

export function createBotPersona(seed: string, preferredSkill?: BotSkill): BotPersona {
  const skillRoll = hash(`${seed}:skill`) % 100
  const skill: BotSkill = preferredSkill ?? (skillRoll < 35 ? 'beginner' : skillRoll < 85 ? 'regular' : 'expert')
  const range = skill === 'beginner' ? [6, 17] : skill === 'regular' ? [18, 34] : [35, 48]
  const level = range[0] + hash(`${seed}:level`) % (range[1] - range[0] + 1)
  const displayName = BOT_NAMES[hash(`${seed}:name`) % BOT_NAMES.length]
  const avatarId = BOT_AVATAR_IDS[hash(`${seed}:avatar`) % BOT_AVATAR_IDS.length]
  const frameId = BOT_FRAME_IDS[hash(`${seed}:frame`) % BOT_FRAME_IDS.length]
  return { displayName, level, skill, avatarId, frameId }
}

export function botTuning(persona: BotPersona): BotTuning {
  if (persona.skill === 'beginner') return { accuracy: 78, minLetters: 2, maxLetters: 3, wordBonusWeight: 2, pressureGap: 8 }
  // Normal must remain strategic without feeling clairvoyant: it still tries
  // three to four tiles and sees useful word completions, but makes a few more
  // human mistakes and waits a little longer before entering comeback mode.
  if (persona.skill === 'regular') return { accuracy: 88, minLetters: 3, maxLetters: 4, wordBonusWeight: 2.5, pressureGap: 7 }
  return { accuracy: 98, minLetters: 4, maxLetters: 5, wordBonusWeight: 3.6, pressureGap: 4 }
}

function neededLetters(grid: GameRuleGrid, occupiedCells: Iterable<number>): string[] {
  const occupied = new Set(occupiedCells)
  return grid.cells.flatMap((cell, index) =>
    cell.kind === 'letter' && cell.solution && !occupied.has(index) ? [cell.solution] : [])
}

export function refillBotRack({
  grid,
  occupiedCells,
  currentLetters,
  avoidLetters = [],
  seed,
}: {
  grid: GameRuleGrid
  occupiedCells: Iterable<number>
  currentLetters: readonly string[]
  avoidLetters?: Iterable<string>
  seed: string
}): string[] {
  return replenishRackFromNeeds({
    neededLetters: neededLetters(grid, occupiedCells),
    currentLetters,
    avoidLetters,
    chooseIndex: (pool, position) => hash(`${seed}:rack:${position}:${pool.join('')}`) % pool.length,
  })
}

function removeFirst(letters: string[], letter: string): void {
  const index = letters.indexOf(letter)
  if (index >= 0) letters.splice(index, 1)
}

function wrongLetterFor(rack: readonly string[], expected: string, seed: string): string | null {
  const candidates = rack.filter(letter => letter !== expected)
  if (!candidates.length) return null
  return candidates[hash(seed) % candidates.length]
}

export function planBotMove({
  grid,
  occupiedCells,
  rackLetters,
  persona,
  seed,
  scoreGap = 0,
}: {
  grid: GameRuleGrid
  occupiedCells: Iterable<number>
  rackLetters: readonly string[]
  persona: BotPersona
  seed: string
  scoreGap?: number
}): BotMovePlan {
  const tuning = botTuning(persona)
  const occupied = new Set(occupiedCells)
  const rack = [...rackLetters]
  const pressureBoost = scoreGap >= tuning.pressureGap * 2 ? 2 : scoreGap >= tuning.pressureGap ? 1 : 0
  const minLetters = Math.min(tuning.maxLetters, tuning.minLetters + pressureBoost)
  const maxLetters = Math.min(5, tuning.maxLetters + pressureBoost)
  const span = Math.max(1, maxLetters - minLetters + 1)
  const target = Math.min(rack.length, minLetters + (hash(`${seed}:target`) % span))
  const attempts: BotMoveAttempt[] = []
  const correctPlacements: GamePlacement[] = []
  const blockedThisTurn = new Set<number>()

  for (let step = 0; step < target; step += 1) {
    const candidates = rack.flatMap(letter => grid.cells.flatMap((cell, cellIndex) => {
      if (cell.kind !== 'letter' || cell.solution !== letter || occupied.has(cellIndex) || blockedThisTurn.has(cellIndex)) return []
      const evaluation = evaluateTurn({ grid, occupiedBefore: occupied, placements: [{ cellIndex, letter }] })
      const wordPoints = evaluation.wordBonuses.reduce((total, word) => total + word.points, 0)
      const relatedWords = grid.words.filter(word => {
        const cells = word.cells?.map(([row, column]) => row * grid.columns + column) ?? []
        return cells.includes(cellIndex)
      })
      const crossingPressure = relatedWords.length
      const progressPressure = relatedWords.reduce((total, word) => {
        const indexes = word.cells?.map(([row, column]) => row * grid.columns + column) ?? []
        if (!indexes.length) return total
        const filledAfter = indexes.filter(index => occupied.has(index) || index === cellIndex).length
        return total + (filledAfter * filledAfter) / indexes.length
      }, 0)
      const score = evaluation.scoreGained * 12
        + wordPoints * tuning.wordBonusWeight * 3
        + crossingPressure * 1.5
        + progressPressure * tuning.wordBonusWeight
        + (hash(`${seed}:jitter:${step}:${cellIndex}`) % 5) / 10
      return [{ cellIndex, letter, score }]
    }))

    if (!candidates.length) break
    candidates.sort((left, right) => right.score - left.score)
    const choiceWindow = persona.skill === 'beginner' ? Math.min(2, candidates.length) : 1
    const chosen = candidates[hash(`${seed}:choice:${step}`) % choiceWindow]
    const correctRoll = hash(`${seed}:accuracy:${step}:${chosen.cellIndex}`) % 100
    const isCorrect = correctRoll < Math.min(99, tuning.accuracy + pressureBoost * 3)
    if (isCorrect) {
      attempts.push({ cellIndex: chosen.cellIndex, letter: chosen.letter, correct: true })
      correctPlacements.push({ cellIndex: chosen.cellIndex, letter: chosen.letter })
      occupied.add(chosen.cellIndex)
      removeFirst(rack, chosen.letter)
    } else {
      const wrong = wrongLetterFor(rack, chosen.letter, `${seed}:wrong:${step}:${chosen.cellIndex}`)
      if (!wrong) {
        attempts.push({ cellIndex: chosen.cellIndex, letter: chosen.letter, correct: true })
        correctPlacements.push({ cellIndex: chosen.cellIndex, letter: chosen.letter })
        occupied.add(chosen.cellIndex)
        removeFirst(rack, chosen.letter)
      } else {
        attempts.push({ cellIndex: chosen.cellIndex, letter: wrong, correct: false })
        blockedThisTurn.add(chosen.cellIndex)
      }
    }
  }

  const rackAfterCorrect = keepRackLettersAfterTurn(rackLetters, correctPlacements)
  const occupiedAfter = new Set([...occupiedCells, ...correctPlacements.map(placement => placement.cellIndex)])
  return {
    attempts,
    rackAfter: refillBotRack({
      grid,
      occupiedCells: occupiedAfter,
      currentLetters: rackAfterCorrect,
      avoidLetters: correctPlacements.map(placement => placement.letter),
      seed: `${seed}:after`,
    }),
  }
}
