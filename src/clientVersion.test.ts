import { describe, expect, it } from 'vitest'
import {
  ANDROID_VERSION_CODE,
  ANDROID_VERSION_NAME,
  functionClientHeaders,
} from './clientVersion'

// Le 16/08/2026, clientVersion.ts annonçait encore 5 / 1.0.4 alors que le bundle
// publié était en 6 / 1.0.5. Monter `minimum_android_version_code` à 6 aurait
// enfermé TOUS les testeurs derrière l'écran de mise à jour obligatoire, sans
// issue côté client.
//
// La cohérence entre clientVersion.ts, android/app/build.gradle et package.json
// est vérifiée par scripts/check_client_version.mjs, câblé sur `pretest:unit` et
// `prebuild` : l'écart fait donc échouer aussi bien les tests que la construction.
// Ce contrôle vit dans un script Node et non ici, parce que tsconfig.app.json
// n'expose délibérément que les types `vite/client` — le code de l'application ne
// doit pas voir les API Node.
describe('identité de version envoyée aux Edge Functions', () => {
  it('annonce précisément le bundle Android publié', () => {
    expect(ANDROID_VERSION_CODE).toBe(6)
    expect(ANDROID_VERSION_NAME).toBe('1.0.5')
    expect(functionClientHeaders(true)).toEqual({
      'x-motman-platform': 'android',
      'x-motman-version-code': '6',
    })
  })

  it('distingue le site web qui se met à jour automatiquement', () => {
    expect(functionClientHeaders(false)).toEqual({ 'x-motman-platform': 'web' })
  })
})
