export type MatchPresentationPhase = 'game' | 'result'

/**
 * A finished server snapshot may still contain a turn that the client has to
 * reveal. Keep the board mounted until that reveal has completely finished;
 * otherwise the result panel hides the final letters and score effects.
 */
export function matchPresentationPhase(
  status: 'active' | 'finished',
  resolvingTurn: boolean,
): MatchPresentationPhase {
  return status === 'active' || resolvingTurn ? 'game' : 'result'
}

export const FINAL_GRID_COMPLETION_HOLD_MS = 800
