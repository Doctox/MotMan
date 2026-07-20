type TurnstileWidget = {
  render: (container: HTMLElement, options: Record<string, unknown>) => string
  remove: (widgetId: string) => void
}

declare global {
  interface Window {
    turnstile?: TurnstileWidget
  }
}

const scriptId = 'motman-turnstile-script'
const scriptUrl = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
// Turnstile site keys are public. Keeping the production key as a fallback makes
// GitHub Pages and native builds safe even when no build variable is injected.
const productionSiteKey = '0x4AAAAAAD559OXTbbx2uJOM'
let scriptPromise: Promise<TurnstileWidget> | null = null

function configuredSiteKey(): string | null {
  const value = String(import.meta.env.VITE_TURNSTILE_SITE_KEY || productionSiteKey).trim()
  return value || null
}

export function isTurnstileConfigured(): boolean {
  return configuredSiteKey() !== null
}

function loadTurnstile(): Promise<TurnstileWidget> {
  if (window.turnstile) return Promise.resolve(window.turnstile)
  if (scriptPromise) return scriptPromise
  const pending = new Promise<TurnstileWidget>((resolve, reject) => {
    const existing = document.getElementById(scriptId) as HTMLScriptElement | null
    const script = existing ?? document.createElement('script')
    const finish = () => window.turnstile
      ? resolve(window.turnstile)
      : reject(new Error('La vérification de sécurité ne s’est pas chargée.'))
    script.addEventListener('load', finish, { once: true })
    script.addEventListener('error', () => reject(new Error('La vérification de sécurité est indisponible.')), { once: true })
    if (!existing) {
      script.id = scriptId
      script.src = scriptUrl
      script.async = true
      script.defer = true
      document.head.append(script)
    }
  })
  const loading = pending.catch(error => {
    scriptPromise = null
    throw error
  })
  scriptPromise = loading
  return loading
}

export async function getAnonymousCaptchaToken(): Promise<string | null> {
  const sitekey = configuredSiteKey()
  if (!sitekey) return null

  const turnstile = await loadTurnstile()
  const host = document.createElement('div')
  host.className = 'turnstile-guard'
  host.setAttribute('aria-label', 'Vérification de sécurité')
  document.body.append(host)

  return new Promise<string>((resolve, reject) => {
    let widgetId = ''
    let settled = false
    const timeout = window.setTimeout(() => finish(new Error('La vérification de sécurité a expiré. Réessayez.')), 30_000)
    const cleanup = () => {
      window.clearTimeout(timeout)
      if (widgetId) {
        try { turnstile.remove(widgetId) } catch { /* Le widget est peut-être déjà retiré. */ }
      }
      host.remove()
    }
    const finish = (result: string | Error) => {
      if (settled) return
      settled = true
      cleanup()
      if (result instanceof Error) reject(result)
      else resolve(result)
    }

    try {
      widgetId = turnstile.render(host, {
        sitekey,
        action: 'anonymous-sign-in',
        theme: 'auto',
        size: 'flexible',
        appearance: 'interaction-only',
        callback: (token: string) => finish(token),
        'error-callback': () => finish(new Error('La vérification de sécurité a échoué. Réessayez.')),
        'timeout-callback': () => finish(new Error('La vérification de sécurité a expiré. Réessayez.')),
      })
    } catch (error) {
      finish(error instanceof Error ? error : new Error('La vérification de sécurité est indisponible.'))
    }
  })
}
