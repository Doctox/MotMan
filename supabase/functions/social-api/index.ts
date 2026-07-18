import { createClient } from '@supabase/supabase-js'

const cors = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'authorization, apikey, content-type, x-client-info', 'Access-Control-Allow-Methods': 'POST, OPTIONS' }
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { ...cors, 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } })

Deno.serve(async request => {
  if (request.method === 'OPTIONS') return new Response('ok', { headers: cors })
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

  const publicProfile = async (id: string) => {
    const { data } = await admin.from('profiles').select('id,display_name,friend_code,avatar_id,frame_id,animation_id,activity,last_seen').eq('id', id).single()
    if (!data) return null
    const online = Date.now() - new Date(data.last_seen).getTime() < 30000
    return { playerId: data.id, displayName: data.display_name, code: data.friend_code, online, activity: online ? data.activity : 'offline', avatarId: data.avatar_id, frameId: data.frame_id, animationId: data.animation_id }
  }
  const state = async () => {
    const [{ data: friendshipRows }, { data: incomingRows }, { data: outgoingRows }, { data: blockedRows }] = await Promise.all([
      admin.from('friendships').select('*').or(`left_user_id.eq.${user.id},right_user_id.eq.${user.id}`),
      admin.from('friend_requests').select('*').eq('to_user_id', user.id),
      admin.from('friend_requests').select('*').eq('from_user_id', user.id),
      admin.from('blocks').select('*').eq('owner_id', user.id),
    ])
    const friends = (await Promise.all((friendshipRows ?? []).map(async row => ({ user: await publicProfile(row.left_user_id === user.id ? row.right_user_id : row.left_user_id), since: row.created_at })))).flatMap(item => item.user ? [{ ...item.user, since: item.since }] : [])
    const incoming = (await Promise.all((incomingRows ?? []).map(async row => ({ id: row.id, createdAt: row.created_at, user: await publicProfile(row.from_user_id) })))).filter(item => item.user)
    const outgoing = (await Promise.all((outgoingRows ?? []).map(async row => ({ id: row.id, createdAt: row.created_at, user: await publicProfile(row.to_user_id) })))).filter(item => item.user)
    const blocked = (await Promise.all((blockedRows ?? []).map(async row => ({ user: await publicProfile(row.blocked_id), blockedAt: row.created_at })))).flatMap(item => item.user ? [{ ...item.user, blockedAt: item.blockedAt }] : [])
    return { friends, incoming, outgoing, blocked }
  }

  try {
    if (action === 'state' || action === 'presence') {
      await admin.from('profiles').update({ activity: body.activity === 'playing' ? 'playing' : 'online', last_seen: new Date().toISOString() }).eq('id', user.id)
    } else if (action === 'request') {
      const { count: pendingCount } = await admin.from('friend_requests').select('id', { count: 'exact', head: true }).eq('from_user_id', user.id)
      if ((pendingCount ?? 0) >= 20) return json(429, { error: 'Vous avez trop de demandes en attente.' })
      const friendCode = typeof body.friendCode === 'string' ? body.friendCode.toUpperCase().replace(/[^A-F0-9]/g, '').slice(0, 8) : ''
      const { data: target } = await admin.from('profiles').select('id').eq('friend_code', friendCode).single()
      if (!target) return json(404, { error: 'Code ami inconnu.' })
      if (target.id === user.id) return json(400, { error: 'Vous ne pouvez pas vous ajouter vous-même.' })
      const { data: blocked } = await admin.from('blocks').select('owner_id').or(`and(owner_id.eq.${user.id},blocked_id.eq.${target.id}),and(owner_id.eq.${target.id},blocked_id.eq.${user.id})`).limit(1)
      if (blocked?.length) return json(409, { error: 'Cette demande ne peut pas être envoyée.' })
      const { data: reverse } = await admin.from('friend_requests').select('id').eq('from_user_id', target.id).eq('to_user_id', user.id).maybeSingle()
      if (reverse) {
        const [left, right] = [user.id, target.id].sort()
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
    console.error(error)
    return json(500, { error: error instanceof Error ? error.message : 'Erreur sociale.' })
  }
})
