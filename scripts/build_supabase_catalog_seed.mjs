import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const catalog = JSON.parse(readFileSync(resolve(root, 'src/data/runtime.grid.catalog.json'), 'utf8'))
const sqlString = value => `'${String(value).replaceAll("'", "''")}'`
const rows = catalog.grids.map(grid => {
  const columns = Number(grid.columns ?? grid.size)
  const rows = Number(grid.rows ?? grid.size)
  return `(${sqlString(grid.id)}, ${Number(catalog.version ?? 1)}, ${columns}, ${rows}, ${sqlString(JSON.stringify(grid))}::jsonb, true)`
})
const batchIndex = process.argv.indexOf('--batch')
if (batchIndex >= 0) {
  const batch = Math.max(0, Number(process.argv[batchIndex + 1]) || 0)
  const selected = rows.slice(batch * 4, batch * 4 + 4)
  const deactivate = batch === 0 ? 'update public.server_grid_catalog set active = false;\n' : ''
  process.stdout.write(`${deactivate}insert into public.server_grid_catalog(id, version, columns, rows, payload, active) values\n${selected.join(',\n')}\non conflict (id) do update set version=excluded.version, columns=excluded.columns, rows=excluded.rows, payload=excluded.payload, active=excluded.active;\n`)
  process.exit(0)
}
const expectedVersion = Number(catalog.version ?? 1)
const expectedCount = rows.length
const safeGridIndex = process.argv.indexOf('--safe-grid')
if (safeGridIndex >= 0) {
  const index = Math.max(0, Number(process.argv[safeGridIndex + 1]) || 0)
  const selected = rows.slice(index, index + 1)
  if (selected.length === 0) process.exit(0)
  process.stdout.write(`insert into public.server_grid_catalog(id, version, columns, rows, payload, active) values
${selected[0].replace(/, true\)$/, ', false)')}
on conflict (id) do update set
  version=excluded.version,
  columns=excluded.columns,
  rows=excluded.rows,
  payload=excluded.payload,
  active=server_grid_catalog.active;
`)
  process.exit(0)
}
const safeBatchIndex = process.argv.indexOf('--safe-batch')
if (safeBatchIndex >= 0) {
  const batch = Math.max(0, Number(process.argv[safeBatchIndex + 1]) || 0)
  const selected = rows.slice(batch * 4, batch * 4 + 4)
  if (selected.length === 0) process.exit(0)
  process.stdout.write(`insert into public.server_grid_catalog(id, version, columns, rows, payload, active) values
${selected.map(row => row.replace(/, true\)$/, ', false)')).join(',\n')}
on conflict (id) do update set
  version=excluded.version,
  columns=excluded.columns,
  rows=excluded.rows,
  payload=excluded.payload,
  active=server_grid_catalog.active;
`)
  process.exit(0)
}
if (process.argv.includes('--safe-finalize')) {
  const expectedIds = catalog.grids.map(grid => sqlString(grid.id)).join(', ')
  process.stdout.write(`begin;
set local lock_timeout = '5s';
set local statement_timeout = '30s';
update public.server_grid_catalog
set active = id in (${expectedIds});
do $catalog_check$
begin
  if (select count(*) from public.server_grid_catalog where active) <> ${expectedCount} then
    raise exception 'MotMan catalog publication expected ${expectedCount} active grids';
  end if;
  if exists (
    select 1 from public.server_grid_catalog
    where active and (version <> ${expectedVersion} or columns <> 7 or rows <> 8)
  ) then
    raise exception 'MotMan catalog publication contains an unexpected version or dimensions';
  end if;
  if exists (
    select 1 from public.server_grid_catalog
    where active and (
      payload->>'id' is distinct from id
      or jsonb_typeof(payload->'words') is distinct from 'array'
      or jsonb_array_length(payload->'words') = 0
    )
  ) then
    raise exception 'MotMan catalog publication contains an invalid payload';
  end if;
end
$catalog_check$;
commit;
`)
  process.exit(0)
}
const sql = `begin;
update public.server_grid_catalog set active = false;
insert into public.server_grid_catalog(id, version, columns, rows, payload, active) values
${rows.join(',\n')}
on conflict (id) do update set version=excluded.version, columns=excluded.columns, rows=excluded.rows, payload=excluded.payload, active=excluded.active;
do $catalog_check$
begin
  if (select count(*) from public.server_grid_catalog where active) <> ${expectedCount} then
    raise exception 'MotMan catalog publication expected ${expectedCount} active grids';
  end if;
  if exists (
    select 1 from public.server_grid_catalog
    where active and (version <> ${expectedVersion} or columns <> 7 or rows <> 8)
  ) then
    raise exception 'MotMan catalog publication contains an unexpected version or dimensions';
  end if;
end
$catalog_check$;
commit;
`
const target = resolve(root, 'output/supabase-grid-catalog.sql')
writeFileSync(target, sql, 'utf8')
console.log(JSON.stringify({ target, grids: rows.length, bytes: Buffer.byteLength(sql) }))
