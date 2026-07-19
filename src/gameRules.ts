export type GameDirection = 'across' | 'down'

export type GameRuleCell = { kind: string; solution?: string }

export type GameRuleWord = {
  id?: string
  answer: string
  direction: GameDirection
  row?: number
  col?: number
  cells?: readonly (readonly [number, number])[]
}

export type GameRuleGrid = {
  columns: number
  rows: number
  cells: readonly GameRuleCell[]
  words: readonly GameRuleWord[]
}

export type GamePlacement = { cellIndex: number; letter: string }

export type CompletedWordBonus = {
  id?: string
  answer: string
  cells: number[]
  points: number
  direction: GameDirection
}

export type TurnEvaluation = {
  correctPlacements: GamePlacement[]
  wrongPlacements: GamePlacement[]
  correctCells: number[]
  wrongCells: number[]
  aidedCell: number | null
  letterPoints: number
  wordBonuses: CompletedWordBonus[]
  rackBonus: number
  scoreGained: number
  productive: boolean
  completesGrid: boolean
}

export const RACK_SIZE = 5
export const RACK_COMPLETION_BONUS = 5
export const MAX_INACTIVITY_COUNT = 3
export const REWARD_STEP_MS = 1_240
export const REWARD_EFFECT_LIFETIME_MS = 1_180

export function gameWordCellIndexes(grid: Pick<GameRuleGrid, 'columns'>, word: GameRuleWord): number[] {
  if (word.cells?.length) return word.cells.map(([row, column]) => row * grid.columns + column)
  if (!Number.isInteger(word.row) || !Number.isInteger(word.col)) {
    throw new Error(`Trajet manquant pour ${word.answer}`)
  }
  const row = Number(word.row)
  const column = Number(word.col)
  const rowStep = word.direction === 'down' ? 1 : 0
  const columnStep = word.direction === 'across' ? 1 : 0
  return Array.from({ length: word.answer.length }, (_, offset) =>
    (row + offset * rowStep) * grid.columns + column + offset * columnStep)
}

export function evaluateTurn({
  grid,
  occupiedBefore,
  placements,
  aidedCell = null,
  rackSize = RACK_SIZE,
}: {
  grid: GameRuleGrid
  occupiedBefore: Iterable<number>
  placements: readonly GamePlacement[]
  aidedCell?: number | null
  rackSize?: number
}): TurnEvaluation {
  const before = new Set(occupiedBefore)
  const correctPlacements: GamePlacement[] = []
  const wrongPlacements: GamePlacement[] = []

  for (const placement of placements) {
    const cell = grid.cells[placement.cellIndex]
    if (cell?.kind === 'letter' && cell.solution === placement.letter) correctPlacements.push(placement)
    else wrongPlacements.push(placement)
  }

  const correctCells = correctPlacements.map(placement => placement.cellIndex)
  const wrongCells = wrongPlacements.map(placement => placement.cellIndex)
  const after = new Set([...before, ...correctCells])
  const aidedPlacedThisTurn = aidedCell !== null && correctCells.includes(aidedCell)
  const wordBonuses = grid.words.flatMap(word => {
    const cells = gameWordCellIndexes(grid, word)
    const completedNow = !cells.every(index => before.has(index)) && cells.every(index => after.has(index))
    // An aided letter and a word completed by that very hint both score zero.
    // If the hint was placed on an earlier turn, a later player placement can
    // still complete and reward the word normally.
    const completedByCurrentHint = completedNow && aidedPlacedThisTurn && cells.includes(aidedCell)
    return completedNow && !completedByCurrentHint
      ? [{ id: word.id, answer: word.answer, cells, points: word.answer.length, direction: word.direction }]
      : []
  })
  const letterPoints = correctPlacements.filter(placement => placement.cellIndex !== aidedCell).length
  const rackBonus = correctPlacements.length === rackSize && aidedCell === null ? RACK_COMPLETION_BONUS : 0
  const wordPoints = wordBonuses.reduce((total, bonus) => total + bonus.points, 0)
  const completesGrid = grid.cells.every((cell, index) => cell.kind !== 'letter' || after.has(index))

  return {
    correctPlacements,
    wrongPlacements,
    correctCells,
    wrongCells,
    aidedCell,
    letterPoints,
    wordBonuses,
    rackBonus,
    scoreGained: letterPoints + wordPoints + rackBonus,
    productive: letterPoints > 0,
    completesGrid,
  }
}

export function hintCandidates(
  grid: Pick<GameRuleGrid, 'cells'>,
  rackLetters: readonly string[],
  occupiedCells: Iterable<number>,
): Array<GamePlacement & { rackIndex: number }> {
  const occupied = new Set(occupiedCells)
  return rackLetters.flatMap((letter, rackIndex) => grid.cells.flatMap((cell, cellIndex) =>
    cell.kind === 'letter' && !occupied.has(cellIndex) && cell.solution === letter
      ? [{ cellIndex, letter, rackIndex }]
      : []))
}

export function replenishRackFromNeeds({
  neededLetters,
  currentLetters,
  avoidLetters = [],
  count = RACK_SIZE,
  chooseIndex,
}: {
  neededLetters: readonly string[]
  currentLetters: readonly string[]
  avoidLetters?: Iterable<string>
  count?: number
  chooseIndex?: (pool: readonly string[], position: number) => number
}): string[] {
  const remaining = [...neededLetters]
  const rack: string[] = []
  const avoided = new Set(avoidLetters)

  for (const letter of currentLetters) {
    if (rack.length >= count) continue
    const neededIndex = remaining.indexOf(letter)
    if (neededIndex < 0) continue
    rack.push(letter)
    remaining.splice(neededIndex, 1)
  }

  while (rack.length < count && remaining.length > 0) {
    const preferred = remaining.filter(letter => !avoided.has(letter))
    const pool = preferred.length > 0 ? preferred : remaining
    const requestedIndex = chooseIndex?.(pool, rack.length) ?? Math.floor(Math.random() * pool.length)
    const safeIndex = Math.abs(Math.floor(requestedIndex)) % pool.length
    const letter = pool[safeIndex]
    const remainingIndex = remaining.indexOf(letter)
    if (remainingIndex < 0) break
    remaining.splice(remainingIndex, 1)
    rack.push(letter)
  }
  return rack
}

export type SharedRackDraw = {
  rack: string[]
  letterBag: string[]
}

/**
 * Draws a rack from the match-wide bag. Every occurrence is removed from the
 * bag when dealt, so two players can only receive the same letter when the
 * unfinished board genuinely needs that letter more than once.
 */
export function drawRackFromBag({
  letterBag,
  currentLetters,
  avoidLetters = [],
  count = RACK_SIZE,
  chooseIndex,
}: {
  letterBag: readonly string[]
  currentLetters: readonly string[]
  avoidLetters?: Iterable<string>
  count?: number
  chooseIndex?: (pool: readonly string[], position: number) => number
}): SharedRackDraw {
  const remaining = [...letterBag]
  const rack: string[] = []
  const avoided = new Set(avoidLetters)

  for (const letter of currentLetters) {
    if (rack.length >= count) continue
    rack.push(letter)
  }

  while (rack.length < count) {
    const preferred = remaining.filter(letter => !avoided.has(letter))
    const pool = preferred.length > 0 ? preferred : remaining
    if (!pool.length) break
    const requestedIndex = chooseIndex?.(pool, rack.length) ?? Math.floor(Math.random() * pool.length)
    const safeIndex = Math.abs(Math.floor(requestedIndex)) % pool.length
    const letter = pool[safeIndex]
    const bagIndex = remaining.indexOf(letter)
    if (bagIndex < 0) break
    remaining.splice(bagIndex, 1)
    rack.push(letter)
  }

  return { rack, letterBag: remaining }
}

/**
 * Removes only letters accepted by the board from the rack. Incorrect
 * placements stay available for the player's next turn.
 */
export function keepRackLettersAfterTurn(
  rackLetters: readonly string[],
  correctPlacements: readonly Pick<GamePlacement, 'letter'>[],
): string[] {
  const remaining = [...rackLetters]
  for (const placement of correctPlacements) {
    const index = remaining.indexOf(placement.letter)
    if (index >= 0) remaining.splice(index, 1)
  }
  return remaining
}

export function canUseHint(alreadyUsed: boolean): boolean {
  return !alreadyUsed
}

export function canUseReroll({ alreadyUsed, pendingPlacements, hintActive }: {
  alreadyUsed: boolean
  pendingPlacements: number
  hintActive: boolean
}): boolean {
  return !alreadyUsed && pendingPlacements === 0 && !hintActive
}

export function shouldForfeitAfterInactivity(inactivityCount: number): boolean {
  return inactivityCount >= MAX_INACTIVITY_COUNT
}

export function isTurnSubmissionExpired(now: number, turnEndsAt: number, graceMilliseconds: number): boolean {
  return now >= turnEndsAt + Math.max(0, graceMilliseconds)
}

export function hasTurnStarted(now: number, turnStartedAt: number): boolean {
  return now >= turnStartedAt
}
