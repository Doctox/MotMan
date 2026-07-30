import type { SupabaseClient } from '@supabase/supabase-js'

const LEGACY_ANDROID_VERSION_CODE = 3
const CACHE_MS = 30_000

type ReleaseConfig = {
  minimumVersionCode: number
  latestVersionCode: number
  latestVersionName: string
  storeUrl: string
}

export type RequiredAndroidUpdate = ReleaseConfig & {
  installedVersionCode: number
}

let cachedConfig: { value: ReleaseConfig; expiresAt: number } | null = null

function positiveInteger(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export function androidClientVersion(request: Request): number | null {
  const platform = request.headers.get('x-motman-platform')?.trim().toLowerCase() ?? ''
  const origin = request.headers.get('origin')?.trim().replace(/\/$/, '') ?? ''
  const nativeAndroid = platform === 'android' || (!platform && origin === 'https://localhost')
  if (!nativeAndroid) return null
  return positiveInteger(request.headers.get('x-motman-version-code')) ?? LEGACY_ANDROID_VERSION_CODE
}

export function evaluateRequiredAndroidUpdate(
  installedVersionCode: number | null,
  config: ReleaseConfig,
): RequiredAndroidUpdate | null {
  if (!installedVersionCode || installedVersionCode >= config.minimumVersionCode) return null
  return { installedVersionCode, ...config }
}

async function releaseConfig(admin: SupabaseClient): Promise<ReleaseConfig | null> {
  if (cachedConfig && cachedConfig.expiresAt > Date.now()) return cachedConfig.value
  const { data, error } = await admin
    .from('server_app_config')
    .select('minimum_android_version_code,android_version_code,android_version_name,android_store_url')
    .eq('id', 'motman')
    .single()
  if (error || !data) return null
  const minimumVersionCode = positiveInteger(data.minimum_android_version_code)
  const latestVersionCode = positiveInteger(data.android_version_code)
  const latestVersionName = String(data.android_version_name ?? '')
  const storeUrl = String(data.android_store_url ?? '')
  if (!minimumVersionCode || !latestVersionCode || minimumVersionCode > latestVersionCode) return null
  const value = { minimumVersionCode, latestVersionCode, latestVersionName, storeUrl }
  cachedConfig = { value, expiresAt: Date.now() + CACHE_MS }
  return value
}

export async function requiredAndroidUpdate(
  request: Request,
  admin: SupabaseClient,
): Promise<RequiredAndroidUpdate | null> {
  const installedVersionCode = androidClientVersion(request)
  if (!installedVersionCode) return null
  const config = await releaseConfig(admin)
  return config ? evaluateRequiredAndroidUpdate(installedVersionCode, config) : null
}
