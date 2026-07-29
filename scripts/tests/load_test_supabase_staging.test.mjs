import assert from 'node:assert/strict'
import test from 'node:test'
import {
  PRODUCTION_PROJECT_REF,
  percentile,
  projectRefFromUrl,
  summarizeSamples,
  validateStagingConfig,
} from '../load_test_supabase_staging.mjs'

test('extracts a Supabase project ref and rejects unrelated hosts', () => {
  assert.equal(projectRefFromUrl('https://stagingref.supabase.co'), 'stagingref')
  assert.equal(projectRefFromUrl('https://example.com'), null)
  assert.equal(projectRefFromUrl('not-an-url'), null)
})

test('hard-blocks the production project', () => {
  assert.throws(() => validateStagingConfig({
    url: `https://${PRODUCTION_PROJECT_REF}.supabase.co`,
    projectRef: PRODUCTION_PROJECT_REF,
    publishableKey: 'publishable-key-long-enough',
    serviceRoleKey: 'service-role-key-long-enough',
    confirmation: `LOAD_TEST_${PRODUCTION_PROJECT_REF}`,
  }), /production/)
})

test('requires an exact staging confirmation', () => {
  assert.throws(() => validateStagingConfig({
    url: 'https://stagingref.supabase.co',
    projectRef: 'stagingref',
    publishableKey: 'publishable-key-long-enough',
    serviceRoleKey: 'service-role-key-long-enough',
    confirmation: 'LOAD_TEST_WRONG',
  }), /LOAD_TEST_stagingref/)
})

test('summarizes status, throughput and latency percentiles', () => {
  const samples = [
    { ok: true, status: 200, durationMs: 10 },
    { ok: true, status: 200, durationMs: 20 },
    { ok: false, status: 503, durationMs: 90, code: 'DOWN', message: 'nope' },
  ]
  assert.equal(percentile(samples.map(sample => sample.durationMs), 50), 20)
  assert.equal(percentile(samples.map(sample => sample.durationMs), 95), 90)
  assert.deepEqual(summarizeSamples(samples, 1000), {
    requests: 3,
    successes: 2,
    failures: 1,
    errorRatePercent: 33.33,
    statusCounts: { 200: 2, 503: 1 },
    latencyMs: { min: 10, p50: 20, p95: 90, p99: 90, max: 90 },
    throughputPerSecond: 3,
    failuresPreview: [{ status: 503, code: 'DOWN', message: 'nope' }],
  })
})
