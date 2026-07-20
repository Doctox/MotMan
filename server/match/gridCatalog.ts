import catalog from '../../src/data/runtime.grid.catalog.json'
import { isCatalogGridPlayable } from '../../src/gridCatalogPolicy'
import { gridCellIndex, resolveGridDimensions } from '../../src/gridDimensions'
import { gameWordCellIndexes, type GameRuleGrid, type GameRuleWord } from '../../src/gameRules'
import type { CatalogGrid, CatalogWord } from './types'

export const grids = (catalog.grids as CatalogGrid[]).filter(isCatalogGridPlayable)
export const gridIds = new Set(grids.map(grid => grid.id))

if (!grids.length) throw new Error('Le catalogue actif ne contient aucune grille jouable.')

const ruleGridCache = new Map<string, GameRuleGrid>()

function ruleWord(word: CatalogWord): GameRuleWord {
  return {
    ...word,
    cells: word.cells.map(([row, column]) => [row, column] as const),
  }
}

export function gridById(gridId: string): CatalogGrid {
  const grid = grids.find(candidate => candidate.id === gridId)
  if (!grid) throw new Error('La grille de cette partie est introuvable.')
  return grid
}

export function ruleGrid(grid: CatalogGrid): GameRuleGrid {
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

export function gridSolution(grid: CatalogGrid): Map<number, string> {
  const dimensions = resolveGridDimensions(grid)
  const solution = new Map<number, string>()
  grid.words.forEach(word => word.cells.forEach(([row, col], offset) => {
    solution.set(gridCellIndex(dimensions, row, col), word.answer[offset])
  }))
  return solution
}

export function wordIndexes(grid: CatalogGrid, word: CatalogWord): number[] {
  return gameWordCellIndexes(ruleGrid(grid), ruleWord(word))
}

export function hash(text: string): number {
  let value = 2166136261
  for (const character of text) value = Math.imul(value ^ character.charCodeAt(0), 16777619)
  return value >>> 0
}

export function publicGrid(grid: CatalogGrid) {
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
