import { describe, expect, it } from 'vitest'
import { requiredUpdateFrom, requiredUpdateFromPayload } from './appUpdate'
import type { ServerAppVersion } from './serverAppVersion'

const server: ServerAppVersion = {
  revision: 49,
  androidVersionName: '1.0.3',
  androidVersionCode: 4,
  minimumAndroidVersionCode: 4,
  androidStoreUrl: 'https://play.google.com/store/apps/details?id=com.motman.game',
  updatedAt: '2026-07-30T08:36:06.000Z',
}

describe('mise à jour Android obligatoire', () => {
  it('bloque seulement un bundle inférieur au minimum serveur', () => {
    expect(requiredUpdateFrom(3, server)).toMatchObject({
      installedVersionCode: 3,
      minimumVersionCode: 4,
      latestVersionName: '1.0.3',
    })
    expect(requiredUpdateFrom(4, server)).toBeNull()
    expect(requiredUpdateFrom(5, server)).toBeNull()
  })

  it('valide strictement un ordre 426 reçu pendant une session', () => {
    expect(requiredUpdateFromPayload({
      installedVersionCode: 3,
      minimumVersionCode: 4,
      latestVersionCode: 4,
      latestVersionName: '1.0.3',
      storeUrl: server.androidStoreUrl,
    })).toMatchObject({ minimumVersionCode: 4 })
    expect(requiredUpdateFromPayload({ minimumVersionCode: 4, latestVersionCode: 3 })).toBeNull()
  })
})
