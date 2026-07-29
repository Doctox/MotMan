import assert from 'node:assert/strict'
import { randomBytes } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createClient } from '@supabase/supabase-js'
import WebSocket from 'ws'

export const PRODUCTION_PROJECT_REF = 'kfacjvxzdtxybvxhfmzg'
const DEFAULT_STAGES = [10, 50, 100]
const REQUEST_TIMEOUT_MS = 20_000
const SETUP_CONCURRENCY = 10

export function projectRefFromUrl(value) {
  try {
    const host = new URL(value).hostname
    const match = host.match(/^([a-z0-9]+)\.supabase\.co$/i)
    return match?.[1]?.toLowerCase() ?? null
  } catch {
    return null
  }
}

export function validateStagingConfig(config) {
  const projectRef = projectRefFromUrl(config.url)
  assert.ok(projectRef, 'MOTMAN_STAGING_URL doit être une URL Supabase valide.')
  assert.notEqual(
    projectRef,
    PRODUCTION_PROJECT_REF,
    'Sécurité : le test de charge refuse catégoriquement le projet MotMan de production.',
  )
  assert.equal(
    config.projectRef,
    projectRef,
    'MOTMAN_STAGING_PROJECT_REF ne correspond pas à MOTMAN_STAGING_URL.',
  )
  assert.equal(
    config.confirmation,
    `LOAD_TEST_${projectRef}`,
    `MOTMAN_LOAD_TEST_CONFIRM doit valoir LOAD_TEST_${projectRef}.`,
  )
  assert.ok(config.publishableKey?.length > 20, 'Clé publique staging absente.')
  assert.ok(config.serviceRoleKey?.length > 20, 'Clé service_role staging absente.')
  assert.notEqual(config.publishableKey, config.serviceRoleKey, 'Les deux clés staging sont identiques.')
  return projectRef
}

export function percentile(values, percent) {
  if (!values.length) return 0
  const ordered = [...values].sort((left, right) => left - right)
  const index = Math.max(0, Math.ceil((percent / 100) * ordered.length) - 1)
  return ordered[index]
}

export function summarizeSamples(samples, wallMs) {
  const durations = samples.map(sample => sample.durationMs)
  const statusCounts = samples.reduce((counts, sample) => {
    const key = String(sample.status)
    counts[key] = (counts[key] ?? 0) + 1
    return counts
  }, {})
  const failures = samples.filter(sample => !sample.ok)
  return {
    requests: samples.length,
    successes: samples.length - failures.length,
    failures: failures.length,
    errorRatePercent: samples.length ? Number((failures.length * 100 / samples.length).toFixed(2)) : 0,
    statusCounts,
    latencyMs: {
      min: durations.length ? Math.min(...durations) : 0,
      p50: percentile(durations, 50),
      p95: percentile(durations, 95),
      p99: percentile(durations, 99),
      max: durations.length ? Math.max(...durations) : 0,
    },
    throughputPerSecond: wallMs > 0
      ? Number((samples.length * 1000 / wallMs).toFixed(2))
      : 0,
    failuresPreview: failures.slice(0, 10).map(sample => ({
      status: sample.status,
      code: sample.code,
      message: sample.message,
    })),
  }
}

function parseEnvText(source) {
  return Object.fromEntries(source.split(/\r?\n/).flatMap(line => {
    const match = line.match(/^\s*([^#=\s]+)\s*=\s*(.*?)\s*$/)
    if (!match) return []
    return [[match[1], match[2].replace(/^['"]|['"]$/g, '')]]
  }))
}

async function loadConfig() {
  const envFileArg = process.argv.find(argument => argument.startsWith('--env='))
  const envFile = envFileArg?.slice('--env='.length)
  const fileEnv = envFile ? parseEnvText(await readFile(resolve(envFile), 'utf8')) : {}
  const env = { ...fileEnv, ...process.env }
  const config = {
    url: env.MOTMAN_STAGING_URL,
    projectRef: env.MOTMAN_STAGING_PROJECT_REF,
    publishableKey: env.MOTMAN_STAGING_PUBLISHABLE_KEY,
    serviceRoleKey: env.MOTMAN_STAGING_SERVICE_ROLE_KEY,
    confirmation: env.MOTMAN_LOAD_TEST_CONFIRM,
  }
  validateStagingConfig(config)
  return config
}

function parseStages() {
  const argument = process.argv.find(item => item.startsWith('--stages='))
  const values = (argument?.slice('--stages='.length) ?? DEFAULT_STAGES.join(','))
    .split(',')
    .map(value => Number(value.trim()))
  assert.ok(values.length > 0 && values.every(value => Number.isInteger(value) && value >= 2 && value <= 100))
  assert.ok(values.every(value => value % 2 === 0), 'Chaque palier doit contenir un nombre pair de joueurs.')
  return values
}

async function mapLimit(items, concurrency, callback) {
  const results = new Array(items.length)
  let cursor = 0
  const workers = Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    while (cursor < items.length) {
      const index = cursor
      cursor += 1
      results[index] = await callback(items[index], index)
    }
  })
  await Promise.all(workers)
  return results
}

function makeClient(url, publishableKey) {
  return createClient(url, publishableKey, {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    realtime: { transport: WebSocket },
  })
}

async function invoke(config, player, functionName, body) {
  const startedAt = performance.now()
  try {
    const response = await fetch(`${config.url}/functions/v1/${functionName}`, {
      method: 'POST',
      headers: {
        apikey: config.publishableKey,
        Authorization: `Bearer ${player.token}`,
        'Content-Type': 'application/json',
        'X-MotMan-Load-Test': player.runId,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
    const payload = await response.json().catch(() => ({}))
    return {
      ok: response.ok,
      status: response.status,
      durationMs: Number((performance.now() - startedAt).toFixed(2)),
      payload,
      code: typeof payload.code === 'string' ? payload.code : null,
      message: response.ok ? null : String(payload.error ?? response.statusText),
    }
  } catch (error) {
    return {
      ok: false,
      status: 0,
      durationMs: Number((performance.now() - startedAt).toFixed(2)),
      payload: {},
      code: error?.name ?? 'NETWORK_ERROR',
      message: error instanceof Error ? error.message : String(error),
    }
  }
}

async function runPhase(name, actors, callback) {
  const startedAt = performance.now()
  const samples = await Promise.all(actors.map(callback))
  const wallMs = Number((performance.now() - startedAt).toFixed(2))
  return { name, wallMs, ...summarizeSamples(samples, wallMs), samples }
}

async function createPlayers(config, runId, count, onPlayerCreated) {
  const admin = createClient(config.url, config.serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  })
  const password = `Load-${randomBytes(18).toString('base64url')}!9`
  return mapLimit(Array.from({ length: count }, (_, index) => index), SETUP_CONCURRENCY, async index => {
    const email = `motman-load-${runId}-${String(index + 1).padStart(3, '0')}@example.invalid`
    const { data: created, error: createError } = await admin.auth.admin.createUser({
      email,
      password,
      email_confirm: true,
      app_metadata: { motman_load_test: true, load_test_run_id: runId },
    })
    if (createError || !created.user) throw createError ?? new Error(`Création impossible pour ${email}`)

    const client = makeClient(config.url, config.publishableKey)
    const player = {
      id: created.user.id,
      email,
      token: null,
      client,
      runId,
    }
    onPlayerCreated(index, player)
    const { data: signedIn, error: signInError } = await client.auth.signInWithPassword({ email, password })
    if (signInError || !signedIn.session) throw signInError ?? new Error(`Connexion impossible pour ${email}`)
    player.token = signedIn.session.access_token
    const bootstrap = await invoke(config, player, 'account-api', {
      action: 'bootstrap',
      identity: { displayName: `Charge ${String(index + 1).padStart(3, '0')}` },
    })
    if (!bootstrap.ok) throw new Error(`Bootstrap ${email}: ${bootstrap.status} ${bootstrap.message}`)
    return player
  })
}

async function subscribeMenu(player) {
  const startedAt = performance.now()
  let channel
  try {
    await new Promise((resolvePromise, rejectPromise) => {
      const timer = setTimeout(() => rejectPromise(new Error('Realtime subscription timeout')), 12_000)
      channel = player.client
        .channel(`user:${player.id}`, { config: { private: true } })
        .on('broadcast', { event: 'changed' }, () => undefined)
        .subscribe((status, error) => {
          if (status === 'SUBSCRIBED') {
            clearTimeout(timer)
            resolvePromise()
          }
          if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT' || status === 'CLOSED') {
            clearTimeout(timer)
            rejectPromise(new Error(error?.message ?? status))
          }
        })
    })
    return {
      ok: true,
      status: 101,
      durationMs: Number((performance.now() - startedAt).toFixed(2)),
      channel,
    }
  } catch (error) {
    if (channel) await player.client.removeChannel(channel).catch(() => undefined)
    return {
      ok: false,
      status: 0,
      durationMs: Number((performance.now() - startedAt).toFixed(2)),
      code: 'REALTIME_SUBSCRIBE_FAILED',
      message: error instanceof Error ? error.message : String(error),
      channel: null,
    }
  }
}

async function closeRealtime(players) {
  await Promise.all(players.map(player => player.client.removeAllChannels().catch(() => undefined)))
}

function activeMatchIdsFromPhase(phase) {
  const ownership = new Map()
  for (let index = 0; index < phase.samples.length; index += 1) {
    const sample = phase.samples[index]
    for (const match of sample.payload?.active ?? []) {
      if (typeof match?.id === 'string' && !ownership.has(match.id)) ownership.set(match.id, index)
    }
  }
  return ownership
}

async function cleanupMatches(config, actors, lobbyPhase) {
  const ownership = activeMatchIdsFromPhase(lobbyPhase)
  const entries = [...ownership.entries()]
  await mapLimit(entries, 10, async ([matchId, playerIndex]) => {
    await invoke(config, actors[playerIndex], 'match-api', { action: 'forfeit', matchId })
  })
  await Promise.all(actors.map(player => invoke(config, player, 'match-api', {
    action: 'search-cancel',
    pace: 'realtime',
  })))
  return entries.length
}

async function runStage(config, allPlayers, virtualUsers) {
  const actors = allPlayers.slice(0, virtualUsers)
  const phases = []

  const realtimeStartedAt = performance.now()
  const realtimeSamples = await Promise.all(actors.map(subscribeMenu))
  const realtimeWallMs = Number((performance.now() - realtimeStartedAt).toFixed(2))
  phases.push({
    name: 'realtime-menu-subscribe',
    wallMs: realtimeWallMs,
    ...summarizeSamples(realtimeSamples, realtimeWallMs),
  })

  phases.push(await runPhase('presence-heartbeat', actors, player =>
    invoke(config, player, 'social-api', { action: 'presence', activity: 'online' })))
  phases.push(await runPhase('social-state', actors, player =>
    invoke(config, player, 'social-api', { action: 'state' })))
  phases.push(await runPhase('match-lobby-before', actors, player =>
    invoke(config, player, 'match-api', { action: 'state' })))
  phases.push(await runPhase('grid-usage-snapshot', actors, player =>
    invoke(config, player, 'grid-usage-api', { action: 'snapshot' })))
  phases.push(await runPhase('atomic-matchmaking', actors, player =>
    invoke(config, player, 'match-api', { action: 'search', pace: 'realtime' })))
  const lobbyAfter = await runPhase('match-lobby-after', actors, player =>
    invoke(config, player, 'match-api', { action: 'state' }))
  phases.push(lobbyAfter)

  const ownership = activeMatchIdsFromPhase(lobbyAfter)
  const matchViews = [...ownership.entries()].map(([matchId, playerIndex]) => ({
    matchId,
    player: actors[playerIndex],
  }))
  phases.push(await runPhase('authoritative-match-view', matchViews, item =>
    invoke(config, item.player, 'match-api', { action: 'match', matchId: item.matchId })))

  await closeRealtime(actors)
  const cleanedMatches = await cleanupMatches(config, actors, lobbyAfter)

  const publicPhases = phases.map(({ samples: _samples, ...phase }) => phase)
  const failures = publicPhases.reduce((total, phase) => total + phase.failures, 0)
  const serverErrors = publicPhases.reduce((total, phase) => total + Object.entries(phase.statusCounts)
    .filter(([status]) => Number(status) >= 500 || status === '0')
    .reduce((sum, [, count]) => sum + count, 0), 0)
  const expectedMatches = virtualUsers / 2
  return {
    virtualUsers,
    expectedMatches,
    matchesObserved: ownership.size,
    matchesCleaned: cleanedMatches,
    phases: publicPhases,
    verdict: {
      passed: failures === 0 && serverErrors === 0 && ownership.size === expectedMatches,
      failures,
      serverErrors,
      matchmakingComplete: ownership.size === expectedMatches,
    },
  }
}

async function cleanupPlayers(config, players) {
  const admin = createClient(config.url, config.serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  })
  return mapLimit(players.filter(Boolean), SETUP_CONCURRENCY, async player => {
    await player.client.removeAllChannels().catch(() => undefined)
    const deleted = player.token
      ? await invoke(config, player, 'account-api', {
        action: 'delete-account',
        confirmation: 'SUPPRIMER',
      })
      : { ok: false }
    if (!deleted.ok) {
      const { error } = await admin.auth.admin.deleteUser(player.id)
      if (error) return { id: player.id, ok: false, error: error.message }
    }
    return { id: player.id, ok: true }
  })
}

async function preflight(config) {
  const admin = createClient(config.url, config.serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  })
  const { count, error } = await admin
    .from('server_grid_catalog')
    .select('id', { count: 'exact', head: true })
    .eq('active', true)
  if (error) throw new Error(`Préflight catalogue staging : ${error.message}`)
  assert.ok((count ?? 0) > 0, 'Le catalogue staging ne contient aucune grille active.')
  return { activeGrids: count }
}

async function main() {
  const config = await loadConfig()
  const stages = parseStages()
  const runId = `lt-${new Date().toISOString().replace(/\D/g, '').slice(0, 14)}-${randomBytes(3).toString('hex')}`
  const projectRef = projectRefFromUrl(config.url)
  const startedAt = new Date().toISOString()
  const preflightResult = await preflight(config)
  let players = []
  const report = {
    schema: 'motman-supabase-staging-load-test',
    version: 1,
    runId,
    projectRef,
    productionProtected: projectRef !== PRODUCTION_PROJECT_REF,
    startedAt,
    stagesRequested: stages,
    preflight: preflightResult,
    stages: [],
    cleanup: null,
  }

  try {
    players = await createPlayers(
      config,
      runId,
      Math.max(...stages),
      (index, player) => { players[index] = player },
    )
    for (const stage of stages) {
      const result = await runStage(config, players, stage)
      report.stages.push(result)
      console.log(JSON.stringify({
        stage,
        passed: result.verdict.passed,
        matches: `${result.matchesObserved}/${result.expectedMatches}`,
        failures: result.verdict.failures,
      }))
      if (!result.verdict.passed) break
    }
  } finally {
    const cleanup = await cleanupPlayers(config, players)
    report.cleanup = {
      attempted: cleanup.length,
      succeeded: cleanup.filter(item => item.ok).length,
      failed: cleanup.filter(item => !item.ok),
    }
    report.completedAt = new Date().toISOString()
    report.passed = report.stages.length === stages.length
      && report.stages.every(stage => stage.verdict.passed)
      && report.cleanup.failed.length === 0
    const outputPath = resolve('output', 'load-tests', `${runId}.json`)
    await mkdir(dirname(outputPath), { recursive: true })
    await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8')
    console.log(`Rapport : ${outputPath}`)
  }

  if (!report.passed) process.exitCode = 1
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : ''
if (invokedPath && fileURLToPath(import.meta.url) === invokedPath) {
  main().catch(error => {
    console.error(error instanceof Error ? error.stack : error)
    process.exitCode = 1
  })
}
