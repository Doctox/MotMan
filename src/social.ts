import type { GuestIdentity } from './playerIdentity'
import { hasSupabaseSession } from './supabaseClient'
import { invokeSupabaseFunction } from './supabaseFunctions'

export type PresenceActivity = 'offline' | 'online' | 'playing'
export type SocialUser = { playerId: string; displayName: string; code: string; online: boolean; activity: PresenceActivity; avatarId?: string; frameId?: string; animationId?: string }
export type SocialRequest = { id: string; createdAt: string; user: SocialUser }
export type Friend = SocialUser & { since: string }
export type BlockedUser = SocialUser & { blockedAt: string }
export type SocialState = {
  friends: Friend[]
  incoming: SocialRequest[]
  outgoing: SocialRequest[]
  blocked: BlockedUser[]
}

export const EMPTY_SOCIAL_STATE: SocialState = { friends: [], incoming: [], outgoing: [], blocked: [] }
const localTestServer = import.meta.env.VITE_MOTMAN_LOCAL_TEST_SERVER === 'true'

async function localSocial<T>(path: string, body?: Record<string, unknown>): Promise<T> {
  const response = await fetch(`/api/social/${path}`, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  } : undefined)
  const payload = await response.json()
  if (!response.ok) throw new Error(payload?.error ?? 'Service social de test indisponible.')
  return payload as T
}

type SocialAction = 'request' | 'respond' | 'cancel' | 'remove' | 'block' | 'unblock'

async function supabaseSocial<T>(action: string, body: Record<string, unknown> = {}): Promise<T> {
  if (!await hasSupabaseSession()) throw new Error('Votre session MotMan a expiré. Reconnectez-vous.')
  return invokeSupabaseFunction<T>('social-api', { action, ...body })
}

export async function registerSocialProfile(identity: GuestIdentity, style?: { avatarId: string; frameId: string; animationId: string }): Promise<SocialState> {
  if (localTestServer) return (await localSocial<{ state: SocialState }>('register', { displayName: identity.displayName, ...style })).state
  void identity; void style
  return (await supabaseSocial<{ state: SocialState }>('state')).state
}

export function loadSocialState(playerId: string): Promise<SocialState> {
  if (localTestServer) return localSocial<SocialState>('state')
  void playerId
  return supabaseSocial<{ state: SocialState }>('state').then(remote => remote.state)
}

export async function setSocialPresence(playerId: string, activity: Exclude<PresenceActivity, 'offline'>): Promise<void> {
  if (localTestServer) { await localSocial('presence', { activity }); return }
  void playerId
  await supabaseSocial<{ ok: true }>('presence', { activity })
}

export async function sendFriendRequest(playerId: string, friendCode: string): Promise<SocialState> {
  if (localTestServer) return (await localSocial<{ state: SocialState }>('request', { friendCode })).state
  void playerId
  return (await supabaseSocial<{ state: SocialState }>('request', { friendCode })).state
}

export async function respondToFriendRequest(playerId: string, requestId: string, decision: 'accept' | 'decline'): Promise<SocialState> {
  if (localTestServer) return (await localSocial<{ state: SocialState }>('respond', { requestId, decision })).state
  void playerId
  return (await supabaseSocial<{ state: SocialState }>('respond', { requestId, decision })).state
}

export async function updateFriend(playerId: string, targetId: string, action: Exclude<SocialAction, 'request' | 'respond'>): Promise<SocialState> {
  if (localTestServer) return (await localSocial<{ state: SocialState }>(action, { targetId })).state
  void playerId
  return (await supabaseSocial<{ state: SocialState }>(action, { targetId })).state
}

export async function reportPlayer(targetId: string, reason: 'pseudo' | 'comportement' | 'triche' | 'harcelement' | 'autre', details = '', matchId?: string): Promise<void> {
  if (localTestServer) { await localSocial('report', { targetId, reason, details, matchId }); return }
  await supabaseSocial<{ ok: true }>('report', { targetId, reason, details, matchId })
}
