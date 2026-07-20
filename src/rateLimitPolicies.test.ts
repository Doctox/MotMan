import { describe, expect, it } from 'vitest'
import { actionRateLimits, globalRateLimit } from './rateLimitPolicies'

describe('rate-limit policies', () => {
  it('keeps normal match synchronization above the fallback polling cadence', () => {
    expect(globalRateLimit('match', true)).toEqual({
      bucket: 'match:all', maxRequests: 180, windowSeconds: 60,
    })
  })

  it('limits anonymous matchmaking more strictly than linked accounts', () => {
    const guest = actionRateLimits('match', 'search', true)[0]
    const account = actionRateLimits('match', 'search', false)[0]
    expect(guest.maxRequests).toBeLessThan(account.maxRequests)
    expect(guest.windowSeconds).toBe(300)
  })

  it('adds a target-specific ceiling to friend match invitations', () => {
    const policies = actionRateLimits('match', 'create', false, '119f939f-c374-4d77-918c-b2e9178ed813')
    expect(policies.map(policy => policy.bucket)).toContain('match:invite-target:119f939f-c374-4d77-918c-b2e9178ed813')
  })

  it('does not put untrusted text into a database bucket', () => {
    const policies = actionRateLimits('match', 'create', false, 'not:a:uuid')
    expect(policies).toHaveLength(1)
  })
})
