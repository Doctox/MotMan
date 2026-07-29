export type PopularityRow = {
  grid_id: string
  plays: number
  completions: number
  positive_reviews: number
  negative_reviews: number
  average_duration_seconds: number | string | null
  popularity_score: number | string
}

export type RecentHistoryRow = {
  grid_id: string
  completed_at: string
}

function safeGridId(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const normalized = value.trim()
  return normalized && normalized.length <= 128 ? normalized : null
}

function finiteNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function buildRecentGridIds(rows: RecentHistoryRow[]) {
  const grouped = new Map<string, { gridId: string; playCount: number; lastPlayedAt: string }>()
  for (const row of rows) {
    const gridId = safeGridId(row.grid_id)
    if (!gridId) continue
    const existing = grouped.get(gridId)
    if (existing) {
      existing.playCount += 1
    } else {
      grouped.set(gridId, { gridId, playCount: 1, lastPlayedAt: row.completed_at })
    }
  }
  return [...grouped.values()]
}

export function buildGridUsageSnapshot(
  popularityRows: PopularityRow[],
  recentRows: RecentHistoryRow[],
  generatedAt = new Date().toISOString(),
) {
  const grids = popularityRows
    .map(row => {
      const gridId = safeGridId(row.grid_id)
      if (!gridId) return null
      const gamesPlayed = Math.max(0, Math.trunc(finiteNumber(row.plays)))
      const completions = Math.max(0, Math.trunc(finiteNumber(row.completions)))
      const duration = row.average_duration_seconds === null
        ? null
        : Math.max(0, Math.round(finiteNumber(row.average_duration_seconds)))
      return {
        gridId,
        gamesPlayed,
        positiveReviews: Math.max(0, Math.trunc(finiteNumber(row.positive_reviews))),
        negativeReviews: Math.max(0, Math.trunc(finiteNumber(row.negative_reviews))),
        abandons: Math.max(0, gamesPlayed - completions),
        averageDurationSeconds: duration,
        popularityScore: finiteNumber(row.popularity_score, 60),
      }
    })
    .filter(Boolean)

  return {
    schema: 'motman-grid-usage-snapshot',
    version: 1,
    generatedAt,
    grids,
    recentGridIds: buildRecentGridIds(recentRows),
  }
}
