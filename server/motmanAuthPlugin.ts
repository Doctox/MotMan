import { promisify } from 'node:util'
import { createHash, randomBytes, randomUUID, scrypt as scryptCallback, timingSafeEqual } from 'node:crypto'
import type { IncomingMessage, ServerResponse } from 'node:http'
import type { Plugin } from 'vite'
import { validatePlayerName } from '../src/playerNamePolicy'
import {
  authenticatedUser, clearSessionCookie, createSession, database, nowIso, readJsonBody,
  requestHasSameOrigin, revokeSession, sendJson, type DatabaseUser,
} from './motmanDatabase'

const scrypt = promisify(scryptCallback)
const PASSWORD_MIN_LENGTH = 10
const PASSWORD_MAX_LENGTH = 128
const RECOVERY_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

type ClientIdentity = {
  version: 2
  playerId: string
  displayName: string
  accountType: 'guest' | 'account'
  friendCode: string
  createdAt: string
}

function identityFor(user: DatabaseUser): ClientIdentity {
  return {
    version: 2,
    playerId: user.id,
    displayName: user.display_name,
    accountType: user.account_type,
    friendCode: user.friend_code,
    createdAt: user.created_at,
  }
}

function accountStateFor(user: DatabaseUser) {
  const items = database.prepare('SELECT kind, item_id FROM inventory WHERE user_id = ? ORDER BY acquired_at').all(user.id) as Array<{ kind: 'avatar' | 'frame' | 'animation'; item_id: string }>
  return {
    progress: {
      version: 2,
      playerId: user.id,
      level: user.level,
      xp: user.xp,
      lifetimeXp: user.lifetime_xp,
      rankedPoints: user.ranked_points,
      rankedDivision: null,
      wins: user.wins,
      losses: user.losses,
      activeMatchIds: [],
      invitationIds: [],
      experienceAwards: [],
    },
    cosmetics: {
      version: 1,
      playerId: user.id,
      plumes: user.feathers,
      ownedAvatarIds: items.filter(item => item.kind === 'avatar').map(item => item.item_id),
      ownedFrameIds: items.filter(item => item.kind === 'frame').map(item => item.item_id),
      ownedAnimationIds: items.filter(item => item.kind === 'animation').map(item => item.item_id),
      equippedAvatarId: user.equipped_avatar_id,
      equippedFrameId: user.equipped_frame_id,
      equippedAnimationId: user.equipped_animation_id,
      openedBaskets: user.opened_baskets,
      basketPity: user.basket_pity,
      transactions: [],
    },
  }
}

function sessionPayload(user: DatabaseUser, extra: Record<string, unknown> = {}) {
  return { identity: identityFor(user), ...accountStateFor(user), ...extra }
}

function usernameKey(value: string): string {
  return value.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').trim().replace(/\s+/g, ' ').toLocaleLowerCase('fr-FR')
}

function cleanLegacyId(value: unknown): string {
  return typeof value === 'string' && /^guest_[0-9a-f-]{16,}$/i.test(value) ? value : ''
}

function friendCodeFromId(id: string): string {
  const base = id.replace(/^guest_/, '').replace(/[^a-f0-9]/gi, '').slice(0, 8).toUpperCase().padEnd(8, '0')
  if (!database.prepare('SELECT 1 FROM users WHERE friend_code = ?').get(base)) return base
  do {
    const next = randomBytes(4).toString('hex').toUpperCase()
    if (!database.prepare('SELECT 1 FROM users WHERE friend_code = ?').get(next)) return next
  } while (true)
}

async function passwordDigest(password: string, salt: Buffer): Promise<Buffer> {
  return scrypt(password.normalize('NFKC'), salt, 64) as Promise<Buffer>
}

async function makePassword(password: string): Promise<{ hash: string; salt: string }> {
  const salt = randomBytes(16)
  const hash = await passwordDigest(password, salt)
  return { hash: hash.toString('base64'), salt: salt.toString('base64') }
}

async function verifyPassword(password: string, user: DatabaseUser): Promise<boolean> {
  if (!user.password_hash || !user.password_salt) return false
  const expected = Buffer.from(user.password_hash, 'base64')
  const actual = await passwordDigest(password, Buffer.from(user.password_salt, 'base64'))
  return expected.length === actual.length && timingSafeEqual(expected, actual)
}

function makeRecoveryCode(): string {
  const bytes = randomBytes(16)
  let raw = ''
  for (let index = 0; index < 16; index += 1) raw += RECOVERY_ALPHABET[bytes[index] % RECOVERY_ALPHABET.length]
  return raw.match(/.{1,4}/g)?.join('-') ?? raw
}

function recoveryHash(code: string): string {
  const normalized = code.toUpperCase().replace(/[^A-Z0-9]/g, '')
  return createHash('sha256').update(normalized).digest('hex')
}

function validPassword(value: unknown): value is string {
  return typeof value === 'string' && value.length >= PASSWORD_MIN_LENGTH && value.length <= PASSWORD_MAX_LENGTH
}

function inventoryIds(value: unknown, fallback: string, max = 250): string[] {
  if (!Array.isArray(value)) return [fallback]
  return [...new Set([fallback, ...value.filter(item => typeof item === 'string' && /^[a-z0-9-]{1,64}$/i.test(item))])].slice(0, max)
}

function importLegacyState(userId: string, progress: unknown, cosmetics: unknown): void {
  const user = database.prepare('SELECT * FROM users WHERE id = ?').get(userId) as DatabaseUser
  if (user.legacy_imported_at) return
  const now = nowIso()
  const candidateProgress = progress && typeof progress === 'object' ? progress as Record<string, unknown> : {}
  const candidateCosmetics = cosmetics && typeof cosmetics === 'object' ? cosmetics as Record<string, unknown> : {}
  const level = Math.max(1, Math.min(50, Math.floor(Number(candidateProgress.level) || 1)))
  const xp = Math.max(0, Math.min(10_000, Math.floor(Number(candidateProgress.xp) || 0)))
  const lifetimeXp = Math.max(xp, Math.min(10_000_000, Math.floor(Number(candidateProgress.lifetimeXp) || xp)))
  const feathers = Math.max(0, Math.min(1_000_000, Math.floor(Number(candidateCosmetics.plumes) || 600)))
  const avatarIds = inventoryIds(candidateCosmetics.ownedAvatarIds, 'plume-motman')
  const frameIds = inventoryIds(candidateCosmetics.ownedFrameIds, 'cadre-ivoire')
  const animationIds = inventoryIds(candidateCosmetics.ownedAnimationIds, 'animation-none')
  const equippedAvatar = avatarIds.includes(String(candidateCosmetics.equippedAvatarId)) ? String(candidateCosmetics.equippedAvatarId) : 'plume-motman'
  const equippedFrame = frameIds.includes(String(candidateCosmetics.equippedFrameId)) ? String(candidateCosmetics.equippedFrameId) : 'cadre-ivoire'
  const equippedAnimation = animationIds.includes(String(candidateCosmetics.equippedAnimationId)) ? String(candidateCosmetics.equippedAnimationId) : 'animation-none'
  const migrate = database.transaction(() => {
    database.prepare(`UPDATE users SET level=?, xp=?, lifetime_xp=?, ranked_points=?, wins=?, losses=?, feathers=?,
      equipped_avatar_id=?, equipped_frame_id=?, equipped_animation_id=?, opened_baskets=?, basket_pity=?, legacy_imported_at=?, updated_at=? WHERE id=?`)
      .run(level, xp, lifetimeXp, Math.max(0, Math.floor(Number(candidateProgress.rankedPoints) || 0)),
        Math.max(0, Math.floor(Number(candidateProgress.wins) || 0)), Math.max(0, Math.floor(Number(candidateProgress.losses) || 0)),
        feathers, equippedAvatar, equippedFrame, equippedAnimation,
        Math.max(0, Math.floor(Number(candidateCosmetics.openedBaskets) || 0)), Math.max(0, Math.min(20, Math.floor(Number(candidateCosmetics.basketPity) || 0))), now, now, userId)
    const insert = database.prepare('INSERT OR IGNORE INTO inventory(user_id, kind, item_id, acquired_at, source) VALUES (?, ?, ?, ?, ?)')
    for (const id of avatarIds) insert.run(userId, 'avatar', id, now, 'legacy-import')
    for (const id of frameIds) insert.run(userId, 'frame', id, now, 'legacy-import')
    for (const id of animationIds) insert.run(userId, 'animation', id, now, 'legacy-import')
    database.prepare('INSERT OR IGNORE INTO economy_transactions(id, user_id, kind, amount, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?)')
      .run(`legacy:${userId}`, userId, 'legacy-import', feathers, '{}', now)
  })
  migrate()
}

function createGuest(legacyId: string, displayName: string): DatabaseUser {
  const now = nowIso()
  database.prepare(`INSERT INTO users(id, account_type, display_name, friend_code, last_seen, created_at, updated_at)
    VALUES (?, 'guest', ?, ?, ?, ?, ?)`)
    .run(legacyId, displayName, friendCodeFromId(legacyId), now, now, now)
  const insert = database.prepare('INSERT INTO inventory(user_id, kind, item_id, acquired_at, source) VALUES (?, ?, ?, ?, ?)')
  insert.run(legacyId, 'avatar', 'plume-motman', now, 'starter')
  insert.run(legacyId, 'frame', 'cadre-ivoire', now, 'starter')
  insert.run(legacyId, 'animation', 'animation-none', now, 'starter')
  return database.prepare('SELECT * FROM users WHERE id = ?').get(legacyId) as DatabaseUser
}

function currentUser(request: IncomingMessage, response: ServerResponse): DatabaseUser | null {
  const user = authenticatedUser(request)
  if (user) return user
  sendJson(response, 401, { error: 'Votre session a expiré.' })
  return null
}

async function handleAuthRequest(request: IncomingMessage, response: ServerResponse): Promise<void> {
  const url = new URL(request.url ?? '/', 'http://motman.local')
  const route = url.pathname.replace(/^\/api\/auth\/?/, '').replace(/^\/+/, '')
  if (request.method === 'GET' && route === 'session') {
    const user = authenticatedUser(request)
    return sendJson(response, user ? 200 : 401, user ? sessionPayload(user) : { error: 'Aucune session.' })
  }
  if (request.method !== 'POST') return sendJson(response, 405, { error: 'Méthode non autorisée.' })
  if (!requestHasSameOrigin(request)) return sendJson(response, 403, { error: 'Origine refusée.' })
  let body: Record<string, unknown>
  try { body = await readJsonBody(request) } catch { return sendJson(response, 400, { error: 'Requête invalide.' }) }

  if (route === 'bootstrap') {
    const existingSession = authenticatedUser(request)
    if (existingSession) return sendJson(response, 200, sessionPayload(existingSession))
    const legacy = body.identity && typeof body.identity === 'object' ? body.identity as Record<string, unknown> : {}
    const legacyId = cleanLegacyId(legacy.playerId) || `guest_${randomUUID()}`
    const name = validatePlayerName(typeof legacy.displayName === 'string' ? legacy.displayName : '')
    const displayName = name.valid ? name.normalized : `Invité ${Math.floor(1000 + Math.random() * 9000)}`
    let user = database.prepare('SELECT * FROM users WHERE id = ?').get(legacyId) as DatabaseUser | undefined
    if (user?.account_type === 'account') return sendJson(response, 401, { error: 'Ce profil est protégé. Connectez-vous avec son mot de passe.' })
    if (!user) user = createGuest(legacyId, displayName)
    importLegacyState(user.id, body.progress, body.cosmetics)
    user = database.prepare('SELECT * FROM users WHERE id = ?').get(user.id) as DatabaseUser
    createSession(request, response, user.id)
    return sendJson(response, 200, sessionPayload(user))
  }

  if (route === 'register') {
    const user = currentUser(request, response)
    if (!user) return
    if (user.account_type === 'account') return sendJson(response, 409, { error: 'Ce profil possède déjà un compte.' })
    const name = validatePlayerName(typeof body.displayName === 'string' ? body.displayName : '')
    if (!name.valid) return sendJson(response, 400, { error: name.error ?? 'Pseudo invalide.' })
    if (!validPassword(body.password)) return sendJson(response, 400, { error: `Le mot de passe doit contenir entre ${PASSWORD_MIN_LENGTH} et ${PASSWORD_MAX_LENGTH} caractères.` })
    const key = usernameKey(name.normalized)
    if (database.prepare('SELECT 1 FROM users WHERE username_key = ? AND id <> ?').get(key, user.id)) return sendJson(response, 409, { error: 'Ce pseudo est déjà associé à un compte.' })
    const secret = await makePassword(body.password)
    const recoveryCode = makeRecoveryCode()
    const now = nowIso()
    database.prepare(`UPDATE users SET account_type='account', username_key=?, display_name=?, password_hash=?, password_salt=?, recovery_hash=?, updated_at=? WHERE id=?`)
      .run(key, name.normalized, secret.hash, secret.salt, recoveryHash(recoveryCode), now, user.id)
    const updated = database.prepare('SELECT * FROM users WHERE id = ?').get(user.id) as DatabaseUser
    return sendJson(response, 200, sessionPayload(updated, { recoveryCode }))
  }

  if (route === 'login') {
    const key = usernameKey(typeof body.displayName === 'string' ? body.displayName : '')
    const password = typeof body.password === 'string' ? body.password : ''
    const user = database.prepare("SELECT * FROM users WHERE username_key = ? AND account_type = 'account'").get(key) as DatabaseUser | undefined
    if (!user || !await verifyPassword(password, user) || user.status !== 'active') return sendJson(response, 401, { error: 'Pseudo ou mot de passe incorrect.' })
    revokeSession(request)
    createSession(request, response, user.id)
    return sendJson(response, 200, sessionPayload(user))
  }

  if (route === 'recover') {
    const key = usernameKey(typeof body.displayName === 'string' ? body.displayName : '')
    const code = typeof body.recoveryCode === 'string' ? body.recoveryCode : ''
    if (!validPassword(body.newPassword)) return sendJson(response, 400, { error: `Le nouveau mot de passe doit contenir au moins ${PASSWORD_MIN_LENGTH} caractères.` })
    const user = database.prepare("SELECT * FROM users WHERE username_key = ? AND account_type = 'account'").get(key) as DatabaseUser | undefined
    const validCode = user?.recovery_hash && timingSafeEqual(Buffer.from(user.recovery_hash), Buffer.from(recoveryHash(code)))
    if (!user || !validCode || user.status !== 'active') return sendJson(response, 401, { error: 'Pseudo ou code de récupération incorrect.' })
    const password = await makePassword(body.newPassword)
    const recoveryCode = makeRecoveryCode()
    database.transaction(() => {
      database.prepare('UPDATE users SET password_hash=?, password_salt=?, recovery_hash=?, updated_at=? WHERE id=?')
        .run(password.hash, password.salt, recoveryHash(recoveryCode), nowIso(), user.id)
      database.prepare('DELETE FROM sessions WHERE user_id = ?').run(user.id)
    })()
    createSession(request, response, user.id)
    const recovered = database.prepare('SELECT * FROM users WHERE id = ?').get(user.id) as DatabaseUser
    return sendJson(response, 200, sessionPayload(recovered, { recoveryCode }))
  }

  if (route === 'logout') {
    revokeSession(request)
    clearSessionCookie(request, response)
    return sendJson(response, 200, { ok: true })
  }

  return sendJson(response, 404, { error: 'Action inconnue.' })
}

function attachAuthApi(middlewares: { use: (route: string, handler: (request: IncomingMessage, response: ServerResponse) => void) => void }): void {
  middlewares.use('/api/auth', (request, response) => {
    void handleAuthRequest(request, response).catch(error => {
      console.error('[motman-auth]', error)
      if (!response.headersSent) sendJson(response, 500, { error: 'Le service de compte a rencontré une erreur.' })
    })
  })
}

export function motmanAuthPlugin(): Plugin {
  return {
    name: 'motman-auth-api',
    configureServer(server) { attachAuthApi(server.middlewares) },
    configurePreviewServer(server) { attachAuthApi(server.middlewares) },
  }
}
