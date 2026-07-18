import {
  evaluateTurn,
  keepRackLettersAfterTurn,
  replenishUniqueRack,
  type GamePlacement,
  type GameRuleGrid,
} from './gameRules'

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

export const BOT_NAMES = ['Léa', 'Hugo', 'Inès', 'Nathan', 'Zoé', 'Lucas', 'Manon', 'Adam', 'Jade', 'Théo', 'Clara', 'Noé', 'Lina', 'Gabriel'] as const
export const BOT_AVATAR_IDS = ['amina', 'malik', 'mei', 'kenji', 'ines', 'nael', 'camille', 'alex'] as const
export const BOT_FRAME_IDS = ['cadre-ivoire', 'cadre-sauge', 'cadre-terracotta', 'cadre-encre', 'cadre-laiton'] as const

function hash(text: string): number {
  let value = 2166136261
  for (const character of text) value = Math.imul(value ^ character.charCodeAt(0), 16777619)
  return value >>> 0
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
  if (persona.skill === 'beginner') return { accuracy: 68, minLetters: 1, maxLetters: 2, wordBonusWeight: 1.4, pressureGap: 10 }
  if (persona.skill === 'regular') return { accuracy: 84, minLetters: 2, maxLetters: 4, wordBonusWeight: 1.9, pressureGap: 7 }
  return { accuracy: 95, minLetters: 3, maxLetters: 5, wordBonusWeight: 2.5, pressureGap: 4 }
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
  return replenishUniqueRack({
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
  const pressureBoost = scoreGap >= tuning.pressureGap ? 1 : 0
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
      const crossingPressure = grid.words.filter(word => {
        const cells = word.cells?.map(([row, column]) => row * grid.columns + column) ?? []
        return cells.includes(cellIndex)
      }).length
      const score = evaluation.scoreGained * 10 + wordPoints * tuning.wordBonusWeight + crossingPressure + (hash(`${seed}:jitter:${step}:${cellIndex}`) % 7) / 10
      return [{ cellIndex, letter, score }]
    }))

    if (!candidates.length) break
    candidates.sort((left, right) => right.score - left.score)
    const choiceWindow = persona.skill === 'beginner' ? Math.min(3, candidates.length) : persona.skill === 'regular' ? Math.min(2, candidates.length) : 1
    const chosen = candidates[hash(`${seed}:choice:${step}`) % choiceWindow]
    const correctRoll = hash(`${seed}:accuracy:${step}:${chosen.cellIndex}`) % 100
    const isCorrect = correctRoll < tuning.accuracy
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
