import { Capacitor } from '@capacitor/core'
import { invokeSupabaseFunction } from './supabaseFunctions'
import { isNativeRuntime } from './nativeRuntime'

const TOKEN_STORAGE_KEY = 'motman-push-token-v1'
let initialization: Promise<void> | null = null

export function pushNotificationRoute(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null
  const payload = data as Record<string, unknown>
  if (typeof payload.matchId === 'string' && /^[0-9a-f-]{36}$/i.test(payload.matchId)) {
    return `#partie=${encodeURIComponent(payload.matchId)}`
  }
  if (payload.type === 'friend_invitation') return '#jouer'
  return null
}

async function registerToken(token: string): Promise<void> {
  localStorage.setItem(TOKEN_STORAGE_KEY, token)
  await invokeSupabaseFunction('account-api', {
    action: 'register-push-device', token, platform: Capacitor.getPlatform(), appId: 'com.motman.game',
  })
}

export async function syncStoredPushDevice(): Promise<void> {
  if (!isNativeRuntime()) return
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  if (token) await registerToken(token)
}

export async function detachStoredPushDevice(): Promise<void> {
  if (!isNativeRuntime()) return
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  if (!token) return
  await invokeSupabaseFunction('account-api', { action: 'unregister-push-device', token }).catch(() => undefined)
}

export function initializeNativePushNotifications(): Promise<void> {
  if (initialization) return initialization
  initialization = (async () => {
    if (!isNativeRuntime()) return
    const { PushNotifications } = await import('@capacitor/push-notifications')

    await PushNotifications.addListener('registration', token => {
      void registerToken(token.value).catch(error => console.error('Enregistrement push impossible', error))
    })
    await PushNotifications.addListener('registrationError', error => {
      console.error('Inscription native aux notifications impossible', error.error)
    })
    await PushNotifications.addListener('pushNotificationActionPerformed', action => {
      const route = pushNotificationRoute(action.notification.data)
      if (!route) return
      history.replaceState(null, '', route)
      location.reload()
    })

    if (Capacitor.getPlatform() === 'android') {
      await PushNotifications.createChannel({
        id: 'motman_turns', name: 'Tours et invitations',
        description: 'Prévient lorsqu’un duel MotMan demande votre attention.',
        importance: 4, visibility: 1, vibration: true, lights: true, lightColor: '#0B5A49',
      })
    }

    let permission = await PushNotifications.checkPermissions()
    if (permission.receive === 'prompt' || permission.receive === 'prompt-with-rationale') {
      permission = await PushNotifications.requestPermissions()
    }
    if (permission.receive === 'granted') await PushNotifications.register()
  })()
  return initialization
}
