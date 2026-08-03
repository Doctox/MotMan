import { isNativeRuntime } from './nativeRuntime'

export const ANDROID_VERSION_CODE = 5
export const ANDROID_VERSION_NAME = '1.0.4'

export function functionClientHeaders(native = isNativeRuntime()): Record<string, string> {
  return native
    ? {
        'x-motman-platform': 'android',
        'x-motman-version-code': String(ANDROID_VERSION_CODE),
      }
    : { 'x-motman-platform': 'web' }
}
