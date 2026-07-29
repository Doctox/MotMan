#!/usr/bin/env node

import { createHash } from 'node:crypto'
import { appendFile, mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

export const DEFAULT_THRESHOLDS = Object.freeze({
  windowMinutes: 15,
  max5xx: 0,
  max429: 4,
  maxP95Ms: 1500,
  maxInvocations: 1000,
  minInvocationsForLatency: 20,
})

function finiteInteger(value, fallback, minimum = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed >= minimum ? Math.trunc(parsed) : fallback
}

export function thresholdsFromEnv(env = process.env) {
  return {
    windowMinutes: finiteInteger(env.EDGE_ALERT_WINDOW_MINUTES, DEFAULT_THRESHOLDS.windowMinutes, 1),
    max5xx: finiteInteger(env.EDGE_ALERT_MAX_5XX, DEFAULT_THRESHOLDS.max5xx),
    max429: finiteInteger(env.EDGE_ALERT_MAX_429, DEFAULT_THRESHOLDS.max429),
    maxP95Ms: finiteInteger(env.EDGE_ALERT_MAX_P95_MS, DEFAULT_THRESHOLDS.maxP95Ms, 1),
    maxInvocations: finiteInteger(env.EDGE_ALERT_MAX_INVOCATIONS, DEFAULT_THRESHOLDS.maxInvocations, 1),
    minInvocationsForLatency: finiteInteger(
      env.EDGE_ALERT_MIN_INVOCATIONS_FOR_LATENCY,
      DEFAULT_THRESHOLDS.minInvocationsForLatency,
      1,
    ),
  }
}

export function buildEdgeMetricsSql() {
  const aggregate = `
  count() as invocations,
  countIf(toInt32OrZero(log_attributes['response.status_code']) between 500 and 599) as errors_5xx,
  countIf(toInt32OrZero(log_attributes['response.status_code']) = 429) as errors_429,
  quantileExact(0.95)(toUInt64OrZero(log_attributes['execution_time_ms'])) as p95_ms,
  max(toUInt64OrZero(log_attributes['execution_time_ms'])) as max_ms`

  return `select 'TOTAL' as scope,${aggregate}
from logs
where source = 'function_edge_logs'
union all
select if(log_attributes['request.pathname'] = '', 'unknown', log_attributes['request.pathname']) as scope,${aggregate}
from logs
where source = 'function_edge_logs'
group by scope
order by invocations desc, scope asc`
}

function numeric(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export function normalizeMetricRows(payload) {
  const rawRows = payload?.result
  const rows = Array.isArray(rawRows) ? rawRows : rawRows && typeof rawRows === 'object' ? [rawRows] : []
  return rows.map(row => ({
    scope: String(row.scope ?? 'unknown'),
    invocations: numeric(row.invocations),
    errors5xx: numeric(row.errors_5xx),
    errors429: numeric(row.errors_429),
    p95Ms: numeric(row.p95_ms),
    maxMs: numeric(row.max_ms),
  }))
}

function alertSeverity(value, threshold) {
  return value > threshold * 2 && threshold > 0 ? 'critical' : 'warning'
}

export function evaluateEdgeMetrics(total, thresholds = DEFAULT_THRESHOLDS) {
  const alerts = []

  if (total.errors5xx > thresholds.max5xx) {
    alerts.push({
      code: 'edge-5xx',
      severity: 'critical',
      value: total.errors5xx,
      threshold: thresholds.max5xx,
      message: `${total.errors5xx} réponse(s) 5xx sur la fenêtre surveillée.`,
    })
  }
  if (total.errors429 > thresholds.max429) {
    alerts.push({
      code: 'edge-429',
      severity: alertSeverity(total.errors429, thresholds.max429),
      value: total.errors429,
      threshold: thresholds.max429,
      message: `${total.errors429} réponse(s) 429 sur la fenêtre surveillée.`,
    })
  }
  if (
    total.invocations >= thresholds.minInvocationsForLatency
    && total.p95Ms > thresholds.maxP95Ms
  ) {
    alerts.push({
      code: 'edge-p95',
      severity: alertSeverity(total.p95Ms, thresholds.maxP95Ms),
      value: total.p95Ms,
      threshold: thresholds.maxP95Ms,
      message: `Latence p95 à ${total.p95Ms} ms.`,
    })
  }
  if (total.invocations > thresholds.maxInvocations) {
    alerts.push({
      code: 'edge-invocations',
      severity: alertSeverity(total.invocations, thresholds.maxInvocations),
      value: total.invocations,
      threshold: thresholds.maxInvocations,
      message: `${total.invocations} invocation(s) Edge sur la fenêtre surveillée.`,
    })
  }

  return alerts
}

export function buildEdgeAlertReport(payload, {
  checkedAt = new Date(),
  thresholds = DEFAULT_THRESHOLDS,
  projectRef,
} = {}) {
  if (payload?.error) throw new Error(`Supabase Logs API: ${payload.error}`)
  const rows = normalizeMetricRows(payload)
  const total = rows.find(row => row.scope === 'TOTAL') ?? {
    scope: 'TOTAL',
    invocations: 0,
    errors5xx: 0,
    errors429: 0,
    p95Ms: 0,
    maxMs: 0,
  }
  const alerts = evaluateEdgeMetrics(total, thresholds)
  const end = new Date(Math.floor(checkedAt.getTime() / 60_000) * 60_000)
  const start = new Date(end.getTime() - thresholds.windowMinutes * 60_000)
  const alertSignature = createHash('sha256')
    .update(alerts.map(alert => `${alert.code}:${alert.severity}`).sort().join('|'))
    .digest('hex')
    .slice(0, 16)

  return {
    schemaVersion: 1,
    projectRef,
    checkedAt: checkedAt.toISOString(),
    window: {
      minutes: thresholds.windowMinutes,
      start: start.toISOString(),
      end: end.toISOString(),
    },
    thresholds,
    healthy: alerts.length === 0,
    alertSignature,
    alerts,
    totals: total,
    functions: rows
      .filter(row => row.scope !== 'TOTAL')
      .sort((left, right) => right.invocations - left.invocations || left.scope.localeCompare(right.scope)),
  }
}

export function renderEdgeAlertMarkdown(report) {
  const status = report.healthy ? '✅ Normal' : '🚨 Alerte'
  const lines = [
    `## Supabase Edge — ${status}`,
    '',
    `Fenêtre : ${report.window.start} → ${report.window.end} (${report.window.minutes} min)`,
    '',
    '| Invocations | 5xx | 429 | p95 | max |',
    '| ---: | ---: | ---: | ---: | ---: |',
    `| ${report.totals.invocations} | ${report.totals.errors5xx} | ${report.totals.errors429} | ${report.totals.p95Ms} ms | ${report.totals.maxMs} ms |`,
  ]

  if (report.alerts.length) {
    lines.push('', '### Seuils dépassés', '')
    for (const alert of report.alerts) lines.push(`- **${alert.severity}** — ${alert.message}`)
  }
  if (report.functions.length) {
    lines.push('', '### Par fonction', '', '| Fonction | Invocations | 5xx | 429 | p95 |', '| --- | ---: | ---: | ---: | ---: |')
    for (const metric of report.functions) {
      lines.push(`| \`${metric.scope}\` | ${metric.invocations} | ${metric.errors5xx} | ${metric.errors429} | ${metric.p95Ms} ms |`)
    }
  }
  return `${lines.join('\n')}\n`
}

export async function queryEdgeMetrics({
  accessToken,
  projectRef,
  checkedAt = new Date(),
  thresholds = DEFAULT_THRESHOLDS,
  fetchImpl = fetch,
}) {
  if (!accessToken) throw new Error('SUPABASE_ACCESS_TOKEN est absent.')
  if (!/^[a-z0-9]{20}$/i.test(projectRef ?? '')) throw new Error('SUPABASE_PROJECT_REF est invalide.')

  const end = new Date(Math.floor(checkedAt.getTime() / 60_000) * 60_000)
  const start = new Date(end.getTime() - thresholds.windowMinutes * 60_000)
  const endpoint = new URL(`https://api.supabase.com/v1/projects/${projectRef}/analytics/endpoints/logs`)
  endpoint.searchParams.set('iso_timestamp_start', start.toISOString())
  endpoint.searchParams.set('iso_timestamp_end', end.toISOString())
  endpoint.searchParams.set('sql', buildEdgeMetricsSql())

  const response = await fetchImpl(endpoint, {
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    signal: AbortSignal.timeout(25_000),
  })
  const text = await response.text()
  let payload
  try {
    payload = JSON.parse(text)
  } catch {
    throw new Error(`La Logs API a renvoyé une réponse non JSON (HTTP ${response.status}).`)
  }
  if (!response.ok) throw new Error(`La Logs API a renvoyé HTTP ${response.status}: ${payload?.message ?? payload?.error ?? 'erreur inconnue'}`)
  return payload
}

function parseArgs(argv) {
  const options = {}
  for (const argument of argv) {
    const match = argument.match(/^--([^=]+)=(.*)$/)
    if (match) options[match[1]] = match[2]
  }
  return options
}

async function appendGithubValue(file, key, value) {
  if (!file) return
  await appendFile(file, `${key}=${value}\n`, 'utf8')
}

export async function main(argv = process.argv.slice(2), env = process.env) {
  const options = parseArgs(argv)
  const checkedAt = options.now ? new Date(options.now) : new Date()
  if (Number.isNaN(checkedAt.getTime())) throw new Error('--now doit être une date ISO valide.')
  const thresholds = thresholdsFromEnv({
    ...env,
    ...(options['window-minutes'] ? { EDGE_ALERT_WINDOW_MINUTES: options['window-minutes'] } : {}),
  })
  const projectRef = options['project-ref'] ?? env.SUPABASE_PROJECT_REF
  let payload
  if (options.fixture) {
    payload = JSON.parse(await readFile(resolve(options.fixture), 'utf8'))
  } else {
    payload = await queryEdgeMetrics({
      accessToken: env.SUPABASE_ACCESS_TOKEN,
      projectRef,
      checkedAt,
      thresholds,
    })
  }

  const report = buildEdgeAlertReport(payload, { checkedAt, thresholds, projectRef })
  const outputPath = resolve(options.output ?? 'output/monitoring/supabase-edge-health.json')
  await mkdir(dirname(outputPath), { recursive: true })
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8')
  const markdown = renderEdgeAlertMarkdown(report)
  process.stdout.write(markdown)

  if (env.GITHUB_STEP_SUMMARY) await appendFile(env.GITHUB_STEP_SUMMARY, markdown, 'utf8')
  await appendGithubValue(env.GITHUB_OUTPUT, 'has_alerts', String(!report.healthy))
  await appendGithubValue(env.GITHUB_OUTPUT, 'alert_count', String(report.alerts.length))
  await appendGithubValue(env.GITHUB_OUTPUT, 'alert_signature', report.alertSignature)
  await appendGithubValue(env.GITHUB_OUTPUT, 'report_path', outputPath.replaceAll('\\', '/'))
  return report
}

const isDirectRun = process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href
if (isDirectRun) {
  main().catch(error => {
    console.error(`Surveillance Supabase Edge impossible : ${error instanceof Error ? error.message : String(error)}`)
    process.exitCode = 1
  })
}
