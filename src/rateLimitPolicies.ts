export type ProtectedApi = 'account' | 'social' | 'match'

export type RateLimitPolicy = {
  bucket: string
  maxRequests: number
  windowSeconds: number
}

const globalLimits: Record<ProtectedApi, { guest: number; account: number }> = {
  account: { guest: 90, account: 180 },
  social: { guest: 90, account: 180 },
  // Realtime wakes are preferred, but a visible match still keeps a slow
  // fallback poll. This ceiling blocks floods without interrupting play.
  match: { guest: 180, account: 300 },
}

export function globalRateLimit(api: ProtectedApi, isAnonymous: boolean): RateLimitPolicy {
  const limits = globalLimits[api]
  return {
    bucket: `${api}:all`,
    maxRequests: isAnonymous ? limits.guest : limits.account,
    windowSeconds: 60,
  }
}

export function actionRateLimits(
  api: ProtectedApi,
  action: string,
  isAnonymous: boolean,
  targetId?: string,
): RateLimitPolicy[] {
  if (api === 'social' && action === 'request') {
    return [{ bucket: 'social:friend-request', maxRequests: isAnonymous ? 8 : 20, windowSeconds: 3600 }]
  }
  if (api === 'social' && action === 'report') {
    return [{ bucket: 'social:report', maxRequests: 5, windowSeconds: 3600 }]
  }
  if (api === 'match' && action === 'search') {
    return [{ bucket: 'match:search', maxRequests: isAnonymous ? 12 : 24, windowSeconds: 300 }]
  }
  if (api === 'match' && action === 'solo') {
    return [{ bucket: 'match:solo', maxRequests: isAnonymous ? 20 : 40, windowSeconds: 600 }]
  }
  if (api === 'match' && action === 'create') {
    const policies: RateLimitPolicy[] = [
      { bucket: 'match:invite', maxRequests: isAnonymous ? 12 : 30, windowSeconds: 1800 },
    ]
    if (targetId && /^[a-f0-9-]{36}$/i.test(targetId)) {
      policies.push({ bucket: `match:invite-target:${targetId.toLowerCase()}`, maxRequests: 6, windowSeconds: 600 })
    }
    return policies
  }
  if (api === 'match' && action === 'feedback') {
    return [{ bucket: 'match:feedback', maxRequests: 20, windowSeconds: 3600 }]
  }
  return []
}
