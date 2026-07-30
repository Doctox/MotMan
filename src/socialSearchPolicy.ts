import { normalizePlayerName, PLAYER_NAME_MAX_LENGTH, PLAYER_NAME_MIN_LENGTH } from './playerNamePolicy.ts'

export const SOCIAL_SEARCH_MIN_LENGTH = PLAYER_NAME_MIN_LENGTH
export const SOCIAL_SEARCH_MAX_LENGTH = PLAYER_NAME_MAX_LENGTH
export const SOCIAL_SEARCH_RESULT_LIMIT = 8

export function normalizeSocialSearch(value: unknown): string {
  if (typeof value !== 'string') return ''
  return Array.from(normalizePlayerName(value)).slice(0, SOCIAL_SEARCH_MAX_LENGTH).join('')
}

export function isValidSocialSearch(value: unknown): boolean {
  const query = normalizeSocialSearch(value)
  const length = Array.from(query).length
  return length >= SOCIAL_SEARCH_MIN_LENGTH && length <= SOCIAL_SEARCH_MAX_LENGTH &&
    /^[\p{L}\p{N}](?:[\p{L}\p{N} _'’\-]*[\p{L}\p{N}])?$/u.test(query)
}

export function escapePostgresLikePattern(value: string): string {
  return value.replace(/[\\%_]/g, character => `\\${character}`)
}
