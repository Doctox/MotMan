import { isNativeRuntime } from './nativeRuntime'

// ⚠️ Ces deux constantes DOIVENT rester alignées sur android/app/build.gradle
// (versionCode / versionName) et sur package.json (version). Une divergence fait
// qu'un APK s'annonce au serveur sous un ancien code : monter
// `minimum_android_version_code` bloquerait alors tous les testeurs sur l'écran de
// mise à jour obligatoire, sans issue côté client.
// Le contrôle de build `scripts/check_client_version.mjs` (câblé sur `prebuild`)
// fait échouer le build en cas d'écart.
export const ANDROID_VERSION_CODE = 6
export const ANDROID_VERSION_NAME = '1.0.5'

export function functionClientHeaders(native = isNativeRuntime()): Record<string, string> {
  return native
    ? {
        'x-motman-platform': 'android',
        'x-motman-version-code': String(ANDROID_VERSION_CODE),
      }
    : { 'x-motman-platform': 'web' }
}
