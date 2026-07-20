import { describe, expect, it } from 'vitest'
import { MATCH_STATE_CONFLICT_CODE, matchStateFromConflict } from './matchConflict'

describe('conflits de synchronisation de partie', () => {
  it('récupère uniquement l’état fourni par un conflit optimiste contrôlé', () => {
    const match = { id: 'match-1', updatedAt: '2026-07-20T12:00:01.000Z' }
    const reason = Object.assign(new Error('Synchronisation'), {
      status: 409,
      payload: { code: MATCH_STATE_CONFLICT_CODE, conflict: true, match },
    })

    expect(matchStateFromConflict<typeof match>(reason)).toBe(match)
  })

  it('ne masque pas les autres erreurs métier ou réseau', () => {
    expect(matchStateFromConflict({ status: 409, payload: { error: 'Ce n’est pas votre tour.' } })).toBeNull()
    expect(matchStateFromConflict({ status: 500, payload: { code: MATCH_STATE_CONFLICT_CODE, conflict: true, match: {} } })).toBeNull()
    expect(matchStateFromConflict(new Error('Connexion interrompue'))).toBeNull()
  })
})
