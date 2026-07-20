const defaultAllowedOrigins = new Set([
  'https://doctox.github.io',
  'https://localhost',
  'capacitor://localhost',
  'http://192.168.1.72:5173',
])

const localDevelopmentOrigin = /^http:\/\/(?:localhost|127\.0\.0\.1)(?::\d{1,5})?$/

function configuredOrigins(value: string | null | undefined): Set<string> {
  return new Set(String(value ?? '')
    .split(',')
    .map(origin => origin.trim().replace(/\/$/, ''))
    .filter(Boolean))
}

export function isAllowedOrigin(origin: string, additionalOrigins?: string | null): boolean {
  const normalized = origin.trim().replace(/\/$/, '')
  return defaultAllowedOrigins.has(normalized)
    || localDevelopmentOrigin.test(normalized)
    || configuredOrigins(additionalOrigins).has(normalized)
}

export function createHttpResponder(request: Request, additionalOrigins?: string | null) {
  const origin = request.headers.get('Origin')?.trim() ?? ''
  const originAllowed = !origin || isAllowedOrigin(origin, additionalOrigins)
  const corsHeaders: Record<string, string> = {
    'Access-Control-Allow-Headers': 'authorization, apikey, content-type, x-client-info',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Max-Age': '86400',
    'Vary': 'Origin',
  }
  if (origin && originAllowed) corsHeaders['Access-Control-Allow-Origin'] = origin

  const json = (status: number, body: unknown, extraHeaders: Record<string, string> = {}) => new Response(JSON.stringify(body), {
    status,
    headers: {
      ...corsHeaders,
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      ...extraHeaders,
    },
  })

  const preflight = () => originAllowed
    ? new Response('ok', { headers: corsHeaders })
    : new Response(null, { status: 403, headers: { 'Cache-Control': 'no-store', 'Vary': 'Origin' } })

  return { originAllowed, json, preflight }
}

export function logServerError(scope: string, error: unknown, context: Record<string, unknown> = {}): string {
  const reference = crypto.randomUUID()
  console.error(`[${scope}] ${reference}`, { ...context, error })
  return reference
}
