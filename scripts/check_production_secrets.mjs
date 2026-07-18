import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../dist/', import.meta.url))
const catalog = JSON.parse(await readFile(new URL('../src/data/runtime.grid.catalog.json', import.meta.url), 'utf8'))
const gridIds = catalog.grids.map(grid => grid.id)
const textFiles = []

async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) await walk(path)
    else if (['.js', '.json', '.html', '.map'].includes(extname(entry.name))) textFiles.push(path)
  }
}

await walk(root)
const shipped = (await Promise.all(textFiles.map(path => readFile(path, 'utf8')))).join('\n')
assert.ok(!shipped.includes('runtime.grid.catalog'), 'Le nom du catalogue de solutions apparaît dans le build client.')
const leakedIds = gridIds.filter(id => shipped.includes(id))
assert.deepEqual(leakedIds, [], `Des grilles privées sont intégrées au navigateur : ${leakedIds.join(', ')}`)
console.log(`Sécurité du build : ${gridIds.length} identifiants privés absents de ${textFiles.length} fichiers client.`)
