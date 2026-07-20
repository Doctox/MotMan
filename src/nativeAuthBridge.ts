import { supabase } from './supabaseClient'
import { NATIVE_AUTH_REDIRECT } from './nativeRuntime'
import { parseGoogleAuthIssue, rememberGoogleAuthIssue } from './googleAuthCallback'

let initialization: Promise<void> | null = null
let lastHandledUrl = ''

async function handleAuthenticationUrl(url: string): Promise<void> {
  if (!url.startsWith(NATIVE_AUTH_REDIRECT) || url === lastHandledUrl) return
  lastHandledUrl = url

  const callback = new URL(url)
  const authIssue = parseGoogleAuthIssue(callback.search, callback.hash)
  if (authIssue) {
    rememberGoogleAuthIssue(sessionStorage, authIssue)
    const { Browser } = await import('@capacitor/browser')
    await Browser.close().catch(() => undefined)
    location.hash = '#profil'
    location.reload()
    return
  }

  const code = callback.searchParams.get('code')
  if (!code) return
  const { error } = await supabase.auth.exchangeCodeForSession(code)
  if (error) throw error

  const { Browser } = await import('@capacitor/browser')
  await Browser.close().catch(() => undefined)
  location.hash = '#profil'
  location.reload()
}

export function initializeNativeAuthBridge(): Promise<void> {
  if (initialization) return initialization
  initialization = (async () => {
    const { App } = await import('@capacitor/app')
    await App.addListener('appUrlOpen', event => {
      void handleAuthenticationUrl(event.url).catch(reason => {
        console.error('Retour d’authentification mobile invalide', reason)
      })
    })
    const launch = await App.getLaunchUrl()
    if (launch?.url) await handleAuthenticationUrl(launch.url)
  })()
  return initialization
}
