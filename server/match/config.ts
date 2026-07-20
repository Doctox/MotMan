import { resolve } from 'node:path'
import { REWARD_STEP_MS } from '../../src/gameRules'

function numericEnvironment(name: string, fallback: number, minimum: number): number {
  const parsed = Number(process.env[name])
  return Number.isFinite(parsed) ? Math.max(minimum, parsed) : fallback
}

export const MATCH_DATABASE_PATH = resolve(process.env.MOTMAN_MATCH_DATABASE_PATH ?? '.motman-matches.json')
export const REALTIME_TURN_DURATION_MS = numericEnvironment('MOTMAN_TURN_DURATION_MS', 45_000, 250)
export const ASYNC_TURN_DURATION_MS = numericEnvironment('MOTMAN_ASYNC_TURN_DURATION_MS', 24 * 60 * 60 * 1_000, 1_000)
export const TURN_READY_DURATION_MS = numericEnvironment('MOTMAN_TURN_READY_DURATION_MS', 1_800, 0)

// A short server grace period lets a phone submit the move displayed at 00:00
// without a simultaneous polling request turning it into a timeout first.
export const TURN_SUBMIT_GRACE_MS = numericEnvironment('MOTMAN_TURN_GRACE_MS', 2_000, 0)
export const REVEAL_STEP_MS = numericEnvironment('MOTMAN_REVEAL_STEP_MS', REWARD_STEP_MS, 0)
export const MIN_REVEAL_DURATION_MS = numericEnvironment('MOTMAN_MIN_REVEAL_DURATION_MS', 700, 0)
export const INVITATION_DURATION_MS = 120_000
export const ASYNC_INVITATION_DURATION_MS = 7 * 24 * 60 * 60 * 1_000
export const REALTIME_SEARCH_STALE_MS = 45_000
export const ASYNC_SEARCH_DURATION_MS = 7 * 24 * 60 * 60 * 1_000
export const REALTIME_BOT_MATCH_DELAY_MS = Math.max(1_000, Number(process.env.MOTMAN_REALTIME_BOT_DELAY_MS) || 30_000)
export const ASYNC_BOT_MATCH_DELAY_MS = Math.max(1_000, Number(process.env.MOTMAN_ASYNC_BOT_DELAY_MS) || 30_000)
export const MAX_ASYNC_MATCHES = 3
export const RECENT_GRID_HISTORY_LIMIT = 12
