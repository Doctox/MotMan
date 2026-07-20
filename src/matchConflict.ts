export const MATCH_STATE_CONFLICT_CODE = 'match_state_conflict'

type MatchConflictFailure = {
  status?: unknown
  payload?: unknown
}

export function matchStateFromConflict<T>(reason: unknown): T | null {
  if (!reason || typeof reason !== 'object') return null
  const failure = reason as MatchConflictFailure
  if (failure.status !== 409 || !failure.payload || typeof failure.payload !== 'object') return null
  const payload = failure.payload as Record<string, unknown>
  if (payload.code !== MATCH_STATE_CONFLICT_CODE || payload.conflict !== true) return null
  return payload.match && typeof payload.match === 'object' ? payload.match as T : null
}
