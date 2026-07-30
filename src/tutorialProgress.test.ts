import { describe, expect, it } from 'vitest'
import {
  completeFirstRunTutorial,
  FIRST_RUN_TUTORIAL_STORAGE_KEY,
  FIRST_RUN_TUTORIAL_VERSION,
  hasCompletedFirstRunTutorial,
} from './tutorialProgress'

function memoryStorage(initialValue: string | null = null) {
  let value = initialValue
  return {
    getItem: (key: string) => key === FIRST_RUN_TUTORIAL_STORAGE_KEY ? value : null,
    setItem: (key: string, next: string) => {
      if (key === FIRST_RUN_TUTORIAL_STORAGE_KEY) value = next
    },
    value: () => value,
  }
}

describe('tutoriel de première ouverture', () => {
  it('s’affiche tant que la version courante n’a pas été terminée', () => {
    expect(hasCompletedFirstRunTutorial(memoryStorage())).toBe(false)
    expect(hasCompletedFirstRunTutorial(memoryStorage('{"version":0,"completedAt":"2026-07-30T12:00:00.000Z"}'))).toBe(false)
    expect(hasCompletedFirstRunTutorial(memoryStorage('invalide'))).toBe(false)
  })

  it('mémorise une complétion versionnée et datée', () => {
    const storage = memoryStorage()
    completeFirstRunTutorial(storage, new Date('2026-07-30T12:00:00.000Z'))

    expect(JSON.parse(storage.value() ?? '{}')).toEqual({
      version: FIRST_RUN_TUTORIAL_VERSION,
      completedAt: '2026-07-30T12:00:00.000Z',
    })
    expect(hasCompletedFirstRunTutorial(storage)).toBe(true)
  })

  it('ne bloque pas le jeu lorsque le stockage est indisponible', () => {
    const unavailable = {
      getItem: () => { throw new Error('storage unavailable') },
      setItem: () => { throw new Error('storage unavailable') },
    }
    expect(hasCompletedFirstRunTutorial(unavailable)).toBe(false)
    expect(() => completeFirstRunTutorial(unavailable)).not.toThrow()
  })
})
