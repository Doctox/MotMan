import runtimePolicy from './data/runtime.catalog-policy.json'

type PolicyWord = { answer: string; clue?: string; image?: unknown }
type PolicyGrid = { id: string; words: PolicyWord[] }

const BLOCKED_ANSWERS = new Set([
  'SS', 'TT', 'PCQ', 'FDP', 'IBN', 'KIL', 'NUD', 'GEN', 'INN', 'THE', 'GUEST', 'BOARD', 'CHAN',
  // Réponses signalées en partie comme archaïques, étrangères ou impossibles
  // à déduire naturellement depuis leur définition.
  'BESEF', 'TUT', 'ATON', 'SPEED',
])
const quarantinedGridIds = new Set(runtimePolicy.quarantinedGridIds)
const rejectedAnswers = new Set(runtimePolicy.rejectedAnswers)
const rejectedPairs = new Set(runtimePolicy.rejectedPairs)

export function isCatalogGridPlayable(grid: PolicyGrid): boolean {
  return !quarantinedGridIds.has(grid.id) && grid.words.every(word =>
    !BLOCKED_ANSWERS.has(word.answer) &&
    !rejectedAnswers.has(word.answer) &&
    !rejectedPairs.has(`${word.answer}\u0000${word.clue ?? ''}`) &&
    Boolean(word.clue?.trim() || word.image)
  )
}
