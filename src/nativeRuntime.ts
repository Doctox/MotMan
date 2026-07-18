export const NATIVE_AUTH_REDIRECT = 'com.motman.game://auth/callback'

type CapacitorWindow = Window & {
  Capacitor?: {
    isNativePlatform?: () => boolean
  }
}

export function isNativeRuntime(): boolean {
  return Boolean((window as CapacitorWindow).Capacitor?.isNativePlatform?.())
}

export async function openNativeAuthentication(url: string): Promise<void> {
  const { Browser } = await import('@capacitor/browser')
  await Browser.open({ url, presentationStyle: 'popover' })
}
