import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { motmanSocialPlugin } from './server/motmanSocialPlugin'
import { motmanMatchPlugin } from './server/motmanMatchPlugin'
import { motmanAuthPlugin } from './server/motmanAuthPlugin'

const githubRepository = process.env.GITHUB_REPOSITORY
const githubPagesBase = githubRepository ? `/${githubRepository.split('/')[1]}/` : '/'

export default defineConfig({
  base: process.env.VITE_BASE_PATH ?? githubPagesBase,
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
