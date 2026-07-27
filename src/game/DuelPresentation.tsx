import { useEffect, useState } from 'react'
import { Feather, Heart, HeartCrack, House } from 'lucide-react'
import { refreshPlayerAccount } from '../auth'
import { CosmeticPortrait } from '../CosmeticPortrait'
import { GameResultScreen } from '../GameResultScreen'
import {
  acknowledgeMatchResult,
  submitMatchGridFeedback,
  submitPendingResultFeedback,
  type MatchState,
  type PendingMatchResult,
} from '../matches'
import type { ExperienceAward } from '../playerProgress'
import { haptic, playEffect } from '../sensoryPreferences'

export function DuelPlayer({ name, score, active, initials, avatarId, frameId, animationId, player, detail }: { name: string; score: number; active: boolean; initials: string; avatarId?: string; frameId?: string; animationId?: string; player?: boolean; detail?: string }) {
  return <div className={`player ${active ? 'active' : ''} ${player ? 'player-you' : ''}`}>{avatarId ? <CosmeticPortrait avatarId={avatarId} frameId={frameId ?? 'cadre-ivoire'} animationId={animationId} alt="" className="game-portrait" /> : <span className="avatar">{initials}</span>}<span><small>{name}</small>{detail ? <em>{detail}</em> : null}<strong className="score-value" key={score}>{score}</strong></span></div>
}

export function ResultPanel({ match, playerId, opponentName, onExit, onHome }: { match: MatchState; playerId: string; opponentName: string; onExit: () => void; onHome: () => void }) {
  const [feedbackSent, setFeedbackSent] = useState(false)
  const [feedbackSending, setFeedbackSending] = useState(false)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)
  const [leaving, setLeaving] = useState(false)
  const [leavingError, setLeavingError] = useState<string | null>(null)
  const [experienceAward, setExperienceAward] = useState<ExperienceAward | null>(null)
  const won = match.winnerId === playerId
  const draw = match.winnerId === null && match.finishReason === 'completed'
  const title = draw ? 'Égalité !' : won ? 'Victoire !' : 'Partie terminée'
  const detail = match.finishReason === 'timeout'
    ? won ? `${opponentName} n’a pas réagi pendant trois de ses tours.` : 'Vous avez laissé expirer trois de vos tours.'
    : match.finishReason === 'forfeit'
      ? won ? `${opponentName} a quitté la partie.` : 'Vous avez abandonné la partie.'
      : draw ? 'Vous terminez avec le même score.' : won ? 'Vous avez rempli la grille avec le meilleur score.' : `${opponentName} remporte cette grille.`
  const sendFeedback = async (quality: 'yes' | 'no') => {
    if (feedbackSending || feedbackSent) return
    setFeedbackSending(true)
    setFeedbackError(null)
    try {
      await submitMatchGridFeedback(playerId, match.id, quality)
      setFeedbackSent(true)
    } catch (reason) {
      setFeedbackError(reason instanceof Error ? reason.message : 'Votre avis n’a pas pu être envoyé.')
    } finally {
      setFeedbackSending(false)
    }
  }
  const leaveResult = async (destination: () => void) => {
    if (leaving) return
    setLeaving(true)
    setLeavingError(null)
    try {
      await acknowledgeMatchResult(playerId, { matchId: match.id })
      destination()
    } catch (reason) {
      setLeavingError(reason instanceof Error ? reason.message : 'Le résultat n’a pas pu être validé.')
      setLeaving(false)
    }
  }
  useEffect(() => {
    let active = true
    void refreshPlayerAccount().then(response => {
      const award = response.progress?.experienceAwards.find(candidate => candidate.id === `server:match:${match.id}`) ?? null
      if (active) setExperienceAward(award)
    }).catch(() => undefined)
    haptic(won ? [18, 32, 18, 55, 28] : 24)
    playEffect(won ? 'word' : 'score')
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' })
    return () => { active = false }
  }, [match.id, won])
  const opponentId = match.playerIds.find(id => id !== playerId) ?? ''
  return <GameResultScreen
    outcome={draw ? 'draw' : won ? 'win' : 'loss'}
    title={title}
    detail={detail}
    playerScore={match.scores[playerId] ?? 0}
    opponentScore={match.scores[opponentId] ?? 0}
    opponentName={opponentName}
    award={experienceAward}
  >
    <div className="result-feedback">
      <p className="duel-feedback-label">{feedbackSent ? 'Merci pour votre retour !' : 'Cette grille était-elle agréable ?'}</p>
      {!feedbackSent ? <div className="feedback-actions"><button type="button" disabled={feedbackSending} onClick={() => void sendFeedback('yes')}><Heart />Oui</button><button type="button" disabled={feedbackSending} onClick={() => void sendFeedback('no')}><HeartCrack />Non</button></div> : null}
      {feedbackError ? <p className="result-feedback-error" role="alert">{feedbackError}</p> : null}
    </div>
    <div className="end-game-actions">
      <button type="button" className="new-game" disabled={leaving} onClick={() => void leaveResult(onExit)}><Feather />Nouvelle partie</button>
      <button type="button" className="end-game-home" disabled={leaving} onClick={() => void leaveResult(onHome)}><House />Retour à l’accueil</button>
    </div>
    {leavingError ? <p className="result-feedback-error" role="alert">{leavingError}</p> : null}
  </GameResultScreen>
}

export function PendingResultPanel({
  result,
  playerId,
  acknowledge,
}: {
  result: PendingMatchResult
  playerId: string
  acknowledge: (resultId: string) => Promise<void>
}) {
  const [feedbackSent, setFeedbackSent] = useState(result.feedbackSent)
  const [feedbackSending, setFeedbackSending] = useState(false)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)
  const [acknowledging, setAcknowledging] = useState(false)
  const [acknowledgeError, setAcknowledgeError] = useState<string | null>(null)
  const [experienceAward, setExperienceAward] = useState<ExperienceAward | null>(null)
  const won = result.outcome === 'win' || result.outcome === 'opponent-abandoned'
  const draw = result.outcome === 'draw'
  const opponentName = result.opponentName ?? (result.mode === 'solo' ? 'Adversaire solo' : 'Votre adversaire')
  const title = draw ? 'Égalité !' : won ? 'Victoire !' : 'Partie terminée'
  const detail = result.finishReason === 'timeout'
    ? won ? `${opponentName} n’a pas réagi pendant trois de ses tours.` : 'Vous avez laissé expirer trois de vos tours.'
    : result.finishReason === 'forfeit'
      ? won ? `${opponentName} a quitté la partie.` : 'Vous avez abandonné la partie.'
      : draw ? 'Vous terminez avec le même score.' : won ? 'Vous avez rempli la grille avec le meilleur score.' : `${opponentName} remporte cette grille.`

  useEffect(() => {
    let active = true
    void refreshPlayerAccount().then(response => {
      const award = response.progress?.experienceAwards.find(candidate => candidate.id === `server:match:${result.matchId}`) ?? null
      if (active) setExperienceAward(award)
    }).catch(() => undefined)
    haptic(won ? [18, 32, 18, 55, 28] : 24)
    playEffect(won ? 'word' : 'score')
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' })
    return () => { active = false }
  }, [result.id, result.matchId, won])

  const sendFeedback = async (quality: 'yes' | 'no') => {
    if (feedbackSending || feedbackSent) return
    setFeedbackSending(true)
    setFeedbackError(null)
    try {
      await submitPendingResultFeedback(playerId, result.id, quality)
      setFeedbackSent(true)
    } catch (reason) {
      setFeedbackError(reason instanceof Error ? reason.message : 'Votre avis n’a pas pu être envoyé.')
    } finally {
      setFeedbackSending(false)
    }
  }

  const confirmHome = async () => {
    if (acknowledging) return
    setAcknowledging(true)
    setAcknowledgeError(null)
    try {
      await acknowledge(result.id)
    } catch (reason) {
      setAcknowledgeError(reason instanceof Error ? reason.message : 'Le résultat n’a pas pu être validé.')
      setAcknowledging(false)
    }
  }

  return <GameResultScreen
    outcome={draw ? 'draw' : won ? 'win' : 'loss'}
    title={title}
    detail={detail}
    playerScore={result.score}
    opponentScore={result.opponentScore}
    opponentName={opponentName}
    award={experienceAward}
  >
    <div className="result-feedback">
      <p className="duel-feedback-label">{feedbackSent ? 'Merci pour votre retour !' : 'Cette grille était-elle agréable ?'}</p>
      {!feedbackSent ? <div className="feedback-actions"><button type="button" disabled={feedbackSending} onClick={() => void sendFeedback('yes')}><Heart />Oui</button><button type="button" disabled={feedbackSending} onClick={() => void sendFeedback('no')}><HeartCrack />Non</button></div> : null}
      {feedbackError ? <p className="result-feedback-error" role="alert">{feedbackError}</p> : null}
    </div>
    <div className="end-game-actions pending-result-actions">
      <button type="button" className="end-game-home" disabled={acknowledging} onClick={() => void confirmHome()}><House />Retour à l’accueil</button>
    </div>
    {acknowledgeError ? <p className="result-feedback-error" role="alert">{acknowledgeError}</p> : null}
  </GameResultScreen>
}

export function LeaveMatchPanel({ opponentName, isAsync = false, cancel, continueLater, leave }: { opponentName: string; isAsync?: boolean; cancel: () => void; continueLater?: () => void; leave: () => void }) {
  return <div className="mm-modal-layer mm-pause-layer"><section className="mm-pause duel-leave"><h2>Quitter la partie ?</h2><p>{isAsync ? 'Vous pouvez la reprendre plus tard ou l’abandonner définitivement.' : `${opponentName} remportera la partie par abandon.`}</p><button type="button" onClick={cancel}>Continuer à jouer</button>{isAsync && continueLater ? <button type="button" className="secondary" onClick={continueLater}>Reprendre plus tard</button> : null}<button type="button" className="danger" onClick={leave}>Abandonner la partie</button></section></div>
}

