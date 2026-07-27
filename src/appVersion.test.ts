import { describe, expect, it } from 'vitest'
import { formatAppVersion } from './appVersion'

describe('formatAppVersion', () => {
  it('affiche le numéro de mise à jour GitHub et le code exact', () => {
    expect(formatAppVersion({
      version: '1.4.0',
      updateNumber: '287',
      buildSha: 'a1b2c3d',
    })).toEqual({
      updateLabel: '#287',
      buildLabel: 'Version 1.4.0 · a1b2c3d',
      accessibleLabel: '#287, version 1.4.0, code a1b2c3d',
    })
  })

  it('identifie clairement un build local', () => {
    expect(formatAppVersion({
      version: '0.1.0',
      updateNumber: 'local',
      buildSha: '7654321',
    }).updateLabel).toBe('Local')
  })
})
