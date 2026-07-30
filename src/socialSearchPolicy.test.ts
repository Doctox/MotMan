import { describe, expect, it } from 'vitest'
import {
  escapePostgresLikePattern,
  isValidSocialSearch,
  normalizeSocialSearch,
  SOCIAL_SEARCH_MAX_LENGTH,
  SOCIAL_SEARCH_MIN_LENGTH,
  SOCIAL_SEARCH_RESULT_LIMIT,
} from './socialSearchPolicy'

describe('friend search policy', () => {
  it('normalizes a partial pseudo without changing its accents', () => {
    expect(normalizeSocialSearch('  Élise   du 75 ')).toBe('Élise du 75')
  })

  it('requires a useful pseudo prefix and limits enumeration', () => {
    expect(isValidSocialSearch('Do')).toBe(false)
    expect(isValidSocialSearch('Doc')).toBe(true)
    expect(SOCIAL_SEARCH_MIN_LENGTH).toBe(3)
    expect(SOCIAL_SEARCH_MAX_LENGTH).toBe(16)
    expect(SOCIAL_SEARCH_RESULT_LIMIT).toBe(8)
  })

  it('rejects wildcard-like input and escapes SQL LIKE metacharacters defensively', () => {
    expect(isValidSocialSearch('Doc%')).toBe(false)
    expect(escapePostgresLikePattern('A_B%\\C')).toBe('A\\_B\\%\\\\C')
  })
})
