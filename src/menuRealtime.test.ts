import { describe, expect, it } from 'vitest'
import { readMenuWakeupScope } from './menuRealtime'
import { lobbyMenuPollDelay, socialMenuPollDelay } from './menuSyncPolicy'

describe('menu Realtime wake-ups', () => {
  it('ne fait confiance qu’aux portées connues', () => {
    expect(readMenuWakeupScope({ scope: 'lobby' })).toBe('lobby')
    expect(readMenuWakeupScope({ scope: 'social' })).toBe('social')
    expect(readMenuWakeupScope({ scope: 'secret-data' })).toBe('all')
    expect(readMenuWakeupScope(null)).toBe('all')
  })

  it('garde un polling lent lorsque Realtime est connecté', () => {
    expect(socialMenuPollDelay('visible', true)).toBe(60_000)
    expect(lobbyMenuPollDelay('visible', true, true)).toBe(45_000)
    expect(lobbyMenuPollDelay('hidden', true, false)).toBe(60_000)
  })

  it('accélère seulement le secours si Realtime est indisponible', () => {
    expect(socialMenuPollDelay('visible', false)).toBe(30_000)
    expect(lobbyMenuPollDelay('visible', false, false)).toBe(30_000)
    expect(lobbyMenuPollDelay('visible', false, true)).toBe(8_000)
  })
})
