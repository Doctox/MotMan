import { describe, expect, it } from 'vitest'
import { createHttpResponder, isAllowedOrigin } from '../supabase/functions/_shared/http'

describe('Edge Function origin policy', () => {
  it('allows the production, native and local development origins', () => {
    expect(isAllowedOrigin('https://doctox.github.io')).toBe(true)
    expect(isAllowedOrigin('https://localhost')).toBe(true)
    expect(isAllowedOrigin('capacitor://localhost')).toBe(true)
    expect(isAllowedOrigin('http://127.0.0.1:4173')).toBe(true)
    expect(isAllowedOrigin('http://localhost:5173')).toBe(true)
    expect(isAllowedOrigin('http://192.168.1.72:5173')).toBe(true)
  })

  it('rejects untrusted origins and never returns a wildcard', () => {
    expect(isAllowedOrigin('https://example.com')).toBe(false)
    const http = createHttpResponder(new Request('https://motman.test', {
      method: 'OPTIONS',
      headers: { Origin: 'https://example.com' },
    }))
    const response = http.preflight()
    expect(response.status).toBe(403)
    expect(response.headers.get('Access-Control-Allow-Origin')).toBeNull()
  })

  it('echoes only an allowed request origin', () => {
    const http = createHttpResponder(new Request('https://motman.test', {
      headers: { Origin: 'https://doctox.github.io' },
    }))
    const response = http.json(200, { ok: true })
    expect(response.headers.get('Access-Control-Allow-Origin')).toBe('https://doctox.github.io')
    expect(response.headers.get('Vary')).toBe('Origin')
  })

  it('supports an explicit additional production origin', () => {
    expect(isAllowedOrigin('https://motman.example', 'https://motman.example, https://staging.motman.example')).toBe(true)
    expect(isAllowedOrigin('https://other.example', 'https://motman.example')).toBe(false)
  })

  it('keeps non-browser server requests available', () => {
    const http = createHttpResponder(new Request('https://motman.test'))
    expect(http.originAllowed).toBe(true)
    expect(http.json(200, { ok: true }).headers.get('Access-Control-Allow-Origin')).toBeNull()
  })
})
