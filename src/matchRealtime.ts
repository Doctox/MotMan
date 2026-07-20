import { supabase, supabaseConfigured } from './supabaseClient'

const localTestServer = import.meta.env.VITE_MOTMAN_LOCAL_TEST_SERVER === 'true'

export type MatchRealtimeStatus = 'connected' | 'disconnected'

/**
 * Realtime carries only a wake-up pulse. Match data is deliberately reloaded
 * through match-api, which remains responsible for authorization and for
 * hiding the solution and the opponent's rack.
 */
export function subscribeToMatchUpdates(
  matchId: string,
  onUpdate: (updatedAt: string | null) => void,
  onStatus?: (status: MatchRealtimeStatus) => void,
): () => void {
  if (!supabaseConfigured || localTestServer) {
    onStatus?.('disconnected')
    return () => undefined
  }

  const channel = supabase
    .channel(`match:${matchId}`, { config: { private: true } })
    .on('broadcast', { event: 'changed' }, message => {
      const updatedAt = typeof message.payload?.updatedAt === 'string' ? message.payload.updatedAt : null
      onUpdate(updatedAt)
    })
    .subscribe(status => {
      if (status === 'SUBSCRIBED') onStatus?.('connected')
      else if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT' || status === 'CLOSED') onStatus?.('disconnected')
    })

  return () => {
    onStatus?.('disconnected')
    void supabase.removeChannel(channel)
  }
}
