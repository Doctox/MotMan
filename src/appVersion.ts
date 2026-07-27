export type AppVersion = {
  version: string
  updateNumber: string
  buildSha: string
}

function normalized(value: unknown, fallback: string) {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

export const appVersion: AppVersion = {
  version: normalized(import.meta.env.VITE_MOTMAN_APP_VERSION, '0.1.0'),
  updateNumber: normalized(import.meta.env.VITE_MOTMAN_UPDATE_NUMBER, 'local'),
  buildSha: normalized(import.meta.env.VITE_MOTMAN_BUILD_SHA, 'inconnu'),
}

export function formatAppVersion({ version, updateNumber, buildSha }: AppVersion) {
  const updateLabel = /^\d+$/.test(updateNumber)
    ? `#${updateNumber}`
    : 'Local'

  return {
    updateLabel,
    buildLabel: `Version ${version} · ${buildSha}`,
    accessibleLabel: `${updateLabel}, version ${version}, code ${buildSha}`,
  }
}

export const appVersionDisplay = formatAppVersion(appVersion)
