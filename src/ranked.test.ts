import { describe, expect, it } from 'vitest'
import {
  nextRankedDivision,
  rankedDivision,
  rankedPlacementLabel,
  RANKED_PLACEMENT_MATCHES,
} from './ranked'

describe('ranked progression', () => {
  it('keeps players unranked throughout all five placement matches', () => {
    expect(rankedDivision(2_500, RANKED_PLACEMENT_MATCHES - 1).id).toBe('unranked')
    expect(rankedPlacementLabel(4)).toBe('4/5 placements')
  })

  it.each([
    [0, 'bronze'],
    [1_099, 'bronze'],
    [1_100, 'silver'],
    [1_300, 'gold'],
    [1_500, 'platinum'],
    [1_700, 'diamond'],
    [1_900, 'master'],
    [2_100, 'legend'],
  ] as const)('maps %i points to %s after placements', (points, division) => {
    expect(rankedDivision(points, RANKED_PLACEMENT_MATCHES).id).toBe(division)
  })

  it('reports the next reachable division', () => {
    expect(nextRankedDivision(1_625, 12)?.id).toBe('diamond')
    expect(nextRankedDivision(2_300, 24)).toBeNull()
  })
})
