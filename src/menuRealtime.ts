import { supabase, supabaseConfigured } from './supabaseClient'

const localTestServer = import.meta.env.VITE_MOTMAN_LOCAL_TEST_SERVER === 'true'

export type MenuRealtimeStatus = 'connected' | 'disconnected'
export type MenuWakeupScope = 'lobby' | 'social' | 'all'

export function readMenuWakeupScope(payload: unknown): MenuWakeupScope {
  if (!payload || typeof payload !== 'object') return 'all'
  const scope = (payload as { scope?: unknown }).scope
  return scope === 'lobby' || scope === 'social' ? scope : 'all'
}

/**
 * This channel only transports a wake-up pulse. Social data and match state
 * are still reloaded through their JWT-protected Edge Functions.
 */
export function subscribeToMenuUpdates(
  userId: string,
  onUpdate: (scope: MenuWakeupScope) => void,
  onStatus?: (status: MenuRealtimeStatus) => void,
): () => void {
  if (!supabaseConfigured || localTestServer) {
    onStatus?.('disconnected')
    return () => undefined
  }

  const channel = supabase
    .channel(`user:${userId}`, { config: { private: true } })
    .on('broadcast', { event: 'changed' }, message => {
      onUpdate(readMenuWakeupScope(message.payload))
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
