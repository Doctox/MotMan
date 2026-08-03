export type SocialActionRoute =
  | 'state'
  | 'search'
  | 'presence'
  | 'request'
  | 'respond'
  | 'moderation'
  | 'target'
  | 'unknown'

const TARGET_ACTIONS = new Set(['cancel', 'remove', 'block', 'unblock', 'report'])

export function socialActionRoute(action: string): SocialActionRoute {
  if (action === 'state') return 'state'
  if (action === 'search') return 'search'
  if (action === 'presence') return 'presence'
  if (action === 'request') return 'request'
  if (action === 'respond') return 'respond'
  if (action === 'moderation-list' || action === 'moderation-resolve') return 'moderation'
  if (TARGET_ACTIONS.has(action)) return 'target'
  return 'unknown'
}
