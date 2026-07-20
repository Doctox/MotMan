import { describe, expect, it } from 'vitest'
import { parseGoogleAuthIssue, rememberGoogleAuthIssue, takeRememberedGoogleAuthIssue } from './googleAuthCallback'

describe('retour de connexion Google', () => {
  it('reconnaît une identité déjà liée dans la query string', () => {
    expect(parseGoogleAuthIssue(
      '?error=identity_already_exists&error_description=Identity+is+already+linked+to+another+user',
      '#profil',
    )).toEqual({
      kind: 'identity-already-linked',
      message: 'Ce compte Google possède déjà un profil MotMan.',
    })
  })

  it('reconnaît le même conflit dans le fragment OAuth', () => {
    expect(parseGoogleAuthIssue('', '#error=server_error&error_description=Identity%20is%20already%20linked%20to%20another%20user'))
      .toMatchObject({ kind: 'identity-already-linked' })
  })

  it('transforme les autres erreurs OAuth en message contrôlé', () => {
    expect(parseGoogleAuthIssue('?error=access_denied&error_description=private-provider-detail', '#profil'))
      .toEqual({
        kind: 'oauth-error',
        message: 'La connexion Google n’a pas abouti. Réessayez dans un instant.',
      })
  })

  it('ignore une navigation normale dans le profil', () => {
    expect(parseGoogleAuthIssue('', '#profil')).toBeNull()
  })

  it('transporte une erreur native pendant le rechargement puis la consomme une seule fois', () => {
    const values = new Map<string, string>()
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    }
    const issue = { kind: 'identity-already-linked', message: 'Compte existant' } as const

    rememberGoogleAuthIssue(storage, issue)
    expect(takeRememberedGoogleAuthIssue(storage)).toEqual(issue)
    expect(takeRememberedGoogleAuthIssue(storage)).toBeNull()
  })
})
