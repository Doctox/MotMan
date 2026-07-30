import { supabase, supabaseConfigured } from './supabaseClient'

export type ServerAppVersion = {
  revision: number
  androidVersionName: string
  androidVersionCode: number
  minimumAndroidVersionCode: number
  androidStoreUrl: string
  updatedAt: string
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>
type VersionQuery = () => Promise<unknown>

const CACHE_KEY = 'motman-server-app-version-v1'

function storageOrUndefined(): StorageLike | undefined {
  try {
    return globalThis.localStorage
  } catch {
    return undefined
  }
}

function positiveInteger(value: unknown): number | null {
  const number = typeof value === 'number' ? value : Number(value)
  return Number.isInteger(number) && number > 0 ? number : null
}

export function parseServerAppVersion(value: unknown): ServerAppVersion | null {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  const revision = positiveInteger(row.revision)
  const androidVersionCode = positiveInteger(row.android_version_code ?? row.androidVersionCode)
  const minimumAndroidVersionCode = positiveInteger(
    row.minimum_android_version_code ?? row.minimumAndroidVersionCode,
  )
  const androidVersionName = String(row.android_version_name ?? row.androidVersionName ?? '').trim()
  const androidStoreUrl = String(row.android_store_url ?? row.androidStoreUrl ?? '').trim()
  const updatedAt = String(row.updated_at ?? row.updatedAt ?? '').trim()
  if (
    !revision ||
    !androidVersionCode ||
    !minimumAndroidVersionCode ||
    minimumAndroidVersionCode > androidVersionCode ||
    !/^\d+\.\d+\.\d+$/.test(androidVersionName) ||
    !/^https:\/\/play\.google\.com\/store\/apps\/details\?id=[a-z0-9._]+$/i.test(androidStoreUrl) ||
    !updatedAt
  ) return null
  return {
    revision,
    androidVersionName,
    androidVersionCode,
    minimumAndroidVersionCode,
    androidStoreUrl,
    updatedAt,
  }
}

export function readCachedServerAppVersion(storage = storageOrUndefined()): ServerAppVersion | null {
  if (!storage) return null
  try {
    return parseServerAppVersion(JSON.parse(storage.getItem(CACHE_KEY) ?? 'null'))
  } catch {
    return null
  }
}

async function queryServerAppVersion(): Promise<unknown> {
  if (!supabaseConfigured) throw new Error('Supabase indisponible.')
  const { data, error } = await supabase
    .from('server_app_config')
    .select('revision,android_version_name,android_version_code,minimum_android_version_code,android_store_url,updated_at')
    .eq('id', 'motman')
    .single()
  if (error) throw error
  return data
}

export async function refreshServerAppVersion(
  query: VersionQuery = queryServerAppVersion,
  storage = storageOrUndefined(),
): Promise<ServerAppVersion | null> {
  const cached = readCachedServerAppVersion(storage)
  try {
    const current = parseServerAppVersion(await query())
    if (!current) return cached
    storage?.setItem(CACHE_KEY, JSON.stringify(current))
    return current
  } catch {
    return cached
  }
}
