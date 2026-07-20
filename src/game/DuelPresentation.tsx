import { useEffect, useState } from 'react'
import { Feather, Heart, HeartCrack, House } from 'lucide-react'
import { refreshPlayerAccount } from '../auth'
import { CosmeticPortrait } from '../CosmeticPortrait'
import { GameResultScreen } from '../GameResultScreen'
import { submitMatchGridFeedback, type MatchState } from '../matches'
import type { ExperienceAward } from '../playerProgress'
import { haptic, playEffect } from '../sensoryPreferences'

export function DuelPlayer({ name, score, active, initials, avatarId, frameId, animationId, player, detail }: { name: string; score: number; active: boolean; initials: string; avatarId?: string; frameId?: string; animationId?: string; player?: boolean; detail?: string }) {
  return <div className={`player ${active ? 'active' : ''} ${player ? 'player-you' : ''}`}>{avatarId ? <CosmeticPortrait avatarId={avatarId} frameId={frameId ?? 'cadre-ivoire'} animationId={animationId} alt="" className="game-portrait" /> : <span className="avatar">{initials}</span>}<span><small>{name}</small>{detail ? <em>{detail}</em> : null}<strong className="score-value" key={score}>{score}</strong></span></div>
}

export function ResultPanel({ match, playerId, opponentName, onExit, onHome }: { match: MatchState; playerId: string; opponentName: string; onExit: () => void; onHome: () => void }) {
  const [feedbackSent, setFeedbackSent] = useState(false)
  const [feedbackSending, setFeedbackSending] = useState(false)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)
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
      <button type="button" className="new-game" onClick={onExit}><Feather />Nouvelle partie</button>
      <button type="button" className="end-game-home" onClick={onHome}><House />Retour à l’accueil</button>
    </div>
  </GameResultScreen>
}

export function LeaveMatchPanel({ opponentName, isAsync = false, cancel, continueLater, leave }: { opponentName: string; isAsync?: boolean; cancel: () => void; continueLater?: () => void; leave: () => void }) {
  return <div className="mm-modal-layer mm-pause-layer"><section className="mm-pause duel-leave"><h2>Quitter la partie ?</h2><p>{isAsync ? 'Vous pouvez la reprendre plus tard ou l’abandonner définitivement.' : `${opponentName} remportera la partie par abandon.`}</p><button type="button" onClick={cancel}>Continuer à jouer</button>{isAsync && continueLater ? <button type="button" className="secondary" onClick={continueLater}>Reprendre plus tard</button> : null}<button type="button" className="danger" onClick={leave}>Abandonner la partie</button></section></div>
}

