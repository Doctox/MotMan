import { useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { ArrowLeft, Check, Feather, Heart, HeartCrack, House, Lightbulb, LoaderCircle, Pause, Settings, Shuffle } from 'lucide-react'
import { assetUrl } from './assetUrl'
import { generateGrid, type ClueEntry, type GeneratedGrid, type GridDifficulty } from './generator'
import { GameOptionsOverlay, PauseOverlay } from './GameOverlays'
import { loadPlayerIdentity, playerInitials } from './playerIdentity'
import { setSocialPresence } from './social'
import { BoardScoreEffects } from './BoardScoreEffects'
import { BoardWordHighlight, type BoardWordHighlightState } from './BoardWordHighlight'
import { awardExperience, type ExperienceAward } from './playerProgress'
import { GameResultScreen } from './GameResultScreen'
import { botThinkingDelayMs, createBotPersona, planBotMove, refillBotRack, type BotSkill } from './botOpponents'
import { canUseReroll, evaluateTurn, gameWordCellIndexes, hintCandidates, replenishUniqueRack, REWARD_EFFECT_LIFETIME_MS, REWARD_STEP_MS } from './gameRules'
import { ClueZoom } from './ClueZoom'
import { haptic, playEffect } from './sensoryPreferences'
import { useDragGhost } from './useDragGhost'
import { loadPlayerCosmetics } from './cosmetics'
import { CosmeticPortrait } from './CosmeticPortrait'

import './styles.css'

type Tile = { id: string; letter: string }
type BoardTile = { tile: Tile; status: 'provisional' | 'confirmed' | 'wrong'; owner: 'player' | 'bot' }
type ScoreEffect = { id: string; kind: 'letter' | 'word'; label: string; owner: 'player' | 'bot'; cellIndex: number }
type HintFlight = { tileId: string; letter: string; cellIndex: number; fromX: number; fromY: number; deltaX: number; deltaY: number }
type SoloPace = 'realtime' | 'async'
type SoloFeedback = 'yes' | 'no' | 'sent' | null
let tileSequence = 0
let effectSequence = 0
const makeTile = (letter: string): Tile => ({ id: `tile-${Date.now()}-${tileSequence++}`, letter })
const makeSoloAwardId = () => `solo:${Date.now()}:${Math.random().toString(36).slice(2)}`
const SOLO_BOT_SKILLS: Record<GridDifficulty, BotSkill> = { easy: 'beginner', normal: 'regular', hard: 'expert' }
const makeSoloOpponent = (difficulty: GridDifficulty) => createBotPersona(`${Date.now()}:${Math.random()}`, SOLO_BOT_SKILLS[difficulty])
const TURN_READY_DURATION_MS = 1_800
const SOLO_GRID_HISTORY_KEY = 'motman-recent-solo-grids-v4'
const SOLO_GRID_HISTORY_LIMIT = 12

function loadRecentSoloGridIds(): string[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(SOLO_GRID_HISTORY_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string').slice(0, SOLO_GRID_HISTORY_LIMIT) : []
  } catch { return [] }
}

function rememberSoloGrid(gridId: string): void {
  const recent = loadRecentSoloGridIds().filter(id => id !== gridId)
  localStorage.setItem(SOLO_GRID_HISTORY_KEY, JSON.stringify([gridId, ...recent].slice(0, SOLO_GRID_HISTORY_LIMIT)))
}

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

function drawTiles(grid: GeneratedGrid, locked: Record<number, string>, count: number): Tile[] {
  const neededLetters = grid.cells.flatMap((cell, index) => cell.kind === 'letter' && !locked[index] ? [cell.solution] : [])
  return replenishUniqueRack({ neededLetters, currentLetters: [], count }).map(makeTile)
}

function reconcileRack(grid: GeneratedGrid, locked: Record<number, string>, current: Tile[], count = 5, avoidLetters: Iterable<string> = []): Tile[] {
  const neededLetters = grid.cells.flatMap((cell, index) => cell.kind === 'letter' && !locked[index] ? [cell.solution] : [])
  const letters = replenishUniqueRack({ neededLetters, currentLetters: current.map(tile => tile.letter), avoidLetters, count })
  return letters.map(letter => current.find(tile => tile.letter === letter) ?? makeTile(letter))
}

function wordCellIndexes(grid: GeneratedGrid, word: GeneratedGrid['words'][number]): number[] {
  return gameWordCellIndexes(grid, word)
}

function Player({ name, score, active, initials, avatarId, frameId, animationId, player, detail }: { name: string; score: number; active?: boolean; initials: string; avatarId?: string; frameId?: string; animationId?: string; player?: boolean; detail?: string }) {
  return <div className={`player ${active ? 'active' : ''} ${player ? 'player-you' : ''}`}>{avatarId ? <CosmeticPortrait avatarId={avatarId} frameId={frameId ?? 'cadre-ivoire'} animationId={animationId} alt="" className="game-portrait" /> : <span className="avatar">{initials}</span>}<span><small>{name}</small>{detail ? <em>{detail}</em> : null}<strong className="score-value" key={score}>{score}</strong></span></div>
}

function SoloResultPanel({ award, playerScore, opponentScore, opponentName, feedback, replay, home, setNegativeFeedback, sendFeedback }: {
  award: ExperienceAward | null
  playerScore: number
  opponentScore: number
  opponentName: string
  feedback: SoloFeedback
  replay: () => Promise<void>
  home: () => void
  setNegativeFeedback: () => void
  sendFeedback: (quality: 'yes' | 'no', reason?: string) => void
}) {
  const [restarting, setRestarting] = useState(false)
  const replayGame = async () => {
    if (restarting) return
    setRestarting(true)
    try { await replay() }
    finally { setRestarting(false) }
  }

  const outcome = playerScore === opponentScore ? 'draw' : playerScore > opponentScore ? 'win' : 'loss'
  const title = outcome === 'win' ? 'Victoire !' : outcome === 'draw' ? 'Égalité !' : 'Partie terminée'
  const detail = outcome === 'win' ? 'Bravo, vous avez trouvé les bons mots.' : outcome === 'draw' ? 'Vous terminez avec le même score.' : `${opponentName} remporte cette grille.`
  return <GameResultScreen outcome={outcome} title={title} detail={detail} playerScore={playerScore} opponentScore={opponentScore} opponentName={opponentName} award={award}>
    <div className="result-feedback">
      {feedback === 'sent' ? <p>Merci, votre retour améliorera les prochaines grilles.</p> : <>
        <p>Cette grille était-elle agréable ?</p>
        <div className="feedback-actions"><button type="button" onClick={() => sendFeedback('yes')}><Heart />Oui</button><button type="button" onClick={setNegativeFeedback}><HeartCrack />Non</button></div>
        {feedback === 'no' ? <div className="reasons">{['Trop facile','Trop difficile','Définitions ambiguës','Mots trop rares','Grille peu agréable'].map(reason => <button type="button" key={reason} onClick={() => sendFeedback('no', reason)}>{reason}</button>)}</div> : null}
      </>}
    </div>
    <div className="end-game-actions">
      <button type="button" className="new-game" onClick={() => void replayGame()} disabled={restarting}><Feather />{restarting ? 'Préparation…' : 'Nouvelle partie'}</button>
      <button type="button" className="end-game-home" onClick={home}><House />Retour à l’accueil</button>
    </div>
  </GameResultScreen>
}

const DIFFICULTY_LABELS: Record<GridDifficulty, string> = {
  easy: 'Facile',
  normal: 'Normal',
  hard: 'Difficile',
}

function SoloGameLoader({ difficulty, pace, onExit, onHome }: { difficulty: GridDifficulty; pace: SoloPace; onExit: () => void; onHome: () => void }) {
  const [attempt, setAttempt] = useState(0)
  const [grid, setGrid] = useState<GeneratedGrid | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setGrid(null)
    setError(null)
    void generateGrid(Date.now(), difficulty, loadRecentSoloGridIds()).then(generated => {
      if (active) setGrid(generated)
    }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : 'La grille ne peut pas être chargée.')
    })
    return () => { active = false }
  }, [attempt, difficulty])

  if (grid) return <GameScreen difficulty={difficulty} pace={pace} initialGrid={grid} onExit={onExit} onHome={onHome} />
  return <main className="app-shell"><div className="duel-loading"><LoaderCircle /><h2>{error ? 'Chargement interrompu' : 'Préparation de la grille…'}</h2><p>{error ?? 'Quelques lettres se mettent en place.'}</p>{error ? <><button type="button" className="new-game" onClick={() => setAttempt(current => current + 1)}>Réessayer</button><button type="button" className="hint-button" onClick={onExit}>Retour</button></> : null}</div></main>
}

function GameScreen({ difficulty, pace, initialGrid, onExit, onHome }: { difficulty: GridDifficulty; pace: SoloPace; initialGrid: GeneratedGrid; onExit: () => void; onHome: () => void }) {
  const turnDuration = pace === 'async' ? 86_400 : 45
  const [grid, setGrid] = useState(initialGrid)
  const [opponent, setOpponent] = useState(() => makeSoloOpponent(difficulty))
  const [boardTiles, setBoardTiles] = useState<Record<number, BoardTile>>({})
  const [rack, setRack] = useState<Tile[]>(() => drawTiles(grid, {}, 5))
  const [botRack, setBotRack] = useState<string[]>(() => refillBotRack({ grid, occupiedCells: [], currentLetters: [], seed: `solo:${grid.id}:bot` }))
  const [selected, setSelected] = useState<Tile | null>(null)
  const [drag, setDrag] = useState<{ tile: Tile; origin: 'rack' | number; x: number; y: number } | null>(null)
  const [dropTarget, setDropTarget] = useState<number | null>(null)
  const [greenCells, setGreenCells] = useState<Set<number>>(new Set())
  const [wrongRevealCells, setWrongRevealCells] = useState<Set<number>>(new Set())
  const [botAnimatedCells, setBotAnimatedCells] = useState<Set<number>>(new Set())
  const [status, setStatus] = useState('À vous de jouer')
  const [score, setScore] = useState(0)
  const [botScore, setBotScore] = useState(0)
  const [botTurn, setBotTurn] = useState(false)
  const [resolvingTurn, setResolvingTurn] = useState(false)
  const [turnSeconds, setTurnSeconds] = useState(turnDuration)
  const [validations, setValidations] = useState(0)
  const [productiveTurns, setProductiveTurns] = useState(0)
  const [experienceAward, setExperienceAward] = useState<ExperienceAward | null>(null)
  const [feedback, setFeedback] = useState<SoloFeedback>(null)
  const [scoreEffects, setScoreEffects] = useState<ScoreEffect[]>([])
  const [wordHighlight, setWordHighlight] = useState<BoardWordHighlightState | null>(null)
  const [hint, setHint] = useState<{ tileId: string; cellIndex: number } | null>(null)
  const [hintFlight, setHintFlight] = useState<HintFlight | null>(null)
  const [autoHintCell, setAutoHintCell] = useState<number | null>(null)
  const [hintUsedInMatch, setHintUsedInMatch] = useState(false)
  const [rerollUsedInMatch, setRerollUsedInMatch] = useState(false)
  const [rackRolling, setRackRolling] = useState(false)
  const [turnAlert, setTurnAlert] = useState(true)
  const [paused, setPaused] = useState(false)
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [expandedClue, setExpandedClue] = useState<ClueEntry | null>(null)
  const startedAt = useRef(Date.now())
  const playerIdentity = useRef(loadPlayerIdentity())
  const playerCosmetics = useRef(loadPlayerCosmetics(playerIdentity.current.playerId))
  const botTimer = useRef<number | null>(null)
  const boardTilesRef = useRef(boardTiles)
  const rackRef = useRef(rack)
  const botRackRef = useRef(botRack)
  const validateRef = useRef<() => void>(() => {})
  const aidedCell = useRef<number | null>(null)
  const hintFlightTimer = useRef<number | null>(null)
  const hintLandingTimer = useRef<number | null>(null)
  const turnAlertTimer = useRef<number | null>(null)
  const wasBotTurn = useRef(false)
  const soloAwardId = useRef(makeSoloAwardId())
  const finishCelebrated = useRef(false)
  const finished = grid.cells.every((cell, index) => cell.kind !== 'letter' || boardTiles[index]?.status === 'confirmed')
  const { ghostRef, moveGhost, stopGhost } = useDragGhost()

  const occupiedTileIds = useMemo(() => new Set(Object.values(boardTiles).map(item => item.tile.id)), [boardTiles])
  const focusedWordCells = useMemo(() => {
    if (!expandedClue) return new Set<number>()
    const word = grid.words.find(candidate => candidate.id === expandedClue.wordId)
    return word ? new Set(wordCellIndexes(grid, word)) : new Set<number>()
  }, [expandedClue, grid])
  const visibleRack = rack.filter(tile => !occupiedTileIds.has(tile.id))
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [])
  useEffect(() => { rememberSoloGrid(grid.id) }, [grid.id])
  useEffect(() => () => {
    if (botTimer.current !== null) window.clearTimeout(botTimer.current)
    if (hintFlightTimer.current !== null) window.clearTimeout(hintFlightTimer.current)
    if (hintLandingTimer.current !== null) window.clearTimeout(hintLandingTimer.current)
    if (turnAlertTimer.current !== null) window.clearTimeout(turnAlertTimer.current)
  }, [])
  useEffect(() => { boardTilesRef.current = boardTiles }, [boardTiles])
  useEffect(() => { rackRef.current = rack }, [rack])
  useEffect(() => { botRackRef.current = botRack }, [botRack])
  useEffect(() => {
    if (!finished || resolvingTurn || botTurn || experienceAward) return
    const outcome = score === botScore ? 'draw' : score > botScore ? 'win' : 'loss'
    const grant = awardExperience({
      playerId: playerIdentity.current.playerId,
      awardId: soloAwardId.current,
      mode: 'solo',
      outcome,
      productiveTurns,
    })
    setExperienceAward(grant.award)
  }, [botScore, botTurn, experienceAward, finished, productiveTurns, resolvingTurn, score])
  useEffect(() => {
    if (!finished || finishCelebrated.current) return
    finishCelebrated.current = true
    haptic([18, 32, 18, 55, 28])
    playEffect('word')
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' })
  }, [finished])
  useEffect(() => {
    const heartbeat = () => void setSocialPresence(playerIdentity.current.playerId, 'playing').catch(() => undefined)
    heartbeat()
    const interval = window.setInterval(heartbeat, 10_000)
    return () => { window.clearInterval(interval); void setSocialPresence(playerIdentity.current.playerId, 'online').catch(() => undefined) }
  }, [])
  useEffect(() => {
    if ((!botTurn && wasBotTurn.current) || turnAlert) {
      setTurnAlert(true)
      haptic([90, 55, 90])
      playEffect('turn')
      if (turnAlertTimer.current !== null) window.clearTimeout(turnAlertTimer.current)
      turnAlertTimer.current = window.setTimeout(() => { setTurnAlert(false); turnAlertTimer.current = null }, TURN_READY_DURATION_MS)
    }
    wasBotTurn.current = botTurn
  }, [botTurn])

  const showScoreEffects = (effects: Omit<ScoreEffect, 'id'>[], lifetime = REWARD_EFFECT_LIFETIME_MS) => {
    if (!effects.length) return
    const created = effects.map(effect => ({ ...effect, id: `score-fx-${effectSequence++}` }))
    setScoreEffects(current => [...current, ...created])
    window.setTimeout(() => setScoreEffects(current => current.filter(effect => !created.some(item => item.id === effect.id))), lifetime)
  }

  const playPlayerRewards = (steps: { effect: Omit<ScoreEffect, 'id'>; points: number; status: string; wordCells?: number[]; wordDirection?: 'across' | 'down' }[], onDone: () => void) => {
    setResolvingTurn(true)
    const play = (position: number) => {
      const step = steps[position]
      if (!step) { setGreenCells(new Set()); setWordHighlight(null); setResolvingTurn(false); onDone(); return }
      setGreenCells(step.effect.kind === 'letter' ? new Set([step.effect.cellIndex]) : new Set())
      setWordHighlight(step.wordCells && step.wordDirection ? { cells: new Set(step.wordCells), owner: 'player', direction: step.wordDirection } : null)
      showScoreEffects([step.effect])
      playEffect(step.effect.kind === 'word' ? 'word' : 'score')
      haptic(step.effect.kind === 'word' ? [14, 28, 14] : 10)
      setScore(value => value + step.points)
      setStatus(step.status)
      botTimer.current = window.setTimeout(() => play(position + 1), REWARD_STEP_MS)
    }
    play(0)
  }

  const requestHint = () => {
    if (hintUsedInMatch || botTurn || resolvingTurn || paused || turnAlert) return
    const current = boardTilesRef.current
    const placedTileIds = new Set(Object.values(current).map(item => item.tile.id))
    const availableTiles = rackRef.current.filter(tile => !placedTileIds.has(tile.id))
    const candidates = hintCandidates(grid, availableTiles.map(tile => tile.letter), Object.keys(current).map(Number))
      .map(candidate => ({ tileId: availableTiles[candidate.rackIndex].id, cellIndex: candidate.cellIndex }))
    if (!candidates.length) {
      setStatus('Aucun indice disponible')
      return
    }
    const nextHint = candidates[Math.floor(Math.random() * candidates.length)]
    const tile = rackRef.current.find(candidate => candidate.id === nextHint.tileId)
    const letter = tile?.letter
    if (!tile) return
    const source = document.querySelector<HTMLElement>(`[data-solo-rack-id="${CSS.escape(tile.id)}"]`)
    const target = document.querySelector<HTMLElement>(`[data-cell="${nextHint.cellIndex}"]`)
    const sourceRect = source?.getBoundingClientRect()
    const targetRect = target?.getBoundingClientRect()
    setHint(nextHint)
    setHintUsedInMatch(true)
    aidedCell.current = nextHint.cellIndex
    setStatus('Indice en route…')
    if (sourceRect && targetRect) {
      const fromX = sourceRect.left + sourceRect.width / 2
      const fromY = sourceRect.top + sourceRect.height / 2
      const toX = targetRect.left + targetRect.width / 2
      const toY = targetRect.top + targetRect.height / 2
      setHintFlight({ tileId: tile.id, letter: tile.letter, cellIndex: nextHint.cellIndex, fromX, fromY, deltaX: toX - fromX, deltaY: toY - fromY })
    }
    const land = () => {
      setHintFlight(null)
      setBoardTiles(current => ({ ...current, [nextHint.cellIndex]: { tile, status: 'provisional', owner: 'player' } }))
      setSelected(null)
      setAutoHintCell(nextHint.cellIndex)
      setStatus('Indice placé · +0')
      haptic([15, 35, 15])
      playEffect('place')
      hintFlightTimer.current = null
      hintLandingTimer.current = window.setTimeout(() => {
        setAutoHintCell(current => current === nextHint.cellIndex ? null : current)
        hintLandingTimer.current = null
      }, 1_050)
    }
    hintFlightTimer.current = window.setTimeout(land, sourceRect && targetRect ? 820 : 40)
  }

  const queueBotTurn = () => {
    const thinkingDelay = botThinkingDelayMs(`solo:${grid.id}:${validations}:${opponent.displayName}`)
    setBotTurn(true)
    // The opponent owns a normal 45-second turn, just like a human. Its move
    // begins after a short, believable pause instead of exposing a
    // separate artificial "bot timer".
    setTurnSeconds(45)
    setSelected(null)
    setStatus(`${opponent.displayName} réfléchit…`)
    botTimer.current = window.setTimeout(() => {
      setResolvingTurn(true)
      const current = boardTilesRef.current
      const confirmed = Object.entries(current).filter(([, item]) => item.status === 'confirmed').map(([rawIndex]) => Number(rawIndex))
      const plan = planBotMove({
        grid,
        occupiedCells: confirmed,
        rackLetters: botRackRef.current,
        persona: opponent,
        seed: `solo:${grid.id}:${validations}:${botScore}:${score}:${Date.now()}`,
        scoreGap: score - botScore,
      })
      setBotRack(plan.rackAfter)
      const attempts = plan.attempts.map(attempt => ({ index: attempt.cellIndex, letter: attempt.letter, correct: attempt.correct }))
      let evolving = { ...current }
      let gained = 0
      let successful = 0
      const finishTurn = () => {
        setBotAnimatedCells(new Set())
        setHint(null)
        aidedCell.current = null
        setStatus(successful ? `${opponent.displayName} termine à +${gained} · à vous` : `${opponent.displayName} passe · à vous`)
        setResolvingTurn(false)
        setBotTurn(false)
        setTurnSeconds(turnDuration)
        botTimer.current = window.setTimeout(() => {
          setStatus('À vous de jouer')
          botTimer.current = null
        }, 1400)
      }
      const placeNext = (position: number) => {
        if (position >= attempts.length) { finishTurn(); return }
        const attempt = attempts[position]
        const index = attempt.index
        const cell = grid.cells[index]
        if (cell.kind !== 'letter') { placeNext(position + 1); return }
        if (!attempt.correct) {
          evolving = { ...evolving, [index]: { tile: makeTile(attempt.letter), status: 'wrong', owner: 'bot' } }
          boardTilesRef.current = evolving
          setBoardTiles(evolving)
          setBotAnimatedCells(animated => new Set([...animated, index]))
          setStatus(`${opponent.displayName} essaie ${attempt.letter}…`)
          haptic(12)
          playEffect('error')
          botTimer.current = window.setTimeout(() => {
            const next = { ...evolving }
            delete next[index]
            evolving = next
            boardTilesRef.current = next
            setBoardTiles(next)
            setBotAnimatedCells(animated => { const nextAnimated = new Set(animated); nextAnimated.delete(index); return nextAnimated })
            placeNext(position + 1)
          }, 1_150)
          return
        }
        const before = new Set(Object.entries(evolving).filter(([, item]) => item.status === 'confirmed').map(([rawIndex]) => Number(rawIndex)))
        evolving = { ...evolving, [index]: { tile: makeTile(cell.solution), status: 'confirmed', owner: 'bot' } }
        const evaluation = evaluateTurn({ grid, occupiedBefore: before, placements: [{ cellIndex: index, letter: cell.solution }] })
        const stepPoints = evaluation.scoreGained
        gained += stepPoints
        successful += 1
        boardTilesRef.current = evolving
        setBoardTiles(evolving)
        setBotAnimatedCells(animated => new Set([...animated, index]))
        setStatus(`${opponent.displayName} pose ${position + 1}/${attempts.length} · ${cell.solution}`)
        haptic(12)
        playEffect('score')
        // Let the confirmed letter reach the screen before its reward appears.
        window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
          setBotScore(value => value + 1)
          showScoreEffects([{ kind: 'letter', label: '+1', owner: 'bot', cellIndex: index }])
        }))
        const showWordBonus = (bonusIndex: number) => {
          const word = evaluation.wordBonuses[bonusIndex]
          if (!word) { placeNext(position + 1); return }
          const cells = word.cells
          const cellIndex = word.direction === 'across' ? cells[cells.length - 1] : cells[Math.floor(cells.length / 2)]
          setWordHighlight({ cells: new Set(cells), owner: 'bot', direction: word.direction })
          showScoreEffects([{ kind: 'word', label: `+${word.points}`, owner: 'bot', cellIndex }])
          setBotScore(value => value + word.points)
          setStatus(`Mot terminé · +${word.points}`)
          botTimer.current = window.setTimeout(() => { setWordHighlight(null); showWordBonus(bonusIndex + 1) }, REWARD_STEP_MS)
        }
        botTimer.current = window.setTimeout(() => showWordBonus(0), REWARD_STEP_MS)
      }
      if (attempts.length) placeNext(0)
      else botTimer.current = window.setTimeout(finishTurn, 650)
    }, thinkingDelay)
  }

  const placeTile = (tile: Tile, index: number, origin: 'rack' | number = 'rack') => {
    if (botTurn || resolvingTurn || turnAlert || boardTiles[index]?.status === 'confirmed' || grid.cells[index].kind !== 'letter') return
    setBoardTiles(current => {
      const next = { ...current }
      for (const [key, item] of Object.entries(next)) if (item.tile.id === tile.id) delete next[Number(key)]
      const displaced = next[index]
      next[index] = { tile, status: 'provisional', owner: 'player' }
      if (displaced && typeof origin === 'number' && origin !== index) next[origin] = displaced
      return next
    })
    setSelected(null); setStatus('À valider')
    if (hint?.tileId === tile.id && index !== aidedCell.current) setHint(null)
    haptic(10)
    playEffect('place')
  }

  const rerollRack = () => {
    const rerollAllowed = canUseReroll({
      alreadyUsed: rerollUsedInMatch,
      pendingPlacements: Object.values(boardTiles).filter(item => item.status !== 'confirmed').length,
      hintActive: aidedCell.current !== null,
    })
    if (!rerollAllowed || botTurn || resolvingTurn || paused || turnAlert) return
    const locked = Object.fromEntries(Object.entries(boardTiles).flatMap(([index, item]) => item.status === 'confirmed' ? [[Number(index), item.tile.letter]] : []))
    const previousLetters = visibleRack.map(tile => tile.letter)
    setRack(reconcileRack(grid, locked, [], 5, previousLetters))
    setRerollUsedInMatch(true)
    setRackRolling(true)
    setStatus('Nouvelles lettres')
    haptic([12, 24, 12])
    playEffect('reroll')
    window.setTimeout(() => setRackRolling(false), 620)
  }

  const pointerDown = (event: React.PointerEvent, tile: Tile, origin: 'rack' | number) => {
    if (botTurn || resolvingTurn || paused || turnAlert) return
    event.currentTarget.setPointerCapture(event.pointerId)
    setDrag({ tile, origin, x: event.clientX, y: event.clientY })
    moveGhost(event.clientX, event.clientY)
  }
  const pointerMove = (event: React.PointerEvent) => {
    if (!drag) return
    moveGhost(event.clientX, event.clientY)
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-cell]')
    const rackTarget = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-rack]')
    const nextTarget = target?.dataset.cell ? Number(target.dataset.cell) : rackTarget ? -1 : null
    setDropTarget(current => current === nextTarget ? current : nextTarget)
  }
  const pointerUp = (event: React.PointerEvent) => {
    if (drag) {
      const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-cell]')
      const rackTarget = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-rack]')
      if (target?.dataset.cell) placeTile(drag.tile, Number(target.dataset.cell), drag.origin)
      else if (rackTarget && typeof drag.origin === 'number') returnTile(drag.origin)
    }
    stopGhost(); setDrag(null); setDropTarget(null)
  }
  const pointerCancel = () => { stopGhost(); setDrag(null); setDropTarget(null) }

  const returnTile = (index: number) => {
    if (botTurn || resolvingTurn || paused || turnAlert) return
    if (index === aidedCell.current) return
    setBoardTiles(current => {
      if (current[index]?.status === 'confirmed') return current
      const next = { ...current }; delete next[index]; return next
    })
    setStatus('Lettre reprise')
  }

  const validate = () => {
    if (turnAlert) return
    const provisionalEntries = Object.entries(boardTiles).filter(([, item]) => item.status !== 'confirmed')
    if (provisionalEntries.length === 0) {
      setValidations(value => value + 1)
      setStatus('Tour passé · chevalet conservé')
      queueBotTurn()
      return
    }
    const confirmedBefore = new Set(Object.entries(boardTiles).filter(([, item]) => item.status === 'confirmed').map(([index]) => Number(index)))
    const aidedCellIndex = aidedCell.current
    const evaluation = evaluateTurn({
      grid,
      occupiedBefore: confirmedBefore,
      placements: provisionalEntries.map(([rawIndex, placement]) => ({ cellIndex: Number(rawIndex), letter: placement.tile.letter })),
      aidedCell: aidedCellIndex,
    })
    const correct = evaluation.correctCells
    const wrong = evaluation.wrongCells
    const gridCompletedByPlayer = evaluation.completesGrid
    const rewardedWords = evaluation.wordBonuses
    const fiveLetterBonus = evaluation.rackBonus
    if (evaluation.productive) setProductiveTurns(value => value + 1)
    if (correct.length) {
      setHint(null)
    }
    setValidations(value => value + 1)
    setResolvingTurn(true)
    setBoardTiles(current => Object.fromEntries(Object.entries(current).map(([rawIndex, item]) => {
      const index = Number(rawIndex)
      if (correct.includes(index)) return [rawIndex, { ...item, status: 'confirmed' as const }]
      return [rawIndex, item]
    })))
    setStatus('Vérification…')
    const reconcileAfterReveal = () => {
      const untouched = visibleRack
      const returned = wrong.map(index => boardTiles[index].tile)
      const nextLocked = Object.fromEntries([
        ...Object.entries(boardTiles).filter(([, item]) => item.status === 'confirmed').map(([index, item]) => [index, item.tile.letter]),
        ...correct.map(index => [index, boardTiles[index].tile.letter]),
      ])
      setRack(reconcileRack(grid, nextLocked, [...untouched, ...returned], 5, correct.map(index => boardTiles[index].tile.letter)))
      setBoardTiles(current => Object.fromEntries(Object.entries(current).filter(([rawIndex]) => !wrong.includes(Number(rawIndex)))))
    }
    const rewardSteps = [
      ...correct.map(cellIndex => { const aided = cellIndex === aidedCellIndex; return { effect: { kind: 'letter' as const, label: aided ? '+0' : '+1', owner: 'player' as const, cellIndex }, points: aided ? 0 : 1, status: aided ? 'Lettre aidée · +0' : 'Lettre correcte · +1' } }),
      ...rewardedWords.map(word => { const cells = word.cells; return { effect: { kind: 'word' as const, label: `+${word.points}`, owner: 'player' as const, cellIndex: word.direction === 'across' ? cells[cells.length - 1] : cells[Math.floor(cells.length / 2)] }, points: word.points, status: `Mot terminé · +${word.points}`, wordCells: cells, wordDirection: word.direction } }),
      ...(fiveLetterBonus ? [{ effect: { kind: 'word' as const, label: '+5', owner: 'player' as const, cellIndex: correct[2] }, points: 5, status: 'Chevalet complet · +5' }] : []),
    ]
    const beginRewards = () => {
      setWrongRevealCells(new Set())
      reconcileAfterReveal()
      const continueGame = () => {
        if (gridCompletedByPlayer) {
          setStatus('Grille terminée')
          return
        }
        queueBotTurn()
      }
      if (rewardSteps.length) playPlayerRewards(rewardSteps, continueGame)
      else {
        setResolvingTurn(false)
        if (gridCompletedByPlayer) setStatus('Grille terminée')
        else {
          setStatus('Aucune lettre bien placée')
          queueBotTurn()
        }
      }
    }
    const revealWrong = (position: number) => {
      const index = wrong[position]
      if (index === undefined) { beginRewards(); return }
      const previousIndex = wrong[position - 1]
      if (previousIndex !== undefined) {
        setBoardTiles(current => {
          const next = { ...current }
          delete next[previousIndex]
          return next
        })
      }
      const letter = boardTiles[index].tile.letter
      setWrongRevealCells(new Set([index]))
      setStatus(`${letter} n’est pas ici`)
      haptic([35, 45, 35])
      playEffect('error')
      botTimer.current = window.setTimeout(() => revealWrong(position + 1), 1_050)
    }
    botTimer.current = window.setTimeout(() => {
      if (wrong.length) revealWrong(0)
      else beginRewards()
    }, 260)
  }

  validateRef.current = validate
  useEffect(() => {
    if (finished || resolvingTurn || paused || turnAlert) return
    const timer = window.setInterval(() => {
      setTurnSeconds(current => {
        if (botTurn) return Math.max(0, current - 1)
        if (current > 1) return current - 1
        window.setTimeout(() => validateRef.current(), 0)
        // Keep the display at zero while the turn is being submitted. The next
        // turn resets it explicitly, which avoids a distracting 45 -> 0 flash.
        return 0
      })
    }, 1000)
    return () => window.clearInterval(timer)
  }, [botTurn, resolvingTurn, finished, pace, paused, turnAlert])

  const newGrid = async () => {
    const generated = await generateGrid(Date.now(), difficulty, loadRecentSoloGridIds())
    if (botTimer.current !== null) window.clearTimeout(botTimer.current)
    botTimer.current = null
    aidedCell.current = null
    finishCelebrated.current = false
    soloAwardId.current = makeSoloAwardId()
    const nextOpponent = makeSoloOpponent(difficulty)
    setGrid(generated); setOpponent(nextOpponent); setBoardTiles({}); setRack(drawTiles(generated, {}, 5)); setBotRack(refillBotRack({ grid: generated, occupiedCells: [], currentLetters: [], seed: `solo:${generated.id}:${nextOpponent.displayName}` })); setSelected(null); setDrag(null); setGreenCells(new Set()); setWrongRevealCells(new Set()); setBotAnimatedCells(new Set()); setScoreEffects([]); setWordHighlight(null); setHint(null); setHintFlight(null); setAutoHintCell(null); setHintUsedInMatch(false); setRerollUsedInMatch(false); setRackRolling(false); setPaused(false); setScore(0); setBotScore(0); setBotTurn(false); setResolvingTurn(false); setTurnSeconds(turnDuration); setValidations(0); setProductiveTurns(0); setExperienceAward(null); setFeedback(null); setStatus('Nouvelle grille'); startedAt.current = Date.now()
  }

  const sendFeedback = (quality: 'yes' | 'no', reason?: string) => {
    const record = { playerId: playerIdentity.current.playerId, gridId: grid.id, seed: grid.seed, version: grid.version, botDifficulty: difficulty, quality, reason, seconds: Math.round((Date.now() - startedAt.current) / 1000), validations, date: new Date().toISOString() }
    const previous = JSON.parse(localStorage.getItem('entrelignes-feedback') ?? '[]') as unknown[]
    localStorage.setItem('entrelignes-feedback', JSON.stringify([...previous, record].slice(-100)))
    setFeedback('sent')
  }

  return <main className={`app-shell ${turnAlert ? 'turn-alerting' : ''} ${resolvingTurn ? 'is-resolving' : ''} ${finished ? 'is-finished' : ''}`}>
    <header><button aria-label={finished ? 'Retour aux parties' : 'Mettre en pause'} onClick={() => finished ? onExit() : !botTurn && !resolvingTurn && setPaused(true)} disabled={!finished && (botTurn || resolvingTurn)}>{finished ? <ArrowLeft /> : <Pause />}</button><img className="game-brand-logo" src={assetUrl('/assets/motman-logo-v2.webp')} alt="MotMan" /><button aria-label="Paramètres" onClick={() => setOptionsOpen(true)}><Settings /></button></header>
    {!finished ? <><section className="scoreboard"><Player name={opponent.displayName} detail={`Niv. ${opponent.level}`} score={botScore} initials={playerInitials(opponent.displayName)} avatarId={opponent.avatarId} frameId={opponent.frameId} active={botTurn} /><div className={`turn ${pace === 'realtime' && !resolvingTurn && turnSeconds <= 10 ? 'urgent' : ''} ${pace === 'async' && !botTurn ? 'async-turn' : ''} ${turnAlert ? 'your-turn-pulse' : ''}`} aria-live="polite"><small>{resolvingTurn ? 'Résultats' : botTurn ? `Tour de ${opponent.displayName}` : 'Temps restant'}</small><span className="turn-timer">{resolvingTurn ? '—' : botTurn && pace === 'async' ? '…' : botTurn ? turnSeconds : pace === 'async' ? `${Math.max(1, Math.ceil(turnSeconds / 3_600))}h` : turnSeconds}</span><strong>{status}</strong></div><Player name="Vous" score={score} initials="VO" avatarId={playerCosmetics.current.equippedAvatarId} frameId={playerCosmetics.current.equippedFrameId} animationId={playerCosmetics.current.equippedAnimationId} active={!botTurn && !resolvingTurn} player /></section>
    <p className="instruction">Solo · Bot {DIFFICULTY_LABELS[difficulty].toLowerCase()} · {pace === 'async' ? 'Temps illimité' : 'Temps limité'} · Glissez une lettre dans la grille</p>
    <section className="board-wrap" aria-label="Grille solo" data-bot-level={difficulty}><div className={`board ${focusedWordCells.size ? 'has-clue-focus' : ''}`} style={{ '--board-columns': grid.columns, '--board-rows': grid.rows, '--board-aspect': `${grid.columns} / ${grid.rows}` } as CSSProperties}>
      {grid.cells.map((cell, index) => {
        if (cell.kind === 'block') return <div className="cell block corner-block" key={index} aria-label="Case centrale des définitions" />
        if (cell.kind === 'clue') {
          const orderedEntries = [...cell.entries].sort((left, right) => Number(left.direction === 'down') - Number(right.direction === 'down'))
          const row = Math.floor(index / grid.columns)
          const column = index % grid.columns
          return <div className={`cell clue clue-tone-${(row + column) % 4} ${orderedEntries.length > 1 ? 'double-clue' : ''} ${orderedEntries.length ? '' : 'corner-clue'}`} key={index}>{orderedEntries.length ? orderedEntries.map(entry => <button type="button" className={`clue-entry ${entry.image ? 'image-entry' : ''}`} key={entry.wordId} aria-label={`Agrandir la définition ${entry.text || entry.image?.alt || ''}`} onClick={() => setExpandedClue(entry)}>{entry.image ? <img className="clue-image" src={assetUrl(entry.image.asset)} alt={entry.image.alt} /> : compactClue(entry.text)}<b aria-hidden="true">{entry.direction === 'across' ? '→' : '↓'}</b></button>) : null}</div>
        }
        const boardTile = boardTiles[index]
        const tile = boardTile?.tile
        const letter = tile?.letter
        const confirmed = boardTile?.status === 'confirmed'
        const owner = boardTile?.owner
        const wordRewardClass = wordHighlight?.cells.has(index) ? `word-reward-cell word-reward-cell--${wordHighlight.owner}` : ''
        const hintLocked = aidedCell.current === index && !confirmed
        const ownershipClass = confirmed ? owner === 'player' ? 'confirmed-player' : 'confirmed-opponent' : ''
        return <button key={index} type="button" data-cell={index} aria-label={`Case ${index + 1}`} className={`cell slot ${ownershipClass} ${wordRewardClass} ${focusedWordCells.has(index) ? 'clue-focus' : ''} ${hint?.cellIndex === index ? 'hint-target' : ''} ${autoHintCell === index ? 'hint-auto-placed' : ''} ${dropTarget === index ? 'drop-target' : ''} ${greenCells.has(index) ? 'correct' : ''} ${botAnimatedCells.has(index) ? 'bot-play' : ''} ${wrongRevealCells.has(index) || boardTile?.status === 'wrong' ? 'wrong' : ''}`} onClick={() => boardTile && !confirmed ? returnTile(index) : selected && placeTile(selected, index)}>
          {letter ? <span className={`letter-only ${confirmed ? `locked confirmed-letter ${owner === 'player' ? 'owned-by-player' : 'owned-by-opponent'}` : `provisional-letter ${hintLocked ? 'locked' : ''}`} ${drag?.tile.id === tile?.id ? 'drag-source' : ''}`} onPointerDown={event => tile && !confirmed && !hintLocked && pointerDown(event, tile, index)} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={pointerCancel}>{letter}</span> : null}
        </button>
      })}
      <BoardWordHighlight highlight={wordHighlight} columns={grid.columns} rows={grid.rows} />
      <BoardScoreEffects effects={scoreEffects} columns={grid.columns} rows={grid.rows} />
    </div></section></> : null}
    {!finished ? <>
      <section className="rack-area"><div className="rack-heading"><strong>Vos lettres</strong><span>{visibleRack.length} disponible{visibleRack.length > 1 ? 's' : ''}</span></div><div className={`rack ${dropTarget === -1 ? 'rack-drop' : ''} ${rackRolling ? 'is-rerolling' : ''}`} data-rack="true" aria-label="Lettres disponibles">
        {rack.map(tile => { const isPlaced = occupiedTileIds.has(tile.id); return <div className="rack-slot" key={tile.id}>{!isPlaced ? <button type="button" data-solo-rack-id={tile.id} disabled={turnAlert || botTurn || resolvingTurn || paused} aria-label={`Lettre ${tile.letter}${hint?.tileId === tile.id ? ', indice disponible' : ''}`} className={`rack-letter ${selected?.id === tile.id ? 'selected' : ''} ${drag?.tile.id === tile.id || hintFlight?.tileId === tile.id ? 'drag-source' : ''} ${hint?.tileId === tile.id ? 'hint-letter' : ''}`} onClick={() => setSelected(current => current?.id === tile.id ? null : tile)} onPointerDown={event => pointerDown(event, tile, 'rack')} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={pointerCancel}>{tile.letter}</button> : null}</div> })}
        {Array.from({ length: Math.max(0, 5 - rack.length) }, (_, index) => <div className="rack-slot" aria-hidden="true" key={`empty-${index}`} />)}
        <button className="reroll-button" type="button" onClick={rerollRack} disabled={turnAlert || rerollUsedInMatch || botTurn || resolvingTurn || Object.values(boardTiles).some(item => item.status !== 'confirmed')} aria-label={rerollUsedInMatch ? 'Relance déjà utilisée pendant cette partie' : 'Relancer les lettres'} title={rerollUsedInMatch ? 'Relance déjà utilisée' : 'Relancer les lettres'}><Shuffle /></button>
      </div></section>
      <div className="turn-actions">
        <button className="hint-button" type="button" onClick={requestHint} disabled={turnAlert || hintUsedInMatch || botTurn || resolvingTurn} title={hintUsedInMatch ? 'Indice déjà utilisé pendant cette partie' : 'Utiliser un indice'}><Lightbulb />Indice</button>
        <button className="validate" type="button" onClick={validate} disabled={turnAlert || botTurn || resolvingTurn}><Check />{botTurn ? `${opponent.displayName} joue…` : resolvingTurn ? 'Résultats…' : 'Valider'}</button>
      </div>
    </> : <SoloResultPanel award={experienceAward} playerScore={score} opponentScore={botScore} opponentName={opponent.displayName} feedback={feedback} replay={newGrid} home={onHome} setNegativeFeedback={() => setFeedback('no')} sendFeedback={sendFeedback} />}
    {drag ? <div ref={ghostRef} className="drag-ghost" style={{ left: drag.x, top: drag.y }}>{drag.tile.letter}</div> : null}
    {hintFlight ? <span className="hint-flight" style={{ left: hintFlight.fromX, top: hintFlight.fromY, '--hint-dx': `${hintFlight.deltaX}px`, '--hint-dy': `${hintFlight.deltaY}px`, '--hint-mid-x': `${hintFlight.deltaX * .7}px`, '--hint-mid-y': `${hintFlight.deltaY * .7 - 10}px` } as CSSProperties}>{hintFlight.letter}</span> : null}
    {turnAlert ? <div className="turn-ready-flash" role="status"><span>À vous !</span></div> : null}
    {expandedClue ? <ClueZoom entry={expandedClue} onClose={() => setExpandedClue(null)} /> : null}
    {optionsOpen ? <GameOptionsOverlay close={() => setOptionsOpen(false)} newGrid={newGrid} /> : null}
    {paused ? <PauseOverlay resume={() => setPaused(false)} quit={onExit} /> : null}
  </main>
}

export function SoloGameScreen({ difficulty, pace, onExit, onHome }: {
  difficulty: GridDifficulty
  pace: SoloPace
  onExit: () => void
  onHome: () => void
}) {
  return <SoloGameLoader difficulty={difficulty} pace={pace} onExit={onExit} onHome={onHome} />
}
