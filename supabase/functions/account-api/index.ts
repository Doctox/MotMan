import { createClient } from '@supabase/supabase-js'
import { validatePlayerName } from '../../../src/playerNamePolicy.ts'
import { basketRarityProbabilities, type RewardRarity } from '../../../src/progressionRewards.ts'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, apikey, content-type, x-client-info',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}

const starterItems = {
  avatar: 'plume-motman',
  frame: 'cadre-ivoire',
  animation: 'animation-none',
} as const

const cosmeticKinds = ['avatar', 'frame', 'animation'] as const
type CosmeticKind = typeof cosmeticKinds[number]

function cosmeticColumn(kind: CosmeticKind): 'avatar_id' | 'frame_id' | 'animation_id' {
  return kind === 'avatar' ? 'avatar_id' : kind === 'frame' ? 'frame_id' : 'animation_id'
}

function cosmeticInput(body: Record<string, unknown>): { kind: CosmeticKind; id: string } | null {
  const kind = typeof body.kind === 'string' && cosmeticKinds.includes(body.kind as CosmeticKind) ? body.kind as CosmeticKind : null
  const id = typeof body.id === 'string' && /^[a-z0-9-]{1,64}$/i.test(body.id) ? body.id : null
  return kind && id ? { kind, id } : null
}

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
  })
}

function normalizeName(value: unknown): { valid: boolean; name: string; error?: string } {
  const checked = validatePlayerName(typeof value === 'string' ? value : '')
  return { valid: checked.valid, name: checked.normalized, error: checked.error }
}

function experienceGoal(level: number): number {
  return level >= 50 ? 0 : 100 + Math.max(0, level - 1) * 15
}

function awardBreakdown(award: Record<string, unknown>) {
  const mode = award.mode === 'solo' ? 'solo' : 'multiplayer'
  const outcome = String(award.outcome)
  const productiveTurns = Math.max(0, Number(award.productive_turns) || 0)
  const productiveXp = productiveTurns * (mode === 'solo' ? 1 : 2)
  const completed = ['win', 'draw', 'loss'].includes(outcome)
  const completionXp = completed ? mode === 'solo' ? 5 : 10 : 0
  const total = Math.max(0, Number(award.xp_amount) || 0)
  return { productiveTurns, productiveXp, completionXp, resultXp: Math.max(0, total - productiveXp - completionXp), total }
}

async function accountState(admin: ReturnType<typeof createClient>, userId: string) {
  const [
    { data: profile }, { data: progress }, { data: wallet }, { data: inventory }, { data: awardRows },
    { data: titleCatalog }, { data: ownedTitles }, { data: cosmeticCatalog },
  ] = await Promise.all([
    admin.from('profiles').select('*').eq('id', userId).single(),
    admin.from('player_progress').select('*').eq('user_id', userId).single(),
    admin.from('player_wallets').select('*').eq('user_id', userId).single(),
    admin.from('player_inventory').select('kind,item_id').eq('user_id', userId),
    admin.from('experience_awards').select('*').eq('user_id', userId).order('created_at', { ascending: false }).limit(200),
    admin.from('server_title_catalog').select('id,name,description,unlock_type,required_value,sort_order').eq('active', true).order('sort_order'),
    admin.from('player_titles').select('title_id,source,unlocked_at').eq('user_id', userId),
    admin.from('server_cosmetic_catalog').select('kind,item_id,rarity').eq('active', true).eq('availability', 'epicerie'),
  ])
  if (!profile || !progress || !wallet) throw new Error('Profil serveur incomplet.')
  const items = inventory ?? []
  const ownedKeys = new Set(items.map(item => `${item.kind}:${item.item_id}`))
  const availableRarities = new Set<RewardRarity>((cosmeticCatalog ?? [])
    .filter(item => !ownedKeys.has(`${item.kind}:${item.item_id}`))
    .map(item => item.rarity as RewardRarity))
  const basketOdds = basketRarityProbabilities(wallet.basket_pity, availableRarities)
  const unlockedTitleMap = new Map((ownedTitles ?? []).map(title => [title.title_id, title]))
  const titles = (titleCatalog ?? []).map(title => ({
    id: title.id,
    name: title.name,
    description: title.description,
    unlockType: title.unlock_type,
    requiredValue: title.required_value,
    unlocked: unlockedTitleMap.has(title.id),
    unlockedAt: unlockedTitleMap.get(title.id)?.unlocked_at ?? null,
  }))
  const titleById = new Map(titles.map(title => [title.id, title]))
  return {
    identity: {
      version: 2,
      playerId: userId,
      displayName: profile.display_name,
      accountType: profile.account_kind,
      friendCode: profile.friend_code,
      createdAt: profile.created_at,
    },
    progress: {
      version: 3, playerId: userId, level: progress.level, xp: progress.xp,
      lifetimeXp: progress.lifetime_xp, rankedPoints: progress.ranked_points, rankedDivision: null,
      wins: progress.wins, losses: progress.losses, activeMatchIds: [], invitationIds: [],
      equippedTitleId: profile.title_id,
      titles,
      experienceAwards: (awardRows ?? []).reverse().map(award => ({
        id: `server:${award.idempotency_key}`,
        mode: award.mode,
        outcome: award.outcome,
        breakdown: awardBreakdown(award),
        levelBefore: award.level_before,
        levelAfter: award.level_after,
        xpAfter: progress.xp,
        xpGoalAfter: experienceGoal(progress.level),
        plumesEarned: award.feather_amount,
        featherBreakdown: award.feather_breakdown ?? {},
        unlockedTitles: (award.unlocked_title_ids ?? []).map((id: string) => titleById.get(id)).filter(Boolean),
        createdAt: award.created_at,
      })),
    },
    cosmetics: {
      version: 1, playerId: userId, plumes: Number(wallet.feathers),
      ownedAvatarIds: items.filter(item => item.kind === 'avatar').map(item => item.item_id),
      ownedFrameIds: items.filter(item => item.kind === 'frame').map(item => item.item_id),
      ownedAnimationIds: items.filter(item => item.kind === 'animation').map(item => item.item_id),
      equippedAvatarId: profile.avatar_id, equippedFrameId: profile.frame_id,
      equippedAnimationId: profile.animation_id, openedBaskets: wallet.opened_baskets,
      basketPity: wallet.basket_pity, basketOdds, transactions: [],
    },
  }
}

Deno.serve(async request => {
  if (request.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })
  if (request.method !== 'POST') return json(405, { error: 'Méthode non autorisée.' })
  const authorization = request.headers.get('Authorization') ?? ''
  const token = authorization.replace(/^Bearer\s+/i, '')
  const url = Deno.env.get('SUPABASE_URL')!
  const anonKey = Deno.env.get('SUPABASE_ANON_KEY')!
  const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
  const authClient = createClient(url, anonKey, { global: { headers: { Authorization: authorization } }, auth: { persistSession: false } })
  const { data: { user }, error: authError } = await authClient.auth.getUser(token)
  if (authError || !user) return json(401, { error: 'Session invalide.' })
  const admin = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } })
  const { data: accessProfile } = await admin.from('profiles').select('status').eq('id', user.id).single()
  if (accessProfile?.status === 'banned') return json(403, { error: 'Ce compte a été banni.' })
  if (accessProfile?.status === 'suspended') return json(403, { error: 'Ce compte est temporairement suspendu.' })
  if (!user.is_anonymous) await admin.from('profiles').update({ account_kind: 'account', updated_at: new Date().toISOString() }).eq('id', user.id)
  let body: Record<string, unknown>
  try { body = await request.json() } catch { return json(400, { error: 'Requête invalide.' }) }
  const action = typeof body.action === 'string' ? body.action : 'state'

  try {
    if (action === 'bootstrap') {
      const { data: profile } = await admin.from('profiles').select('legacy_imported_at').eq('id', user.id).single()
      if (profile && !profile.legacy_imported_at) {
        const identity = body.identity && typeof body.identity === 'object' ? body.identity as Record<string, unknown> : {}
        const checkedName = normalizeName(identity.displayName)
        // Scores, feathers and inventory are initialized by Postgres. Trusting
        // localStorage here would let a player mint their own rewards.
        await admin.from('profiles').update({
          ...(checkedName.valid ? { display_name: checkedName.name } : {}),
          legacy_imported_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        }).eq('id', user.id)
      }
    } else if (action === 'update-profile') {
      const checkedName = normalizeName(body.displayName)
      if (!checkedName.valid) return json(400, { error: checkedName.error })
      const avatarId = typeof body.avatarId === 'string' ? body.avatarId : starterItems.avatar
      const frameId = typeof body.frameId === 'string' ? body.frameId : starterItems.frame
      const animationId = typeof body.animationId === 'string' ? body.animationId : starterItems.animation
      const titleId = typeof body.titleId === 'string' && body.titleId ? body.titleId : null
      const [{ data: owned }, { data: ownedTitle }] = await Promise.all([
        admin.from('player_inventory').select('kind,item_id').eq('user_id', user.id),
        titleId ? admin.from('player_titles').select('title_id').eq('user_id', user.id).eq('title_id', titleId).maybeSingle() : Promise.resolve({ data: null }),
      ])
      const owns = (kind: string, id: string) => (owned ?? []).some(item => item.kind === kind && item.item_id === id)
      if (!owns('avatar', avatarId) || !owns('frame', frameId) || !owns('animation', animationId)) return json(403, { error: 'Élément de profil non possédé.' })
      if (titleId && !ownedTitle) return json(403, { error: 'Titre non débloqué.' })
      const { error } = await admin.from('profiles').update({ display_name: checkedName.name, avatar_id: avatarId, frame_id: frameId, animation_id: animationId, title_id: titleId, updated_at: new Date().toISOString() }).eq('id', user.id)
      if (error?.code === '23505') return json(409, { error: 'Ce pseudo est déjà utilisé.' })
      if (error) throw error
    } else if (action === 'equip-cosmetic') {
      const cosmetic = cosmeticInput(body)
      if (!cosmetic) return json(400, { error: 'Élément invalide.' })
      const { data: owned } = await admin.from('player_inventory').select('item_id').eq('user_id', user.id).eq('kind', cosmetic.kind).eq('item_id', cosmetic.id).maybeSingle()
      if (!owned) return json(403, { error: 'Élément non possédé.' })
      const { error } = await admin.from('profiles').update({ [cosmeticColumn(cosmetic.kind)]: cosmetic.id, updated_at: new Date().toISOString() }).eq('id', user.id)
      if (error) throw error
    } else if (action === 'purchase-cosmetic') {
      const cosmetic = cosmeticInput(body)
      if (!cosmetic) return json(400, { error: 'Élément invalide.' })
      const idempotencyKey = typeof body.idempotencyKey === 'string' && /^[a-zA-Z0-9:_-]{8,100}$/.test(body.idempotencyKey) ? body.idempotencyKey : crypto.randomUUID()
      const { error } = await admin.rpc('server_purchase_cosmetic', {
        p_user_id: user.id, p_kind: cosmetic.kind, p_item_id: cosmetic.id, p_idempotency_key: idempotencyKey,
      })
      if (error) throw error
      const { error: equipError } = await admin.from('profiles').update({ [cosmeticColumn(cosmetic.kind)]: cosmetic.id, updated_at: new Date().toISOString() }).eq('id', user.id)
      if (equipError) throw equipError
    } else if (action === 'open-basket') {
      const basketId = typeof body.basketId === 'string' && /^[a-z0-9-]{1,64}$/i.test(body.basketId) ? body.basketId : ''
      if (!basketId) return json(400, { error: 'Panier invalide.' })
      const idempotencyKey = typeof body.idempotencyKey === 'string' && /^[a-zA-Z0-9:_-]{8,100}$/.test(body.idempotencyKey) ? body.idempotencyKey : crypto.randomUUID()
      const { data: reward, error } = await admin.rpc('server_open_basket', {
        p_user_id: user.id, p_basket_id: basketId, p_idempotency_key: idempotencyKey,
      })
      if (error) throw error
      return json(200, { ...(await accountState(admin, user.id)), reward })
    } else if (action !== 'state') return json(404, { error: 'Action inconnue.' })
    return json(200, await accountState(admin, user.id))
  } catch (error) {
    console.error(error)
    const message = error instanceof Error ? error.message : 'Erreur du compte.'
    return json(message.includes('plumes') || message.includes('posséd') || message.includes('collection') || message.includes('indisponible') ? 400 : 500, { error: message })
  }
})
