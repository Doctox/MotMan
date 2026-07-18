import { defineConfig, devices } from '@playwright/test'
import { resolve } from 'node:path'

const stateDirectory = resolve('output/playwright/state')

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 12_000 },
  reporter: 'line',
  outputDir: 'output/playwright/results',
  use: {
    baseURL: 'http://127.0.0.1:4175',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'webkit', use: { ...devices['iPhone 13'] } },
  ],
  webServer: {
    command: 'npm run dev -- --port 4175',
    url: 'http://127.0.0.1:4175',
    reuseExistingServer: true,
    timeout: 120_000,
    env: {
      ...process.env,
      MOTMAN_MATCH_DATABASE_PATH: resolve(stateDirectory, 'matches.json'),
      MOTMAN_SOCIAL_DATABASE_PATH: resolve(stateDirectory, 'social.json'),
      // Keep enough room for two cold mobile contexts while making the
      // 2 s / 1 s / 0 s boundary matrix practical on every test run.
      // Production remains at 45 seconds.
      MOTMAN_TURN_DURATION_MS: '12000',
      MOTMAN_ASYNC_TURN_DURATION_MS: '6000',
      // Long enough for Chromium/WebKit to observe the two-beat turn cue reliably.
      MOTMAN_TURN_READY_DURATION_MS: '350',
      MOTMAN_TURN_GRACE_MS: '1200',
      MOTMAN_REVEAL_STEP_MS: '30',
      MOTMAN_MIN_REVEAL_DURATION_MS: '20',
      MOTMAN_REALTIME_BOT_DELAY_MS: '60000',
      MOTMAN_ASYNC_BOT_DELAY_MS: '60000',
      VITE_MOTMAN_LOCAL_TEST_SERVER: 'true',
    },
  },
})
