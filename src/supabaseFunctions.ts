import { supabase } from './supabaseClient'
import { functionClientHeaders } from './clientVersion'

type FunctionFailure = Error & { payload?: Record<string, unknown>; status?: number }

// Panne du 28/08/2026 : des workers Edge immobilisés ont laissé les appels sans
// réponse pendant 150 secondes. Côté client, ça ne s'est pas traduit par une
// erreur mais par RIEN — l'app restait sur son écran d'ouverture, indéfiniment.
//
// Un appel qui n'aboutit jamais est pire qu'un appel qui échoue : le joueur n'a
// aucune information et aucun recours. On borne donc tous les appels ici, au
// seul endroit qu'ils traversent tous, plutôt que d'espérer que chaque appelant
// y pense. La requête réseau continue peut-être sa vie, mais l'interface, elle,
// cesse d'attendre et peut afficher quelque chose.
export const FUNCTION_TIMEOUT_MS = 20_000

function timeoutFailure(name: string): FunctionFailure {
  return Object.assign(
    new Error(`Le service ${name} ne répond pas. Vérifiez votre connexion, puis réessayez.`),
    { payload: { code: 'REQUEST_TIMEOUT' as const }, status: 0 },
  ) as FunctionFailure
}

export async function invokeSupabaseFunction<T>(
  name: string,
  body: Record<string, unknown>,
  timeoutMs: number = FUNCTION_TIMEOUT_MS,
): Promise<T> {
  let expiration: ReturnType<typeof setTimeout> | undefined
  const deadline = new Promise<never>((_, reject) => {
    expiration = setTimeout(() => reject(timeoutFailure(name)), timeoutMs)
  })
  try {
    return await Promise.race([callSupabaseFunction<T>(name, body), deadline])
  } finally {
    if (expiration !== undefined) clearTimeout(expiration)
  }
}

async function callSupabaseFunction<T>(name: string, body: Record<string, unknown>): Promise<T> {
  const { data, error } = await supabase.functions.invoke(name, {
    body,
    headers: functionClientHeaders(),
  })
  if (!error && !data?.error) return data as T

  let payload = data && typeof data === 'object' ? data as Record<string, unknown> : undefined
  let status: number | undefined
  const context = (error as { context?: unknown } | null)?.context
  if (context instanceof Response) {
    status = context.status
    if (!payload) {
      try { payload = await context.clone().json() as Record<string, unknown> } catch { /* Réponse non JSON. */ }
    }
  }
  const message = typeof payload?.error === 'string' ? payload.error : error?.message || `Le service ${name} est indisponible.`
  if (status === 426 || payload?.code === 'APP_UPDATE_REQUIRED') {
    window.dispatchEvent(new CustomEvent('motman:update-required', { detail: payload }))
  }
  const failure = Object.assign(new Error(message), { payload, status }) as FunctionFailure
  throw failure
}
