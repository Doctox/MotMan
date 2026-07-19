export type MatchHistoryOutcome = 'win' | 'draw' | 'loss' | 'abandon' | 'opponent-abandoned'

export type MatchHistoryTone = 'won' | 'drawn' | 'lost'

export function matchHistoryTone(outcome: MatchHistoryOutcome): MatchHistoryTone {
  if (outcome === 'win' || outcome === 'opponent-abandoned') return 'won'
  if (outcome === 'draw') return 'drawn'
  return 'lost'
}

export function matchHistoryResultLabel(outcome: MatchHistoryOutcome): string {
  const tone = matchHistoryTone(outcome)
  return tone === 'won' ? 'Victoire' : tone === 'drawn' ? 'Égalité' : 'Défaite'
}

export function matchHistoryDateLabel(completedAt: string, now = Date.now()): string {
  const elapsedMinutes = Math.max(0, Math.floor((now - new Date(completedAt).getTime()) / 60_000))
  if (elapsedMinutes < 1) return 'À l’instant'
  if (elapsedMinutes < 60) return `Il y a ${elapsedMinutes} min`
  const elapsedHours = Math.floor(elapsedMinutes / 60)
  if (elapsedHours < 24) return `Il y a ${elapsedHours} h`
  const elapsedDays = Math.floor(elapsedHours / 24)
  if (elapsedDays === 1) return 'Hier'
  if (elapsedDays < 7) return `Il y a ${elapsedDays} j`
  return new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short' }).format(new Date(completedAt))
}
