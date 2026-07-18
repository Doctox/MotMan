import { isCatalogGridPlayable } from './gridCatalogPolicy'
import { gridCellIndex, resolveGridDimensions, type GridDimensionsSource } from './gridDimensions'

export type Direction = 'across' | 'down'
export type ArrowDirection = 'right' | 'down' | 'downright' | 'rightdown'
export type GridDifficulty = 'easy' | 'normal' | 'hard'
export type ClueImage = { asset: string; alt: string; source: string; license: string }
export type PlacedWord = { answer: string; clue: string; image?: ClueImage; difficulty: 1 | 2 | 3; theme: string; id: string; row: number; col: number; direction: Direction }
export type ClueEntry = { text: string; image?: ClueImage; direction: Direction; arrow: ArrowDirection; wordId: string }
export type GeneratedCell =
  | { kind: 'block' }
  | { kind: 'clue'; entries: ClueEntry[] }
  | { kind: 'letter'; solution: string; wordIds: string[] }
export type GridValidation = { valid: boolean; errors: string[]; score: number }
export type GeneratedGrid = { id: string; size?: number; columns: number; rows: number; difficulty: GridDifficulty; cells: GeneratedCell[]; words: PlacedWord[]; seed: number; version: string; validation: GridValidation }

type CatalogWord = { wordId?: string; answer: string; clue?: string; image?: ClueImage; direction: Direction; arrow?: ArrowDirection; clueCell: number[]; cells: number[][] }
type CatalogGrid = GridDimensionsSource & { id: string; difficulty?: GridDifficulty; clueCells: number[][]; words: CatalogWord[] }
type GridCatalog = { version: number; grids: CatalogGrid[] }
type LoadedCatalog = { version: string; playable: CatalogGrid[] }

let catalogPromise: Promise<LoadedCatalog> | null = null

export function preloadGridCatalog(): Promise<LoadedCatalog> {
  catalogPromise ??= import('./data/runtime.grid.catalog.json').then(module => {
    const catalog = module.default as GridCatalog
    return {
      version: `offline-catalog-${catalog.version}`,
      playable: catalog.grids.filter(isCatalogGridPlayable),
    }
  })
  return catalogPromise
}

function catalogSeed(id: string): number {
  return [...id].reduce((hash, character) => Math.imul(hash ^ character.charCodeAt(0), 16777619), 2166136261) >>> 0
}

function materialize(source: CatalogGrid, difficulty: GridDifficulty, version: string): GeneratedGrid {
  const dimensions = resolveGridDimensions(source)
  const cells: GeneratedCell[] = Array.from({ length: dimensions.columns * dimensions.rows }, () => ({ kind: 'block' }))
  source.clueCells.forEach(([row, col]) => {
    cells[gridCellIndex(dimensions, row, col)] = { kind: 'clue', entries: [] }
  })
  const words: PlacedWord[] = source.words.map((item, wordIndex) => {
    const id = item.wordId ?? `${source.id}:word:${wordIndex}`
    const [row, col] = item.cells[0]
    const clue = item.clue?.trim() ?? ''
    if (!clue && !item.image) throw new Error(`${source.id}: définition non relue pour ${item.answer}`)
    const placed: PlacedWord = { answer: item.answer, clue, image: item.image, difficulty: 1, theme: 'catalogue', id, row, col, direction: item.direction }
    const clueIndex = gridCellIndex(dimensions, item.clueCell[0], item.clueCell[1])
    const clueCell = cells[clueIndex]
    if (clueCell.kind !== 'clue') throw new Error(`${source.id}: case de définition absente`)
    const arrow = item.arrow ?? (item.direction === 'across' ? 'right' : 'down')
    clueCell.entries.push({ text: clue, image: item.image, direction: item.direction, arrow, wordId: id })
    item.cells.forEach(([letterRow, letterCol], offset) => {
      const index = gridCellIndex(dimensions, letterRow, letterCol)
      const existing = cells[index]
      const solution = item.answer[offset]
      if (existing.kind === 'letter') {
        if (existing.solution !== solution) throw new Error(`${source.id}: croisement incohérent`)
        existing.wordIds.push(id)
      } else if (existing.kind === 'block') cells[index] = { kind: 'letter', solution, wordIds: [id] }
      else throw new Error(`${source.id}: une définition coupe un mot`)
    })
    return placed
  })
  const validation = validateGrid({ ...dimensions, size: source.size, cells, words })
  if (!validation.valid) throw new Error(`${source.id}: ${validation.errors.join('; ')}`)
  return { id: source.id, size: source.size, ...dimensions, difficulty, cells, words, seed: catalogSeed(source.id), version, validation }
}

export function validateGrid(grid: Pick<GeneratedGrid, 'size' | 'columns' | 'rows' | 'cells' | 'words'>): GridValidation {
  const errors: string[] = []
  const dimensions = resolveGridDimensions(grid)
  const expectedCells = dimensions.columns * dimensions.rows
  if (grid.cells.length !== expectedCells) errors.push(`La grille doit contenir ${expectedCells} cases`)
  if (grid.cells.some(cell => cell.kind === 'block')) errors.push('Une case du catalogue est sans fonction')
  grid.words.forEach(word => {
    const dr = word.direction === 'down' ? 1 : 0
    const dc = word.direction === 'across' ? 1 : 0
    word.answer.split('').forEach((letter, offset) => {
      const cell = grid.cells[gridCellIndex(dimensions, word.row + offset * dr, word.col + offset * dc)]
      if (cell?.kind !== 'letter' || cell.solution !== letter || !cell.wordIds.includes(word.id)) errors.push(`${word.answer}: trajet incorrect`)
    })
  })
  const filled = grid.cells.filter(cell => cell.kind !== 'block').length / expectedCells
  return { valid: errors.length === 0, errors, score: Math.round(filled * 100) }
}

export async function generateGrid(seed = Date.now(), difficulty: GridDifficulty = 'normal', excludedGridIds: Iterable<string> = []): Promise<GeneratedGrid> {
  const { playable: playableCatalog, version } = await preloadGridCatalog()
  if (!playableCatalog.length) throw new Error('Le catalogue actif est vide')
  const excluded = new Set(excludedGridIds)
  const available = playableCatalog.filter(grid => !excluded.has(grid.id))
  const pool = available.length ? available : playableCatalog
  const source = pool[Math.abs(seed) % pool.length]
  return materialize(source, difficulty, version)
}

export async function generateGridById(gridId: string, difficulty: GridDifficulty = 'normal'): Promise<GeneratedGrid> {
  const { playable: playableCatalog, version } = await preloadGridCatalog()
  const source = playableCatalog.find(grid => grid.id === gridId)
  if (!source) throw new Error(`La grille ${gridId} est introuvable`)
  return materialize(source, difficulty, version)
}
