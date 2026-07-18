import { supabase } from './supabaseClient'

type FunctionFailure = Error & { payload?: Record<string, unknown>; status?: number }

export async function invokeSupabaseFunction<T>(name: string, body: Record<string, unknown>): Promise<T> {
  const { data, error } = await supabase.functions.invoke(name, { body })
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
  const failure = Object.assign(new Error(message), { payload, status }) as FunctionFailure
  throw failure
}
