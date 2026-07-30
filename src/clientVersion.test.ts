import { describe, expect, it } from 'vitest'
import {
  ANDROID_VERSION_CODE,
  ANDROID_VERSION_NAME,
  functionClientHeaders,
} from './clientVersion'

describe('identité de version envoyée aux Edge Functions', () => {
  it('annonce précisément le prochain bundle Android', () => {
    expect(ANDROID_VERSION_CODE).toBe(4)
    expect(ANDROID_VERSION_NAME).toBe('1.0.3')
    expect(functionClientHeaders(true)).toEqual({
      'x-motman-platform': 'android',
      'x-motman-version-code': '4',
    })
  })

  it('distingue le site web qui se met à jour automatiquement', () => {
    expect(functionClientHeaders(false)).toEqual({ 'x-motman-platform': 'web' })
  })
})
