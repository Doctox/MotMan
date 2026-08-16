import { useEffect, useState } from 'react'
import { Check, ChevronRight, Flame, RotateCcw, Snowflake } from 'lucide-react'
import { currentDailyDateKey } from '../dailyDate'
import {
  dailyAttempts,
  dailyStatus,
  loadDailyChallengeState,
  type DailyAdvanceEffects,
  type DailyChallengeState,
  type DailyStatus,
} from '../dailyChallenge'
import './menu-daily.css'

// Composants « Défi du jour » — Option A (intégration chirurgicale).
// 100 % présentation, pilotés par l'état LOCAL réel (motman-daily-v1). Le défi
// est rejouable : trois états (à faire / perdu / gagné). Aucun changement de nav.
//
// ⚠️ AUCUN LIBELLÉ DE THÈME N'EST AFFICHÉ. Les 56 grilles publiées sont
// génériques : annoncer « Sport » ou « Animaux » serait mentir au joueur. Le champ
// `theme` reste au format du calendrier (contrat 3) et continue d'alimenter
// l'historique local, mais il ne sera réintroduit ici que le jour où de vraies
// grilles à thème seront publiées.

export function useDailyChallenge() {
  const [day] = useState(() => currentDailyDateKey())
  const [state, setState] = useState<DailyChallengeState>(() => loadDailyChallengeState())
  useEffect(() => {
    const sync = (event: Event) => {
      const detail = (event as CustomEvent<DailyChallengeState>).detail
      if (detail) setState(detail)
    }
    window.addEventListener('motman:daily', sync)
    return () => window.removeEventListener('motman:daily', sync)
  }, [])
  return {
    day,
    state,
    streak: state.currentStreak,
    freezes: state.freezes,
    status: dailyStatus(state, day) as DailyStatus,
    attempts: dailyAttempts(state, day),
  }
}

function streakLabel(streak: number): string {
  return streak > 1 ? `Série ${streak} jours` : streak === 1 ? 'Série 1 jour' : 'Commencez votre série'
}

// Heures restantes avant la prochaine bascule (minuit Europe/Paris). Approximation
// suffisante pour l'affichage « revient dans Xh » (ignore les jours de DST à 23/25 h).
function hoursUntilParisMidnight(nowMs: number): number {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Paris', hour12: false, hour: '2-digit', minute: '2-digit' })
    .format(new Date(nowMs)).split(':').map(Number)
  const minutesElapsed = (parts[0] ?? 0) * 60 + (parts[1] ?? 0)
  return Math.max(1, Math.ceil((24 * 60 - minutesElapsed) / 60))
}

/** Puce de série pour le header. Visible sur les 4 onglets, dès la 1re session. */
export function DailyStreakChip() {
  const { streak, status } = useDailyChallenge()
  return (
    <span
      className={`mm-streak-chip ${status === 'won' ? 'is-done' : ''}`}
      title={status === 'won' ? 'Défi du jour réussi' : 'Défi du jour'}
      aria-label={`${streakLabel(streak)}${status === 'won' ? ', défi du jour réussi' : ''}`}
    >
      <Flame aria-hidden="true" />
      <b>{streak}</b>
    </span>
  )
}

/**
 * Carte héro « Défi du jour », en tête de la zone mm-attention de l'Accueil.
 * Trois états rejouables : à faire / perdu (invitation, jamais sanction) / gagné.
 */
export function DailyChallengeHero({ onPlay }: { onPlay: () => void }) {
  const { status, streak, freezes, attempts } = useDailyChallenge()
  const [nowMs] = useState(() => Date.now())

  if (status === 'won') {
    const hours = hoursUntilParisMidnight(nowMs)
    return (
      <section className="mm-daily-hero is-done" aria-label="Défi du jour réussi">
        <span className="mm-daily-hero-badge" aria-hidden="true"><Check /></span>
        <div className="mm-daily-hero-copy">
          <small>Défi du jour</small>
          <strong>Défi réussi</strong>
          <span className="mm-daily-hero-meta">
            <Flame aria-hidden="true" />{streakLabel(streak)}
            <span className="mm-daily-dot" aria-hidden="true">·</span>revient dans {hours} h
          </span>
        </div>
      </section>
    )
  }

  if (status === 'lost') {
    return (
      <button type="button" className="mm-daily-hero is-lost" onClick={onPlay} aria-label={`Réessayer le défi du jour, tentative ${attempts + 1}. Vous avez jusqu'à minuit.`}>
        <span className="mm-daily-hero-badge" aria-hidden="true"><RotateCcw /></span>
        <div className="mm-daily-hero-copy">
          <small>Défi du jour · tentative {attempts}</small>
          <strong>Pas cette fois — on retente ?</strong>
          <span className="mm-daily-hero-meta">Tu as jusqu'à minuit pour le battre</span>
        </div>
        <ChevronRight aria-hidden="true" />
      </button>
    )
  }

  return (
    <button type="button" className="mm-daily-hero" onClick={onPlay} aria-label={`Jouer le défi du jour. ${streakLabel(streak)}.`}>
      <span className="mm-daily-hero-badge" aria-hidden="true"><Flame /></span>
      <div className="mm-daily-hero-copy">
        <small>Défi du jour</small>
        <strong>Jouer la grille du jour</strong>
        <span className="mm-daily-hero-meta">
          <Flame aria-hidden="true" />{streakLabel(streak)}
          {freezes > 0 ? <><span className="mm-daily-dot" aria-hidden="true">·</span><Snowflake aria-hidden="true" />gel ×{freezes}</> : null}
        </span>
      </div>
      <ChevronRight aria-hidden="true" />
    </button>
  )
}

/**
 * Ligne de série pour la séquence de récompense de fin de partie (à côté de l'XP
 * et des plumes), quand la partie terminée EST une victoire au défi du jour.
 * Pilotée par les effets d'une victoire (`recordDailyResult(...).effects`).
 */
export function DailyStreakReward({ effects }: { effects: DailyAdvanceEffects }) {
  if (!effects.changed) return null
  const milestone = effects.reachedMilestones.at(-1)
  return (
    <section className="mm-daily-reward" aria-label={`Série du défi du jour : ${effects.streak} jour${effects.streak > 1 ? 's' : ''}`}>
      <div className="mm-daily-reward-heading">
        <span><Flame aria-hidden="true" />Série</span>
        <strong>{effects.streak} jour{effects.streak > 1 ? 's' : ''}</strong>
      </div>
      {effects.usedFreeze ? <p className="mm-daily-reward-note"><Snowflake aria-hidden="true" />Gel de série utilisé — série préservée</p> : null}
      {effects.recovered ? <p className="mm-daily-reward-note"><Flame aria-hidden="true" />Série restaurée</p> : null}
      {milestone ? <p className="mm-daily-reward-milestone">Palier {milestone.streak} jours atteint{milestone.plumes > 0 ? ` · +${milestone.plumes} plumes` : ''}{milestone.freeze > 0 ? ` · +${milestone.freeze} gel` : ''}</p> : null}
    </section>
  )
}
