import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createServer } from 'vite'

const catalog = JSON.parse(await readFile(new URL('../src/data/grid.catalog.json', import.meta.url), 'utf8'))
const blacklist = JSON.parse(await readFile(new URL('../src/data/editorial.blacklist.json', import.meta.url), 'utf8'))

const vite = await createServer({
  appType: 'custom',
  configFile: false,
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const dimensionsModule = await vite.ssrLoadModule('/src/gridDimensions.ts')
  const generatorModule = await vite.ssrLoadModule('/src/generator.ts')
  const policyModule = await vite.ssrLoadModule('/src/gridCatalogPolicy.ts')
  const { gridCellCoordinates, gridCellIndex, resolveGridDimensions } = dimensionsModule
  const { generateGrid, generateGridById, validateGrid } = generatorModule
  const { isCatalogGridPlayable } = policyModule

  assert.deepEqual(resolveGridDimensions({ size: 9 }), { columns: 9, rows: 9 })
  assert.deepEqual(resolveGridDimensions({ columns: 9, rows: 10 }), { columns: 9, rows: 10 })
  assert.deepEqual(resolveGridDimensions({ size: 9, rows: 10 }), { columns: 9, rows: 10 })
  assert.equal(gridCellIndex({ columns: 9, rows: 10 }, 9, 8), 89)
  assert.deepEqual(gridCellCoordinates({ columns: 9, rows: 10 }, 89), { row: 9, column: 8 })
  assert.throws(() => resolveGridDimensions({ columns: 9 }), /invalides/)

  const cells = Array.from({ length: 90 }, () => ({ kind: 'clue', entries: [] }))
  const answer = 'CHAT'
  const word = { answer, clue: 'Félin', difficulty: 1, theme: 'test', id: 'pilot:word:1', row: 1, col: 1, direction: 'across' }
  answer.split('').forEach((solution, offset) => {
    cells[gridCellIndex({ columns: 9, rows: 10 }, 1, 1 + offset)] = { kind: 'letter', solution, wordIds: [word.id] }
  })
  const validation = validateGrid({ columns: 9, rows: 10, cells, words: [word] })
  assert.equal(validation.valid, true, validation.errors.join('; '))
  assert.equal(validation.score, 100)

  assert.ok(catalog.version >= 4)
  assert.ok(catalog.grids.length >= 30)
  assert.ok(catalog.grids.every(grid => grid.columns === 9 && grid.rows === 10 && grid.size === undefined))
  assert.ok(catalog.grids.every(grid => grid.difficulty === undefined))
  assert.ok(catalog.grids.reduce((count, grid) => count + grid.words.filter(word => word.image).length, 0) >= 48)
  assert.equal(new Set(catalog.grids.map(grid => grid.id)).size, catalog.grids.length)
  const playableSources = catalog.grids.filter(isCatalogGridPlayable)
  const storedQuarantines = catalog.grids.filter(grid => blacklist.quarantinedGridIds.includes(grid.id))
  assert.equal(playableSources.length, catalog.grids.length - storedQuarantines.length)
  assert.ok(playableSources.length > 0)
  for (const source of playableSources) {
    const generated = await generateGridById(source.id)
    assert.equal(generated.cells.length, 90)
    assert.equal(generated.validation.valid, true, `${source.id}: ${generated.validation.errors.join('; ')}`)
    assert.equal(generated.version, `offline-catalog-${catalog.version}`)
  }
  const chosenIds = new Set()
  for (let seed = 0; seed < playableSources.length; seed += 1) {
    chosenIds.add((await generateGrid(seed, seed % 2 ? 'easy' : 'hard')).id)
  }
  assert.equal(chosenIds.size, playableSources.length)
  const excludedIds = playableSources.slice(0, 12).map(grid => grid.id)
  const availableSources = playableSources.filter(grid => !excludedIds.includes(grid.id))
  const chosenAfterExclusion = new Set()
  for (let seed = 0; seed < availableSources.length; seed += 1) {
    const selected = await generateGrid(seed, 'normal', excludedIds)
    assert.ok(!excludedIds.includes(selected.id))
    chosenAfterExclusion.add(selected.id)
  }
  assert.equal(chosenAfterExclusion.size, availableSources.length)

  console.log(`Catalogue v${catalog.version} : ${catalog.grids.length} grilles 9x10 stockées, ${playableSources.length} jouables, toutes atteignables par le tirage et indexation jusqu'à 89 validée.`)
} finally {
  await vite.close()
}
