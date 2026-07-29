import type { PollVisibility } from './adaptivePolling'

export function socialMenuPollDelay(visibility: PollVisibility, realtimeConnected: boolean): number {
  if (visibility === 'hidden') return 60_000
  return realtimeConnected ? 60_000 : 30_000
}

export function lobbyMenuPollDelay(
  visibility: PollVisibility,
  realtimeConnected: boolean,
  matchmakingPending: boolean,
): number {
  if (visibility === 'hidden') return 60_000
  if (realtimeConnected) return 45_000
  return matchmakingPending ? 8_000 : 30_000
}
