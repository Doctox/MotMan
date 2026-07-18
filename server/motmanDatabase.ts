import Database from 'better-sqlite3'
import { createHash, randomBytes } from 'node:crypto'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { resolve } from 'node:path'

export const MOTMAN_DATABASE_PATH = resolve(process.env.MOTMAN_DATABASE_PATH ?? '.motman.sqlite')
export const SESSION_COOKIE = 'motman_session'
const SESSION_LIFETIME_MS = 30 * 24 * 60 * 60 * 1000

export const database: Database.Database = new Database(MOTMAN_DATABASE_PATH)
database.pragma('journal_mode = WAL')
database.pragma('foreign_keys = ON')
database.pragma('busy_timeout = 5000')

database.exec(`
  CREATE TABLE IF NOT EXISTS server_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    account_type TEXT NOT NULL DEFAULT 'guest' CHECK (account_type IN ('guest', 'account')),
    username_key TEXT UNIQUE,
    display_name TEXT NOT NULL,
    friend_code TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    password_salt TEXT,
    recovery_hash TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'banned')),
    role TEXT NOT NULL DEFAULT 'player' CHECK (role IN ('player', 'moderator', 'admin')),
    level INTEGER NOT NULL DEFAULT 1,
    xp INTEGER NOT NULL DEFAULT 0,
    lifetime_xp INTEGER NOT NULL DEFAULT 0,
    ranked_points INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    feathers INTEGER NOT NULL DEFAULT 600,
    equipped_avatar_id TEXT NOT NULL DEFAULT 'plume-motman',
    equipped_frame_id TEXT NOT NULL DEFAULT 'cadre-ivoire',
    equipped_animation_id TEXT NOT NULL DEFAULT 'animation-none',
    opened_baskets INTEGER NOT NULL DEFAULT 0,
    basket_pity INTEGER NOT NULL DEFAULT 0,
    activity TEXT NOT NULL DEFAULT 'online' CHECK (activity IN ('online', 'playing')),
    last_seen TEXT NOT NULL,
    legacy_imported_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    expires_at TEXT NOT NULL
  );
  CREATE INDEX IF NOT EXISTS sessions_user_id ON sessions(user_id);
  CREATE INDEX IF NOT EXISTS sessions_expires_at ON sessions(expires_at);

  CREATE TABLE IF NOT EXISTS friend_requests (
    id TEXT PRIMARY KEY,
    from_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    to_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    UNIQUE(from_user_id, to_user_id)
  );
  CREATE TABLE IF NOT EXISTS friendships (
    left_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    right_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY(left_user_id, right_user_id),
    CHECK(left_user_id < right_user_id)
  );
  CREATE TABLE IF NOT EXISTS blocks (
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blocked_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY(owner_id, blocked_id)
  );

  CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    reporter_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reported_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    match_id TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'reviewed', 'dismissed', 'actioned')),
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewed_by TEXT REFERENCES users(id)
  );
  CREATE INDEX IF NOT EXISTS reports_status_created ON reports(status, created_at);

  CREATE TABLE IF NOT EXISTS moderation_actions (
    id TEXT PRIMARY KEY,
    moderator_id TEXT REFERENCES users(id),
    target_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    expires_at TEXT,
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS inventory (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('avatar', 'frame', 'animation')),
    item_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY(user_id, kind, item_id)
  );

  CREATE TABLE IF NOT EXISTS economy_transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    amount INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
  );
  CREATE INDEX IF NOT EXISTS economy_transactions_user ON economy_transactions(user_id, created_at);

  CREATE TABLE IF NOT EXISTS experience_awards (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode TEXT NOT NULL,
    outcome TEXT NOT NULL,
    productive_turns INTEGER NOT NULL,
    xp_amount INTEGER NOT NULL,
    feather_amount INTEGER NOT NULL,
    level_before INTEGER NOT NULL,
    level_after INTEGER NOT NULL,
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS matches (
    id TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    status TEXT NOT NULL,
    pace TEXT NOT NULL,
    grid_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );
  CREATE TABLE IF NOT EXISTS match_players (
    match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY(match_id, user_id)
  );
`)

export type DatabaseUser = {
  id: string
  account_type: 'guest' | 'account'
  username_key: string | null
  display_name: string
  friend_code: string
  password_hash: string | null
  password_salt: string | null
  recovery_hash: string | null
  status: 'active' | 'suspended' | 'banned'
  role: 'player' | 'moderator' | 'admin'
  level: number
  xp: number
  lifetime_xp: number
  ranked_points: number
  wins: number
  losses: number
  feathers: number
  equipped_avatar_id: string
  equipped_frame_id: string
  equipped_animation_id: string
  opened_baskets: number
  basket_pity: number
  activity: 'online' | 'playing'
  last_seen: string
  legacy_imported_at: string | null
  created_at: string
  updated_at: string
}

export function nowIso(): string {
  return new Date().toISOString()
}

export function hashToken(token: string): string {
  return createHash('sha256').update(token).digest('hex')
}

export function parseCookies(request: IncomingMessage): Record<string, string> {
  const header = request.headers.cookie ?? ''
  return Object.fromEntries(header.split(';').flatMap(part => {
    const separator = part.indexOf('=')
    if (separator < 1) return []
    return [[decodeURIComponent(part.slice(0, separator).trim()), decodeURIComponent(part.slice(separator + 1).trim())]]
  }))
}

function cookieSecure(request: IncomingMessage): boolean {
  const forwarded = request.headers['x-forwarded-proto']
  return forwarded === 'https' || Boolean((request.socket as { encrypted?: boolean }).encrypted)
}

export function setSessionCookie(request: IncomingMessage, response: ServerResponse, token: string): void {
  const secure = cookieSecure(request) ? '; Secure' : ''
  response.setHeader('Set-Cookie', `${SESSION_COOKIE}=${encodeURIComponent(token)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${Math.floor(SESSION_LIFETIME_MS / 1000)}${secure}`)
}

export function clearSessionCookie(request: IncomingMessage, response: ServerResponse): void {
  const secure = cookieSecure(request) ? '; Secure' : ''
  response.setHeader('Set-Cookie', `${SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0${secure}`)
}

export function createSession(request: IncomingMessage, response: ServerResponse, userId: string): void {
  const token = randomBytes(32).toString('base64url')
  const now = nowIso()
  const expiresAt = new Date(Date.now() + SESSION_LIFETIME_MS).toISOString()
  database.prepare('INSERT INTO sessions(token_hash, user_id, created_at, last_seen, expires_at) VALUES (?, ?, ?, ?, ?)')
    .run(hashToken(token), userId, now, now, expiresAt)
  setSessionCookie(request, response, token)
}

export function revokeSession(request: IncomingMessage): void {
  const token = parseCookies(request)[SESSION_COOKIE]
  if (token) database.prepare('DELETE FROM sessions WHERE token_hash = ?').run(hashToken(token))
}

export function authenticatedUser(request: IncomingMessage, touch = true): DatabaseUser | null {
  const token = parseCookies(request)[SESSION_COOKIE]
  if (!token) return null
  const tokenHash = hashToken(token)
  const row = database.prepare(`
    SELECT users.* FROM sessions
    JOIN users ON users.id = sessions.user_id
    WHERE sessions.token_hash = ? AND sessions.expires_at > ?
  `).get(tokenHash, nowIso()) as DatabaseUser | undefined
  if (!row || row.status !== 'active') return null
  if (touch) {
    const now = nowIso()
    database.prepare('UPDATE sessions SET last_seen = ? WHERE token_hash = ?').run(now, tokenHash)
    database.prepare('UPDATE users SET last_seen = ?, updated_at = ? WHERE id = ?').run(now, now, row.id)
    row.last_seen = now
  }
  return row
}

export function requireAuthenticatedUser(request: IncomingMessage, response: ServerResponse): DatabaseUser | null {
  const user = authenticatedUser(request)
  if (user) return user
  sendJson(response, 401, { error: 'Votre session a expiré. Reconnectez-vous.' })
  return null
}

export function sendJson(response: ServerResponse, status: number, payload: unknown): void {
  response.statusCode = status
  response.setHeader('Content-Type', 'application/json; charset=utf-8')
  response.setHeader('Cache-Control', 'no-store')
  response.setHeader('X-Content-Type-Options', 'nosniff')
  response.end(JSON.stringify(payload))
}

export async function readJsonBody(request: IncomingMessage, limit = 64 * 1024): Promise<Record<string, unknown>> {
  const chunks: Uint8Array[] = []
  let size = 0
  for await (const chunk of request) {
    const buffer = typeof chunk === 'string' ? Buffer.from(chunk) : chunk
    size += buffer.length
    if (size > limit) throw new Error('payload-too-large')
    chunks.push(buffer)
  }
  if (!chunks.length) return {}
  return JSON.parse(Buffer.concat(chunks).toString('utf8')) as Record<string, unknown>
}

export function requestHasSameOrigin(request: IncomingMessage): boolean {
  const origin = request.headers.origin
  if (!origin) return true
  try {
    return new URL(origin).host === request.headers.host
  } catch {
    return false
  }
}

export function cleanupExpiredSessions(): void {
  database.prepare('DELETE FROM sessions WHERE expires_at <= ?').run(nowIso())
}

cleanupExpiredSessions()
