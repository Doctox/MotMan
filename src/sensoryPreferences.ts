import { useCallback, useEffect, useState } from 'react'

export type SensoryPreferences = {
  effects: boolean
  vibration: boolean
  largeText: boolean
}

export type GameEffect = 'place' | 'score' | 'word' | 'error' | 'turn' | 'reroll'

const STORAGE_KEY = 'motman-sensory-preferences-v1'
const CHANGE_EVENT = 'motman:sensory-preferences'
const DEFAULTS: SensoryPreferences = { effects: true, vibration: true, largeText: false }

let audioContext: AudioContext | null = null

export function loadSensoryPreferences(): SensoryPreferences {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Partial<SensoryPreferences>
    return {
      effects: typeof stored.effects === 'boolean' ? stored.effects : DEFAULTS.effects,
      vibration: typeof stored.vibration === 'boolean' ? stored.vibration : DEFAULTS.vibration,
      largeText: typeof stored.largeText === 'boolean' ? stored.largeText : DEFAULTS.largeText,
    }
  } catch {
    return { ...DEFAULTS }
  }
}

export function applySensoryPreferences(preferences: SensoryPreferences): void {
  document.documentElement.dataset.textSize = preferences.largeText ? 'large' : 'normal'
}

export function initializeSensoryPreferences(): void {
  applySensoryPreferences(loadSensoryPreferences())
}

export function saveSensoryPreferences(preferences: SensoryPreferences): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences))
  applySensoryPreferences(preferences)
  window.dispatchEvent(new CustomEvent<SensoryPreferences>(CHANGE_EVENT, { detail: preferences }))
}

export function useSensoryPreferences() {
  const [preferences, setPreferences] = useState<SensoryPreferences>(loadSensoryPreferences)

  useEffect(() => {
    const sync = (event: Event) => setPreferences((event as CustomEvent<SensoryPreferences>).detail)
    window.addEventListener(CHANGE_EVENT, sync)
    return () => window.removeEventListener(CHANGE_EVENT, sync)
  }, [])

  const setPreference = useCallback((key: keyof SensoryPreferences, value: boolean) => {
    const next = { ...loadSensoryPreferences(), [key]: value }
    saveSensoryPreferences(next)
    setPreferences(next)
  }, [])

  return { preferences, setPreference }
}

export function haptic(pattern: number | number[]): void {
  if (!loadSensoryPreferences().vibration) return
  navigator.vibrate?.(pattern)
}

const EFFECT_NOTES: Record<GameEffect, ReadonlyArray<readonly [frequency: number, delay: number, duration: number, volume: number]>> = {
  place: [[330, 0, .055, .012]],
  score: [[440, 0, .08, .016]],
  word: [[392, 0, .1, .017], [523, .085, .16, .019]],
  error: [[196, 0, .13, .012]],
  turn: [[392, 0, .1, .014], [494, .13, .18, .016]],
  reroll: [[330, 0, .07, .012], [392, .075, .13, .014]],
}

export function playEffect(effect: GameEffect): void {
  if (!loadSensoryPreferences().effects) return
  const AudioContextConstructor = window.AudioContext ?? (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!AudioContextConstructor) return

  try {
    audioContext ??= new AudioContextConstructor()
    const context = audioContext
    const play = () => {
      const start = context.currentTime + .012
      EFFECT_NOTES[effect].forEach(([frequency, delay, duration, volume]) => {
        const oscillator = context.createOscillator()
        const gain = context.createGain()
        oscillator.type = 'sine'
        oscillator.frequency.setValueAtTime(frequency, start + delay)
        gain.gain.setValueAtTime(.0001, start + delay)
        gain.gain.exponentialRampToValueAtTime(volume, start + delay + .018)
        gain.gain.exponentialRampToValueAtTime(.0001, start + delay + duration)
        oscillator.connect(gain)
        gain.connect(context.destination)
        oscillator.start(start + delay)
        oscillator.stop(start + delay + duration + .025)
      })
    }
    if (context.state === 'suspended') void context.resume().then(play).catch(() => undefined)
    else play()
  } catch {
    // Les retours sonores restent un agrément : ils ne doivent jamais bloquer le jeu.
  }
}
