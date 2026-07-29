import { describe, expect, it } from 'vitest'
import { buildGridUsageSnapshot } from '../supabase/functions/grid-usage-api/snapshot'

describe('Grid Studio usage snapshot', () => {
  it('returns only aggregate grid usage and groups the twelve most recent rows', () => {
    const snapshot = buildGridUsageSnapshot([
      {
        grid_id: 'compact-01',
        plays: 8,
        completions: 6,
        positive_reviews: 3,
        negative_reviews: 1,
        average_duration_seconds: '124.6',
        popularity_score: '72.4',
      },
    ], [
      { grid_id: 'compact-01', completed_at: '2026-07-26T12:00:00.000Z' },
      { grid_id: 'compact-01', completed_at: '2026-07-25T12:00:00.000Z' },
      { grid_id: 'compact-02', completed_at: '2026-07-24T12:00:00.000Z' },
    ], '2026-07-26T13:00:00.000Z')

    expect(snapshot).toEqual({
      schema: 'motman-grid-usage-snapshot',
      version: 1,
      generatedAt: '2026-07-26T13:00:00.000Z',
      grids: [{
        gridId: 'compact-01',
        gamesPlayed: 8,
        positiveReviews: 3,
        negativeReviews: 1,
        abandons: 2,
        averageDurationSeconds: 125,
        popularityScore: 72.4,
      }],
      recentGridIds: [
        { gridId: 'compact-01', playCount: 2, lastPlayedAt: '2026-07-26T12:00:00.000Z' },
        { gridId: 'compact-02', playCount: 1, lastPlayedAt: '2026-07-24T12:00:00.000Z' },
      ],
    })
    expect(JSON.stringify(snapshot)).not.toMatch(/userId|email|displayName|token|secret/i)
  })

  it('drops malformed grid ids and clamps invalid counters', () => {
    const snapshot = buildGridUsageSnapshot([
      {
        grid_id: '',
        plays: 1,
        completions: 1,
        positive_reviews: 0,
        negative_reviews: 0,
        average_duration_seconds: null,
        popularity_score: 60,
      },
      {
        grid_id: 'compact-03',
        plays: -5,
        completions: -2,
        positive_reviews: -1,
        negative_reviews: -1,
        average_duration_seconds: null,
        popularity_score: Number.NaN,
      },
    ], [])

    expect(snapshot.grids).toEqual([{
      gridId: 'compact-03',
      gamesPlayed: 0,
      positiveReviews: 0,
      negativeReviews: 0,
      abandons: 0,
      averageDurationSeconds: null,
      popularityScore: 60,
    }])
  })
})
