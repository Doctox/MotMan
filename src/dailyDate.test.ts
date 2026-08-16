import { describe, expect, it } from 'vitest'
import { dailyDateKey } from './dailyDate'

describe('dailyDateKey (Europe/Paris)', () => {
  it('formate en YYYY-MM-DD et est déterministe', () => {
    const ms = Date.parse('2026-08-05T10:00:00Z')
    expect(dailyDateKey(ms)).toBe('2026-08-05')
    expect(dailyDateKey(ms)).toBe(dailyDateKey(ms))
  })

  it('bascule le jour à minuit heure d’été (Paris = UTC+2 → 22:00 UTC)', () => {
    expect(dailyDateKey(Date.parse('2026-07-15T21:59:59Z'))).toBe('2026-07-15')
    expect(dailyDateKey(Date.parse('2026-07-15T22:00:00Z'))).toBe('2026-07-16')
  })

  it('bascule le jour à minuit heure d’hiver (Paris = UTC+1 → 23:00 UTC)', () => {
    expect(dailyDateKey(Date.parse('2026-01-15T22:59:59Z'))).toBe('2026-01-15')
    expect(dailyDateKey(Date.parse('2026-01-15T23:00:00Z'))).toBe('2026-01-16')
  })
})
