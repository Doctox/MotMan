import { describe, expect, it } from 'vitest'
import {
  canUseHint,
  canUseReroll,
  evaluateTurn,
  gameWordCellIndexes,
  hasTurnStarted,
  hintCandidates,
  isTurnSubmissionExpired,
  keepRackLettersAfterTurn,
  replenishUniqueRack,
  shouldForfeitAfterInactivity,
  type GameRuleGrid,
} from './gameRules'

const crossingGrid: GameRuleGrid = {
  columns: 3,
  rows: 3,
  cells: [
    { kind: 'letter', solution: 'C' }, { kind: 'letter', solution: 'A' }, { kind: 'letter', solution: 'T' },
    { kind: 'letter', solution: 'A' }, { kind: 'clue' }, { kind: 'clue' },
    { kind: 'letter', solution: 'R' }, { kind: 'clue' }, { kind: 'clue' },
  ],
  words: [
    { id: 'cat', answer: 'CAT', direction: 'across', row: 0, col: 0 },
    { id: 'car', answer: 'CAR', direction: 'down', row: 0, col: 0 },
  ],
}

describe('moteur de règles partagé', () => {
  it('sépare les lettres correctes et incorrectes', () => {
    const result = evaluateTurn({
      grid: crossingGrid,
      occupiedBefore: [],
      placements: [{ cellIndex: 0, letter: 'C' }, { cellIndex: 2, letter: 'R' }],
    })
    expect(result.correctCells).toEqual([0])
    expect(result.wrongCells).toEqual([2])
    expect(result.letterPoints).toBe(1)
    expect(result.scoreGained).toBe(1)
    expect(result.productive).toBe(true)
  })

  it('récompense un mot terminé par le joueur', () => {
    const result = evaluateTurn({
      grid: crossingGrid,
      occupiedBefore: [0, 1],
      placements: [{ cellIndex: 2, letter: 'T' }],
    })
    expect(result.wordBonuses.map(word => word.answer)).toEqual(['CAT'])
    expect(result.letterPoints).toBe(1)
    expect(result.scoreGained).toBe(4)
  })

  it('récompense les deux mots complétés sur un croisement', () => {
    const result = evaluateTurn({
      grid: crossingGrid,
      occupiedBefore: [1, 2, 3, 6],
      placements: [{ cellIndex: 0, letter: 'C' }],
    })
    expect(result.wordBonuses.map(word => word.answer)).toEqual(['CAT', 'CAR'])
    expect(result.scoreGained).toBe(7)
    expect(result.completesGrid).toBe(true)
  })

  it('donne zéro à la lettre aidée et au mot qu’elle termine immédiatement', () => {
    const result = evaluateTurn({
      grid: crossingGrid,
      occupiedBefore: [0, 1],
      placements: [{ cellIndex: 2, letter: 'T' }],
      aidedCell: 2,
    })
    expect(result.letterPoints).toBe(0)
    expect(result.wordBonuses).toEqual([])
    expect(result.scoreGained).toBe(0)
    expect(result.productive).toBe(false)
  })

  it('récompense un mot terminé plus tard malgré un ancien indice', () => {
    const result = evaluateTurn({
      grid: crossingGrid,
      occupiedBefore: [0, 1],
      placements: [{ cellIndex: 2, letter: 'T' }],
      aidedCell: 1,
    })
    expect(result.wordBonuses.map(word => word.answer)).toEqual(['CAT'])
    expect(result.scoreGained).toBe(4)
  })

  it('ajoute cinq points quand les cinq lettres du chevalet sont correctes', () => {
    const grid: GameRuleGrid = {
      columns: 5,
      rows: 1,
      cells: [...'SALUT'].map(solution => ({ kind: 'letter' as const, solution })),
      words: [{ id: 'salut', answer: 'SALUT', direction: 'across', row: 0, col: 0 }],
    }
    const result = evaluateTurn({
      grid,
      occupiedBefore: [],
      placements: [...'SALUT'].map((letter, cellIndex) => ({ cellIndex, letter })),
    })
    expect(result.letterPoints).toBe(5)
    expect(result.rackBonus).toBe(5)
    expect(result.wordBonuses[0].points).toBe(5)
    expect(result.scoreGained).toBe(15)
    expect(result.completesGrid).toBe(true)
  })

  it('calcule les trajets explicites et implicites de la même façon', () => {
    expect(gameWordCellIndexes(crossingGrid, crossingGrid.words[0])).toEqual([0, 1, 2])
    expect(gameWordCellIndexes(crossingGrid, { answer: 'CAR', direction: 'down', cells: [[0, 0], [1, 0], [2, 0]] })).toEqual([0, 3, 6])
  })
})

describe('indice et chevalet', () => {
  it('ne propose que les lettres du chevalet encore utiles', () => {
    const candidates = hintCandidates(crossingGrid, ['T', 'R', 'Z'], [2])
    expect(candidates).toEqual([{ cellIndex: 6, letter: 'R', rackIndex: 1 }])
  })

  it('garde un chevalet unique et évite d’abord les lettres fraîchement jouées', () => {
    const rack = replenishUniqueRack({
      neededLetters: ['A', 'A', 'B', 'C', 'D', 'E'],
      currentLetters: ['A', 'A', 'X'],
      avoidLetters: ['B'],
      chooseIndex: () => 0,
    })
    expect(rack).toEqual(['A', 'C', 'D', 'E', 'B'])
    expect(new Set(rack).size).toBe(rack.length)
  })

  it('retire uniquement les lettres correctes et rend les lettres refusées au chevalet', () => {
    const rackBefore = ['A', 'B', 'C', 'D', 'E']
    const evaluated = evaluateTurn({
      grid: crossingGrid,
      occupiedBefore: [],
      placements: [{ cellIndex: 0, letter: 'C' }, { cellIndex: 2, letter: 'A' }],
    })

    expect(evaluated.correctPlacements).toEqual([{ cellIndex: 0, letter: 'C' }])
    expect(evaluated.wrongPlacements).toEqual([{ cellIndex: 2, letter: 'A' }])
    expect(keepRackLettersAfterTurn(rackBefore, evaluated.correctPlacements)).toEqual(['A', 'B', 'D', 'E'])
  })

  it('limite chaque bonus à une utilisation et bloque la relance avec une lettre posée', () => {
    expect(canUseHint(false)).toBe(true)
    expect(canUseHint(true)).toBe(false)
    expect(canUseReroll({ alreadyUsed: false, pendingPlacements: 0, hintActive: false })).toBe(true)
    expect(canUseReroll({ alreadyUsed: true, pendingPlacements: 0, hintActive: false })).toBe(false)
    expect(canUseReroll({ alreadyUsed: false, pendingPlacements: 1, hintActive: false })).toBe(false)
    expect(canUseReroll({ alreadyUsed: false, pendingPlacements: 0, hintActive: true })).toBe(false)
  })
})

describe('limites de tour', () => {
  it('refuse une action avant le début serveur du tour', () => {
    expect(hasTurnStarted(9_999, 10_000)).toBe(false)
    expect(hasTurnStarted(10_000, 10_000)).toBe(true)
  })

  it('accorde la grâce réseau jusqu’à sa limite exacte', () => {
    expect(isTurnSubmissionExpired(10_999, 10_000, 1_000)).toBe(false)
    expect(isTurnSubmissionExpired(11_000, 10_000, 1_000)).toBe(true)
  })

  it.each([
    { remainingSeconds: 2, now: 8_000 },
    { remainingSeconds: 1, now: 9_000 },
    { remainingSeconds: 0, now: 10_000 },
  ])('accepte une réponse quand le compteur affiche encore $remainingSeconds seconde(s)', ({ now }) => {
    expect(isTurnSubmissionExpired(now, 10_000, 2_000)).toBe(false)
  })

  it('ne déclare une défaite qu’au troisième tour inactif', () => {
    expect(shouldForfeitAfterInactivity(1)).toBe(false)
    expect(shouldForfeitAfterInactivity(2)).toBe(false)
    expect(shouldForfeitAfterInactivity(3)).toBe(true)
  })
})
