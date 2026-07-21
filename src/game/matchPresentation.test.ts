import { describe, expect, it } from 'vitest'
import { matchPresentationPhase } from './matchPresentation'

describe('matchPresentationPhase', () => {
  it('keeps the game visible during an active turn', () => {
    expect(matchPresentationPhase('active', false)).toBe('game')
  })

  it('keeps the board visible while the final turn is being revealed', () => {
    expect(matchPresentationPhase('finished', true)).toBe('game')
  })

  it('shows the result panel only after the final reveal', () => {
    expect(matchPresentationPhase('finished', false)).toBe('result')
  })
})
