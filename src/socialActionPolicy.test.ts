import { describe, expect, it } from 'vitest'
import { socialActionRoute } from './socialActionPolicy'

describe('routage des actions sociales', () => {
  it('charge l’état social sans exiger de joueur cible', () => {
    expect(socialActionRoute('state')).toBe('state')
  })

  it.each(['cancel', 'remove', 'block', 'unblock', 'report'])(
    'réserve %s aux actions visant un joueur',
    action => {
      expect(socialActionRoute(action)).toBe('target')
    },
  )

  it('ne transforme pas une action inconnue en action visant un joueur', () => {
    expect(socialActionRoute('inconnue')).toBe('unknown')
  })
})
