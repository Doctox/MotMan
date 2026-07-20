import type { SupabaseClient } from '@supabase/supabase-js'
import { actionRateLimits, globalRateLimit, type ProtectedApi, type RateLimitPolicy } from '../../../src/rateLimitPolicies.ts'

type RateLimitRow = {
  allowed: boolean
  remaining: number
  retry_after_seconds: number
}

export class RateLimitExceededError extends Error {
  constructor(readonly retryAfterSeconds: number) {
    super('Trop de demandes. Patientez un instant puis réessayez.')
    this.name = 'RateLimitExceededError'
  }
}

async function consume(admin: SupabaseClient, userId: string, policy: RateLimitPolicy): Promise<void> {
  const { data, error } = await admin.rpc('server_consume_rate_limit', {
    p_subject_id: userId,
    p_bucket: policy.bucket,
    p_max_requests: policy.maxRequests,
    p_window_seconds: policy.windowSeconds,
  })
  if (error) throw error
  const row = (Array.isArray(data) ? data[0] : data) as RateLimitRow | null
  if (!row) throw new Error('Le contrôle de débit est indisponible.')
  if (!row.allowed) throw new RateLimitExceededError(Math.max(1, Number(row.retry_after_seconds) || 1))
}

export async function enforceRateLimits(
  admin: SupabaseClient,
  api: ProtectedApi,
  userId: string,
  isAnonymous: boolean,
  action: string,
  targetId?: string,
): Promise<void> {
  await consume(admin, userId, globalRateLimit(api, isAnonymous))
  for (const policy of actionRateLimits(api, action, isAnonymous, targetId)) {
    await consume(admin, userId, policy)
  }
}
