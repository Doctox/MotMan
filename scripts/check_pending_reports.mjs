// Surveillance des signalements de joueurs.
//
// POURQUOI CE SCRIPT : le bouton « Signaler l'adversaire » écrit une ligne dans
// `public.reports` et s'arrête là. Aucun e-mail, aucune notification, aucun
// écran de modération. Un joueur harcelé pouvait donc signaler dans le vide.
// Ce script transforme la table en alerte : il compte les signalements non
// traités et laisse le workflow ouvrir une issue GitHub — le même canal que la
// surveillance des Edge Functions, donc aucun nouveau service ni secret.
//
// Il n'écrit RIEN et ne lit AUCUN détail de signalement : seulement des
// compteurs et des motifs. Le contenu rédigé par les joueurs reste en base ;
// il n'a pas à transiter par une issue GitHub, fût-elle privée.

import { mkdir, writeFile, appendFile } from 'node:fs/promises'
import path from 'node:path'

const MANAGEMENT_API = 'https://api.supabase.com'

/** Exécute une requête SQL via l'API de gestion Supabase (jeton déjà utilisé par la surveillance Edge). */
async function runQuery(projectRef, accessToken, query, fetchImpl = fetch) {
  const response = await fetchImpl(`${MANAGEMENT_API}/v1/projects/${projectRef}/database/query`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  })
  if (!response.ok) {
    throw new Error(`Supabase a refusé la requête (HTTP ${response.status}) : ${(await response.text()).slice(0, 300)}`)
  }
  return response.json()
}

/** Agrège les signalements non traités. Aucun détail rédigé par un joueur n'est remonté. */
export async function collectPendingReports(projectRef, accessToken, fetchImpl = fetch) {
  const rows = await runQuery(projectRef, accessToken, `
    select
      count(*)::int                                                as pending,
      count(*) filter (where created_at > now() - interval '24 hours')::int as last24h,
      min(created_at)                                              as oldest,
      coalesce(
        jsonb_object_agg(reason, n) filter (where reason is not null),
        '{}'::jsonb
      )                                                            as by_reason
    from (
      select reason, created_at, count(*) over (partition by reason)::int as n
      from public.reports
      where reviewed_at is null
    ) t;
  `, fetchImpl)

  const row = Array.isArray(rows) ? rows[0] ?? {} : {}
  const pending = Number(row.pending ?? 0)
  const oldest = row.oldest ? new Date(row.oldest) : null
  const ageHours = oldest ? Math.floor((Date.now() - oldest.getTime()) / 3_600_000) : 0

  return {
    generatedAt: new Date().toISOString(),
    pending,
    last24h: Number(row.last24h ?? 0),
    oldestIso: oldest ? oldest.toISOString() : null,
    oldestAgeHours: ageHours,
    byReason: row.by_reason ?? {},
    // Signature stable : évite de re-notifier tant que rien n'a changé.
    signature: `${pending}:${row.oldest ?? 'none'}`,
    hasPending: pending > 0,
  }
}

async function appendGithubValue(file, key, value) {
  if (!file) return
  await appendFile(file, `${key}=${value}\n`, 'utf8')
}

async function main(env = process.env) {
  const projectRef = env.SUPABASE_PROJECT_REF?.trim()
  const accessToken = env.SUPABASE_ACCESS_TOKEN?.trim()
  if (!projectRef || !accessToken) {
    throw new Error('SUPABASE_PROJECT_REF et SUPABASE_ACCESS_TOKEN sont requis.')
  }

  const report = await collectPendingReports(projectRef, accessToken)
  const outputPath = path.join('output', 'monitoring', 'player-reports.json')
  await mkdir(path.dirname(outputPath), { recursive: true })
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8')

  await appendGithubValue(env.GITHUB_OUTPUT, 'has_pending', String(report.hasPending))
  await appendGithubValue(env.GITHUB_OUTPUT, 'pending_count', String(report.pending))
  await appendGithubValue(env.GITHUB_OUTPUT, 'signature', report.signature)

  console.log(report.hasPending
    ? `[ALERTE] ${report.pending} signalement(s) non traité(s), le plus ancien depuis ${report.oldestAgeHours} h.`
    : '[OK] Aucun signalement en attente.')
}

// Ne s'exécute que si le script est lancé directement, jamais à l'import.
// (Un garde basé sur `endsWith(basename(argv[1]))` est piégeux : sous `node -e`,
//  `argv[1]` est absent, `basename('')` vaut '' et `endsWith('')` est toujours vrai.)
const lanceDirectement = process.argv[1]
  && import.meta.url === new URL(`file://${path.resolve(process.argv[1]).replaceAll('\\', '/')}`).href

if (lanceDirectement) {
  main().catch(error => {
    console.error(error.message)
    process.exitCode = 1
  })
}
