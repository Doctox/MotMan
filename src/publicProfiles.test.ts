import { describe, expect, it, vi } from 'vitest'
import { loadPublicProfiles, uniqueProfileIds } from '../supabase/functions/_shared/publicProfiles'

describe('grouped public profile loading', () => {
  it('deduplicates identifiers while preserving their first useful order', () => {
    expect(uniqueProfileIds([' player-b ', 'player-a', 'player-b', '', 'player-a']))
      .toEqual(['player-b', 'player-a'])
  })

  it('loads every requested profile with one grouped query', async () => {
    const groupedFilter = vi.fn().mockResolvedValue({
      data: [
        {
          id: 'player-a',
          display_name: 'Alice',
          friend_code: 'A11CE001',
          avatar_id: 'avatar-a',
          frame_id: 'frame-a',
          animation_id: 'animation-a',
          activity: 'playing',
          last_seen: '2026-07-29T20:00:00.000Z',
        },
        {
          id: 'player-b',
          display_name: 'Bob',
          friend_code: 'B0B00002',
          avatar_id: 'avatar-b',
          frame_id: 'frame-b',
          animation_id: 'animation-b',
          activity: 'online',
          last_seen: '2026-07-29T19:50:00.000Z',
        },
      ],
      error: null,
    })
    const select = vi.fn().mockReturnValue({ in: groupedFilter })
    const from = vi.fn().mockReturnValue({ select })

    const profiles = await loadPublicProfiles(
      { from } as never,
      ['player-a', 'player-b', 'player-a'],
      { normalizeOfflineActivity: true, now: Date.parse('2026-07-29T20:00:30.000Z') },
    )

    expect(from).toHaveBeenCalledTimes(1)
    expect(from).toHaveBeenCalledWith('profiles')
    expect(select).toHaveBeenCalledTimes(1)
    expect(groupedFilter).toHaveBeenCalledTimes(1)
    expect(groupedFilter).toHaveBeenCalledWith('id', ['player-a', 'player-b'])
    expect(profiles.get('player-a')).toMatchObject({ displayName: 'Alice', online: true, activity: 'playing' })
    expect(profiles.get('player-b')).toMatchObject({ displayName: 'Bob', online: false, activity: 'offline' })
  })

  it('does not query Supabase when no profile is needed', async () => {
    const from = vi.fn()
    const profiles = await loadPublicProfiles({ from } as never, ['', '   '])
    expect(from).not.toHaveBeenCalled()
    expect(profiles.size).toBe(0)
  })
})
