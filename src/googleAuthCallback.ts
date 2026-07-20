export type GoogleAuthIssue = {
  kind: 'identity-already-linked' | 'oauth-error'
  message: string
}

export const GOOGLE_AUTH_ISSUE_STORAGE_KEY = 'motman-google-auth-issue-v1'

function callbackParams(search: string, hash: string): URLSearchParams[] {
  const candidates = [search.replace(/^\?/, '')]
  const hashValue = hash.replace(/^#/, '')
  const hashQuery = hashValue.includes('?') ? hashValue.slice(hashValue.indexOf('?') + 1) : hashValue
  candidates.push(hashQuery)
  return candidates.filter(Boolean).map(value => new URLSearchParams(value))
}

export function parseGoogleAuthIssue(search: string, hash: string): GoogleAuthIssue | null {
  for (const params of callbackParams(search, hash)) {
    const code = (params.get('error_code') ?? params.get('error') ?? '').toLocaleLowerCase('en')
    const description = (params.get('error_description') ?? '').replace(/\+/g, ' ').trim()
    if (!code && !description) continue

    const normalizedDescription = description.toLocaleLowerCase('en')
    if (code.includes('identity_already_exists') || normalizedDescription.includes('already linked to another user')) {
      return {
        kind: 'identity-already-linked',
        message: 'Ce compte Google possède déjà un profil MotMan.',
      }
    }

    return {
      kind: 'oauth-error',
      message: 'La connexion Google n’a pas abouti. Réessayez dans un instant.',
    }
  }
  return null
}

export function rememberGoogleAuthIssue(storage: Pick<Storage, 'setItem'>, issue: GoogleAuthIssue): void {
  try {
    storage.setItem(GOOGLE_AUTH_ISSUE_STORAGE_KEY, JSON.stringify(issue))
  } catch {
    // Some private browsing modes can refuse session storage.
  }
}

export function takeRememberedGoogleAuthIssue(storage: Pick<Storage, 'getItem' | 'removeItem'>): GoogleAuthIssue | null {
  try {
    const stored = storage.getItem(GOOGLE_AUTH_ISSUE_STORAGE_KEY)
    storage.removeItem(GOOGLE_AUTH_ISSUE_STORAGE_KEY)
    if (!stored) return null
    const issue = JSON.parse(stored) as Partial<GoogleAuthIssue>
    return (issue.kind === 'identity-already-linked' || issue.kind === 'oauth-error') && typeof issue.message === 'string'
      ? issue as GoogleAuthIssue
      : null
  } catch {
    return null
  }
}
