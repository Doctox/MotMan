import { isNativeRuntime } from './nativeRuntime'
import {
  readCachedServerAppVersion,
  refreshServerAppVersion,
  type ServerAppVersion,
} from './serverAppVersion'

export type RequiredAppUpdate = {
  installedVersionCode: number
  minimumVersionCode: number
  latestVersionCode: number
  latestVersionName: string
  storeUrl: string
}

function positiveInteger(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export function requiredUpdateFrom(
  installedVersionCode: number,
  serverVersion: ServerAppVersion | null,
): RequiredAppUpdate | null {
  if (!serverVersion || installedVersionCode >= serverVersion.minimumAndroidVersionCode) return null
  return {
    installedVersionCode,
    minimumVersionCode: serverVersion.minimumAndroidVersionCode,
    latestVersionCode: serverVersion.androidVersionCode,
    latestVersionName: serverVersion.androidVersionName,
    storeUrl: serverVersion.androidStoreUrl,
  }
}

export function requiredUpdateFromPayload(value: unknown): RequiredAppUpdate | null {
  if (!value || typeof value !== 'object') return null
  const payload = value as Record<string, unknown>
  const installedVersionCode = positiveInteger(payload.installedVersionCode) ?? 1
  const minimumVersionCode = positiveInteger(payload.minimumVersionCode)
  const latestVersionCode = positiveInteger(payload.latestVersionCode)
  const latestVersionName = String(payload.latestVersionName ?? '').trim()
  const storeUrl = String(payload.storeUrl ?? '').trim()
  if (
    !minimumVersionCode ||
    !latestVersionCode ||
    minimumVersionCode > latestVersionCode ||
    !/^\d+\.\d+\.\d+$/.test(latestVersionName) ||
    !storeUrl.startsWith('https://play.google.com/')
  ) return null
  return { installedVersionCode, minimumVersionCode, latestVersionCode, latestVersionName, storeUrl }
}

export async function checkRequiredAppUpdate(): Promise<RequiredAppUpdate | null> {
  if (!isNativeRuntime()) return null
  const { App } = await import('@capacitor/app')
  const info = await App.getInfo()
  const installedVersionCode = positiveInteger(info.build)
  if (!installedVersionCode) return null
  const serverVersion = await refreshServerAppVersion()
  return requiredUpdateFrom(installedVersionCode, serverVersion ?? readCachedServerAppVersion())
}
