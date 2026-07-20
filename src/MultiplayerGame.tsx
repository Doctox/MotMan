import { memo, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { ArrowLeft, Check, Feather, Heart, HeartCrack, House, Hourglass, Lightbulb, Settings, Shuffle, Wifi } from 'lucide-react'
import { assetUrl } from './assetUrl'
import type { ClueEntry, GeneratedGrid } from './generator'
import { loadPlayerIdentity, playerInitials } from './playerIdentity'
import { forfeitMatch, loadMatch, playMatchTurn, requestMatchHint, rerollMatchRack, submitMatchGridFeedback, type MatchState, type MatchTurn } from './matches'
import './styles.css'
import { GameOptionsOverlay, ReportPlayerOverlay } from './GameOverlays'
import { reportPlayer, setSocialPresence } from './social'
import { BoardScoreEffects } from './BoardScoreEffects'
import { BoardWordHighlight, type BoardWordHighlightState } from './BoardWordHighlight'
import type { ExperienceAward } from './playerProgress'
import { refreshPlayerAccount } from './auth'
import { GameResultScreen } from './GameResultScreen'
import { ClueZoom } from './ClueZoom'
import { haptic, playEffect } from './sensoryPreferences'
import { useDragGhost } from './useDragGhost'
import { loadPlayerCosmetics } from './cosmetics'
import { CosmeticPortrait } from './CosmeticPortrait'
import { canUseReroll, gameWordCellIndexes, REWARD_EFFECT_LIFETIME_MS, REWARD_STEP_MS } from './gameRules'
import { startAdaptivePolling, type AdaptivePollingController } from './adaptivePolling'
import { createMatchRackTiles, type RackTile } from './rackTiles'
import { subscribeToMatchUpdates } from './matchRealtime'
import { matchPollDelay } from './matchSyncPolicy'

type Tile = RackTile
type ScoreEffect = { id: string; kind: 'letter' | 'word'; label: string; owner: 'player' | 'bot'; cellIndex: number }
type HintFlight = { letter: string; cellIndex: number; fromX: number; fromY: number; deltaX: number; deltaY: number }
const DIFFICULTY_LABELS = { easy: 'Facile', normal: 'Normale', hard: 'Difficile' } as const
let multiplayerEffectSequence = 0
const TURN_READY_DURATION_MS = 1_800
const ASYNC_TURN_DURATION_SECONDS = 24 * 60 * 60

function turnClockLabel(seconds: number, async: boolean): string {
  if (!async) return String(Math.min(45, seconds))
  const visibleSeconds = Math.min(ASYNC_TURN_DURATION_SECONDS, seconds)
  if (visibleSeconds >= 3_600) return `${Math.ceil(visibleSeconds / 3_600)}h`
  if (visibleSeconds >= 60) return `${Math.ceil(visibleSeconds / 60)}m`
  return `${visibleSeconds}s`
}

type TurnPhase = { started: boolean; expired: boolean; urgent: boolean }

function phaseAt(match: MatchState | null, instant = Date.now()): TurnPhase {
  if (!match || match.status !== 'active') return { started: false, expired: false, urgent: false }
  const startsAt = new Date(match.turnStartedAt).getTime()
  const endsAt = new Date(match.turnEndsAt).getTime()
  const started = instant >= startsAt
  const expired = instant >= endsAt
  return { started, expired, urgent: match.pace === 'realtime' && started && !expired && endsAt - instant <= 10_000 }
}

function useTurnPhase(match: MatchState | null): TurnPhase {
  const [phase, setPhase] = useState<TurnPhase>(() => phaseAt(match))
  useEffect(() => {
    const update = () => {
      const next = phaseAt(match)
      setPhase(current => current.started === next.started && current.expired === next.expired && current.urgent === next.urgent ? current : next)
    }
    update()
    if (!match || match.status !== 'active') return
    const now = Date.now()
    const startsAt = new Date(match.turnStartedAt).getTime()
    const endsAt = new Date(match.turnEndsAt).getTime()
    const boundaries = [startsAt, match.pace === 'realtime' ? endsAt - 10_000 : 0, endsAt]
      .filter(boundary => boundary > now)
      .map(boundary => window.setTimeout(update, boundary - now + 8))
    return () => boundaries.forEach(timer => window.clearTimeout(timer))
  }, [match?.id, match?.pace, match?.status, match?.turnEndsAt, match?.turnNumber, match?.turnStartedAt])
  return phase
}

function TurnTimer({ match, resolving, started }: { match: MatchState; resolving: boolean; started: boolean }) {
  const labelAt = () => {
    if (match.status !== 'active' || resolving || !started) return '—'
    const seconds = Math.max(0, Math.ceil((new Date(match.turnEndsAt).getTime() - Date.now()) / 1_000))
    return turnClockLabel(seconds, match.pace === 'async')
  }
  const [label, setLabel] = useState(labelAt)
  useEffect(() => {
    const update = () => setLabel(current => {
      const next = labelAt()
      return current === next ? current : next
    })
    update()
    if (match.status !== 'active' || resolving || !started) return
    const timer = window.setInterval(update, 250)
    return () => window.clearInterval(timer)
  }, [match.pace, match.status, match.turnEndsAt, match.turnNumber, resolving, started])
  return <span className="turn-timer">{label}</span>
}

function sameNumberRecord(left: Record<string, number>, right: Record<string, number>): boolean {
  const leftKeys = Object.keys(left)
  const rightKeys = Object.keys(right)
  return leftKeys.length === rightKeys.length && leftKeys.every(key => left[key] === right[key])
}

export const StableBoardLetters = memo(function StableBoardLetters({
  cellCount,
  board,
  provisional,
  failed,
  playerId,
  hiddenCell,
  draggedTileId,
}: {
  cellCount: number
  board: MatchState['board']
  provisional: Record<number, Tile>
  failed?: Record<number, string>
  playerId: string
  hiddenCell: number | null
  draggedTileId: string | null
}) {
  return <div className="confirmed-board-layer" aria-hidden="true">
    {Array.from({ length: cellCount }, (_, index) => {
      const confirmed = board[index]
      const pending = provisional[index]
      const failedLetter = failed?.[index]
      if (failedLetter) {
        return <span className="confirmed-board-letter failed-board-letter" key={index}>{failedLetter}</span>
      }
      if (confirmed && hiddenCell !== index) {
        return <span className={`confirmed-board-letter ${confirmed.playerId === playerId ? 'player-effect' : 'opponent-effect'}`} key={index}>{confirmed.letter}</span>
      }
      if (!confirmed && pending && pending.id !== draggedTileId) {
        return <span className="confirmed-board-letter provisional-effect" key={index}>{pending.letter}</span>
      }
      return <span className="confirmed-board-letter-spacer" key={index} />
    })}
  </div>
})

function compactClue(text: string): string {
  const firstIdea = text.split(/[;.(]/, 1)[0].split(/, dont |, qui |, où /i, 1)[0].trim()
  if (firstIdea.length <= 19) return firstIdea
  const words = firstIdea.split(/\s+/)
  let compact = ''
  for (const word of words) {
    if (`${compact} ${word}`.trim().length > 17) break
    compact = `${compact} ${word}`.trim()
  }
  return `${compact || firstIdea.slice(0, 17)}…`
}

function DuelPlayer({ name, score, active, initials, avatarId, frameId, animationId, player, detail }: { name: string; score: number; active: boolean; initials: string; avatarId?: string; frameId?: string; animationId?: string; player?: boolean; detail?: string }) {
  return <div className={`player ${active ? 'active' : ''} ${player ? 'player-you' : ''}`}>{avatarId ? <CosmeticPortrait avatarId={avatarId} frameId={frameId ?? 'cadre-ivoire'} animationId={animationId} alt="" className="game-portrait" /> : <span className="avatar">{initials}</span>}<span><small>{name}</small>{detail ? <em>{detail}</em> : null}<strong className="score-value" key={score}>{score}</strong></span></div>
}

function ResultPanel({ match, playerId, opponentName, onExit, onHome }: { match: MatchState; playerId: string; opponentName: string; onExit: () => void; onHome: () => void }) {
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

export function MultiplayerGameScreen({ matchId, onExit, onHome }: { matchId: string; onExit: () => void; onHome: () => void }) {
  const identity = useRef(loadPlayerIdentity())
  const playerId = identity.current.playerId
  const playerCosmetics = useRef(loadPlayerCosmetics(playerId))
  const [match, setMatch] = useState<MatchState | null>(null)
  const [grid, setGrid] = useState<GeneratedGrid | null>(null)
  const [provisional, setProvisional] = useState<Record<number, Tile>>({})
  const [selected, setSelected] = useState<Tile | null>(null)
  const [drag, setDrag] = useState<{ tile: Tile; origin: 'rack' | number; x: number; y: number } | null>(null)
  const [dropTarget, setDropTarget] = useState<number | null>(null)
  const [status, setStatus] = useState('Connexion à la partie…')
  const [resolving, setResolving] = useState(false)
  const [wrongCells, setWrongCells] = useState<Set<number>>(new Set())
  const [revealedWrong, setRevealedWrong] = useState<Record<number, string>>({})
  const [greenCells, setGreenCells] = useState<Set<number>>(new Set())
  const [orangeCells, setOrangeCells] = useState<Set<number>>(new Set())
  const [autoHintCell, setAutoHintCell] = useState<number | null>(null)
  const [hintFlight, setHintFlight] = useState<HintFlight | null>(null)
  const [hintRequesting, setHintRequesting] = useState(false)
  const [rerollRequesting, setRerollRequesting] = useState(false)
  const [rackRolling, setRackRolling] = useState(false)
  const [scoreEffects, setScoreEffects] = useState<ScoreEffect[]>([])
  const [wordHighlight, setWordHighlight] = useState<BoardWordHighlightState | null>(null)
  const [leaveOpen, setLeaveOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [displayedScores, setDisplayedScores] = useState<Record<string, number>>({})
  const [turnAlert, setTurnAlert] = useState(false)
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [reportOpen, setReportOpen] = useState(false)
  const [expandedClue, setExpandedClue] = useState<ClueEntry | null>(null)
  const seenTurn = useRef<string | null>(null)
  const animationTimer = useRef<number | null>(null)
  const hintFlightTimer = useRef<number | null>(null)
  const hintLandingTimer = useRef<number | null>(null)
  const alive = useRef(true)
  const matchRef = useRef<MatchState | null>(null)
  const provisionalRef = useRef<Record<number, Tile>>({})
  const resolvingRef = useRef(false)
  const submittedTurns = useRef(new Set<number>())
  const submitTurnRef = useRef<(automatic?: boolean) => void>(() => undefined)
  const wasMyTurn = useRef(false)
  const turnAlertTimer = useRef<number | null>(null)
  const rerollTimer = useRef<number | null>(null)
  const opponentNameRef = useRef('Votre adversaire')
  const hintRequestingRef = useRef(false)
  const pollingRef = useRef<AdaptivePollingController | null>(null)
  const realtimeConnectedRef = useRef(false)
  const unchangedPollsRef = useRef(0)
  const syncFailuresRef = useRef(0)
  const loadedGridId = useRef<string | null>(null)

  const assignedToMe = match?.status === 'active' && match.currentPlayerId === playerId
  const turnPhase = useTurnPhase(match)
  const turnHasStarted = turnPhase.started
  const isMyTurn = Boolean(assignedToMe && turnHasStarted && !turnPhase.expired)
  const canAct = Boolean(isMyTurn && !turnAlert)
  const isAsync = match?.pace === 'async'
  const opponent = match?.players.find(player => player.playerId !== playerId)
  const opponentId = match?.playerIds.find(id => id !== playerId) ?? ''
  const opponentName = match?.bot?.displayName ?? opponent?.displayName ?? 'Votre adversaire'
  const { ghostRef, moveGhost, stopGhost } = useDragGhost()
  opponentNameRef.current = opponentName
  const rack = useMemo<Tile[]>(() => createMatchRackTiles(match?.racks[playerId] ?? [], match?.turnNumber ?? 0), [match?.racks, match?.turnNumber, playerId])
  const placedIds = useMemo(() => new Set(Object.values(provisional).map(tile => tile.id)), [provisional])
  const focusedWordCells = useMemo(() => {
    if (!expandedClue || !grid) return new Set<number>()
    const word = grid.words.find(candidate => candidate.id === expandedClue.wordId)
    if (!word) return new Set<number>()
    return new Set(gameWordCellIndexes(grid, word))
  }, [expandedClue, grid])
  const applyMatchState = (next: MatchState) => {
    const current = matchRef.current
    if (current?.id === next.id) {
      const nextUpdatedAt = new Date(next.updatedAt).getTime()
      const currentUpdatedAt = new Date(current.updatedAt).getTime()
      const containsNewBoardCell = Object.keys(next.board).some(cellIndex => !current.board[Number(cellIndex)])
      if (nextUpdatedAt === currentUpdatedAt && !containsNewBoardCell) return
      if (nextUpdatedAt < currentUpdatedAt && !containsNewBoardCell) return
    }
    const freshest = !current || current.id !== next.id || new Date(next.updatedAt).getTime() > new Date(current.updatedAt).getTime() ? next : current
    // Confirmed cells are append-only. Merge both snapshots so a slower poll
    // can never hide a validation that a newer response has already revealed.
    const merged = current?.id === next.id ? { ...freshest, board: { ...current.board, ...next.board } } : freshest
    matchRef.current = merged
    setMatch(merged)
  }

  const showEffect = (effect: Omit<ScoreEffect, 'id'>) => {
    const created = { ...effect, id: `duel-score-${multiplayerEffectSequence++}` }
    setScoreEffects(current => [...current, created])
    window.setTimeout(() => setScoreEffects(current => current.filter(item => item.id !== created.id)), REWARD_EFFECT_LIFETIME_MS)
  }

  const stopAnimationTimer = () => {
    if (animationTimer.current !== null) window.clearTimeout(animationTimer.current)
    animationTimer.current = null
  }

  const updateProvisional = (updater: (current: Record<number, Tile>) => Record<number, Tile>) => {
    setProvisional(current => {
      const next = updater(current)
      // Keep the transport snapshot synchronous with the last pointer/click
      // event. A timeout firing in the same frame must submit that placement.
      provisionalRef.current = next
      return next
    })
  }

  const animateTurn = (turn: MatchTurn, owner: 'player' | 'bot', finalScores: Record<string, number>, revealEndsAt: number | null) => {
    stopAnimationTimer()
    setWrongCells(new Set())
    setRevealedWrong({})
    const steps: Array<{ points: number; run: () => void }> = []
    ;(turn.wrongPlacements ?? []).forEach(placement => steps.push({ points: 0, run: () => {
      setGreenCells(new Set()); setOrangeCells(new Set()); setWordHighlight(null)
      setWrongCells(new Set([placement.cellIndex]))
      setRevealedWrong({ [placement.cellIndex]: placement.letter })
      setStatus(owner === 'player' ? `${placement.letter} n’est pas ici` : `${opponentNameRef.current} essaie ${placement.letter}`)
      haptic([35, 45, 35])
      playEffect('error')
    }}))
    turn.correct.forEach(cellIndex => steps.push({ points: cellIndex === turn.aidedCell ? 0 : 1, run: () => {
      setWrongCells(new Set()); setRevealedWrong({}); setWordHighlight(null)
      if (owner === 'player') setGreenCells(new Set([cellIndex])); else setOrangeCells(new Set([cellIndex]))
      const points = cellIndex === turn.aidedCell ? 0 : 1
      showEffect({ kind: 'letter', label: `+${points}`, owner, cellIndex })
      playEffect('score')
      haptic(10)
      setStatus(owner === 'player' ? `Lettre correcte · +${points}` : `${opponentNameRef.current} marque +${points}`)
    }}))
    turn.wordBonuses.forEach(bonus => steps.push({ points: bonus.points, run: () => {
      setGreenCells(new Set()); setOrangeCells(new Set()); setWrongCells(new Set()); setRevealedWrong({})
      setWordHighlight({ cells: new Set(bonus.cells), owner, direction: bonus.direction })
      const cellIndex = bonus.direction === 'across' ? bonus.cells[bonus.cells.length - 1] : bonus.cells[Math.floor(bonus.cells.length / 2)]
      showEffect({ kind: 'word', label: `+${bonus.points}`, owner, cellIndex })
      playEffect('word')
      haptic([14, 28, 14])
      setStatus(`Mot terminé · +${bonus.points}`)
    }}))
    if (turn.rackBonus) steps.push({ points: turn.rackBonus, run: () => {
      const cellIndex = turn.correct[Math.floor(turn.correct.length / 2)] ?? 0
      showEffect({ kind: 'word', label: `+${turn.rackBonus}`, owner, cellIndex })
      playEffect('word')
      setStatus(`Chevalet complet · +${turn.rackBonus}`)
    }})
    const revealRemaining = revealEndsAt === null ? steps.length * REWARD_STEP_MS + 350 : revealEndsAt - Date.now()
    const finishAnimation = () => {
      setGreenCells(new Set()); setOrangeCells(new Set()); setWrongCells(new Set()); setWordHighlight(null)
      setRevealedWrong({}); provisionalRef.current = {}; setProvisional({})
      setDisplayedScores(finalScores)
      resolvingRef.current = false; setResolving(false)
      const latest = matchRef.current
      setStatus(latest?.status === 'finished' ? 'Partie terminée' : latest?.currentPlayerId === playerId ? 'À vous de jouer' : `Au tour de ${opponentNameRef.current}`)
      animationTimer.current = null
    }
    // If this result reached a phone late (background tab or weak network), do
    // not replay an old reveal over the already-running 45-second turn.
    if (steps.length && revealEndsAt !== null && revealRemaining <= 180) {
      finishAnimation()
      return
    }
    resolvingRef.current = steps.length > 0
    setResolving(steps.length > 0)
    setDisplayedScores(steps.length ? { ...finalScores, [turn.playerId]: Math.max(0, (finalScores[turn.playerId] ?? 0) - turn.scoreGained) } : finalScores)
    const stepDelay = steps.length
      ? Math.min(REWARD_STEP_MS, Math.max(180, Math.floor((Math.max(220, revealRemaining) - 120) / steps.length)))
      : 0
    const play = (index: number) => {
      const step = steps[index]
      if (!step) {
        finishAnimation()
        return
      }
      step.run()
      if (step.points) setDisplayedScores(current => ({ ...current, [turn.playerId]: (current[turn.playerId] ?? 0) + step.points }))
      animationTimer.current = window.setTimeout(() => play(index + 1), stepDelay)
    }
    if (steps.length) play(0)
    else {
      provisionalRef.current = {}; setProvisional({}); setDisplayedScores(finalScores)
      resolvingRef.current = false; setResolving(false)
      setStatus(turn.kind === 'timeout'
        ? owner === 'player' ? `Temps écoulé · ${turn.inactivityCount}/3` : `${opponentNameRef.current} n’a pas joué · ${turn.inactivityCount}/3`
        : owner === 'player' ? 'Tour passé' : `${opponentNameRef.current} passe`)
    }
  }

  useEffect(() => {
    alive.current = true
    window.scrollTo(0, 0)
    const sync = async () => {
      try {
        const next = await loadMatch(playerId, matchId, matchRef.current?.updatedAt)
        if (!next) {
          unchangedPollsRef.current += 1
          syncFailuresRef.current = 0
          return
        }
        if (!alive.current) return
        unchangedPollsRef.current = 0
        syncFailuresRef.current = 0
        applyMatchState(next)
        if (loadedGridId.current !== next.gridId) {
          // Online matches receive a sanitized board from the authoritative server:
          // clues and word geometry are present, answers and cell solutions are not.
          if (!next.grid) throw new Error('Le serveur n’a pas transmis la grille publique de cette partie.')
          const generated = next.grid
          if (!alive.current) return
          loadedGridId.current = next.gridId
          setGrid(generated)
        }
        setError(null)
        if (next.lastTurn && next.lastTurn.id !== seenTurn.current) {
          seenTurn.current = next.lastTurn.id
          animateTurn(next.lastTurn, next.lastTurn.playerId === playerId ? 'player' : 'bot', next.scores, next.status === 'active' ? new Date(next.turnStartedAt).getTime() : null)
        } else if (!resolvingRef.current) {
          setDisplayedScores(current => sameNumberRecord(current, next.scores) ? current : next.scores)
        }
      } catch (reason) {
        syncFailuresRef.current += 1
        if (alive.current) setError(reason instanceof Error ? reason.message : 'Connexion interrompue')
      }
    }
    const polling = startAdaptivePolling({
      task: sync,
      delay: visibility => matchPollDelay({
        match: matchRef.current,
        playerId,
        visibility,
        realtimeConnected: realtimeConnectedRef.current,
        unchangedPolls: unchangedPollsRef.current,
        failureCount: syncFailuresRef.current,
      }),
    })
    pollingRef.current = polling
    const unsubscribeRealtime = subscribeToMatchUpdates(matchId, updatedAt => {
      const knownUpdatedAt = matchRef.current?.updatedAt
      if (!updatedAt || !knownUpdatedAt || new Date(updatedAt).getTime() > new Date(knownUpdatedAt).getTime()) polling.wake()
    }, status => {
      realtimeConnectedRef.current = status === 'connected'
      if (status === 'connected') polling.wake()
    })
    return () => {
      alive.current = false
      pollingRef.current = null
      unsubscribeRealtime(); polling.stop(); stopAnimationTimer()
      if (hintFlightTimer.current !== null) window.clearTimeout(hintFlightTimer.current)
      if (hintLandingTimer.current !== null) window.clearTimeout(hintLandingTimer.current)
      if (turnAlertTimer.current !== null) window.clearTimeout(turnAlertTimer.current)
      if (rerollTimer.current !== null) window.clearTimeout(rerollTimer.current)
    }
    // The match identity is fixed for the lifetime of this screen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchId, playerId])

  useEffect(() => { provisionalRef.current = provisional }, [provisional])
  useEffect(() => { resolvingRef.current = resolving }, [resolving])
  useEffect(() => { hintRequestingRef.current = hintRequesting }, [hintRequesting])
  useEffect(() => {
    const heartbeat = () => void setSocialPresence(playerId, 'playing').catch(() => undefined)
    heartbeat()
    const interval = window.setInterval(heartbeat, 10_000)
    return () => { window.clearInterval(interval); void setSocialPresence(playerId, 'online').catch(() => undefined) }
  }, [playerId])

  useEffect(() => {
    if (isMyTurn && !wasMyTurn.current) {
      setTurnAlert(true)
      haptic([140, 80, 140])
      playEffect('turn')
      document.title = 'À vous de jouer · MotMan'
      if (turnAlertTimer.current !== null) window.clearTimeout(turnAlertTimer.current)
      turnAlertTimer.current = window.setTimeout(() => { setTurnAlert(false); turnAlertTimer.current = null }, TURN_READY_DURATION_MS)
    } else if (!isMyTurn && match?.status === 'active') document.title = `Tour de ${opponentName} · MotMan`
    wasMyTurn.current = isMyTurn
  }, [isMyTurn, match?.status, opponentName])

  useEffect(() => {
    if (assignedToMe && turnHasStarted && turnPhase.expired && match && !submittedTurns.current.has(match.turnNumber)) {
      submitTurnRef.current(true)
    }
  }, [assignedToMe, match, turnHasStarted, turnPhase.expired])

  useEffect(() => {
    if (!match || resolving) return
    setStatus(match.status === 'finished' ? 'Partie terminée' : isMyTurn ? 'À vous de jouer' : `Au tour de ${opponentName}`)
  }, [isMyTurn, match?.status, match?.turnNumber, opponentName, resolving])

  const placeTile = (tile: Tile, cellIndex: number, origin: 'rack' | number = 'rack') => {
    if (!canAct || resolving || !grid || match?.board[cellIndex] || grid.cells[cellIndex].kind !== 'letter') return
    updateProvisional(current => {
      const next = { ...current }
      Object.entries(next).forEach(([index, item]) => { if (item.id === tile.id) delete next[Number(index)] })
      const displaced = next[cellIndex]
      next[cellIndex] = tile
      if (displaced && typeof origin === 'number' && origin !== cellIndex) next[origin] = displaced
      return next
    })
    setSelected(null); setStatus('À valider'); haptic(10); playEffect('place')
  }

  const returnTile = (cellIndex: number) => {
    updateProvisional(current => { const next = { ...current }; delete next[cellIndex]; return next })
    setStatus('Lettre reprise')
  }

  const pointerDown = (event: React.PointerEvent, tile: Tile, origin: 'rack' | number) => {
    if (!canAct || resolving) return
    event.currentTarget.setPointerCapture(event.pointerId)
    setDrag({ tile, origin, x: event.clientX, y: event.clientY })
    moveGhost(event.clientX, event.clientY)
  }
  const pointerMove = (event: React.PointerEvent) => {
    if (!drag) return
    moveGhost(event.clientX, event.clientY)
    const cell = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-cell]')
    const rackTarget = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-rack]')
    const nextTarget = cell?.dataset.cell ? Number(cell.dataset.cell) : rackTarget ? -1 : null
    setDropTarget(current => current === nextTarget ? current : nextTarget)
  }
  const pointerUp = (event: React.PointerEvent) => {
    if (drag) {
      const cell = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-cell]')
      const rackTarget = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-rack]')
      if (cell?.dataset.cell) placeTile(drag.tile, Number(cell.dataset.cell), drag.origin)
      else if (rackTarget && typeof drag.origin === 'number') returnTile(drag.origin)
    }
    stopGhost(); setDrag(null); setDropTarget(null)
  }
  const pointerCancel = () => { stopGhost(); setDrag(null); setDropTarget(null) }

  const validate = async (automatic = false) => {
    const currentMatch = matchRef.current
    if (!currentMatch || currentMatch.status !== 'active' || currentMatch.currentPlayerId !== playerId || resolvingRef.current) return
    if (!automatic && (!canAct || Date.now() >= new Date(currentMatch.turnEndsAt).getTime())) return
    if (submittedTurns.current.has(currentMatch.turnNumber)) return
    submittedTurns.current.add(currentMatch.turnNumber)
    resolvingRef.current = true; setResolving(true); setError(null); setStatus(automatic ? 'Temps écoulé · validation…' : 'Validation…')
    try {
      const response = await playMatchTurn(playerId, currentMatch.id, currentMatch.turnNumber, Object.entries(provisionalRef.current).map(([cellIndex, tile]) => ({ cellIndex: Number(cellIndex), letter: tile.letter })), automatic)
      applyMatchState(response.match)
      if (seenTurn.current !== response.result.id) {
        seenTurn.current = response.result.id
        animateTurn(response.result, 'player', response.match.scores, response.match.status === 'active' ? new Date(response.match.turnStartedAt).getTime() : null)
      }
    } catch (reason) {
      const payload = (reason as { payload?: { match?: MatchState } })?.payload
      if (payload?.match) applyMatchState(payload.match)
      // A lost response must not permanently lock the local turn. Retrying is
      // safe because the server returns the already-recorded result by turn id.
      submittedTurns.current.delete(currentMatch.turnNumber)
      resolvingRef.current = false; setResolving(false)
      setError(reason instanceof Error ? reason.message : 'Validation impossible')
    }
  }
  submitTurnRef.current = automatic => { void validate(Boolean(automatic)) }

  const requestHint = async () => {
    if (!match || !canAct || resolving || hintRequestingRef.current) return
    const sourceRects = new Map<string, DOMRect>()
    rack.forEach(tile => {
      const provisionalOrigin = Object.entries(provisionalRef.current).find(([, placed]) => placed.letter === tile.letter)?.[0]
      const source = provisionalOrigin
        ? document.querySelector<HTMLElement>(`[data-cell="${provisionalOrigin}"] .letter-only`)
        : document.querySelector<HTMLElement>(`[data-rack-letter="${tile.letter}"]`)
      const rect = source?.getBoundingClientRect()
      if (rect) sourceRects.set(tile.letter, rect)
    })
    hintRequestingRef.current = true
    setHintRequesting(true)
    try {
      const next = await requestMatchHint(playerId, match.id)
      const placedHint = next.hint
      if (placedHint) {
        const target = document.querySelector<HTMLElement>(`[data-cell="${placedHint.cellIndex}"]`)
        const sourceRect = sourceRects.get(placedHint.letter)
        const targetRect = target?.getBoundingClientRect()
        applyMatchState(next)
        updateProvisional(current => Object.fromEntries(Object.entries(current).filter(([cellIndex, tile]) => Number(cellIndex) !== placedHint.cellIndex && tile.letter !== placedHint.letter)))
        setSelected(null)
        if (sourceRect && targetRect) {
          const fromX = sourceRect.left + sourceRect.width / 2
          const fromY = sourceRect.top + sourceRect.height / 2
          const toX = targetRect.left + targetRect.width / 2
          const toY = targetRect.top + targetRect.height / 2
          setHintFlight({ letter: placedHint.letter, cellIndex: placedHint.cellIndex, fromX, fromY, deltaX: toX - fromX, deltaY: toY - fromY })
          setStatus('Indice en route…')
        } else setAutoHintCell(placedHint.cellIndex)
        hintRequestingRef.current = false
        setHintRequesting(false)
        if (hintFlightTimer.current !== null) window.clearTimeout(hintFlightTimer.current)
        if (hintLandingTimer.current !== null) window.clearTimeout(hintLandingTimer.current)
        hintFlightTimer.current = window.setTimeout(() => {
          setHintFlight(null)
          setAutoHintCell(placedHint.cellIndex)
          showEffect({ kind: 'letter', label: '+0', owner: 'player', cellIndex: placedHint.cellIndex })
          setStatus('Indice placé · +0')
          haptic([15, 35, 15])
          playEffect('place')
          hintFlightTimer.current = null
          hintLandingTimer.current = window.setTimeout(() => {
            setAutoHintCell(current => current === placedHint.cellIndex ? null : current)
            hintLandingTimer.current = null
          }, 1050)
        }, sourceRect && targetRect ? 720 : 40)
      } else { applyMatchState(next); hintRequestingRef.current = false; setHintRequesting(false) }
    }
    catch (reason) {
      hintRequestingRef.current = false
      setHintRequesting(false)
      setError(reason instanceof Error ? reason.message : 'Indice indisponible')
    }
  }

  const rerollRack = async () => {
    const currentMatch = matchRef.current
    if (!currentMatch || !canAct || resolving || rerollRequesting) return
    const rerollAllowed = canUseReroll({
      alreadyUsed: Boolean(currentMatch.rerollUsed?.[playerId]),
      pendingPlacements: Object.keys(provisionalRef.current).length,
      hintActive: currentMatch.hint?.playerId === playerId && currentMatch.hint.turnNumber === currentMatch.turnNumber,
    })
    if (!rerollAllowed) return
    setRerollRequesting(true)
    setError(null)
    try {
      const next = await rerollMatchRack(playerId, currentMatch.id)
      applyMatchState(next)
      setSelected(null)
      setRackRolling(true)
      setStatus('Nouvelles lettres')
      haptic([12, 24, 12])
      playEffect('reroll')
      if (rerollTimer.current !== null) window.clearTimeout(rerollTimer.current)
      rerollTimer.current = window.setTimeout(() => { setRackRolling(false); rerollTimer.current = null }, 620)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Relance indisponible')
    } finally { setRerollRequesting(false) }
  }

  const leave = async () => {
    if (match?.status === 'active') {
      try { applyMatchState(await forfeitMatch(playerId, match.id)) } catch { /* Le serveur appliquera aussi le délai si la connexion est perdue. */ }
    }
    onExit()
  }

  if (!match || !grid) return <main className="app-shell duel-loading"><Wifi /><h2>Connexion à la partie…</h2>{error ? <p>{error}</p> : null}</main>

  const hint = match.hint?.playerId === playerId && match.hint.turnNumber === match.turnNumber ? match.hint : null
  const hintUsedInMatch = Boolean(match.hintUsed?.[playerId])
  const rerollUsedInMatch = Boolean(match.rerollUsed?.[playerId])
  const myScore = displayedScores[playerId] ?? match.scores[playerId] ?? 0
  const opponentScore = displayedScores[opponentId] ?? match.scores[opponentId] ?? 0
  const myInactivity = match.inactivity[playerId] ?? 0
  const opponentInactivity = match.inactivity[opponentId] ?? 0
  const hiddenStableLetterCell = hintFlight?.cellIndex ?? (hintRequesting && match.hint?.playerId === playerId ? match.hint.cellIndex : null)

  return <main className={`app-shell multiplayer-shell ${turnAlert ? 'turn-alerting' : ''} ${resolving ? 'is-resolving' : ''} ${match.status === 'finished' ? 'is-finished' : ''}`}>
    <header><button type="button" aria-label={match.status === 'active' ? 'Options de sortie' : 'Retour aux parties'} onClick={() => match.status === 'active' ? setLeaveOpen(true) : onExit()}><ArrowLeft /></button><img className="game-brand-logo" src={assetUrl('/assets/motman-logo-v2.webp')} alt="MotMan" /><button type="button" aria-label="Paramètres" onClick={() => setOptionsOpen(true)}><Settings /></button></header>
    {match.status === 'active' ? <><section className="scoreboard"><DuelPlayer name={opponentName} detail={match.bot ? `Niv. ${match.bot.level}` : undefined} score={opponentScore} initials={playerInitials(opponentName)} avatarId={match.bot?.avatarId ?? opponent?.avatarId} frameId={match.bot?.frameId ?? opponent?.frameId} animationId={opponent?.animationId} active={turnHasStarted && !assignedToMe} /><div className={`turn ${turnPhase.urgent && isMyTurn ? 'urgent' : ''} ${isAsync ? 'async-turn' : ''} ${turnAlert ? 'your-turn-pulse' : ''}`} aria-live="polite"><small>{resolving || !turnHasStarted ? 'Résultats' : isMyTurn ? 'Votre tour' : `Tour de ${opponentName}`}</small><TurnTimer match={match} resolving={resolving} started={turnHasStarted} /><strong>{status}</strong></div><DuelPlayer name="Vous" score={myScore} initials={playerInitials(identity.current.displayName)} avatarId={playerCosmetics.current.equippedAvatarId} frameId={playerCosmetics.current.equippedFrameId} animationId={playerCosmetics.current.equippedAnimationId} active={Boolean(isMyTurn)} player /></section>
    <p className="instruction duel-instruction"><span>{match.mode === 'solo' ? 'Solo' : match.mode === 'normal' ? 'Normal' : 'Duel ami'}{match.bot ? ` · Bot ${DIFFICULTY_LABELS[match.difficulty].toLowerCase()}` : ''} · {isAsync ? '24 h par tour' : '45 s par tour'}</span><span className={`duel-live ${isAsync ? 'async' : ''}`} aria-label={isAsync ? 'Partie en temps illimité' : 'Partie en temps limité'}>{isAsync ? <Hourglass /> : <i />}{isAsync ? 'ILLIMITÉ' : 'LIMITÉ'}</span></p>
    {myInactivity || opponentInactivity ? <div className="duel-inactivity" aria-label="Avertissements d’inactivité">
      {opponentInactivity ? <span><b>{opponentName}</b> {opponentInactivity}/3</span> : null}
      {myInactivity ? <span className="mine"><b>Vous</b> {myInactivity}/3</span> : null}
    </div> : null}</> : null}
    {error ? <p className="duel-error" role="alert">{error}</p> : null}
    {match.status === 'active' ? <section className="board-wrap" aria-label="Grille multijoueur" data-bot-level={match.bot ? match.difficulty : undefined}><div className={`board ${focusedWordCells.size ? 'has-clue-focus' : ''}`} style={{ '--board-columns': grid.columns, '--board-rows': grid.rows, '--board-aspect': `${grid.columns} / ${grid.rows}` } as CSSProperties}>
      {grid.cells.map((cell, index) => {
        if (cell.kind === 'block') return <div className="cell block corner-block" key={index} aria-label="Case centrale des définitions" />
        if (cell.kind === 'clue') {
          const entries = [...cell.entries].sort((left, right) => Number(left.direction === 'down') - Number(right.direction === 'down'))
          const row = Math.floor(index / grid.columns)
          const column = index % grid.columns
          return <div className={`cell clue clue-tone-${(row + column) % 4} ${entries.length > 1 ? 'double-clue' : ''} ${entries.length ? '' : 'corner-clue'}`} key={index}>{entries.map(entry => <button type="button" className={`clue-entry ${entry.image ? 'image-entry' : ''}`} key={entry.wordId} aria-label={`Agrandir la définition ${entry.text || entry.image?.alt || ''}`} onClick={() => setExpandedClue(entry)}>{entry.image ? <img className="clue-image" src={assetUrl(entry.image.asset)} alt={entry.image.alt} /> : compactClue(entry.text)}<b aria-hidden="true">{entry.direction === 'across' ? '→' : '↓'}</b></button>)}</div>
        }
        const confirmed = match.board[index]
        const localTile = provisional[index]
        const failedLetter = revealedWrong[index]
        const confirmedHintHidden = Boolean(confirmed && (hintFlight?.cellIndex === index || hintRequesting && match.hint?.playerId === playerId && match.hint.cellIndex === index))
        const letter = confirmed && !confirmedHintHidden ? confirmed.letter : !failedLetter && !confirmed ? localTile?.letter : undefined
        const wordRewardClass = wordHighlight?.cells.has(index) ? `word-reward-cell word-reward-cell--${wordHighlight.owner}` : ''
        const ownershipClass = confirmed ? confirmed.playerId === playerId ? 'confirmed-player' : 'confirmed-opponent' : ''
        return <button type="button" key={index} data-cell={index} data-confirmed={confirmed ? 'true' : 'false'} aria-disabled={Boolean(confirmed || (!canAct && !localTile))} tabIndex={confirmed ? -1 : canAct || localTile ? 0 : -1} aria-label={`Case ${index + 1}${confirmed ? ` · ${confirmed.letter} validée` : ''}`} className={`cell slot ${ownershipClass} ${wordRewardClass} ${focusedWordCells.has(index) ? 'clue-focus' : ''} ${hintFlight?.cellIndex === index ? 'hint-awaiting' : ''} ${autoHintCell === index ? 'hint-auto-placed' : ''} ${dropTarget === index ? 'drop-target' : ''} ${greenCells.has(index) ? 'correct' : ''} ${orangeCells.has(index) ? 'bot-play' : ''} ${wrongCells.has(index) ? 'wrong' : ''}`} onClick={() => confirmed ? undefined : localTile ? returnTile(index) : selected && placeTile(selected, index)}>
          {letter ? <span className={`letter-only ${confirmed ? 'locked confirmed-letter' : localTile && !failedLetter ? 'stable-provisional-letter' : ''} ${confirmed?.playerId === playerId ? 'owned-by-player' : confirmed ? 'owned-by-opponent' : ''} ${failedLetter ? 'failed-reveal-letter' : ''} ${drag?.tile.id === localTile?.id ? 'drag-source' : ''}`} onPointerDown={event => localTile && !confirmed && !failedLetter && pointerDown(event, localTile, index)} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={pointerCancel}>{letter}</span> : null}
        </button>
      })}
      <StableBoardLetters cellCount={grid.cells.length} board={match.board} provisional={provisional} failed={revealedWrong} playerId={playerId} hiddenCell={hiddenStableLetterCell} draggedTileId={drag?.tile.id ?? null} />
      <BoardWordHighlight highlight={wordHighlight} columns={grid.columns} rows={grid.rows} />
      <BoardScoreEffects effects={scoreEffects} columns={grid.columns} rows={grid.rows} />
    </div></section> : null}
    {match.status === 'active' ? <>
      <section className={`rack-area ${!isMyTurn ? 'duel-rack-waiting' : ''}`}><div className="rack-heading"><strong>{isMyTurn ? 'Vos lettres' : `${opponentName} joue…`}</strong><span>{isMyTurn ? `${rack.length - placedIds.size} disponible${rack.length - placedIds.size > 1 ? 's' : ''}` : 'Préparez votre prochain coup'}</span></div><div className={`rack ${dropTarget === -1 ? 'rack-drop' : ''} ${rackRolling ? 'is-rerolling' : ''}`} data-rack="true" aria-label="Lettres disponibles">
        {rack.map(tile => <div className="rack-slot" key={tile.id}>{!placedIds.has(tile.id) ? <button type="button" data-rack-letter={tile.letter} data-rack-id={tile.id} disabled={!canAct || resolving} aria-label={`Lettre ${tile.letter}`} className={`rack-letter ${selected?.id === tile.id ? 'selected' : ''} ${drag?.tile.id === tile.id ? 'drag-source' : ''}`} onClick={() => setSelected(current => current?.id === tile.id ? null : tile)} onPointerDown={event => pointerDown(event, tile, 'rack')} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={pointerCancel}>{tile.letter}</button> : null}</div>)}
        {Array.from({ length: Math.max(0, 5 - rack.length) }, (_, index) => <div className="rack-slot" aria-hidden="true" key={`empty-${index}`} />)}
        <button className="reroll-button" type="button" onClick={() => void rerollRack()} disabled={!canAct || resolving || rerollRequesting || rerollUsedInMatch || Object.keys(provisional).length > 0} aria-label={rerollUsedInMatch ? 'Relance déjà utilisée pendant cette partie' : 'Relancer les lettres'} title={rerollUsedInMatch ? 'Relance déjà utilisée' : 'Relancer les lettres'}><Shuffle /></button>
      </div></section>
      <div className="turn-actions"><button className="hint-button" type="button" onClick={requestHint} disabled={!canAct || resolving || hintRequesting || hintUsedInMatch} title={hintUsedInMatch ? 'Indice déjà utilisé pendant cette partie' : 'Utiliser un indice'}><Lightbulb />Indice</button><button className="validate" type="button" onClick={() => void validate(false)} disabled={!canAct || resolving}><Check />{isMyTurn ? resolving ? 'Résultats…' : 'Valider' : `Tour de ${opponentName}`}</button></div>
    </> : <ResultPanel match={match} playerId={playerId} opponentName={opponentName} onExit={onExit} onHome={onHome} />}
    {drag ? <div ref={ghostRef} className="drag-ghost" style={{ left: drag.x, top: drag.y }}>{drag.tile.letter}</div> : null}
    {hintFlight ? <span className="hint-flight" style={{ left: hintFlight.fromX, top: hintFlight.fromY, '--hint-dx': `${hintFlight.deltaX}px`, '--hint-dy': `${hintFlight.deltaY}px`, '--hint-mid-x': `${hintFlight.deltaX * .7}px`, '--hint-mid-y': `${hintFlight.deltaY * .7 - 10}px` } as CSSProperties}>{hintFlight.letter}</span> : null}
    {turnAlert ? <div className="turn-ready-flash" role="status"><span>À vous !</span></div> : null}
    {expandedClue ? <ClueZoom entry={expandedClue} onClose={() => setExpandedClue(null)} /> : null}
    {leaveOpen ? <LeaveMatchPanel opponentName={opponentName} isAsync={Boolean(isAsync)} cancel={() => setLeaveOpen(false)} continueLater={onExit} leave={() => void leave()} /> : null}
    {optionsOpen ? <GameOptionsOverlay close={() => setOptionsOpen(false)} report={match.bot ? undefined : () => setReportOpen(true)} /> : null}
    {reportOpen && !match.bot ? <ReportPlayerOverlay playerName={opponentName} close={() => setReportOpen(false)} submit={(reason, details) => reportPlayer(opponentId, reason, details, match.id)} /> : null}
  </main>
}
