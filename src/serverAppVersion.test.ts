import { describe, expect, it, vi } from 'vitest'
import {
  parseServerAppVersion,
  readCachedServerAppVersion,
  refreshServerAppVersion,
} from './serverAppVersion'

function memoryStorage() {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  }
}

const serverRow = {
  revision: 47,
  android_version_name: '1.0.2',
  android_version_code: 3,
  minimum_android_version_code: 3,
  android_store_url: 'https://play.google.com/store/apps/details?id=com.motman.game',
  updated_at: '2026-07-29T19:36:04.000Z',
}

describe('version MotMan pilotée par le serveur', () => {
  it('valide strictement les métadonnées publiques', () => {
    expect(parseServerAppVersion(serverRow)).toEqual({
      revision: 47,
      androidVersionName: '1.0.2',
      androidVersionCode: 3,
      minimumAndroidVersionCode: 3,
      androidStoreUrl: 'https://play.google.com/store/apps/details?id=com.motman.game',
      updatedAt: '2026-07-29T19:36:04.000Z',
    })
    expect(parseServerAppVersion({ ...serverRow, revision: 0 })).toBeNull()
    expect(parseServerAppVersion({ ...serverRow, android_version_name: 'prochaine' })).toBeNull()
    expect(parseServerAppVersion({ ...serverRow, minimum_android_version_code: 4 })).toBeNull()
    expect(parseServerAppVersion({ ...serverRow, android_store_url: 'https://example.com/app' })).toBeNull()
  })

  it('met en cache la dernière révision reçue', async () => {
    const storage = memoryStorage()
    expect(await refreshServerAppVersion(async () => serverRow, storage)).toMatchObject({ revision: 47 })
    expect(readCachedServerAppVersion(storage)).toMatchObject({ revision: 47, androidVersionCode: 3 })
  })

  it('reste lisible hors ligne grâce à la dernière valeur valide', async () => {
    const storage = memoryStorage()
    await refreshServerAppVersion(async () => serverRow, storage)
    const offlineQuery = vi.fn(async () => { throw new Error('hors ligne') })
    expect(await refreshServerAppVersion(offlineQuery, storage)).toMatchObject({ revision: 47 })
    expect(offlineQuery).toHaveBeenCalledOnce()
  })
})
