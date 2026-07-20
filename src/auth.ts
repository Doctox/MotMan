import { savePlayerCosmetics, type CosmeticKind, type CosmeticReward, type PlayerCosmetics } from './cosmetics'
import { loadPlayerIdentity, savePlayerIdentity, type GuestIdentity } from './playerIdentity'
import { savePlayerProgress, type PlayerProgress } from './playerProgress'
import { supabase, supabaseConfigured } from './supabaseClient'
import { invokeSupabaseFunction } from './supabaseFunctions'
import { isNativeRuntime, NATIVE_AUTH_REDIRECT, openNativeAuthentication } from './nativeRuntime'
import { getAnonymousCaptchaToken } from './turnstile'

const recoveryListeners = new Set<() => void>()
let passwordRecoveryPending = false
const localTestServer = import.meta.env.VITE_MOTMAN_LOCAL_TEST_SERVER === 'true'

if (supabaseConfigured) {
  supabase.auth.onAuthStateChange(event => {
    if (event !== 'PASSWORD_RECOVERY') return
    passwordRecoveryPending = true
    recoveryListeners.forEach(listener => listener())
  })
}

export type AuthResponse = {
  identity: GuestIdentity
  progress?: PlayerProgress
  cosmetics?: PlayerCosmetics
  emailConfirmationRequired?: boolean
}

function store(payload: AuthResponse): AuthResponse {
  savePlayerIdentity(payload.identity)
  if (payload.progress) savePlayerProgress(payload.progress)
  if (payload.cosmetics) savePlayerCosmetics(payload.cosmetics)
  return payload
}

function clearPlayerDataFromDevice(): void {
  localStorage.removeItem('motman-player-v1')
  localStorage.removeItem('motman-progress-v1')
  localStorage.removeItem('motman-cosmetics-v1')
  localStorage.removeItem('motman-recent-solo-grids-v4')
  localStorage.removeItem('entrelignes-feedback')
}

async function accountAction(action: string, body: Record<string, unknown> = {}): Promise<AuthResponse> {
  return store(await invokeSupabaseFunction<AuthResponse>('account-api', { action, ...body }))
}

export async function bootstrapPlayerSession(): Promise<GuestIdentity> {
  const legacyIdentity = loadPlayerIdentity()
  if (localTestServer) {
    const response = await fetch('/api/auth/bootstrap', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identity: legacyIdentity }),
    })
    const payload = await response.json() as AuthResponse & { error?: string }
    if (!response.ok) throw new Error(payload.error ?? 'Session locale de test indisponible.')
    return store(payload).identity
  }
  if (!supabaseConfigured) throw new Error('MotMan ne trouve pas sa configuration Supabase.')
  let { data: sessionData } = await supabase.auth.getSession()
  if (!sessionData.session) {
    const captchaToken = await getAnonymousCaptchaToken()
    const { data, error } = await supabase.auth.signInAnonymously(captchaToken ? { options: { captchaToken } } : undefined)
    if (error || !data.session) throw new Error(error?.message || 'Création de la session MotMan impossible.')
    sessionData = { session: data.session }
  }
  const response = await accountAction('bootstrap', { identity: legacyIdentity })
  return response.identity
}

export function refreshPlayerAccount(): Promise<AuthResponse> {
  return accountAction('state')
}

export function subscribePasswordRecovery(listener: () => void): () => void {
  recoveryListeners.add(listener)
  if (passwordRecoveryPending) queueMicrotask(listener)
  return () => recoveryListeners.delete(listener)
}

export function consumePasswordRecovery(): boolean {
  const pending = passwordRecoveryPending
  passwordRecoveryPending = false
  return pending
}

export async function createPlayerAccount(email: string): Promise<AuthResponse> {
  const emailRedirectTo = isNativeRuntime()
    ? NATIVE_AUTH_REDIRECT
    : `${location.origin}${location.pathname}#profil`
  const { error } = await supabase.auth.updateUser({ email: email.trim() }, { emailRedirectTo })
  if (error) throw new Error(error.message)
  const state = await accountAction('state')
  return { ...state, emailConfirmationRequired: true }
}

export async function finishPlayerAccount(password: string): Promise<AuthResponse> {
  const { error } = await supabase.auth.updateUser({ password })
  if (error) throw new Error(error.message)
  return accountAction('state')
}

export async function loginPlayerAccount(email: string, password: string): Promise<AuthResponse> {
  if (isNativeRuntime()) {
    await import('./nativePushNotifications').then(module => module.detachStoredPushDevice()).catch(() => undefined)
  }
  const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
  if (error) {
    if (isNativeRuntime()) {
      void import('./nativePushNotifications').then(module => module.syncStoredPushDevice()).catch(() => undefined)
    }
    throw new Error('E-mail ou mot de passe incorrect.')
  }
  const account = await accountAction('state')
  if (isNativeRuntime()) {
    void import('./nativePushNotifications').then(module => module.syncStoredPushDevice()).catch(() => undefined)
  }
  return account
}

export async function authenticateWithGoogle(): Promise<void> {
  if (!supabaseConfigured) {
    throw new Error('Connexion Google indisponible. Redémarrez MotMan puis réessayez.')
  }
  const native = isNativeRuntime()
  const redirectTo = native ? NATIVE_AUTH_REDIRECT : `${location.origin}${location.pathname}#profil`
  const { data: { user } } = await supabase.auth.getUser()
  const options = { redirectTo, skipBrowserRedirect: native }
  const { data, error } = user?.is_anonymous
    ? await supabase.auth.linkIdentity({ provider: 'google', options })
    : await supabase.auth.signInWithOAuth({ provider: 'google', options })
  if (error) throw new Error(error.message)
  if (data?.url) {
    if (native) await openNativeAuthentication(data.url)
    else location.assign(data.url)
  }
}

export async function recoverPlayerAccount(email: string): Promise<void> {
  const redirectTo = isNativeRuntime()
    ? NATIVE_AUTH_REDIRECT
    : `${location.origin}${location.pathname}#profil`
  const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo })
  if (error) throw new Error(error.message)
}

export async function logoutPlayerAccount(): Promise<GuestIdentity> {
  if (isNativeRuntime()) {
    await import('./nativePushNotifications').then(module => module.detachStoredPushDevice()).catch(() => undefined)
  }
  await supabase.auth.signOut()
  clearPlayerDataFromDevice()
  const identity = await bootstrapPlayerSession()
  if (isNativeRuntime()) {
    void import('./nativePushNotifications').then(module => module.syncStoredPushDevice()).catch(() => undefined)
  }
  return identity
}

export async function deletePlayerAccount(confirmation: string): Promise<AuthResponse> {
  if (confirmation !== 'SUPPRIMER') throw new Error('Écrivez SUPPRIMER pour confirmer.')

  if (isNativeRuntime()) {
    await import('./nativePushNotifications').then(module => module.detachStoredPushDevice()).catch(() => undefined)
  }

  if (localTestServer) {
    const response = await fetch('/api/auth/delete', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmation }),
    })
    const payload = await response.json().catch(() => ({})) as { error?: string }
    if (!response.ok) throw new Error(payload.error ?? 'Suppression du compte impossible.')
  } else {
    await invokeSupabaseFunction<{ deleted: true }>('account-api', { action: 'delete-account', confirmation })
    // The server has already revoked every refresh token and deleted the user.
    // This local sign-out only clears Supabase's browser/native storage.
    await supabase.auth.signOut({ scope: 'local' }).catch(() => undefined)
  }

  clearPlayerDataFromDevice()
  const identity = await bootstrapPlayerSession()
  if (isNativeRuntime()) {
    void import('./nativePushNotifications').then(module => module.syncStoredPushDevice()).catch(() => undefined)
  }
  return { identity }
}

export function updateServerProfile(displayName: string, avatarId: string, frameId: string, animationId: string, titleId: string | null): Promise<AuthResponse> {
  return accountAction('update-profile', { displayName, avatarId, frameId, animationId, titleId })
}

export function equipServerCosmetic(kind: CosmeticKind, id: string): Promise<AuthResponse> {
  return accountAction('equip-cosmetic', { kind, id })
}

export function purchaseServerCosmetic(kind: CosmeticKind, id: string, idempotencyKey = crypto.randomUUID()): Promise<AuthResponse> {
  return accountAction('purchase-cosmetic', { kind, id, idempotencyKey })
}

export async function openServerBasket(basketId: string, idempotencyKey = crypto.randomUUID()): Promise<AuthResponse & { reward: CosmeticReward }> {
  return accountAction('open-basket', { basketId, idempotencyKey }) as Promise<AuthResponse & { reward: CosmeticReward }>
}
