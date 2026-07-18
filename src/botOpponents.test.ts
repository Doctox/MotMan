import { describe, expect, it } from 'vitest'
import { planBotMove, refillBotRack, type BotPersona } from './botOpponents'
import type { GameRuleGrid } from './gameRules'

const expert: BotPersona = {
  displayName: 'Jade',
  level: 42,
  skill: 'expert',
  avatarId: 'mei',
  frameId: 'cadre-sauge',
}

const beginner: BotPersona = {
  displayName: 'Noe',
  level: 8,
  skill: 'beginner',
  avatarId: 'nael',
  frameId: 'cadre-ivoire',
}

const grid: GameRuleGrid = {
  columns: 4,
  rows: 3,
  cells: [
    { kind: 'letter', solution: 'B' }, { kind: 'letter', solution: 'U' }, { kind: 'letter', solution: 'S' }, { kind: 'clue' },
    { kind: 'letter', solution: 'C' }, { kind: 'letter', solution: 'H' }, { kind: 'letter', solution: 'A' }, { kind: 'letter', solution: 'T' },
    { kind: 'letter', solution: 'R' }, { kind: 'letter', solution: 'O' }, { kind: 'letter', solution: 'S' }, { kind: 'letter', solution: 'E' },
  ],
  words: [
    { id: 'bus', answer: 'BUS', direction: 'across', cells: [[0, 0], [0, 1], [0, 2]] },
    { id: 'chat', answer: 'CHAT', direction: 'across', cells: [[1, 0], [1, 1], [1, 2], [1, 3]] },
    { id: 'rose', answer: 'ROSE', direction: 'across', cells: [[2, 0], [2, 1], [2, 2], [2, 3]] },
  ],
}

describe('adversaires bot', () => {
  it('joue uniquement avec les lettres de son chevalet', () => {
    const plan = planBotMove({
      grid,
      occupiedCells: [0, 1],
      rackLetters: ['X', 'Y', 'Z'],
      persona: expert,
      seed: 'rack-only',
    })

    expect(plan.attempts).toEqual([])
  })

  it('priorise une lettre qui termine un mot', () => {
    const plan = planBotMove({
      grid,
      occupiedCells: [0, 1],
      rackLetters: ['S', 'C', 'H', 'A', 'T'],
      persona: expert,
      seed: 'finish-word',
    })

    expect(plan.attempts[0]).toMatchObject({ cellIndex: 2, letter: 'S', correct: true })
  })

  it('renouvelle le chevalet cache apres les lettres correctes', () => {
    const plan = planBotMove({
      grid,
      occupiedCells: [0, 1],
      rackLetters: ['S', 'C', 'H', 'A', 'T'],
      persona: expert,
      seed: 'refresh-rack',
    })

    const correctLetters = plan.attempts.filter(attempt => attempt.correct).map(attempt => attempt.letter)
    expect(plan.rackAfter.length).toBeGreaterThan(0)
    expect(plan.rackAfter.length).toBeLessThanOrEqual(5)
    for (const letter of correctLetters) expect(plan.rackAfter.filter(item => item === letter).length).toBeLessThanOrEqual(1)
  })

  it('compose un chevalet cache sans doublons inutiles', () => {
    const rack = refillBotRack({
      grid,
      occupiedCells: [],
      currentLetters: [],
      seed: 'fresh-rack',
    })

    expect(new Set(rack).size).toBe(rack.length)
  })

  it('reste moins agressif en niveau debutant', () => {
    const plan = planBotMove({
      grid,
      occupiedCells: [0, 1],
      rackLetters: ['S', 'C', 'H', 'A', 'T'],
      persona: beginner,
      seed: 'beginner-tempo',
    })

    expect(plan.attempts.length).toBeLessThanOrEqual(2)
  })
})
