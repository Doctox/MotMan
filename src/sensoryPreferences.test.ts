import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  initializeSensoryPreferences,
  loadSensoryPreferences,
  saveSensoryPreferences,
} from './sensoryPreferences'

const stored = new Map<string, string>()
const dataset: Record<string, string> = {}

beforeEach(() => {
  stored.clear()
  Object.keys(dataset).forEach(key => delete dataset[key])
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => stored.get(key) ?? null,
    setItem: (key: string, value: string) => stored.set(key, value),
  })
  vi.stubGlobal('document', { documentElement: { dataset } })
  vi.stubGlobal('window', { dispatchEvent: vi.fn() })
  vi.stubGlobal('CustomEvent', class<T> { constructor(public type: string, public init: { detail: T }) {} })
})

describe('préférences d’accessibilité', () => {
  it('migre silencieusement les anciennes préférences avec Musique', () => {
    stored.set('motman-sensory-preferences-v1', JSON.stringify({ music: false, effects: false }))
    expect(loadSensoryPreferences()).toEqual({ effects: false, vibration: true, largeText: false })
  })

  it('applique et conserve le texte agrandi', () => {
    saveSensoryPreferences({ effects: true, vibration: false, largeText: true })
    expect(dataset.textSize).toBe('large')
    expect(JSON.parse(stored.get('motman-sensory-preferences-v1') ?? '{}')).toEqual({
      effects: true,
      vibration: false,
      largeText: true,
    })
  })

  it('applique la préférence avant le premier écran', () => {
    stored.set('motman-sensory-preferences-v1', JSON.stringify({ largeText: true }))
    initializeSensoryPreferences()
    expect(dataset.textSize).toBe('large')
  })
})
