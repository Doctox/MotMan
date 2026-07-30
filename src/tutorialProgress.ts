export const FIRST_RUN_TUTORIAL_VERSION = 1
export const FIRST_RUN_TUTORIAL_STORAGE_KEY = 'motman-first-run-tutorial'

type TutorialProgress = {
  version: number
  completedAt: string
}

function isTutorialProgress(value: unknown): value is TutorialProgress {
  if (!value || typeof value !== 'object') return false
  const progress = value as Partial<TutorialProgress>
  return Number.isInteger(progress.version)
    && typeof progress.completedAt === 'string'
    && Number.isFinite(Date.parse(progress.completedAt))
}

export function hasCompletedFirstRunTutorial(storage: Pick<Storage, 'getItem'> = localStorage): boolean {
  try {
    const raw = storage.getItem(FIRST_RUN_TUTORIAL_STORAGE_KEY)
    if (!raw) return false
    const progress = JSON.parse(raw) as unknown
    return isTutorialProgress(progress) && progress.version >= FIRST_RUN_TUTORIAL_VERSION
  } catch {
    return false
  }
}

export function completeFirstRunTutorial(
  storage: Pick<Storage, 'setItem'> = localStorage,
  completedAt = new Date(),
): void {
  const progress: TutorialProgress = {
    version: FIRST_RUN_TUTORIAL_VERSION,
    completedAt: completedAt.toISOString(),
  }
  try {
    storage.setItem(FIRST_RUN_TUTORIAL_STORAGE_KEY, JSON.stringify(progress))
  } catch {
    // Le tutoriel reste utilisable si le stockage privé est indisponible.
  }
}
