export type PresenceVisibility = 'visible' | 'hidden'

/**
 * Presence is deliberately independent from social-state loading.
 * Visible clients send one lightweight heartbeat every 25 seconds. Hidden
 * clients slow down, while the TTL keeps enough margin for timer/network jitter.
 */
export const PRESENCE_HEARTBEAT_VISIBLE_MS = 25_000
export const PRESENCE_HEARTBEAT_HIDDEN_MS = 60_000
export const PRESENCE_ONLINE_TTL_MS = 75_000

export function presenceHeartbeatDelay(visibility: PresenceVisibility): number {
  return visibility === 'hidden' ? PRESENCE_HEARTBEAT_HIDDEN_MS : PRESENCE_HEARTBEAT_VISIBLE_MS
}

export function isPresenceOnline(lastSeen: string | number | Date, now = Date.now()): boolean {
  const timestamp = new Date(lastSeen).getTime()
  return Number.isFinite(timestamp) && now - timestamp < PRESENCE_ONLINE_TTL_MS
}
