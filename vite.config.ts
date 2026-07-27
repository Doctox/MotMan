import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execFileSync } from 'node:child_process'
import { motmanSocialPlugin } from './server/motmanSocialPlugin'
import { motmanMatchPlugin } from './server/motmanMatchPlugin'
import { motmanAuthPlugin } from './server/motmanAuthPlugin'

const githubRepository = process.env.GITHUB_REPOSITORY
const githubPagesBase = githubRepository ? `/${githubRepository.split('/')[1]}/` : '/'
const appVersion = process.env.npm_package_version ?? '0.1.0'
const updateNumber = process.env.GITHUB_RUN_NUMBER?.trim() || 'local'

function resolveBuildSha() {
  const githubSha = process.env.GITHUB_SHA?.trim()
  if (githubSha) return githubSha.slice(0, 7)

  try {
    return execFileSync('git', ['rev-parse', '--short=7', 'HEAD'], { encoding: 'utf8' }).trim()
  } catch {
    return 'inconnu'
  }
}

export default defineConfig({
  base: process.env.VITE_BASE_PATH ?? githubPagesBase,
  define: {
    'import.meta.env.VITE_MOTMAN_APP_VERSION': JSON.stringify(appVersion),
    'import.meta.env.VITE_MOTMAN_BUILD_SHA': JSON.stringify(resolveBuildSha()),
    'import.meta.env.VITE_MOTMAN_UPDATE_NUMBER': JSON.stringify(updateNumber),
  },
  plugins: [react(), motmanAuthPlugin(), motmanSocialPlugin(), motmanMatchPlugin()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react/') || id.includes('node_modules/react-dom/') || id.includes('node_modules/scheduler/')) return 'react-vendor'
          if (id.includes('node_modules/lucide-react/')) return 'icons-vendor'
          if (id.includes('node_modules/@supabase/')) return 'supabase-vendor'
        },
      },
    },
  },
  server: {
    // Phones are used for real multiplayer playtests while the shared grid
    // workspace keeps evolving. Automatic HMR reloads would interrupt both
    // players whenever a catalog, blacklist or clue asset changes.
    hmr: false,
    watch: {
      ignored: ['**/.motman-*.json', '**/.motman*.sqlite*', '**/output/**', '**/dist/**', '**/assets/source-originals/**'],
    },
  },
})
