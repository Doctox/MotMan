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
const sql = `update public.server_grid_catalog set active = false;\ninsert into public.server_grid_catalog(id, version, columns, rows, payload, active) values\n${rows.join(',\n')}\non conflict (id) do update set version=excluded.version, columns=excluded.columns, rows=excluded.rows, payload=excluded.payload, active=excluded.active;\n`
const target = resolve(root, 'output/supabase-grid-catalog.sql')
writeFileSync(target, sql, 'utf8')
console.log(JSON.stringify({ target, grids: rows.length, bytes: Buffer.byteLength(sql) }))
