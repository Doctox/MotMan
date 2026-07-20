import type { MatchState } from './matches'
import type { PollVisibility } from './adaptivePolling'

type MatchPollDelayOptions = {
  match: MatchState | null
  playerId: string
  visibility: PollVisibility
  realtimeConnected: boolean
  unchangedPolls: number
  failureCount: number
  now?: number
}

/**
 * Safety polling for missed websocket events, bot thinking and server-side
 * timeout resolution. Hidden games are fully suspended and wake immediately
 * when the application becomes visible again.
 */
export function matchPollDelay({
  match,
  playerId,
  visibility,
  realtimeConnected,
  unchangedPolls,
  failureCount,
  now = Date.now(),
}: MatchPollDelayOptions): number {
  if (visibility === 'hidden' || match?.status === 'finished') return -1

  const failureBackoff = Math.min(30_000, failureCount > 0 ? 2_500 * 2 ** Math.min(3, failureCount - 1) : 0)
  if (failureBackoff) return failureBackoff
  if (!match) return realtimeConnected ? 8_000 : 2_000

  const botIsThinking = Boolean(match.bot && match.currentPlayerId === match.bot.playerId)
  if (botIsThinking) return 1_250

  const untilTurnBoundary = Math.max(0, new Date(match.turnEndsAt).getTime() - now + 180)
  const boundaryDelay = untilTurnBoundary > 0 ? Math.max(350, untilTurnBoundary) : 350
  const unchangedBackoff = Math.min(8_000, Math.floor(Math.max(0, unchangedPolls) / 2) * 1_000)

  if (match.pace === 'async') {
    const fallback = realtimeConnected ? 30_000 : 8_000
    return Math.min(fallback + unchangedBackoff, boundaryDelay)
  }

  const ownTurn = match.currentPlayerId === playerId
  const fallback = realtimeConnected ? ownTurn ? 12_000 : 8_000 : ownTurn ? 3_000 : 2_000
  return Math.min(fallback + unchangedBackoff, boundaryDelay)
}
