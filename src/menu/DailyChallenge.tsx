import { useEffect, useState } from 'react'
import { Check, ChevronRight, Flame, RotateCcw, Snowflake } from 'lucide-react'
import { currentDailyDateKey, dailyDateKey } from '../dailyDate'
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
  // Le jour NE DOIT PAS être figé au montage : le menu reste souvent ouvert, et
  // un joueur qui passe minuit verrait sinon éternellement « Défi réussi » alors
  // qu'une nouvelle grille l'attend. On réévalue donc la clé de jour
  // périodiquement, et on ne déclenche un rendu que lorsqu'elle change vraiment.
  const [day, setDay] = useState(() => currentDailyDateKey())
  const [state, setState] = useState<DailyChallengeState>(() => loadDailyChallengeState())
  useEffect(() => {
    const sync = (event: Event) => {
      const detail = (event as CustomEvent<DailyChallengeState>).detail
      if (detail) setState(detail)
    }
    window.addEventListener('motman:daily', sync)
    return () => window.removeEventListener('motman:daily', sync)
  }, [])
  useEffect(() => {
    const refreshDay = () => {
      const current = currentDailyDateKey()
      setDay(previous => (previous === current ? previous : current))
    }
    // 30 s suffisent : la bascule est visible presque immédiatement sans
    // réveiller le rendu inutilement. `visibilitychange` couvre le cas le plus
    // fréquent sur mobile — l'app mise en veille la veille, rouverte le lendemain.
    const timer = window.setInterval(refreshDay, 30_000)
    document.addEventListener('visibilitychange', refreshDay)
    window.addEventListener('focus', refreshDay)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', refreshDay)
      window.removeEventListener('focus', refreshDay)
    }
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

/**
 * Millisecondes avant la prochaine grille, par recherche dichotomique sur la clé
 * de jour elle-même.
 *
 * POURQUOI PAS UN SIMPLE « 24 h − heure de Paris » : les jours de changement
 * d'heure durent 23 ou 25 h, et le calcul naïf se trompe alors d'une heure
 * pendant toute la journée. Interroger `dailyDateKey` donne la bascule réelle,
 * quel que soit le fuseau du joueur et quelles que soient les règles d'été.
 *
 * POURQUOI UN COMPTE À REBOURS ET PAS UNE HEURE : la bascule est fixée à minuit
 * à PARIS, pour que tout le monde ait la même grille au même instant. Annoncer
 * « à minuit » ne serait donc vrai qu'en France — au Québec la bascule tombe à
 * 18 h locale. Un compte à rebours reste juste partout.
 */
function msUntilNextDailyGrid(nowMs: number): number {
  const today = dailyDateKey(nowMs)
  let stillToday = 0
  let alreadyTomorrow = 26 * 3_600_000 // borne haute : couvre le jour le plus long
  while (alreadyTomorrow - stillToday > 30_000) {
    const middle = Math.floor((stillToday + alreadyTomorrow) / 2)
    if (dailyDateKey(nowMs + middle) === today) stillToday = middle
    else alreadyTomorrow = middle
  }
  return alreadyTomorrow
}

/** « 3 h 12 », « 21 min », « moins d'une minute ». La précision aux minutes évite
 *  qu'un « dans 1 h » arrondi se lise comme un défi qui reviendrait chaque heure. */
function countdownLabel(remainingMs: number): string {
  const totalMinutes = Math.floor(remainingMs / 60_000)
  if (totalMinutes < 1) return 'moins d’une minute'
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (hours === 0) return `${minutes} min`
  return minutes === 0 ? `${hours} h` : `${hours} h ${String(minutes).padStart(2, '0')}`
}

/** Compte à rebours vivant, réveillé aussi au retour de veille (usage mobile). */
function useDailyCountdown(): string {
  const [remainingMs, setRemainingMs] = useState(() => msUntilNextDailyGrid(Date.now()))
  useEffect(() => {
    const refresh = () => setRemainingMs(msUntilNextDailyGrid(Date.now()))
    const timer = window.setInterval(refresh, 30_000)
    document.addEventListener('visibilitychange', refresh)
    window.addEventListener('focus', refresh)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', refresh)
      window.removeEventListener('focus', refresh)
    }
  }, [])
  return countdownLabel(remainingMs)
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
  const countdown = useDailyCountdown()

  if (status === 'won') {
    return (
      <section className="mm-daily-hero is-done" aria-label={`Défi du jour réussi. ${streakLabel(streak)}. Nouvelle grille dans ${countdown}.`}>
        <span className="mm-daily-hero-badge" aria-hidden="true"><Check /></span>
        <div className="mm-daily-hero-copy">
          <small>Défi du jour</small>
          <strong>Défi réussi</strong>
          <span className="mm-daily-hero-meta">
            <Flame aria-hidden="true" />{streakLabel(streak)}
            <span className="mm-daily-dot" aria-hidden="true">·</span>nouvelle grille dans {countdown}
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
