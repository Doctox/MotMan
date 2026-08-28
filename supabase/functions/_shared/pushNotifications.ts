import type { SupabaseClient } from '@supabase/supabase-js'

type PushMessage = {
  title: string
  body: string
  data: Record<string, string>
  tag?: string
}

type FirebaseServiceAccount = {
  project_id: string
  client_email: string
  private_key: string
  token_uri?: string
}

type PushDevice = { id: string; token: string }

const FCM_SCOPE = 'https://www.googleapis.com/auth/firebase.messaging'

// Panne de production du 28/08/2026 : des workers Edge sont restés immobilisés
// 150 secondes (la limite de la plateforme), jusqu'à ce que `account-api` et
// `social-api` répondent 504 IDLE_TIMEOUT et 546 WORKER_RESOURCE_LIMIT et que
// l'app ne démarre plus du tout.
//
// Les deux appels ci-dessous partent vers Google et étaient lancés SANS aucune
// borne de temps, puis confiés à `EdgeRuntime.waitUntil` : un Google lent
// gardait donc le worker en vie bien après que la réponse HTTP soit partie.
// Une notification perdue est un incident mineur ; un serveur de jeu gelé, non.
// On préfère explicitement rater l'envoi que retenir le worker.
const FCM_TIMEOUT_MS = 8_000

const encoder = new TextEncoder()
let cachedAccessToken: { value: string; expiresAt: number } | null = null
let configurationWarningLogged = false

function base64Url(value: string | Uint8Array): string {
  const bytes = typeof value === 'string' ? encoder.encode(value) : value
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

function serviceAccount(): FirebaseServiceAccount | null {
  const raw = Deno.env.get('FIREBASE_SERVICE_ACCOUNT_JSON')
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<FirebaseServiceAccount>
    if (!parsed.project_id || !parsed.client_email || !parsed.private_key) return null
    return parsed as FirebaseServiceAccount
  } catch {
    return null
  }
}

async function importPrivateKey(pem: string): Promise<CryptoKey> {
  const compact = pem.replace(/-----BEGIN PRIVATE KEY-----|-----END PRIVATE KEY-----|\s/g, '')
  const binary = atob(compact)
  const bytes = Uint8Array.from(binary, character => character.charCodeAt(0))
  return crypto.subtle.importKey('pkcs8', bytes, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['sign'])
}

async function firebaseAccessToken(account: FirebaseServiceAccount): Promise<string> {
  if (cachedAccessToken && cachedAccessToken.expiresAt > Date.now() + 60_000) return cachedAccessToken.value
  const issuedAt = Math.floor(Date.now() / 1000)
  const tokenUri = account.token_uri ?? 'https://oauth2.googleapis.com/token'
  const unsigned = `${base64Url(JSON.stringify({ alg: 'RS256', typ: 'JWT' }))}.${base64Url(JSON.stringify({
    iss: account.client_email,
    scope: FCM_SCOPE,
    aud: tokenUri,
    iat: issuedAt,
    exp: issuedAt + 3600,
  }))}`
  const signature = await crypto.subtle.sign('RSASSA-PKCS1-v1_5', await importPrivateKey(account.private_key), encoder.encode(unsigned))
  const assertion = `${unsigned}.${base64Url(new Uint8Array(signature))}`
  const response = await fetch(tokenUri, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer', assertion }),
    signal: AbortSignal.timeout(FCM_TIMEOUT_MS),
  })
  const payload = await response.json() as { access_token?: string; expires_in?: number; error_description?: string }
  if (!response.ok || !payload.access_token) throw new Error(payload.error_description ?? 'Jeton Firebase indisponible.')
  cachedAccessToken = { value: payload.access_token, expiresAt: Date.now() + Math.max(60, payload.expires_in ?? 3600) * 1000 }
  return payload.access_token
}

function firebaseErrorCode(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return ''
  const error = (payload as { error?: { details?: Array<Record<string, unknown>> } }).error
  for (const detail of error?.details ?? []) {
    if (typeof detail.errorCode === 'string') return detail.errorCode
  }
  return ''
}

async function sendToDevice(account: FirebaseServiceAccount, accessToken: string, device: PushDevice, message: PushMessage) {
  const response = await fetch(`https://fcm.googleapis.com/v1/projects/${encodeURIComponent(account.project_id)}/messages:send`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: {
        token: device.token,
        notification: { title: message.title, body: message.body },
        data: message.data,
        android: {
          priority: 'high',
          notification: {
            channel_id: 'motman_turns',
            icon: 'ic_stat_motman',
            color: '#0B5A49',
            sound: 'default',
            tag: message.tag ?? message.data.matchId ?? message.data.type,
          },
        },
      },
    }),
    signal: AbortSignal.timeout(FCM_TIMEOUT_MS),
  })
  const payload = await response.json().catch(() => ({}))
  return { ok: response.ok, invalid: ['UNREGISTERED', 'INVALID_ARGUMENT'].includes(firebaseErrorCode(payload)) }
}

export async function sendPushToUser(admin: SupabaseClient, userId: string, message: PushMessage): Promise<void> {
  const account = serviceAccount()
  if (!account) {
    if (!configurationWarningLogged) {
      configurationWarningLogged = true
      console.info('Notifications push inactives : FIREBASE_SERVICE_ACCOUNT_JSON absent ou invalide.')
    }
    return
  }

  const cutoff = new Date(Date.now() - 90 * 86400000).toISOString()
  const { data, error } = await admin.from('push_devices').select('id,token')
    .eq('user_id', userId).eq('enabled', true).gte('last_seen_at', cutoff)
  if (error) throw error
  const devices = (data ?? []) as PushDevice[]
  if (!devices.length) return

  const accessToken = await firebaseAccessToken(account)
  const results = await Promise.allSettled(devices.map(device => sendToDevice(account, accessToken, device, message)))
  const invalidIds: string[] = []
  const notifiedIds: string[] = []
  results.forEach((result, index) => {
    if (result.status === 'fulfilled' && result.value.invalid) invalidIds.push(devices[index].id)
    else if (result.status === 'fulfilled' && result.value.ok) notifiedIds.push(devices[index].id)
  })
  if (invalidIds.length) await admin.from('push_devices').delete().in('id', invalidIds)
  if (notifiedIds.length) await admin.from('push_devices').update({ last_notified_at: new Date().toISOString() }).in('id', notifiedIds)
}

// Filet de sécurité au-dessus des délais de `fetch` : quoi qu'il arrive dans la
// tâche confiée à `waitUntil` — un appel réseau imprévu, une écriture en base
// qui traîne — le worker est libéré au bout de PUSH_TASK_DEADLINE_MS. Sans
// cela, il faut qu'AUCUN futur ajout dans cette chaîne n'oublie sa borne ; avec
// cela, l'oubli reste sans conséquence pour la disponibilité du serveur.
const PUSH_TASK_DEADLINE_MS = 20_000

export function queuePush(task: Promise<void>): void {
  const guarded = task.catch(error => console.error('Notification push non envoyée', error))
  let deadline: ReturnType<typeof setTimeout> | undefined
  const bounded = Promise.race([
    guarded,
    new Promise<void>(resolve => {
      deadline = setTimeout(() => {
        console.error(`Notification push abandonnée après ${PUSH_TASK_DEADLINE_MS} ms — le worker est libéré.`)
        resolve()
      }, PUSH_TASK_DEADLINE_MS)
    }),
  ]).finally(() => { if (deadline !== undefined) clearTimeout(deadline) })
  const runtime = (globalThis as typeof globalThis & { EdgeRuntime?: { waitUntil(promise: Promise<unknown>): void } }).EdgeRuntime
  if (runtime) runtime.waitUntil(bounded)
  else void bounded
}
