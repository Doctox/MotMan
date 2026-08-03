import { describe, expect, it } from 'vitest'
import { createMatchRackTiles, reconcileRackPlacements } from './rackTiles'

describe('createMatchRackTiles', () => {
  it('keeps duplicate letters as distinct physical tiles', () => {
    const tiles = createMatchRackTiles(['A', 'A', 'E', 'M', 'L'], 11)

    expect(tiles.map(tile => tile.letter)).toEqual(['A', 'A', 'E', 'M', 'L'])
    expect(new Set(tiles.map(tile => tile.id)).size).toBe(5)
  })

  it('is deterministic for the duration of a turn', () => {
    expect(createMatchRackTiles(['O', 'O'], 4)).toEqual(createMatchRackTiles(['O', 'O'], 4))
  })

  it('préserve les lettres déjà posées lorsque l’indice consomme une autre tuile', () => {
    const placed = {
      8: { id: 'duel-4-2-D', letter: 'D' },
    }

    expect(reconcileRackPlacements(placed, ['C', 'D'], 4)).toEqual({
      8: { id: 'duel-4-1-D', letter: 'D' },
    })
  })
})
