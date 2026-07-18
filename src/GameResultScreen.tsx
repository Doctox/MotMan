import type { ReactNode } from 'react'
import { Feather, Minus } from 'lucide-react'
import { assetUrl } from './assetUrl'
import { ExperienceReward } from './ExperienceReward'
import type { ExperienceAward } from './playerProgress'

export type GameResultOutcome = 'win' | 'draw' | 'loss'

export function GameResultScreen({
  outcome,
  title,
  detail,
  playerScore,
  opponentScore,
  playerName = 'Vous',
  opponentName,
  award,
  children,
}: {
  outcome: GameResultOutcome
  title: string
  detail: string
  playerScore: number
  opponentScore: number
  playerName?: string
  opponentName: string
  award: ExperienceAward | null
  children: ReactNode
}) {
  return <section className={`game-result-screen result-${outcome}`} aria-labelledby="game-result-title">
    <div className="game-result-hero">
      {outcome === 'win' ? <img className="game-result-art" src={assetUrl('/assets/result-victory-hero.webp')} alt="" aria-hidden="true" />
        : outcome === 'loss' ? <img className="game-result-art" src={assetUrl('/assets/result-loss-hero.webp')} alt="" aria-hidden="true" /> : <>
        <Feather className="result-feather result-feather-left" aria-hidden="true" />
        <Feather className="result-feather result-feather-right" aria-hidden="true" />
        <div className="game-result-emblem" aria-hidden="true"><span><Minus /></span></div>
      </>}
      <h2 id="game-result-title">{title}</h2>
      <p>{detail}</p>
    </div>

    <div className="game-result-score" aria-label={`Score final : ${playerScore} à ${opponentScore}`}>
      <span className="game-result-score-side player-score"><strong>{playerScore}</strong><small>{playerName}</small></span>
      <i aria-hidden="true" />
      <span className="game-result-score-side opponent-score"><strong>{opponentScore}</strong><small>{opponentName}</small></span>
    </div>

    {award ? <ExperienceReward award={award} /> : <p className="experience-pending">Calcul de l’expérience…</p>}
    {children}
  </section>
}
