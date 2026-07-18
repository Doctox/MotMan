import { describe, expect, it } from 'vitest'
import { basketRarityProbabilities, calculateFeatherReward } from './progressionRewards'

describe('calculateFeatherReward', () => {
  it('applique les montants validés et les trois bonus', () => {
    expect(calculateFeatherReward({
      mode: 'multiplayer', outcome: 'win', hintUsed: false, rerollUsed: false, rackCompletions: 2,
    })).toEqual({ base: 160, noHint: 5, noReroll: 5, fullRack: 10, total: 180 })
  })

  it('ne donne rien après un abandon', () => {
    expect(calculateFeatherReward({
      mode: 'solo', outcome: 'abandon', hintUsed: false, rerollUsed: false, rackCompletions: 3,
    }).total).toBe(0)
  })

  it('limite une victoire sur abandon adverse selon les tours joués', () => {
    expect(calculateFeatherReward({
      mode: 'multiplayer', outcome: 'opponent-abandoned', totalProductiveTurns: 4,
      hintUsed: true, rerollUsed: true,
    }).total).toBe(40)
  })
})

describe('basketRarityProbabilities', () => {
  it('produit les probabilités initiales validées', () => {
    const odds = basketRarityProbabilities(0)
    expect(odds.commun).toBeCloseTo(50)
    expect(odds.singulier).toBeCloseTo(28)
    expect(odds.rare).toBeCloseTo(14)
    expect(odds.precieux).toBeCloseTo(5)
    expect(odds.exceptionnel).toBeCloseTo(2.5)
    expect(odds.legendaire).toBeCloseTo(0.5)
  })

  it('redistribue exactement les chances quand une rareté est épuisée', () => {
    const odds = basketRarityProbabilities(0, ['rare', 'legendaire'])
    expect(odds.commun).toBe(0)
    expect(odds.rare + odds.legendaire).toBeCloseTo(100)
  })
})
