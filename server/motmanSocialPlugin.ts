import { randomUUID } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { IncomingMessage, ServerResponse } from 'node:http'
import type { Plugin } from 'vite'
import { validatePlayerName } from '../src/playerNamePolicy'
import {
  database, nowIso, readJsonBody, requestHasSameOrigin, requireAuthenticatedUser, sendJson,
  type DatabaseUser,
} from './motmanDatabase'

type PresenceActivity = 'online' | 'playing'
const PRESENCE_TTL_MS = 30_000
const LEGACY_DATABASE_PATH = resolve(process.env.MOTMAN_SOCIAL_DATABASE_PATH ?? '.motman-social.json')

function orderedPair(left: string, right: string): [string, string] {
  return left < right ? [left, right] : [right, left]
}

function cleanCode(value: unknown): string {
  return typeof value === 'string' ? value.toUpperCase().replace(/[^A-F0-9]/g, '').slice(0, 8) : ''
}

function cleanTargetId(value: unknown): string {
  return typeof value === 'string' && /^guest_[0-9a-f-]{16,}$/i.test(value) ? value : ''
}

function importLegacySocialDatabase(): void {
  const alreadyImported = database.prepare("SELECT 1 FROM server_meta WHERE key = 'migration:social-json:v1'").get()
  if (alreadyImported || !existsSync(LEGACY_DATABASE_PATH)) return
  try {
    const legacy = JSON.parse(readFileSync(LEGACY_DATABASE_PATH, 'utf8')) as {
      users?: Array<{ playerId: string; displayName: string; code: string; lastSeen: string; activity?: PresenceActivity; avatarId?: string; frameId?: string; animationId?: string }>
      requests?: Array<{ id: string; fromPlayerId: string; toPlayerId: string; createdAt: string }>
      friendships?: Array<{ playerIds: [string, string]; createdAt: string }>
      blocks?: Array<{ ownerId: string; blockedId: string; createdAt: string }>
    }
    database.transaction(() => {
      const insertUser = database.prepare(`INSERT OR IGNORE INTO users(
        id, account_type, display_name, friend_code, equipped_avatar_id, equipped_frame_id, equipped_animation_id,
        activity, last_seen, created_at, updated_at
      ) VALUES (?, 'guest', ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      const insertItem = database.prepare('INSERT OR IGNORE INTO inventory(user_id, kind, item_id, acquired_at, source) VALUES (?, ?, ?, ?, ?)')
      for (const user of legacy.users ?? []) {
        const id = cleanTargetId(user.playerId)
        const name = validatePlayerName(user.displayName)
        const code = cleanCode(user.code)
        if (!id || !name.valid || code.length !== 8) continue
        const createdAt = user.lastSeen || nowIso()
        insertUser.run(id, name.normalized, code, user.avatarId ?? 'plume-motman', user.frameId ?? 'cadre-ivoire', user.animationId ?? 'animation-none', user.activity ?? 'online', createdAt, createdAt, createdAt)
        insertItem.run(id, 'avatar', user.avatarId ?? 'plume-motman', createdAt, 'legacy-social')
        insertItem.run(id, 'frame', user.frameId ?? 'cadre-ivoire', createdAt, 'legacy-social')
        insertItem.run(id, 'animation', user.animationId ?? 'animation-none', createdAt, 'legacy-social')
      }
      const userExists = database.prepare('SELECT 1 FROM users WHERE id = ?')
      const insertRequest = database.prepare('INSERT OR IGNORE INTO friend_requests(id, from_user_id, to_user_id, created_at) VALUES (?, ?, ?, ?)')
      for (const request of legacy.requests ?? []) if (userExists.get(request.fromPlayerId) && userExists.get(request.toPlayerId))
        insertRequest.run(request.id, request.fromPlayerId, request.toPlayerId, request.createdAt)
      const insertFriend = database.prepare('INSERT OR IGNORE INTO friendships(left_user_id, right_user_id, created_at) VALUES (?, ?, ?)')
      for (const friendship of legacy.friendships ?? []) {
        const [left, right] = orderedPair(...friendship.playerIds)
        if (userExists.get(left) && userExists.get(right)) insertFriend.run(left, right, friendship.createdAt)
      }
      const insertBlock = database.prepare('INSERT OR IGNORE INTO blocks(owner_id, blocked_id, created_at) VALUES (?, ?, ?)')
      for (const block of legacy.blocks ?? []) if (userExists.get(block.ownerId) && userExists.get(block.blockedId))
        insertBlock.run(block.ownerId, block.blockedId, block.createdAt)
      database.prepare('INSERT INTO server_meta(key, value) VALUES (?, ?)')
        .run('migration:social-json:v1', nowIso())
    })()
  } catch (error) {
    console.error('[motman-social] legacy import skipped', error)
  }
}

function publicUser(playerId: string) {
  const user = database.prepare('SELECT * FROM users WHERE id = ?').get(playerId) as DatabaseUser | undefined
  if (!user) return null
  const recent = Date.now() - new Date(user.last_seen).getTime() < PRESENCE_TTL_MS
  return {
    playerId: user.id,
    displayName: user.display_name,
    code: user.friend_code,
    online: recent,
    activity: recent ? user.activity : 'offline',
    avatarId: user.equipped_avatar_id,
    frameId: user.equipped_frame_id,
    animationId: user.equipped_animation_id,
  }
}

function isBlocked(left: string, right: string): boolean {
  return Boolean(database.prepare(`SELECT 1 FROM blocks WHERE
    (owner_id = ? AND blocked_id = ?) OR (owner_id = ? AND blocked_id = ?)`)
    .get(left, right, right, left))
}

function socialState(playerId: string) {
  const friends = (database.prepare(`SELECT left_user_id, right_user_id, created_at FROM friendships
    WHERE left_user_id = ? OR right_user_id = ? ORDER BY created_at DESC`).all(playerId, playerId) as Array<{ left_user_id: string; right_user_id: string; created_at: string }>)
    .flatMap(friendship => {
      const friendId = friendship.left_user_id === playerId ? friendship.right_user_id : friendship.left_user_id
      const user = publicUser(friendId)
      return user ? [{ ...user, since: friendship.created_at }] : []
    })
  const incoming = (database.prepare('SELECT * FROM friend_requests WHERE to_user_id = ? ORDER BY created_at DESC').all(playerId) as Array<{ id: string; from_user_id: string; created_at: string }>)
    .flatMap(request => {
      const user = publicUser(request.from_user_id)
      return user ? [{ id: request.id, createdAt: request.created_at, user }] : []
    })
  const outgoing = (database.prepare('SELECT * FROM friend_requests WHERE from_user_id = ? ORDER BY created_at DESC').all(playerId) as Array<{ id: string; to_user_id: string; created_at: string }>)
    .flatMap(request => {
      const user = publicUser(request.to_user_id)
      return user ? [{ id: request.id, createdAt: request.created_at, user }] : []
    })
  const blocked = (database.prepare('SELECT blocked_id, created_at FROM blocks WHERE owner_id = ? ORDER BY created_at DESC').all(playerId) as Array<{ blocked_id: string; created_at: string }>)
    .flatMap(block => {
      const user = publicUser(block.blocked_id)
      return user ? [{ ...user, blockedAt: block.created_at }] : []
    })
  return { friends, incoming, outgoing, blocked }
}

async function handleSocialRequest(request: IncomingMessage, response: ServerResponse): Promise<void> {
  const url = new URL(request.url ?? '/', 'http://motman.local')
  const route = url.pathname.replace(/^\/api\/social\/?/, '').replace(/^\/+/, '')
  const user = requireAuthenticatedUser(request, response)
  if (!user) return
  const playerId = user.id

  if (request.method === 'GET' && route === 'state') {
    database.prepare("UPDATE users SET activity='online', last_seen=?, updated_at=? WHERE id=?").run(nowIso(), nowIso(), playerId)
    return sendJson(response, 200, socialState(playerId))
  }
  if (request.method !== 'POST') return sendJson(response, 405, { error: 'Méthode non autorisée.' })
  if (!requestHasSameOrigin(request)) return sendJson(response, 403, { error: 'Origine refusée.' })
  let body: Record<string, unknown>
  try { body = await readJsonBody(request) } catch { return sendJson(response, 400, { error: 'Requête invalide.' }) }

  if (route === 'register') {
    const name = validatePlayerName(typeof body.displayName === 'string' ? body.displayName : user.display_name)
    if (!name.valid) return sendJson(response, 400, { error: name.error ?? 'Pseudo invalide.' })
    const displayName = user.account_type === 'guest' ? name.normalized : user.display_name
    database.prepare("UPDATE users SET display_name=?, activity='online', last_seen=?, updated_at=? WHERE id=?")
      .run(displayName, nowIso(), nowIso(), playerId)
    return sendJson(response, 200, { ok: true, state: socialState(playerId) })
  }

  if (route === 'presence') {
    const activity: PresenceActivity = body.activity === 'playing' ? 'playing' : 'online'
    database.prepare('UPDATE users SET activity=?, last_seen=?, updated_at=? WHERE id=?').run(activity, nowIso(), nowIso(), playerId)
    return sendJson(response, 200, { ok: true })
  }

  if (route === 'request') {
    const friendCode = cleanCode(body.friendCode)
    const target = database.prepare('SELECT * FROM users WHERE friend_code = ?').get(friendCode) as DatabaseUser | undefined
    if (!target) return sendJson(response, 404, { error: 'Code ami inconnu.' })
    if (target.id === playerId) return sendJson(response, 400, { error: 'Vous ne pouvez pas vous ajouter vous-même.' })
    if (isBlocked(playerId, target.id)) return sendJson(response, 409, { error: 'Cette demande ne peut pas être envoyée.' })
    const [left, right] = orderedPair(playerId, target.id)
    if (database.prepare('SELECT 1 FROM friendships WHERE left_user_id=? AND right_user_id=?').get(left, right))
      return sendJson(response, 409, { error: 'Ce joueur est déjà dans vos amis.' })
    const reverse = database.prepare('SELECT id FROM friend_requests WHERE from_user_id=? AND to_user_id=?').get(target.id, playerId) as { id: string } | undefined
    if (reverse) database.transaction(() => {
      database.prepare('DELETE FROM friend_requests WHERE id=?').run(reverse.id)
      database.prepare('INSERT OR IGNORE INTO friendships(left_user_id,right_user_id,created_at) VALUES(?,?,?)').run(left, right, nowIso())
    })()
    else database.prepare('INSERT OR IGNORE INTO friend_requests(id,from_user_id,to_user_id,created_at) VALUES(?,?,?,?)')
      .run(randomUUID(), playerId, target.id, nowIso())
    return sendJson(response, 200, { ok: true, state: socialState(playerId) })
  }

  if (route === 'respond') {
    const requestId = typeof body.requestId === 'string' ? body.requestId : ''
    const pending = database.prepare('SELECT * FROM friend_requests WHERE id=? AND to_user_id=?').get(requestId, playerId) as { from_user_id: string } | undefined
    if (!pending) return sendJson(response, 404, { error: 'Cette demande n’existe plus.' })
    database.transaction(() => {
      database.prepare('DELETE FROM friend_requests WHERE id=?').run(requestId)
      if (body.decision === 'accept' && !isBlocked(playerId, pending.from_user_id)) {
        const [left, right] = orderedPair(playerId, pending.from_user_id)
        database.prepare('INSERT OR IGNORE INTO friendships(left_user_id,right_user_id,created_at) VALUES(?,?,?)').run(left, right, nowIso())
      }
    })()
    return sendJson(response, 200, { ok: true, state: socialState(playerId) })
  }

  const targetId = cleanTargetId(body.targetId)
  if (!targetId) return sendJson(response, 400, { error: 'Joueur invalide.' })
  const [left, right] = orderedPair(playerId, targetId)
  if (route === 'cancel') database.prepare('DELETE FROM friend_requests WHERE from_user_id=? AND to_user_id=?').run(playerId, targetId)
  else if (route === 'remove') database.prepare('DELETE FROM friendships WHERE left_user_id=? AND right_user_id=?').run(left, right)
  else if (route === 'block') database.transaction(() => {
    database.prepare('DELETE FROM friendships WHERE left_user_id=? AND right_user_id=?').run(left, right)
    database.prepare('DELETE FROM friend_requests WHERE (from_user_id=? AND to_user_id=?) OR (from_user_id=? AND to_user_id=?)').run(playerId, targetId, targetId, playerId)
    database.prepare('INSERT OR IGNORE INTO blocks(owner_id,blocked_id,created_at) VALUES(?,?,?)').run(playerId, targetId, nowIso())
  })()
  else if (route === 'unblock') database.prepare('DELETE FROM blocks WHERE owner_id=? AND blocked_id=?').run(playerId, targetId)
  else if (route === 'report') {
    const allowedReasons = ['pseudo', 'comportement', 'triche', 'harcelement', 'autre']
    const reason = typeof body.reason === 'string' && allowedReasons.includes(body.reason) ? body.reason : 'autre'
    const details = typeof body.details === 'string' ? body.details.trim().slice(0, 500) : ''
    const matchId = typeof body.matchId === 'string' ? body.matchId.slice(0, 80) : null
    if (targetId === playerId) return sendJson(response, 400, { error: 'Vous ne pouvez pas vous signaler vous-même.' })
    database.prepare('INSERT INTO reports(id,reporter_id,reported_id,reason,details,match_id,created_at) VALUES(?,?,?,?,?,?,?)')
      .run(randomUUID(), playerId, targetId, reason, details, matchId, nowIso())
  } else return sendJson(response, 404, { error: 'Action inconnue.' })
  return sendJson(response, 200, { ok: true, state: socialState(playerId) })
}

function attachSocialApi(middlewares: { use: (route: string, handler: (request: IncomingMessage, response: ServerResponse) => void) => void }): void {
  middlewares.use('/api/social', (request, response) => {
    void handleSocialRequest(request, response).catch(error => {
      console.error('[motman-social]', error)
      if (!response.headersSent) sendJson(response, 500, { error: 'Le service amis a rencontré une erreur.' })
    })
  })
}

importLegacySocialDatabase()

export function motmanSocialPlugin(): Plugin {
  return {
    name: 'motman-social-api',
    configureServer(server) { attachSocialApi(server.middlewares) },
    configurePreviewServer(server) { attachSocialApi(server.middlewares) },
  }
}
