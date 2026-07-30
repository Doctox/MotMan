import { describe, expect, it } from 'vitest'
import {
  androidClientVersion,
  evaluateRequiredAndroidUpdate,
} from '../supabase/functions/_shared/clientVersion'

const config = {
  minimumVersionCode: 4,
  latestVersionCode: 4,
  latestVersionName: '1.0.3',
  storeUrl: 'https://play.google.com/store/apps/details?id=com.motman.game',
}

describe('contrôle de version Android côté Edge Functions', () => {
  it('reconnaît le nouveau client et l’ancien AAB Capacitor', () => {
    expect(androidClientVersion(new Request('https://example.test', {
      headers: { 'x-motman-platform': 'android', 'x-motman-version-code': '4' },
    }))).toBe(4)
    expect(androidClientVersion(new Request('https://example.test', {
      headers: { origin: 'https://localhost' },
    }))).toBe(3)
    expect(androidClientVersion(new Request('https://example.test', {
      headers: { 'x-motman-platform': 'web' },
    }))).toBeNull()
  })

  it('produit un blocage 426 seulement sous le minimum', () => {
    expect(evaluateRequiredAndroidUpdate(3, config)).toMatchObject({ installedVersionCode: 3 })
    expect(evaluateRequiredAndroidUpdate(4, config)).toBeNull()
    expect(evaluateRequiredAndroidUpdate(null, config)).toBeNull()
  })
})
