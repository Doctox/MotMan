import type { ExperienceAward } from './playerProgress'
import { MAX_PLAYER_LEVEL } from './playerProgress'
import { Feather, Sparkles } from 'lucide-react'

export function ExperienceReward({ award }: { award: ExperienceAward }) {
  const reachedMax = award.levelAfter >= MAX_PLAYER_LEVEL
  const progress = reachedMax || award.xpGoalAfter === 0 ? 100 : Math.min(100, award.xpAfter / award.xpGoalAfter * 100)
  const levelUp = award.levelAfter > award.levelBefore
  const featherDetails = award.featherBreakdown ? [
    ['Résultat', award.featherBreakdown.base],
    ['Sans indice', award.featherBreakdown.noHint],
    ['Sans renouvellement', award.featherBreakdown.noReroll],
    ['Chevalet complet', award.featherBreakdown.fullRack],
  ].filter((entry): entry is [string, number] => typeof entry[1] === 'number' && entry[1] > 0) : []
  return <section className="experience-reward" aria-label={`${award.breakdown.total} points d’expérience gagnés`}>
    <div className="experience-reward-heading"><span>Expérience</span><strong>+{award.breakdown.total} XP</strong></div>
    {award.plumesEarned ? <div className="experience-plumes"><Feather /><span>+{award.plumesEarned} plumes</span></div> : null}
    {featherDetails.length ? <div className="experience-feather-breakdown">{featherDetails.map(([label, amount]) => <span key={label}>{label}<b>+{amount}</b></span>)}</div> : null}
    <div className="experience-breakdown">
      <span>{award.breakdown.productiveTurns} tour{award.breakdown.productiveTurns > 1 ? 's' : ''} productif{award.breakdown.productiveTurns > 1 ? 's' : ''}<b>+{award.breakdown.productiveXp}</b></span>
      {award.breakdown.completionXp ? <span>Grille terminée<b>+{award.breakdown.completionXp}</b></span> : null}
      {award.breakdown.resultXp ? <span>Résultat<b>+{award.breakdown.resultXp}</b></span> : null}
    </div>
    <div className="experience-level"><span>{reachedMax ? 'Niveau maximum' : `Niveau ${award.levelAfter}`}</span>{levelUp ? <strong>Niveau supérieur !</strong> : reachedMax ? <strong>50</strong> : <small>{award.xpAfter} / {award.xpGoalAfter}</small>}</div>
    <i className="experience-progress"><b style={{ width: `${progress}%` }} /></i>
    {award.unlockedTitles?.map(title => <div className="experience-title-unlocked" key={title.id}><Sparkles /><span><small>Nouveau titre</small><strong>{title.name}</strong></span></div>)}
  </section>
}
