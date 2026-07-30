import { createClient } from '@supabase/supabase-js'
import { requiredAndroidUpdate } from '../_shared/clientVersion.ts'
import { createHttpResponder, logServerError } from '../_shared/http.ts'
import { loadPublicProfiles } from '../_shared/publicProfiles.ts'
import { enforceRateLimits, RateLimitExceededError } from '../_shared/rateLimit.ts'
import {
  escapePostgresLikePattern,
  isValidSocialSearch,
  normalizeSocialSearch,
  SOCIAL_SEARCH_RESULT_LIMIT,
} from '../../../src/socialSearchPolicy.ts'

const UUID_PATTERN = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i

Deno.serve(async request => {
  const http = createHttpResponder(request, Deno.env.get('MOTMAN_ALLOWED_ORIGINS'))
  const { json } = http
  if (request.method === 'OPTIONS') return http.preflight()
  if (!http.originAllowed) return json(403, { error: 'Origine non autorisée.', code: 'ORIGIN_NOT_ALLOWED' })
  if (request.method !== 'POST') return json(405, { error: 'Méthode non autorisée.' })
  const authorization = request.headers.get('Authorization') ?? ''
  const url = Deno.env.get('SUPABASE_URL')!
  const authClient = createClient(url, Deno.env.get('SUPABASE_ANON_KEY')!, { global: { headers: { Authorization: authorization } }, auth: { persistSession: false } })
  const { data: { user } } = await authClient.auth.getUser(authorization.replace(/^Bearer\s+/i, ''))
  if (!user) return json(401, { error: 'Session invalide.' })
  const admin = createClient(url, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!, { auth: { persistSession: false, autoRefreshToken: false } })
  const { data: accessProfile } = await admin.from('profiles').select('status,role').eq('id', user.id).single()
  if (accessProfile?.status === 'banned') return json(403, { error: 'Ce compte a été banni.' })
  if (accessProfile?.status === 'suspended') return json(403, { error: 'Ce compte est temporairement suspendu.' })
  let body: Record<string, unknown>
  try { body = await request.json() } catch { return json(400, { error: 'Requête invalide.' }) }
  const action = typeof body.action === 'string' ? body.action : 'state'
  const appUpdate = await requiredAndroidUpdate(request, admin)
  if (appUpdate) {
    return json(426, {
      error: 'Une mise à jour de MotMan est nécessaire pour continuer.',
      code: 'APP_UPDATE_REQUIRED',
      ...appUpdate,
    })
  }

  const state = async () => {
    const [{ data: friendshipRows }, { data: incomingRows }, { data: outgoingRows }, { data: blockedRows }] = await Promise.all([
      admin.from('friendships').select('*').or(`left_user_id.eq.${user.id},right_user_id.eq.${user.id}`),
      admin.from('friend_requests').select('*').eq('to_user_id', user.id),
      admin.from('friend_requests').select('*').eq('from_user_id', user.id),
      admin.from('blocks').select('*').eq('owner_id', user.id),
    ])
    const profileIds = [
      ...(friendshipRows ?? []).map(row => row.left_user_id === user.id ? row.right_user_id : row.left_user_id),
      ...(incomingRows ?? []).map(row => row.from_user_id),
      ...(outgoingRows ?? []).map(row => row.to_user_id),
      ...(blockedRows ?? []).map(row => row.blocked_id),
    ]
    const profiles = await loadPublicProfiles(admin, profileIds, { normalizeOfflineActivity: true })
    const friends = (friendshipRows ?? []).flatMap(row => {
      const friendId = row.left_user_id === user.id ? row.right_user_id : row.left_user_id
      const friend = profiles.get(friendId)
      return friend ? [{ ...friend, since: row.created_at }] : []
    })
    const incoming = (incomingRows ?? []).map(row => ({
      id: row.id,
      createdAt: row.created_at,
      user: profiles.get(row.from_user_id) ?? null,
    })).filter(item => item.user)
    const outgoing = (outgoingRows ?? []).map(row => ({
      id: row.id,
      createdAt: row.created_at,
      user: profiles.get(row.to_user_id) ?? null,
    })).filter(item => item.user)
    const blocked = (blockedRows ?? []).flatMap(row => {
      const blockedUser = profiles.get(row.blocked_id)
      return blockedUser ? [{ ...blockedUser, blockedAt: row.created_at }] : []
    })
    return { friends, incoming, outgoing, blocked }
  }

  try {
    await enforceRateLimits(admin, 'social', user.id, user.is_anonymous === true, action)
    if (action === 'search') {
      const query = normalizeSocialSearch(body.query)
      if (!isValidSocialSearch(query)) {
        return json(400, { error: 'Entre au moins 3 caractères du pseudo recherché.' })
      }
      const escapedPrefix = `${escapePostgresLikePattern(query)}%`
      const [
        { data: candidateRows, error: candidateError },
        { data: friendshipRows, error: friendshipError },
        { data: incomingRows, error: incomingError },
        { data: outgoingRows, error: outgoingError },
        { data: blockRows, error: blockError },
      ] = await Promise.all([
        admin.from('profiles').select('id').eq('status', 'active').neq('id', user.id)
          .ilike('display_name', escapedPrefix).order('display_name').limit(SOCIAL_SEARCH_RESULT_LIMIT * 3),
        admin.from('friendships').select('left_user_id,right_user_id').or(`left_user_id.eq.${user.id},right_user_id.eq.${user.id}`),
        admin.from('friend_requests').select('from_user_id').eq('to_user_id', user.id),
        admin.from('friend_requests').select('to_user_id').eq('from_user_id', user.id),
        admin.from('blocks').select('owner_id,blocked_id').or(`owner_id.eq.${user.id},blocked_id.eq.${user.id}`),
      ])
      const searchError = candidateError ?? friendshipError ?? incomingError ?? outgoingError ?? blockError
      if (searchError) throw searchError

      const blockedIds = new Set((blockRows ?? []).map(row => row.owner_id === user.id ? row.blocked_id : row.owner_id))
      const friendIds = new Set((friendshipRows ?? []).map(row => row.left_user_id === user.id ? row.right_user_id : row.left_user_id))
      const incomingIds = new Set((incomingRows ?? []).map(row => row.from_user_id))
      const outgoingIds = new Set((outgoingRows ?? []).map(row => row.to_user_id))
      const candidateIds = (candidateRows ?? []).map(row => row.id).filter(id => !blockedIds.has(id))
      const profiles = await loadPublicProfiles(admin, candidateIds, { normalizeOfflineActivity: true })
      const normalizedQuery = query.toLocaleLowerCase('fr')
      const results = [...profiles.values()]
        .sort((left, right) => {
          const leftExact = left.displayName.toLocaleLowerCase('fr') === normalizedQuery ? 0 : 1
          const rightExact = right.displayName.toLocaleLowerCase('fr') === normalizedQuery ? 0 : 1
          return leftExact - rightExact || left.displayName.localeCompare(right.displayName, 'fr', { sensitivity: 'base' })
        })
        .slice(0, SOCIAL_SEARCH_RESULT_LIMIT)
        .map(({ code: _privateFriendCode, ...profile }) => ({
          ...profile,
          relation: friendIds.has(profile.playerId) ? 'friend'
            : outgoingIds.has(profile.playerId) ? 'outgoing'
              : incomingIds.has(profile.playerId) ? 'incoming'
                : 'available',
        }))
      return json(200, { ok: true, results })
    } else if (action === 'presence') {
      await admin.from('profiles').update({ activity: body.activity === 'playing' ? 'playing' : 'online', last_seen: new Date().toISOString() }).eq('id', user.id)
    } else if (action === 'request') {
      const { count: pendingCount } = await admin.from('friend_requests').select('id', { count: 'exact', head: true }).eq('from_user_id', user.id)
      if ((pendingCount ?? 0) >= 20) return json(429, { error: 'Vous avez trop de demandes en attente.' })
      const friendCode = typeof body.friendCode === 'string' ? body.friendCode.toUpperCase().replace(/[^A-F0-9]/g, '').slice(0, 8) : ''
      const targetId = typeof body.targetId === 'string' && UUID_PATTERN.test(body.targetId) ? body.targetId : ''
      const targetQuery = admin.from('profiles').select('id').eq('status', 'active')
      const { data: target } = targetId
        ? await targetQuery.eq('id', targetId).maybeSingle()
        : await targetQuery.eq('friend_code', friendCode).maybeSingle()
      if (!target) return json(404, { error: targetId ? 'Joueur introuvable.' : 'Code ami inconnu.' })
      if (target.id === user.id) return json(400, { error: 'Vous ne pouvez pas vous ajouter vous-même.' })
      const { data: blocked } = await admin.from('blocks').select('owner_id').or(`and(owner_id.eq.${user.id},blocked_id.eq.${target.id}),and(owner_id.eq.${target.id},blocked_id.eq.${user.id})`).limit(1)
      if (blocked?.length) return json(409, { error: 'Cette demande ne peut pas être envoyée.' })
      const [left, right] = [user.id, target.id].sort()
      const { data: existingFriendship } = await admin.from('friendships').select('left_user_id')
        .eq('left_user_id', left).eq('right_user_id', right).maybeSingle()
      if (existingFriendship) return json(409, { error: 'Ce joueur est déjà dans vos amis.' })
      const { data: reverse } = await admin.from('friend_requests').select('id').eq('from_user_id', target.id).eq('to_user_id', user.id).maybeSingle()
      if (reverse) {
        await admin.from('friend_requests').delete().eq('id', reverse.id)
        await admin.from('friendships').upsert({ left_user_id: left, right_user_id: right })
      } else await admin.from('friend_requests').upsert({ from_user_id: user.id, to_user_id: target.id }, { onConflict: 'from_user_id,to_user_id' })
    } else if (action === 'respond') {
      const requestId = typeof body.requestId === 'string' ? body.requestId : ''
      const { data: pending } = await admin.from('friend_requests').select('*').eq('id', requestId).eq('to_user_id', user.id).single()
      if (!pending) return json(404, { error: 'Cette demande n’existe plus.' })
      await admin.from('friend_requests').delete().eq('id', requestId)
      if (body.decision === 'accept') {
        const [left, right] = [user.id, pending.from_user_id].sort()
        await admin.from('friendships').upsert({ left_user_id: left, right_user_id: right })
      }
    } else if (action === 'moderation-list' || action === 'moderation-resolve') {
      if (!['moderator', 'admin'].includes(accessProfile?.role ?? 'player')) return json(403, { error: 'Accès modération refusé.' })
      if (action === 'moderation-list') {
        const { data: reports } = await admin.from('reports').select('*').eq('status', 'open').order('created_at').limit(100)
        return json(200, { ok: true, reports: reports ?? [] })
      }
      const reportId = typeof body.reportId === 'string' ? body.reportId : ''
      const decision = typeof body.decision === 'string' ? body.decision : ''
      if (!['dismiss', 'warn', 'suspend', 'ban'].includes(decision)) return json(400, { error: 'Décision invalide.' })
      const { data: report } = await admin.from('reports').select('reported_id').eq('id', reportId).eq('status', 'open').single()
      if (!report) return json(404, { error: 'Signalement introuvable.' })
      if (decision === 'suspend' || decision === 'ban') await admin.from('profiles').update({ status: decision === 'ban' ? 'banned' : 'suspended', updated_at: new Date().toISOString() }).eq('id', report.reported_id)
      await admin.from('reports').update({ status: decision === 'dismiss' ? 'dismissed' : 'actioned', reviewed_at: new Date().toISOString(), reviewed_by: user.id }).eq('id', reportId)
      return json(200, { ok: true })
    } else {
      const targetId = typeof body.targetId === 'string' ? body.targetId : ''
      if (!targetId || targetId === user.id) return json(400, { error: 'Joueur invalide.' })
      const [left, right] = [user.id, targetId].sort()
      if (action === 'cancel') await admin.from('friend_requests').delete().eq('from_user_id', user.id).eq('to_user_id', targetId)
      else if (action === 'remove') await admin.from('friendships').delete().eq('left_user_id', left).eq('right_user_id', right)
      else if (action === 'block') {
        await admin.from('friendships').delete().eq('left_user_id', left).eq('right_user_id', right)
        await admin.from('friend_requests').delete().or(`and(from_user_id.eq.${user.id},to_user_id.eq.${targetId}),and(from_user_id.eq.${targetId},to_user_id.eq.${user.id})`)
        await admin.from('blocks').upsert({ owner_id: user.id, blocked_id: targetId })
      } else if (action === 'unblock') await admin.from('blocks').delete().eq('owner_id', user.id).eq('blocked_id', targetId)
      else if (action === 'report') {
        const allowed = ['pseudo','comportement','triche','harcelement','autre']
        const since = new Date(Date.now() - 60 * 60 * 1000).toISOString()
        const { count } = await admin.from('reports').select('id', { count: 'exact', head: true }).eq('reporter_id', user.id).gte('created_at', since)
        if ((count ?? 0) >= 5) return json(429, { error: 'Limite de signalements atteinte pour cette heure.' })
        const { data: target } = await admin.from('profiles').select('id').eq('id', targetId).maybeSingle()
        if (!target) return json(404, { error: 'Joueur introuvable.' })
        await admin.from('reports').insert({ reporter_id: user.id, reported_id: targetId, reason: allowed.includes(String(body.reason)) ? body.reason : 'autre', details: typeof body.details === 'string' ? body.details.trim().slice(0, 500) : '', match_id: typeof body.matchId === 'string' ? body.matchId : null })
      } else return json(404, { error: 'Action inconnue.' })
    }
    return json(200, action === 'presence' ? { ok: true } : { ok: true, state: await state() })
  } catch (error) {
    if (error instanceof RateLimitExceededError) {
      return json(429, { error: 'Trop de requêtes. Réessayez dans un instant.', code: 'RATE_LIMITED', retryAfter: error.retryAfterSeconds }, { 'Retry-After': String(error.retryAfterSeconds) })
    }
    const reference = logServerError('social-api', error, { action, userId: user.id })
    return json(500, {
      error: 'Le service Amis est momentanément indisponible. Réessayez.',
      code: 'SOCIAL_SERVICE_UNAVAILABLE',
      reference,
    })
  }
})
