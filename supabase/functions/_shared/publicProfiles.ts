import type { SupabaseClient } from '@supabase/supabase-js'
import { isPresenceOnline } from '../../../src/presencePolicy.ts'

type PublicProfileRow = {
  id: string
  display_name: string
  friend_code: string
  avatar_id: string
  frame_id: string
  animation_id: string
  activity: string
  last_seen: string
}

export type PublicPlayerProfile = {
  playerId: string
  displayName: string
  code: string
  online: boolean
  activity: string
  avatarId: string
  frameId: string
  animationId: string
}

type PublicProfileOptions = {
  normalizeOfflineActivity?: boolean
  now?: number
}

const PROFILE_COLUMNS = 'id,display_name,friend_code,avatar_id,frame_id,animation_id,activity,last_seen'

export function uniqueProfileIds(ids: Iterable<string>): string[] {
  return [...new Set([...ids].map(id => id.trim()).filter(Boolean))]
}

export async function loadPublicProfiles(
  admin: SupabaseClient,
  ids: Iterable<string>,
  options: PublicProfileOptions = {},
): Promise<Map<string, PublicPlayerProfile>> {
  const uniqueIds = uniqueProfileIds(ids)
  if (!uniqueIds.length) return new Map()

  const { data, error } = await admin.from('profiles')
    .select(PROFILE_COLUMNS)
    .in('id', uniqueIds)
  if (error) throw error

  const now = options.now ?? Date.now()
  return new Map(((data ?? []) as PublicProfileRow[]).map(row => {
    const online = isPresenceOnline(row.last_seen, now)
    return [row.id, {
      playerId: row.id,
      displayName: row.display_name,
      code: row.friend_code,
      online,
      activity: options.normalizeOfflineActivity && !online ? 'offline' : row.activity,
      avatarId: row.avatar_id,
      frameId: row.frame_id,
      animationId: row.animation_id,
    }]
  }))
}

export async function loadPublicProfile(
  admin: SupabaseClient,
  id: string,
  options: PublicProfileOptions = {},
): Promise<PublicPlayerProfile | null> {
  return (await loadPublicProfiles(admin, [id], options)).get(id) ?? null
}
