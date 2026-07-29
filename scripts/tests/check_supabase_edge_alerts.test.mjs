import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildEdgeAlertReport,
  buildEdgeMetricsSql,
  DEFAULT_THRESHOLDS,
  evaluateEdgeMetrics,
  normalizeMetricRows,
  renderEdgeAlertMarkdown,
  thresholdsFromEnv,
} from '../check_supabase_edge_alerts.mjs'

const healthyTotal = {
  scope: 'TOTAL',
  invocations: 100,
  errors5xx: 0,
  errors429: 2,
  p95Ms: 900,
  maxMs: 1800,
}

test('builds a narrow query over the Edge Function log source', () => {
  const sql = buildEdgeMetricsSql()
  assert.match(sql, /source = 'function_edge_logs'/)
  assert.match(sql, /execution_time_ms/)
  assert.match(sql, /response\.status_code/)
  assert.match(sql, /request\.pathname/)
  assert.doesNotMatch(sql, /select \*/)
})

test('normalizes the object and array response shapes from the Logs API', () => {
  const row = {
    scope: 'TOTAL',
    invocations: '12',
    errors_5xx: '1',
    errors_429: '2',
    p95_ms: '345',
    max_ms: '678',
  }
  assert.deepEqual(normalizeMetricRows({ result: row }), [{
    scope: 'TOTAL',
    invocations: 12,
    errors5xx: 1,
    errors429: 2,
    p95Ms: 345,
    maxMs: 678,
  }])
  assert.equal(normalizeMetricRows({ result: [row] }).length, 1)
})

test('keeps a normal window healthy', () => {
  assert.deepEqual(evaluateEdgeMetrics(healthyTotal, DEFAULT_THRESHOLDS), [])
})

test('detects 5xx, repeated 429, high p95 and invocation spikes', () => {
  const alerts = evaluateEdgeMetrics({
    ...healthyTotal,
    invocations: 1500,
    errors5xx: 1,
    errors429: 8,
    p95Ms: 2400,
  }, DEFAULT_THRESHOLDS)
  assert.deepEqual(alerts.map(alert => alert.code), [
    'edge-5xx',
    'edge-429',
    'edge-p95',
    'edge-invocations',
  ])
})

test('does not alert on p95 when the sample is too small', () => {
  const alerts = evaluateEdgeMetrics({
    ...healthyTotal,
    invocations: 3,
    p95Ms: 9000,
  }, DEFAULT_THRESHOLDS)
  assert.equal(alerts.some(alert => alert.code === 'edge-p95'), false)
})

test('accepts threshold overrides while rejecting invalid values', () => {
  assert.deepEqual(thresholdsFromEnv({
    EDGE_ALERT_WINDOW_MINUTES: '30',
    EDGE_ALERT_MAX_5XX: '2',
    EDGE_ALERT_MAX_429: 'bad',
    EDGE_ALERT_MAX_P95_MS: '2000',
    EDGE_ALERT_MAX_INVOCATIONS: '2500',
    EDGE_ALERT_MIN_INVOCATIONS_FOR_LATENCY: '50',
  }), {
    windowMinutes: 30,
    max5xx: 2,
    max429: DEFAULT_THRESHOLDS.max429,
    maxP95Ms: 2000,
    maxInvocations: 2500,
    minInvocationsForLatency: 50,
  })
})

test('builds a readable report with per-function metrics', () => {
  const report = buildEdgeAlertReport({
    result: [
      {
        scope: 'TOTAL',
        invocations: 25,
        errors_5xx: 0,
        errors_429: 0,
        p95_ms: 700,
        max_ms: 1100,
      },
      {
        scope: '/functions/v1/match-api',
        invocations: 20,
        errors_5xx: 0,
        errors_429: 0,
        p95_ms: 750,
        max_ms: 1100,
      },
    ],
  }, {
    checkedAt: new Date('2026-07-29T12:34:56.000Z'),
    thresholds: DEFAULT_THRESHOLDS,
    projectRef: 'kfacjvxzdtxybvxhfmzg',
  })
  assert.equal(report.healthy, true)
  assert.equal(report.window.end, '2026-07-29T12:34:00.000Z')
  assert.equal(report.functions[0].scope, '/functions/v1/match-api')
  assert.match(renderEdgeAlertMarkdown(report), /Supabase Edge — ✅ Normal/)
})

test('rejects an API payload carrying an error', () => {
  assert.throws(() => buildEdgeAlertReport({ result: [], error: 'query failed' }), /query failed/)
})
