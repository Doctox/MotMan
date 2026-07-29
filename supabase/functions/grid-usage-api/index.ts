import { createClient } from '@supabase/supabase-js'
import { createHttpResponder, logServerError } from '../_shared/http.ts'
import { enforceRateLimits, RateLimitExceededError } from '../_shared/rateLimit.ts'
import {
  buildGridUsageSnapshot,
  type PopularityRow,
  type RecentHistoryRow,
} from './snapshot.ts'

Deno.serve(async request => {
  const http = createHttpResponder(request, Deno.env.get('MOTMAN_ALLOWED_ORIGINS'))
  const { json } = http
  if (request.method === 'OPTIONS') return http.preflight()
  if (!http.originAllowed) return json(403, { error: 'Origine non autorisée.', code: 'ORIGIN_NOT_ALLOWED' })
  if (request.method !== 'POST') return json(405, { error: 'Méthode non autorisée.' })

  const authorization = request.headers.get('Authorization') ?? ''
  const token = authorization.replace(/^Bearer\s+/i, '')
  if (!token) return json(401, { error: 'Session invalide.' })

  const url = Deno.env.get('SUPABASE_URL')!
  const anonKey = Deno.env.get('SUPABASE_ANON_KEY')!
  const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
  const authClient = createClient(url, anonKey, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false },
  })
  const { data: { user }, error: authError } = await authClient.auth.getUser(token)
  if (authError || !user) return json(401, { error: 'Session invalide.' })

  let body: Record<string, unknown>
  try {
    body = await request.json()
  } catch {
    return json(400, { error: 'Requête invalide.' })
  }
  const action = typeof body.action === 'string' ? body.action : 'snapshot'
  if (action !== 'snapshot') return json(404, { error: 'Action inconnue.' })

  const admin = createClient(url, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  })

  try {
    const { data: accessProfile, error: profileError } = await admin
      .from('profiles')
      .select('status')
      .eq('id', user.id)
      .single()
    if (profileError) throw profileError
    if (accessProfile?.status === 'banned') return json(403, { error: 'Ce compte a été banni.' })
    if (accessProfile?.status === 'suspended') {
      return json(403, { error: 'Ce compte est temporairement suspendu.' })
    }

    await enforceRateLimits(admin, 'account', user.id, user.is_anonymous === true, 'grid-usage-snapshot')

    const [
      { data: popularityRows, error: popularityError },
      { data: recentRows, error: recentError },
    ] = await Promise.all([
      admin
        .from('grid_popularity')
        .select('grid_id,plays,completions,positive_reviews,negative_reviews,average_duration_seconds,popularity_score')
        .order('grid_id'),
      admin
        .from('grid_player_history')
        .select('grid_id,completed_at')
        .eq('user_id', user.id)
        .order('completed_at', { ascending: false })
        .limit(12),
    ])
    if (popularityError) throw popularityError
    if (recentError) throw recentError

    return json(200, buildGridUsageSnapshot(
      (popularityRows ?? []) as PopularityRow[],
      (recentRows ?? []) as RecentHistoryRow[],
    ))
  } catch (error) {
    if (error instanceof RateLimitExceededError) {
      return json(429, {
        error: 'Trop de requêtes. Réessayez dans un instant.',
        code: 'RATE_LIMITED',
        retryAfter: error.retryAfterSeconds,
      }, { 'Retry-After': String(error.retryAfterSeconds) })
    }
    const reference = logServerError('grid-usage-api', error, { action, userId: user.id })
    return json(500, {
      error: 'L’historique des grilles est momentanément indisponible. Réessayez.',
      code: 'GRID_USAGE_SERVICE_UNAVAILABLE',
      reference,
    })
  }
})
